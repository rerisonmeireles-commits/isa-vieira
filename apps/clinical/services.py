"""Services do domínio clínico.
Funções de negócio: ciclo de vida da Avaliação (L/P/I), criação de
Evolução SOAP vinculada ao atendimento e registro de acesso ao
Prontuário com trilha de auditoria.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.audit.models import LogAuditoria
from apps.attendance.models import Atendimento
from apps.clinical.exceptions import (
    AvaliacaoStatusInvalidoError,
    PermissaoClinicaError,
    ProntuarioInexistenteError,
    EvolucaoAtendimentoError,
)
from apps.clinical.models import Avaliacao, Evolucao, Prontuario
from apps.accounts.constants import (
    GRUPOS_CLINICO_EDITAR,
    GRUPOS_CLINICO_LIBERAR,
)

GRUPOS_QUE_EDITAM = set(GRUPOS_CLINICO_EDITAR)
GRUPOS_QUE_LIBERAM = set(GRUPOS_CLINICO_LIBERAR)


def _pode_editar(usuario):
    """Quem pode criar/editar conteúdo clínico (avaliações, prontuário)."""
    if usuario.is_superuser:
        return True
    return usuario.groups.filter(name__in=GRUPOS_QUE_EDITAM).exists()


def _pode_liberar(usuario):
    """Quem pode executar ações de ciclo de vida (liberar/inativar)."""
    if usuario.is_superuser:
        return True
    return usuario.groups.filter(name__in=GRUPOS_QUE_LIBERAM).exists()


# ---------------------------------------------------------------------------
# Ciclo de vida da Avaliação - L/P/I
# ---------------------------------------------------------------------------
TRANSICOES_AVALIACAO = {
    Avaliacao.Status.PENDENTE: {Avaliacao.Status.LIBERADA, Avaliacao.Status.INATIVADA},
    Avaliacao.Status.LIBERADA: {Avaliacao.Status.INATIVADA},
    Avaliacao.Status.INATIVADA: set(),  # terminal - reativação exige nova avaliação
}

TOTAL_ITENS_FIM = 18  # 13 motores + 5 cognitivos


def fim_preenchidos(avaliacao):
    """Quantos dos 18 itens do FIM estão pontuados (fonte estruturada: itens_fim)."""
    return avaliacao.itens_fim.filter(pontuacao__isnull=False).count()


@transaction.atomic
def liberar_avaliacao(avaliacao_id, usuario):
    """P → L. Exige Fisioterapeuta/Administrador e preenche o rastreio.
    Item 6: se o FIM estiver incompleto, anexa o flag transitório
    "fim_aviso" - a view exibe o aviso; a liberação NÃO é bloqueada.
    """
    avaliacao = Avaliacao.objects.select_for_update().get(pk=avaliacao_id)
    if not _pode_liberar(usuario):
        raise PermissaoClinicaError(
            "Apenas Fisioterapeuta ou Administrador podem liberar avaliações."
        )
    if Avaliacao.Status.LIBERADA not in TRANSICOES_AVALIACAO.get(
        avaliacao.status, set()
    ):
        raise AvaliacaoStatusInvalidoError(
            f"Transição inválida: {avaliacao.status} → LIBERADA."
        )

    # Item 6 - contagem ANTES de mudar o status (a fonte é itens_fim)
    preenchidos = fim_preenchidos(avaliacao)

    antes = {"status": avaliacao.status}
    avaliacao.status = Avaliacao.Status.LIBERADA
    avaliacao.liberado_por = usuario
    avaliacao.liberado_em = timezone.now()
    avaliacao.save(update_fields=["status", "liberado_por", "liberado_em", "updated_at"])

    # Flag transitório - NÃO é campo do model, nunca vai para o banco.
    # A view lê com getattr(avaliacao_liberada, "fim_aviso", None).
    if preenchidos < TOTAL_ITENS_FIM:
        avaliacao.fim_aviso = f"FIM incompleto: {preenchidos}/{TOTAL_ITENS_FIM}"

    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.UPDATE,
        tabela="avaliacao",
        registro_id=avaliacao.pk,
        dados_antes=antes,
        dados_depois={
            "status": avaliacao.status,
            "fim_preenchidos": preenchidos,
        },
    )
    return avaliacao


@transaction.atomic
def inativar_avaliacao(avaliacao_id, usuario, motivo=None):
    """P ou L → I. Exige autorização e preenche o rastreio de inativação."""
    avaliacao = Avaliacao.objects.select_for_update().get(pk=avaliacao_id)
    if not _pode_liberar(usuario):
        raise PermissaoClinicaError (
            "Apenas Fisioterapeuta ou Administrador podem inativar avaliações."
        )
    if Avaliacao.Status.INATIVADA not in TRANSICOES_AVALIACAO.get(
        avaliacao.status, set()
    ):
        raise AvaliacaoStatusInvalidoError(
            f"Transição inválida: {avaliacao.status} → INATIVADA."
        )
    antes = {"status": avaliacao.status}
    avaliacao.status = Avaliacao.Status.INATIVADA
    avaliacao.inativado_por = usuario
    avaliacao.inativado_em = timezone.now()
    if motivo:
        avaliacao.observacoes = motivo
    avaliacao.save(update_fields=["status", "inativado_por", "inativado_em",
                                  "observacoes", "updated_at"])
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.UPDATE,
        tabela="avaliacao",
        registro_id=avaliacao.pk,
        dados_antes=antes,
        dados_depois={"status": avaliacao.status, "motivo": motivo},
    )
    return avaliacao


# ---------------------------------------------------------------------------
# Evolução SOAP - vinculada ao atendimento
# ---------------------------------------------------------------------------
def atendimento_em_curso(profissional, paciente=None):
    """Atendimento EM_ANDAMENTO do profissional - a posse ativa."""
    qs = Atendimento.objects.filter(
        profissional=profissional,
        status=Atendimento.Status.EM_ANDAMENTO,
    )
    if paciente is not None:
        qs = qs.filter(paciente=paciente)
    return qs.order_by("-data_inicio").first()


@transaction.atomic
def criar_evolucao(usuario, paciente, *, atendimento, **campos):
    """Cria Evolução SOAP com posse do atendimento.
    Regras de posse:
      1. O atendimento é obrigatório - toda evolução pertence a uma sessão.
      2. O atendimento precisa estar EM_ANDAMENTO.
      3. O profissional do atendimento é o autor da evolução.
      4. O atendimento pertence ao mesmo paciente.
    """
    profissional = getattr(usuario, "profissional", None)
    if profissional is None:
        raise PermissaoClinicaError (
            "Somente profissionais clínicos registram evoluções."
        )
    if atendimento is None:
        raise EvolucaoAtendimentoError(
            "A evolução precisa estar vinculada a um atendimento em andamento."
        )
    if atendimento.status != Atendimento.Status.EM_ANDAMENTO:
        raise EvolucaoAtendimentoError(
            "Só é possível evoluir um atendimento em andamento "
            f"(status atual: {atendimento.get_status_display()})."
        )
    if atendimento.profissional_id != profissional.pk:
        raise PermissaoClinicaError (
            "Apenas o profissional responsável pelo atendimento pode evoluí-lo."
        )
    if atendimento.paciente_id != paciente.pk:
        raise EvolucaoAtendimentoError(
            "O atendimento pertence a outro paciente."
        )
    evolucao = Evolucao.objects.create(
        paciente=paciente,
        profissional=profissional,
        atendimento=atendimento,
        **campos,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.CREATE,
        tabela="evolucao",
        registro_id=evolucao.pk,
        dados_depois={
            "atendimento_id": atendimento.pk,
            "paciente_id": paciente.pk,
        },
    )
    return evolucao


# ---------------------------------------------------------------------------
# Acesso ao Prontuário - log de auditoria obrigatório
# ---------------------------------------------------------------------------
def registrar_acesso_prontuario(usuario, paciente, motivo, request=None):
    """Registra cada visualização do prontuário (LGPD/COFFITO).
    O motivo é obrigatório - acesso justificado. Retorna o prontuário
    para a view usar diretamente.
    """
    prontuario = Prontuario.objects.filter(paciente=paciente).first()
    if prontuario is None:
        raise ProntuarioInexistenteError(
            f"Paciente {paciente} não possui prontuário."
        )
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.ACESSO_PRONTUARIO,
        tabela="prontuario",
        registro_id=prontuario.pk,
        motivo=motivo,
        ip=request.META.get("REMOTE_ADDR") if request else None,
        user_agent=request.META.get("HTTP_USER_AGENT") if request else None,
    )
    return prontuario


# ---------------------------------------------------------------------------
# Edição de Avaliação Pendente (rascunho)
# ---------------------------------------------------------------------------
@transaction.atomic
def salvar_avaliacao(avaliacao, usuario, dados_validados):
    """Salva alterações em Avaliação Pendente (rascunho).
    Liberada e Inativada são imutáveis - correção exige inativar + nova.
    """
    if not _pode_editar(usuario):
        raise PermissaoClinicaError (
            "Apenas Fisioterapeuta ou Administrador podem editar avaliações."
        )
    if avaliacao.status != Avaliacao.Status.PENDENTE:
        raise AvaliacaoStatusInvalidoError(
            "Apenas avaliações Pendentes podem ser editadas. "
            "Para corrigir uma Liberada, inative-a e crie uma nova."
        )
    antes = {
        "queixa_principal": avaliacao.queixa_principal,
        "hipotese_diagnostica": avaliacao.hipotese_diagnostica,
    }
    for campo, valor in dados_validados.items():
        setattr(avaliacao, campo, valor)
    avaliacao.save()
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.UPDATE,
        tabela="avaliacao",
        registro_id=avaliacao.pk,
        dados_antes=antes,
    )
    return avaliacao


# ---------------------------------------------------------------------------
# Edição de Evolução SOAP
# ---------------------------------------------------------------------------
JANELA_EDICAO_EVOLUCAO = timedelta(hours=24)


def pode_editar_evolucao(evolucao, usuario):
    """Editável só pelo autor, dentro de 24h da criação."""
    profissional = getattr(usuario, "profissional", None)
    if profissional is None or evolucao.profissional_id != profissional.pk:
        return False
    return timezone.now() - evolucao.created_at <= JANELA_EDICAO_EVOLUCAO


@transaction.atomic
def salvar_evolucao(evolucao, usuario, dados_validados):
    """Salva alterações na própria evolução dentro da janela de 24h."""
    if not pode_editar_evolucao(evolucao, usuario):
        raise PermissaoClinicaError(
            "Evolução editável apenas pelo autor, até 24h após a criação. "
            "Para corrigir depois, registre uma nova evolução."
        )
    antes = {"subjetivo": evolucao.subjetivo, "plano": evolucao.plano}
    for campo, valor in dados_validados.items():
        setattr(evolucao, campo, valor)
    evolucao.save()
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.UPDATE,
        tabela="evolucao",
        registro_id=evolucao.pk,
        dados_antes=antes,
    )
    return evolucao


@transaction.atomic
def editar_prontuario(prontuario, usuario, dados_validados):
    """Atualiza o container clínico. Restrito a Fisioterapeuta/Administrador."""
    if not _pode_editar(usuario):
        raise PermissaoClinicaError(
            "Apenas Fisioterapeuta ou Administrador podem editar o prontuário."
        )
    campos = list(dados_validados.keys())
    antes = {c: getattr(prontuario, c) for c in campos}
    for campo, valor in dados_validados.items():
        setattr(prontuario, campo, valor)
    prontuario.save(update_fields=campos + ["updated_at"])
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.UPDATE,
        tabela="prontuario",
        registro_id=prontuario.pk,
        dados_antes=antes,
        dados_depois=dados_validados,
    )
    return prontuario
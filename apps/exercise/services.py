from django.db import transaction
from django.utils import timezone

from apps.accounts.constants import (
    GRUPOS_EXERCICIOS_EDITAR,
    GRUPOS_EXERCICIOS_VER,
)
from apps.audit.models import LogAuditoria
from apps.exercise.models import (
    ExecucaoExercicio,
    Exercicio,
    Prescricao,
    PrescricaoExercicio,
)


class PermissaoExercicioError(Exception):
    pass


class ExercicioStatusInvalidoError(Exception):
    pass


def _pode_ver(usuario):
    if usuario.is_superuser:
        return True
    return usuario.groups.filter(name__in=GRUPOS_EXERCICIOS_VER).exists()


def _pode_editar(usuario):
    if usuario.is_superuser:
        return True
    return usuario.groups.filter(name__in=GRUPOS_EXERCICIOS_EDITAR).exists()


def _profissional_do_usuario(usuario):
    """Resolve o Profissional vinculado ao usuário logado."""
    return getattr(usuario, "profissional", None)


def _para_log(valor):
    """Arquivos (FieldFile/UploadedFile) viram o caminho no storage; demais valores passam direto."""
    nome = getattr(valor, "name", None)
    return nome if isinstance(nome, str) else valor

# ---------------------------------------------------------------------------
# Catálogo cinesiológico - Exercicio
# ---------------------------------------------------------------------------

@transaction.atomic
def criar_exercicio(usuario, dados):
    if not _pode_editar(usuario):
        raise PermissaoExercicioError(
            "Apenas Fisioterapeuta ou Administrador podem cadastrar exercícios."
        )
    exercicio = Exercicio.objects.create(**dados)
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.CREATE,
        tabela="exercicio",
        registro_id=exercicio.pk,
        dados_depois={"nome": exercicio.nome, "categoria": exercicio.categoria},
    )
    return exercicio


@transaction.atomic
def atualizar_exercicio(exercicio, usuario, dados):
    if not _pode_editar(usuario):
        raise PermissaoExercicioError(
            "Apenas Fisioterapeuta ou Administrador podem editar exercícios."
        )

    # Contrato do ClearableFileInput: com imagem já salva, o checkbox "Limpar"
    # marcado entrega False em cleaned_data - significa "apagar a imagem".
    # O ModelForm.save() trata isso internamente; este service aplica os dados
    # à mão, então implementa o mesmo comportamento:
    if dados.get("imagem") is False:
        if exercicio.imagem:
            exercicio.imagem.delete(save=False)  # remove o arquivo do storage
        dados["imagem"] = None                   # estado final do campo

    campos = list(dados.keys())
    antes = {c: getattr(exercicio, c) for c in campos}
    for campo, valor in dados.items():
        setattr(exercicio, campo, valor)
    exercicio.save(update_fields=campos + ["updated_at"])

    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.UPDATE,
        tabela="exercicio",
        registro_id=exercicio.pk,
        dados_antes={c: _para_log(v) for c, v in antes.items()},
        dados_depois={c: _para_log(v) for c, v in dados.items()},
    )
    return exercicio

@transaction.atomic
def inativar_exercicio(exercicio, usuario):
    """Soft: ativo=False. Nunca hard delete - preserva prescrições vinculadas."""
    if not _pode_editar(usuario):
        raise PermissaoExercicioError(
            "Apenas Fisioterapeuta ou Administrador podem inativar exercícios."
        )
    exercicio.ativo = False
    exercicio.save(update_fields=["ativo", "updated_at"])
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.UPDATE,
        tabela="exercicio",
        registro_id=exercicio.pk,
        dados_antes={"ativo": True},
        dados_depois={"ativo": False},
    )
    return exercicio


# ---------------------------------------------------------------------------
# Prescrição - ciclo de vida ATIVA / ENCERRADA / CANCELADA
# ---------------------------------------------------------------------------

TRANSICOES_PRESCRICAO = {
    Prescricao.Status.ATIVA: {
        Prescricao.Status.ENCERRADA,
        Prescricao.Status.CANCELADA,
    },
    Prescricao.Status.ENCERRADA: set(),
    Prescricao.Status.CANCELADA: set(),
}


@transaction.atomic
def criar_prescricao(usuario, dados):
    """Cria prescrição ATIVA. `dados` contém paciente + campos do formulário."""
    if not _pode_editar(usuario):
        raise PermissaoExercicioError(
            "Apenas Fisioterapeuta ou Administrador podem prescrever exercícios."
        )
    profissional = _profissional_do_usuario(usuario)
    if profissional is None:
        raise PermissaoExercicioError(
            "Somente profissionais clínicos podem criar prescrições."
        )

    paciente = dados.pop("paciente")
    prescricao = Prescricao.objects.create(
        paciente=paciente,
        profissional=profissional,
        **dados,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.CREATE,
        tabela="prescricao",
        registro_id=prescricao.pk,
        dados_depois={"paciente_id": paciente.pk, "status": prescricao.status},
    )
    return prescricao


@transaction.atomic
def normalizar_ordem(prescricao):
    """Renumera os itens ativos sequencialmente (1..n).

    Usa update em duas fases (ordem negativa temporária) para não violar a
    UniqueConstraint (prescricao, ordem) durante a renumeração.
    """
    itens = list(prescricao.itens.all())
    for i, item in enumerate(itens, start=1):
        PrescricaoExercicio.objects.filter(pk=item.pk).update(ordem=-i)
    for i, item in enumerate(itens, start=1):
        PrescricaoExercicio.objects.filter(pk=item.pk).update(ordem=i)


@transaction.atomic
def reordenar_itens(prescricao, usuario, nova_ordem_ids):    
    """nova_ordem: lista de ids na nova sequência desejada."""
    if not _pode_editar(usuario):
        raise PermissaoExercicioError(
            "Apenas Fisioterapeuta ou Administrador podem reordenar itens."
        )
    if prescricao.status != Prescricao.Status.ATIVA:
        raise ExercicioStatusInvalidoError(
            "Apenas prescrições Ativas podem ter itens reordenados."
        )
    itens = list(prescricao.itens.all())
    ids_atuais = {i.pk for i in itens}
    if set(nova_ordem_ids) != ids_atuais or len(nova_ordem_ids) != len(itens):
        raise ExercicioStatusInvalidoError(
            "A ordem fornecida não corresponde aos itens da prescrição."
        )
    # Fase 1: desloca para um intervalo alto (fora do range real 1..N),
    # evitando colisão com a constraint única sem violar o CHECK ordem >= 0.
    OFFSET = 1000
    for i, item_id in enumerate(nova_ordem_ids):
        PrescricaoExercicio.objects.filter(pk=item_id).update(ordem=OFFSET + i)

    # Fase 2: numeração definitiva.
    for i, item_id in enumerate(nova_ordem_ids, start=1):
        PrescricaoExercicio.objects.filter(pk=item_id).update(ordem=i)

    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.UPDATE,
        tabela="prescricao_exercicio",
        registro_id=prescricao.pk,
        dados_depois={"nova_ordem": nova_ordem_ids},
    )


@transaction.atomic
def encerrar_prescricao(prescricao, usuario, motivo=None):
    if not _pode_editar(usuario):
        raise PermissaoExercicioError(
            "Apenas Fisioterapeuta ou Administrador podem encerrar prescrições."
        )
    if Prescricao.Status.ENCERRADA not in TRANSICOES_PRESCRICAO.get(
        prescricao.status, set()
    ):
        raise ExercicioStatusInvalidoError(
            f"Transição inválida: {prescricao.get_status_display()} → Encerrada."
        )
    antes = {"status": prescricao.status}
    prescricao.status = Prescricao.Status.ENCERRADA
    if motivo:
        prescricao.motivo_encerramento = motivo
    prescricao.save(update_fields=["status", "motivo_encerramento", "updated_at"])
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.UPDATE,
        tabela="prescricao",
        registro_id=prescricao.pk,
        dados_antes=antes,
        dados_depois={"status": prescricao.status, "motivo": motivo},
    )
    return prescricao


@transaction.atomic
def cancelar_prescricao(prescricao, usuario, motivo=None):
    if not _pode_editar(usuario):
        raise PermissaoExercicioError(
            "Apenas Fisioterapeuta ou Administrador podem cancelar prescrições."
        )
    if Prescricao.Status.CANCELADA not in TRANSICOES_PRESCRICAO.get(
        prescricao.status, set()
    ):
        raise ExercicioStatusInvalidoError(
            f"Transição inválida: {prescricao.get_status_display()} → Cancelada."
        )
    antes = {"status": prescricao.status}
    prescricao.status = Prescricao.Status.CANCELADA
    if motivo:
        prescricao.motivo_encerramento = motivo
    prescricao.save(update_fields=["status", "motivo_encerramento", "updated_at"])
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.UPDATE,
        tabela="prescricao",
        registro_id=prescricao.pk,
        dados_antes=antes,
        dados_depois={"status": prescricao.status, "motivo": motivo},
    )
    return prescricao


# ---------------------------------------------------------------------------
# Execução de exercício
# ---------------------------------------------------------------------------

@transaction.atomic
def registrar_execucao_clinica(usuario, prescricao_exercicio, paciente, dados):
    if prescricao_exercicio.prescricao.status != Prescricao.Status.ATIVA:
        raise ExercicioStatusInvalidoError(
            "Só é possível registrar execução em prescrição Ativa. "
            f"Status atual: {prescricao_exercicio.prescricao.get_status_display()}."
        )    
    if prescricao_exercicio.prescricao.status != Prescricao.Status.ATIVA:
        raise ExercicioStatusInvalidoError(
            "Só é possível registrar execução em prescrição Ativa. "
            f"Status atual: {prescricao_exercicio.prescricao.get_status_display()}."
        )   
     
    """Execução registrada pela clínica (criado_via=CLINICA)."""
    if not _pode_editar(usuario):
        raise PermissaoExercicioError(
            "Apenas Fisioterapeuta ou Administrador podem registrar execuções."
        )
    execucao = ExecucaoExercicio.objects.create(
        prescricao_exercicio=prescricao_exercicio,
        paciente=paciente,
        criado_via=ExecucaoExercicio.CriadoVia.CLINICA,
        **dados,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.CREATE,
        tabela="execucao_exercicio",
        registro_id=execucao.pk,
        dados_depois={"item_id": prescricao_exercicio.pk, "realizado": execucao.realizado},
    )
    return execucao


@transaction.atomic
def registrar_execucao_portal(usuario, prescricao_exercicio, dados):
    """Execução registrada pelo próprio paciente no Portal (criado_via=PORTAL).

    A autorização aqui é por posse: o usuário logado DEVE ser o paciente dono
    da prescrição - não usa grupo RBAC.
    """
    paciente = getattr(usuario, "paciente", None)
    if paciente is None or paciente.pk != prescricao_exercicio.prescricao.paciente_id:
        raise PermissaoExercicioError(
            "O paciente só pode registrar execução da própria prescrição."
        )
    return ExecucaoExercicio.objects.create(
        prescricao_exercicio=prescricao_exercicio,
        paciente=paciente,
        criado_via=ExecucaoExercicio.CriadoVia.PORTAL,
        **dados,
    )

@transaction.atomic
def editar_prescricao(usuario, prescricao, dados):
    """Atualiza prescrição ATIVA (campos do formulário principal)."""
    if not _pode_editar(usuario):
        raise PermissaoExercicioError(
            "Apenas Fisioterapeuta ou Administrador podem editar prescrições."
        )
    if prescricao.status != Prescricao.Status.ATIVA:
        raise ExercicioStatusInvalidoError(
            "Apenas prescrições Ativas podem ser editadas."
        )
    campos = list(dados.keys())
    antes = {c: getattr(prescricao, c) for c in campos}
    for campo, valor in dados.items():
        setattr(prescricao, campo, valor)
    prescricao.save(update_fields=campos + ["updated_at"])
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=LogAuditoria.Acao.UPDATE,
        tabela="prescricao",
        registro_id=prescricao.pk,
        dados_antes=antes,
        dados_depois=dados,
    )
    return prescricao
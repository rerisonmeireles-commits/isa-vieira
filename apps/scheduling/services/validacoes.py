"""Validações de negócio da agenda - apps/scheduling/services/validacoes.py

Funções puras (não alteram estado) - recebem dados, levantam AgendaError.
Usadas tanto na geração de slots quanto na reserva, garantindo que a mesma
regra valha nos dois caminhos.

GUARDA DE COLAGEM: este arquivo NÃO define models. Se você encontrar
`class Agenda(models.Model)` ou `class Agendamento`, o conteúdo foi colado
em apps/scheduling/models.py por engano.
"""

from datetime import time, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.clinic.models import Configuracao
from apps.registry.models import Feriado
from apps.scheduling.exceptions import (
    AgendaBloqueadaError,
    ConflitoProfissionalError,
    ConflitoSalaError,
    FeriadoError,
    ForaDaJanelaAgendamentoError,
    ForaDoHorarioFuncionamentoError,
    ProfissionalIndisponivelError,
)
from apps.scheduling.models import Agendamento, SlotAgenda

# Status que efetivamente ocupam o horário (bloqueiam conflito).
# Inclui FALTOU: a constraint uq_slot_agendamento_ativo e a grade tratam
# FALTOU como ocupando o slot - a validação precisa alinhar.
STATUS_QUE_OCUPAM = (
    Agendamento.Status.AGENDADO,
    Agendamento.Status.CONFIRMADO,
    Agendamento.Status.EM_ATENDIMENTO,
    Agendamento.Status.ATENDIDO,
    Agendamento.Status.FALTOU,
)

# ALIAS, não redeclaração. O conjunto canônico vive em
# Agendamento.STATUS_LIBERAM_SLOT; duplicá-lo aqui criava uma terceira fonte
# de verdade para o mesmo conceito.
STATUS_QUE_LIBERAM = Agendamento.STATUS_LIBERAM_SLOT

# UF assumida quando nem Configuracao nem Clinica têm UF cadastrada.
# Explícito para não ser um literal solto no meio do código (V4).
UF_PADRAO = "SP"

# Máquina de estados - UMA única fonte de verdade.
# EM_ATENDIMENTO NÃO permite CANCELADO: o caminho de saída correto é o
# Finalizar (ATENDIDO) ou marcar FALTOU. Decisão alinhada com a UI, que
# esconde o Cancelar durante o atendimento.
TRANSICOES_VALIDAS = {
    Agendamento.Status.AGENDADO: {
        Agendamento.Status.CONFIRMADO,
        Agendamento.Status.CANCELADO,
        Agendamento.Status.REMARCADO,
        Agendamento.Status.FALTOU,
    },
    Agendamento.Status.CONFIRMADO: {
        Agendamento.Status.EM_ATENDIMENTO,
        Agendamento.Status.CANCELADO,
        Agendamento.Status.REMARCADO,
        Agendamento.Status.FALTOU,
    },
    Agendamento.Status.EM_ATENDIMENTO: {
        Agendamento.Status.ATENDIDO,
        Agendamento.Status.FALTOU,
    },
    Agendamento.Status.ATENDIDO: set(),
    Agendamento.Status.CANCELADO: set(),
    Agendamento.Status.FALTOU: set(),
    Agendamento.Status.REMARCADO: set(),
}


def intervalos_sobrepoem(inicio_a, fim_a, inicio_b, fim_b):
    """Dois intervalos [inicio, fim) se sobrepõem se um começa antes do outro terminar."""
    return inicio_a < fim_b and inicio_b < fim_a


def obter_configuracao():
    """Configuração da clínica (single-tenant). Pode ser None antes do cadastro."""
    return Configuracao.objects.select_related("clinica").first()


# ---------------------------------------------------------------------------
# Validações de janela e calendário
# ---------------------------------------------------------------------------


def validar_janela_agendamento(data, configuracao=None):
    """Impede agendamento no passado ou além do horizonte permitido."""
    configuracao = configuracao or obter_configuracao()
    hoje = timezone.localdate()

    if data < hoje:
        raise ForaDaJanelaAgendamentoError(
            "Não é possível agendar em uma data passada."
        )

    if configuracao and configuracao.dias_max_antecedencia:
        limite = hoje + timedelta(days=configuracao.dias_max_antecedencia)
        if data > limite:
            raise ForaDaJanelaAgendamentoError(
                f"Agendamento permitido apenas até {limite:%d/%m/%Y} "
                f"({configuracao.dias_max_antecedencia} dias de antecedência)."
            )


def validar_horario_funcionamento(data, hora_inicio, hora_fim, configuracao=None):
    """O atendimento tem de caber dentro do horário de funcionamento da clínica.

    Recebe os limites do ATENDIMENTO (bloco inteiro), não do slot âncora.
    """
    configuracao = configuracao or obter_configuracao()
    if not configuracao:
        return  # sem configuração cadastrada, não há restrição a aplicar

    if hora_inicio < configuracao.hora_abertura or hora_fim > configuracao.hora_fechamento:
        raise ForaDoHorarioFuncionamentoError(
            f"Horário fora do funcionamento da clínica "
            f"({configuracao.hora_abertura:%H:%M} às {configuracao.hora_fechamento:%H:%M})."
        )


# ---------------------------------------------------------------------------
# Feriado - usa os helpers de localidade (UF da clínica + cidade).
# ---------------------------------------------------------------------------


def _uf_clinica(configuracao):
    """UF da clínica: Configuracao.uf → Clinica.uf → UF_PADRAO."""
    if configuracao and getattr(configuracao, "uf", None):
        return configuracao.uf
    if configuracao and configuracao.clinica_id and configuracao.clinica.uf:
        return configuracao.clinica.uf
    return UF_PADRAO


def _cidade_clinica(configuracao):
    if configuracao and configuracao.clinica_id:
        return (configuracao.clinica.cidade or "").strip() or None
    return None


def _filtro_local_feriado(uf_clinica, cidade):
    """Feriados estaduais/municipais aplicáveis à UF (e cidade) da clínica."""
    estadual = Q(tipo=Feriado.Tipo.ESTADUAL, uf=uf_clinica)
    municipal = Q(tipo=Feriado.Tipo.MUNICIPAL, uf=uf_clinica)

    if cidade:
        municipal &= (Q(municipio__isnull=True) | Q(municipio__iexact=cidade))
    # V6 (decisão pendente): sem cidade cadastrada, o filtro acima NÃO é
    # aplicado e qualquer feriado municipal da UF bloqueia a clínica.
    # Para restringir, troque o `if` por `municipal &= Q(municipio__iexact=cidade or "")`.
    # A escolha atual privilegia bloquear demais em vez de trabalhar em feriado.

    return estadual | municipal


def _eh_feriado(data, uf_clinica, cidade=None):
    """True se a data é feriado aplicável à clínica (recorrentes incluídos)."""
    local = _filtro_local_feriado(uf_clinica, cidade)

    if Feriado.objects.filter(
        Q(tipo=Feriado.Tipo.NACIONAL, data=data) | Q(local, data=data)
    ).exists():
        return True

    # Recorrentes: casa por MÊS/DIA, ignorando o ano - vale para todos os anos.
    # Confirmado em runtime: um registro com recorrente=True e data 2026-12-23
    # bloqueia 2027-12-23, 2028-12-23, etc.
    return Feriado.objects.filter(
        recorrente=True,
        data__month=data.month,
        data__day=data.day,
    ).filter(Q(tipo=Feriado.Tipo.NACIONAL) | local).exists()


def validar_feriado(data, configuracao=None):
    """Bloqueia feriados aplicáveis à clínica (nacional, estadual, municipal; recorrentes incluídos)."""
    configuracao = configuracao or obter_configuracao()
    uf_clinica = _uf_clinica(configuracao)
    cidade = _cidade_clinica(configuracao)
    if _eh_feriado(data, uf_clinica, cidade):
        raise FeriadoError(f"Data indisponível: {data:%d/%m/%Y} é feriado.")


# ---------------------------------------------------------------------------
# Validações de disponibilidade do profissional
# ---------------------------------------------------------------------------


def validar_ausencia(profissional, data):
    """Profissional em férias/licença/afastamento não atende."""
    ausencia = (
        profissional.ausencias
        .filter(data_inicio__lte=data)
        .filter(Q(data_fim__isnull=True) | Q(data_fim__gte=data))
        .first()
    )
    if ausencia:
        raise ProfissionalIndisponivelError(
            f"Profissional indisponível nesta data ({ausencia.get_tipo_display()})."
        )


def validar_bloqueio_agenda(data, hora_inicio, hora_fim, profissional=None, sala=None, agenda=None):
    """Bloqueio de agenda (manutenção, evento, folga) impede o horário.

    V1 - CORRIGIDO. O filtro antigo era
        Q(profissional=p) | Q(sala=s) | Q(agenda=a)
    Passar sala=None gerava Q(sala=None), que casa com TODO bloqueio de sala
    nula - inclusive de outro profissional. Um único bloqueio cadastrado sem
    sala bloqueava qualquer reserva feita sem sala. Agora o Q só é montado
    para os campos que realmente foram informados.

    V3 - CORRIGIDO. BloqueioAgenda herda TimeStampedModel (que tem deleted_at)
    mas usa o Manager padrão, então deleted_at nunca era filtrado: um bloqueio
    soft-deletado continuava bloqueando horários.
    """
    from apps.scheduling.models import BloqueioAgenda  # evita import circular

    condicoes = [
        Q(**{campo: valor})
        for campo, valor in (
            ("profissional", profissional),
            ("sala", sala),
            ("agenda", agenda),
        )
        if valor is not None
    ]
    if not condicoes:
        # Sem escopo informado não há como afirmar que existe bloqueio aplicável.
        return

    filtro = condicoes[0]
    for condicao in condicoes[1:]:
        filtro |= condicao

    bloqueios = (
        BloqueioAgenda.objects
        .filter(deleted_at__isnull=True)
        .filter(filtro)
        .filter(data_inicio__lte=data)
        .filter(Q(data_fim__isnull=True) | Q(data_fim__gte=data))
    )

    for bloqueio in bloqueios:
        data_fim = bloqueio.data_fim or bloqueio.data_inicio
        inicio_bloqueio = (
            bloqueio.hora_inicio if data == bloqueio.data_inicio else time.min
        )
        fim_bloqueio = (
            (bloqueio.hora_fim or time.max) if data == data_fim else time.max
        )
        if intervalos_sobrepoem(hora_inicio, hora_fim, inicio_bloqueio, fim_bloqueio):
            raise AgendaBloqueadaError(f"Horário bloqueado: {bloqueio.motivo}.")


def _agendamento_ocupa_intervalo(queryset, data, hora_inicio, hora_fim):
    """True se algum agendamento do queryset ocupa o intervalo informado.

    V2 - CORRIGIDO. A validação olhava APENAS slots_ocupados (M2M). Um
    agendamento cujo bloco não foi populado - dado legado, importação ou
    registro criado fora do service layer - não era encontrado, e o horário
    podia ser reservado duas vezes. É a mesma assimetria FK ∪ M2M que já
    resolvemos em Agendamento.slots_envolvidos().

    Duas queries com exists() em vez de um OR entre joins: evita produto
    cartesiano entre a relação multivalorada e a FK, e cada caminho fica
    legível isoladamente. exists() curto-circuita, então o custo normal é
    uma query só.
    """
    por_bloco = queryset.filter(
        slots_ocupados__agenda__data=data,
        slots_ocupados__hora_inicio__lt=hora_fim,
        slots_ocupados__hora_fim__gt=hora_inicio,
    )
    if por_bloco.exists():
        return True

    return queryset.filter(
        slot__agenda__data=data,
        slot__hora_inicio__lt=hora_fim,
        slot__hora_fim__gt=hora_inicio,
    ).exists()


def validar_conflito_profissional(profissional, data, hora_inicio, hora_fim, ignorar_agendamento_id=None):
    """Conflito considera o BLOCO inteiro (M2M) e o âncora (FK)."""
    conflitos = Agendamento.objects.filter(
        profissional=profissional,
        status__in=STATUS_QUE_OCUPAM,
    )
    if ignorar_agendamento_id:
        conflitos = conflitos.exclude(pk=ignorar_agendamento_id)

    if _agendamento_ocupa_intervalo(conflitos, data, hora_inicio, hora_fim):
        raise ConflitoProfissionalError(
            "Profissional já possui atendimento neste horário."
        )


def validar_conflito_sala(sala, data, hora_inicio, hora_fim, ignorar_agendamento_id=None):
    """Sala ocupada em QUALQUER slot de um bloco gera conflito."""
    if sala is None:
        return

    conflitos = Agendamento.objects.filter(
        sala=sala,
        status__in=STATUS_QUE_OCUPAM,
    )
    if ignorar_agendamento_id:
        conflitos = conflitos.exclude(pk=ignorar_agendamento_id)

    if _agendamento_ocupa_intervalo(conflitos, data, hora_inicio, hora_fim):
        raise ConflitoSalaError(f"Sala {sala.nome} já está ocupada neste horário.")


def validar_transicao_status(status_atual, novo_status):
    """Garante que o agendamento só ande para estados válidos."""
    from apps.scheduling.exceptions import TransicaoStatusInvalidaError

    permitidos = TRANSICOES_VALIDAS.get(status_atual, set())
    if novo_status not in permitidos:
        raise TransicaoStatusInvalidaError(
            f"Transição inválida: {status_atual} → {novo_status}."
        )
"""Geração de slots a partir da disponibilidade do profissional.

Pipeline: disponibilidade (regra recorrente) → cruza com feriado, ausência,
bloqueio e horário de funcionamento → materializa slots concretos na tabela
slot_agenda.

Idempotência em dois níveis:
  1. A Agenda do dia é o marcador de "dia processado" - criada inclusive
     quando não há expediente (status SEM_EXPEDIENTE). Sem esse marcador,
     dias sem disponibilidade / feriado / ausência custariam uma tentativa
     completa de geração a cada navegação da grade (retry eterno).
  2. Rodar duas vezes para o mesmo dia não duplica slots nem apaga
     agendamentos existentes.
"""

from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.professionals.models import Disponibilidade, Profissional
from apps.scheduling.exceptions import (
    AgendaBloqueadaError,
    FeriadoError,
    ProfissionalIndisponivelError,
)
from apps.scheduling.models import Agenda, Agendamento, SlotAgenda
from apps.scheduling.services import validacoes as V


def _horarios_do_bloco(hora_inicio, hora_fim, passo_minutos):
    """Fatia [hora_inicio, hora_fim) em slots de N minutos. O último é truncado."""
    atual = datetime.combine(date.min, hora_inicio)
    limite = datetime.combine(date.min, hora_fim)
    passo = timedelta(minutes=passo_minutos)

    while atual < limite:
        fim = min(atual + passo, limite)
        yield atual.time(), fim.time()
        atual += passo


def _disponibilidade_vigente(disponibilidade, data):
    """Regra RECORRENTE vale sempre; ESPECIFICA só dentro da vigência."""
    if disponibilidade.tipo == Disponibilidade.Tipo.RECORRENTE:
        return True
    if disponibilidade.data_inicio and data < disponibilidade.data_inicio:
        return False
    if disponibilidade.data_fim and data > disponibilidade.data_fim:
        return False
    return True


def _slot_esta_bloqueado(data, hora_inicio, hora_fim, profissional, agenda):
    """Testa bloqueio sem levantar exceção - usado na geração (marca, não falha)."""
    try:
        V.validar_bloqueio_agenda(
            data, hora_inicio, hora_fim,
            profissional=profissional, agenda=agenda,
        )
        return False
    except AgendaBloqueadaError:
        return True


def _marcar_sem_expediente(profissional, data):
    agenda, criada = Agenda.objects.get_or_create(
        profissional=profissional,
        data=data,
        defaults={"status": Agenda.Status.SEM_EXPEDIENTE},
    )
    if criada or agenda.status == Agenda.Status.SEM_EXPEDIENTE:
        return agenda

    if agenda.slots.filter(status=SlotAgenda.Status.OCUPADO).exists():
        raise ValidationError(
            f"Agenda de {data:%d/%m/%Y} tem horários agendados. "
            "Cancele ou remarque os atendimentos antes de marcar o dia "
            "como sem expediente."
        )

    agenda.status = Agenda.Status.SEM_EXPEDIENTE
    agenda.save(update_fields=["status", "updated_at"])
    return agenda


@transaction.atomic
def gerar_slots_do_dia(profissional, data, configuracao=None):
    """Gera (ou reconcilia) os slots de um profissional para um dia.

    Retorna a Agenda com expediente, ou None se o dia não tem expediente.
    Mesmo retornando None, a Agenda é materializada como SEM_EXPEDIENTE para
    que a próxima chamada reconheça o dia como já processado.
    """
    configuracao = configuracao or V.obter_configuracao()
    agenda = Agenda.objects.filter(profissional=profissional, data=data).first()

    # 1. Feriado - só bloqueia se não houver exceção declarada para o dia.
    try:
        V.validar_feriado(data, configuracao)
    except FeriadoError:
        if not (agenda is not None and agenda.excecao_feriado):
            _marcar_sem_expediente(profissional, data)
            return None

    # 2. Ausência do profissional (férias, afastamento).
    try:
        V.validar_ausencia(profissional, data)
    except ProfissionalIndisponivelError:
        _marcar_sem_expediente(profissional, data)
        return None

    # 3. Disponibilidades vigentes para o dia da semana (isoweekday: 1=seg..7=dom).
    disponibilidades = [
        d for d in profissional.disponibilidades.filter(
            ativa=True,
            dia_semana=data.isoweekday(),
        ).select_related("sala_padrao")
        if _disponibilidade_vigente(d, data)
    ]
    if not disponibilidades:
        _marcar_sem_expediente(profissional, data)
        return None

    if agenda is None:
        agenda, _ = Agenda.objects.get_or_create(profissional=profissional, data=data)

    # Dia antes marcado como sem expediente passou a ter grade (exceção de
    # feriado, nova disponibilidade). Reabilita o status.
    if agenda.status != Agenda.Status.GERADA:
        agenda.status = Agenda.Status.GERADA
        agenda.save(update_fields=["status", "updated_at"])

    # 4. Conjunto desejado de horários: {hora_inicio: (hora_fim, status, origem)}.
    desejados = {}
    for disponibilidade in disponibilidades:
        for hora_inicio, hora_fim in _horarios_do_bloco(
            disponibilidade.hora_inicio,
            disponibilidade.hora_fim,
            disponibilidade.intervalo_minutos,
        ):
            # Slot precisa caber no horário de funcionamento da clínica.
            try:
                V.validar_horario_funcionamento(data, hora_inicio, hora_fim, configuracao)
            except Exception:
                continue

            bloqueado = _slot_esta_bloqueado(data, hora_inicio, hora_fim, profissional, agenda)
            desejados[hora_inicio] = (
                hora_fim,
                SlotAgenda.Status.BLOQUEADO if bloqueado else SlotAgenda.Status.LIVRE,
                disponibilidade,
            )

    #existentes = {slot.hora_inicio: slot for slot in agenda.slots.all()}
    existentes = {
        slot.hora_inicio: slot
        for slot in agenda.slots.filter(deleted_at__isnull=True)
    }
    
    # 5. Cria apenas os slots que faltam. ignore_conflicts protege contra
    #    corrida com a constraint UNIQUE(agenda, hora_inicio).
    novos = [
        SlotAgenda(
            agenda=agenda,
            hora_inicio=hora_inicio,
            hora_fim=dados[0],
            status=dados[1],
            origem_disponibilidade=dados[2],
        )
        for hora_inicio, dados in desejados.items()
        if hora_inicio not in existentes
    ]
    if novos:
        SlotAgenda.objects.bulk_create(novos, ignore_conflicts=True)

    # 6. Reconciliação: slot LIVRE que sumiu da disponibilidade vira INDISPONIVEL.
    #    Slots OCUPADOS nunca são tocados - agendamento existente tem precedência.
    orfaos = [
        hora for hora, slot in existentes.items()
        if hora not in desejados and slot.status == SlotAgenda.Status.LIVRE
    ]
    if orfaos:
        SlotAgenda.objects.filter(
            agenda=agenda,
            hora_inicio__in=orfaos,
            status=SlotAgenda.Status.LIVRE,
        ).update(status=SlotAgenda.Status.INDISPONIVEL)

    return agenda


def gerar_slots_periodo(profissional, data_inicio, dias=45, configuracao=None):
    """Gera a grade de um profissional para um intervalo de dias.

    Días sem expediente também passam pelo gerador (para criar o marcador
    SEM_EXPEDIENTE), mas não entram na lista retornada.
    """
    configuracao = configuracao or V.obter_configuracao()
    geradas = []

    for offset in range(dias):
        data = data_inicio + timedelta(days=offset)
        agenda = gerar_slots_do_dia(profissional, data, configuracao)
        if agenda:
            geradas.append(agenda)

    return geradas


def gerar_slots_todos_profissionais(data_inicio=None, dias=45, profissional_id=None):
    """Job principal: materializa a grade de todos os profissionais ativos.

    Horizonte padrão de 45 dias (decisão 45/120): cobre a rotina da recepção.
    Datas além disso são geradas sob demanda pelas views (garantir_grade_do_dia).
    """
    data_inicio = data_inicio or timezone.localdate()
    configuracao = V.obter_configuracao()

    profissionais = Profissional.objects.filter(status=Profissional.Status.ATIVO)
    if profissional_id:
        profissionais = profissionais.filter(pk=profissional_id)

    total_agendas = 0
    for profissional in profissionais:
        agendas = gerar_slots_periodo(profissional, data_inicio, dias, configuracao)
        total_agendas += len(agendas)

    return {"profissionais": profissionais.count(), "agendas": total_agendas}


@transaction.atomic
def liberar_funcionamento_feriado(profissional, data, configuracao=None):
    """Declara a exceção de funcionamento em feriado e materializa a grade.

    Granularidade: por profissional e data específica - decisão pontual.
    Não vale para o mesmo feriado em anos seguintes (recorrente continua
    fechado a menos que a liberação seja declarada de novo).
    """
    configuracao = configuracao or V.obter_configuracao()
    agenda, _ = Agenda.objects.get_or_create(
        profissional=profissional,
        data=data,
        defaults={"excecao_feriado": True},
    )
    if not agenda.excecao_feriado:
        agenda.excecao_feriado = True
        agenda.save(update_fields=["excecao_feriado", "updated_at"])
    return gerar_slots_do_dia(profissional, data, configuracao)


@transaction.atomic
def reverter_excecao_feriado(profissional, data):
    """Remove a exceção e devolve o dia ao estado "sem expediente".

    A Agenda NÃO é apagada: ela é o marcador de "dia processado". Apagá-la
    faria a geração sob demanda retentar o dia a cada navegação da grade.
    """
    agenda = Agenda.objects.filter(profissional=profissional, data=data).first()
    if not agenda:
        return 0
    removidos = agenda.slots.filter(status=SlotAgenda.Status.LIVRE).delete()[0]
    agenda.excecao_feriado = False
    agenda.status = (
        Agenda.Status.GERADA
        if agenda.slots.exists()
        else Agenda.Status.SEM_EXPEDIENTE
    )
    agenda.save(update_fields=["excecao_feriado", "status", "updated_at"])
    return removidos


@transaction.atomic
def limpar_slots_feriado(data):
    """Limpeza retroativa: remove slots livres de agendas em data de feriado.

    Preserva slots com agendamento (histórico clínico) e agendas com
    exceção declarada (excecao_feriado=True).
    """    
    agendas = (Agenda.objects.filter(data=data, excecao_feriado=False)
               .exclude(status=Agenda.Status.SEM_EXPEDIENTE))
    removidos = 0
    for agenda in agendas:
        removidos += agenda.slots.filter(status=SlotAgenda.Status.LIVRE).delete()[0]
        if not agenda.slots.exists() and not Agendamento.objects.filter(
            slot__agenda=agenda
        ).exists():
            agenda.delete()
    return removidos


def garantir_grade_do_dia(profissional, data, configuracao=None):
    """Gera sob demanda a grade de um dia, se ela ainda não existir.

    A existência da Agenda é o marcador de "dia processado" - inclusive quando
    o dia não tem expediente (Agenda com status SEM_EXPEDIENTE). Sem esse
    marcador, dias sem disponibilidade / feriado / ausência custariam uma
    tentativa completa de geração a cada navegação da grade.
    """
    agenda = Agenda.objects.filter(profissional=profissional, data=data).first()
    if agenda is not None:
        return agenda
    gerar_slots_do_dia(profissional, data, configuracao)
    return Agenda.objects.filter(profissional=profissional, data=data).first()


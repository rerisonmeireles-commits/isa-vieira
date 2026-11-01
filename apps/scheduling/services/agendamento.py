"""Serviços de agendamento: reserva, cancelamento, remarcação e transição de status.

ORDEM DE LOCK - REGRA ÚNICA DO MÓDULO (evita deadlock entre serviços)
=====================================================================
    1. Se houver um Agendamento envolvido, ele é travado PRIMEIRO.
    2. Depois, as linhas de slot_agenda em UMA única query, ORDER BY pk.

    A versão anterior prometia ordenação apenas *entre slots*. Como
    `cancelar_agendamento` travava slot → agendamento e `remarcar`/
    `alterar_status` travavam agendamento → slot, dois usuários podiam
    fechar um ciclo e o PostgreSQL mataria uma das transações com
    "deadlock detected". Agora todos os serviços seguem a mesma ordem.

    `reservar_slot` é a exceção legítima: não existe agendamento ainda,
    então ele trava slots primeiro e insere depois - inserir não disputa
    linha existente, logo não há ciclo possível.

SIMETRIA DE SLOTS
=================
    Toda liberação passa por `Agendamento.liberar_slots()`, que carrega o
    guard de dono ativo. Nenhum `SlotAgenda.objects.filter(...).update()`
    cru neste módulo - era por ali que o guard era anulado.
"""

from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.scheduling.models import Agendamento, SlotAgenda
from apps.scheduling.services import validacoes as V

# Âncora fixa para aritmética de horário.
# ─── CORREÇÃO 6 ───
# A versão anterior usava datetime.min como base, então um bloco que
# cruzava a meia-noite "voltava" para 00:20 e a comparação com o fim do
# expediente passava a ser contra o início do dia. Âncora fixa + checagem
# explícita de transbordo tornam o erro visível em vez de silencioso.
_DIA_ANCORA = date(2000, 1, 1)

# Status que liberam o slot e devem ser excluídos do guard de dono ativo.
# Espelha Agendamento.STATUS_LIBERAM_SLOT para uso nas queries deste módulo.
_STATUS_LIBERAM = frozenset(
    {Agendamento.Status.CANCELADO, Agendamento.Status.REMARCADO}
)


# ══════════════════════════════════════════════════════════════════════
# Helpers internos
# ══════════════════════════════════════════════════════════════════════


def _somar_minutos(referencia, minutos):
    """Soma minutos a um `time`, com checagem explícita de transbordo de dia.

    Aceita `time` (retorna `time`) ou `datetime` (retorna `datetime`).
    Levanta ValidationError se um `time` ultrapassar a meia-noite.
    """
    if isinstance(referencia, time):
        base = datetime.combine(_DIA_ANCORA, referencia)
        resultado = base + timedelta(minutes=minutos)
        if resultado.date() != _DIA_ANCORA:
            raise ValidationError(
                f"Bloco ultrapassa a meia-noite a partir de {referencia}. "
                "Ajuste a duração do tipo de atendimento ou o horário do slot."
            )
        return resultado.time()

    return referencia + timedelta(minutes=minutos)


def _calcular_bloco(slot, duracao_minutos):
    """Slots contíguos necessários para cobrir `duracao_minutos`.

    Retorna sempre uma lista começando pelo slot âncora. Levanta
    ValidationError se não houver slots suficientes na agenda.
    """
    if not duracao_minutos or duracao_minutos <= 0:
        return [slot]

    candidatos = list(
        SlotAgenda.objects.filter(
            agenda=slot.agenda, hora_inicio__gte=slot.hora_inicio
        ).order_by("hora_inicio")
    )
    if not candidatos:
        raise ValidationError("Slot não encontrado na agenda informada.")

    limite = _somar_minutos(slot.hora_inicio, duracao_minutos)

    bloco = []
    for candidato in candidatos:
        if candidato.hora_inicio >= limite:
            break
        bloco.append(candidato)

    if not bloco:
        raise ValidationError("Nenhum slot disponível a partir do horário informado.")

    # Cobertura efetiva: o fim do último slot do bloco precisa alcançar o limite.
    if bloco[-1].hora_fim < limite:
        raise ValidationError(
            f"Agenda insuficiente: {duracao_minutos} min exigem slots até "
            f"{limite.strftime('%H:%M')}, mas a agenda termina em "
            f"{bloco[-1].hora_fim.strftime('%H:%M')}."
        )

    return bloco


def _travar_slots_por_id(ids):
    """Trava as linhas de slot em UMA query, ORDER BY pk, e as devolve relidas.

    A query de lock roda com `values_list` para não materializar join algum
    (um `select_for_update` com `select_related` travaria a linha de `agenda`
    também, fora da ordem acordada). A releitura acontece FORA do lock e traz
    os dados necessários, já com as linhas bloqueadas pela transação.
    """
    ids = list(ids)
    if not ids:
        return []

    list(
        SlotAgenda.objects
        .select_for_update()
        .filter(pk__in=ids)
        .order_by("pk")
        .values_list("pk", flat=True)
    )

    return list(
        SlotAgenda.objects
        .filter(pk__in=ids)
        .select_related("agenda", "origem_disponibilidade")
        .order_by("hora_inicio")
    )


def _travar_agendamento(agendamento_id):
    """Trava o Agendamento primeiro (passo 1 da ordem de lock).

    `of=("self",)` restringe o FOR UPDATE à tabela do agendamento. Sem isso o
    PostgreSQL travaria também a linha de `slot_agenda` do join, invertendo a
    ordem e reintroduzindo o risco de deadlock.
    """
    return (
        Agendamento.objects
        .select_for_update(of=("self",))
        .select_related("slot", "slot__agenda", "paciente", "profissional")
        .get(pk=agendamento_id)
    )


def _validar_calendario(data, agenda, profissional, hora_inicio, hora_fim, configuracao):
    """Validações de calendário compartilhadas por reserva e remarcação.

    Recebe os LIMITES DO BLOCO, não do slot âncora: a clínica precisa abrir
    no início do bloco e fechar no fim dele, e é isso que
    validar_horario_funcionamento(data, hora_inicio, hora_fim, configuracao)
    espera - assinatura conferida em apps/scheduling/services/validacoes.py.
    """
    V.validar_janela_agendamento(data, configuracao)

    try:
        V.validar_feriado(data, configuracao)
    except V.FeriadoError:
        # Exceção pontual registrada na própria agenda do dia.
        if not agenda.excecao_feriado:
            raise

    V.validar_horario_funcionamento(data, hora_inicio, hora_fim, configuracao)
    V.validar_ausencia(profissional, data)


# ══════════════════════════════════════════════════════════════════════
# Reserva
# ══════════════════════════════════════════════════════════════════════


@transaction.atomic
def reservar_slot(
    slot_id,
    paciente,
    profissional,
    tipo_atendimento,
    sala=None,
    convenio=None,
    paciente_convenio=None,
    observacoes=None,
    origem=Agendamento.Origem.RECEPCAO,
    criado_por=None,
):
    """Cria um agendamento ocupando todos os slots contíguos necessários."""
    configuracao = V.obter_configuracao()

    slot = (
        SlotAgenda.objects
        .select_related("agenda", "origem_disponibilidade")
        .get(pk=slot_id)
    )
    data = slot.agenda.data
    duracao = tipo_atendimento.duracao_minutos

    if not duracao or duracao <= 0:
        raise ValidationError(
            "O tipo de atendimento precisa de duração definida (minutos)."
        )

    # Bloco primeiro (leitura pura, sem lock): as validações de calendário
    # precisam de hora_inicio e hora_fim reais, não só do slot âncora.
    bloco = _calcular_bloco(slot, duracao)
    hora_inicio_bloco = bloco[0].hora_inicio
    fim_bloco = bloco[-1].hora_fim

    _validar_calendario(
        data, slot.agenda, profissional, hora_inicio_bloco, fim_bloco, configuracao
    )

    # Sala resolvida ANTES de validar_bloqueio_agenda: um BloqueioAgenda(sala=X)
    # era ignorado quando X vinha de sala_padrao.
    if sala is None and slot.origem_disponibilidade:
        sala = slot.origem_disponibilidade.sala_padrao

    slots = _travar_slots_por_id([s.pk for s in bloco])

    # Status lido DEPOIS do lock - é aqui que a corrida se resolve.
    indisponiveis = [s for s in slots if s.status != SlotAgenda.Status.LIVRE]
    if indisponiveis:
        raise ValidationError(
            "Slot indisponível: "
            + ", ".join(
                f"{s.hora_inicio.strftime('%H:%M')} ({s.get_status_display()})"
                for s in indisponiveis
            )
        )

    hora_inicio_bloco = slots[0].hora_inicio
    fim_bloco = slots[-1].hora_fim

    V.validar_bloqueio_agenda(
        data,
        hora_inicio_bloco,
        fim_bloco,
        profissional=profissional,
        sala=sala,
        agenda=slot.agenda,
    )
    V.validar_conflito_profissional(profissional, data, hora_inicio_bloco, fim_bloco)
    if sala is not None:
        V.validar_conflito_sala(sala, data, hora_inicio_bloco, fim_bloco)

    agendamento = Agendamento(
        slot=slots[0],
        paciente=paciente,
        profissional=profissional,
        tipo_atendimento=tipo_atendimento,
        sala=sala,
        convenio=convenio,
        paciente_convenio=paciente_convenio,
        observacoes=observacoes,
        origem=origem,
        criado_por=criado_por,
        duracao_minutos=duracao,
        status=Agendamento.Status.AGENDADO,
    )
    agendamento.save()

    agendamento.slots_ocupados.set(slots)

    # ─── CORREÇÃO 5 ───
    # Era `SlotAgenda.objects.filter(...).update(OCUPADO)`: terceira cópia da
    # regra de ocupação. Delegado ao model, a regra existe em um lugar só.
    agendamento.ocupar_slots()

    return agendamento


# ══════════════════════════════════════════════════════════════════════
# Transição de status
# ══════════════════════════════════════════════════════════════════════


@transaction.atomic
def alterar_status(agendamento_id, novo_status, usuario=None, motivo=None):
    """Transiciona o status respeitando a máquina de estados.

    CANCELADO e REMARCADO não passam por aqui: eles têm serviços próprios
    (`cancelar_agendamento` e `remarcar_agendamento`) que tratam liberação de
    slots, motivo e cadeia de remarcação. Bloquear aqui é intencional.
    """
    if novo_status in _STATUS_LIBERAM:
        raise ValidationError(
            f"Status {novo_status} deve ser aplicado por "
            "cancelar_agendamento() ou remarcar_agendamento()."
        )

    agendamento = _travar_agendamento(agendamento_id)
    V.validar_transicao_status(agendamento.status, novo_status)

    campos = ["status", "updated_at"]
    agendamento.status = novo_status

    if motivo:
        agendamento.observacoes = (
            f"{agendamento.observacoes}\n{motivo}"
            if agendamento.observacoes
            else motivo
        )
        campos.append("observacoes")

    agendamento.save(update_fields=campos, _sincronizar_slots=False)
    return agendamento


# ══════════════════════════════════════════════════════════════════════
# Cancelamento
# ══════════════════════════════════════════════════════════════════════


@transaction.atomic
def cancelar_agendamento(agendamento_id, motivo, usuario=None):
    """Cancela e libera slots do âncora e do bloco, preservando o histórico.

    ─── CORREÇÃO 1 (guard anulado) ───
    A versão anterior fazia `save()` (que já libera com guard) e em seguida
    um `SlotAgenda.objects.filter(...).update(LIVRE)` cru, que ignorava o
    guard e liberava mesmo slot compartilhado com outro dono ativo. A linha
    era redundante e furava a proteção. Agora há UM caminho de liberação.

    ─── CORREÇÃO 2 (ordem de lock) ───
    Travava slot → agendamento, inverso de `remarcar`/`alterar_status`.
    Dois usuários simultâneos podiam fechar ciclo e gerar deadlock.

    ─── CORREÇÃO 4 (clear() destrutivo) ───
    `slots_ocupados.clear()` apagava o vínculo M2M. Como `slots_envolvidos()`
    unia FK ∪ M2M, um `restore()` posterior reocupava apenas 1 slot de um
    bloco de 4 - corrupção silenciosa da grade. O M2M é mantido: a constraint
    `uq_slot_agendamento_ativo`, a property `agendamento_ativo`, os
    `validar_conflito_*` e o guard já excluem status terminais. Manter o
    vínculo não quebra nada e preserva o histórico do bloco (LGPD/COFFITO).
    """
    agendamento = _travar_agendamento(agendamento_id)
    V.validar_transicao_status(agendamento.status, Agendamento.Status.CANCELADO)

    ids = agendamento.slots_envolvidos()

    agendamento.status = Agendamento.Status.CANCELADO
    agendamento.motivo_cancelamento = motivo
    agendamento.cancelado_por = usuario
    agendamento.save(
        update_fields=[
            "status",
            "motivo_cancelamento",
            "cancelado_por",
            "updated_at",
        ],
        # Liberação explícita logo abaixo, com guard e com os ids já capturados.
        _sincronizar_slots=False,
    )
    agendamento.liberar_slots(ids=ids)

    return agendamento


# ══════════════════════════════════════════════════════════════════════
# Remarcação
# ══════════════════════════════════════════════════════════════════════


@transaction.atomic
def remarcar_agendamento(agendamento_id, novo_slot_id, usuario=None, motivo=None):
    """Remarca criando um NOVO agendamento e fechando o anterior como REMARCADO.

    ─── CORREÇÃO 3 ───
    Passa pelas mesmas validações de calendário que `reservar_slot`.

    ─── CORREÇÃO 5 ───
    Usa `slots_envolvidos()` (FK ∪ M2M) em vez do helper local `_ids_do_bloco`,
    que preferia M2M *ou* FK. Um registro com âncora fora do M2M deixava slot
    preso - mesma classe de bug da duplicação eliminada no queryset.

    ─── CORREÇÃO 7 (campos mortos) ───
    `remarcado_de` e `data_remarcacao` nunca eram preenchidos e o status
    REMARCADO nunca era aplicado: a cadeia de remarcações se perdia. Agora o
    novo registro aponta para o antigo, que fecha como REMARCADO.
    """
    configuracao = V.obter_configuracao()

    antigo = _travar_agendamento(agendamento_id)
    V.validar_transicao_status(antigo.status, Agendamento.Status.REMARCADO)

    slot_destino = (
        SlotAgenda.objects
        .select_related("agenda", "origem_disponibilidade")
        .get(pk=novo_slot_id)
    )
    data_destino = slot_destino.agenda.data
    duracao = antigo.duracao_minutos or antigo.tipo_atendimento.duracao_minutos

    bloco = _calcular_bloco(slot_destino, duracao)
    inicio = bloco[0].hora_inicio
    fim = bloco[-1].hora_fim

    _validar_calendario(
        data_destino,
        slot_destino.agenda,
        antigo.profissional,
        inicio,
        fim,
        configuracao,
    )

    # Guard que existia na versão anterior e não pode se perder:
    # validar_janela_agendamento só compara DATAS, então hoje às 15h aceitaria
    # remarcar para hoje às 08h.
    inicio_dt = timezone.make_aware(datetime.combine(data_destino, inicio))
    if inicio_dt <= timezone.now():
        raise ValidationError("Não é possível remarcar para um horário no passado.")

    sala = antigo.sala
    if sala is None and slot_destino.origem_disponibilidade:
        sala = slot_destino.origem_disponibilidade.sala_padrao

    slots_destino = _travar_slots_por_id([s.pk for s in bloco])

    indisponiveis = [s for s in slots_destino if s.status != SlotAgenda.Status.LIVRE]
    if indisponiveis:
        raise ValidationError(
            "Slot de destino indisponível: "
            + ", ".join(
                f"{s.hora_inicio.strftime('%H:%M')} ({s.get_status_display()})"
                for s in indisponiveis
            )
        )

    inicio = slots_destino[0].hora_inicio
    fim = slots_destino[-1].hora_fim

    V.validar_bloqueio_agenda(
        data_destino,
        inicio,
        fim,
        profissional=antigo.profissional,
        sala=sala,
        agenda=slot_destino.agenda,
    )
    V.validar_conflito_profissional(
        antigo.profissional,
        data_destino,
        inicio,
        fim,
        ignorar_agendamento_id=antigo.pk,
    )
    if sala is not None:
        V.validar_conflito_sala(
            sala,
            data_destino,
            inicio,
            fim,
            ignorar_agendamento_id=antigo.pk,
        )

    # Fecha o antigo ANTES de criar o novo: a constraint
    # uq_slot_agendamento_ativo exige que o slot esteja livre ou que o dono
    # anterior já esteja em status terminal.
    ids_antigos = antigo.slots_envolvidos()

    antigo.status = Agendamento.Status.REMARCADO
    antigo.data_remarcacao = timezone.now()
    antigo.save(
        update_fields=["status", "data_remarcacao", "updated_at"],
        _sincronizar_slots=False,
    )
    antigo.liberar_slots(ids=ids_antigos)

    novo = Agendamento(
        slot=slots_destino[0],
        paciente=antigo.paciente,
        profissional=antigo.profissional,
        tipo_atendimento=antigo.tipo_atendimento,
        sala=sala,
        convenio=antigo.convenio,
        paciente_convenio=antigo.paciente_convenio,
        observacoes=antigo.observacoes,
        origem=antigo.origem,
        criado_por=usuario or antigo.criado_por,
        duracao_minutos=duracao,
        status=Agendamento.Status.AGENDADO,
        remarcado_de=antigo,
    )
    novo.save()

    novo.slots_ocupados.set(slots_destino)
    novo.ocupar_slots()

    return novo

@transaction.atomic
def desfazer_remarcacao(agendamento_id, usuario=None, motivo=None):
    """Cancela o substituto e reativa o original, nessa ordem.

    O nome próprio existe para deixar rastro: no log de auditoria,
    'desfazer_remarcacao' é distinguível de 'cancelar' e de 'restore'.
    """
    antigo = (Agendamento.all_objects
              .select_for_update()
              .get(pk=agendamento_id))

    substituto = antigo._substituto_ativo()
    if substituto is None:
        raise ValidationError(
            "Não há substituto ativo: use restore() diretamente."
        )

    cancelar_agendamento(substituto.pk, motivo or "Desfeita a remarcação", usuario)
    return antigo.restore()
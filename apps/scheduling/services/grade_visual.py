"""Montagem da grade mesclada: blocos multi-slot com rowspan.

Para cada dia, produz:
  - celulas: {hora_inicio: item} - o que renderizar naquela hora
  - cobertos: conjunto de horas cobertas por um bloco (célula omitida)

A ocupação é resolvida pela property `SlotAgenda.agendamento_ativo`, que
enxerga tanto a FK principal quanto o M2M `slots_ocupados`. Quando a view
aplica os DOIS prefetches (`_agendamentos_ativos` e `_agendamentos_bloco`),
a property responde do cache sem queries extras.
"""

from apps.scheduling.models import SlotAgenda


def montar_dia_mesclado(agenda, slots=None):
    """Retorna (celulas, cobertos) da coluna do dia. agenda=None → vazios.

    `slots` permite que o chamador passe os slots já carregados com o cache
    de ocupação injetado (`_agendamentos_ativos`/`_agendamentos_bloco`).
    Quando omitido, cai em `agenda.slots.all()` - correto, porém mais lento.
    """
    celulas, cobertos = {}, set()
    if agenda is None:
        return celulas, cobertos

    if slots is None:
        slots = list(agenda.slots.all().order_by("hora_inicio"))
    else:
        slots = list(slots)

    por_pk = {s.pk: s for s in slots}
    processados = set()

    for slot in slots:
        if slot.pk in processados:
            continue

        # 1. Estados estruturais: independem de agendamento.
        if slot.status == SlotAgenda.Status.BLOQUEADO:
            celulas[slot.hora_inicio] = {"tipo": "bloqueado"}
            processados.add(slot.pk)
            continue

        if slot.status == SlotAgenda.Status.INDISPONIVEL:
            celulas[slot.hora_inicio] = {"tipo": "outro"}
            processados.add(slot.pk)
            continue

        # 2. Ocupação: usa o cache só quando ele está íntegro (os DOIS
        #    prefetches aplicados). Sem cache, `LIVRE` confia no status para
        #    não disparar uma query por slot livre (N+1 na grade inteira).
        cache_integro = (
            getattr(slot, "_agendamentos_ativos", None) is not None
            and getattr(slot, "_agendamentos_bloco", None) is not None
        )
        if slot.status == SlotAgenda.Status.LIVRE and not cache_integro:
            celulas[slot.hora_inicio] = {"tipo": "livre", "slot": slot}
            processados.add(slot.pk)
            continue

        ag = slot.agendamento_ativo

        if ag is None:
            if slot.status == SlotAgenda.Status.OCUPADO:
                # Slot ocupado sem dono ativo (resíduo de exclusão/cancelamento).
                celulas[slot.hora_inicio] = {"tipo": "ocupado_sem_ag"}
            else:
                celulas[slot.hora_inicio] = {"tipo": "livre", "slot": slot}
            processados.add(slot.pk)
            continue

        # 3. Bloco: restringe aos slots que existem nesta agenda, para o
        #    rowspan nunca transbordar a coluna renderizada.
        bloco = sorted(
            (s for s in ag.slots_ocupados.all() if s.pk in por_pk),
            key=lambda s: s.hora_inicio,
        )
        if slot.pk not in {s.pk for s in bloco}:
            bloco = sorted(bloco + [slot], key=lambda s: s.hora_inicio)

        ancora = bloco[0]
        processados.update(s.pk for s in bloco)

        if ancora.pk != slot.pk:
            # Âncora real fora desta coluna (outra agenda / virada de dia):
            # renderiza célula morta em vez de deixar a linha sem <td>.
            celulas[slot.hora_inicio] = {"tipo": "ocupado_sem_ag"}
            continue

        celulas[ancora.hora_inicio] = {
            "tipo": "bloco",
            "agendamento": ag,
            "rowspan": len(bloco),
            "hora_inicio": ancora.hora_inicio,
            "hora_fim": bloco[-1].hora_fim,
        }
        for s in bloco[1:]:
            cobertos.add(s.hora_inicio)

    return celulas, cobertos
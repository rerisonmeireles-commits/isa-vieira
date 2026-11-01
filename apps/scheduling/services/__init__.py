"""API pública do service layer da agenda.

Views devem importar daqui - nunca de módulos internos.
"""
from apps.scheduling.services.agendamento import (
    alterar_status,
    cancelar_agendamento,
    remarcar_agendamento,
    reservar_slot,
)
from apps.scheduling.services.geracao_slots import (
    gerar_slots_do_dia,
    gerar_slots_periodo,
    gerar_slots_todos_profissionais,
)

__all__ = [
    "reservar_slot",
    "alterar_status",
    "cancelar_agendamento",
    "remarcar_agendamento",
    "gerar_slots_do_dia",
    "gerar_slots_periodo",
    "gerar_slots_todos_profissionais",
]
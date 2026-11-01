from django.db import IntegrityError, transaction

from apps.scheduling.exceptions import AgendaError
from apps.scheduling.models import Agendamento
from apps.scheduling.services import reservar_slot


class PortalAgendaError(Exception):
    """Erro de negócio na reserva feita pelo portal."""


def reservar_para_paciente(*, paciente, slot, tipo, usuario, observacoes=""):
    try:
        with transaction.atomic():
            return reservar_slot(
                slot_id=slot.pk,
                paciente=paciente,
                tipo_atendimento=tipo,
                usuario=usuario,
                origem=Agendamento.Origem.PORTAL,
                observacoes=observacoes,
            )
    except AgendaError as exc:
        raise PortalAgendaError(str(exc)) from exc
    except IntegrityError as exc:
        raise PortalAgendaError("Este horário acabou de ser reservado. Escolha outro.") from exc
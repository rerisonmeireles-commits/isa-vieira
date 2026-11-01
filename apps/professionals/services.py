"""Regras de negócio do módulo de Profissionais."""

from django.db import transaction

from apps.professionals.models import Profissional


@transaction.atomic
def salvar_profissional(*, form, disponibilidades, ausencias):
    """Salva o profissional e seus relacionados numa única transação."""
    profissional = form.save()
    for formset in (disponibilidades, ausencias):
        formset.instance = profissional
        formset.save()
    return profissional


def alternar_status(profissional):
    """Cicla ATIVO → AFASTADO → INATIVO → ATIVO (reversível).

    Diferente do Paciente (binário), o Profissional tem 3 estados - o ciclo
    cobre todos sem precisar de um seletor extra na listagem.
    """
    ordem = [
        Profissional.Status.ATIVO,
        Profissional.Status.AFASTADO,
        Profissional.Status.INATIVO,
    ]
    indice = ordem.index(profissional.status)
    profissional.status = ordem[(indice + 1) % len(ordem)]
    profissional.save(update_fields=["status", "updated_at"])
    return profissional
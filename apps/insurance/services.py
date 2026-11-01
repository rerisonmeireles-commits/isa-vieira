"""Regras de negócio do módulo de Convênios."""

from django.db import transaction

from apps.insurance.models import Convenio


@transaction.atomic
def salvar_convenio(*, form, planos):
    """Salva o convênio e seus planos numa única transação."""
    convenio = form.save()
    planos.instance = convenio
    planos.save()
    return convenio


def alternar_ativo(convenio):
    """Alterna o flag ativo (reversível)."""
    convenio.ativo = not convenio.ativo
    convenio.save(update_fields=["ativo", "updated_at"])
    return convenio
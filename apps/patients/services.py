"""Regras de negócio do módulo de Pacientes."""

from django.db import transaction

from apps.patients.models import Paciente


@transaction.atomic
def salvar_paciente(*, form, enderecos, contatos, emergencias):
    """Salva o paciente e seus relacionados numa única transação.

    Se qualquer formset falhar, a transação inteira é revertida - nunca
    sobra um paciente sem endereço/contato por falha parcial.
    """
    paciente = form.save()
    for formset in (enderecos, contatos, emergencias):
        formset.instance = paciente
        formset.save()
    return paciente


def alternar_status(paciente):
    """Alterna ATIVO <-> INATIVO.

    ⚠️ É a inativação OPERACIONAL (reversível). Não confundir com o soft
    delete (`deleted_at`), que remove o registro da operação e libera o CPF.
    """
    paciente.status = (
        Paciente.Status.INATIVO
        if paciente.status == Paciente.Status.ATIVO
        else Paciente.Status.ATIVO
    )
    paciente.save(update_fields=["status", "updated_at"])
    return paciente
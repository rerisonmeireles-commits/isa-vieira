"""Regras de negócio do módulo Clinic (Estrutura)."""

from django.db import transaction

from apps.clinic.models import Clinica, Configuracao


@transaction.atomic
def salvar_clinica_e_configuracao(*, clinica_form, configuracao_form):
    """Salva a clínica e a configuração na mesma transação.

    A Configuracao é OneToOne com a Clinica - se ainda não existir, é criada
    no primeiro salvamento (single-tenant: uma única clínica no sistema).
    """
    clinica = clinica_form.save()

    configuracao = configuracao_form.save(commit=False)
    configuracao.clinica = clinica
    configuracao.save()

    return clinica, configuracao


def obter_configuracao_ou_none():
    return Configuracao.objects.select_related("clinica").first()


def salvar_sala(*, form):
    return form.save()


def salvar_tipo(*, form):
    return form.save()


def alternar_tipo_ativo(tipo):
    tipo.ativo = not tipo.ativo
    tipo.save(update_fields=["ativo", "updated_at"])
    return tipo
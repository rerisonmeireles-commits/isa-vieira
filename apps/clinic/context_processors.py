"""Context processors do módulo Clinic."""

from apps.clinic.models import Clinica


def clinica_global(request):
    """Disponibiliza a clínica (single-tenant) para todos os templates."""
    clinica = Clinica.objects.select_related("configuracao").first()
    return {"clinica": clinica}
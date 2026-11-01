"""Autorização de escopo do Portal do Paciente.

Verificações de runtime que sustentam este módulo:
    user model ...................... accounts.Usuario
    Paciente._default_manager ....... SoftDeleteManager
    Paciente._base_manager .......... Manager        (iguais: False)
    uuid ............................ 8/8 modelos da §1.3

A terceira linha manda aqui. O Django resolve OneToOneField reverso por
_base_manager, que neste projeto é Manager puro: user.paciente NÃO filtra
deleted_at. O guard abaixo é o único filtro desse caminho.

Não "conserte" isso apontando base_manager_name para SoftDeleteManager.
O Django exige base manager sem filtro; filtrá-lo quebra template histórico,
admin e integridade referencial.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied


class PacienteScopedMixin(LoginRequiredMixin):
    """Restringe o queryset do portal ao paciente autenticado."""

    paciente_lookup = "paciente"

    def get_paciente(self):
        if not hasattr(self, "_paciente_cache"):
            try:
                paciente = self.request.user.paciente
            except ObjectDoesNotExist:
                paciente = None

            if paciente is not None and paciente.deleted_at is not None:
                paciente = None

            self._paciente_cache = paciente

        return self._paciente_cache

    def dispatch(self, request, *args, **kwargs):
        # Sem este guard, request.user.paciente levanta nos perfis sem paciente
        # e sobe como HTTP 500 - sintoma mudo. Aqui vira 403 explícito.
        if request.user.is_authenticated and self.get_paciente() is None:
            raise PermissionDenied("Área exclusiva de pacientes.")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        paciente = self.get_paciente()
        if paciente is None:
            return qs.none()
        return qs.filter(**{self.paciente_lookup: paciente})
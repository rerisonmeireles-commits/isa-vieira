from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseForbidden

from apps.patients.models import Paciente


def paciente_do_usuario(user):
    """Paciente vinculado ao usuário logado (ou None).

    Vínculo: FK user do Paciente (related_name="paciente").
    Paciente soft-deletado é tratado como sem vínculo.
    """
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        paciente = user.paciente
    except (AttributeError, ObjectDoesNotExist):
        return None
    if paciente.deleted_at is not None:
        return None
    return paciente


def portal_required(view):
    @login_required
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        paciente = paciente_do_usuario(request.user)
        if paciente is None:
            return HttpResponseForbidden("Acesso restrito ao portal do paciente.")
        request.paciente = paciente
        return view(request, *args, **kwargs)
    return _wrapped
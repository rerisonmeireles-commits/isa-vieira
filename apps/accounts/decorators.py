# apps/accounts/decorators.py
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def grupos_requeridos(*grupos):
    """Exige login + pertencimento a pelo menos um dos grupos.

    Superusuário passa sempre. Uso:
        @grupos_requeridos(*GRUPOS_AGENDA)
        def minha_view(request): ...
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            if request.user.groups.filter(name__in=grupos).exists():
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return _wrapped
    return decorator
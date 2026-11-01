"""Decoradores de autorização baseados em grupos (RBAC do portal clínico)."""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

# Grupos que operam a agenda no portal clínico.
# ⚠️ Os nomes precisam bater EXATAMENTE com o Django Admin (aqui: "Recepção").
from apps.accounts.constants import GRUPOS_AGENDA, GRUPOS_GERACAO_GRADE

def grupos_requeridos(*grupos):
    """Exige login E pertencimento a UM dos grupos informados.

    Comportamento:
      - Usuário anônimo                → redireciona para o login (?next=...)
      - Autenticado sem o grupo certo  → HTTP 403 (NÃO volta para o login)
      - Superusuário                   → sempre permitido
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            usuario = request.user
            if not usuario.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if usuario.is_superuser or usuario.groups.filter(name__in=grupos).exists():
                return view_func(request, *args, **kwargs)
            raise PermissionDenied(
                "Sua conta não tem permissão para acessar esta área."
            )
        return _wrapped
    return decorator

def grupos_do_usuario(request):
    if not hasattr(request, "_grupos_cache"):
        request._grupos_cache = set(
            request.user.groups.values_list("name", flat=True)
        ) if request.user.is_authenticated else set()
    return request._grupos_cache
"""Context processors do portal - injetam dados em TODAS as páginas."""

from django.utils import timezone

from apps.accounts.menu import menu_do_usuario


def portal(request):
    """Menu filtrado por perfil + data atual (topbar e sidebar)."""
    if not request.user.is_authenticated:
        return {}
    return {
        "menu_itens": menu_do_usuario(request.user),
        "hoje": timezone.localdate(),
    }

"""EXPÕE AS PERMISSÕES DE PERFIL DO USUÁRIO A TODOS OS TEMPLATES.
Uso no template: {% if perm.evoluir %} ... {% endif %}
Fonte única: apps.accounts.constants - nenhuma string crua no template.
"""
from apps.accounts.constants import (
    GRUPOS_AGENDA,
    GRUPOS_ATENDIMENTOS_INICIAR,
    GRUPOS_CLINICO_EDITAR,
    GRUPOS_CLINICO_VER,
    GRUPOS_FINANCEIRO_VER,
)

def permissoes(request):
    user = request.user
    if not user.is_authenticated:
        return {"perm": {}}

    # 1 query por request - nomes dos grupos do usuário
    grupos_do_usuario = set(user.groups.values_list("name", flat=True))

    def tem(grupos):
        return user.is_superuser or bool(grupos_do_usuario & set(grupos))

    return {
        "perm": {
            "agenda": tem(GRUPOS_AGENDA),
            "atender": tem(GRUPOS_ATENDIMENTOS_INICIAR), 
            "clinico_ver": tem(GRUPOS_CLINICO_VER),
            "evoluir": tem(GRUPOS_CLINICO_EDITAR),
            "financeiro": tem(GRUPOS_FINANCEIRO_VER),
            # adicione flags novas aqui conforme os botões da grade
        }
    }
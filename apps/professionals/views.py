"""Views do módulo de Profissionais: listagem, cadastro, edição e ficha.

Padrão do projeto: view fina, service gorda.

RBAC:
  - Ver / consultar: Administrador, Recepção
  - Cadastrar / editar / alterar status: Administrador, Recepção
"""

import re

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import F, Q, Value
from django.db.models.functions import Replace
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.constants import (
    GRUPOS_PROFISSIONAIS_EDITAR,
    GRUPOS_PROFISSIONAIS_VER,
)
from apps.accounts.permissions import grupos_requeridos
from apps.professionals.forms import (
    AusenciaFormSetFactory,
    DisponibilidadeFormSetFactory,
    ProfissionalForm,
)
from apps.professionals.models import Profissional
from apps.professionals.services import alternar_status, salvar_profissional

ITENS_POR_PAGINA = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pode_editar(usuario):
    return usuario.is_superuser or usuario.groups.filter(
        name__in=GRUPOS_PROFISSIONAIS_EDITAR
    ).exists()


def _cpf_sem_mascara():
    """Expressão ORM que remove pontos e traço do CPF (busca por dígitos)."""
    return Replace(Replace(F("cpf"), Value("."), Value("")), Value("-"), Value(""))


def _querystring_sem_page(request):
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return parametros.urlencode()


# ---------------------------------------------------------------------------
# Listagem
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_PROFISSIONAIS_VER)
def listar(request):
    busca = (request.GET.get("q") or "").strip()
    status_filtro = request.GET.get("status") or ""

    profissionais = Profissional.objects.select_related("conselho").all()

    if busca:
        condicao = Q(nome_completo__icontains=busca) | Q(
            registro_conselho__icontains=busca
        )
        digitos = re.sub(r"\D", "", busca)
        if digitos:
            profissionais = profissionais.annotate(cpf_limpo=_cpf_sem_mascara())
            condicao |= Q(cpf_limpo__icontains=digitos)
        profissionais = profissionais.filter(condicao)

    if status_filtro in dict(Profissional.Status.choices):
        profissionais = profissionais.filter(status=status_filtro)

    paginador = Paginator(profissionais, ITENS_POR_PAGINA)

    return render(request, "professionals/listar.html", {
        "pagina": paginador.get_page(request.GET.get("page")),
        "busca": busca,
        "status_filtro": status_filtro,
        "status_choices": Profissional.Status.choices,
        "pode_editar": _pode_editar(request.user),
        "total": paginador.count,
        "querystring": _querystring_sem_page(request),
    })


# ---------------------------------------------------------------------------
# Ficha
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_PROFISSIONAIS_VER)
def ficha(request, pk):
    profissional = get_object_or_404(
        Profissional.objects.select_related("conselho").prefetch_related(
            "especialidades", "disponibilidades", "ausencias"
        ),
        pk=pk,
    )
    return render(request, "professionals/ficha.html", {
        "profissional": profissional,
        "pode_editar": _pode_editar(request.user),
    })


# ---------------------------------------------------------------------------
# Cadastro e edição
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_PROFISSIONAIS_EDITAR)
def criar(request):
    return _formulario(request, profissional=None)


@grupos_requeridos(*GRUPOS_PROFISSIONAIS_EDITAR)
def editar(request, pk):
    profissional = get_object_or_404(Profissional, pk=pk)
    return _formulario(request, profissional=profissional)


def _formulario(request, profissional):
    instancia = profissional if profissional else Profissional()

    if request.method == "POST":
        form = ProfissionalForm(request.POST, request.FILES, instance=instancia)
        disponibilidades = DisponibilidadeFormSetFactory(
            request.POST, instance=instancia, prefix="disponibilidades"
        )
        ausencias = AusenciaFormSetFactory(
            request.POST, instance=instancia, prefix="ausencias"
        )

        if all([form.is_valid(), disponibilidades.is_valid(), ausencias.is_valid()]):
            try:
                salvo = salvar_profissional(
                    form=form,
                    disponibilidades=disponibilidades,
                    ausencias=ausencias,
                )
            except IntegrityError:
                # Rede de segurança: cobre o caso de o model ainda usar
                # unique=True no CPF (antes do Passo 0).
                messages.error(
                    request,
                    "Não foi possível salvar: CPF já cadastrado ou regra de "
                    "disponibilidade duplicada.",
                )
                return render(request, "professionals/form.html", {
                    "form": form,
                    "disponibilidades": disponibilidades,
                    "ausencias": ausencias,
                    "profissional": profissional,
                })
            messages.success(
                request, f"Profissional {salvo.nome_completo} salvo com sucesso."
            )
            return redirect("professionals:ficha", pk=salvo.pk)
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = ProfissionalForm(instance=instancia)
        disponibilidades = DisponibilidadeFormSetFactory(
            instance=instancia, prefix="disponibilidades"
        )
        ausencias = AusenciaFormSetFactory(
            instance=instancia, prefix="ausencias"
        )

    return render(request, "professionals/form.html", {
        "form": form,
        "disponibilidades": disponibilidades,
        "ausencias": ausencias,
        "profissional": profissional,
    })


# ---------------------------------------------------------------------------
# Status (ciclo ATIVO → AFASTADO → INATIVO)
# ---------------------------------------------------------------------------

@require_POST
@grupos_requeridos(*GRUPOS_PROFISSIONAIS_EDITAR)
def alternar_status_view(request, pk):
    profissional = alternar_status(get_object_or_404(Profissional, pk=pk))
    messages.success(
        request,
        f"Status de {profissional.nome_completo} atualizado para "
        f"{profissional.get_status_display()}.",
    )
    return redirect("professionals:ficha", pk=profissional.pk)
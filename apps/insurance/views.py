"""Views do módulo de Convênios: listagem, cadastro, edição e ficha.

Padrão do projeto: view fina, service gorda.

RBAC:
  - Ver / consultar: Administrador, Recepção, Financeiro
  - Cadastrar / editar / inativar: Administrador, Financeiro
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.constants import GRUPOS_CONVENIOS_EDITAR, GRUPOS_CONVENIOS_VER
from apps.accounts.permissions import grupos_requeridos
from apps.insurance.forms import ConvenioForm, PlanoFormSetFactory
from apps.insurance.models import Convenio
from apps.insurance.services import alternar_ativo, salvar_convenio

ITENS_POR_PAGINA = 20


def _pode_editar(usuario):
    return usuario.is_superuser or usuario.groups.filter(
        name__in=GRUPOS_CONVENIOS_EDITAR
    ).exists()


def _querystring_sem_page(request):
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return parametros.urlencode()


@grupos_requeridos(*GRUPOS_CONVENIOS_VER)
def listar(request):
    busca = (request.GET.get("q") or "").strip()
    ativo_filtro = request.GET.get("ativo") or ""

    convenios = Convenio.objects.annotate(num_planos=Count("planos"))

    if busca:
        convenios = convenios.filter(
            Q(nome__icontains=busca) | Q(planos__nome__icontains=busca)
        ).distinct()

    if ativo_filtro in ("1", "0"):
        convenios = convenios.filter(ativo=ativo_filtro == "1")

    paginador = Paginator(convenios, ITENS_POR_PAGINA)

    return render(request, "insurance/listar.html", {
        "pagina": paginador.get_page(request.GET.get("page")),
        "busca": busca,
        "ativo_filtro": ativo_filtro,
        "pode_editar": _pode_editar(request.user),
        "total": paginador.count,
        "querystring": _querystring_sem_page(request),
    })


@grupos_requeridos(*GRUPOS_CONVENIOS_VER)
def ficha(request, pk):
    convenio = get_object_or_404(
        Convenio.objects.prefetch_related("planos").annotate(
            num_pacientes=Count("planos__pacientes")
        ),
        pk=pk,
    )
    return render(request, "insurance/ficha.html", {
        "convenio": convenio,
        "pode_editar": _pode_editar(request.user),
    })


@grupos_requeridos(*GRUPOS_CONVENIOS_EDITAR)
def criar(request):
    return _formulario(request, convenio=None)


@grupos_requeridos(*GRUPOS_CONVENIOS_EDITAR)
def editar(request, pk):
    convenio = get_object_or_404(Convenio, pk=pk)
    return _formulario(request, convenio=convenio)


def _formulario(request, convenio):
    instancia = convenio if convenio else Convenio()

    if request.method == "POST":
        form = ConvenioForm(request.POST, instance=instancia)
        planos = PlanoFormSetFactory(request.POST, instance=instancia, prefix="planos")

        if all([form.is_valid(), planos.is_valid()]):
            salvo = salvar_convenio(form=form, planos=planos)
            messages.success(request, f"Convênio {salvo.nome} salvo com sucesso.")
            return redirect("insurance:ficha", pk=salvo.pk)
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = ConvenioForm(instance=instancia)
        planos = PlanoFormSetFactory(instance=instancia, prefix="planos")

    return render(request, "insurance/form.html", {
        "form": form,
        "planos": planos,
        "convenio": convenio,
    })


@require_POST
@grupos_requeridos(*GRUPOS_CONVENIOS_EDITAR)
def alternar_ativo_view(request, pk):
    convenio = alternar_ativo(get_object_or_404(Convenio, pk=pk))
    messages.success(
        request,
        f"Convênio {convenio.nome} está agora {'ativo' if convenio.ativo else 'inativo'}.",
    )
    return redirect("insurance:ficha", pk=convenio.pk)
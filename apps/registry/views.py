"""Views do módulo Registry: cadastros básicos (Conselhos, Especialidades, Feriados).

Padrão do projeto: view fina, service gorda.

RBAC: restrito ao Administrador - dados de configuração da clínica.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.constants import GRUPOS_REGISTRY_EDITAR, GRUPOS_REGISTRY_VER
from apps.accounts.permissions import grupos_requeridos
from apps.registry.forms import ConselhoProfissionalForm, EspecialidadeForm, FeriadoForm
from apps.registry.models import ConselhoProfissional, Especialidade, Feriado
from apps.registry.services import (
    alternar_ativa_especialidade,
    excluir_feriado as excluir_feriado_service,
    salvar_conselho,
    salvar_especialidade,
    salvar_feriado,
)

ITENS_POR_PAGINA = 20


def _querystring_sem_page(request):
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return parametros.urlencode()


# ---------------------------------------------------------------------------
# Especialidades
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_REGISTRY_VER)
def listar_especialidades(request):
    busca = (request.GET.get("q") or "").strip()
    ativa_filtro = request.GET.get("ativa") or ""

    especialidades = Especialidade.objects.order_by("nome")
    if busca:
        especialidades = especialidades.filter(
            Q(nome__icontains=busca) | Q(descricao__icontains=busca)
        )
    if ativa_filtro in ("1", "0"):
        especialidades = especialidades.filter(ativa=ativa_filtro == "1")

    paginador = Paginator(especialidades, ITENS_POR_PAGINA)
    return render(request, "registry/listar_especialidades.html", {
        "pagina": paginador.get_page(request.GET.get("page")),
        "busca": busca,
        "ativa_filtro": ativa_filtro,
        "total": paginador.count,
        "querystring": _querystring_sem_page(request),
    })


@grupos_requeridos(*GRUPOS_REGISTRY_EDITAR)
def criar_especialidade(request):
    if request.method == "POST":
        form = EspecialidadeForm(request.POST)
        if form.is_valid():
            salvar_especialidade(form=form)
            messages.success(request, "Especialidade salva com sucesso.")
            return redirect("registry:listar_especialidades")
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = EspecialidadeForm()

    return render(request, "registry/form_especialidade.html", {"form": form})


@grupos_requeridos(*GRUPOS_REGISTRY_EDITAR)
def editar_especialidade(request, pk):
    especialidade = get_object_or_404(Especialidade, pk=pk)
    if request.method == "POST":
        form = EspecialidadeForm(request.POST, instance=especialidade)
        if form.is_valid():
            salvar_especialidade(form=form)
            messages.success(request, "Especialidade atualizada com sucesso.")
            return redirect("registry:listar_especialidades")
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = EspecialidadeForm(instance=especialidade)

    return render(request, "registry/form_especialidade.html", {
        "form": form,
        "especialidade": especialidade,
    })


@require_POST
@grupos_requeridos(*GRUPOS_REGISTRY_EDITAR)
def alternar_ativa(request, pk):
    especialidade = alternar_ativa_especialidade(
        get_object_or_404(Especialidade, pk=pk)
    )
    messages.success(
        request,
        f"Especialidade {especialidade.nome} está agora "
        f"{'ativa' if especialidade.ativa else 'inativa'}.",
    )
    return redirect("registry:listar_especialidades")


# ---------------------------------------------------------------------------
# Conselhos Profissionais
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_REGISTRY_VER)
def listar_conselhos(request):
    busca = (request.GET.get("q") or "").strip()

    conselhos = ConselhoProfissional.objects.order_by("sigla")
    if busca:
        conselhos = conselhos.filter(
            Q(sigla__icontains=busca)
            | Q(nome__icontains=busca)
            | Q(uf__icontains=busca)
        )

    paginador = Paginator(conselhos, ITENS_POR_PAGINA)
    return render(request, "registry/listar_conselhos.html", {
        "pagina": paginador.get_page(request.GET.get("page")),
        "busca": busca,
        "total": paginador.count,
        "querystring": _querystring_sem_page(request),
    })


@grupos_requeridos(*GRUPOS_REGISTRY_EDITAR)
def criar_conselho(request):
    if request.method == "POST":
        form = ConselhoProfissionalForm(request.POST)
        if form.is_valid():
            salvar_conselho(form=form)
            messages.success(request, "Conselho salvo com sucesso.")
            return redirect("registry:listar_conselhos")
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = ConselhoProfissionalForm()

    return render(request, "registry/form_conselho.html", {"form": form})


@grupos_requeridos(*GRUPOS_REGISTRY_EDITAR)
def editar_conselho(request, pk):
    conselho = get_object_or_404(ConselhoProfissional, pk=pk)
    if request.method == "POST":
        form = ConselhoProfissionalForm(request.POST, instance=conselho)
        if form.is_valid():
            salvar_conselho(form=form)
            messages.success(request, "Conselho atualizado com sucesso.")
            return redirect("registry:listar_conselhos")
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = ConselhoProfissionalForm(instance=conselho)

    return render(request, "registry/form_conselho.html", {
        "form": form,
        "conselho": conselho,
    })


# ---------------------------------------------------------------------------
# Feriados
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_REGISTRY_VER)
def listar_feriados(request):
    busca = (request.GET.get("q") or "").strip()
    tipo_filtro = request.GET.get("tipo") or ""

    feriados = Feriado.objects.all()  # Meta.ordering = ["data"]
    if busca:
        feriados = feriados.filter(descricao__icontains=busca)
    if tipo_filtro in dict(Feriado.Tipo.choices):
        feriados = feriados.filter(tipo=tipo_filtro)

    paginador = Paginator(feriados, ITENS_POR_PAGINA)
    return render(request, "registry/listar_feriados.html", {
        "pagina": paginador.get_page(request.GET.get("page")),
        "busca": busca,
        "tipo_filtro": tipo_filtro,
        "tipo_choices": Feriado.Tipo.choices,
        "total": paginador.count,
        "querystring": _querystring_sem_page(request),
    })


@grupos_requeridos(*GRUPOS_REGISTRY_EDITAR)
def criar_feriado(request):
    if request.method == "POST":
        form = FeriadoForm(request.POST)
        if form.is_valid():
            salvar_feriado(form=form)
            messages.success(request, "Feriado salvo com sucesso.")
            return redirect("registry:listar_feriados")
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = FeriadoForm()

    return render(request, "registry/form_feriado.html", {"form": form})


@grupos_requeridos(*GRUPOS_REGISTRY_EDITAR)
def editar_feriado(request, pk):
    feriado = get_object_or_404(Feriado, pk=pk)
    if request.method == "POST":
        form = FeriadoForm(request.POST, instance=feriado)
        if form.is_valid():
            salvar_feriado(form=form)
            messages.success(request, "Feriado atualizado com sucesso.")
            return redirect("registry:listar_feriados")
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = FeriadoForm(instance=feriado)

    return render(request, "registry/form_feriado.html", {
        "form": form,
        "feriado": feriado,
    })


@require_POST
@grupos_requeridos(*GRUPOS_REGISTRY_EDITAR)
def excluir_feriado(request, pk):
    feriado = get_object_or_404(Feriado, pk=pk)
    excluir_feriado_service(feriado) 
    messages.success(request, f"Feriado {feriado.descricao} excluído.")
    return redirect("registry:listar_feriados")
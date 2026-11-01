"""Views do módulo Clinic: dados da clínica, configuração, salas e tipos.

Padrão do projeto: view fina, service gorda.

RBAC: restrito ao Administrador - dados de estrutura e configuração.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
 
from apps.accounts.constants import GRUPOS_CLINICA_EDITAR, GRUPOS_CLINICA_VER
from apps.accounts.permissions import grupos_requeridos
from apps.clinic.forms import ClinicaForm, ConfiguracaoForm, SalaForm, TipoAtendimentoForm
from apps.clinic.models import Clinica, Sala, TipoAtendimento
from apps.clinic.services import (
    alternar_tipo_ativo,
    obter_configuracao_ou_none,
    salvar_clinica_e_configuracao,
    salvar_sala,
    salvar_tipo,
)

ITENS_POR_PAGINA = 20


def _querystring_sem_page(request):
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return parametros.urlencode()


# ---------------------------------------------------------------------------
# Dados da Clínica + Configuração (single-tenant)
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_CLINICA_VER)
def dados_clinica(request):
    """Página única de dados da clínica e configuração (edição/criação)."""
    clinica = Clinica.objects.first()
    configuracao = obter_configuracao_ou_none()

    if request.method == "POST":
        clinica_form = ClinicaForm(request.POST, request.FILES, instance=clinica)
        configuracao_form = ConfiguracaoForm(request.POST, instance=configuracao)
        if clinica_form.is_valid() and configuracao_form.is_valid():
            salvar_clinica_e_configuracao(
                clinica_form=clinica_form,
                configuracao_form=configuracao_form,
            )
            messages.success(request, "Dados da clínica salvos com sucesso.")
            return redirect("clinica:dados_clinica")
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        clinica_form = ClinicaForm(instance=clinica)
        configuracao_form = ConfiguracaoForm(instance=configuracao)

    return render(request, "clinic/dados_clinica.html", {
        "clinica_form": clinica_form,
        "configuracao_form": configuracao_form,
        "clinica": clinica,
    })


# ---------------------------------------------------------------------------
# Salas
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_CLINICA_VER)
def listar_salas(request):
    busca = (request.GET.get("q") or "").strip()
    status_filtro = request.GET.get("status") or ""

    salas = Sala.objects.order_by("nome")
    if busca:
        salas = salas.filter(
            Q(nome__icontains=busca) | Q(descricao__icontains=busca)
        )
    if status_filtro in dict(Sala.Status.choices):
        salas = salas.filter(status=status_filtro)

    paginador = Paginator(salas, ITENS_POR_PAGINA)
    return render(request, "clinic/listar_salas.html", {
        "pagina": paginador.get_page(request.GET.get("page")),
        "busca": busca,
        "status_filtro": status_filtro,
        "status_choices": Sala.Status.choices,
        "total": paginador.count,
        "querystring": _querystring_sem_page(request),
    })


@grupos_requeridos(*GRUPOS_CLINICA_EDITAR)
def criar_sala(request):
    if request.method == "POST":
        form = SalaForm(request.POST)
        if form.is_valid():
            salvar_sala(form=form)
            messages.success(request, "Sala salva com sucesso.")
            return redirect("clinica:listar_salas")
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = SalaForm()

    return render(request, "clinic/form_sala.html", {"form": form})


@grupos_requeridos(*GRUPOS_CLINICA_EDITAR)
def editar_sala(request, pk):
    sala = get_object_or_404(Sala, pk=pk)
    if request.method == "POST":
        form = SalaForm(request.POST, instance=sala)
        if form.is_valid():
            salvar_sala(form=form)
            messages.success(request, "Sala atualizada com sucesso.")
            return redirect("clinica:listar_salas")
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = SalaForm(instance=sala)

    return render(request, "clinic/form_sala.html", {
        "form": form,
        "sala": sala,
    })


# ---------------------------------------------------------------------------
# Tipos de Atendimento
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_CLINICA_VER)
def listar_tipos(request):
    busca = (request.GET.get("q") or "").strip()
    ativo_filtro = request.GET.get("ativo") or ""

    tipos = TipoAtendimento.objects.order_by("nome")
    if busca:
        tipos = tipos.filter(
            Q(nome__icontains=busca) | Q(descricao__icontains=busca)
        )
    if ativo_filtro in ("1", "0"):
        tipos = tipos.filter(ativo=ativo_filtro == "1")

    paginador = Paginator(tipos, ITENS_POR_PAGINA)
    return render(request, "clinic/listar_tipos.html", {
        "pagina": paginador.get_page(request.GET.get("page")),
        "busca": busca,
        "ativo_filtro": ativo_filtro,
        "total": paginador.count,
        "querystring": _querystring_sem_page(request),
    })


@grupos_requeridos(*GRUPOS_CLINICA_EDITAR)
def criar_tipo(request):
    if request.method == "POST":
        form = TipoAtendimentoForm(request.POST)
        if form.is_valid():
            salvar_tipo(form=form)
            messages.success(request, "Tipo de atendimento salvo com sucesso.")
            return redirect("clinica:listar_tipos")
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = TipoAtendimentoForm()

    return render(request, "clinic/form_tipo.html", {"form": form})


@grupos_requeridos(*GRUPOS_CLINICA_EDITAR)
def editar_tipo(request, pk):
    tipo = get_object_or_404(TipoAtendimento, pk=pk)
    if request.method == "POST":
        form = TipoAtendimentoForm(request.POST, instance=tipo)
        if form.is_valid():
            salvar_tipo(form=form)
            messages.success(request, "Tipo de atendimento atualizado com sucesso.")
            return redirect("clinica:listar_tipos")
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = TipoAtendimentoForm(instance=tipo)

    return render(request, "clinic/form_tipo.html", {
        "form": form,
        "tipo": tipo,
    })


@require_POST
@grupos_requeridos(*GRUPOS_CLINICA_EDITAR)
def alternar_tipo_ativo_view(request, pk):
    tipo = alternar_tipo_ativo(get_object_or_404(TipoAtendimento, pk=pk))
    messages.success(
        request,
        f"Tipo {tipo.nome} está agora {'ativo' if tipo.ativo else 'inativo'}.",
    )
    return redirect("clinica:listar_tipos")
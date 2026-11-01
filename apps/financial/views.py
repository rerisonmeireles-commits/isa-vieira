"""Views do módulo Financeiro: contas a receber, pagamentos e faturamento.

Padrão do projeto: view fina, service gorda.

RBAC:
  - Ver / consultar: Administrador, Financeiro, Recepção
  - Editar / baixar pagamento / faturamento: Administrador, Financeiro
"""

import datetime
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.constants import GRUPOS_FINANCEIRO_EDITAR, GRUPOS_FINANCEIRO_VER
from apps.accounts.permissions import grupos_requeridos
from apps.financial.forms import ContaReceberForm, FaturamentoLoteForm, PagamentoForm
from apps.financial.models import ContaReceber, Faturamento, Pagamento
from apps.financial.services import (
    confirmar_pagamento,
    contas_elegiveis_para_lote,
    editar_pagamento,
    estornar_pagamento,
    gerar_lote_faturamento,
    registrar_pagamento,
    salvar_conta,
    reparcelar_conta,
)
from apps.financial.exceptions import FinanceiroError

ITENS_POR_PAGINA = 20


def _pode_editar(usuario):
    return usuario.is_superuser or usuario.groups.filter(
        name__in=GRUPOS_FINANCEIRO_EDITAR
    ).exists()


def _querystring_sem_page(request):
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return parametros.urlencode()


# ---------------------------------------------------------------------------
# Contas a Receber
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_FINANCEIRO_VER)
def listar_contas(request):
    busca = (request.GET.get("q") or "").strip()
    status_filtro = request.GET.get("status") or ""

    contas = ContaReceber.objects.select_related("paciente", "convenio").annotate(
        total_pago=Coalesce(
            Sum("pagamentos__valor", filter=Q(pagamentos__status=Pagamento.Status.APROVADO)),
            Decimal("0"),
        )
    )

    if busca:
        contas = contas.filter(
            Q(paciente__nome_completo__icontains=busca)
            | Q(descricao__icontains=busca)
        )
    if status_filtro in dict(ContaReceber.Status.choices):
        contas = contas.filter(status=status_filtro)

    contas = contas.order_by("-data_vencimento")

    paginador = Paginator(contas, ITENS_POR_PAGINA)

    return render(request, "financial/listar_contas.html", {
        "pagina": paginador.get_page(request.GET.get("page")),
        "busca": busca,
        "status_filtro": status_filtro,
        "status_choices": ContaReceber.Status.choices,
        "pode_editar": _pode_editar(request.user),
        "total": paginador.count,
        "querystring": _querystring_sem_page(request),
    })


@grupos_requeridos(*GRUPOS_FINANCEIRO_VER)
def ficha_conta(request, pk):
    conta = get_object_or_404(
        ContaReceber.objects.select_related("paciente", "convenio", "agendamento__slot__agenda"),
        pk=pk,
    )
    pagamentos = conta.pagamentos.select_related("recebido_por").order_by("-data_pagamento")
    total_pago = pagamentos.filter(status=Pagamento.Status.APROVADO).aggregate(
        total=Sum("valor")
    )["total"] or Decimal("0")

    return render(request, "financial/ficha_conta.html", {
        "conta": conta,
        "pagamentos": pagamentos,
        "total_pago": total_pago,
        "saldo": conta.valor_total - total_pago,
        "pagamento_form": PagamentoForm(),
        "pode_editar": _pode_editar(request.user),
    })


@grupos_requeridos(*GRUPOS_FINANCEIRO_EDITAR)
def criar_conta(request):
    if request.method == "POST":
        form = ContaReceberForm(request.POST)
        if form.is_valid():
            try:
                resultado = salvar_conta(
                    form=form,
                    usuario=request.user if request.user.is_authenticated else None,
                )
            except FinanceiroError as erro:
                messages.error(request, str(erro))
                return render(request, "financial/form_conta.html", {"form": form})
            if isinstance(resultado, list):   # parcelas > 1 → lista de contas
                messages.success(
                    request,
                    f"{len(resultado)} parcelas registradas para "
                    f"{resultado[0].paciente.nome_completo}.",
                )
                return redirect("financial:listar_contas")
            messages.success(request, f"Conta de {resultado.paciente.nome_completo} criada.")
            return redirect("financial:ficha_conta", pk=resultado.pk)
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = ContaReceberForm()

    return render(request, "financial/form_conta.html", {
        "form": form,
    })


@require_POST
@grupos_requeridos(*GRUPOS_FINANCEIRO_EDITAR)
def baixa_pagamento(request, pk):
    conta = get_object_or_404(ContaReceber, pk=pk)
    form = PagamentoForm(request.POST, request.FILES)
    if form.is_valid():
        registrar_pagamento(
            conta=conta,
            form=form,
            usuario=request.user if request.user.is_authenticated else None,
        )
        messages.success(request, "Pagamento registrado com sucesso.")
    else:
        messages.error(request, "Corrija os campos do pagamento antes de salvar.")

    return redirect("financial:ficha_conta", pk=conta.pk)


# ---------------------------------------------------------------------------
# Faturamento (lote de guias)
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_FINANCEIRO_VER)
def listar_faturamentos(request):
    faturamentos = Faturamento.objects.select_related("convenio").order_by("-periodo_inicio")
    paginador = Paginator(faturamentos, ITENS_POR_PAGINA)
    return render(request, "financial/listar_faturamentos.html", {
        "pagina": paginador.get_page(request.GET.get("page")),
        "pode_editar": _pode_editar(request.user),
        "total": paginador.count,
        "querystring": _querystring_sem_page(request),
    })


@grupos_requeridos(*GRUPOS_FINANCEIRO_EDITAR)
def criar_faturamento(request):
    """Cria o lote via service: totais e status calculados das contas."""
    if request.method == "POST":
        form = FaturamentoLoteForm(request.POST)
        if form.is_valid():
            try:
                lote = gerar_lote_faturamento(
                    convenio=form.cleaned_data["convenio"],
                    periodo_inicio=form.cleaned_data["periodo_inicio"],
                    periodo_fim=form.cleaned_data["periodo_fim"],
                    usuario=request.user if request.user.is_authenticated else None,
                )
            except FinanceiroError as erro:
                messages.error(request, str(erro))
            else:
                messages.success(
                    request,
                    f"Lote gerado: {lote.guias_enviadas} guia(s), "
                    f"total R$ {lote.valor_total}.",
                )
                return redirect("financial:listar_faturamentos")
        else:
            messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = FaturamentoLoteForm()

    return render(request, "financial/form_faturamento.html", {"form": form})


@grupos_requeridos(*GRUPOS_FINANCEIRO_EDITAR)
def preview_lote(request):
    """Fragmento HTMX: contas elegíveis para o lote (convênio + período)."""
    convenio_id = (request.GET.get("convenio") or "").strip()
    inicio = (request.GET.get("periodo_inicio") or "").strip()
    fim = (request.GET.get("periodo_fim") or "").strip()

    contexto = {"elegiveis": None, "total": Decimal("0")}
    if convenio_id.isdigit() and inicio and fim:
        try:
            data_inicio = datetime.date.fromisoformat(inicio)
            data_fim = datetime.date.fromisoformat(fim)
        except ValueError:
            contexto["elegiveis"] = []
        else:
            contas = contas_elegiveis_para_lote(
                convenio_id=int(convenio_id),
                periodo_inicio=data_inicio,
                periodo_fim=data_fim,
            )
            contexto["elegiveis"] = contas
            contexto["total"] = (
                contas.aggregate(total=Sum("valor_total"))["total"] or Decimal("0")
            )
    return render(request, "financial/_lote_preview.html", contexto)


@grupos_requeridos(*GRUPOS_FINANCEIRO_VER)
def ficha_faturamento(request, pk):
    lote = get_object_or_404(Faturamento.objects.select_related("convenio"), pk=pk)
    contas = lote.contas_faturadas.select_related("paciente").order_by("data_vencimento")
    return render(request, "financial/ficha_faturamento.html", {
        "lote": lote,
        "contas": contas,
        "pode_editar": _pode_editar(request.user),
    })

@require_POST
@grupos_requeridos(*GRUPOS_FINANCEIRO_EDITAR)
def reparcelar_conta_view(request, pk):
    """Substitui a conta por N parcelas (fluxo 'paciente pediu para parcelar')."""
    conta = get_object_or_404(ContaReceber, pk=pk)
    try:
        n = int(request.POST.get("parcelas") or 0)
    except (TypeError, ValueError):
        n = 0
    try:
        parcelas = reparcelar_conta(
            conta=conta,
            n_parcelas=n,
            usuario=request.user if request.user.is_authenticated else None,
        )
    except FinanceiroError as erro:
        messages.error(request, str(erro))
        return redirect("financial:ficha_conta", pk=conta.pk)
    messages.success(request, f"Conta substituída por {len(parcelas)} parcela(s).")
    return redirect("financial:ficha_conta", pk=parcelas[0].pk)

# ---------------------------------------------------------------------------
# Pagamentos - ações pontuais
# ---------------------------------------------------------------------------

@require_POST
@grupos_requeridos(*GRUPOS_FINANCEIRO_EDITAR)
def confirmar_pagamento_view(request, pk):
    """Confirma um pagamento pendente (PENDENTE → APROVADO)."""
    pagamento = get_object_or_404(Pagamento, pk=pk)
    try:
        confirmar_pagamento(
            pagamento_id=pagamento.pk,
            usuario=request.user if request.user.is_authenticated else None,
        )
    except FinanceiroError as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, "Pagamento confirmado com sucesso.")
    return redirect("financial:ficha_conta", pk=pagamento.conta_receber.pk)


@require_POST
@grupos_requeridos(*GRUPOS_FINANCEIRO_EDITAR)
def estornar_pagamento_view(request, pk):
    """Estorna um pagamento aprovado (APROVADO → ESTORNADO) e recalcula a conta."""
    pagamento = get_object_or_404(Pagamento, pk=pk)
    try:
        estornar_pagamento(
            pagamento_id=pagamento.pk,
            usuario=request.user if request.user.is_authenticated else None,
        )
    except FinanceiroError as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, "Pagamento estornado; status da conta recalculado.")
    return redirect("financial:ficha_conta", pk=pagamento.conta_receber.pk)


@grupos_requeridos(*GRUPOS_FINANCEIRO_EDITAR)
def editar_pagamento_view(request, pk):
    """Edita um pagamento existente (valor, forma, status, comprovante)."""
    pagamento = get_object_or_404(
        Pagamento.objects.select_related("conta_receber__paciente"),
        pk=pk,
    )

    if request.method == "POST":
        form = PagamentoForm(request.POST, request.FILES, instance=pagamento)
        if form.is_valid():
            editar_pagamento(pagamento=pagamento, form=form)
            messages.success(request, "Pagamento atualizado com sucesso.")
            return redirect("financial:ficha_conta", pk=pagamento.conta_receber.pk)
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = PagamentoForm(instance=pagamento)

    return render(request, "financial/form_pagamento.html", {
        "form": form,
        "pagamento": pagamento,
    })
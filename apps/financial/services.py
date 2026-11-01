"""Regras de negócio do módulo Financeiro.

Padrão do projeto: view fina, service gorda. Todos os fluxos de escrita
passam por _recalcular_status_conta, que deriva o status da conta
(PAGA/PARCIAL/ABERTA/ATRASADA) e, em cadeia, o status do lote de
faturamento (EMITIDO/PARCIAL/PAGO).
"""

from datetime import timedelta
from decimal import Decimal, ROUND_DOWN

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.financial.models import ContaReceber, Faturamento, Pagamento
from apps.financial.exceptions import FinanceiroError


# ---------------------------------------------------------------------------
# Contas a Receber
# ---------------------------------------------------------------------------
@transaction.atomic
def salvar_conta(*, form, usuario):
    """Salva uma conta a receber; com parcelas > 1, gera N contas escalonadas.

    Trava anti-duplicação: agendamento com conta ativa não recebe outra -
    para parcelar uma conta existente, use reparcelar_conta (ficha da conta).
    Retorna a conta única (parcelas=1) ou a lista de parcelas geradas.
    """
    agendamento = form.cleaned_data.get("agendamento")
    if agendamento and agendamento.contas_receber.exists():
        raise FinanceiroError(
            "Este agendamento já possui conta a receber. "
            "Para parcelar a conta existente, use 'Reparcelar' na ficha da conta."
        )

    n = max(1, int(form.cleaned_data.get("parcelas") or 1))
    if n > 1:
        return _gerar_parcelas(form, usuario, n)

    conta = form.save(commit=False)
    if not conta.criado_por_id:
        conta.criado_por = usuario
    conta.save()
    return conta


def _criar_parcelas(*, paciente, convenio, agendamento, tipo, descricao,
                    valor_total, data_vencimento, forma_pagamento, usuario, n):
    """Gera N contas com vencimentos a cada 30 dias.

    A última parcela absorve o centavo do arredondamento; apenas a 1ª
    fica vinculada ao agendamento (preserva a trava anti-duplicação do
    check-out). Cada parcela nasce ABERTA e evolui sozinha.
    """
    valor_base = (valor_total / n).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    valor_ultima = valor_total - valor_base * (n - 1)

    contas = []
    vencimento = data_vencimento
    for i in range(1, n + 1):
        contas.append(
            ContaReceber.objects.create(
                paciente=paciente,
                convenio=convenio,
                agendamento=agendamento if i == 1 else None,
                tipo=tipo,
                descricao=f"{descricao} - parcela {i}/{n}",
                valor_total=valor_ultima if i == n else valor_base,
                parcelas=1,
                data_vencimento=vencimento,
                status=ContaReceber.Status.ABERTA,
                forma_pagamento=forma_pagamento,
                criado_por=usuario,
            )
        )
        vencimento += timedelta(days=30)
    return contas


def _gerar_parcelas(form, usuario, n):
    """Adapta o form preenchido para a geração de parcelas."""
    base = form.save(commit=False)
    if not base.data_vencimento:
        raise FinanceiroError("Informe a data de vencimento para gerar parcelas.")
    return _criar_parcelas(
        paciente=base.paciente,
        convenio=base.convenio,
        agendamento=base.agendamento,
        tipo=base.tipo,
        descricao=base.descricao,
        valor_total=base.valor_total,
        data_vencimento=base.data_vencimento,
        forma_pagamento=base.forma_pagamento,
        usuario=usuario,
        n=n,
    )


@transaction.atomic
def reparcelar_conta(*, conta, n_parcelas, usuario=None):
    """Substitui uma conta ABERTA sem pagamentos por N parcelas.

    Fluxo do cenário 'paciente pediu para parcelar': a conta automática
    do check-out é cancelada (soft delete) e substituída pelas parcelas -
    as duas nunca coexistem. Bloqueios: pagamento aprovado, lote de
    faturamento ou falta de vencimento impedem o reparcelamento.
    """
    if not n_parcelas or n_parcelas <= 1:
        raise FinanceiroError("Informe um número de parcelas maior que 1.")
    if conta.faturamento_id:
        raise FinanceiroError(
            "Conta vinculada a um lote de faturamento não pode ser reparcelada."
        )
    total_aprovado = conta.pagamentos.filter(
        status=Pagamento.Status.APROVADO
    ).aggregate(total=Sum("valor"))["total"] or Decimal("0")
    if total_aprovado > 0:
        raise FinanceiroError(
            "Conta com pagamentos aprovados não pode ser reparcelada. "
            "Estorne os pagamentos primeiro."
        )
    if not conta.data_vencimento:
        raise FinanceiroError("Conta sem data de vencimento não pode ser reparcelada.")

    parcelas = _criar_parcelas(
        paciente=conta.paciente,
        convenio=conta.convenio,
        agendamento=conta.agendamento,
        tipo=conta.tipo,
        descricao=conta.descricao,
        valor_total=conta.valor_total,
        data_vencimento=conta.data_vencimento,
        forma_pagamento=conta.forma_pagamento,
        usuario=usuario,
        n=n_parcelas,
    )
    conta.deleted_at = timezone.now()
    conta.save(update_fields=["deleted_at"])
    return parcelas



def _recalcular_status_conta(conta):
    """Recalcula o status da conta a partir dos pagamentos APROVADOS.

    Regras:
      - PAGA: total pago >= valor_total
      - PARCIAL: algum pagamento aprovado, mas não cobre o total
      - ABERTA: nenhum pagamento aprovado
      - ATRASADA: vencida e não paga (derivado - nunca digitado à mão)
    Se a conta pertence a um lote, o status do lote é recalculado junto.
    """
    total_pago = conta.pagamentos.filter(
        status=Pagamento.Status.APROVADO
    ).aggregate(total=Sum("valor"))["total"] or Decimal("0")

    if conta.valor_total > 0 and total_pago >= conta.valor_total:
        conta.status = ContaReceber.Status.PAGA
    elif total_pago > 0:
        conta.status = ContaReceber.Status.PARCIAL
    else:
        conta.status = ContaReceber.Status.ABERTA

    if (
        conta.status != ContaReceber.Status.PAGA
        and conta.data_vencimento
        and conta.data_vencimento < timezone.localdate()
    ):
        conta.status = ContaReceber.Status.ATRASADA

    conta.save(update_fields=["status", "updated_at"])

    if conta.faturamento_id:
        _recalcular_status_lote(conta.faturamento)

    return total_pago


def _recalcular_status_lote(lote):
    """Deriva o status do lote das contas vinculadas.

    Todas as contas PAGA → lote PAGO; alguma paga → PARCIAL;
    nenhuma paga → EMITIDO.
    """
    contas = lote.contas_faturadas.all()
    total = contas.count()
    pagas = contas.filter(status=ContaReceber.Status.PAGA).count()

    if total and pagas == total:
        lote.status = Faturamento.Status.PAGO
    elif pagas:
        lote.status = Faturamento.Status.PARCIAL
    else:
        lote.status = Faturamento.Status.EMITIDO

    lote.save(update_fields=["status"])


@transaction.atomic
def gerar_conta_do_atendimento(*, atendimento):
    """Gera a ContaReceber de uma sessão concluída (chamado no check-out).

    Se o agendamento já possui conta, não duplica.
    Retorna None se o tipo de atendimento não tiver valor configurado -
    nesse caso, a conta deve ser criada manualmente pelo Financeiro.
    """
    agendamento = atendimento.agendamento
    if agendamento.contas_receber.exists():
        return agendamento.contas_receber.first()

    valor = atendimento.tipo_atendimento.valor_padrao
    if valor is None or valor <= 0:
        return None

    return ContaReceber.objects.create(
        paciente=atendimento.paciente,
        convenio=agendamento.convenio,
        agendamento=agendamento,
        tipo=ContaReceber.Tipo.SESSAO,
        descricao=f"Sessão de {atendimento.tipo_atendimento.nome}",
        valor_total=valor,
        data_vencimento=agendamento.slot.agenda.data,
        status=ContaReceber.Status.ABERTA,
    )


# ---------------------------------------------------------------------------
# Pagamentos
# ---------------------------------------------------------------------------

@transaction.atomic
def registrar_pagamento(*, conta, form, usuario):
    """Registra um pagamento e recalcula o status da conta."""
    pagamento = form.save(commit=False)
    pagamento.conta_receber = conta
    pagamento.recebido_por = usuario
    pagamento.save()
    _recalcular_status_conta(conta)
    return pagamento


@transaction.atomic
def confirmar_pagamento(*, pagamento_id, usuario=None):
    """Confirma um pagamento pendente/recusado (→ APROVADO) e recalcula a conta.

    Regras:
      - Apenas PENDENTE ou RECUSADO podem ser confirmados.
      - O recálculo roda na mesma transação (PENDENTE → APROVADO pode
        levar a conta de ABERTA para PAGA automaticamente).
    """
    pagamento = (
        Pagamento.objects
        .select_for_update(of=("self",))          # disciplina de lock do projeto
        .select_related("conta_receber")
        .get(pk=pagamento_id)
    )

    if pagamento.status not in (
        Pagamento.Status.PENDENTE,
        Pagamento.Status.RECUSADO,
    ):
        raise FinanceiroError(
            "Apenas pagamentos pendentes ou recusados podem ser confirmados."
        )

    pagamento.status = Pagamento.Status.APROVADO
    pagamento.save(update_fields=["status"])      # Pagamento não tem updated_at

    _recalcular_status_conta(pagamento.conta_receber)
    return pagamento


@transaction.atomic
def estornar_pagamento(*, pagamento_id, usuario=None):
    """Estorna um pagamento APROVADO (→ ESTORNADO) e recalcula a conta.

    O valor estornado sai do total pago: uma conta PAGA pode voltar a
    PARCIAL/ABERTA (ou ATRASADA, se vencida) na mesma transação.
    """
    pagamento = (
        Pagamento.objects
        .select_for_update(of=("self",))          # disciplina de lock do projeto
        .select_related("conta_receber")
        .get(pk=pagamento_id)
    )

    if pagamento.status != Pagamento.Status.APROVADO:
        raise FinanceiroError("Apenas pagamentos aprovados podem ser estornados.")

    pagamento.status = Pagamento.Status.ESTORNADO
    pagamento.save(update_fields=["status"])

    _recalcular_status_conta(pagamento.conta_receber)
    return pagamento


@transaction.atomic
def editar_pagamento(*, pagamento, form):
    """Atualiza um pagamento existente e recalcula o status da conta.

    Permite corrigir forma/valor/observações/data e anexar o comprovante.
    Se o status for alterado no formulário, o recálculo ajusta a conta
    na mesma transação.
    """
    pagamento = form.save()
    _recalcular_status_conta(pagamento.conta_receber)
    return pagamento


# ---------------------------------------------------------------------------
# Faturamento (lote de guias)
# ---------------------------------------------------------------------------

def contas_elegiveis_para_lote(*, convenio_id, periodo_inicio, periodo_fim):
    """Contas aptas a entrar em um lote (sem lock).

    Usada pelo preview HTMX e por gerar_lote_faturamento - critério único,
    sem drift entre o que o usuário vê e o que entra no lote.
    """
    return (
        ContaReceber.objects
        .select_related("paciente")
        .filter(
            convenio_id=convenio_id,
            faturamento__isnull=True,
            status__in=[
                ContaReceber.Status.ABERTA,
                ContaReceber.Status.PARCIAL,
                ContaReceber.Status.ATRASADA,
            ],
            data_vencimento__range=(periodo_inicio, periodo_fim),
        )
        .order_by("data_vencimento")
    )


@transaction.atomic
def gerar_lote_faturamento(*, convenio, periodo_inicio, periodo_fim, usuario=None):
    """Gera o lote de faturamento do convênio no período.

    Elegíveis: contas não pagas do convênio, sem lote, vencimento no
    período. valor_total e guias_enviadas são CALCULADOS das contas
    vinculadas - nunca digitados. Lotes sobrepostos são self-healing:
    a 1ª chamada leva as contas; a seguinte falha sem elegíveis.
    """
    contas = list(
        contas_elegiveis_para_lote(
            convenio_id=convenio.pk,
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
        ).select_for_update()
    )
    if not contas:
        raise FinanceiroError("Nenhuma conta elegível no período para este convênio.")

    lote = Faturamento.objects.create(
        convenio=convenio,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        valor_total=Decimal("0"),
        guias_enviadas=0,
        status=Faturamento.Status.EMITIDO,
    )

    total = Decimal("0")
    for conta in contas:
        conta.faturamento = lote
        conta.save(update_fields=["faturamento", "updated_at"])
        total += conta.valor_total

    lote.valor_total = total
    lote.guias_enviadas = len(contas)
    lote.save(update_fields=["valor_total", "guias_enviadas"])
    return lote
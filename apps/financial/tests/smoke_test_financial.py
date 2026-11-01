# =============================================================================
# SMOKE FUNCIONAL — FINANCEIRO (contas, pagamentos, faturamento)
# PARTE A: RBAC por status code nas rotas do módulo.
# PARTE B: ciclo funcional via services — parcelas, pagamentos, estorno,
#          confirmação, lote de faturamento, ATRASADA, travas e reparcelamento.
# Padrão dos smokes: check(), usuários get_or_create, limpeza _raw_delete,
# idempotente (pode rodar quantas vezes quiser).
# =============================================================================
import os
from datetime import timedelta
from decimal import Decimal

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")  # ← confira no manage.py
django.setup()

import logging
logging.getLogger("django.request").setLevel(logging.CRITICAL)  # silencia o traceback cosmético dos 403

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.accounts.models import Usuario
from apps.accounts.constants import (
    GRUPO_ADMINISTRADOR,      # ← Passo 0: confirme os 4 nomes
    GRUPO_FISIOTERAPEUTA,
    GRUPO_RECEPCAO,
    GRUPO_FINANCEIRO,
)
from apps.financial.forms import ContaReceberForm, PagamentoForm
from apps.financial.models import ContaReceber, Faturamento, Pagamento
from apps.financial.services import (
    salvar_conta,
    registrar_pagamento,
    confirmar_pagamento,
    estornar_pagamento,
    gerar_lote_faturamento,
    reparcelar_conta,
)
from apps.financial.exceptions import FinanceiroError
from apps.patients.models import Paciente
from apps.insurance.models import Convenio   # ← Passo 0: confirme o app do Convenio

TOTAL = 0
FALHAS = []

def check(descricao, ok):
    global TOTAL
    TOTAL += 1
    print(("✅ " if ok else "❌ ") + descricao)
    if not ok:
        FALHAS.append(descricao)

HOJE = timezone.localdate()

# --- Limpeza física (idempotente): tudo SMOKE é rastreável pelo prefixo ---
def _limpar_smoke():
    contas = list(ContaReceber._base_manager.filter(descricao__startswith="SMOKE FIN"))
    pks = [c.pk for c in contas]
    if pks:
        Pagamento._base_manager.filter(conta_receber_id__in=pks)._raw_delete(using="default")
        ContaReceber._base_manager.filter(pk__in=pks)._raw_delete(using="default")
    convenio_smoke = Convenio._base_manager.filter(nome__startswith="SMOKE Convênio").first()
    if convenio_smoke:
        Faturamento._base_manager.filter(convenio_id=convenio_smoke.pk)._raw_delete(using="default")
        Convenio._base_manager.filter(pk=convenio_smoke.pk)._raw_delete(using="default")

print("--- SMOKE FUNCIONAL FINANCEIRO ---")

# --- Setup: usuários dos 4 perfis (idempotente) ---
def _usuario(username, grupo_nome):
    grupo, _ = Group.objects.get_or_create(name=grupo_nome)
    user, criado = Usuario.objects.get_or_create(
        username=username,
        defaults={"email": f"{username}@smoke.local", "is_active": True},
    )
    if criado:
        user.set_password("smoke-1234")
        user.save()
    user.groups.add(grupo)
    return user

admin = _usuario("smoke_admin", GRUPO_ADMINISTRADOR)
financ = _usuario("smoke_financ", GRUPO_FINANCEIRO)
recepcao = _usuario("smoke_recepcao", GRUPO_RECEPCAO)
fisio = _usuario("smoke_fisio", GRUPO_FISIOTERAPEUTA)

# =============================================================================
# PARTE A — RBAC (status codes)
# VER: Administrador, Financeiro, Recepção | EDITAR: Administrador, Financeiro
# =============================================================================
print("\n--- PARTE A: RBAC (status codes) ---")
client = Client()

client.force_login(admin)
check("smoke_admin em /financeiro/ → 200", client.get("/financeiro/").status_code == 200)

client.force_login(financ)
check("smoke_financ em /financeiro/ → 200", client.get("/financeiro/").status_code == 200)
check("smoke_financ em /financeiro/faturamentos/ → 200",
      client.get("/financeiro/faturamentos/").status_code == 200)

client.force_login(recepcao)
check("smoke_recepcao em /financeiro/ → 200", client.get("/financeiro/").status_code == 200)
check("smoke_recepcao em POST nova conta → 403",
      client.post("/financeiro/conta/nova/").status_code == 403)

client.force_login(fisio)
check("smoke_fisio em /financeiro/ → 403", client.get("/financeiro/").status_code == 403)
check("smoke_fisio em POST nova conta → 403",
      client.post("/financeiro/conta/nova/").status_code == 403)
check("smoke_fisio em /financeiro/faturamentos/ → 403",
      client.get("/financeiro/faturamentos/").status_code == 403)

# =============================================================================
# PARTE B — Ciclo funcional (services)
# =============================================================================
print("\n--- PARTE B: ciclo funcional (services) ---")

# Resíduos de execuções anteriores ANTES de criar o convênio SMOKE
_limpar_smoke()

paciente = Paciente.objects.filter(status=Paciente.Status.ATIVO).first()
check("Existe paciente ativo", paciente is not None)

convenio_smoke, _ = Convenio.objects.get_or_create(nome="SMOKE Convênio Financeiro")
check("Convênio SMOKE disponível", convenio_smoke is not None)

# --- Helpers de dados ---
def _forma_conta():
    campo = ContaReceber._meta.get_field("forma_pagamento")
    return campo.choices[0][0] if campo.choices else ""

def _forma_pagamento():
    campo = Pagamento._meta.get_field("forma")
    return campo.choices[0][0] if campo.choices else ""

def _form_conta(**overrides):
    dados = {
        "paciente": paciente.pk,
        "tipo": ContaReceber.Tipo.SESSAO,
        "descricao": "SMOKE FIN conta",
        "valor_total": "600.00",
        "parcelas": "1",
        "data_vencimento": HOJE.isoformat(),
        "forma_pagamento": _forma_conta(),
    }
    dados.update(overrides)
    return ContaReceberForm(data=dados)

def _form_pagamento(valor, status):
    return PagamentoForm(data={
        "valor": str(valor),
        "forma": _forma_pagamento(),
        "status": status,
        "data_pagamento": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
    })

def _pagamento_direto(conta, valor, status):
    return Pagamento.objects.create(
        conta_receber=conta,
        valor=Decimal(valor),
        forma=_forma_pagamento(),
        status=status,
    )

# --- 1. Status não é digitável (furo do cenário "editar para ABERTA") ---
check("ContaReceberForm não expõe o campo status",
      "status" not in ContaReceberForm._meta.fields)

# --- 2. Parcelas escalonadas via salvar_conta ---
form = _form_conta(parcelas="3", descricao="SMOKE FIN parcelado", valor_total="600.00")
check("Form de conta com parcelas válido", form.is_valid())
if form.is_valid():
    parcelas = salvar_conta(form=form, usuario=admin)
    check("salvar_conta com parcelas=3 → 3 contas",
          isinstance(parcelas, list) and len(parcelas) == 3)
    if isinstance(parcelas, list) and len(parcelas) == 3:
        check("Valores 200/200/200 (última absorve o centavo)",
              [p.valor_total for p in parcelas]
              == [Decimal("200.00"), Decimal("200.00"), Decimal("200.00")])
        check("Vencimentos escalonados (+30 dias)",
              parcelas[1].data_vencimento - parcelas[0].data_vencimento == timedelta(days=30)
              and parcelas[2].data_vencimento - parcelas[1].data_vencimento == timedelta(days=30))
        check("Descrição identifica a parcela", parcelas[0].descricao.endswith("parcela 1/3"))
else:
    print("⚠️ Form inválido:", form.errors)

# --- 3. Pagamentos: parcial → paga → estorno → confirmação ---
conta_pag = ContaReceber.objects.create(
    paciente=paciente, convenio=None, tipo=ContaReceber.Tipo.SESSAO,
    descricao="SMOKE FIN pagamentos", valor_total=Decimal("200.00"),
    parcelas=1, data_vencimento=HOJE, status=ContaReceber.Status.ABERTA,
    forma_pagamento=_forma_conta(), criado_por=admin,
)

form_pg = _form_pagamento("100.00", Pagamento.Status.APROVADO)
check("Form de pagamento válido", form_pg.is_valid())
if form_pg.is_valid():
    registrar_pagamento(conta=conta_pag, form=form_pg, usuario=admin)
    conta_pag.refresh_from_db()
    check("Pagamento parcial → conta PARCIAL", conta_pag.status == ContaReceber.Status.PARCIAL)

    registrar_pagamento(conta=conta_pag,
                        form=_form_pagamento("100.00", Pagamento.Status.APROVADO),
                        usuario=admin)
    conta_pag.refresh_from_db()
    check("Pagamento completa → conta PAGA", conta_pag.status == ContaReceber.Status.PAGA)

    aprovado = conta_pag.pagamentos.filter(status=Pagamento.Status.APROVADO).first()
    estornar_pagamento(pagamento_id=aprovado.pk, usuario=admin)
    aprovado.refresh_from_db()
    conta_pag.refresh_from_db()
    check("Estorno → pagamento ESTORNADO e conta PARCIAL",
          aprovado.status == Pagamento.Status.ESTORNADO
          and conta_pag.status == ContaReceber.Status.PARCIAL)

    pendente = _pagamento_direto(conta_pag, "100.00", Pagamento.Status.PENDENTE)
    confirmar_pagamento(pagamento_id=pendente.pk, usuario=admin)
    pendente.refresh_from_db()
    conta_pag.refresh_from_db()
    check("Confirmação → APROVADO e conta PAGA",
          pendente.status == Pagamento.Status.APROVADO
          and conta_pag.status == ContaReceber.Status.PAGA)

# --- 4. Lote de faturamento: totais calculados, self-healing, cadeia ---
lote_contas = [
    ContaReceber.objects.create(
        paciente=paciente, convenio=convenio_smoke, tipo=ContaReceber.Tipo.SESSAO,
        descricao=f"SMOKE FIN lote {i}", valor_total=Decimal(v),
        parcelas=1, data_vencimento=HOJE, status=ContaReceber.Status.ABERTA,
        forma_pagamento=_forma_conta(), criado_por=admin,
    )
    for i, v in [(1, "150.00"), (2, "250.00")]
]

lote = gerar_lote_faturamento(
    convenio=convenio_smoke,
    periodo_inicio=HOJE - timedelta(days=7),
    periodo_fim=HOJE + timedelta(days=7),
    usuario=admin,
)
check("Lote gerado com status EMITIDO", lote.status == Faturamento.Status.EMITIDO)
check("Lote calcula guias das contas (2)", lote.guias_enviadas == 2)
check("Lote calcula total das contas (400)", lote.valor_total == Decimal("400.00"))

try:
    gerar_lote_faturamento(convenio=convenio_smoke,
                           periodo_inicio=HOJE - timedelta(days=7),
                           periodo_fim=HOJE + timedelta(days=7))
    check("Lote repetido no mesmo período é bloqueado", False)
except FinanceiroError:
    check("Lote repetido no mesmo período é bloqueado", True)

# Os objetos de lote_contas foram criados ANTES do gerar_lote_faturamento
# vinculá-los — em memória, faturamento_id ainda é None. refresh_from_db()
# recarrega o vínculo gravado no banco (as views de produção sempre buscam
# objetos frescos, então esse artefato só existe no teste).
primeira, segunda = lote_contas
primeira.refresh_from_db()
registrar_pagamento(conta=primeira,
                    form=_form_pagamento(str(primeira.valor_total), Pagamento.Status.APROVADO),
                    usuario=admin)
lote.refresh_from_db()
check("Recálculo em cadeia: 1ª paga → lote PARCIAL", lote.status == Faturamento.Status.PARCIAL)

segunda.refresh_from_db()
registrar_pagamento(conta=segunda,
                    form=_form_pagamento(str(segunda.valor_total), Pagamento.Status.APROVADO),
                    usuario=admin)
lote.refresh_from_db()
check("Recálculo em cadeia: ambas pagas → lote PAGO", lote.status == Faturamento.Status.PAGO)

# --- 5. ATRASADA derivada via management command ---
conta_atrasada = ContaReceber.objects.create(
    paciente=paciente, convenio=convenio_smoke, tipo=ContaReceber.Tipo.SESSAO,
    descricao="SMOKE FIN atrasada", valor_total=Decimal("100.00"),
    parcelas=1, data_vencimento=HOJE - timedelta(days=30),
    status=ContaReceber.Status.ABERTA, forma_pagamento=_forma_conta(),
    criado_por=admin,
)
call_command("marcar_contas_atrasadas")
conta_atrasada.refresh_from_db()
check("Command marca conta vencida como ATRASADA",
      conta_atrasada.status == ContaReceber.Status.ATRASADA)

# --- 6. Trava anti-duplicação (usa agendamento real que já tem conta) ---
ocupada = (ContaReceber.objects
           .filter(agendamento__isnull=False, deleted_at__isnull=True)
           .exclude(descricao__startswith="SMOKE FIN")
           .first())
if ocupada:
    form_trava = _form_conta(
        agendamento=ocupada.agendamento_id,
        paciente=ocupada.paciente_id,
        descricao="SMOKE FIN trava",
        valor_total="100.00",
    )
    if form_trava.is_valid():
        try:
            salvar_conta(form=form_trava, usuario=admin)
            check("Trava: agendamento com conta não recebe outra", False)
        except FinanceiroError:
            check("Trava: agendamento com conta não recebe outra", True)
    else:
        print("⚠️ Form da trava inválido:", form_trava.errors)
else:
    print("⚠️ Nenhum agendamento com conta no banco — teste da trava pulado.")

# --- 7. Reparcelamento: substituição com soft delete + bloqueio ---
conta_rep = ContaReceber.objects.create(
    paciente=paciente, convenio=None, tipo=ContaReceber.Tipo.SESSAO,
    descricao="SMOKE FIN reparcelar", valor_total=Decimal("300.00"),
    parcelas=1, data_vencimento=HOJE, status=ContaReceber.Status.ABERTA,
    forma_pagamento=_forma_conta(), criado_por=admin,
)
parcelas_rep = reparcelar_conta(conta=conta_rep, n_parcelas=3, usuario=admin)
check("Reparcelamento gera 3 parcelas",
      isinstance(parcelas_rep, list) and len(parcelas_rep) == 3)
conta_rep.refresh_from_db()
check("Conta original cancelada (soft delete) e some da lista",
      conta_rep.deleted_at is not None
      and not ContaReceber.objects.filter(pk=conta_rep.pk).exists())

conta_bloqueada = ContaReceber.objects.create(
    paciente=paciente, convenio=None, tipo=ContaReceber.Tipo.SESSAO,
    descricao="SMOKE FIN bloqueada", valor_total=Decimal("100.00"),
    parcelas=1, data_vencimento=HOJE, status=ContaReceber.Status.ABERTA,
    forma_pagamento=_forma_conta(), criado_por=admin,
)
_pagamento_direto(conta_bloqueada, "100.00", Pagamento.Status.APROVADO)
try:
    reparcelar_conta(conta=conta_bloqueada, n_parcelas=3, usuario=admin)
    check("Reparcelamento bloqueado com pagamento aprovado", False)
except FinanceiroError:
    check("Reparcelamento bloqueado com pagamento aprovado", True)

# --- Limpeza ---
print("\n--- Limpeza ---")
try:
    _limpar_smoke()
    print("Dados SMOKE removidos (contas, pagamentos, lote e convênio).")
except Exception as erro:
    print(f"⚠️ Erro na limpeza: {erro}")

print("\n" + "=" * 50)
print(f"RESULTADO: {TOTAL - len(FALHAS)}/{TOTAL} checks OK")
if FALHAS:
    print("Falhas:")
    for f in FALHAS:
        print(f" - {f}")
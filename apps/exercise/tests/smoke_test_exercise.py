# smoke_test_exercise.py — Smoke test do módulo exercise
# Execução: python smoke_test_exercise.py
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import logging
logging.getLogger("django.request").setLevel(logging.CRITICAL)

from django.test import Client
from django.contrib.auth.models import Group

from apps.accounts.constants import (
    GRUPO_ADMINISTRADOR, GRUPO_RECEPCAO, GRUPO_FISIOTERAPEUTA, GRUPO_FINANCEIRO,
)
from apps.accounts.models import Usuario
from apps.exercise.models import (
    ExecucaoExercicio, Exercicio, Prescricao, PrescricaoExercicio,
)
from apps.exercise import services
from apps.exercise.services import (
    PermissaoExercicioError, ExercicioStatusInvalidoError,
)

resultados = []

def check(nome, condicao):
    resultados.append((nome, bool(condicao)))
    print(("✅" if condicao else "❌"), nome)

# ---------------------------------------------------------------------------
# Limpeza defensiva (ordem respeitando ON DELETE PROTECT: filho → pai)
# ---------------------------------------------------------------------------
def limpar_smoke():
    """Exclusão FÍSICA dos dados SMOKE — _raw_delete ignora o soft delete.

    _base_manager enxerga também as linhas soft-deletadas de execuções
    anteriores (objects filtraria e as deixaria para sempre);
    _raw_delete emite DELETE SQL direto, sem collector e sem o override
    lógico. Ordem filho → pai respeitando as FKs.
    """
    ExecucaoExercicio._base_manager.filter(
        prescricao_exercicio__prescricao__objetivo__startswith="SMOKE"
    )._raw_delete(using="default")
    PrescricaoExercicio._base_manager.filter(
        exercicio__nome__startswith="SMOKE"
    )._raw_delete(using="default")
    Prescricao._base_manager.filter(
        objetivo__startswith="SMOKE"
    )._raw_delete(using="default")
    Exercicio._base_manager.filter(
        nome__startswith="SMOKE"
    )._raw_delete(using="default")
    
limpar_smoke()

# ---------------------------------------------------------------------------
# Setup: usuários de teste (1 por perfil)
# ---------------------------------------------------------------------------
def criar_usuario(username, grupo_nome):
    grupo, _ = Group.objects.get_or_create(name=grupo_nome)
    usuario, criado = Usuario.objects.get_or_create(
        username=username,
        defaults={"email": f"{username}@smoke.local", "is_active": True},
    )
    if criado:
        usuario.set_password("smoke-1234")
        usuario.save()
    usuario.groups.add(grupo)
    return usuario

admin      = criar_usuario("smoke_admin",    GRUPO_ADMINISTRADOR)
recepcao   = criar_usuario("smoke_recepcao", GRUPO_RECEPCAO)
fisio      = criar_usuario("smoke_fisio",    GRUPO_FISIOTERAPEUTA)
financeiro = criar_usuario("smoke_financ",   GRUPO_FINANCEIRO)

# ---------------------------------------------------------------------------
# PARTE A — RBAC via cliente HTTP
# ---------------------------------------------------------------------------
print("\n--- PARTE A: RBAC (status codes) ---")

URLS_LEITURA = [
    ("/exercicios/exercicios/", "catálogo"),
    ("/exercicios/prescricoes/", "lista de prescrições"),
]

for url, rotulo in URLS_LEITURA:
    for usuario, esperado in [
        (fisio, 200), (admin, 200), (recepcao, 403), (financeiro, 403),
    ]:
        client = Client()
        client.force_login(usuario)
        resposta = client.get(url)
        check(
            f"{usuario.username} em {rotulo} → {esperado}",
            resposta.status_code == esperado,
        )

# POST em ação mutante sem grupo → 403
client = Client(); client.force_login(recepcao)
resposta = client.post("/exercicios/exercicios/1/inativar/")
check("Recepção em POST inativar → 403", resposta.status_code == 403)

# ---------------------------------------------------------------------------
# PARTE B — Ciclo de vida via services
# ---------------------------------------------------------------------------
print("\n--- PARTE B: ciclo da prescrição ---")

from apps.patients.models import Paciente
from apps.professionals.models import Profissional

paciente = Paciente.objects.filter(status=Paciente.Status.ATIVO).first()
profissional = Profissional.objects.first()

if not (paciente and profissional):
    print("⚠️  Cadastre ao menos 1 paciente ativo e 1 profissional antes de rodar a Parte B.")
else:
    try:
        ex1 = Exercicio.objects.create(nome="SMOKE — Agachamento livre", categoria="FORCA")
        ex2 = Exercicio.objects.create(nome="SMOKE — Ponte de glúteo", categoria="FORCA")

        presc = Prescricao.objects.create(
            paciente=paciente, profissional=profissional,
            objetivo="SMOKE — fortalecimento de MMII",
        )
        item1 = PrescricaoExercicio.objects.create(prescricao=presc, exercicio=ex1, ordem=1)
        item2 = PrescricaoExercicio.objects.create(prescricao=presc, exercicio=ex2, ordem=2)

        # 1. Reordenação em prescrição ATIVA
        services.reordenar_itens(presc, fisio, [item2.pk, item1.pk])
        presc.refresh_from_db()
        nova_primeira = presc.itens.order_by("ordem").first()
        check("Reordenar em ATIVA funciona", nova_primeira.pk == item2.pk)

        # 2. Execução em prescrição ATIVA — canal CLINICA
        exec1 = services.registrar_execucao_clinica(
            fisio, item1, paciente,
            {"realizado": True, "series_feitas": 3},
        )
        check("Execução registrada em ATIVA", exec1.pk is not None)
        check("criado_via == CLINICA", exec1.criado_via == "CLINICA")

        # 3. Encerrar com motivo
        services.encerrar_prescricao(presc, fisio, motivo="SMOKE — alta funcional")
        presc.refresh_from_db()
        check("Status → ENCERRADA", presc.status == "ENCERRADA")

        # 4. Regras pós-encerramento (todas devem BLOQUEAR)
        def bloqueia(fn, rotulo):
            try:
                fn()
                check(rotulo, False)   # não deveria passar
            except (ExercicioStatusInvalidoError, PermissaoExercicioError):
                check(rotulo, True)    # bloqueou corretamente

        bloqueia(lambda: services.reordenar_itens(presc, fisio, [item1.pk, item2.pk]),
                 "Reordenar em ENCERRADA bloqueado")
        bloqueia(lambda: services.cancelar_prescricao(presc, fisio, motivo="x"),
                 "Cancelar em ENCERRADA bloqueado")
        bloqueia(lambda: services.registrar_execucao_clinica(
                     fisio, item1, paciente, {"realizado": True}),
                 "Execução em ENCERRADA bloqueada")

        # 5. Inativação de exercício
        services.inativar_exercicio(ex1, fisio)
        ex1.refresh_from_db()
        check("Exercício inativado", ex1.ativo is False)

    except Exception as erro:
        print(f"❌ Erro durante a Parte B: {erro}")
    finally:
        print("\n--- Limpeza ---")
        try:
            limpar_smoke()
            print("Dados SMOKE removidos.")
        except Exception as erro:
            print(f"⚠️ Erro durante a limpeza: {erro}")

# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------
falhas = [n for n, ok in resultados if not ok]
print(f"\n{'='*50}")
print(f"RESULTADO: {len(resultados) - len(falhas)}/{len(resultados)} checks OK")
if falhas:
    print("FALHAS:")
    for n in falhas:
        print("  ❌", n)
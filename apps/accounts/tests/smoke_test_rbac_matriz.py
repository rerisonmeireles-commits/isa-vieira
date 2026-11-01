# smoke_test_rbac_matriz.py — Fase 3, item 2
# Matriz RBAC completa: URL × perfil → status esperado
# Execução: python smoke_test_rbac_matriz.py
import os
import django
import gc, time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import logging
logging.getLogger("django.request").setLevel(logging.CRITICAL)

from django.test import Client
from django.contrib.auth.models import Group

from apps.accounts.constants import (
    GRUPO_ADMINISTRADOR, GRUPO_RECEPCAO, GRUPO_FISIOTERAPEUTA,
    GRUPO_FINANCEIRO, GRUPO_PACIENTE,   # ⚠️ confirme o nome no constants.py
)
from apps.accounts.models import Usuario
from apps.patients.models import Paciente

resultados = []

def check(nome, condicao, dica=None):
    resultados.append((nome, bool(condicao)))
    print(("✅" if condicao else "❌"), nome)
    if not condicao and dica:
        print("   💡", dica)

# ---------------------------------------------------------------------------
# Setup: 1 usuário por perfil (reutilizados entre execuções)
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

perfis = {
    "admin":      criar_usuario("smoke_admin",    GRUPO_ADMINISTRADOR),
    "recepcao":   criar_usuario("smoke_recepcao", GRUPO_RECEPCAO),
    "fisio":      criar_usuario("smoke_fisio",    GRUPO_FISIOTERAPEUTA),
    "financeiro": criar_usuario("smoke_financ",   GRUPO_FINANCEIRO),
    "paciente":   criar_usuario("smoke_paciente", GRUPO_PACIENTE),
}

# ---------------------------------------------------------------------------
# MATRIZ RBAC — url → {perfil: status esperado}
# ⚠️ Os status esperados são a proposta segundo a spec — valide contra os
#    seus GRUPOS_* e decorators. Qualquer divergência é ACHADO, não bug do script.
# ---------------------------------------------------------------------------
paciente_qualquer = Paciente.objects.first()

# Home real do sistema é a agenda — a entrada "/" foi removida (não há rota na raiz).
URL_PRONTUARIO = f"/clinical/prontuario/{paciente_qualquer.pk}/"

MATRIZ = [
    # --- Pacientes — VER inclui Financeiro (consulta p/ cobrança, sem editar) ---
    ("/pacientes/", {
        "admin": 200, "recepcao": 200, "fisio": 200,
        "financeiro": 200, "paciente": 403,
    }),

    # --- Agenda (home do sistema) ---
    ("/agenda/", {
        "admin": 200, "recepcao": 200, "fisio": 200,
        "financeiro": 403, "paciente": 403,
    }),

    # --- Prontuário — dado clínico sensível (só clínicos) ---
    *([(
        URL_PRONTUARIO,
        {"admin": 200, "recepcao": 403, "fisio": 200,
         "financeiro": 403, "paciente": 403},
    )] if paciente_qualquer else []),

    # --- Financeiro — VER inclui Recepção (consulta no balcão, sem baixa) ---
    ("/financeiro/", {
        "admin": 200, "recepcao": 200, "fisio": 403,
        "financeiro": 200, "paciente": 403,
    }),

    # --- Exercícios (regressão do item 1) ---
    ("/exercicios/exercicios/", {
        "admin": 200, "recepcao": 403, "fisio": 200,
        "financeiro": 403, "paciente": 403,
    }),
]

# ---------------------------------------------------------------------------
# Execução da matriz
# ---------------------------------------------------------------------------
print("\n--- MATRIZ RBAC (status codes) ---")

for url, esperados in MATRIZ:
    for perfil_nome, status_esperado in esperados.items():
        client = Client()
        client.force_login(perfis[perfil_nome])
        resposta = client.get(url)
        dica = None
        if resposta.status_code == 404:
            dica = f"404 — a URL '{url}' não existe; confira no urls.py do app."
        elif resposta.status_code == 302:
            dica = "302 — redirecionamento; confira se falta @login_required/decorator."
        check(
            f"{perfil_nome} em {url} → {status_esperado}",
            resposta.status_code == status_esperado,
            dica,
        )

# ---------------------------------------------------------------------------
# Bônus: anônimo deve ser redirecionado ao login em URL protegida
# ---------------------------------------------------------------------------
client = Client()  # sem login
resposta = client.get("/exercicios/exercicios/")
check("Anônimo em URL protegida → 302 (login)", resposta.status_code == 302)

# ===========================================================================
# DOCUMENTOS — GED (design de dois níveis — confirmado no constants.py)
#   VER (GRUPOS_DOCUMENTOS = admin, recepcao, fisio): lista, novo, baixar
#   GESTAO (GRUPOS_DOCUMENTOS_GESTAO = admin, fisio): editar, excluir
#   Bloco AUTÔNOMO: cria os próprios usuários — não depende do setup da matriz.
# ===========================================================================
print("\n--- DOCUMENTOS (GED) ---")

import os
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from apps.accounts.models import Usuario
from apps.accounts.constants import (
    GRUPO_ADMINISTRADOR, GRUPO_RECEPCAO, GRUPO_FISIOTERAPEUTA,
    GRUPO_FINANCEIRO, GRUPO_PACIENTE,
)
from apps.documents.models import Documento
from apps.patients.models import Paciente

# --- Usuários próprios do bloco (get_or_create = idempotente) ---
def _ged_usuario(username, grupo_nome):
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

admin      = _ged_usuario("smoke_admin",    GRUPO_ADMINISTRADOR)
fisio      = _ged_usuario("smoke_fisio",    GRUPO_FISIOTERAPEUTA)
recepcao   = _ged_usuario("smoke_recepcao", GRUPO_RECEPCAO)
financeiro = _ged_usuario("smoke_financ",   GRUPO_FINANCEIRO)
paciente   = _ged_usuario("smoke_paciente", GRUPO_PACIENTE)

# --- Documento SMOKE (idempotente — limpa o resíduo da execução que quebrou) ---
paciente_docs = Paciente.objects.filter(status=Paciente.Status.ATIVO).first()

def _criar_doc_smoke():
    d = Documento(paciente=paciente_docs, tipo="OUTROS", titulo="SMOKE — doc matriz")
    d.arquivo.save("smoke_matriz.pdf", ContentFile(b"%PDF-1.4 SMOKE"), save=True)
    return d


def _remover_doc_smoke(d):
    if not d:
        return
    if d.arquivo:
        caminho = d.arquivo.path
        if os.path.exists(caminho):
            for _ in range(3):
                try:
                    os.remove(caminho)
                    break
                except PermissionError:
                    gc.collect()        # força a coleta de FileResponses não fechados
                    time.sleep(0.3)
    Documento._base_manager.filter(pk=d.pk)._raw_delete(using="default")

# def _remover_doc_smoke(d):
#     if not d:
#         return
#     if d.arquivo and os.path.exists(d.arquivo.path):
#         os.remove(d.arquivo.path)
#     Documento._base_manager.filter(pk=d.pk)._raw_delete(using="default")

# residuo = Documento._base_manager.filter(titulo="SMOKE — doc matriz").first()
# if residuo:
#     _remover_doc_smoke(residuo)

doc = _criar_doc_smoke()

# --- Expectativas (constants.py: GESTAO inclui fisio) ---
ESPERA = {
    "lista":   {"smoke_admin": 200, "smoke_fisio": 200, "smoke_recepcao": 200, "smoke_financ": 403, "smoke_paciente": 403},
    "novo":    {"smoke_admin": 200, "smoke_fisio": 200, "smoke_recepcao": 200, "smoke_financ": 403, "smoke_paciente": 403},
    "editar":  {"smoke_admin": 200, "smoke_fisio": 200, "smoke_recepcao": 403, "smoke_financ": 403, "smoke_paciente": 403},
    "baixar":  {"smoke_admin": 200, "smoke_fisio": 200, "smoke_recepcao": 200, "smoke_financ": 403, "smoke_paciente": 403},
}

PERFIS = [
    (admin, "smoke_admin"),
    (fisio, "smoke_fisio"),
    (recepcao, "smoke_recepcao"),
    (financeiro, "smoke_financ"),
    (paciente, "smoke_paciente"),
]

# --- GET nas 4 rotas de leitura/formulário ---
for chave, url in [
    ("lista",  "/documentos/"),
    ("novo",   "/documentos/novo/"),
    ("editar", f"/documentos/{doc.pk}/editar/"),
    ("baixar", f"/documentos/{doc.uuid}/baixar/"),
]:
    for usuario, username in PERFIS:
        client = Client(); client.force_login(usuario)
        resposta = client.get(url)
        esperado = ESPERA[chave][username]
        if getattr(resposta, "streaming", False):
            resposta.close()         
        check(f"{username} em documentos/{chave} → {esperado}", resposta.status_code == esperado)

# --- excluir: POST (mutante) — 403s primeiro; fisio soft-deleta; recria; admin ---
ORDEM_EXCLUIR = [
    (recepcao, "smoke_recepcao", 403),
    (financeiro, "smoke_financ", 403),
    (paciente, "smoke_paciente", 403),
    (fisio, "smoke_fisio", (200, 302)),
    (admin, "smoke_admin", (200, 302)),
]
for usuario, username, esperado in ORDEM_EXCLUIR:
    if username == "smoke_admin":
        _remover_doc_smoke(doc)     # o POST do fisio soft-deletou o doc
        doc = _criar_doc_smoke()    # doc vivo para o teste do admin
    client = Client(); client.force_login(usuario)
    resposta = client.post(f"/documentos/{doc.pk}/excluir/")
    codigos = esperado if isinstance(esperado, tuple) else (esperado,)
    check(f"{username} em documentos/excluir → {esperado}", resposta.status_code in codigos)

# --- Anônimo ---
client = Client()
resposta = client.get("/documentos/")
check("Anônimo em /documentos/ → 302 (login)", resposta.status_code == 302)

# --- Limpeza ---
print("\n--- Limpeza documentos ---")
try:
    _remover_doc_smoke(doc)
    residuo = Documento._base_manager.filter(titulo="SMOKE — doc matriz").first()
    if residuo:
        _remover_doc_smoke(residuo)
    print("Documento SMOKE removido.")
except Exception as erro:
    print(f"⚠️ Erro na limpeza: {erro}")

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
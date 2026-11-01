# =============================================================================
# SMOKE FUNCIONAL — DOCUMENTOS (GED)
# Prova de ponta a ponta: upload → hash SHA-256 gravado → download
# → re-hash idêntico (integridade) → exclusão lógica → some da lista.
# Padrão dos smokes existentes: check(), usuários get_or_create,
# limpeza _raw_delete + retry contra WinError 32.
# =============================================================================
import os
import gc
import time
import hashlib
import uuid

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")  # ← confira no manage.py
django.setup()

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.accounts.models import Usuario
from apps.accounts.constants import GRUPO_ADMINISTRADOR
from apps.documents.models import Documento
from apps.patients.models import Paciente

# --- check() no padrão dos smokes ---
TOTAL = 0
FALHAS = []

def check(descricao, ok):
    global TOTAL
    TOTAL += 1
    print(("✅ " if ok else "❌ ") + descricao)
    if not ok:
        FALHAS.append(descricao)

# --- Limpeza física (linha + arquivo), com retry do WinError 32 ---
def _remover_doc(d):
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
                    gc.collect()
                    time.sleep(0.3)
    Documento._base_manager.filter(pk=d.pk)._raw_delete(using="default")

print("--- SMOKE FUNCIONAL DOCUMENTOS (GED) ---")

# --- Setup: usuário admin (idempotente) ---
grupo_admin, _ = Group.objects.get_or_create(name=GRUPO_ADMINISTRADOR)
admin, criado = Usuario.objects.get_or_create(
    username="smoke_admin",
    defaults={"email": "smoke_admin@smoke.local", "is_active": True},
)
if criado:
    admin.set_password("smoke-1234")
    admin.save()
admin.groups.add(grupo_admin)

# --- Setup: paciente ativo + conteúdo de teste (bytes aleatórios = hash único) ---
paciente = Paciente.objects.filter(status=Paciente.Status.ATIVO).first()
check("Existe paciente ativo para o teste", paciente is not None)

titulo = f"SMOKE integridade {uuid.uuid4().hex[:8]}"
conteudo = b"%PDF-1.4 SMOKE INTEGRIDADE " + os.urandom(64)
hash_esperado = hashlib.sha256(conteudo).hexdigest()

# --- Idempotência: remove resíduos de execuções anteriores ---
for residuo in list(Documento._base_manager.filter(titulo__startswith="SMOKE integridade")):
    _remover_doc(residuo)

# =============================================================================
# 1. UPLOAD — pela rota real (mesmo caminho do modal), passando pelo service
# =============================================================================
print("\n--- 1. Upload ---")
client = Client()
client.force_login(admin)
resposta = client.post("/documentos/novo/", {
    "paciente": paciente.pk,
    "tipo": "OUTROS",
    "titulo": titulo,
    "arquivo": SimpleUploadedFile("smoke_integridade.pdf", conteudo,
                                  content_type="application/pdf"),
    "visivel_paciente": "on",
})
check("POST /documentos/novo/ → sucesso (header X-Doc-OK)",
      resposta.headers.get("X-Doc-OK") == "1")

doc = Documento._base_manager.filter(titulo=titulo).first()
check("Documento criado no banco", doc is not None)

if doc:
    check("hash_sha256 gravado = SHA-256 do conteúdo", doc.hash_sha256 == hash_esperado)
    check("tamanho_bytes gravado = tamanho do upload", doc.tamanho_bytes == len(conteudo))
    check("mime_type gravado = application/pdf", doc.mime_type == "application/pdf")
    check("uuid público gerado", doc.uuid is not None)
    check("Arquivo persistido no storage", bool(doc.arquivo) and os.path.exists(doc.arquivo.path))
else:
    print("⚠️ Upload falhou — testes seguintes pulados (form pode exigir campos extras).")

# =============================================================================
# 2. DOWNLOAD — integridade byte a byte
# =============================================================================
if doc:
    print("\n--- 2. Download (integridade) ---")
    client = Client()
    client.force_login(admin)
    resposta = client.get(f"/documentos/{doc.uuid}/baixar/")
    check("GET /documentos/<uuid>/baixar/ → 200", resposta.status_code == 200)

    if getattr(resposta, "streaming", False):
        conteudo_baixado = b"".join(resposta.streaming_content)
        resposta.close()   # solta o handle (lição do WinError 32)
    else:
        conteudo_baixado = resposta.content

    hash_baixado = hashlib.sha256(conteudo_baixado).hexdigest()
    check("Re-hash do arquivo baixado = hash gravado", hash_baixado == hash_esperado)

    # =========================================================================
    # 3. EXCLUSÃO LÓGICA
    # =========================================================================
    print("\n--- 3. Exclusão lógica ---")
    resposta = client.post(f"/documentos/{doc.pk}/excluir/")
    check("POST /documentos/<pk>/excluir/ → 200/302", resposta.status_code in (200, 302))

    doc_apos = Documento._base_manager.filter(pk=doc.pk).first()
    check("Linha ainda existe no banco (soft delete)", doc_apos is not None)
    check("deleted_at preenchido", doc_apos is not None and doc_apos.deleted_at is not None)
    check("Some do manager padrão (objects)",
          not Documento.objects.filter(pk=doc.pk).exists())

    # =========================================================================
    # 4. SOME DA LISTA
    # =========================================================================
    print("\n--- 4. Lista após exclusão ---")
    client.get("/documentos/")   # 1º GET consome a flash message pendente
                                # (o sucesso do excluir ecoa o título no texto)
    resposta = client.get("/documentos/")
    check("GET /documentos/ → 200", resposta.status_code == 200)
    check("Título do excluído NÃO aparece na lista",
        titulo not in resposta.content.decode("utf-8"))

# --- Limpeza ---
print("\n--- Limpeza ---")
try:
    _remover_doc(doc)
    print("Documento SMOKE removido (linha + arquivo).")
except Exception as erro:
    print(f"⚠️ Erro na limpeza: {erro}")

print("\n" + "=" * 50)
print(f"RESULTADO: {TOTAL - len(FALHAS)}/{TOTAL} checks OK")
if FALHAS:
    print("Falhas:")
    for f in FALHAS:
        print(f" - {f}")
"""
SMOKE FUNCIONAL — Comunicação (mensagem + notificacao)
Execução: python smoke_test_communication.py

PARTE A — acesso e anti-IDOR por HTTP. RBAC deste módulo é por DONO:
todos os perfis autenticados acessam; ninguém toca em dados de terceiros.
PARTE B — ciclo funcional via services + conclusão em cadeia + CHECK no banco.
Limpeza dos dados SMOKE ao final (idempotente; usuários smoke_com_* ficam para reuso).
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse

from apps.communication.exceptions import CommunicationError
from apps.communication.models import Mensagem, Notificacao
from apps.communication.services import (
    enviar_mensagem,
    marcar_mensagem_lida,
    marcar_notificacao_lida,
)

U = get_user_model()
SENHA = "smoke@123"
resultados = []


def check(nome, ok):
    resultados.append(ok)
    print(f"{'✅' if ok else '❌'} {nome}")


def usuario_smoke(username):
    user, _ = U.objects.get_or_create(
        username=username,
        defaults={"email": f"{username}@smoke.local", "first_name": "Smoke"},
    )
    user.is_active = True
    user.set_password(SENHA)
    user.save()
    return user


def client_para(user):
    c = Client(SERVER_NAME="localhost")
    c.login(username=user.username, password=SENHA)
    return c


print("\n--- SMOKE FUNCIONAL COMUNICAÇÃO ---\n")

a = usuario_smoke("smoke_com_a")   # remetente
b = usuario_smoke("smoke_com_b")   # destinatário
c = usuario_smoke("smoke_com_c")   # terceiro (provas de anti-IDOR)

# ---------- PARTE A ----------
print("--- PARTE A: acesso e anti-IDOR (HTTP) ---")

anon = Client(SERVER_NAME="localhost")
r = anon.get("/comunicacao/")
check("Anônimo em /comunicacao/ → 302 (login obrigatório)", r.status_code == 302)
r = anon.get("/comunicacao/mensagens/")
check("Anônimo em /comunicacao/mensagens/ → 302", r.status_code == 302)

for user, rotulo in ((a, "smoke_com_a"), (b, "smoke_com_b"), (c, "smoke_com_c")):
    r = client_para(user).get("/comunicacao/")
    check(f"{rotulo} em /comunicacao/ → 200", r.status_code == 200)

r = client_para(b).get("/comunicacao/mensagens/")
check("smoke_com_b em /comunicacao/mensagens/ → 200", r.status_code == 200)

m_ab = enviar_mensagem(remetente=a, destinatario=b, assunto="SMOKE A→B", corpo="corpo A→B")
r = client_para(c).get(f"/comunicacao/mensagens/{m_ab.pk}/")
check("Anti-IDOR: terceiro abre mensagem alheia → 403", r.status_code == 403)

notif_ab = Notificacao.objects.get(
    destinatario=b, link_url=reverse("communication:mensagem_detalhe", args=[m_ab.pk])
)
client_para(c).post(f"/comunicacao/notificacao/{notif_ab.pk}/ler/")
notif_ab.refresh_from_db()
check("Anti-IDOR: POST de terceiro não marca notificação alheia", notif_ab.lida is False)

# ---------- PARTE B ----------
print("\n--- PARTE B: ciclo funcional (services) ---")

m2 = enviar_mensagem(remetente=a, destinatario=b, assunto="SMOKE interno", corpo="corpo interno")
n2 = Notificacao.objects.get(
    destinatario=b, link_url=reverse("communication:mensagem_detalhe", args=[m2.pk])
)
check("enviar_mensagem INTERNO → notificação IN_APP vinculada ao detalhe",
      n2.lida is False and n2.canal == Notificacao.Canal.IN_APP)

m_email = enviar_mensagem(remetente=a, destinatario=b, assunto="SMOKE email",
                          corpo="corpo email", canal=Mensagem.Canal.EMAIL)
check("enviar_mensagem EMAIL → status ENTREGUE (console backend)",
      m_email.status == Mensagem.Status.ENTREGUE)

marcar_mensagem_lida(mensagem_id=m_ab.pk, usuario=b)
m_ab.refresh_from_db()
check("Destinatário lê → status LIDA + data_leitura",
      m_ab.status == Mensagem.Status.LIDA and m_ab.data_leitura is not None)

try:
    marcar_mensagem_lida(mensagem_id=m_ab.pk, usuario=a)
    check("Anti-IDOR no service: remetente não marca mensagem", False)
except CommunicationError:
    check("Anti-IDOR no service: remetente não marca mensagem", True)

marcar_notificacao_lida(notificacao_id=n2.pk, usuario=b)
n2.refresh_from_db()
check("marcar_notificacao_lida → lida=True + data_lida", n2.lida and n2.data_lida is not None)

try:
    marcar_notificacao_lida(notificacao_id=n2.pk, usuario=c)
    check("Anti-IDOR na notificação: terceiro bloqueado", False)
except CommunicationError:
    check("Anti-IDOR na notificação: terceiro bloqueado", True)

m3 = enviar_mensagem(remetente=a, destinatario=b, assunto="SMOKE cadeia", corpo="corpo cadeia")
n3 = Notificacao.objects.get(
    destinatario=b, link_url=reverse("communication:mensagem_detalhe", args=[m3.pk])
)
check("Cadeia: notificação nasce não lida (badge ativo)", n3.lida is False)

r = client_para(b).get(f"/comunicacao/mensagens/{m3.pk}/")
n3.refresh_from_db()
check("Cadeia: abrir mensagem conclui a notificação (badge zera)",
      r.status_code == 200 and n3.lida and n3.data_lida is not None)

r = client_para(b).post(
    f"/comunicacao/mensagens/{m3.pk}/responder/",
    {"destinatario": a.pk, "assunto": "Re: SMOKE cadeia", "corpo": "resposta SMOKE"},
)
resposta = Mensagem.objects.filter(remetente=b, assunto="Re: SMOKE cadeia").order_by("-data_envio").first()
check("Responder via tela → 302 e mensagem 'Re:' criada", r.status_code == 302 and resposta is not None)

try:
    with transaction.atomic():
        Mensagem.objects.create(canal="FAX", corpo="teste-check")
    check("CHECK no banco: canal inválido rejeitado", False)
except IntegrityError:
    check("CHECK no banco: canal inválido rejeitado (IntegrityError)", True)

# ---------- Limpeza ----------
print("\n--- Limpeza ---")
Mensagem.objects.filter(remetente__in=[a, b, c]).delete()
Mensagem.objects.filter(destinatario__in=[a, b, c]).delete()
Notificacao.objects.filter(destinatario__in=[a, b, c]).delete()
print("Dados SMOKE removidos (mensagens e notificações). Usuários smoke_com_* mantidos para reuso.")

print("\n" + "=" * 50)
print(f"RESULTADO: {sum(resultados)}/{len(resultados)} checks OK")
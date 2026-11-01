"""Diagnostico da grade — execute com:
   python manage.py shell -c "exec(open('_diag_grade.py', encoding='utf-8').read())"
"""
import re
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.template import RequestContext, engines
from django.template.loader import get_template
from django.test import RequestFactory, override_settings
from django.urls import NoReverseMatch, reverse

from apps.professionals.models import Profissional
from apps.scheduling import views as sched_views

SEP = "=" * 64

U = get_user_model()
u = U.objects.filter(is_superuser=True).first()
prof = Profissional.objects.filter(status="ATIVO").first()

print(SEP)
print("0) USUARIO / PROFISSIONAL")
print("  usuario:", u, "| is_superuser:", u.is_superuser)
print("  profissional:", prof)

# ---------- 1. caminho real do template ----------
print(SEP)
print("1) TEMPLATE EM DISCO")
tpl = get_template("scheduling/_grade.html")
origin = getattr(getattr(tpl, "origin", None), "name", None)
print("  caminho real:", origin)
src = getattr(getattr(tpl, "template", None), "source", "") or ""
print("  usa 'perm.'      :", "perm." in src)
print("  usa 'pode_atender':", "pode_atender" in src)
for m in sorted(set(re.findall(r"perm\.\w+", src))):
    print("    ->", m)

# ---------- 2. context processors ----------
print(SEP)
print("2) CONTEXT PROCESSORS (com middleware aplicado)")
rf = RequestFactory()
req = rf.get("/agenda/")
req.user = u
SessionMiddleware(lambda r: None).process_request(req)
MessageMiddleware(lambda r: None).process_request(req)

for cp in engines["django"].engine.template_context_processors:
    nome = getattr(cp, "__name__", repr(cp))
    try:
        out = cp(req)
    except Exception as exc:
        print(f"  {nome}: ERRO {type(exc).__name__}: {exc}")
        continue
    if isinstance(out, dict):
        print(f"  {nome}: {sorted(out.keys())}")
    else:
        print(f"  {nome}: {type(out).__name__}")

# ---------- 3. TESTE DECISIVO (sem dados de agenda) ----------
print(SEP)
print("3) AS VARIAVEIS EXISTEM? (render inline, processors aplicados)")
for expr in ("perm.atender", "pode_atender", "perms.scheduling.add_agendamento"):
    t = engines["django"].engine.from_string(
        "{%% if %s %%}TRUE{%% else %%}FALSE{%% endif %%}" % expr
    )
    try:
        valor = t.render(RequestContext(req))
    except Exception as exc:
        valor = f"ERRO {type(exc).__name__}: {exc}"
    print(f"  {expr:42s} -> {valor}")

# ---------- 4. render fiel pela URL ----------
print(SEP)
print("4) RENDER VIA URL (middleware + processors reais)")
try:
    url = reverse("scheduling:grade")
except NoReverseMatch:
    url = "/agenda/"
print("  url:", url)

prof_ref = prof
with override_settings(ALLOWED_HOSTS=["*"]):
    from django.test import Client

    c = Client()
    c.force_login(u)
    resp = c.get(url, {"profissional": prof_ref.pk, "data_inicio": "2026-12-28"})
html = resp.content.decode()
print("  status:", resp.status_code, "| bytes:", len(html))
print("  'Iniciar Atendimento' :", "Iniciar Atendimento" in html)
print("  'Ficha do atendimento':", "Ficha do atendimento" in html)
print("  'Sem expediente'      :", "Sem expediente" in html)
print("  'Nao gerada'          :", "Não gerada" in html)

linhas = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
print("  linhas <tr>:", len(linhas))
for i, ln in enumerate(linhas[:3]):
    tds = len(re.findall(r"<td", ln))
    rs = re.findall(r'rowspan="(\d+)"', ln)
    print(f"    linha {i}: {tds} <td> | rowspans {rs}")

# ---------- 5. contagem de queries ----------
print(SEP)
print("5) QUERIES (2a chamada, regime estavel)")
from django.db import connection
from django.test.utils import CaptureQueriesContext

with override_settings(ALLOWED_HOSTS=["*"]):
    c = Client()
    c.force_login(u)
    c.get(url, {"profissional": prof_ref.pk, "data_inicio": "2026-12-28"})
    with CaptureQueriesContext(connection) as ctx:
        c.get(url, {"profissional": prof_ref.pk, "data_inicio": "2026-12-28"})
print("  queries:", len(ctx.captured_queries))
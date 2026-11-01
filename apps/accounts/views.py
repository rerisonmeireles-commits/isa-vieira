"""Views do portal clínico: painel inicial (home) e placeholder de módulos."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone

from apps.accounts.constants import GRUPOS_PORTAL
from apps.accounts.permissions import grupos_requeridos
from apps.accounts.forms import ConsentimentoForm, UsuarioForm
from apps.accounts.models import ConsentimentoLgpd, Usuario

from apps.patients.models import Paciente
from apps.scheduling.models import Agendamento

from django.views.decorators.http import require_GET, require_POST

from apps.accounts.constants import (
    GRUPOS_CONSENTIMENTO,
    GRUPOS_CONSENTIMENTO_GESTAO,
    GRUPOS_USUARIOS_GESTAO,
)
from apps.accounts.services import (
    alternar_status,
    atualizar_usuario,
    criar_usuario,
    registrar_consentimento,
    revogar_consentimento,
)

# Status que contam como agendamento "ativo" nos KPIs.
STATUS_ATIVOS = ("AGENDADO", "CONFIRMADO", "EM_ATENDIMENTO", "ATENDIDO")

@grupos_requeridos(*GRUPOS_PORTAL)
def home(request):
    """Painel inicial pós-login: KPIs reais do banco + agenda de hoje.

    O menu lateral é renderizado pelo context processor `portal`, já
    filtrado pelo perfil do usuário (RBAC no template).
    """
    hoje = timezone.localdate()
    agendamentos_hoje = Agendamento.objects.filter(
        slot__agenda__data=hoje,
        status__in=STATUS_ATIVOS,
    )

    contexto = {
        "kpi_agendamentos": agendamentos_hoje.count(),
        "kpi_confirmados": agendamentos_hoje.filter(status="CONFIRMADO").count(),
        "kpi_pacientes": Paciente.objects.filter(status=Paciente.Status.ATIVO).count(),
        "kpi_pendencias": agendamentos_hoje.filter(status="AGENDADO").count(),
        "agendamentos_lista": agendamentos_hoje.select_related(
            "paciente", "profissional", "tipo_atendimento", "slot__agenda",
        ).order_by("slot__hora_inicio")[:8],
    }
    return render(request, "accounts/home.html", contexto)


@login_required
def em_breve(request, slug):
    """Placeholder para módulos reservados no menu mas ainda não implementados."""
    return render(request, "accounts/em_breve.html", {"modulo": slug})


def _tabela(request, template, contexto):
    if request.headers.get("HX-Request"):
        return render(request, template, contexto)
    return render(request, contexto["pagina"], contexto)


# ---------------------------------------------------------------------------
# Usuários
# ---------------------------------------------------------------------------
@require_GET
@grupos_requeridos(*GRUPOS_USUARIOS_GESTAO)
def usuario_lista(request):
    contexto = {
        "pagina": "accounts/usuario_lista.html",
        "usuarios": Usuario.objects.order_by("first_name", "username"),
    }
    return _tabela(request, "accounts/_usuario_tabela.html", contexto)


@grupos_requeridos(*GRUPOS_USUARIOS_GESTAO)
def usuario_criar(request):
    if request.method == "GET":
        return render(request, "accounts/_usuario_form.html", {"form": UsuarioForm()})
    form = UsuarioForm(request.POST)
    if not form.is_valid():
        return render(request, "accounts/_usuario_form.html", {"form": form, "oob": True})
    dados = form.cleaned_data
    usuario = criar_usuario(dados, senha=dados["senha"])
    messages.success(request, f"Usuário '{usuario}' criado com sucesso.")
    resposta = _tabela(request, "accounts/_usuario_tabela.html", {
        "usuarios": Usuario.objects.order_by("first_name", "username"),
    })
    resposta["X-User-OK"] = "1"
    return resposta


@grupos_requeridos(*GRUPOS_USUARIOS_GESTAO)
def usuario_editar(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method == "GET":
        form = UsuarioForm(instance=usuario, initial={"grupos": usuario.groups.all()})
        return render(request, "accounts/_usuario_form.html", {"form": form, "usuario": usuario})
    form = UsuarioForm(request.POST, instance=usuario)
    if not form.is_valid():
        return render(request, "accounts/_usuario_form.html", {"form": form, "usuario": usuario, "oob": True})
    dados = form.cleaned_data
    atualizar_usuario(usuario, dados, senha=dados.get("senha"))
    messages.success(request, f"Usuário '{usuario}' atualizado.")
    resposta = _tabela(request, "accounts/_usuario_tabela.html", {
        "usuarios": Usuario.objects.order_by("first_name", "username"),
    })
    resposta["X-User-OK"] = "1"
    return resposta


@require_POST
@grupos_requeridos(*GRUPOS_USUARIOS_GESTAO)
def usuario_alternar_status(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    try:
        alternar_status(usuario.pk)
    except ValueError as erro:
        messages.error(request, str(erro))
    else:
        acao = "ativado" if usuario.is_active else "desativado"
        messages.success(request, f"Usuário '{usuario}' {acao}.")
    return _tabela(request, "accounts/_usuario_tabela.html", {
        "usuarios": Usuario.objects.order_by("first_name", "username"),
    })


# ---------------------------------------------------------------------------
# Consentimento LGPD
# ---------------------------------------------------------------------------

@require_GET
@grupos_requeridos(*GRUPOS_CONSENTIMENTO)
def consentimento_lista(request):
    consentimentos = ConsentimentoLgpd.objects.select_related("paciente").order_by("-created_at")
    paciente_id = request.GET.get("paciente") or ""
    if paciente_id:
        consentimentos = consentimentos.filter(paciente_id=paciente_id)
    contexto = {
        "pagina": "accounts/consentimento_lista.html",
        "consentimentos": consentimentos,
        "pacientes": Paciente.objects.filter(status=Paciente.Status.ATIVO).order_by("nome_completo"),
        "pode_revogar": request.user.is_superuser or request.user.groups.filter(
            name__in=GRUPOS_CONSENTIMENTO_GESTAO
        ).exists(),
    }
    return _tabela(request, "accounts/_consentimento_tabela.html", contexto)


@grupos_requeridos(*GRUPOS_CONSENTIMENTO)
def consentimento_criar(request):
    if request.method == "GET":
        return render(request, "accounts/_consentimento_form.html", {"form": ConsentimentoForm()})
    form = ConsentimentoForm(request.POST)
    if not form.is_valid():
        return render(request, "accounts/_consentimento_form.html", {"form": form, "oob": True})
    dados = form.cleaned_data
    consentimento = registrar_consentimento(
        paciente=dados["paciente"],
        versao_termo=dados["versao_termo"],
        canal=dados["canal"],
        aceito=dados["aceito"],
        ip_origem=dados.get("ip_origem"),
    )
    estado = "registrado" if consentimento.aceito else "registrado como recusa"
    messages.success(request, f"Consentimento {estado} para {consentimento.paciente}.")
    resposta = consentimento_lista(request)
    resposta["X-Consent-OK"] = "1"
    return resposta


@require_POST
@grupos_requeridos(*GRUPOS_CONSENTIMENTO_GESTAO)
def consentimento_revogar(request, pk):
    original = get_object_or_404(ConsentimentoLgpd, pk=pk)
    revogado = revogar_consentimento(original.pk)
    messages.success(request, f"Consentimento de {revogado.paciente} revogado.")
    return consentimento_lista(request)


from django.contrib.auth import logout          # acrescentar ao import existente
from apps.portal.helpers import paciente_do_usuario


@login_required
def pos_login(request):
    """Encaminha o usuário para o portal correspondente ao perfil.

    LOGIN_REDIRECT_URL é uma única URL para todos os logins, e o sistema tem
    dois portais segregados (§1.1). Este dispatcher só roda quando o login
    acontece SEM parâmetro `next`: grupos_requeridos() usa
    redirect_to_login(get_full_path()), então quem foi desviado de uma view
    protegida volta direto para ela e a autorização fica com o guard da view.

    O critério do portal clínico é IDÊNTICO ao de grupos_requeridos(*GRUPOS_PORTAL):
    superusuário ou pertencimento a um dos grupos operacionais. Deliberadamente
    não usa is_staff - neste projeto o RBAC é por grupo, e is_staff só controla
    o Django Admin. Divergir aqui faria o redirect prometer acesso que o guard nega.

    O vínculo com Paciente é resolvido por paciente_do_usuario(), que já trata
    soft delete, usuário anônimo e ausência de acessor reverso.
    """
    user = request.user

    if user.is_superuser or user.groups.filter(name__in=GRUPOS_PORTAL).exists():
        return redirect("conta:home")

    if paciente_do_usuario(user) is not None:
        return redirect("portal:home")

    # Sem grupo operacional e sem vínculo de paciente: provisionamento
    # incompleto. A raiz "" herda apps.scheduling.urls e exige GRUPOS_AGENDA,
    # então redirecionar para "/" deixaria a sessão presa num 403 perpétuo.
    logout(request)
    messages.error(
        request,
        "Sua conta não tem perfil configurado. Procure a recepção da clínica.",
    )
    return redirect("conta:login")
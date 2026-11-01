"""Views do módulo de Pacientes: listagem, cadastro, edição e ficha.

Padrão do projeto: view fina, service gorda.

RBAC:
  - Ver / consultar: Administrador, Recepção, Fisioterapeuta, Financeiro
  - Cadastrar / editar / inativar: Administrador, Recepção, Fisioterapeuta
"""

import re

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q, Value
from django.db.models.functions import Replace
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.constants import GRUPOS_PACIENTES_EDITAR, GRUPOS_PACIENTES_VER
from apps.accounts.permissions import grupos_requeridos
from apps.accounts.services import registrar_consentimento
from apps.patients.forms import (
    ContatoEmergenciaFormSet,
    ContatoFormSet,
    EnderecoFormSet,
    PacienteConvenioForm,
    PacienteForm,
)

from apps.patients.models import Paciente
from apps.patients.services import alternar_status, salvar_paciente
from apps.insurance.models import PacienteConvenio

ITENS_POR_PAGINA = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pode_editar(usuario):
    return usuario.is_superuser or usuario.groups.filter(
        name__in=GRUPOS_PACIENTES_EDITAR
    ).exists()


def _cpf_sem_mascara():
    """Expressão ORM que remove pontos e traço do CPF (busca por dígitos)."""
    return Replace(Replace(F("cpf"), Value("."), Value("")), Value("-"), Value(""))


def _querystring_sem_page(request):
    """Preserva busca e filtro nos links de paginação."""
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return parametros.urlencode()


# ---------------------------------------------------------------------------
# Listagem
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_PACIENTES_VER)
def listar(request):
    busca = (request.GET.get("q") or "").strip()
    status_filtro = request.GET.get("status") or ""

    pacientes = Paciente.objects.all()

    if busca:
        condicao = Q(nome_completo__icontains=busca)
        digitos = re.sub(r"\D", "", busca)
        if digitos:
            # O CPF é gravado formatado; a anotação permite buscar por dígitos puros.
            pacientes = pacientes.annotate(cpf_limpo=_cpf_sem_mascara())
            condicao |= Q(cpf_limpo__icontains=digitos)
        pacientes = pacientes.filter(condicao)

    if status_filtro in dict(Paciente.Status.choices):
        pacientes = pacientes.filter(status=status_filtro)

    paginador = Paginator(pacientes, ITENS_POR_PAGINA)

    return render(request, "patients/listar.html", {
        "pagina": paginador.get_page(request.GET.get("page")),
        "busca": busca,
        "status_filtro": status_filtro,
        "status_choices": Paciente.Status.choices,
        "pode_editar": _pode_editar(request.user),
        "total": paginador.count,
        "querystring": _querystring_sem_page(request),
    })


# ---------------------------------------------------------------------------
# Ficha
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_PACIENTES_VER)
def ficha(request, uuid):
    paciente = get_object_or_404(
        Paciente.objects.prefetch_related(
            "enderecos",
            "contatos",
            "contatos_emergencia",
            "convenios__plano__convenio",
        ),
        uuid=uuid,
    )
    agendamentos = (
        paciente.agendamentos
        .select_related("profissional", "tipo_atendimento", "sala", "slot__agenda")
        .order_by("-slot__agenda__data", "-slot__hora_inicio")[:10]
    )
    # NOVO: último registro de consentimento define o alerta da ficha.
    consentimento = paciente.consentimentos.order_by("-created_at").first()
    return render(request, "patients/ficha.html", {
        "paciente": paciente,
        "agendamentos": agendamentos,
        "pode_editar": _pode_editar(request.user),
        "consentimento": consentimento,
    })


# ---------------------------------------------------------------------------
# Cadastro e edição
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_PACIENTES_EDITAR)
def criar(request):
    return _formulario(request, paciente=None)


@grupos_requeridos(*GRUPOS_PACIENTES_EDITAR)
def editar(request, uuid):
    paciente = get_object_or_404(Paciente, uuid=uuid)
    return _formulario(request, paciente=paciente)


def _formulario(request, paciente):
    """Fluxo compartilhado de cadastro/edição (Paciente + 3 formsets inline).

    Na criação, o aceite LGPD marcado no form gera o registro de
    consentimento na MESMA transação - ou os dois registros nascem,
    ou nenhum.
    """
    instancia = paciente if paciente else Paciente()

    if request.method == "POST":
        form = PacienteForm(request.POST, instance=instancia)
        enderecos = EnderecoFormSet(request.POST, instance=instancia, prefix="enderecos")
        contatos = ContatoFormSet(request.POST, instance=instancia, prefix="contatos")
        emergencias = ContatoEmergenciaFormSet(request.POST, instance=instancia, prefix="emergencias")

        # all() sobre a lista garante que TODOS os formulários sejam validados.
        if all([
            form.is_valid(),
            enderecos.is_valid(),
            contatos.is_valid(),
            emergencias.is_valid(),
        ]):
            dados = form.cleaned_data
            with transaction.atomic():
                salvo = salvar_paciente(
                    form=form,
                    enderecos=enderecos,
                    contatos=contatos,
                    emergencias=emergencias,
                )
                # NOVO: consentimento só na CRIAÇÃO - histórico imutável,
                # a edição nunca re-registra (o form nem traz os campos).
                if paciente is None and dados.get("consent_aceito"):
                    registrar_consentimento(
                        paciente=salvo,
                        versao_termo=dados["consent_versao_termo"],
                        canal=dados["consent_canal"],
                        aceito=True,
                        ip_origem=request.META.get("REMOTE_ADDR"),
                    )
            messages.success(request, f"Paciente {salvo.nome_completo} salvo com sucesso.")
            return redirect("patients:ficha", uuid=salvo.uuid)
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = PacienteForm(instance=instancia)
        enderecos = EnderecoFormSet(instance=instancia, prefix="enderecos")
        contatos = ContatoFormSet(instance=instancia, prefix="contatos")
        emergencias = ContatoEmergenciaFormSet(instance=instancia, prefix="emergencias")

    return render(request, "patients/form.html", {
        "form": form,
        "enderecos": enderecos,
        "contatos": contatos,
        "emergencias": emergencias,
        "paciente": paciente,
    })


# ---------------------------------------------------------------------------
# Inativação operacional (status) - reversível
# ---------------------------------------------------------------------------

@require_POST
@grupos_requeridos(*GRUPOS_PACIENTES_EDITAR)
def alternar_status_view(request, uuid):
    paciente = alternar_status(get_object_or_404(Paciente, uuid=uuid))
    messages.success(
        request,
        f"Paciente {paciente.nome_completo} está agora {paciente.get_status_display().lower()}.",
    )
    return redirect("patients:ficha", uuid=paciente.uuid)

# ---------------------------------------------------------------------------
# Vínculo de convênio (PacienteConvenio)
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_PACIENTES_EDITAR)
def vincular_convenio(request, uuid):
    paciente = get_object_or_404(Paciente, uuid=uuid)
    return _convenio_form(request, paciente, vinculo=None)


@grupos_requeridos(*GRUPOS_PACIENTES_EDITAR)
def editar_convenio(request, uuid, vinculo_id):
    paciente = get_object_or_404(Paciente, uuid=uuid)
    vinculo = get_object_or_404(
        PacienteConvenio, pk=vinculo_id, paciente=paciente
    )
    return _convenio_form(request, paciente, vinculo=vinculo)


def _convenio_form(request, paciente, vinculo):
    """Fluxo compartilhado de vincular/editar convênio do paciente."""
    instancia = vinculo if vinculo else PacienteConvenio(paciente=paciente)

    if request.method == "POST":
        form = PacienteConvenioForm(
            request.POST, instance=instancia, paciente=paciente
        )
        if form.is_valid():
            salvo = form.save()
            messages.success(
                request,
                f"Convênio {salvo.plano.convenio.nome} vinculado com sucesso.",
            )
            return redirect("patients:ficha", uuid=paciente.uuid)
        messages.error(request, "Corrija os campos destacados antes de salvar.")
    else:
        form = PacienteConvenioForm(instance=instancia, paciente=paciente)

    return render(request, "patients/convenio_form.html", {
        "form": form,
        "paciente": paciente,
        "vinculo": vinculo,
    })


@require_POST
@grupos_requeridos(*GRUPOS_PACIENTES_EDITAR)
def remover_convenio(request, uuid, vinculo_id):
    paciente = get_object_or_404(Paciente, uuid=uuid)
    vinculo = get_object_or_404(
        PacienteConvenio, pk=vinculo_id, paciente=paciente
    )
    vinculo.delete()
    messages.success(request, "Vínculo de convênio removido.")
    return redirect("patients:ficha", uuid=paciente.uuid)
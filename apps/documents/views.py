"""CRUD de documentos (portal administrativo).

Padrão: view fina, service gorda. RBAC:
  - Ver/baixar/anexar: Administrador, Recepção, Fisioterapeuta
  - Editar/excluir: Administrador, Fisioterapeuta
Download via uuid (identificador público - mitigação de IDOR).
"""
import os

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render

from django.views.decorators.http import require_GET, require_POST

from apps.accounts.constants import GRUPOS_DOCUMENTOS, GRUPOS_DOCUMENTOS_GESTAO
from apps.accounts.permissions import grupos_requeridos

from apps.documents.forms import DocumentoForm
from apps.documents.models import Documento
from apps.documents.services import (
    atualizar_documento,
    excluir_documento,
    registrar_documento,
)
from apps.patients.models import Paciente


def _pode_gerenciar(usuario):
    return usuario.is_superuser or usuario.groups.filter(
        name__in=GRUPOS_DOCUMENTOS_GESTAO
    ).exists()


def _documentos_filtrados(request):
    documentos = Documento.objects.select_related(
        "paciente", "profissional"
    ).order_by("-created_at")
    q = (request.GET.get("q") or "").strip()
    if q:
        documentos = documentos.filter(titulo__icontains=q)
    tipo = request.GET.get("tipo") or ""
    if tipo:
        documentos = documentos.filter(tipo=tipo)
    paciente_id = request.GET.get("paciente") or ""
    if paciente_id:
        documentos = documentos.filter(paciente_id=paciente_id)
    return documentos


def _tabela_fragment(request, documentos):
    return render(request, "documents/_documento_tabela.html", {
        "documentos": documentos,
        "pode_gerenciar": _pode_gerenciar(request.user),
        "paciente_escopo": request.GET.get("paciente") or "",
    })

@require_GET
@grupos_requeridos(*GRUPOS_DOCUMENTOS)
def documento_lista(request):
    contexto = {
        "documentos": _documentos_filtrados(request),
        "pacientes": Paciente.objects.filter(
            status=Paciente.Status.ATIVO
        ).order_by("nome_completo"),
        "pode_gerenciar": _pode_gerenciar(request.user),
    }
    if request.headers.get("HX-Request"):
        return render(request, "documents/_documento_tabela.html", contexto)
    return render(request, "documents/documento_lista.html", contexto)

 
@grupos_requeridos(*GRUPOS_DOCUMENTOS)
def documento_criar(request):
    paciente_id = request.GET.get("paciente")
    initial = {"paciente": paciente_id} if paciente_id else None    
    
    if request.method == "GET":
        return render(request, "documents/_documento_form.html", {
            "form": DocumentoForm(initial=initial),
        })
    form = DocumentoForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "documents/_documento_form.html", {
            "form": form, "oob": True,
        })
    dados = form.cleaned_data
    documento = registrar_documento(
        paciente=dados["paciente"],
        arquivo=dados["arquivo"],
        tipo=dados["tipo"],
        titulo=dados["titulo"],
        descricao=dados.get("descricao") or "",
        profissional=dados.get("profissional"),
        atendimento=dados.get("atendimento"),
        data_emissao=dados.get("data_emissao"),
        visivel_paciente=dados.get("visivel_paciente", True),
        assinado=dados.get("assinado", False),
    )
    messages.success(request, f"Documento '{documento.titulo}' registrado com sucesso.")
    resposta = _tabela_fragment(request, _documentos_filtrados(request))
    resposta["X-Doc-OK"] = "1"
    return resposta


@grupos_requeridos(*GRUPOS_DOCUMENTOS_GESTAO)
def documento_editar(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    if request.method == "GET":
        return render(request, "documents/_documento_form.html", {
            "form": DocumentoForm(instance=documento),
            "documento": documento,
        })
    form = DocumentoForm(request.POST, request.FILES, instance=documento)
    if not form.is_valid():
        return render(request, "documents/_documento_form.html", {
            "form": form, "documento": documento, "oob": True,
        })
    dados = form.cleaned_data
    atualizar_documento(
        documento,
        arquivo=dados.get("arquivo"),
        paciente=dados["paciente"],
        tipo=dados["tipo"],
        titulo=dados["titulo"],
        descricao=dados.get("descricao") or "",
        profissional=dados.get("profissional"),
        atendimento=dados.get("atendimento"),
        data_emissao=dados.get("data_emissao"),
        visivel_paciente=dados.get("visivel_paciente", False),
        assinado=dados.get("assinado", False),
    )
    messages.success(request, f"Documento '{documento.titulo}' atualizado.")
    resposta = _tabela_fragment(request, _documentos_filtrados(request))
    resposta["X-Doc-OK"] = "1"
    return resposta


@require_POST
@grupos_requeridos(*GRUPOS_DOCUMENTOS_GESTAO)
def documento_excluir(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    titulo = excluir_documento(documento.pk)
    messages.success(request, f"Documento '{titulo}' excluído.")
    return _tabela_fragment(request, _documentos_filtrados(request))


@grupos_requeridos(*GRUPOS_DOCUMENTOS)
def documento_download(request, uuid):
    """Serve o arquivo do documento para operadores com acesso a documentos.

    O controle de acesso é o GRUPO, não o paciente: qualquer operador com
    GRUPOS_DOCUMENTOS baixa qualquer documento (decisão de negócio vigente).

    deleted_at__isnull=True é obrigatório: sem ele, um documento excluído
    logicamente continua baixável pelo UUID antigo - o soft delete vira
    decorativo e o link antigo vaza conteúdo que deveria ter sumido.
    """
    documento = get_object_or_404(
        Documento,
        uuid=uuid,
        deleted_at__isnull=True,
    )

    if not documento.arquivo:
        raise Http404("Arquivo não encontrado.")

    return FileResponse(
        documento.arquivo.open("rb"),
        as_attachment=True,
        filename=os.path.basename(documento.arquivo.name),
    )
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.urls import reverse

from apps.communication.exceptions import CommunicationError
from apps.communication.forms import MensagemForm
from apps.communication.models import Mensagem, Notificacao
from apps.communication.services import (
    enviar_mensagem,
    marcar_mensagem_lida,
    marcar_notificacao_lida,
)


@login_required
def central_notificacoes(request):
    notificacoes = Notificacao.objects.filter(destinatario=request.user).order_by("-created_at")
    return render(request, "communication/notificacoes.html", {"notificacoes": notificacoes})


@login_required
@require_POST
def notificacao_marcar_lida(request, pk):
    try:
        marcar_notificacao_lida(notificacao_id=pk, usuario=request.user)
    except CommunicationError as erro:
        messages.error(request, str(erro))
    notificacoes = Notificacao.objects.filter(destinatario=request.user).order_by("-created_at")
    return render(request, "communication/_notificacao_lista.html", {"notificacoes": notificacoes})


@login_required
def inbox(request):
    caixa = request.GET.get("caixa", "recebidas")
    if caixa == "enviadas":
        mensagens = (
            Mensagem.objects.filter(remetente=request.user)
            .select_related("destinatario", "paciente")
            .order_by("-data_envio")
        )
    else:
        caixa = "recebidas"
        mensagens = (
            Mensagem.objects.filter(destinatario=request.user)
            .select_related("remetente", "paciente")
            .order_by("-data_envio")
        )
    return render(request, "communication/inbox.html", {"mensagens": mensagens, "caixa": caixa})


@login_required
def mensagem_detalhe(request, pk):
    mensagem = get_object_or_404(Mensagem, pk=pk)
    if request.user.pk not in (mensagem.remetente_id, mensagem.destinatario_id):
        return HttpResponseForbidden("Você não participa desta conversa.")
    if mensagem.destinatario_id == request.user.pk:
        if mensagem.data_leitura is None:
            marcar_mensagem_lida(mensagem_id=mensagem.pk, usuario=request.user)
            mensagem.refresh_from_db()
        # Conclui as notificações IN_APP que anunciaram esta mensagem
        prefixo = reverse("communication:mensagem_detalhe", args=[mensagem.pk])
        Notificacao.objects.filter(
            destinatario=request.user,
            canal=Notificacao.Canal.IN_APP,
            link_url=prefixo,
            lida=False,
        ).update(lida=True, data_lida=timezone.now())
    return render(request, "communication/mensagem_detalhe.html", {"mensagem": mensagem})


@login_required
def mensagem_nova(request):
    if request.method == "POST":
        form = MensagemForm(request.POST, remetente=request.user)
        if form.is_valid():
            enviar_mensagem(
                remetente=request.user,
                destinatario=form.cleaned_data["destinatario"],
                assunto=form.cleaned_data["assunto"] or None,
                corpo=form.cleaned_data["corpo"],
            )
            messages.success(request, "Mensagem enviada.")
            return redirect("communication:inbox")
    else:
        form = MensagemForm(remetente=request.user)
    return render(request, "communication/mensagem_form.html", {"form": form, "titulo": "Nova mensagem"})


@login_required
def mensagem_responder(request, pk):
    original = get_object_or_404(Mensagem, pk=pk)
    if request.user.pk not in (original.remetente_id, original.destinatario_id):
        return HttpResponseForbidden("Você não participa desta conversa.")

    outro = original.destinatario if original.remetente_id == request.user.pk else original.remetente
    if outro is None:
        messages.info(request, "Esta mensagem não tem remetente para responder.")
        return redirect("communication:mensagem_nova")

    inicial = {
        "destinatario": outro.pk,
        "assunto": f"Re: {original.assunto}" if original.assunto else "",
    }
    if request.method == "POST":
        form = MensagemForm(request.POST, remetente=request.user)
        if form.is_valid():
            enviar_mensagem(
                remetente=request.user,
                destinatario=form.cleaned_data["destinatario"],
                assunto=form.cleaned_data["assunto"] or None,
                corpo=form.cleaned_data["corpo"],
            )
            messages.success(request, "Resposta enviada.")
            return redirect("communication:inbox")
    else:
        form = MensagemForm(initial=inicial, remetente=request.user)
    return render(request, "communication/mensagem_form.html", {"form": form, "titulo": "Responder mensagem"})
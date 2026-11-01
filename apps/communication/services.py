from django.utils import timezone
from django.urls import reverse

from apps.communication.dispatch import despachar_email, despachar_whatsapp
from apps.communication.exceptions import CommunicationError
from apps.communication.models import Mensagem, Notificacao


def enviar_notificacao(*, destinatario, tipo, titulo, mensagem,
                       canal=Notificacao.Canal.IN_APP, link_url=None,
                       agendamento=None, prescricao=None):
    """Cria a notificação e despacha pelo canal.

    IN_APP: o próprio registro é a entrega.
    EMAIL/WHATSAPP: tenta o canal externo; o registro é a trilha.
    """
    notificacao = Notificacao.objects.create(
        destinatario=destinatario,
        tipo=tipo,
        titulo=titulo,
        mensagem=mensagem,
        canal=canal,
        link_url=link_url,
        agendamento=agendamento,
        prescricao=prescricao,
    )

    if canal == Notificacao.Canal.EMAIL:
        despachar_email(destinatario_email=destinatario.email,
                        titulo=titulo, mensagem=mensagem)
    elif canal == Notificacao.Canal.WHATSAPP:
        despachar_whatsapp(telefone=destinatario.telefone,
                           titulo=titulo, mensagem=mensagem)

    return notificacao


def enviar_mensagem(*, remetente, destinatario, corpo, assunto=None,
                    paciente=None, canal=Mensagem.Canal.INTERNO):
    """Cria a mensagem e a notificação IN_APP do destinatário."""
    if remetente and destinatario and remetente.pk == destinatario.pk:
        raise CommunicationError("Remetente e destinatário devem ser diferentes.")

    mensagem = Mensagem.objects.create(
        remetente=remetente, destinatario=destinatario, paciente=paciente,
        canal=canal, assunto=assunto, corpo=corpo,
    )

    # Entrega por canal externo atualiza o status (ENTREGUE/FALHOU).
    if canal == Mensagem.Canal.EMAIL:
        ok = despachar_email(
            destinatario_email=destinatario.email if destinatario else None,
            titulo=assunto or "Nova mensagem", mensagem=corpo)
        mensagem.status = Mensagem.Status.ENTREGUE if ok else Mensagem.Status.FALHOU
        mensagem.save(update_fields=["status"])
    elif canal == Mensagem.Canal.WHATSAPP:
        ok = despachar_whatsapp(
            telefone=destinatario.telefone if destinatario else None,
            titulo=assunto or "Nova mensagem", mensagem=corpo)
        mensagem.status = Mensagem.Status.ENTREGUE if ok else Mensagem.Status.FALHOU
        mensagem.save(update_fields=["status"])

    # Notificação IN_APP para a central do destinatário.
    if destinatario:
        enviar_notificacao(
            destinatario=destinatario,
            tipo=Notificacao.Tipo.SISTEMA,
            titulo=assunto or "Nova mensagem",
            mensagem=corpo,
            link_url=reverse("communication:mensagem_detalhe", args=[mensagem.pk]),
        )        

    return mensagem


def marcar_mensagem_lida(*, mensagem_id, usuario):
    """Marca a mensagem como lida - somente o destinatário (anti-IDOR)."""
    mensagem = Mensagem.objects.filter(pk=mensagem_id).first()
    if mensagem is None:
        raise CommunicationError("Mensagem não encontrada.")
    if mensagem.destinatario_id != usuario.pk:
        raise CommunicationError("Somente o destinatário pode marcar a mensagem como lida.")
    if mensagem.data_leitura is None:
        mensagem.data_leitura = timezone.now()
        mensagem.status = Mensagem.Status.LIDA
        mensagem.save(update_fields=["data_leitura", "status"])
    return mensagem


def marcar_notificacao_lida(*, notificacao_id, usuario):
    """Marca a notificação como lida - somente o destinatário (anti-IDOR)."""
    notificacao = Notificacao.objects.filter(pk=notificacao_id).first()
    if notificacao is None:
        raise CommunicationError("Notificação não encontrada.")
    if notificacao.destinatario_id != usuario.pk:
        raise CommunicationError("Somente o destinatário pode marcar a notificação como lida.")
    if not notificacao.lida:
        notificacao.lida = True
        notificacao.data_lida = timezone.now()
        notificacao.save(update_fields=["lida", "data_lida"])
    return notificacao
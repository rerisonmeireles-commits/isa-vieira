import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def despachar_email(*, destinatario_email, titulo, mensagem):
    """Envia e-mail via backend configurado (console em dev).

    Falha de SMTP NUNCA propaga: registra no log e retorna False,
    para o service marcar a mensagem como FALHOU (spec 3.14.1).
    """
    if not destinatario_email:
        return False
    try:
        send_mail(
            subject=titulo,
            message=mensagem,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "nao-responder@clinica.local"),
            recipient_list=[destinatario_email],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Falha ao despachar e-mail para %s", destinatario_email)
        return False


def despachar_whatsapp(*, telefone, titulo, mensagem):
    """Stub do provedor de WhatsApp - mesmo contrato de falha do e-mail."""
    if not telefone:
        return False
    try:
        # TODO: integrar provedor (Twilio/Z-API/Evolution) com o mesmo padrão:
        # exceção → log + return False.
        print(f"[WHATSAPP STUB] para {telefone}: {titulo} - {mensagem}")
        return True
    except Exception:
        logger.exception("Falha ao despachar WhatsApp para %s", telefone)
        return False
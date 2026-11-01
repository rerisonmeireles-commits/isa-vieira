from apps.communication.models import Notificacao


def badge_notificacoes(request):
    if not request.user.is_authenticated:
        return {}
    total = Notificacao.objects.filter(destinatario=request.user, lida=False).count()
    return {"badge_notificacoes": total}
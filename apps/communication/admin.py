from django.contrib import admin

from .models import Mensagem, Notificacao


@admin.register(Mensagem)
class MensagemAdmin(admin.ModelAdmin):
    list_display = ("assunto", "remetente", "destinatario", "canal", "data_envio", "status")
    list_filter = ("canal", "status")
    search_fields = ("assunto", "corpo")
    readonly_fields = ("data_envio",)


@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "destinatario", "tipo", "canal", "lida", "created_at")
    list_filter = ("tipo", "canal", "lida")
    search_fields = ("titulo", "mensagem")
    readonly_fields = ("created_at",)
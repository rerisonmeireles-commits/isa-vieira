from django.contrib import admin

from .models import Atendimento


@admin.register(Atendimento)
class AtendimentoAdmin(admin.ModelAdmin):
    list_display = ("paciente", "profissional", "tipo_atendimento", "data_inicio", "data_fim", "status")
    list_filter = ("status", "tipo_atendimento")
    search_fields = ("paciente__nome_completo", "profissional__nome_completo")
    readonly_fields = ("uuid", "agendamento", "created_at", "updated_at")
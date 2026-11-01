from django.contrib import admin

from .models import Ausencia, Disponibilidade, Profissional


@admin.register(Profissional)
class ProfissionalAdmin(admin.ModelAdmin):
    list_display = ("nome_completo", "registro_conselho", "conselho", "status", "cor_agenda")
    list_filter = ("status", "conselho", "especialidades")
    search_fields = ("nome_completo", "cpf", "registro_conselho")
    filter_horizontal = ("especialidades",)


@admin.register(Disponibilidade)
class DisponibilidadeAdmin(admin.ModelAdmin):
    list_display = ("profissional", "dia_semana", "hora_inicio", "hora_fim", "intervalo_minutos", "tipo", "ativa")
    list_filter = ("tipo", "ativa", "dia_semana")
    search_fields = ("profissional__nome_completo",)


@admin.register(Ausencia)
class AusenciaAdmin(admin.ModelAdmin):
    list_display = ("profissional", "tipo", "data_inicio", "data_fim", "aprovado_por")
    list_filter = ("tipo",)
    search_fields = ("profissional__nome_completo",)
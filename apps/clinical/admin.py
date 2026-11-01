from django.utils import timezone
from django.contrib import admin

from .models import Avaliacao, Evolucao, Prontuario


@admin.register(Prontuario)
class ProntuarioAdmin(admin.ModelAdmin):
    list_display = ("paciente", "data_abertura", "alergias")
    search_fields = ("paciente__nome_completo",)
    readonly_fields = ("uuid", "created_at", "updated_at")


@admin.register(Avaliacao)
class AvaliacaoAdmin(admin.ModelAdmin):
    list_display = ("paciente", "profissional", "data", "tipo", "status", "escalas_eva_dor")
    list_filter = ("status", "tipo")
    search_fields = ("paciente__nome_completo", "profissional__nome_completo")
    # liberado_por/em ficam readonly: só a action abaixo pode preencher (regra P -> L)
    readonly_fields = (
        "uuid", "liberado_por", "liberado_em",
        "inativado_por", "inativado_em", "created_at", "updated_at",
    )
    actions = ["liberar_avaliacoes"]

    @admin.action(description="Liberar avaliações selecionadas (P → L)")
    def liberar_avaliacoes(self, request, queryset):
        for avaliacao in queryset.filter(status=Avaliacao.Status.PENDENTE):
            avaliacao.status = Avaliacao.Status.LIBERADA
            avaliacao.liberado_por = request.user
            avaliacao.liberado_em = timezone.now()
            avaliacao.save()


@admin.register(Evolucao)
class EvolucaoAdmin(admin.ModelAdmin):
    list_display = ("paciente", "profissional", "subjetivo")
    search_fields = ("paciente__nome_completo", "profissional__nome_completo")
    readonly_fields = ("uuid", "created_at", "updated_at")
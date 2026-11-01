from django.contrib import admin

from .models import Clinica, Configuracao, Sala, TipoAtendimento


@admin.register(Clinica)
class ClinicaAdmin(admin.ModelAdmin):
    list_display = ("nome_fantasia", "cnpj", "cidade", "uf", "telefone", "ativa")
    list_filter = ("ativa", "uf")
    search_fields = ("nome_fantasia", "razao_social", "cnpj")


@admin.register(Configuracao)
class ConfiguracaoAdmin(admin.ModelAdmin):
    list_display = ("clinica", "hora_abertura", "hora_fechamento", "duracao_padrao_minutos")


@admin.register(Sala)
class SalaAdmin(admin.ModelAdmin):
    list_display = ("nome", "capacidade", "status", "cor")
    list_filter = ("status",)
    search_fields = ("nome",)


@admin.register(TipoAtendimento)
class TipoAtendimentoAdmin(admin.ModelAdmin):
    list_display = ("nome", "duracao_minutos", "valor_padrao", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome",)
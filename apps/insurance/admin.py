from django.contrib import admin

from .models import Convenio, PacienteConvenio, Plano


class PlanoInline(admin.TabularInline):
    model = Plano
    extra = 0


@admin.register(Convenio)
class ConvenioAdmin(admin.ModelAdmin):
    list_display = ("nome", "registro_ans", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome", "registro_ans")
    inlines = [PlanoInline]


@admin.register(Plano)
class PlanoAdmin(admin.ModelAdmin):
    list_display = ("nome", "convenio", "codigo_ans", "carencia_dias", "ativo")
    list_filter = ("ativo", "convenio")
    search_fields = ("nome", "convenio__nome")


@admin.register(PacienteConvenio)
class PacienteConvenioAdmin(admin.ModelAdmin):
    list_display = ("paciente", "plano", "numero_carteirinha", "data_validade", "status")
    list_filter = ("status", "plano__convenio")
    search_fields = ("paciente__nome_completo", "numero_carteirinha")
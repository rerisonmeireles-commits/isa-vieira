from django.contrib import admin

from .models import ConselhoProfissional, Especialidade, Feriado


@admin.register(Especialidade)
class EspecialidadeAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativa")
    list_filter = ("ativa",)
    search_fields = ("nome",)


@admin.register(ConselhoProfissional)
class ConselhoProfissionalAdmin(admin.ModelAdmin):
    list_display = ("sigla", "nome", "uf")
    search_fields = ("sigla", "nome")


@admin.register(Feriado)
class FeriadoAdmin(admin.ModelAdmin):
    list_display = ("data", "descricao", "tipo", "uf", "recorrente")
    list_filter = ("tipo", "recorrente", "uf")
    search_fields = ("descricao",)
    date_hierarchy = "data"
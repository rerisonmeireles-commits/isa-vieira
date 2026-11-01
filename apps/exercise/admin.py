from django.contrib import admin

from .models import (ExecucaoExercicio, Exercicio, Prescricao,
                     PrescricaoExercicio)


class PrescricaoExercicioInline(admin.TabularInline):
    model = PrescricaoExercicio
    extra = 0


@admin.register(Exercicio)
class ExercicioAdmin(admin.ModelAdmin):
    list_display = ("nome", "categoria", "ativo")
    list_filter = ("categoria", "ativo")
    search_fields = ("nome",)


@admin.register(Prescricao)
class PrescricaoAdmin(admin.ModelAdmin):
    list_display = ("paciente", "profissional", "data", "status", "data_validade")
    list_filter = ("status",)
    search_fields = ("paciente__nome_completo", "profissional__nome_completo")
    readonly_fields = ("uuid", "created_at", "updated_at")
    inlines = [PrescricaoExercicioInline]


@admin.register(PrescricaoExercicio)
class PrescricaoExercicioAdmin(admin.ModelAdmin):
    list_display = ("prescricao", "ordem", "exercicio", "series", "repeticoes", "ativo")
    search_fields = ("prescricao__paciente__nome_completo", "exercicio__nome")


@admin.register(ExecucaoExercicio)
class ExecucaoExercicioAdmin(admin.ModelAdmin):
    list_display = ("paciente", "prescricao_exercicio", "data", "realizado", "percepcao_esforco", "criado_via")
    list_filter = ("realizado", "criado_via")
    search_fields = ("paciente__nome_completo",)
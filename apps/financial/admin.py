from django.contrib import admin

from .models import ContaReceber, Faturamento, Pagamento


class PagamentoInline(admin.TabularInline):
    model = Pagamento
    extra = 0
    readonly_fields = ("data_pagamento",)


@admin.register(ContaReceber)
class ContaReceberAdmin(admin.ModelAdmin):
    list_display = ("paciente", "descricao", "valor_total", "data_vencimento", "status", "tipo")
    list_filter = ("status", "tipo")
    search_fields = ("paciente__nome_completo", "descricao")
    date_hierarchy = "data_vencimento"
    inlines = [PagamentoInline]


@admin.register(Pagamento)
class PagamentoAdmin(admin.ModelAdmin):
    list_display = ("conta_receber", "valor", "forma", "data_pagamento", "status", "recebido_por")
    list_filter = ("forma", "status")
    search_fields = ("conta_receber__paciente__nome_completo",)


@admin.register(Faturamento)
class FaturamentoAdmin(admin.ModelAdmin):
    list_display = ("convenio", "periodo_inicio", "periodo_fim", "valor_total", "guias_enviadas", "status")
    list_filter = ("status",)
    search_fields = ("convenio__nome",)
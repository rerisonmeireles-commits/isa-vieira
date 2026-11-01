"""Registro no Django Admin do domínio de Agenda."""

from django.contrib import admin

from apps.scheduling.models import Agenda, Agendamento, BloqueioAgenda, SlotAgenda


class SlotAgendaInline(admin.TabularInline):
    model = SlotAgenda
    extra = 0
    can_delete = False
    ordering = ("hora_inicio",)
    fields = ("hora_inicio", "hora_fim", "status", "agendamento_do_slot")
    readonly_fields = ("hora_inicio", "hora_fim", "status", "agendamento_do_slot")

    @admin.display(description="Agendamento ativo")
    def agendamento_do_slot(self, obj):
        agendamento = obj.agendamento_ativo
        if not agendamento:
            return "-"
        return f"{agendamento.paciente} ({agendamento.get_status_display()})"


@admin.register(Agenda)
class AgendaAdmin(admin.ModelAdmin):
    list_display = ("profissional", "data", "status", "slots_livres", "slots_ocupados")
    list_filter = ("status", "profissional")
    search_fields = ("profissional__nome_completo",)
    date_hierarchy = "data"
    list_select_related = ("profissional",)
    inlines = [SlotAgendaInline]

    @admin.display(description="Livres")
    def slots_livres(self, obj):
        return obj.slots.filter(status=SlotAgenda.Status.LIVRE).count()

    @admin.display(description="Ocupados")
    def slots_ocupados(self, obj):
        return obj.slots.filter(status=SlotAgenda.Status.OCUPADO).count()


@admin.register(SlotAgenda)
class SlotAgendaAdmin(admin.ModelAdmin):
    list_display = ("agenda", "hora_inicio", "hora_fim", "status", "agendamento_do_slot")
    list_filter = ("status", "agenda__data", "agenda__profissional")
    search_fields = (
        "agenda__profissional__nome_completo",
        "agendamentos__paciente__nome_completo",
    )
    list_select_related = ("agenda__profissional",)
    ordering = ("agenda__data", "hora_inicio")

    @admin.display(description="Agendamento ativo")
    def agendamento_do_slot(self, obj):
        agendamento = obj.agendamento_ativo
        if not agendamento:
            return "-"
        return f"{agendamento.paciente} ({agendamento.get_status_display()})"


@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ("paciente", "data_hora", "profissional", "status", "origem", "valor")
    list_filter = ("status", "origem", "profissional")
    search_fields = ("paciente__nome_completo", "uuid")
    readonly_fields = (
        "uuid", "created_at", "updated_at", "remarcado_de", "data_remarcacao",
    )
    list_select_related = ("paciente", "profissional", "slot__agenda")
    date_hierarchy = "slot__agenda__data"

    @admin.display(description="Data/Hora", ordering="slot__agenda__data")
    def data_hora(self, obj):
        return f"{obj.slot.agenda.data:%d/%m/%Y} {obj.slot.hora_inicio:%H:%M}"


@admin.register(BloqueioAgenda)
class BloqueioAgendaAdmin(admin.ModelAdmin):
    list_display = ("motivo", "tipo", "profissional", "sala", "data_inicio", "data_fim")
    list_filter = ("tipo", "profissional")
    search_fields = ("motivo",)
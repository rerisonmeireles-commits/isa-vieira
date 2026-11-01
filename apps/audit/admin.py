from django.contrib import admin

from .models import LogAuditoria


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(admin.ModelAdmin):
    """Trilha de auditoria imutável: leitura apenas, sem exceções.

    Quatro camadas de proteção, cada uma bloqueando uma superfície diferente:
    - readonly_fields: nenhum campo é editável no formulário
    - has_add_permission: ninguém cria log manualmente (só o serviço cria)
    - has_change_permission: o formulário de edição nem abre
    - has_delete_permission: exclusão individual bloqueada
    - actions = None: exclusão em massa bloqueada (defesa em profundidade)

    A trilha responde "quem fez o quê, quando, de onde e por quê". Se qualquer
    uma dessas camadas cair, a trilha deixa de valer como prova.
    """

    list_display = ("data_hora", "usuario", "acao", "tabela", "registro_id", "ip")
    list_filter = ("acao", "tabela")
    search_fields = ("usuario__username", "tabela", "motivo")
    readonly_fields = [field.name for field in LogAuditoria._meta.fields]
    date_hierarchy = "data_hora"

    # Desliga o dropdown de ações em massa (delete_selected, etc.)
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        # Explícito para clareza: leitura é o propósito da trilha.
        return True
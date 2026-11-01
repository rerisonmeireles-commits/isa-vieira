from django.contrib import admin

from .models import Documento


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "paciente", "tipo", "data_emissao", "visivel_paciente", "assinado")
    list_filter = ("tipo", "visivel_paciente", "assinado")
    search_fields = ("titulo", "paciente__nome_completo")
    readonly_fields = ("uuid", "hash_sha256", "created_at", "updated_at")
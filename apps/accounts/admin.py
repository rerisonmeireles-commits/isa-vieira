from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ConsentimentoLgpd, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "is_active")
    list_filter = ("is_staff", "is_active", "groups")
    search_fields = ("username", "email", "first_name", "last_name", "documento")
    fieldsets = UserAdmin.fieldsets + (
        ("Dados Complementares", {"fields": ("documento", "telefone", "aceite_termos")}),
    )


@admin.register(ConsentimentoLgpd)
class ConsentimentoLgpdAdmin(admin.ModelAdmin):
    list_display = ("paciente", "versao_termo", "data_assinatura", "canal", "aceito")
    list_filter = ("canal", "aceito")
    search_fields = ("paciente__nome_completo", "versao_termo")
    readonly_fields = ("created_at",)
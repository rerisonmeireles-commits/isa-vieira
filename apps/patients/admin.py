from django.contrib import admin

from .models import Contato, ContatoEmergencia, Endereco, Paciente


class EnderecoInline(admin.TabularInline):
    model = Endereco
    extra = 0


class ContatoInline(admin.TabularInline):
    model = Contato
    extra = 0


class ContatoEmergenciaInline(admin.TabularInline):
    model = ContatoEmergencia
    extra = 0


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = ("nome_completo", "cpf", "telefone", "origem", "user", "status")
    list_filter = ("status", "origem", "sexo")
    search_fields = ("nome_completo", "cpf", "email")
    inlines = [EnderecoInline, ContatoInline, ContatoEmergenciaInline]
    readonly_fields = ("uuid", "created_at", "updated_at")


@admin.register(Endereco)
class EnderecoAdmin(admin.ModelAdmin):
    list_display = ("paciente", "logradouro", "numero", "cidade", "uf", "is_principal")
    search_fields = ("paciente__nome_completo", "cidade")


@admin.register(Contato)
class ContatoAdmin(admin.ModelAdmin):
    list_display = ("paciente", "tipo", "valor", "is_principal")
    list_filter = ("tipo",)
    search_fields = ("paciente__nome_completo", "valor")


@admin.register(ContatoEmergencia)
class ContatoEmergenciaAdmin(admin.ModelAdmin):
    list_display = ("paciente", "nome", "parentesco", "telefone")
    search_fields = ("paciente__nome_completo", "nome")
import re

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.accounts.models import ConsentimentoLgpd, Usuario


def _limpar_cpf(valor):
    return re.sub(r"\D", "", valor or "")


class UsuarioForm(forms.ModelForm):
    senha = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput,
        required=False,
        help_text="Obrigatória na criação. Na edição, deixe vazio para manter a atual.",
    )
    grupos = forms.ModelMultipleChoiceField(
        label="Perfis de acesso",
        queryset=None,
        widget=forms.SelectMultiple(attrs={"size": 5}),
        required=False,
    )

    class Meta:
        model = Usuario
        fields = [
            "username", "first_name", "last_name", "email",
            "documento", "telefone", "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth.models import Group
        self.fields["grupos"].queryset = Group.objects.all().order_by("name")
        self.fields["email"].required = True
        if self.instance.pk:
            self.fields["senha"].help_text = "Deixe vazio para manter a senha atual."
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.CheckboxInput):
                campo.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(campo.widget, forms.Select):
                campo.widget.attrs.setdefault("class", "form-select form-select-sm")
            else:
                campo.widget.attrs.setdefault("class", "form-control form-control-sm")

    def clean_documento(self):
        cpf = _limpar_cpf(self.cleaned_data.get("documento"))
        if cpf and len(cpf) != 11:
            raise ValidationError("O CPF deve ter 11 dígitos.")
        return cpf or None

    def clean_senha(self):
        senha = self.cleaned_data.get("senha")
        if senha:
            validate_password(senha)
        return senha

    def clean(self):
        dados = super().clean()
        if not self.instance.pk and not dados.get("senha"):
            raise ValidationError("A senha é obrigatória ao criar um usuário.")
        return dados


class ConsentimentoForm(forms.ModelForm):
    class Meta:
        model = ConsentimentoLgpd
        fields = ["paciente", "versao_termo", "canal", "aceito", "ip_origem"]
        widgets = {
            "ip_origem": forms.TextInput(attrs={"placeholder": "Opcional"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.CheckboxInput):
                campo.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(campo.widget, forms.Select):
                campo.widget.attrs.setdefault("class", "form-select form-select-sm")
            else:
                campo.widget.attrs.setdefault("class", "form-control form-control-sm")
"""Formulários do módulo de Convênios: operadora + planos associados."""

import re

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from apps.insurance.models import Convenio, Plano


# ---------------------------------------------------------------------------
# CNPJ - validação pelos dígitos verificadores e formatação canônica
# ---------------------------------------------------------------------------

def _apenas_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def validar_cnpj(cnpj):
    """Valida os dois dígitos verificadores do CNPJ (algoritmo oficial)."""
    digitos = _apenas_digitos(cnpj)
    if len(digitos) != 14 or digitos == digitos[0] * 14:
        return False

    def _calcular_digito(base, pesos):
        soma = sum(int(d) * p for d, p in zip(base, pesos))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    if _calcular_digito(digitos[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]) != int(digitos[12]):
        return False
    if _calcular_digito(digitos[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]) != int(digitos[13]):
        return False
    return True


def formatar_cnpj(cnpj):
    """Normaliza para XX.XXX.XXX/XXXX-XX (mesmo formato gravado no banco)."""
    digitos = _apenas_digitos(cnpj)
    if len(digitos) != 14:
        return cnpj
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


# ---------------------------------------------------------------------------
# Formulário principal
# ---------------------------------------------------------------------------

class ConvenioForm(forms.ModelForm):
    class Meta:
        model = Convenio
        fields = ["nome", "cnpj", "registro_ans", "ativo", "observacoes"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "cnpj": forms.TextInput(attrs={"class": "form-control", "placeholder": "00.000.000/0000-00"}),
            "registro_ans": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex.: 123456"}),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "observacoes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean_nome(self):
        nome = (self.cleaned_data.get("nome") or "").strip()
        if len(nome) < 3:
            raise ValidationError("Informe o nome do convênio.")
        conflito = Convenio.objects.filter(nome__iexact=nome)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if conflito.exists():
            raise ValidationError("Já existe um convênio com este nome.")
        return nome

    def clean_cnpj(self):
        cnpj = self.cleaned_data.get("cnpj")
        if not cnpj:
            return None
        if not validar_cnpj(cnpj):
            raise ValidationError("CNPJ inválido - confira os dígitos informados.")
        return formatar_cnpj(cnpj)


# ---------------------------------------------------------------------------
# Planos (formset)
# ---------------------------------------------------------------------------

class PlanoForm(forms.ModelForm):
    class Meta:
        model = Plano
        fields = ["nome", "codigo_ans", "carencia_dias", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "codigo_ans": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "carencia_dias": forms.NumberInput(attrs={"class": "form-control form-control-sm"}),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class PlanoFormSet(forms.BaseInlineFormSet):
    """Detecta planos duplicados (mesma constraint uq_plano_convenio_nome)
    e traduz em mensagem amigável - evita IntegrityError cru."""

    def clean(self):
        if any(self.errors):
            return

        nomes = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            nome = (form.cleaned_data.get("nome") or "").strip().lower()
            if nome in nomes:
                raise ValidationError("Plano duplicado: já existe um plano com este nome nesta lista.")
            nomes.append(nome)

        if self.instance.pk:
            ids_editados = [f.instance.pk for f in self.forms if f.instance.pk]
            existentes = Plano.objects.filter(convenio=self.instance).exclude(pk__in=ids_editados)
            for form in self.forms:
                if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                    continue
                nome = (form.cleaned_data.get("nome") or "").strip().lower()
                if existentes.filter(nome__iexact=nome).exists():
                    raise ValidationError(
                        "Já existe um plano com este nome para este convênio no banco."
                    )


PlanoFormSetFactory = inlineformset_factory(
    Convenio,
    Plano,
    form=PlanoForm,
    formset=PlanoFormSet,
    extra=0,          # lição aprendida: linha em branco automática valida campos vazios
    can_delete=True,
)
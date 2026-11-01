"""Formulários do módulo Clinic: dados da clínica, configuração, salas e tipos."""

import re

from django import forms
from django.core.exceptions import ValidationError

from apps.clinic.models import Clinica, Configuracao, Sala, TipoAtendimento

UF_CHOICES = [
    ("", "-"),
    ("AC", "AC - Acre"), ("AL", "AL - Alagoas"), ("AP", "AP - Amapá"),
    ("AM", "AM - Amazonas"), ("BA", "BA - Bahia"), ("CE", "CE - Ceará"),
    ("DF", "DF - Distrito Federal"), ("ES", "ES - Espírito Santo"),
    ("GO", "GO - Goiás"), ("MA", "MA - Maranhão"), ("MT", "MT - Mato Grosso"),
    ("MS", "MS - Mato Grosso do Sul"), ("MG", "MG - Minas Gerais"),
    ("PA", "PA - Pará"), ("PB", "PB - Paraíba"), ("PR", "PR - Paraná"),
    ("PE", "PE - Pernambuco"), ("PI", "PI - Piauí"), ("RJ", "RJ - Rio de Janeiro"),
    ("RN", "RN - Rio Grande do Norte"), ("RS", "RS - Rio Grande do Sul"),
    ("RO", "RO - Rondônia"), ("RR", "RR - Roraima"), ("SC", "SC - Santa Catarina"),
    ("SP", "SP - São Paulo"), ("SE", "SE - Sergipe"), ("TO", "TO - Tocantins"),
]


def _validar_cnpj(cnpj):
    """Valida o CNPJ (algoritmo dos dígitos verificadores)."""
    cnpj = re.sub(r"\D", "", cnpj or "")
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    def digito(parcial, pesos):
        soma = sum(int(d) * p for d, p in zip(parcial, pesos))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    d1 = digito(cnpj[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = digito(cnpj[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return cnpj[-2:] == f"{d1}{d2}"


class ClinicaForm(forms.ModelForm):
    uf = forms.ChoiceField(
        choices=UF_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    class Meta:
        model = Clinica
        fields = [
            "nome_fantasia", "razao_social", "cnpj", "inscricao_estadual",
            "logradouro", "numero", "complemento", "bairro", "cidade", "uf",
            "cep", "telefone", "email", "logo", "ativa",
        ]
        widgets = {
            "nome_fantasia": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "razao_social": forms.TextInput(attrs={"class": "form-control"}),            
            "cnpj": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "00.000.000/0000-00",
                "data-mascara": "cnpj",          # ← novo
            }),
            "inscricao_estadual": forms.TextInput(attrs={"class": "form-control"}),
            "logradouro": forms.TextInput(attrs={"class": "form-control"}),
            "numero": forms.TextInput(attrs={"class": "form-control"}),
            "complemento": forms.TextInput(attrs={"class": "form-control"}),
            "bairro": forms.TextInput(attrs={"class": "form-control"}),
            "cidade": forms.TextInput(attrs={"class": "form-control"}),
            "uf": forms.Select(attrs={"class": "form-select"}),            
            "cep": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "00000-000",
                "data-mascara": "cep",          # ← novo
            }),

            "telefone": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "(00) 00000-0000",
                "data-mascara": "telefone",      # ← novo
            }),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "logo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "ativa": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #self.fields["uf"].choices = [("", "-")] + UF_CHOICES
        #self.fields["uf"].required = False

    def clean_cnpj(self):
        cnpj = self.cleaned_data.get("cnpj")
        if not _validar_cnpj(cnpj):
            raise ValidationError("CNPJ inválido.")
        conflito = Clinica.objects.filter(cnpj__iexact=cnpj)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if conflito.exists():
            raise ValidationError("Já existe uma clínica com este CNPJ.")
        return cnpj


class ConfiguracaoForm(forms.ModelForm):
    uf = forms.ChoiceField(
        choices=UF_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )    
    class Meta:
        model = Configuracao
        fields = [
            "hora_abertura", "hora_fechamento", "duracao_padrao_minutos",
            "intervalo_padrao_minutos", "politica_cancelamento_horas",
            "dias_max_antecedencia", "permite_agendamento_online",
            "mensagem_boas_vindas", "mensagem_lembrete", "uf",
        ]
        widgets = {
            "hora_abertura": forms.TimeInput(attrs={"class": "form-control", "type": "time"}, format="%H:%M"),
            "hora_fechamento": forms.TimeInput(attrs={"class": "form-control", "type": "time"}, format="%H:%M"),
            "duracao_padrao_minutos": forms.NumberInput(attrs={"class": "form-control"}),
            "intervalo_padrao_minutos": forms.NumberInput(attrs={"class": "form-control"}),
            "politica_cancelamento_horas": forms.NumberInput(attrs={"class": "form-control"}),
            "dias_max_antecedencia": forms.NumberInput(attrs={"class": "form-control"}),
            "permite_agendamento_online": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "mensagem_boas_vindas": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "mensagem_lembrete": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "uf": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["hora_abertura"].input_formats = ["%H:%M"]
        #self.fields["hora_fechamento"].input_formats = ["%H:%M"]
        #self.fields["uf"].choices = [("", "-")] + UF_CHOICES

    def clean(self):
        dados = super().clean()
        abertura = dados.get("hora_abertura")
        fechamento = dados.get("hora_fechamento")
        if abertura and fechamento and fechamento <= abertura:
            raise ValidationError("O horário de fechamento deve ser posterior ao de abertura.")
        return dados


class SalaForm(forms.ModelForm):
    class Meta:
        model = Sala
        fields = ["nome", "descricao", "capacidade", "equipamentos", "status", "cor"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "descricao": forms.TextInput(attrs={"class": "form-control"}),
            "capacidade": forms.NumberInput(attrs={"class": "form-control"}),
            "equipamentos": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "cor": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        }

    def clean_nome(self):
        nome = (self.cleaned_data.get("nome") or "").strip()
        if len(nome) < 2:
            raise ValidationError("Informe o nome da sala.")
        conflito = Sala.objects.filter(nome__iexact=nome)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if conflito.exists():
            raise ValidationError("Já existe uma sala com este nome.")
        return nome

    def clean_capacidade(self):
        capacidade = self.cleaned_data.get("capacidade")
        if capacidade is None or capacidade < 1:
            raise ValidationError("A capacidade deve ser maior que zero.")
        return capacidade


class TipoAtendimentoForm(forms.ModelForm):
    class Meta:
        model = TipoAtendimento
        fields = ["nome", "descricao", "duracao_minutos", "valor_padrao", "cor", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "descricao": forms.TextInput(attrs={"class": "form-control"}),
            "duracao_minutos": forms.NumberInput(attrs={"class": "form-control"}),
            "valor_padrao": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "cor": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_nome(self):
        nome = (self.cleaned_data.get("nome") or "").strip()
        if len(nome) < 3:
            raise ValidationError("Informe o nome do tipo de atendimento.")
        conflito = TipoAtendimento.objects.filter(nome__iexact=nome)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if conflito.exists():
            raise ValidationError("Já existe um tipo de atendimento com este nome.")
        return nome

    def clean_duracao_minutos(self):
        duracao = self.cleaned_data.get("duracao_minutos")
        if duracao is None or duracao <= 0:
            raise ValidationError("A duração deve ser maior que zero.")
        return duracao

    def clean_valor_padrao(self):
        valor = self.cleaned_data.get("valor_padrao")
        if valor is not None and valor < 0:
            raise ValidationError("O valor padrão não pode ser negativo.")
        return valor
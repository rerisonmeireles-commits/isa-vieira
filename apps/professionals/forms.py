"""Formulários do módulo de Profissionais: cadastro + disponibilidade + ausências."""

import re

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from apps.clinic.models import Sala
from apps.professionals.models import Ausencia, Disponibilidade, Profissional
from apps.registry.models import ConselhoProfissional, Especialidade


# ---------------------------------------------------------------------------
# CPF - mesmos validadores do módulo de Pacientes
# (extrair para um módulo compartilhado em apps/base quando o 3º app precisar)
# ---------------------------------------------------------------------------

def _apenas_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def validar_cpf(cpf):
    """Valida os dois dígitos verificadores do CPF (algoritmo oficial)."""
    digitos = _apenas_digitos(cpf)
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11
        if digito == 10:
            digito = 0
        if digito != int(digitos[tamanho]):
            return False
    return True


def formatar_cpf(cpf):
    digitos = _apenas_digitos(cpf)
    if len(digitos) != 11:
        return cpf
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


DIAS_SEMANA = [
    (1, "Segunda-feira"), (2, "Terça-feira"), (3, "Quarta-feira"),
    (4, "Quinta-feira"), (5, "Sexta-feira"), (6, "Sábado"), (7, "Domingo"),
]


# ---------------------------------------------------------------------------
# Formulário principal
# ---------------------------------------------------------------------------

class ProfissionalForm(forms.ModelForm):
    class Meta:
        model = Profissional
        fields = [
            "nome_completo", "cpf", "registro_conselho", "conselho",
            "especialidades", "status", "cor_agenda", "foto",
            "data_admissao", "observacoes",
        ]
        widgets = {
            "nome_completo": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "cpf": forms.TextInput(attrs={"class": "form-control", "placeholder": "000.000.000-00"}),
            "registro_conselho": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex.: 12345-F"}),
            "conselho": forms.Select(attrs={"class": "form-select"}),
            "especialidades": forms.CheckboxSelectMultiple(),
            "status": forms.Select(attrs={"class": "form-select"}),
            "cor_agenda": forms.TextInput(attrs={"class": "form-control form-control-color", "type": "color"}),
            "foto": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "data_admissao": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "observacoes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_admissao"].input_formats = ["%Y-%m-%d"]
        self.fields["conselho"].queryset = ConselhoProfissional.objects.order_by("nome")
        self.fields["especialidades"].queryset = Especialidade.objects.order_by("nome")

    def clean_nome_completo(self):
        nome = (self.cleaned_data.get("nome_completo") or "").strip()
        if len(nome) < 3:
            raise ValidationError("Informe o nome completo do profissional.")
        return nome

    def clean_cpf(self):
        cpf = self.cleaned_data.get("cpf")
        if not cpf:
            return None
        if not validar_cpf(cpf):
            raise ValidationError("CPF inválido - confira os dígitos informados.")
        formatado = formatar_cpf(cpf)
        # Mesma regra da constraint uq_profissional_cpf_ativo: único entre os
        # registros NÃO soft-deletados.
        conflito = Profissional.objects.filter(cpf=formatado, deleted_at__isnull=True)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if conflito.exists():
            raise ValidationError("Já existe um profissional ativo com este CPF.")
        return formatado


# ---------------------------------------------------------------------------
# Disponibilidade (formset)
# ---------------------------------------------------------------------------

class DisponibilidadeForm(forms.ModelForm):
    class Meta:
        model = Disponibilidade
        fields = [
            "dia_semana", "hora_inicio", "hora_fim", "intervalo_minutos",
            "sala_padrao", "tipo", "data_inicio", "data_fim", "ativa",
        ]
        widgets = {
            "dia_semana": forms.Select(choices=DIAS_SEMANA, attrs={"class": "form-select form-select-sm"}),
            "hora_inicio": forms.TimeInput(attrs={"class": "form-control form-control-sm", "type": "time"}, format="%H:%M"),
            "hora_fim": forms.TimeInput(attrs={"class": "form-control form-control-sm", "type": "time"}, format="%H:%M"),
            "intervalo_minutos": forms.NumberInput(attrs={"class": "form-control form-control-sm"}),
            "sala_padrao": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "tipo": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "data_inicio": forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}, format="%Y-%m-%d"),
            "data_fim": forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}, format="%Y-%m-%d"),
            "ativa": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sala_padrao"].queryset = Sala.objects.order_by("nome")
        self.fields["hora_inicio"].input_formats = ["%H:%M"]
        self.fields["hora_fim"].input_formats = ["%H:%M"]
        self.fields["data_inicio"].input_formats = ["%Y-%m-%d"]
        self.fields["data_fim"].input_formats = ["%Y-%m-%d"]

    def clean(self):
        dados = super().clean()
        inicio = dados.get("hora_inicio")
        fim = dados.get("hora_fim")
        if inicio and fim and fim <= inicio:
            raise ValidationError("O horário final deve ser maior que o inicial.")
        return dados


class DisponibilidadeFormSet(forms.BaseInlineFormSet):
    """Detecta regras duplicadas (mesma constraint uq_disponibilidade_regra)
    e traduz em mensagem amigável - evita IntegrityError cru."""

    def clean(self):
        if any(self.errors):
            return

        regras = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            chave = (
                form.cleaned_data.get("dia_semana"),
                form.cleaned_data.get("hora_inicio"),
                form.cleaned_data.get("tipo"),
            )
            if chave in regras:
                raise ValidationError(
                    "Regra duplicada: já existe disponibilidade para este dia/horário/tipo."
                )
            regras.append(chave)

        # Conflito com regras já gravadas no banco (exceto as desta edição)
        if self.instance.pk:
            ids_editados = [f.instance.pk for f in self.forms if f.instance.pk]
            existentes = Disponibilidade.objects.filter(
                profissional=self.instance
            ).exclude(pk__in=ids_editados)
            for form in self.forms:
                if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                    continue
                chave = (
                    form.cleaned_data.get("dia_semana"),
                    form.cleaned_data.get("hora_inicio"),
                    form.cleaned_data.get("tipo"),
                )
                if existentes.filter(
                    dia_semana=chave[0], hora_inicio=chave[1], tipo=chave[2]
                ).exists():
                    raise ValidationError(
                        "Já existe uma regra de disponibilidade para este dia/horário/tipo no banco."
                    )


DisponibilidadeFormSetFactory = inlineformset_factory(
    Profissional,
    Disponibilidade,
    form=DisponibilidadeForm,
    formset=DisponibilidadeFormSet,
    extra=0,          # ← era 1
    can_delete=True,
)


# ---------------------------------------------------------------------------
# Ausência (formset)
# ---------------------------------------------------------------------------

class AusenciaForm(forms.ModelForm):
    class Meta:
        model = Ausencia
        fields = ["tipo", "data_inicio", "data_fim", "observacoes"]
        widgets = {
            "tipo": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "data_inicio": forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}, format="%Y-%m-%d"),
            "data_fim": forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}, format="%Y-%m-%d"),
            "observacoes": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_inicio"].input_formats = ["%Y-%m-%d"]
        self.fields["data_fim"].input_formats = ["%Y-%m-%d"]

    def clean(self):
        dados = super().clean()
        inicio = dados.get("data_inicio")
        fim = dados.get("data_fim")
        if inicio and fim and fim < inicio:
            raise ValidationError("A data final deve ser maior ou igual à inicial.")
        return dados


AusenciaFormSetFactory = inlineformset_factory(
    Profissional,
    Ausencia,
    form=AusenciaForm,
    extra=0,          # ← era 1 adicionado para não criar linha em branco no formset
    can_delete=True,
)
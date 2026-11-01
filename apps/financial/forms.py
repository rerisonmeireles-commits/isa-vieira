"""Formulários do módulo Financeiro: contas a receber, pagamentos e faturamento."""

from django import forms
from django.urls import reverse_lazy
from django.utils import timezone

from apps.financial.models import ContaReceber, Faturamento, Pagamento


class ContaReceberForm(forms.ModelForm):
    class Meta:
        model = ContaReceber
        # status REMOVIDO: é derivado dos pagamentos pelo recálculo -
        # nunca digitado à mão (furo do cenário "editar parcela para ABERTA")
        fields = [
            "paciente", "convenio", "agendamento", "tipo", "descricao",
            "valor_total", "parcelas", "data_vencimento", "forma_pagamento",
        ]
        widgets = {
            "paciente": forms.Select(attrs={"class": "form-select"}),
            "convenio": forms.Select(attrs={"class": "form-select"}),
            "agendamento": forms.Select(attrs={"class": "form-select"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "descricao": forms.TextInput(attrs={"class": "form-control"}),
            "valor_total": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "parcelas": forms.NumberInput(attrs={"class": "form-control"}),
            "data_vencimento": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "forma_pagamento": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_vencimento"].input_formats = ["%Y-%m-%d"]
        self.fields["paciente"].queryset = self.fields["paciente"].queryset.order_by("nome_completo")
        self.fields["convenio"].required = False
        self.fields["agendamento"].required = False

    def clean_valor_total(self):
        valor = self.cleaned_data.get("valor_total")
        if valor is None or valor < 0:
            raise forms.ValidationError("O valor total não pode ser negativo.")
        return valor


class PagamentoForm(forms.ModelForm):
    class Meta:
        model = Pagamento
        fields = ["valor", "forma", "status", "comprovante", "observacoes", "data_pagamento"]
        widgets = {
            "valor": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "forma": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "comprovante": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "observacoes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "data_pagamento": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_pagamento"].input_formats = [
            "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
        ]

    def clean_valor(self):
        valor = self.cleaned_data.get("valor")
        if valor is None or valor <= 0:
            raise forms.ValidationError("O valor do pagamento deve ser maior que zero.")
        return valor

    def clean_data_pagamento(self):
        """Decisão 4: retrodatação permitida; data futura, nunca."""
        data = self.cleaned_data.get("data_pagamento")
        if data and data > timezone.now():
            raise forms.ValidationError("A data do pagamento não pode ser no futuro.")
        return data


# Atributos hx-* nos widgets fazem o preview funcionar sem editar os inputs
# do template - o <form> precisa de id="form-lote" e a div #lote-preview existir.
_HX_PREVIEW = {
    "hx-get": reverse_lazy("financial:preview_lote"),
    "hx-include": "#form-lote",
    "hx-target": "#lote-preview",
    "hx-trigger": "change",
}

class FaturamentoLoteForm(forms.ModelForm):
    """Criação de lote: convênio + período. Totais e status são calculados
    pelo service a partir das contas vinculadas - nunca digitados."""

    class Meta:
        model = Faturamento
        fields = ["convenio", "periodo_inicio", "periodo_fim", "observacoes"]
        widgets = {
            "convenio": forms.Select(attrs={"class": "form-select", **_HX_PREVIEW}),
            "periodo_inicio": forms.DateInput(
                attrs={"class": "form-control", "type": "date", **_HX_PREVIEW},
                format="%Y-%m-%d",
            ),
            "periodo_fim": forms.DateInput(
                attrs={"class": "form-control", "type": "date", **_HX_PREVIEW},
                format="%Y-%m-%d",
            ),
            "observacoes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["periodo_inicio"].input_formats = ["%Y-%m-%d"]
        self.fields["periodo_fim"].input_formats = ["%Y-%m-%d"]
        self.fields["convenio"].required = True   # lote é sempre de um convênio

    def clean(self):
        dados = super().clean()
        inicio = dados.get("periodo_inicio")
        fim = dados.get("periodo_fim")
        if inicio and fim and fim < inicio:
            raise forms.ValidationError("O período final deve ser maior ou igual ao inicial.")
        return dados


class FaturamentoForm(forms.ModelForm):
    """(Legado) Totais digitáveis - mantido por compatibilidade.
    A criação pela tela usa FaturamentoLoteForm, que calcula os totais."""

    class Meta:
        model = Faturamento
        fields = ["convenio", "periodo_inicio", "periodo_fim", "valor_total", "guias_enviadas", "status", "observacoes"]
        widgets = {
            "convenio": forms.Select(attrs={"class": "form-select"}),
            "periodo_inicio": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "periodo_fim": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "valor_total": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "guias_enviadas": forms.NumberInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "observacoes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["periodo_inicio"].input_formats = ["%Y-%m-%d"]
        self.fields["periodo_fim"].input_formats = ["%Y-%m-%d"]
        self.fields["convenio"].required = False

    def clean(self):
        dados = super().clean()
        inicio = dados.get("periodo_inicio")
        fim = dados.get("periodo_fim")
        if inicio and fim and fim < inicio:
            raise forms.ValidationError("O período final deve ser maior ou igual ao inicial.")
        return dados
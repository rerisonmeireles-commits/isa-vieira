from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet

from apps.clinical.models import Avaliacao, Evolucao, Prontuario, FimItem, GoniometriaMedicao

class AvaliacaoForm(forms.ModelForm):
    class Meta:
        model = Avaliacao
        fields = [
            "tipo", "queixa_principal", "historia_doenca_atual",
            "historia_pregressa", "medicamentos_em_uso", "exame_fisico",
            "escalas_eva_dor", "hipotese_diagnostica", "conduta",
            "plano_terapeutico", "objetivo_curto_prazo",
            "objetivo_longo_prazo", "observacoes",
        ]

        widgets = {
            "queixa_principal": forms.Textarea(attrs={"rows": 4,"class": "form-control",}),
            "historia_doenca_atual": forms.Textarea(attrs={"rows": 3,"class": "form-control",}),
            "historia_pregressa": forms.Textarea(attrs={"rows": 3,"class": "form-control",}),
            "medicamentos_em_uso": forms.Textarea(attrs={"rows": 3,"class": "form-control",}),
            "exame_fisico": forms.Textarea(attrs={"rows": 3,"class": "form-control",}),
            "goniometria": forms.Textarea(attrs={"rows": 5,"class": "form-control",}),
            "hipotese_diagnostica": forms.Textarea(attrs={"rows": 4,"class": "form-control",}),
            "conduta": forms.Textarea(attrs={"rows": 4,"class": "form-control",}),
            "plano_terapeutico": forms.Textarea(attrs={"rows": 4,"class": "form-control",}),
            "objetivo_curto_prazo": forms.Textarea(attrs={"rows": 3,"class": "form-control",}),
            "objetivo_longo_prazo": forms.Textarea(attrs={"rows": 3,"class": "form-control",}),
            "observacoes": forms.Textarea(attrs={"rows": 6,"class": "form-control",}),
        }
    # Campos Obrigatórios para Rascunho: nenhum campo de texto obrigatório - só o tipo identifica a avaliação
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)        
        for nome, campo in self.fields.items():
            if nome != "tipo":
                campo.required = False
                

class EvolucaoForm(forms.ModelForm):

    class Meta:
        model = Evolucao
        fields = [
            "subjetivo",
            "objetivo",
            "avaliacao_clinica",
            "plano",
            "frequencia_cardiaca",
            "frequencia_respiratoria",
            "pressao_arterial",
            "saturacao_o2",
            "observacoes",
        ]

        widgets = {
            "subjetivo": forms.Textarea(attrs={"rows": 6,"class": "form-control",}),
            "objetivo": forms.Textarea(attrs={"rows": 6,"class": "form-control",}),
            "avaliacao_clinica": forms.Textarea(attrs={"rows": 6,"class": "form-control",}),
            "plano": forms.Textarea(attrs={"rows": 6,"class": "form-control",}),
            "observacoes": forms.Textarea(attrs={"rows": 4,"class": "form-control",}),
        }

    class Meta:
        model = Evolucao
        fields = ["subjetivo", "objetivo", "avaliacao", "plano"]
        widgets = {
            "subjetivo": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "objetivo": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "avaliacao": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "plano": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for campo in self.fields.values():
            campo.required = False

class ProntuarioForm(forms.ModelForm):
    class Meta:
        model = Prontuario
        fields = [
            "historico_clinico", "alergias", "medicamentos_em_uso",
            "condicoes_cronicas", "observacoes",
        ]
        widgets = {
            "historico_clinico": forms.Textarea(attrs={"rows": 4,"class": "form-control",}),
            "alergias": forms.Textarea(attrs={"rows": 4,"class": "form-control",}),
            "medicamentos_em_uso": forms.Textarea(attrs={"rows": 4,"class": "form-control",}),
            "condicoes_cronicas": forms.Textarea(attrs={"rows": 4,"class": "form-control",}),
            "observacoes": forms.Textarea(attrs={"rows": 6,"class": "form-control",}),
        }            

#ESCALAS DE AVALIAÇÃO (FIM – Functional Independence Measure).
class FimItemForm(forms.ModelForm):
    class Meta:
        model = FimItem
        fields = ["item", "dominio", "pontuacao"]
        widgets = {
            "item": forms.HiddenInput(),
            "dominio": forms.HiddenInput(),
            "pontuacao": forms.NumberInput(
                attrs={"min": 1, "max": 7, "class": "form-control form-control-sm"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pontuacao"].required = False  # rascunho: item sem nota é permitido
        # Linhas extras pré-montadas: copia o initial para o instance,
        # para o template resolver get_item_display / dominio
        if self.initial.get("item"):
            self.instance.item = self.initial["item"]
            self.instance.dominio = self.initial["dominio"]


FimItemFormSet = inlineformset_factory(
    Avaliacao, FimItem, form=FimItemForm,
    extra=18, max_num=18, can_delete=False,
)

class GoniometriaMedicaoForm(forms.ModelForm):
    class Meta:
        model = GoniometriaMedicao
        fields = ["articulacao", "movimento", "lado", "graus", "observacao"]
        widgets = {
            "graus": forms.NumberInput(
                attrs={"min": 0, "max": 360, "class": "form-control form-control-sm"}
            ),
        }


class GoniometriaFormSet(BaseInlineFormSet):
    """Descarta linhas vazias (sem articulação preenchida)."""

    def clean(self):
        super().clean()
        for form in self.forms:
            if not form.cleaned_data.get("articulacao"):
                if not form.cleaned_data.get("DELETE"):
                    form.cleaned_data["DELETE"] = True


GoniometriaMedicaoFormSet = inlineformset_factory(
    Avaliacao, GoniometriaMedicao, form=GoniometriaMedicaoForm,
    formset=GoniometriaFormSet,
    extra=4, max_num=40, can_delete=True,
)        
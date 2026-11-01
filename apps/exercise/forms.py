from django import forms

from apps.exercise.models import (
    ExecucaoExercicio,
    Exercicio,
    Prescricao,
    PrescricaoExercicio,
)


class ExercicioForm(forms.ModelForm):
    class Meta:
        model = Exercicio
        fields = [
            "nome", "categoria", "descricao", "musculos_envolvidos",
            "contraindicacoes", "instrucoes", "video_url", "imagem", "ativo",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "descricao": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),            
            "musculos_envolvidos": forms.Textarea(
                attrs={"rows": 4, "class": "form-control"}
            ),
            "contraindicacoes": forms.Textarea(
                attrs={"rows": 4, "class": "form-control"}
            ),
            "instrucoes": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "video_url": forms.URLInput(attrs={"class": "form-control"}),
            "imagem": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class PrescricaoForm(forms.ModelForm):
    class Meta:
        model = Prescricao
        fields = ["paciente", "objetivo", "observacoes", "data_validade"]
        widgets = {
            "paciente": forms.Select(attrs={"class": "form-select"}),
            "objetivo": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "observacoes": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "data_validade": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
        }


class PrescricaoExercicioForm(forms.ModelForm):
    class Meta:
        model = PrescricaoExercicio
        fields = [
            "exercicio", "series", "repeticoes", "carga", "intervalo_segundos",
            "frequencia_semanal", "duracao_minutos", "progressao", "observacoes",
            "ativo",
        ]
        widgets = {
            "exercicio": forms.Select(attrs={"class": "form-select"}),
            "series": forms.NumberInput(
                attrs={"class": "form-control form-control-sm", "min": 1}
            ),
            "repeticoes": forms.TextInput(
                attrs={"class": "form-control form-control-sm",
                       "placeholder": "ex.: 12x ou 30s"}
            ),
            "carga": forms.TextInput(
                attrs={"class": "form-control form-control-sm",
                       "placeholder": "ex.: canelera 2kg"}
            ),
            "intervalo_segundos": forms.NumberInput(
                attrs={"class": "form-control form-control-sm", "min": 0}
            ),
            "frequencia_semanal": forms.NumberInput(
                attrs={"class": "form-control form-control-sm", "min": 1}
            ),
            "duracao_minutos": forms.NumberInput(
                attrs={"class": "form-control form-control-sm", "min": 0}
            ),
            "progressao": forms.Textarea(
                attrs={"rows": 2, "class": "form-control form-control-sm"}
            ),
            "observacoes": forms.Textarea(
                attrs={"rows": 2, "class": "form-control form-control-sm"}
            ),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


PrescricaoExercicioFormSet = forms.inlineformset_factory(
    Prescricao,
    PrescricaoExercicio,
    form=PrescricaoExercicioForm,
    extra=3,
    can_delete=True,
)


class ExecucaoExercicioForm(forms.ModelForm):
    class Meta:
        model = ExecucaoExercicio
        fields = [
            "realizado", "series_feitas", "repeticoes_feitas",
            "percepcao_esforco", "dor_eva", "observacoes",
        ]
        widgets = {
            "realizado": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "series_feitas": forms.NumberInput(
                attrs={"class": "form-control", "min": 0}
            ),
            "repeticoes_feitas": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "ex.: 12x"}
            ),
            "percepcao_esforco": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "max": 10}
            ),
            "dor_eva": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 10}
            ),
            "observacoes": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
                           
        }
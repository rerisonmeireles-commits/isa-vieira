"""Formulários do módulo Registry: Conselhos, Especialidades e Feriados."""

from django import forms
from django.core.exceptions import ValidationError

from apps.registry.models import ConselhoProfissional, Especialidade, Feriado

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


class EspecialidadeForm(forms.ModelForm):
    class Meta:
        model = Especialidade
        fields = ["nome", "descricao", "ativa"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "descricao": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "ativa": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_nome(self):
        nome = (self.cleaned_data.get("nome") or "").strip()
        if len(nome) < 3:
            raise ValidationError("Informe o nome da especialidade.")
        conflito = Especialidade.objects.filter(nome__iexact=nome)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if conflito.exists():
            raise ValidationError("Já existe uma especialidade com este nome.")
        return nome


class ConselhoProfissionalForm(forms.ModelForm):
    uf = forms.ChoiceField(
        choices=UF_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )    
    class Meta:
        model = ConselhoProfissional
        fields = ["sigla", "nome", "uf"]
        widgets = {
            "sigla": forms.TextInput(attrs={
                "class": "form-control", "autofocus": True,
                "placeholder": "Ex.: CREFITO-3",
            }),
            "nome": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ex.: Conselho Regional de Fisioterapia e Terapia Ocupacional",
            }),
            "uf": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #self.fields["uf"].choices = [("", "Todas as UFs")] + UF_CHOICES
        #self.fields["uf"].required = False

    def clean_sigla(self):
        sigla = (self.cleaned_data.get("sigla") or "").strip().upper()
        if len(sigla) < 2:
            raise ValidationError("Informe a sigla do conselho.")
        conflito = ConselhoProfissional.objects.filter(sigla__iexact=sigla)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if conflito.exists():
            raise ValidationError("Já existe um conselho com esta sigla.")
        return sigla


class FeriadoForm(forms.ModelForm):
    class Meta:
        model = Feriado
        fields = ["data", "descricao", "tipo", "uf", "municipio", "recorrente"]
        widgets = {
            "data": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "descricao": forms.TextInput(attrs={
                "class": "form-control", "autofocus": True, "placeholder": "Ex.: Ano Novo",
            }),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "uf": forms.Select(attrs={"class": "form-select"}),
            "municipio": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex.: São Paulo"}),
            "recorrente": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data"].input_formats = ["%Y-%m-%d"]
        self.fields["uf"].choices = [("", "-")] + UF_CHOICES
        self.fields["uf"].required = False
        self.fields["municipio"].required = False

    def clean(self):
        dados = super().clean()
        data = dados.get("data")
        tipo = dados.get("tipo")
        if not data:
            return dados

        uf = dados.get("uf")
        municipio = dados.get("municipio")

        # Normaliza por tipo: NACIONAL não tem localidade; ESTADUAL só UF;
        # MUNICIPAL exige UF + município.
        if tipo == Feriado.Tipo.NACIONAL:
            uf = None
            municipio = None
        elif tipo == Feriado.Tipo.ESTADUAL:
            municipio = None
            if not uf:
                self.add_error("uf", "Informe a UF para feriados estaduais.")
                return dados
        elif tipo == Feriado.Tipo.MUNICIPAL:
            if not uf:
                self.add_error("uf", "Informe a UF para feriados municipais.")
                return dados
            if not municipio:
                self.add_error("municipio", "Informe o município para feriados municipais.")
                return dados

        # Unicidade efetiva: NULLs não colidem no PostgreSQL, então a regra
        # (data, uf, municipio) precisa ser validada em Python.
        conflito = Feriado.objects.filter(data=data, uf=uf, municipio=municipio)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if conflito.exists():
            raise ValidationError("Já existe um feriado para esta data e localidade.")

        dados["uf"] = uf
        dados["municipio"] = municipio
        return dados
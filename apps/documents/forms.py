import os

from django import forms
from django.core.exceptions import ValidationError

from apps.documents.models import Documento

TAMANHO_MAXIMO_MB = 10
TAMANHO_MAXIMO_BYTES = TAMANHO_MAXIMO_MB * 1024 * 1024
EXTENSOES_PERMITIDAS = [".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"]


class DocumentoForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = [
            "paciente", "tipo", "titulo", "descricao", "arquivo",
            "profissional", "atendimento", "data_emissao",
            "visivel_paciente", "assinado",
        ]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 2}),
            "data_emissao": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Na edição, o arquivo atual é mantido se nenhum novo for enviado.
        if self.instance.pk:
            self.fields["arquivo"].required = False
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.CheckboxInput):
                campo.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(campo.widget, forms.Select):
                campo.widget.attrs.setdefault("class", "form-select form-select-sm")
            else:
                campo.widget.attrs.setdefault("class", "form-control form-control-sm")

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get("arquivo")
        if not arquivo:
            return arquivo
        extensao = os.path.splitext(arquivo.name)[1].lower()
        if extensao not in EXTENSOES_PERMITIDAS:
            raise ValidationError(
                "Formato não permitido. Aceitos: " + ", ".join(EXTENSOES_PERMITIDAS) + "."
            )
        if arquivo.size > TAMANHO_MAXIMO_BYTES:
            raise ValidationError(f"O arquivo excede o limite de {TAMANHO_MAXIMO_MB} MB.")
        return arquivo
"""Formulários do módulo de Pacientes: dados cadastrais + entidades relacionadas."""

import re

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from apps.patients.models import Contato, ContatoEmergencia, Endereco, Paciente
from apps.insurance.models import PacienteConvenio, Plano
from apps.accounts.constants import VERSAO_TERMO_VIGENTE
from apps.accounts.models import ConsentimentoLgpd
from apps.patients.models import Contato, ContatoEmergencia, Endereco, Paciente

# ---------------------------------------------------------------------------
# CPF - validação pelos dígitos verificadores e formatação canônica
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
    """Normaliza para 000.000.000-00 (mesmo formato gravado no banco)."""
    digitos = _apenas_digitos(cpf)
    if len(digitos) != 11:
        return cpf
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


# ---------------------------------------------------------------------------
# Formulário principal
# ---------------------------------------------------------------------------

class PacienteForm(forms.ModelForm):
    # --- NOVO: consentimento LGPD coletado na criação (Approach A) ---
    consent_aceito = forms.BooleanField(
        label="Paciente aceitou os termos de tratamento de dados (LGPD)",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    consent_versao_termo = forms.CharField(
        label="Versão do termo",
        max_length=50,
        initial=VERSAO_TERMO_VIGENTE,
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    consent_canal = forms.ChoiceField(
        label="Canal",
        choices=ConsentimentoLgpd.Canal.choices,
        initial=ConsentimentoLgpd.Canal.RECEPCAO,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    # -----------------------------------------------------------------       
       
    class Meta:
        model = Paciente
        fields = [
            "nome_completo", "data_nascimento", "sexo", "cpf", "rg",
            "email", "telefone", "estado_civil", "profissao",
            "origem", "status", "observacoes",
        ]
        widgets = {
            "nome_completo": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "data_nascimento": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"
            ),
            "sexo": forms.Select(attrs={"class": "form-select"}),
            "cpf": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "000.000.000-00"}
            ),
            "rg": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "telefone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "(00) 00000-0000"}
            ),
            "estado_civil": forms.TextInput(attrs={"class": "form-control"}),
            "profissao": forms.TextInput(attrs={"class": "form-control"}),
            "origem": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "observacoes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # O input type="date" do navegador envia AAAA-MM-DD.
        self.fields["data_nascimento"].input_formats = ["%Y-%m-%d"]

    def clean_nome_completo(self):
        nome = (self.cleaned_data.get("nome_completo") or "").strip()
        if len(nome) < 3:
            raise ValidationError("Informe o nome completo do paciente.")
        return nome
            
        # Consentimento é histórico imutável - nunca é re-registrado aqui.
        if self.instance.pk:
            for campo in ("consent_aceito", "consent_versao_termo", "consent_canal"):
                self.fields.pop(campo, None)

    def clean_cpf(self):
        cpf = self.cleaned_data.get("cpf")
        if not cpf:
            return None
        if not validar_cpf(cpf):
            raise ValidationError("CPF inválido - confira os dígitos informados.")

        formatado = formatar_cpf(cpf)
        # Mesma regra da constraint uq_paciente_cpf_ativo: único entre os
        # registros NÃO soft-deletados.
        conflito = Paciente.objects.filter(cpf=formatado, deleted_at__isnull=True)
        if self.instance.pk:
            conflito = conflito.exclude(pk=self.instance.pk)
        if conflito.exists():
            raise ValidationError("Já existe um paciente ativo com este CPF.")
        return formatado


# ---------------------------------------------------------------------------
# Formsets das entidades relacionadas
# ---------------------------------------------------------------------------

_WIDGETS_ENDERECO = {
    "tipo": forms.Select(attrs={"class": "form-select form-select-sm"}),
    "logradouro": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    "numero": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    "complemento": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    "bairro": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    "cidade": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    "uf": forms.TextInput(attrs={"class": "form-control form-control-sm", "maxlength": 2}),
    "cep": forms.TextInput(attrs={"class": "form-control form-control-sm"}),    
    "is_principal": forms.CheckboxInput(attrs={"class": "form-check-input"}),    
}
class EnderecoForm(forms.ModelForm):

    class Meta:
        model = Endereco

        fields = [
            "tipo",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "uf",
            "cep",
            "is_principal",
        ]

        labels = {
            "tipo": "Tipo de Endereço",
            "logradouro": "Logradouro",
            "numero": "Número",
            "complemento": "Complemento",
            "bairro": "Bairro",
            "cidade": "Cidade",
            "uf": "UF",
            "cep": "CEP",
            "is_principal": "Principal",
        }

        widgets = _WIDGETS_ENDERECO

EnderecoFormSet = inlineformset_factory(
    Paciente, 
    Endereco,
    form=EnderecoForm,
    widgets=_WIDGETS_ENDERECO,
    extra=0,
    can_delete=True,
)


_WIDGETS_CONTATO = {
    "tipo": forms.Select(attrs={"class": "form-select form-select-sm"}),
    "valor": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    "is_principal": forms.CheckboxInput(attrs={"class": "form-check-input"}),
    "observacoes": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
}

ContatoFormSet = inlineformset_factory(
    Paciente,
    Contato,
    fields=["tipo", "valor", "is_principal", "observacoes"],
    widgets=_WIDGETS_CONTATO,
    extra=1,
    can_delete=True,
)


_WIDGETS_EMERGENCIA = {
    "nome": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    "parentesco": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    "telefone": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    "observacoes": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
}

ContatoEmergenciaFormSet = inlineformset_factory(
    Paciente,
    ContatoEmergencia,
    fields=["nome", "parentesco", "telefone", "observacoes"],
    widgets=_WIDGETS_EMERGENCIA,
    extra=1,
    can_delete=True,
)

class PlanoChoiceField(forms.ModelChoiceField):
    """Exibe 'Operadora - Plano' no select, em vez de só o nome do plano."""

    def label_from_instance(self, obj):
        return f"{obj.convenio.nome} - {obj.nome}"


class PacienteConvenioForm(forms.ModelForm):
    class Meta:
        model = PacienteConvenio
        fields = [
            "plano", "numero_carteirinha", "data_validade",
            "titular", "status", "observacoes",
        ]
        widgets = {
            "plano": forms.Select(attrs={"class": "form-select"}),
            "numero_carteirinha": forms.TextInput(attrs={"class": "form-control"}),
            "data_validade": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"
            ),
            "titular": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "observacoes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, paciente=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.paciente = paciente
        self.fields["data_validade"].input_formats = ["%Y-%m-%d"]

        # Apenas planos ativos de operadoras ativas; na edição, mantém o plano
        # atual do vínculo mesmo que tenha sido inativado depois.
        queryset = Plano.objects.filter(ativo=True, convenio__ativo=True)
        if self.instance and self.instance.pk and self.instance.plano_id:
            queryset = queryset | Plano.objects.filter(pk=self.instance.plano_id)
        self.fields["plano"] = PlanoChoiceField(
            queryset=queryset.select_related("convenio").order_by("convenio__nome", "nome"),
            widget=forms.Select(attrs={"class": "form-select"}),
        )

    def clean(self):
        dados = super().clean()
        plano = dados.get("plano")
        if plano and self.paciente:
            # Mesma regra da constraint uq_paciente_plano: traduz em mensagem
            # amigável, sem IntegrityError cru.
            conflito = PacienteConvenio.objects.filter(
                paciente=self.paciente, plano=plano
            )
            if self.instance.pk:
                conflito = conflito.exclude(pk=self.instance.pk)
            if conflito.exists():
                raise ValidationError(
                    "Este paciente já possui vínculo com este plano."
                )
        return dados
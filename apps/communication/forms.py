
from django import forms
from django.contrib.auth import get_user_model

Usuario = get_user_model()


class MensagemForm(forms.Form):

    destinatario = forms.ModelChoiceField(
        queryset=Usuario.objects.none(),
        label="Destinatário",
        empty_label="Selecione um destinatário",
        widget=forms.Select(attrs={
            "class": "form-select w-100",
        }),
    )

    assunto = forms.CharField(
        max_length=200,
        required=False,
        label="Assunto",
        widget=forms.TextInput(attrs={
            "class": "form-control w-100",
            "placeholder": "Digite o assunto (opcional)",
        }),
    )

    corpo = forms.CharField(
        label="Mensagem",
        widget=forms.Textarea(attrs={
            "class": "form-control w-100",
            "rows": 5,
            "placeholder": "Digite sua mensagem...",
        }),
    )

    def __init__(self, *args, remetente=None, **kwargs):
        super().__init__(*args, **kwargs)

        usuarios = Usuario.objects.filter(is_active=True)

        if remetente is not None:
            usuarios = usuarios.exclude(pk=remetente.pk)

        self.fields["destinatario"].queryset = usuarios.order_by(
            "first_name", "username"
        )

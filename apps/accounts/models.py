from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    documento = models.CharField("CPF", max_length=14, unique=True, null=True, blank=True)
    telefone = models.CharField(max_length=20, null=True, blank=True)
    aceite_termos = models.BooleanField("Aceite dos termos", default=False)

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

    def __str__(self):
        return self.get_full_name() or self.username


class ConsentimentoLgpd(models.Model):
    class Canal(models.TextChoices):
        PORTAL = "PORTAL", "Portal"
        RECEPCAO = "RECEPCAO", "Recepção"
        APP = "APP", "App"
        TELEFONE = "TELEFONE", "Telefone"

    paciente = models.ForeignKey(
        "patients.Paciente",
        on_delete=models.PROTECT,
        related_name="consentimentos",
    )
    versao_termo = models.CharField(max_length=50)
    data_assinatura = models.DateField(auto_now_add=True)
    canal = models.CharField(max_length=20, choices=Canal.choices, default=Canal.RECEPCAO)
    aceito = models.BooleanField(default=True)
    ip_origem = models.GenericIPAddressField(null=True, blank=True)
    hash_termo = models.CharField("Hash SHA-256 do termo", max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Consentimento LGPD"
        verbose_name_plural = "Consentimentos LGPD"
        indexes = [models.Index(fields=["paciente"])]

    def __str__(self):
        return f"{self.paciente} - {self.versao_termo}"
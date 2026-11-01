import uuid
import hashlib

from django.db import models

from apps.base import SoftDeleteModel

class Documento(SoftDeleteModel):
    class Tipo(models.TextChoices):
        RECEITA = "RECEITA", "Receita"
        ATESTADO = "ATESTADO", "Atestado"
        LAUDO = "LAUDO", "Laudo"
        TERMO_CONSENTIMENTO = "TERMO_CONSENTIMENTO", "Termo de Consentimento"
        EVOLUCAO = "EVOLUCAO", "Evolução"
        AVALIACAO = "AVALIACAO", "Avaliação"
        RELATORIO = "RELATORIO", "Relatório"
        OUTROS = "OUTROS", "Outros"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    paciente = models.ForeignKey(
        "patients.Paciente",
        on_delete=models.PROTECT,
        related_name="documentos",
    )
    profissional = models.ForeignKey(
        "professionals.Profissional",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documentos",
    )
    atendimento = models.ForeignKey(
        "attendance.Atendimento",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documentos",
    )
    tipo = models.CharField(max_length=25, choices=Tipo.choices)
    titulo = models.CharField(max_length=200)
    descricao = models.TextField(null=True, blank=True)
    arquivo = models.FileField(upload_to="documentos/")
    tamanho_bytes = models.BigIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=100, null=True, blank=True)
    hash_sha256 = models.CharField(max_length=64, null=True, blank=True)
    data_emissao = models.DateField(null=True, blank=True)
    visivel_paciente = models.BooleanField(default=True)
    assinado = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Documento"
        verbose_name_plural = "Documentos"
        indexes = [models.Index(fields=["paciente", "tipo"])]

    def __str__(self):
        return self.titulo
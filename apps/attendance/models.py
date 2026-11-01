import uuid

from django.db import models

from apps.base import SoftDeleteModel


class Atendimento(SoftDeleteModel):
    class Status(models.TextChoices):
        AGENDADO = "AGENDADO", "Agendado"
        EM_ANDAMENTO = "EM_ANDAMENTO", "Em Andamento"
        CONCLUIDO = "CONCLUIDO", "Concluído"
        NAO_REALIZADO = "NAO_REALIZADO", "Não Realizado"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    agendamento = models.OneToOneField(
        "scheduling.Agendamento",
        on_delete=models.PROTECT,
        related_name="atendimento",
    )
    paciente = models.ForeignKey(
        "patients.Paciente",
        on_delete=models.PROTECT,
        related_name="atendimentos",
    )
    profissional = models.ForeignKey(
        "professionals.Profissional",
        on_delete=models.PROTECT,
        related_name="atendimentos",
    )
    sala = models.ForeignKey(
        "clinic.Sala",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="atendimentos",
    )
    tipo_atendimento = models.ForeignKey(
        "clinic.TipoAtendimento",
        on_delete=models.PROTECT,
        related_name="atendimentos",
    )
    data_inicio = models.DateTimeField(null=True, blank=True)
    data_fim = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AGENDADO)
    observacoes = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Atendimento"
        verbose_name_plural = "Atendimentos"
        indexes = [
            models.Index(fields=["paciente", "data_inicio"]),
            models.Index(fields=["profissional", "data_inicio"]),
        ]

    def __str__(self):
        return f"Atendimento #{self.pk} - {self.paciente}"

    
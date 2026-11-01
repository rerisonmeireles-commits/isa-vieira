from django.db import models

from apps.base import SoftDeleteModel


class Convenio(SoftDeleteModel):
    nome = models.CharField(max_length=150)
    cnpj = models.CharField(max_length=18, null=True, blank=True)
    registro_ans = models.CharField(max_length=20, null=True, blank=True)
    ativo = models.BooleanField(default=True)
    observacoes = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Convênio"
        verbose_name_plural = "Convênios"
        constraints = [
            models.UniqueConstraint(
                fields=["nome"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_convenio_nome_ativo",
            ),
        ]


    def __str__(self):
        return self.nome


class Plano(SoftDeleteModel):
    convenio = models.ForeignKey(Convenio, on_delete=models.PROTECT, related_name="planos")
    nome = models.CharField(max_length=150)
    codigo_ans = models.CharField(max_length=20, null=True, blank=True)
    carencia_dias = models.PositiveSmallIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Plano"
        verbose_name_plural = "Planos"
        models.UniqueConstraint(
            fields=["convenio", "nome"],
            condition=models.Q(deleted_at__isnull=True),
            name="uq_plano_convenio_nome_ativo",
        ),

    def __str__(self):
        return f"{self.convenio} - {self.nome}"


class PacienteConvenio(SoftDeleteModel):
    class Status(models.TextChoices):
        ATIVO = "ATIVO", "Ativo"
        SUSPENSO = "SUSPENSO", "Suspenso"
        CANCELADO = "CANCELADO", "Cancelado"

    paciente = models.ForeignKey(
        "patients.Paciente",
        on_delete=models.CASCADE,
        related_name="convenios",
    )
    plano = models.ForeignKey(Plano, on_delete=models.PROTECT, related_name="pacientes")
    numero_carteirinha = models.CharField(max_length=50, null=True, blank=True)
    data_validade = models.DateField(null=True, blank=True)
    titular = models.BooleanField(default=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ATIVO)
    observacoes = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Paciente Convênio"
        verbose_name_plural = "Pacientes Convênio"
        indexes = [models.Index(fields=["paciente", "status"])]
        models.UniqueConstraint(
            fields=["paciente", "plano"],
            condition=models.Q(deleted_at__isnull=True),
            name="uq_paciente_plano_ativo",
        ),

    def __str__(self):
        return f"{self.paciente} - {self.plano}"
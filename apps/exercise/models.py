import uuid

from django.db import models

from apps.base import SoftDeleteModel


class Exercicio(SoftDeleteModel):
    class Categoria(models.TextChoices):
        MOBILIDADE = "MOBILIDADE", "Mobilidade"
        FORCA = "FORCA", "Força"
        EQUILIBRIO = "EQUILIBRIO", "Equilíbrio"
        RESPIRATORIO = "RESPIRATORIO", "Respiratório"
        ALONGAMENTO = "ALONGAMENTO", "Alongamento"
        PROPRIOCEPCAO = "PROPRIOCEPCAO", "Propriocepção"
        OUTROS = "OUTROS", "Outros"

    nome = models.CharField(max_length=150)
    descricao = models.TextField(null=True, blank=True)
    categoria = models.CharField(max_length=25, choices=Categoria.choices, default=Categoria.OUTROS)
    musculos_envolvidos = models.TextField(null=True, blank=True)
    contraindicacoes = models.TextField(null=True, blank=True)
    instrucoes = models.TextField(null=True, blank=True)
    video_url = models.URLField(null=True, blank=True)
    imagem = models.ImageField(upload_to="exercicios/", null=True, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Exercício"
        verbose_name_plural = "Exercícios"
        models.UniqueConstraint(
            fields=["nome"],
            condition=models.Q(deleted_at__isnull=True),
            name="uq_exercicio_nome_ativo",
        ),        

    def __str__(self):
        return self.nome


class Prescricao(SoftDeleteModel):
    class Status(models.TextChoices):
        ATIVA = "ATIVA", "Ativa"
        ENCERRADA = "ENCERRADA", "Encerrada"
        CANCELADA = "CANCELADA", "Cancelada"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    paciente = models.ForeignKey(
        "patients.Paciente",
        on_delete=models.PROTECT,
        related_name="prescricoes",
    )
    profissional = models.ForeignKey(
        "professionals.Profissional",
        on_delete=models.PROTECT,
        related_name="prescricoes",
    )
    data = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ATIVA)
    objetivo = models.TextField(null=True, blank=True)
    observacoes = models.TextField(null=True, blank=True)
    data_validade = models.DateField(null=True, blank=True)
    motivo_encerramento = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = "Prescrição"
        verbose_name_plural = "Prescrições"
        indexes = [models.Index(fields=["paciente", "status"])]

    def __str__(self):
        return f"Prescrição {self.paciente} - {self.data}"


class PrescricaoExercicio(models.Model):
    """Item de uma prescrição.

    Não implementa soft delete: a remoção lógica é feita via ativo=False.
    Prescricao e ExecucaoExercicio têm deleted_at; este model não.
    """    
    prescricao = models.ForeignKey(Prescricao, on_delete=models.PROTECT, related_name="itens")
    exercicio = models.ForeignKey(Exercicio, on_delete=models.PROTECT, related_name="prescricoes")
    ordem = models.PositiveSmallIntegerField(default=1)
    series = models.PositiveSmallIntegerField(default=3)
    repeticoes = models.CharField(max_length=30, null=True, blank=True)  # ex.: "12x" ou "30s"
    carga = models.CharField(max_length=50, null=True, blank=True)       # ex.: "canelera 2kg"
    intervalo_segundos = models.PositiveSmallIntegerField(default=30)
    frequencia_semanal = models.PositiveSmallIntegerField(default=5)
    duracao_minutos = models.PositiveSmallIntegerField(null=True, blank=True)
    progressao = models.TextField(null=True, blank=True)
    observacoes = models.TextField(null=True, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Item de Prescrição"
        verbose_name_plural = "Itens de Prescrição"
        ordering = ["ordem"]
        constraints = [
            models.UniqueConstraint(
                fields=["prescricao", "exercicio", "ordem"],
                name="uq_prescricao_exercicio_ordem",
            ),
        ]

    def __str__(self):
        return f"{self.ordem}. {self.exercicio}"


class ExecucaoExercicio(SoftDeleteModel):    
    class CriadoVia(models.TextChoices):
        PORTAL = "PORTAL", "Portal"
        CLINICA = "CLINICA", "Clínica"

    prescricao_exercicio = models.ForeignKey(PrescricaoExercicio, on_delete=models.PROTECT, related_name="execucoes")
    paciente = models.ForeignKey(
        "patients.Paciente",
        on_delete=models.PROTECT,
        related_name="execucoes_exercicios",
    )
    data = models.DateField(auto_now_add=True)
    realizado = models.BooleanField(default=False)
    series_feitas = models.PositiveSmallIntegerField(null=True, blank=True)
    repeticoes_feitas = models.CharField(max_length=30, null=True, blank=True)
    percepcao_esforco = models.PositiveSmallIntegerField(null=True, blank=True)
    dor_eva = models.PositiveSmallIntegerField(null=True, blank=True)
    observacoes = models.TextField(null=True, blank=True)
    criado_via = models.CharField(max_length=15, choices=CriadoVia.choices, default=CriadoVia.PORTAL)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = "Execução de Exercício"
        verbose_name_plural = "Execuções de Exercícios"
        indexes = [models.Index(fields=["prescricao_exercicio", "data"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(percepcao_esforco__gte=1, percepcao_esforco__lte=10),
                name="ck_execucao_esforco",
            ),
            models.CheckConstraint(
                condition=models.Q(dor_eva__gte=0, dor_eva__lte=10),
                name="ck_execucao_dor",
            ),
        ]

    def __str__(self):
        return f"{self.paciente} - {self.data} ({'feito' if self.realizado else 'não feito'})"
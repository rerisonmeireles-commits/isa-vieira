from django.db import models

from apps.base import SoftDeleteModel, TimeStampedModel


class Profissional(SoftDeleteModel):
    class Status(models.TextChoices):
        ATIVO = "ATIVO", "Ativo"
        AFASTADO = "AFASTADO", "Afastado"
        INATIVO = "INATIVO", "Inativo"

    user = models.OneToOneField(
        "accounts.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="profissional",
    )
    nome_completo = models.CharField(max_length=200)    
    cpf = models.CharField(max_length=14, null=True, blank=True)
    registro_conselho = models.CharField(max_length=30)
    conselho = models.ForeignKey(
        "registry.ConselhoProfissional",
        on_delete=models.PROTECT,
        related_name="profissionais",
    )
    especialidades = models.ManyToManyField(
        "registry.Especialidade",
        related_name="profissionais",
        blank=True,
    )
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ATIVO)
    cor_agenda = models.CharField(max_length=7, default="#3B82F6")
    foto = models.ImageField(upload_to="profissionais/", null=True, blank=True)
    data_admissao = models.DateField(null=True, blank=True)
    observacoes = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Profissional"
        verbose_name_plural = "Profissionais"
        ordering = ["nome_completo"]
        indexes = [models.Index(fields=["status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["cpf"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_profissional_cpf_ativo",
            ),
        ]

    def __str__(self):
        return self.nome_completo


class Disponibilidade(TimeStampedModel):
    class Tipo(models.TextChoices):
        RECORRENTE = "RECORRENTE", "Recorrente"
        ESPECIFICA = "ESPECIFICA", "Específica"

    profissional = models.ForeignKey(
        Profissional,
        on_delete=models.CASCADE,
        related_name="disponibilidades",
    )
    dia_semana = models.PositiveSmallIntegerField(help_text="1=Segunda ... 7=Domingo")
    hora_inicio = models.TimeField()
    hora_fim = models.TimeField()
    intervalo_minutos = models.PositiveSmallIntegerField(default=30)
    sala_padrao = models.ForeignKey(
        "clinic.Sala",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disponibilidades",
    )
    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.RECORRENTE)
    data_inicio = models.DateField(null=True, blank=True)
    data_fim = models.DateField(null=True, blank=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Disponibilidade"
        verbose_name_plural = "Disponibilidades"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(hora_fim__gt=models.F("hora_inicio")),
                name="ck_disponibilidade_horario",
            ),
            models.UniqueConstraint(
                fields=["profissional", "dia_semana", "hora_inicio", "tipo"],
                name="uq_disponibilidade_regra",
            ),
        ]

    def __str__(self):
        return f"{self.profissional} - dia {self.dia_semana} {self.hora_inicio}-{self.hora_fim}"


    DIAS = {
        1: "Segunda-feira", 2: "Terça-feira", 3: "Quarta-feira",
        4: "Quinta-feira", 5: "Sexta-feira", 6: "Sábado", 7: "Domingo",
    }

    @property
    def dia_semana_label(self):
        return self.DIAS.get(self.dia_semana, str(self.dia_semana))
    
class Ausencia(TimeStampedModel):
    class Tipo(models.TextChoices):
        FERIAS = "FERIAS", "Férias"
        LICENCA = "LICENCA", "Licença"
        FOLGA = "FOLGA", "Folga"
        AFASTAMENTO = "AFASTAMENTO", "Afastamento"
        OUTRO = "OUTRO", "Outro"

    profissional = models.ForeignKey(
        Profissional,
        on_delete=models.CASCADE,
        related_name="ausencias",
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.FERIAS)
    data_inicio = models.DateField()
    data_fim = models.DateField()
    observacoes = models.TextField(null=True, blank=True)
    aprovado_por = models.ForeignKey(
        "accounts.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ausencias_aprovadas",
    )

    class Meta:
        verbose_name = "Ausência"
        verbose_name_plural = "Ausências"
        indexes = [models.Index(fields=["profissional", "data_inicio", "data_fim"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(data_fim__gte=models.F("data_inicio")),
                name="ck_ausencia_periodo",
            ),
        ]

    def __str__(self):
        return f"{self.profissional} - {self.tipo} ({self.data_inicio} a {self.data_fim})"
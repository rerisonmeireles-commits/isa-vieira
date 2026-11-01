from django.db import models


class Especialidade(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    descricao = models.TextField(null=True, blank=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Especialidade"
        verbose_name_plural = "Especialidades"

    def __str__(self):
        return self.nome


class ConselhoProfissional(models.Model):
    sigla = models.CharField(max_length=20, unique=True)  # CREFITO-3, CRM, ...
    nome = models.CharField(max_length=150, null=True, blank=True)
    uf = models.CharField(max_length=2, null=True, blank=True)

    class Meta:
        verbose_name = "Conselho Profissional"
        verbose_name_plural = "Conselhos Profissionais"

    def __str__(self):
        return self.sigla


class Feriado(models.Model):
    class Tipo(models.TextChoices):
        NACIONAL = "NACIONAL", "Nacional"
        ESTADUAL = "ESTADUAL", "Estadual"
        MUNICIPAL = "MUNICIPAL", "Municipal"

    data = models.DateField()
    descricao = models.CharField(max_length=150)
    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.NACIONAL)
    uf = models.CharField(max_length=2, null=True, blank=True)
    municipio = models.CharField(max_length=100, null=True, blank=True)
    recorrente = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Feriado"
        verbose_name_plural = "Feriados"
        ordering = ["data"]
        # Nota: NULLs não colidem no PostgreSQL - feriados nacionais podem se repetir
        # com o mesmo (data, NULL, NULL); a unicidade efetiva é validada no service layer.
        constraints = [
            models.UniqueConstraint(fields=["data", "uf", "municipio"], name="uq_feriado_data_local"),
        ]

    def __str__(self):
        return f"{self.descricao} - {self.data}"
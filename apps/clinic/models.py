from django.db import models

from apps.base import SoftDeleteModel, TimeStampedModel

class Clinica(TimeStampedModel):
    nome_fantasia = models.CharField(max_length=200)
    razao_social = models.CharField(max_length=200, null=True, blank=True)
    cnpj = models.CharField(max_length=18, unique=True)
    inscricao_estadual = models.CharField(max_length=20, null=True, blank=True)
    logradouro = models.CharField(max_length=200, null=True, blank=True)
    numero = models.CharField(max_length=10, null=True, blank=True)
    complemento = models.CharField(max_length=100, null=True, blank=True)
    bairro = models.CharField(max_length=100, null=True, blank=True)
    cidade = models.CharField(max_length=100, null=True, blank=True)
    uf = models.CharField(max_length=2, null=True, blank=True)
    cep = models.CharField(max_length=9, null=True, blank=True)
    telefone = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    logo = models.ImageField(upload_to="clinica/logo/", null=True, blank=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Clínica"
        verbose_name_plural = "Clínicas"

    def __str__(self):
        return self.nome_fantasia


class Configuracao(TimeStampedModel):
    clinica = models.OneToOneField(Clinica, on_delete=models.CASCADE, related_name="configuracao")
    hora_abertura = models.TimeField(default="08:00")
    hora_fechamento = models.TimeField(default="18:00")
    duracao_padrao_minutos = models.PositiveSmallIntegerField(default=45)
    intervalo_padrao_minutos = models.PositiveSmallIntegerField(default=15)
    politica_cancelamento_horas = models.PositiveSmallIntegerField(default=24)
    dias_max_antecedencia = models.PositiveSmallIntegerField(default=30)
    permite_agendamento_online = models.BooleanField(default=True)
    mensagem_boas_vindas = models.TextField(null=True, blank=True)
    mensagem_lembrete = models.TextField(null=True, blank=True)
    uf = models.CharField(
        max_length=2, default="SP",
        help_text="UF da clínica - usada para casar feriados estaduais/municipais",
    )
    
    class Meta:
        verbose_name = "Configuração"
        verbose_name_plural = "Configurações"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(hora_fechamento__gt=models.F("hora_abertura")),
                name="ck_configuracao_horario",
            ),
        ]

    def __str__(self):
        return f"Configuração - {self.clinica}"


class Sala(SoftDeleteModel):
    class Status(models.TextChoices):
        ATIVA = "ATIVA", "Ativa"
        INATIVA = "INATIVA", "Inativa"
        MANUTENCAO = "MANUTENCAO", "Manutenção"

    nome = models.CharField(max_length=100)
    descricao = models.CharField(max_length=255, null=True, blank=True)
    capacidade = models.PositiveSmallIntegerField(default=1)
    equipamentos = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ATIVA)
    cor = models.CharField(max_length=7, default="#10B981")

    class Meta:
        verbose_name = "Sala"
        verbose_name_plural = "Salas"

        models.UniqueConstraint(
            fields=["nome"],
            condition=models.Q(deleted_at__isnull=True),
            name="uq_sala_nome_ativo",
        ),        

    def __str__(self):
        return self.nome


class TipoAtendimento(SoftDeleteModel):
    nome = models.CharField(max_length=100)
    descricao = models.CharField(max_length=255, null=True, blank=True)
    duracao_minutos = models.PositiveSmallIntegerField(default=45)
    valor_padrao = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cor = models.CharField(max_length=7, null=True, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tipo de Atendimento"
        verbose_name_plural = "Tipos de Atendimento"

        models.UniqueConstraint(
            fields=["nome"],
            condition=models.Q(deleted_at__isnull=True),
            name="uq_tipo_atendimento_nome_ativo",
        ),

    def __str__(self):
        return self.nome
from django.db import models
from django.utils import timezone

from apps.base import SoftDeleteModel


class ContaReceber(SoftDeleteModel):
    class Tipo(models.TextChoices):
        CONSULTA = "CONSULTA", "Consulta"
        SESSAO = "SESSAO", "Sessão"
        PACOTE = "PACOTE", "Pacote"
        OUTROS = "OUTROS", "Outros"

    class Status(models.TextChoices):
        ABERTA = "ABERTA", "Aberta"
        PAGA = "PAGA", "Paga"
        PARCIAL = "PARCIAL", "Parcial"
        ATRASADA = "ATRASADA", "Atrasada"
        CANCELADA = "CANCELADA", "Cancelada"

    paciente = models.ForeignKey(
        "patients.Paciente",
        on_delete=models.PROTECT,
        related_name="contas_receber",
    )
    convenio = models.ForeignKey(
        "insurance.Convenio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contas_receber",
    )
    agendamento = models.ForeignKey(
        "scheduling.Agendamento",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contas_receber",
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.SESSAO)
    descricao = models.CharField(max_length=255, null=True, blank=True)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)
    parcelas = models.PositiveSmallIntegerField(default=1)
    data_vencimento = models.DateField()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ABERTA)
    forma_pagamento = models.CharField(max_length=20, null=True, blank=True)
    criado_por = models.ForeignKey(
        "accounts.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contas_criadas",
    )

    faturamento = models.ForeignKey(
        "Faturamento",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contas_faturadas",
        verbose_name="lote de faturamento",
    )

    class Meta:
        verbose_name = "Conta a Receber"
        verbose_name_plural = "Contas a Receber"
        indexes = [
            models.Index(fields=["paciente", "status"]),
            models.Index(fields=["data_vencimento"]),
            models.Index(fields=["convenio", "status"], name="ix_conta_convenio_status"),            
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valor_total__gte=0),
                name="ck_conta_valor",
            ),
        ]

    def __str__(self):
        return f"{self.descricao or self.tipo} - {self.valor_total} ({self.status})"


class Pagamento(SoftDeleteModel):
    class Forma(models.TextChoices):
        DINHEIRO = "DINHEIRO", "Dinheiro"
        PIX = "PIX", "PIX"
        CARTAO_DEBITO = "CARTAO_DEBITO", "Cartão de Débito"
        CARTAO_CREDITO = "CARTAO_CREDITO", "Cartão de Crédito"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferência"
        BOLETO = "BOLETO", "Boleto"
        OUTRO = "OUTRO", "Outro"

    class Status(models.TextChoices):
        APROVADO = "APROVADO", "Aprovado"
        PENDENTE = "PENDENTE", "Pendente"
        RECUSADO = "RECUSADO", "Recusado"
        ESTORNADO = "ESTORNADO", "Estornado"

    conta_receber = models.ForeignKey(
        ContaReceber,
        on_delete=models.PROTECT,
        related_name="pagamentos",
    )
    valor = models.DecimalField(max_digits=10, decimal_places=2)    
    data_pagamento = models.DateTimeField(default=timezone.now, verbose_name="data do pagamento")    
    forma = models.CharField(max_length=20, choices=Forma.choices)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.APROVADO)
    recebido_por = models.ForeignKey(
        "accounts.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagamentos_recebidos",
    )
    comprovante = models.FileField(upload_to="financeiro/comprovantes/", null=True, blank=True)
    observacoes = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Pagamento"
        verbose_name_plural = "Pagamentos"
        indexes = [models.Index(fields=["conta_receber"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valor__gt=0),
                name="ck_pagamento_valor",
            ),
        ]

    def __str__(self):
        return f"{self.forma} - {self.valor}"


class Faturamento(SoftDeleteModel):
    class Status(models.TextChoices):
        EMITIDO = "EMITIDO", "Emitido"
        ENVIADO = "ENVIADO", "Enviado"
        PAGO = "PAGO", "Pago"
        PARCIAL = "PARCIAL", "Parcial"
        CANCELADO = "CANCELADO", "Cancelado"

    convenio = models.ForeignKey(
        "insurance.Convenio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="faturamentos",
    )
    periodo_inicio = models.DateField()
    periodo_fim = models.DateField()
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    guias_enviadas = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.EMITIDO)
    observacoes = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Faturamento"
        verbose_name_plural = "Faturamentos"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(periodo_fim__gte=models.F("periodo_inicio")),
                name="ck_faturamento_periodo",
            ),
        ]

    def __str__(self):
        return f"Faturamento {self.periodo_inicio} a {self.periodo_fim}"
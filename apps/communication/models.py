from django.db import models


class Mensagem(models.Model):
    class Canal(models.TextChoices):
        INTERNO = "INTERNO", "Interno"
        EMAIL = "EMAIL", "E-mail"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    class Status(models.TextChoices):
        ENVIADA = "ENVIADA", "Enviada"
        ENTREGUE = "ENTREGUE", "Entregue"
        LIDA = "LIDA", "Lida"
        FALHOU = "FALHOU", "Falhou"

    remetente = models.ForeignKey(
        "accounts.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mensagens_enviadas",
    )
    destinatario = models.ForeignKey(
        "accounts.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mensagens_recebidas",
    )
    paciente = models.ForeignKey(
        "patients.Paciente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mensagens",
    )
    canal = models.CharField(max_length=15, choices=Canal.choices, default=Canal.INTERNO)
    assunto = models.CharField(max_length=200, null=True, blank=True)
    corpo = models.TextField()
    data_envio = models.DateTimeField(auto_now_add=True)
    data_leitura = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ENVIADA)    
    created_at = models.DateTimeField(auto_now_add=True)   # ← NOVO (spec 3.14.1)

    class Meta:
        verbose_name = "Mensagem"
        verbose_name_plural = "Mensagens"
        ordering = ["-data_envio"]
        indexes = [models.Index(fields=["destinatario", "-data_envio"])]
        constraints = [                                    # ← NOVO (spec 1.4)
            models.CheckConstraint(
                condition=models.Q(canal__in=["INTERNO", "EMAIL", "WHATSAPP"]),
                name="mensagem_canal_check",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["ENVIADA", "ENTREGUE", "LIDA", "FALHOU"]),
                name="mensagem_status_check",
            ),
        ]

    def __str__(self):
        return f"{self.assunto or 'Mensagem'} - {self.data_envio}"


class Notificacao(models.Model):
    class Tipo(models.TextChoices):
        AGENDAMENTO = "AGENDAMENTO", "Agendamento"
        CANCELAMENTO = "CANCELAMENTO", "Cancelamento"
        REMARCACAO = "REMARCACAO", "Remarcação"
        LEMBRETE = "LEMBRETE", "Lembrete"
        EXERCICIO_PRESCRITO = "EXERCICIO_PRESCRITO", "Exercício Prescrito"
        COBRANCA = "COBRANCA", "Cobrança"
        DOCUMENTO = "DOCUMENTO", "Documento"
        SISTEMA = "SISTEMA", "Sistema"

    class Canal(models.TextChoices):
        IN_APP = "IN_APP", "In-App"
        EMAIL = "EMAIL", "E-mail"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    destinatario = models.ForeignKey(
        "accounts.Usuario",
        on_delete=models.CASCADE,
        related_name="notificacoes",
    )
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    titulo = models.CharField(max_length=200)
    mensagem = models.TextField()
    link_url = models.CharField(max_length=255, null=True, blank=True)
    agendamento = models.ForeignKey(
        "scheduling.Agendamento",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notificacoes",
    )
    prescricao = models.ForeignKey(
        "exercise.Prescricao",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notificacoes",
    )
    canal = models.CharField(max_length=15, choices=Canal.choices, default=Canal.IN_APP)
    lida = models.BooleanField(default=False)
    data_lida = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notificação"
        verbose_name_plural = "Notificações"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["destinatario", "lida"]),
            models.Index(fields=["destinatario", "-created_at"]),
        ]

        constraints = [                                    # ← NOVO (spec 1.4)
            models.CheckConstraint(
                condition=models.Q(tipo__in=[
                    "AGENDAMENTO", "CANCELAMENTO", "REMARCACAO", "LEMBRETE",
                    "EXERCICIO_PRESCRITO", "COBRANCA", "DOCUMENTO", "SISTEMA",
                ]),
                name="notificacao_tipo_check",
            ),
            models.CheckConstraint(
                condition=models.Q(canal__in=["IN_APP", "EMAIL", "WHATSAPP"]),
                name="notificacao_canal_check",
            ),
        ]        

    def __str__(self):
        return f"{self.titulo} - {self.destinatario}"
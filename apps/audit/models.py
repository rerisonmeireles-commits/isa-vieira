from django.db import models


class LogAuditoria(models.Model):
    class Acao(models.TextChoices):
        CREATE = "CREATE", "Criação"
        UPDATE = "UPDATE", "Atualização"
        DELETE = "DELETE", "Exclusão"
        LOGIN = "LOGIN", "Login"
        LOGOUT = "LOGOUT", "Logout"
        LOGIN_FALHO = "LOGIN_FALHO", "Login Falho"
        ACESSO_PRONTUARIO = "ACESSO_PRONTUARIO", "Acesso a Prontuário"
        EXPORTACAO = "EXPORTACAO", "Exportação"

    usuario = models.ForeignKey(
        "accounts.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs_auditoria",
    )
    acao = models.CharField(max_length=20, choices=Acao.choices)
    tabela = models.CharField(max_length=100)
    registro_id = models.BigIntegerField()
    dados_antes = models.JSONField(null=True, blank=True)   # JSONB no PostgreSQL
    dados_depois = models.JSONField(null=True, blank=True)  # JSONB no PostgreSQL
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    motivo = models.CharField(max_length=255, null=True, blank=True)
    data_hora = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Log de Auditoria"
        verbose_name_plural = "Logs de Auditoria"
        ordering = ["-data_hora"]
        indexes = [
            models.Index(fields=["tabela", "registro_id"]),
            models.Index(fields=["usuario", "-data_hora"]),
            models.Index(fields=["acao", "data_hora"]),
        ]

    def __str__(self):
        return f"{self.acao} em {self.tabela}#{self.registro_id}"
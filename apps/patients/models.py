import uuid

from django.db import models
from django.utils import timezone
from apps.base import SoftDeleteModel

class Paciente(SoftDeleteModel):
    class Sexo(models.TextChoices):
        MASCULINO = "M", "Masculino"
        FEMININO = "F", "Feminino"
        OUTRO = "O", "Outro"

    class Origem(models.TextChoices):
        PARTICULAR = "PARTICULAR", "Particular"
        CONVENIO = "CONVENIO", "Convênio"

    class Status(models.TextChoices):
        ATIVO = "ATIVO", "Ativo"
        INATIVO = "INATIVO", "Inativo"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.OneToOneField(
        "accounts.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paciente",
    )
    nome_completo = models.CharField(max_length=200)
    data_nascimento = models.DateField(null=True, blank=True)
    sexo = models.CharField(max_length=1, choices=Sexo.choices, null=True, blank=True)
    cpf = models.CharField(max_length=14, null=True, blank=True)
    rg = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    telefone = models.CharField(max_length=20, null=True, blank=True)
    estado_civil = models.CharField(max_length=20, null=True, blank=True)
    profissao = models.CharField(max_length=100, null=True, blank=True)
    origem = models.CharField(max_length=15, choices=Origem.choices, default=Origem.PARTICULAR)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ATIVO)
    observacoes = models.TextField(null=True, blank=True)

    @property
    def idade(self):
        """Idade em anos completos (None se a data de nascimento não foi informada)."""
        if not self.data_nascimento:
            return None
        hoje = timezone.localdate()
        return hoje.year - self.data_nascimento.year - (
            (hoje.month, hoje.day) < (self.data_nascimento.month, self.data_nascimento.day)
        )
    
    class Meta:
        verbose_name = "Paciente"
        verbose_name_plural = "Pacientes"
        ordering = ["nome_completo"]
        indexes = [
            models.Index(fields=["nome_completo"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            # Índice único parcial: permite reutilizar o CPF apenas se o registro
            # antigo foi soft-deletado (deleted_at preenchido).
            models.UniqueConstraint(
                fields=["cpf"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_paciente_cpf_ativo",
            ),
        ]

    def __str__(self):
        return self.nome_completo


class Endereco(models.Model):
    class Tipo(models.TextChoices):
        RESIDENCIAL = "RESIDENCIAL", "Residencial"
        COMERCIAL = "COMERCIAL", "Comercial"
        OUTRO = "OUTRO", "Outro"

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="enderecos")
    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.RESIDENCIAL)
    logradouro = models.CharField(max_length=200)
    numero = models.CharField(max_length=10, null=True, blank=True)
    complemento = models.CharField(max_length=100, null=True, blank=True)
    bairro = models.CharField(max_length=100, null=True, blank=True)
    cidade = models.CharField(max_length=100)
    uf = models.CharField(max_length=2 )
    cep = models.CharField(max_length=9, null=True, blank=True)
    is_principal = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Endereço"
        verbose_name_plural = "Endereços"

    def __str__(self):
        return f"{self.logradouro}, {self.numero} - {self.cidade}/{self.uf}"


class Contato(models.Model):
    class Tipo(models.TextChoices):
        TELEFONE = "TELEFONE", "Telefone"
        EMAIL = "EMAIL", "E-mail"
        WHATSAPP = "WHATSAPP", "WhatsApp" 
        OUTRO = "OUTRO", "Outro"

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="contatos")
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    valor = models.CharField(max_length=150)
    is_principal = models.BooleanField(default=False)
    observacoes = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = "Contato"
        verbose_name_plural = "Contatos"

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.valor}"


class ContatoEmergencia(models.Model):
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="contatos_emergencia")
    nome = models.CharField(max_length=200)
    parentesco = models.CharField(max_length=50, null=True, blank=True)
    telefone = models.CharField(max_length=20)
    observacoes = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = "Contato de Emergência"
        verbose_name_plural = "Contatos de Emergência"

    def __str__(self):
        return f"{self.nome} ({self.telefone})"
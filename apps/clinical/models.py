import uuid

from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator

from apps.base import SoftDeleteModel


class Prontuario(SoftDeleteModel):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    paciente = models.OneToOneField(
        "patients.Paciente",
        on_delete=models.PROTECT,
        related_name="prontuario",
    )
    data_abertura = models.DateField(auto_now_add=True)
    alergias = models.TextField(null=True, blank=True)
    medicamentos_em_uso = models.TextField(null=True, blank=True)
    condicoes_cronicas = models.TextField(null=True, blank=True)
    historico_clinico = models.TextField(null=True, blank=True)
    observacoes = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Prontuário"
        verbose_name_plural = "Prontuários"

    def __str__(self):
        return f"Prontuário de {self.paciente}"


class Avaliacao(SoftDeleteModel):
    class Tipo(models.TextChoices):
        INICIAL = "INICIAL", "Inicial"
        REAVALIACAO = "REAVALIACAO", "Reavaliação"
        REAVALIACAO_ALTA = "REAVALIACAO_ALTA", "Reavaliação de Alta"

    class Status(models.TextChoices):
        LIBERADA = "L", "Liberada"
        PENDENTE = "P", "Pendente de Liberação"
        INATIVADA = "I", "Inativada"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    paciente = models.ForeignKey(
        "patients.Paciente",
        on_delete=models.PROTECT,
        related_name="avaliacoes",
    )
    profissional = models.ForeignKey(
        "professionals.Profissional",
        on_delete=models.PROTECT,
        related_name="avaliacoes",
    )
    atendimento = models.ForeignKey(
        "attendance.Atendimento",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="avaliacoes",
    )
    data = models.DateField(auto_now_add=True)
    tipo = models.CharField(max_length=25, choices=Tipo.choices, default=Tipo.INICIAL)
    status = models.CharField(max_length=1, choices=Status.choices, default=Status.PENDENTE)
    queixa_principal = models.TextField(null=True, blank=True)
    historia_doenca_atual = models.TextField(null=True, blank=True)
    historia_pregressa = models.TextField(null=True, blank=True)
    medicamentos_em_uso = models.TextField(null=True, blank=True)
    exame_fisico = models.TextField(null=True, blank=True)
    escalas_eva_dor = models.PositiveSmallIntegerField(validators=[MinValueValidator(0), MaxValueValidator(10)], null=True, blank=True)        
    goniometria = models.TextField(null=True, blank=True)
    hipotese_diagnostica = models.TextField(null=True, blank=True)
    conduta = models.TextField(null=True, blank=True)
    plano_terapeutico = models.TextField(null=True, blank=True)
    objetivo_curto_prazo = models.TextField(null=True, blank=True)
    objetivo_longo_prazo = models.TextField(null=True, blank=True)
    liberado_por = models.ForeignKey(
        "accounts.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="avaliacoes_liberadas",
    )
    liberado_em = models.DateTimeField(null=True, blank=True)
    inativado_por = models.ForeignKey(
        "accounts.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="avaliacoes_inativadas",
    )
    inativado_em = models.DateTimeField(null=True, blank=True)
    observacoes = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Avaliação"
        verbose_name_plural = "Avaliações"
        indexes = [models.Index(fields=["paciente", "data"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(escalas_eva_dor__gte=0, escalas_eva_dor__lte=10),
                name="ck_avaliacao_eva",
            ),
            # Novas: garantem rastreio de quem liberou/inativou
            models.CheckConstraint(
                condition=(
                    models.Q(status="L", liberado_por__isnull=False, liberado_em__isnull=False)
                    | ~models.Q(status="L")
                ),
                name="ck_avaliacao_liberada_com_rastreio",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="I", inativado_por__isnull=False, inativado_em__isnull=False)
                    | ~models.Q(status="I")
                ),
                name="ck_avaliacao_inativada_com_rastreio",
            ),
        ]

    @property
    def fim_motor_total(self):
        return sum(i.pontuacao or 0 for i in self.itens_fim.filter(dominio=FimItem.Dominio.MOTOR))

    @property
    def fim_cognitivo_total(self):
        return sum(i.pontuacao or 0 for i in self.itens_fim.filter(dominio=FimItem.Dominio.COGNITIVO))

    @property
    def fim_total(self):
        return self.fim_motor_total + self.fim_cognitivo_total

    @property
    def goniometria_resumo(self):
        """Resumo em texto - derivado das medições, nunca digitado."""
        linhas = [
            f"{m.get_articulacao_display()} · {m.get_movimento_display()} · "
            f"{m.get_lado_display()}: {m.graus}°"
            for m in self.medicoes_goniometria.all()
        ]
        return "\n".join(linhas) or "-"


    def __str__(self):
        return f"Avaliação {self.paciente} - {self.data} ({self.status})"


class Evolucao(SoftDeleteModel):
    class Status(models.TextChoices):
        LIBERADA = "L", "Liberada"
        PENDENTE = "P", "Pendente de Liberação"
        INATIVADA = "I", "Inativada"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    paciente = models.ForeignKey(
        "patients.Paciente",
        on_delete=models.PROTECT,
        related_name="evolucoes",
    )
    profissional = models.ForeignKey(
        "professionals.Profissional",
        on_delete=models.PROTECT,
        related_name="evolucoes",
    )
    # Posse: a sessão à qual esta evolução pertence.
    atendimento = models.ForeignKey(
        "attendance.Atendimento",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="evolucoes",
    )

    # SOAP
    subjetivo = models.TextField(null=True, blank=True)
    objetivo = models.TextField(null=True, blank=True)
    avaliacao = models.TextField(null=True, blank=True)
    plano = models.TextField(null=True, blank=True)
    
    #PADRONIZAÇÃO DE MODELOS: status, liberado_por, liberado_em, inativado_por, inativado_em
    status = models.CharField(max_length=1, choices=Status.choices, default=Status.PENDENTE)
    liberado_por = models.ForeignKey(
        "accounts.Usuario", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="evolucoes_liberadas",
    )
    liberado_em = models.DateTimeField(null=True, blank=True)
    inativado_por = models.ForeignKey(
        "accounts.Usuario", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="evolucoes_inativadas",
    )
    inativado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Evolução"
        verbose_name_plural = "Evoluções"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["paciente", "created_at"]),
            models.Index(fields=["atendimento"]),
        ]

    def __str__(self):
        return f"Evolução {self.paciente} - {self.created_at:%d/%m/%Y}"

class FimItem(models.Model):
    """Pontuação item a item da escala FIM (18 itens, 1–7 cada)."""

    class Dominio(models.TextChoices):
        MOTOR = "MOTOR", "Motor"
        COGNITIVO = "COGNITIVO", "Cognitivo"

    class Item(models.TextChoices):
        # Motor (13)
        ALIMENTACAO = "ALIMENTACAO", "Alimentação"
        HIGIENE = "HIGIENE", "Cuidados pessoais (higiene)"
        BANHO = "BANHO", "Banho"
        VESTIR_SUPERIOR = "VESTIR_SUP", "Vestir parte superior"
        VESTIR_INFERIOR = "VESTIR_INF", "Vestir parte inferior"
        TOALETE = "TOALETE", "Toalete (higiene íntima)"
        ESFINCTER_BEXIGA = "ESF_BEXIGA", "Controle esfíncter - bexiga"
        ESFINCTER_INTESTINO = "ESF_INTEST", "Controle esfíncter - intestino"
        TRANS_CAMA = "TRANS_CAMA", "Transferência cama/cadeira"
        TRANS_VASO = "TRANS_VASO", "Transferência vaso sanitário"
        TRANS_BANHO = "TRANS_BANHO", "Transferência banho/chuveiro"
        LOCOMOCAO = "LOCOMOCAO", "Locomoção (caminhar/rodas)"
        ESCADAS = "ESCADAS", "Escadas"
        # Cognitivo (5)
        COMPREENSAO = "COMPREENSAO", "Compreensão"
        EXPRESSAO = "EXPRESSAO", "Expressão"
        INTERACAO = "INTERACAO", "Interação social"
        PROBLEMAS = "PROBLEMAS", "Resolução de problemas"
        MEMORIA = "MEMORIA", "Memória"

    avaliacao = models.ForeignKey(
        "clinical.Avaliacao", on_delete=models.PROTECT,
        related_name="itens_fim",
    )
    item = models.CharField(max_length=20, choices=Item.choices)
    dominio = models.CharField(max_length=10, choices=Dominio.choices)
    pontuacao = models.PositiveSmallIntegerField(null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(7)],
        help_text="1 = assistência total · 7 = independência completa",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["avaliacao", "item"], name="ck_fim_item_unico"
            ),
        ]

    def __str__(self):
        return f"{self.get_item_display()}: {self.pontuacao}"


class GoniometriaMedicao(models.Model):
    class Articulacao(models.TextChoices):
        OMBRO = "OMBRO", "Ombro"
        COTOVELO = "COTOVELO", "Cotovelo"
        PUNHO = "PUNHO", "Punho"
        QUADRIL = "QUADRIL", "Quadril"
        JOELHO = "JOELHO", "Joelho"
        TORNOZELO = "TORNOZELO", "Tornozelo"
        COLUNA_CERVICAL = "COL_CERV", "Coluna Cervical"
        COLUNA_TORACICA = "COL_TORAC", "Coluna Torácica"
        COLUNA_LOMBAR = "COL_LOMBAR", "Coluna Lombar"

    class Movimento(models.TextChoices):
        FLEXAO = "FLEXAO", "Flexão"
        EXTENSAO = "EXTENSAO", "Extensão"
        ABDUCAO = "ABDUCAO", "Abdução"
        ADUCAO = "ADUCAO", "Adução"
        ROTACAO_INTERNA = "RI", "Rotação Interna"
        ROTACAO_EXTERNA = "RE", "Rotação Externa"
        DORSIFLEXAO = "DORSIFLEX", "Dorsiflexão"
        FLEXAO_PLANTAR = "FLEX_PLANT", "Flexão Plantar"
        INCLINACAO_LATERAL = "INCL_LAT", "Inclinação Lateral"
        ROTACAO = "ROTACAO", "Rotação"

    class Lado(models.TextChoices):
        DIREITO = "D", "Direito"
        ESQUERDO = "E", "Esquerdo"

    avaliacao = models.ForeignKey(
        "clinical.Avaliacao", on_delete=models.PROTECT,
        related_name="medicoes_goniometria",
    )
    articulacao = models.CharField(max_length=20, choices=Articulacao.choices)
    movimento = models.CharField(max_length=20, choices=Movimento.choices)
    lado = models.CharField(max_length=1, choices=Lado.choices)
    graus = models.PositiveSmallIntegerField(validators=[MaxValueValidator(360)])
    observacao = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["avaliacao", "articulacao", "movimento", "lado"],
                name="ck_goniometria_unico",
            ),
        ]
        ordering = ["articulacao", "movimento", "lado"]

    def __str__(self):
        return f"{self.articulacao}/{self.movimento} ({self.get_lado_display()}): {self.graus}°"    
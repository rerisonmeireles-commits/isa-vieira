import uuid
from datetime import date, datetime, timedelta

from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.base import (
    SoftDeleteManager,
    SoftDeleteModel,
    SoftDeleteQuerySet,
    TimeStampedModel,
)


class Agenda(TimeStampedModel):
    class Status(models.TextChoices):
        GERADA = "GERADA", "Gerada"
        BLOQUEADA = "BLOQUEADA", "Bloqueada"
        FINALIZADA = "FINALIZADA", "Finalizada"
        SEM_EXPEDIENTE = "SEM_EXPEDIENTE", "Sem expediente"

    profissional = models.ForeignKey(
        "professionals.Profissional",
        on_delete=models.CASCADE,
        related_name="agendas",
    )
    data = models.DateField()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.GERADA)
    excecao_feriado = models.BooleanField(
        default=False,
        help_text="Clínica decidiu funcionar neste feriado (decisão pontual)",
    )

    class Meta:
        verbose_name = "Agenda"
        verbose_name_plural = "Agendas"
        ordering = ["data"]
        indexes = [
            # Janela do wizard/grade: WHERE data BETWEEN ... AND status = ...
            models.Index(fields=["data", "status"], name="ix_agenda_data_status"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["profissional", "data"], name="uq_agenda_prof_data"),
        ]

    def __str__(self):
        return f"{self.profissional} - {self.data}"


class SlotAgenda(TimeStampedModel):
    class Status(models.TextChoices):
        LIVRE = "LIVRE", "Livre"
        OCUPADO = "OCUPADO", "Ocupado"
        BLOQUEADO = "BLOQUEADO", "Bloqueado"
        INDISPONIVEL = "INDISPONIVEL", "Indisponível"

    agenda = models.ForeignKey(Agenda, on_delete=models.CASCADE, related_name="slots")
    origem_disponibilidade = models.ForeignKey(
        "professionals.Disponibilidade",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="slots",
    )
    hora_inicio = models.TimeField()
    hora_fim = models.TimeField()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.LIVRE)

    class Meta:
        verbose_name = "Slot de Agenda"
        verbose_name_plural = "Slots de Agenda"
        ordering = ["hora_inicio"]
        indexes = [models.Index(fields=["agenda", "status"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(hora_fim__gt=models.F("hora_inicio")),
                name="ck_slot_hora_valida",
            ),
            models.UniqueConstraint(
                fields=["agenda", "hora_inicio"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_slot_agenda_hora",
            ),
        ]

    @property
    def agendamento_ativo(self):
        """Agendamento vigente do slot, considerando FK principal E bloco M2M.

        O cache só é usado quando AMBOS os prefetches foram aplicados
        (`_agendamentos_ativos` e `_agendamentos_bloco`). Um cache parcial
        esconderia slots secundários de reservas multi-slot.

        Os dois caminhos precisam devolver o MESMO registro. O prefetch herda
        Meta.ordering (["-created_at"]), ou seja, o mais recente primeiro - por
        isso o cache é reordenado explicitamente em vez de usar lista[0]. E o
        de-dup por pk é obrigatório: o slot principal de uma reserva multi-slot
        aparece na FK E no M2M.
        """
        fk = getattr(self, "_agendamentos_ativos", None)
        bloco = getattr(self, "_agendamentos_bloco", None)
        if fk is not None and bloco is not None:
            unicos = {ag.pk: ag for ag in list(fk) + list(bloco)}
            if not unicos:
                return None
            return min(unicos.values(), key=lambda ag: ag.created_at)
        return (
            Agendamento.objects.filter(
                models.Q(slot_id=self.pk) | models.Q(slots_ocupados__id=self.pk),
                status__in=[
                    Agendamento.Status.AGENDADO,
                    Agendamento.Status.CONFIRMADO,
                    Agendamento.Status.EM_ATENDIMENTO,
                    Agendamento.Status.ATENDIDO,
                    Agendamento.Status.FALTOU,
                ],
            )
            .select_related("paciente")
            .distinct()
            .order_by("created_at")
            .first()
        )


class AgendamentoQuerySet(SoftDeleteQuerySet):
    """Soft delete em massa com liberação dos slots ocupados.

    Delega para Model.liberar_slots(): a definição de "quais slots este
    agendamento ocupa" mora em slots_envolvidos() (FK ∪ M2M). Duas
    implementações divergem com o tempo, e a divergência é silenciosa.
    """

    def delete(self):
        objetos = list(self)
        if not objetos:
            return super().delete()

        # Captura os IDs ANTES: o soft delete não remove os vínculos M2M, mas
        # materializar o mapa evita N queries dentro da transação.
        mapa = {ag.pk: ag.slots_envolvidos() for ag in objetos}
        with transaction.atomic():
            resultado = super().delete()
            # Libera DEPOIS de marcar deleted_at. Com o guard ativo, liberar
            # antes cria impasse: dois agendamentos do mesmo lote que
            # compartilham slot se enxergariam como donos e nenhum liberaria.
            for agendamento in objetos:
                agendamento.liberar_slots(ids=mapa.get(agendamento.pk))
            return resultado

    def restore(self):
        """Restaura em massa, validando TODOS antes de escrever qualquer um.

        Validar dentro do laço de escrita deixaria metade do lote restaurada
        e metade recusada - e ninguém saberia qual é qual. Aqui o lote é
        atômico: um substituto ativo no terceiro item cancela o lote inteiro.

        ATENÇÃO: self está restrito ao manager. Só faz sentido chamar via
        Agendamento.all_objects - com Agendamento.objects o filtro
        deleted_at__isnull=True torna `objetos` sempre vazio e o restore vira
        no-op silencioso em vez de erro.
        """
        objetos = [ag for ag in self if ag.deleted_at is not None]
        if not objetos:
            return super().restore()
        with transaction.atomic():
            mapa = {ag.pk: ag.slots_envolvidos() for ag in objetos}
            for ag in objetos:
                ag._validar_restauracao(mapa[ag.pk])
            resultado = super().restore()
            for ag in objetos:
                ag.deleted_at = None
                campos = []
                if ag.status in ag.STATUS_LIBERAM_SLOT:
                    ag.status = ag.Status.AGENDADO
                    ag.cancelado_por = None
                    ag.motivo_cancelamento = None
                    campos = [
                        "status",
                        "cancelado_por",
                        "motivo_cancelamento",
                        "updated_at",
                    ]
                if campos:
                    ag.save(update_fields=campos, _sincronizar_slots=False)
                ag.ocupar_slots()
            return resultado


class AgendamentoManager(SoftDeleteManager):
    def get_queryset(self):
        return AgendamentoQuerySet(self.model, using=self._db).all().filter(
            deleted_at__isnull=True
        )


class Agendamento(SoftDeleteModel, TimeStampedModel):
    class Status(models.TextChoices):
        AGENDADO = "AGENDADO", "Agendado"
        CONFIRMADO = "CONFIRMADO", "Agendamento Confirmado"
        EM_ATENDIMENTO = "EM_ATENDIMENTO", "Aguardando Atendimento"
        ATENDIDO = "ATENDIDO", "Atendimento Finalizado"
        CANCELADO = "CANCELADO", "Cancelado"
        FALTOU = "FALTOU", "Faltou"
        REMARCADO = "REMARCADO", "Remarcado"

    class Origem(models.TextChoices):
        PORTAL = "PORTAL", "Portal"
        RECEPCAO = "RECEPCAO", "Recepção"
        APP = "APP", "App"
        TELEFONE = "TELEFONE", "Telefone"

    # Status que devolvem os slots para LIVRE ao serem atingidos.
    STATUS_LIBERAM_SLOT = frozenset({Status.CANCELADO, Status.REMARCADO})

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    slot = models.ForeignKey(
        "SlotAgenda",
        on_delete=models.PROTECT,
        related_name="agendamentos",
    )
    slots_ocupados = models.ManyToManyField(
        "SlotAgenda",
        related_name="agendamentos_bloco",
        blank=True,
        help_text="Todos os slots contíguos ocupados (reserva multi-slot).",
    )
    duracao_minutos = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Snapshot da duração do tipo no momento da reserva.",
    )
    paciente = models.ForeignKey(
        "patients.Paciente",
        on_delete=models.PROTECT,
        related_name="agendamentos",
    )
    profissional = models.ForeignKey(
        "professionals.Profissional",
        on_delete=models.PROTECT,
        related_name="agendamentos",
    )
    sala = models.ForeignKey(
        "clinic.Sala",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agendamentos",
    )
    tipo_atendimento = models.ForeignKey(
        "clinic.TipoAtendimento",
        on_delete=models.PROTECT,
        related_name="agendamentos",
    )
    convenio = models.ForeignKey(
        "insurance.Convenio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agendamentos",
    )
    paciente_convenio = models.ForeignKey(
        "insurance.PacienteConvenio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agendamentos",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AGENDADO)
    origem = models.CharField(max_length=20, choices=Origem.choices, default=Origem.RECEPCAO)
    valor = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    observacoes = models.TextField(null=True, blank=True)
    criado_por = models.ForeignKey(
        "accounts.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agendamentos_criados",
    )
    cancelado_por = models.ForeignKey(
        "accounts.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agendamentos_cancelados",
    )
    motivo_cancelamento = models.CharField(max_length=255, null=True, blank=True)
    remarcado_de = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="remarcacoes",
    )
    data_remarcacao = models.DateTimeField(null=True, blank=True)
    lembretes_enviados = models.PositiveSmallIntegerField(default=0)

    objects = AgendamentoManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "Agendamento"
        verbose_name_plural = "Agendamentos"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["paciente", "status"]),
            models.Index(fields=["profissional", "status"]),
        ]
        constraints = [
            # Os literais repetem STATUS_LIBERAM_SLOT porque Meta é um escopo
            # de classe aninhado e não enxerga os atributos do corpo externo.
            # Ao mudar a regra, atualize os dois lugares.
            models.UniqueConstraint(
                fields=["slot"],
                condition=(
                    models.Q(deleted_at__isnull=True)
                    & ~models.Q(status__in=["CANCELADO", "REMARCADO"])
                ),
                name="uq_slot_agendamento_ativo",
            ),
        ]

    # --- Apresentação ------------------------------------------------------
    # Agendamento não guarda data nem hora: o dado vive no slot. Consultas
    # devem usar .select_related("slot__agenda", "tipo_atendimento",
    # "profissional") ou cada property dispara uma query (N+1).

    @property
    def data(self):
        return self.slot.agenda.data if self.slot_id else None

    @property
    def hora_inicio(self):
        return self.slot.hora_inicio if self.slot_id else None

    @property
    def hora_fim(self):
        # Calculado a partir da duração, não de slot.hora_fim: uma sessão pode
        # ocupar vários slots (ver slots_ocupados) e slot.hora_fim marcaria
        # apenas o fim do primeiro.
        #
        # O fallback para tipo_atendimento.duracao_minutos é obrigatório:
        # duracao_minutos é nullable e, sem ele, `or 0` fazia hora_fim igual a
        # hora_inicio - meia hora de sessão exibida como zero, sem erro.
        # _bloco_incompleto já usa este mesmo fallback; ter duas regras para o
        # mesmo dado era a origem da divergência.
        if not self.hora_inicio:
            return None
        duracao = self.duracao_minutos or self.tipo_atendimento.duracao_minutos or 0
        base = datetime.combine(date.min, self.hora_inicio)
        return (base + timedelta(minutes=duracao)).time()

    @property
    def inicio_datetime(self):
        """Início como datetime aware - fonte única para regras de prazo."""
        if not self.data or not self.hora_inicio:
            return None
        return timezone.make_aware(datetime.combine(self.data, self.hora_inicio))

    # --- Status ------------------------------------------------------------

    STATUS_CSS = {
        "AGENDADO": "text-bg-secondary",
        "CONFIRMADO": "text-bg-primary",
        "EM_ATENDIMENTO": "text-bg-info",
        "ATENDIDO": "text-bg-success",
        "CANCELADO": "text-bg-danger",
        "FALTOU": "text-bg-dark",
        "REMARCADO": "text-bg-warning",
    }

    @property
    def status_css(self):
        return self.STATUS_CSS.get(self.status, "text-bg-light border")

    PRAZO_CANCELAMENTO_HORAS = 24

    @property
    def pode_cancelar(self):
        """Regra de prazo no modelo, não no template nem na view."""
        if self.status not in (self.Status.AGENDADO, self.Status.CONFIRMADO):
            return False
        inicio = self.inicio_datetime
        if inicio is None:
            return False
        return inicio - timezone.now() > timedelta(hours=self.PRAZO_CANCELAMENTO_HORAS)

    @property
    def motivo_bloqueio_cancelamento(self):
        """Texto explicativo para o template - evita {% if %} com literais.

        Cada status terminal precisa do seu próprio texto. Sem o branch de
        EM_ATENDIMENTO e REMARCADO o paciente leria o aviso de prazo de 24h
        para uma consulta que já está acontecendo ou que já foi remarcada.
        """
        if self.pode_cancelar:
            return ""
        if self.status == self.Status.CANCELADO:
            return "Esta consulta já foi cancelada."
        if self.status == self.Status.REMARCADO:
            return "Esta consulta foi remarcada. Consulte a nova data."
        if self.status == self.Status.ATENDIDO:
            return "Esta consulta já foi realizada."
        if self.status == self.Status.FALTOU:
            return "Esta consulta foi registrada como falta."
        if self.status == self.Status.EM_ATENDIMENTO:
            return "Esta consulta já está em atendimento."
        return (
            f"Cancelamentos pelo portal só são possíveis até "
            f"{self.PRAZO_CANCELAMENTO_HORAS}h antes do horário."
        )

    def __str__(self):
        return f"{self.paciente} - {self.slot.agenda.data} {self.slot.hora_inicio} ({self.status})"

    # ---------- sincronização de slots ----------

    def slots_envolvidos(self):
        """IDs do slot principal + slots do bloco M2M."""
        ids = set()
        if self.slot_id:
            ids.add(self.slot_id)
        if self.pk:
            ids.update(self.slots_ocupados.values_list("pk", flat=True))
        return ids

    def liberar_slots(self, ids=None):
        """Devolve para LIVRE os slots ocupados por este agendamento.

        Idempotente: só toca slots que ainda estão OCUPADO.

        Guard: um slot compartilhado por OUTRO agendamento ativo não é
        liberado. O M2M slots_ocupados não tem constraint, então dois
        agendamentos ativos podem apontar para o mesmo slot.

        A checagem usa Agendamento.objects (não os related managers reversos)
        por dois motivos: não depende do related_name da FK e herda o filtro
        de soft delete do AgendamentoManager.

        O filtro por STATUS_LIBERAM_SLOT é obrigatório: agendamento cancelado
        ou remarcado MANTÉM os vínculos M2M e a FK (a liberação muda apenas o
        status do slot), então sem esse filtro ele bloquearia a liberação
        indefinidamente.
        """
        alvo = list(ids if ids is not None else self.slots_envolvidos())
        if not alvo:
            return 0
        liberaveis = []
        for pk in alvo:
            qs = (
                Agendamento.objects
                .filter(models.Q(slot_id=pk) | models.Q(slots_ocupados__pk=pk))
                .exclude(status__in=self.STATUS_LIBERAM_SLOT)
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if not qs.exists():
                liberaveis.append(pk)
        if not liberaveis:
            return 0
        return SlotAgenda.objects.filter(
            pk__in=liberaveis, status=SlotAgenda.Status.OCUPADO
        ).update(status=SlotAgenda.Status.LIVRE)

    def ocupar_slots(self):
        """Marca como OCUPADO o slot principal e os do bloco. Idempotente."""
        ids = self.slots_envolvidos()
        if not ids:
            return 0
        return SlotAgenda.objects.filter(
            pk__in=ids, status=SlotAgenda.Status.LIVRE
        ).update(status=SlotAgenda.Status.OCUPADO)

    # ---------- ciclo de vida ----------

    def save(self, *args, **kwargs):
        """Libera slots quando o status transita para CANCELADO/REMARCADO.

        Rede de segurança para caminhos que não passam pelo service layer
        (admin, shell, scripts). Custa 1 query por save de registro existente.
        """
        sincronizar = kwargs.pop("_sincronizar_slots", True)
        liberar = False
        if sincronizar and self.pk:
            anterior = (
                type(self).objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            if (
                anterior
                and anterior not in self.STATUS_LIBERAM_SLOT
                and self.status in self.STATUS_LIBERAM_SLOT
            ):
                liberar = True
        super().save(*args, **kwargs)
        if liberar:
            self.liberar_slots()

    def delete(self, *args, **kwargs):
        """Exclusão unitária liberando slots principal e de bloco.

        Os IDs são capturados ANTES do super(), e a liberação acontece DEPOIS
        do soft delete - o guard consulta Agendamento.objects, que passa a
        excluir este registro e não o contaria como dono concorrente.
        """
        ids = self.slots_envolvidos()
        with transaction.atomic():
            resultado = super().delete(*args, **kwargs)
            self.liberar_slots(ids=ids)
        return resultado

    def _substituto_ativo(self):
        """Agendamento criado por remarcação deste que ainda está vigente.

        O related_name vem da FK remarcado_de. Filtra explicitamente por
        deleted_at mesmo o manager reverso já fazendo isso - a dependência do
        _default_manager é implícita e não sobrevive a uma futura troca de
        manager sem que ninguém perceba.
        """
        if not self.pk:
            return None
        return (
            self.remarcacoes
            .filter(deleted_at__isnull=True)
            .exclude(status__in=self.STATUS_LIBERAM_SLOT)
            .order_by("created_at")
            .first()
        )

    def _slots_indisponiveis(self, ids=None):
        """Slots do conjunto indisponíveis para ocupação.

        Dois critérios, não um: status diferente de LIVRE OU reivindicação
        por outro agendamento não-terminal. O segundo é necessário porque o
        estado órfão legado (slot LIVRE com dono ativo via M2M) não aparece
        no status - e restaurar sobre ele cria M2M compartilhado com registro
        ativo, que a grade resolve por created_at e exibe só um dos dois.
        """
        alvo = list(ids if ids is not None else self.slots_envolvidos())
        if not alvo:
            return []
        ocupados_por_status = set(
            SlotAgenda.objects
            .filter(pk__in=alvo)
            .exclude(status=SlotAgenda.Status.LIVRE)
            .values_list("pk", flat=True)
        )
        reivindicados = set(
            SlotAgenda.objects
            .filter(pk__in=alvo)
            .filter(agendamentos_bloco__in=Agendamento.objects.exclude(
                status__in=self.STATUS_LIBERAM_SLOT))
            .values_list("pk", flat=True)
        )
        suspeitos = sorted(ocupados_por_status | reivindicados)
        return list(
            SlotAgenda.objects.filter(pk__in=suspeitos)
            .order_by("hora_inicio")
            .values_list("hora_inicio", "status")
        )

    def _bloco_incompleto(self, ids=None):
        """True se o vínculo de slots não cobre a duração do atendimento.

        Ressonância do período em que cancelar_agendamento() chamava
        slots_ocupados.clear(): o M2M ficou vazio e slots_envolvidos() passou a
        devolver só a FK. Restaurar esse registro ocuparia 1 slot de um bloco
        de N sem erro algum - corrupção parcial silenciosa.

        Soma as durações dos slots vinculados e compara com a duração do
        atendimento. Não assume granularidade fixa: funciona com slot de 15,
        20, 30 ou 45 minutos.
        """
        duracao = self.duracao_minutos or self.tipo_atendimento.duracao_minutos
        if not duracao:
            return False
        alvo = list(ids if ids is not None else self.slots_envolvidos())
        if not alvo:
            return False
        total = 0
        for hora_inicio, hora_fim in (
            SlotAgenda.objects.filter(pk__in=alvo)
            .values_list("hora_inicio", "hora_fim")
        ):
            total += (
                datetime.combine(date.min, hora_fim)
                - datetime.combine(date.min, hora_inicio)
            ).seconds // 60
        return total < duracao

    def _validar_restauracao(self, ids=None):
        """Verifica os dois invariantes de restauração. Não escreve nada.

        Separado do restore() porque o queryset precisa validar TODOS os
        objetos antes de escrever o primeiro.
        """
        if self._bloco_incompleto(ids):
            raise ValidationError(
                f"Agendamento #{self.pk} tem vínculo de slots incompleto: "
                f"os slots vinculados não cobrem os "
                f"{self.duracao_minutos or self.tipo_atendimento.duracao_minutos} "
                "minutos do atendimento. Reconstrua o bloco antes de restaurar."
            )
        substituto = self._substituto_ativo()
        if substituto:
            raise ValidationError(
                f"Agendamento #{self.pk} foi remarcado e o substituto "
                f"#{substituto.pk} continua ativo em "
                f"{substituto.slot.agenda.data:%d/%m/%Y} "
                f"{substituto.slot.hora_inicio:%H:%M}. "
                "Cancele o substituto antes de restaurar."
            )
        indisponiveis = self._slots_indisponiveis(ids)
        if indisponiveis:
            raise ValidationError(
                "Não é possível restaurar: "
                + ", ".join(
                    f"{hora:%H:%M} ({status})" for hora, status in indisponiveis
                )
                + " já estão ocupados."
            )

    def restore(self, *args, **kwargs):
        """Desfaz o soft delete, reativa o status e reocupa os slots.

        A validação roda ANTES de super().restore(): ele já persiste
        deleted_at=None, e um raise depois disso - fora de transação -
        deixaria o registro restaurado pela metade, com status terminal e sem
        slots. O atomic() garante que qualquer falha desfaça o conjunto.

        Restaurar um REMARCADO cujo substituto foi cancelado é permitido: o
        invariante é o substituto vivo, não o status. Recusar por status
        bloquearia a operação legítima de voltar ao horário original.
        """
        if self.deleted_at is None:
            # restore() em registro vivo não reativa nada.
            return super().restore(*args, **kwargs)
        ids = self.slots_envolvidos()
        with transaction.atomic():
            self._validar_restauracao(ids)
            resultado = super().restore(*args, **kwargs)
            campos = []
            if self.status in self.STATUS_LIBERAM_SLOT:
                self.status = self.Status.AGENDADO
                self.cancelado_por = None
                self.motivo_cancelamento = None
                campos = [
                    "status",
                    "cancelado_por",
                    "motivo_cancelamento",
                    "updated_at",
                ]
            if campos:
                self.save(update_fields=campos, _sincronizar_slots=False)
            self.ocupar_slots()
            return resultado


class BloqueioAgenda(TimeStampedModel):
    class Tipo(models.TextChoices):
        MANUTENCAO = "MANUTENCAO", "Manutenção"
        FOLGA = "FOLGA", "Folga"
        EVENTO = "EVENTO", "Evento"
        FERIADO_INTERNO = "FERIADO_INTERNO", "Feriado Interno"
        OUTRO = "OUTRO", "Outro"

    profissional = models.ForeignKey(
        "professionals.Profissional",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bloqueios",
    )
    sala = models.ForeignKey(
        "clinic.Sala",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bloqueios",
    )
    agenda = models.ForeignKey(
        Agenda,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bloqueios",
    )
    data_inicio = models.DateField()
    hora_inicio = models.TimeField()
    data_fim = models.DateField(null=True, blank=True)
    hora_fim = models.TimeField(null=True, blank=True)
    motivo = models.CharField(max_length=255)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.MANUTENCAO)
    criado_por = models.ForeignKey(
        "accounts.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bloqueios_criados",
    )

    class Meta:
        verbose_name = "Bloqueio de Agenda"
        verbose_name_plural = "Bloqueios de Agenda"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(data_fim__gte=models.F("data_inicio")),
                name="ck_bloqueio_periodo",
            ),
        ]

    def __str__(self):
        return f"{self.motivo} ({self.data_inicio} {self.hora_inicio})"
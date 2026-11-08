import os
import logging
from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from apps.attendance.models import Atendimento
from apps.audit.services import registrar_auditoria
from apps.clinic.models import TipoAtendimento
from apps.clinical.models import Avaliacao, Evolucao
from apps.communication.models import Notificacao
from apps.communication.services import enviar_mensagem
from apps.documents.models import Documento
from apps.exercise.models import Prescricao, ExecucaoExercicio, PrescricaoExercicio
from apps.portal.helpers import portal_required
from apps.portal.mixins import PacienteScopedMixin
from apps.portal.services import PortalAgendaError, reservar_para_paciente
from apps.professionals.models import Profissional
from apps.scheduling.models import Agendamento, Agenda, SlotAgenda
from apps.scheduling.services.geracao_slots import gerar_slots_do_dia

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# HOME
# ─────────────────────────────────────────────────────────────

@portal_required
def home(request):
    paciente = request.paciente
    agora = timezone.localtime()
    hoje = timezone.localdate()

    proximo = (
        Agendamento.objects.filter(
            paciente=paciente,
            status__in=[
                Agendamento.Status.AGENDADO,
                Agendamento.Status.CONFIRMADO,
                Agendamento.Status.EM_ATENDIMENTO,
            ],
        )
        .filter(
            Q(slot__agenda__data__gt=hoje)
            | Q(slot__agenda__data=hoje, slot__hora_inicio__gte=agora.time())
        )
        .select_related("profissional", "tipo_atendimento", "slot__agenda")
        .order_by("slot__agenda__data", "slot__hora_inicio")
        .first()
    )

    servicos = TipoAtendimento.objects.filter(ativo=True, deleted_at__isnull=True)
    nao_lidas = Notificacao.objects.filter(
        destinatario=request.user,
        lida=False,
    ).count()

    tiles = [
        {"rotulo": "Agendar", "icone": "bi-calendar-plus", "url": reverse("portal:agendar")},
        {"rotulo": "Meu treino", "icone": "bi-heart-pulse", "url": reverse("portal:treinos")},
        {"rotulo": "Evolução", "icone": "bi-graph-up", "url": reverse("portal:evolucao")},
        {"rotulo": "Avaliações", "icone": "bi-clipboard2-pulse", "url": reverse("portal:avaliacoes")},
        {"rotulo": "Minha equipe", "icone": "bi-people", "url": reverse("portal:equipe")},
        {"rotulo": "Contato", "icone": "bi-chat-dots", "url": reverse("portal:contato")},
        {"rotulo": "Documentos", "icone": "bi-file-earmark-text", "url": reverse("portal:documentos")},
    ]

    return render(request, "portal/home.html", {
        "proximo": proximo,
        "servicos": servicos,
        "nao_lidas": nao_lidas,
        "tiles": tiles,
    })


# ─────────────────────────────────────────────────────────────
# CONSULTAS
# ─────────────────────────────────────────────────────────────

@portal_required
def consultas(request):
    consultas_qs = (
        Agendamento.objects
        .filter(paciente=request.paciente)
        .select_related("slot__agenda", "tipo_atendimento", "profissional")
        .order_by("-slot__agenda__data", "-slot__hora_inicio")
    )
    return render(request, "portal/consultas.html", {"consultas": consultas_qs})


@portal_required
def consulta_detalhe(request, uuid):
    """Detalhe de uma consulta do paciente.

    O filtro de dono vai na query, nunca num `if` posterior: devolve 404
    uniforme e não revela se o uuid existe. AgendamentoManager já filtra
    deleted_at, então não repita o filtro aqui.
    """
    consulta = get_object_or_404(
        Agendamento.objects.select_related(
            "slot__agenda", "tipo_atendimento", "profissional", "cancelado_por",
        ),
        uuid=uuid,
        paciente=request.paciente,
    )
    return render(request, "portal/consulta_detalhe.html", {"consulta": consulta})


@portal_required
@require_POST
def cancelar_consulta(request, uuid):
    """Cancela consulta pelo portal, liberando os slots ocupados.

    Valida pode_cancelar no servidor: esconder o botão no template não é
    controle de acesso, é conveniência de UI.
    """
    consulta = get_object_or_404(
        Agendamento.objects.select_related("slot__agenda"),
        uuid=uuid,
        paciente=request.paciente,
    )

    if not consulta.pode_cancelar:
        messages.error(request, consulta.motivo_bloqueio_cancelamento)
        return redirect("portal:consulta_detalhe", uuid=consulta.uuid)

    motivo = (request.POST.get("motivo") or "").strip()
    if not motivo:
        messages.error(request, "Informe o motivo do cancelamento.")
        return redirect("portal:consulta_detalhe", uuid=consulta.uuid)

    motivo_limpo = motivo[:500]

    with transaction.atomic():
        slot_ids = set(consulta.slots_ocupados.values_list("pk", flat=True))
        if consulta.slot_id:
            slot_ids.add(consulta.slot_id)

        slots = list(
            SlotAgenda.objects.select_for_update().filter(pk__in=slot_ids)
        )

        status_anterior = consulta.status
        consulta.status = Agendamento.Status.CANCELADO
        consulta.cancelado_por = request.user
        consulta.motivo_cancelamento = motivo_limpo
        consulta.save(
            update_fields=[
                "status", "cancelado_por", "motivo_cancelamento", "updated_at",
            ]
        )

        # 1) Libera PRIMEIRO. gerar_slots_do_dia não toca slot OCUPADO —
        #    reconciliar antes da liberação é no-op puro.
        for slot in slots:
            slot.status = SlotAgenda.Status.LIVRE
            slot.save(update_fields=["status", "updated_at"])

        # 2) Trilha de auditoria do cancelamento. Best-effort: o serviço
        #    nunca levanta exceção, então não pode reverter o cancelamento.
        registrar_auditoria(
            usuario=request.user,
            acao="CANCELAMENTO_PORTAL",
            tabela="agendamento",
            registro_id=consulta.pk,
            dados_antes={"status": status_anterior},
            dados_depois={"status": Agendamento.Status.CANCELADO},
            motivo=motivo_limpo,
            request=request,
        )

        # 3) Reconcilia DEPOIS, com os slots já livres: o que saiu da
        #    disponibilidade vigente vira INDISPONIVEL em vez de LIVRE.
        #    Best-effort: se o dia virou sem expediente mas ainda tem
        #    outros pacientes agendados, a guarda recusa o rebaixamento.
        #    O cancelamento NÃO pode falhar por isso.
        try:
            gerar_slots_do_dia(consulta.profissional, consulta.data)
        except ValidationError as exc:
            logger.warning(
                "Cancelamento de %s aplicado, reconciliação não: %s",
                consulta.uuid,
                exc,
            )

    messages.success(
        request,
        "Consulta cancelada. O horário voltou a ficar disponível.",
    )
    return redirect("portal:consultas")


# ─────────────────────────────────────────────────────────────
# DOCUMENTOS
# ─────────────────────────────────────────────────────────────

@portal_required
def documentos(request):
    docs = (
        Documento.objects.filter(
            paciente=request.paciente,
            visivel_paciente=True,
            deleted_at__isnull=True,
        )
        .order_by("-created_at")
    )
    return render(request, "portal/documentos.html", {"documentos": docs})


@portal_required
def documento_download(request, uuid):
    """Serve o arquivo do documento com validação de dono + visibilidade.

    Revalida no momento do download (não só na listagem): se o profissional
    revogar `visivel_paciente` depois, o link antigo deixa de funcionar.
    O get_object_or_404 já filtra visivel_paciente=True — 404 uniforme é
    a política correta contra enumeração de uuid.
    """
    documento = get_object_or_404(
        Documento,
        uuid=uuid,
        paciente=request.paciente,
        visivel_paciente=True,
        deleted_at__isnull=True,
    )

    nome = os.path.basename(documento.arquivo.name)
    return FileResponse(
        documento.arquivo.open("rb"),
        as_attachment=True,
        filename=nome,
    )


# ─────────────────────────────────────────────────────────────
# EVOLUÇÃO / AVALIAÇÕES
# ─────────────────────────────────────────────────────────────

@portal_required
def evolucao(request):
    """Só evoluções LIBERADAS chegam ao paciente.

    Rascunho (P) e inativada (I) nunca são visíveis no portal — é a
    contrapartida do trigger de imutabilidade construído nas migrações
    0013–0017.
    """
    evolucoes = (
        Evolucao.objects.filter(
            paciente=request.paciente,
            status=Evolucao.Status.LIBERADA,
        )
        .select_related("atendimento", "profissional")
        .order_by("-created_at")
    )
    return render(request, "portal/evolucao.html", {"evolucoes": evolucoes})


@portal_required
def avaliacoes(request):
    avaliacoes_qs = (
        Avaliacao.objects.filter(
            paciente=request.paciente,
            status=Avaliacao.Status.LIBERADA,
        )
        .select_related("profissional")
        .order_by("-created_at")
    )
    return render(request, "portal/avaliacoes.html", {"avaliacoes": avaliacoes_qs})


@portal_required
def avaliacao_detalhe(request, uuid):
    avaliacao = get_object_or_404(
        Avaliacao,
        uuid=uuid,
        paciente=request.paciente,
        status=Avaliacao.Status.LIBERADA,
    )
    return render(request, "portal/avaliacao_detalhe.html", {"avaliacao": avaliacao})


# ─────────────────────────────────────────────────────────────
# EQUIPE / PERFIL / CONTATO
# ─────────────────────────────────────────────────────────────

@portal_required
def equipe(request):
    profissionais = Profissional.objects.filter(status="ATIVO").order_by("nome_completo")
    return render(request, "portal/equipe.html", {"profissionais": profissionais})

@portal_required
def perfil(request):
    registrar_auditoria(
        usuario=request.user,
        acao="ACESSO_PERFIL_PORTAL",
        tabela="paciente",
        registro_id=request.paciente.pk,
        request=request,
    )
    return render(request, "portal/perfil.html", {"paciente": request.paciente})

@portal_required
def contato(request):
    """Formulário de contato — envia mensagem para a equipe do paciente.

    A "equipe" é definida por vínculo real de atendimento: profissionais
    com quem o paciente tem ou teve agendamento. Sem esse filtro, o
    paciente pode enviar mensagem para qualquer profissional do banco
    passando um pk arbitrário no POST.
    """
    # Profissionais da equipe: com agendamento (qualquer status) para
    # este paciente. distinct() porque um profissional pode ter vários
    # agendamentos com o mesmo paciente.
    profissionais = (
        Profissional.objects.filter(
            vinculos_pacientes__paciente=request.paciente,
            vinculos_pacientes__ativo=True,
            vinculos_pacientes__deleted_at__isnull=True,
            status=Profissional.Status.ATIVO,
            user__isnull=False,
        )
        .select_related("user")
        .distinct()
        .order_by("nome_completo")
    )
    if request.method == "POST":
        destinatario_id = request.POST.get("destinatario")
        corpo = request.POST.get("corpo", "").strip()

        if not destinatario_id or not corpo:
            messages.error(request, "Informe o destinatário e a mensagem.")
        else:
            # Filtra pelo MESMO queryset da listagem: o destinatário
            # precisa estar na equipe do paciente. pk de terceiro → None.
            profissional = profissionais.filter(pk=destinatario_id).first()

            if profissional is None:
                messages.error(
                    request,
                    "Destinatário inválido. Escolha um profissional da sua equipe.",
                )
            else:
                enviar_mensagem(
                    remetente=request.user,
                    destinatario=profissional.user,
                    assunto=f"Contato do paciente {request.paciente.nome_completo}",
                    corpo=corpo,
                    paciente=request.paciente,
                )
                messages.success(request, "Mensagem enviada à equipe.")
                return redirect("portal:contato")

    return render(request, "portal/contato.html", {"profissionais": profissionais})


@portal_required
def em_breve(request):
    return render(request, "portal/em_breve.html")


# ─────────────────────────────────────────────────────────────
# AGENDAMENTO — fluxo em 4 passos
# ─────────────────────────────────────────────────────────────

DIAS_JANELA = 28


def _profissionais_ativos():
    return Profissional.objects.filter(status="ATIVO").order_by("nome_completo")


def _mapa_de_vagas(profissional, inicio, fim):
    """1 query: quantos slots livres por dia na janela."""
    linhas = (
        SlotAgenda.objects.filter(
            agenda__profissional=profissional,
            agenda__data__range=(inicio, fim),
            agenda__status=Agenda.Status.GERADA,
            status=SlotAgenda.Status.LIVRE,
        )
        .values("agenda__data")
        .annotate(total=Count("id"))
        .order_by("agenda__data")
    )
    return {linha["agenda__data"]: linha["total"] for linha in linhas}


@portal_required
def agendar(request):
    """Passo 1 — escolha do serviço (só tipos ativos e não excluídos)."""
    tipos = (
        TipoAtendimento.objects.filter(ativo=True, deleted_at__isnull=True)
        .order_by("nome")
    )
    return render(request, "portal/agendar_tipo.html", {"tipos": tipos})


@portal_required
def agendar_profissional(request, tipo_id):
    """Passo 2 — escolha do profissional."""
    tipo = get_object_or_404(TipoAtendimento, pk=tipo_id)
    return render(request, "portal/agendar_profissional.html", {
        "tipo": tipo,
        "profissionais": _profissionais_ativos(),
    })


@portal_required
def agendar_horario(request, tipo_id, profissional_id):
    """Passo 3 — calendário da janela de 28 dias + slots do dia inicial."""
    tipo = get_object_or_404(TipoAtendimento, pk=tipo_id)
    profissional = get_object_or_404(Profissional, pk=profissional_id, status="ATIVO")

    hoje = timezone.localdate()
    fim = hoje + timedelta(days=DIAS_JANELA - 1)
    mapa = _mapa_de_vagas(profissional, hoje, fim)

    dias = []
    cursor = hoje
    while cursor <= fim:
        dias.append({"data": cursor, "total": mapa.get(cursor, 0)})
        cursor += timedelta(days=1)

    primeiro_livre = next((d["data"] for d in dias if d["total"]), hoje)

    return render(request, "portal/agendar_horario.html", {
        "tipo": tipo,
        "profissional": profissional,
        "dias": dias,
        "data_selecionada": primeiro_livre,
        "slots": _slots_do_dia(profissional, primeiro_livre),
    })


@portal_required
def agendar_slots(request, tipo_id, profissional_id, data):
    """Parcial HTMX — slots livres de uma data."""
    profissional = get_object_or_404(Profissional, pk=profissional_id, status="ATIVO")
    dia = timezone.datetime.strptime(data, "%Y-%m-%d").date()
    return render(request, "portal/_slots.html", {
        "tipo_id": tipo_id,
        "profissional": profissional,
        "data_selecionada": dia,
        "slots": _slots_do_dia(profissional, dia),
    })


def _slots_do_dia(profissional, dia):
    qs = SlotAgenda.objects.filter(
        agenda__profissional=profissional,
        agenda__data=dia,
        agenda__status=Agenda.Status.GERADA,
        agenda__deleted_at__isnull=True,
        deleted_at__isnull=True,
        status=SlotAgenda.Status.LIVRE,
    )
    if dia == timezone.localdate():
        qs = qs.filter(hora_inicio__gte=timezone.localtime().time())
    return qs.order_by("hora_inicio")


@portal_required
@require_POST
def agendar_confirmar(request):
    """Passo 4 — confirma a reserva.

    Ordem obrigatória: resolver tipo → profissional → slot, DEPOIS validar
    janela temporal, coerência de profissional e disponibilidade. O guard
    temporal usa `slot.agenda.data`, então `slot` precisa existir antes.
    """
    # 1) Resolve o tipo de atendimento.
    tipo = get_object_or_404(
        TipoAtendimento,
        pk=request.POST.get("tipo"),
        ativo=True,
        deleted_at__isnull=True,
    )

    # 2) Resolve o profissional.
    profissional = get_object_or_404(
        Profissional,
        pk=request.POST.get("profissional"),
        status=Profissional.Status.ATIVO,
        deleted_at__isnull=True,
    )

    # 3) Resolve o slot (select_related para evitar N+1).
    slot = get_object_or_404(
        SlotAgenda.objects.select_related("agenda", "agenda__profissional"),
        pk=request.POST.get("slot"),
    )

    # 4) Guard temporal — o formulário nunca oferece horário passado
    #    (_slots_do_dia filtra hora_inicio__gte=localtime), mas o servidor
    #    não pode confiar no formulário. localtime() e não now().time():
    #    now() devolve UTC e erra 3h em America/Sao_Paulo.
    hoje = timezone.localdate()
    agora = timezone.localtime().time()
    if slot.agenda.data < hoje or (
        slot.agenda.data == hoje and slot.hora_inicio <= agora
    ):
        messages.error(request, "Este horário já passou. Escolha outro.")
        return redirect(
            "portal:agendar_horario",
            tipo_id=tipo.pk,
            profissional_id=profissional.pk,
        )

    # 5) Coerência: o slot pertence ao profissional escolhido?
    if slot.agenda.profissional_id != profissional.pk:
        messages.error(request, "Horário inválido. Escolha outro.")
        return redirect(
            "portal:agendar_horario",
            tipo_id=tipo.pk,
            profissional_id=profissional.pk,
        )

    # 6) Disponibilidade: agenda gerada e slot livre?
    if (
        slot.agenda.status != Agenda.Status.GERADA
        or slot.status != SlotAgenda.Status.LIVRE
    ):
        messages.error(request, "Este horário não está mais disponível.")
        return redirect(
            "portal:agendar_horario",
            tipo_id=tipo.pk,
            profissional_id=profissional.pk,
        )

    # 7) Formatação ANTES da mutação: um erro aqui não deixa reserva órfã.
    data_txt = slot.agenda.data.strftime("%d/%m/%Y")
    hora_txt = slot.hora_inicio.strftime("%H:%M")

    # 8) Reserva via service (que já faz select_for_update internamente).
    try:
        agendamento = reservar_para_paciente(
            paciente=request.paciente,
            slot=slot,
            tipo=tipo,
            usuario=request.user,
        )
    except PortalAgendaError as exc:
        messages.error(request, f"Não foi possível agendar: {exc}")
        return redirect(
            "portal:agendar_horario",
            tipo_id=tipo.pk,
            profissional_id=profissional.pk,
        )

    messages.success(request, f"Agendamento confirmado para {data_txt} às {hora_txt}.")

    if getattr(agendamento, "uuid", None):
        return redirect("portal:consulta_detalhe", uuid=agendamento.uuid)
    return redirect("portal:consultas")


# ─────────────────────────────────────────────────────────────
# AGENDAMENTOS FUTUROS (ListView)
# ─────────────────────────────────────────────────────────────

STATUS_PROXIMOS = (Agendamento.Status.AGENDADO, Agendamento.Status.CONFIRMADO)


class AgendamentosFuturosView(PacienteScopedMixin, ListView):
    model = Agendamento
    template_name = "portal/agendamentos_futuros.html"
    context_object_name = "agendamentos"
    paginate_by = 20

    def get_queryset(self):
        # super() primeiro: escopo por paciente antes do recorte de data.
        # O filtro é slot__agenda__data — Agendamento NÃO tem campo "agenda".
        return (
            super().get_queryset()
            .filter(status__in=STATUS_PROXIMOS)
            .filter(slot__agenda__data__gte=timezone.localdate())
            .select_related(
                "slot__agenda",
                "slot__agenda__profissional",
                "slot__agenda__profissional__user",
                "tipo_atendimento",
                "sala",
            )
            .order_by("slot__agenda__data", "slot__hora_inicio")
        )

#─────────────────────────────────────────────────────────────
#EXECUÇÃO DE EXERCÍCIOS
#─────────────────────────────────────────────────────────────
@portal_required
def treinos(request):
    """Lista as prescrições ativas do paciente."""
    hoje = timezone.localdate()

    prescricoes = (
        Prescricao.objects.filter(
            paciente=request.paciente,
            deleted_at__isnull=True,
            status=Prescricao.Status.ATIVA,
        )
        .filter(
            Q(data_validade__isnull=True) | Q(data_validade__gte=hoje)
        )
        .select_related("profissional")
        .prefetch_related("itens__exercicio")
        .order_by("-data", "-created_at")
    )

    return render(
        request,
        "portal/treinos.html",
        {"prescricoes": prescricoes},
    )


@portal_required
def treino_detalhe(request, uuid):
    """Detalhe de uma prescrição — 404 uniforme se não for do paciente."""
    prescricao = get_object_or_404(
        Prescricao.objects.filter(
            deleted_at__isnull=True,
            status=Prescricao.Status.ATIVA,
        ).select_related("profissional"),
        uuid=uuid,
        paciente=request.paciente,
    )

    # PrescricaoExercicio NÃO tem deleted_at — só o flag ativo.
    itens = (
        prescricao.itens.filter(ativo=True)
        .select_related("exercicio")
        .order_by("ordem")
    )

    # ExecucaoExercicio TEM deleted_at.
    executados = set(
        ExecucaoExercicio.objects.filter(
            prescricao_exercicio__in=itens,
            deleted_at__isnull=True,
        ).values_list("prescricao_exercicio_id", flat=True)
    )

    return render(
        request,
        "portal/treino_detalhe.html",
        {
            "prescricao": prescricao,
            "itens": itens,
            "executados": executados,
        },
    )


@portal_required
@require_POST
def executar_exercicio(request, uuid, item_id):
    """Registra a execução de um exercício pelo paciente."""
    item = get_object_or_404(
        PrescricaoExercicio.objects.filter(
            prescricao__deleted_at__isnull=True,
            prescricao__status=Prescricao.Status.ATIVA,
            prescricao__paciente=request.paciente,
            ativo=True,
        ).select_related("prescricao", "exercicio"),
        pk=item_id,
        prescricao__uuid=uuid,
    )

    series = request.POST.get("series_feitas", "").strip()
    repeticoes = request.POST.get("repeticoes_feitas", "").strip()
    esforco = request.POST.get("percepcao_esforco", "").strip()
    dor = request.POST.get("dor_eva", "").strip()
    observacoes = request.POST.get("observacoes", "").strip()

    ExecucaoExercicio.objects.create(
        prescricao_exercicio=item,
        paciente=request.paciente,
        data=timezone.localdate(),
        realizado=True,
        series_feitas=int(series) if series.isdigit() else None,
        repeticoes_feitas=repeticoes or None,
        percepcao_esforco=int(esforco) if esforco.isdigit() else None,
        dor_eva=int(dor) if dor.isdigit() else None,
        observacoes=observacoes or None,
        criado_via=ExecucaoExercicio.CriadoVia.PORTAL,
    )

    messages.success(request, f"Exercício «{item.exercicio.nome}» registrado.")
    return redirect("portal:treino_detalhe", uuid=item.prescricao.uuid)
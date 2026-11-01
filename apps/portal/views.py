import os
import logging

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.contrib import messages
from django.db.models import Count, Q
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from apps.attendance.models import Atendimento
from apps.clinic.models import TipoAtendimento
from apps.clinical.models import Avaliacao, Evolucao
from apps.communication.models import Notificacao
from apps.communication.services import enviar_mensagem
from apps.documents.models import Documento
from apps.portal.helpers import portal_required
from apps.portal.mixins import PacienteScopedMixin
from apps.portal.services import PortalAgendaError, reservar_para_paciente
from apps.professionals.models import Profissional
from apps.scheduling.models import Agendamento, Agenda, SlotAgenda
from apps.scheduling.services.geracao_slots import gerar_slots_do_dia
from apps.audit.services import registrar_auditoria

logger = logging.getLogger(__name__)

@portal_required
def home(request):
    paciente = request.paciente
    agora = timezone.now()
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
    servicos = TipoAtendimento.objects.all()
    nao_lidas = Notificacao.objects.filter(destinatario=request.user, lida=False).count()

    tiles = [
        {"rotulo": "Agendar", "icone": "bi-calendar-plus", "url": reverse("portal:agendar")},
        {"rotulo": "Meu treinsssso", "icone": "bi-heart-pulse", "url": reverse("portal:treinos")},
        {"rotulo": "Evolução", "icone": "bi-graph-up", "url": reverse("portal:evolucao")},
        {"rotulo": "Avaliações", "icone": "bi-clipboard2-pulse", "url": reverse("portal:avaliacoes")},
        {"rotulo": "Minha equipe", "icone": "bi-people", "url": reverse("portal:equipe")},
        {"rotulo": "Contato", "icone": "bi-chat-dots", "url": reverse("portal:contato")},
        {"rotulo": "Documentos", "icone": "bi-file-earmark-text", "url": reverse("portal:documentos")},
    ]

    return render(request, "portal/home.html", {
        "proximo": proximo, "servicos": servicos,
        "nao_lidas": nao_lidas, "tiles": tiles,
    })


@portal_required
def consultas(request):
    consultas = (
        Agendamento.objects
        .filter(paciente=request.paciente)
        .select_related("slot__agenda", "tipo_atendimento", "profissional")
        .order_by("-slot__agenda__data", "-slot__hora_inicio")
    )
    return render(request, "portal/consultas.html", {"consultas": consultas})

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

        # Captura ANTES de mutar: consulta é referência, não cópia.
        status_anterior = consulta.status
        motivo_anterior = consulta.motivo_cancelamento

        consulta.status = Agendamento.Status.CANCELADO
        consulta.cancelado_por = request.user
        consulta.motivo_cancelamento = motivo_limpo
        consulta.save(
            update_fields=[
                "status", "cancelado_por", "motivo_cancelamento", "updated_at",
            ]
        )

        # 1) Libera PRIMEIRO. gerar_slots_do_dia não toca slot OCUPADO -
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
    """    
    documento = get_object_or_404(
        Documento,
        uuid=uuid,
        paciente=request.paciente,
        visivel_paciente=True,
        deleted_at__isnull=True,
    )    
    if not documento.visivel_paciente:
        return HttpResponseForbidden("Este documento não está disponível no portal.")
    
    nome = os.path.basename(documento.arquivo.name)

    return FileResponse(
        documento.arquivo.open("rb"),
        as_attachment=True,
        filename=nome,        
    )

def test_documento_de_outro_paciente_devolve_404(self):
    doc = Documento.objects.create(
        paciente=self.outro_paciente,
        visivel_paciente=True,
        arquivo="documentos/teste.pdf",
    )
    self.client.force_login(self.user)
    resposta = self.client.get(
        reverse("portal:documento_download", kwargs={"uuid": doc.uuid})
    )
    self.assertEqual(resposta.status_code, 404)    

@portal_required
def evolucao(request):
    evolucoes = (
        Evolucao.objects.filter(paciente=request.paciente)
        .select_related("atendimento", "profissional")
        .order_by("-created_at")
    )
    return render(request, "portal/evolucao.html", {"evolucoes": evolucoes})


@portal_required
def avaliacoes(request):
    avaliacoes = (
        Avaliacao.objects.filter(
            paciente=request.paciente,
            status=Avaliacao.Status.LIBERADA,
        )
        .select_related("profissional")
        .order_by("-created_at")
    )
    return render(request, "portal/avaliacoes.html", {"avaliacoes": avaliacoes})


@portal_required
def avaliacao_detalhe(request, uuid):
    avaliacao = get_object_or_404(
        Avaliacao,
        uuid=uuid,
        paciente=request.paciente,
        status=Avaliacao.Status.LIBERADA,
    )
    return render(request, "portal/avaliacao_detalhe.html", {"avaliacao": avaliacao})


@portal_required
def equipe(request):
    profissionais = Profissional.objects.filter(status="ATIVO").order_by("nome_completo")
    return render(request, "portal/equipe.html", {"profissionais": profissionais})


@portal_required
def perfil(request):
    return render(request, "portal/perfil.html", {"paciente": request.paciente})


@portal_required
def contato(request):
    """Formulário de contato - envia mensagem para a equipe via Comunicação."""
    profissionais = (
        Profissional.objects.filter(status="ATIVO", user__isnull=False)
        .select_related("user")
        .order_by("nome_completo")
    )
    if request.method == "POST":
        destinatario_id = request.POST.get("destinatario")
        corpo = request.POST.get("corpo", "").strip()
        if not destinatario_id or not corpo:
            messages.error(request, "Informe o destinatário e a mensagem.")
        else:
            profissional = Profissional.objects.filter(pk=destinatario_id).first()
            if profissional and profissional.user:
                enviar_mensagem(
                    remetente=request.user,
                    destinatario=profissional.user,
                    assunto=f"Contato do paciente {request.paciente.nome_completo}",
                    corpo=corpo,
                    paciente=request.paciente,
                )
                messages.success(request, "Mensagem enviada à equipe.")
                return redirect("portal:contato")
            messages.error(request, "Destinatário inválido.")
    return render(request, "portal/contato.html", {"profissionais": profissionais})


@portal_required
def em_breve(request):
    return render(request, "portal/em_breve.html")


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
    """Passo 1 - escolha do serviço (só tipos ativos e não excluídos)."""
    tipos = (
        TipoAtendimento.objects.filter(ativo=True, deleted_at__isnull=True)
        .order_by("nome")
    )
    return render(request, "portal/agendar_tipo.html", {"tipos": tipos})

@portal_required
def agendar_profissional(request, tipo_id):
    """Passo 2 - escolha do profissional."""
    tipo = get_object_or_404(TipoAtendimento, pk=tipo_id)
    return render(request, "portal/agendar_profissional.html", {
        "tipo": tipo, "profissionais": _profissionais_ativos(),
    })


@portal_required
def agendar_horario(request, tipo_id, profissional_id):
    """Passo 3 - calendário da janela de 28 dias + slots do dia inicial."""
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

    # Primeiro dia com vaga já vem selecionado (menos um clique)
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
    """Parcial HTMX - slots livres de uma data."""
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
    tipo = get_object_or_404(
        TipoAtendimento, pk=request.POST.get("tipo"),
        ativo=True, deleted_at__isnull=True,
    )
    # Guard temporal: o formulário nunca oferece horário passado
    # (_slots_do_dia filtra hora_inicio__gte=timezone.localtime().time()),
    # mas o servidor não pode confiar no formulário.
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

    slot = get_object_or_404(
        SlotAgenda.objects.select_related("agenda", "agenda__profissional"),
        pk=request.POST.get("slot"),
    )

    # Política do canal, não do domínio: a recepção pode lançar retroativo
    # pelo portal clínico, então este guard fica aqui e não em reservar_slot().
    # localtime() e não now().time(): now() devolve UTC e erra 3h em
    # America/Sao_Paulo.
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
    
    profissional = get_object_or_404(
        Profissional,
        pk=request.POST.get("profissional"),
        status=Profissional.Status.ATIVO,
        deleted_at__isnull=True,
    )
    
    slot = get_object_or_404(
        SlotAgenda.objects.select_related("agenda", "agenda__profissional"),
        pk=request.POST.get("slot"),
    )

    if slot.agenda.profissional_id != profissional.pk:
        messages.error(request, "Horário inválido. Escolha outro.")
        return redirect("portal:agendar_horario", tipo_id=tipo.pk, profissional_id=profissional.pk)
    if slot.agenda.status != Agenda.Status.GERADA or slot.status != SlotAgenda.Status.LIVRE:
        messages.error(request, "Este horário não está mais disponível.")
        return redirect("portal:agendar_horario", tipo_id=tipo.pk, profissional_id=profissional.pk)

    # Formatação ANTES da mutação: um erro aqui não deixa reserva órfã no banco.
    data_txt = slot.agenda.data.strftime("%d/%m/%Y")
    hora_txt = slot.hora_inicio.strftime("%H:%M")

    try:
        agendamento = reservar_para_paciente(
            paciente=request.paciente, slot=slot, tipo=tipo, usuario=request.user,
        )
    except PortalAgendaError as exc:
        messages.error(request, f"Não foi possível agendar: {exc}")
        return redirect("portal:agendar_horario", tipo_id=tipo.pk, profissional_id=profissional.pk)

    messages.success(request, f"Agendamento confirmado para {data_txt} às {hora_txt}.")

    if getattr(agendamento, "uuid", None):
        return redirect("portal:consulta_detalhe", uuid=agendamento.uuid)
    return redirect("portal:consultas")



STATUS_PROXIMOS = (Agendamento.Status.AGENDADO, Agendamento.Status.CONFIRMADO)


class AgendamentosFuturosView(PacienteScopedMixin, ListView):
    model = Agendamento
    template_name = "portal/agendamentos_futuros.html"
    context_object_name = "agendamentos"
    paginate_by = 20

    def get_queryset(self):
        # super() primeiro: escopo por paciente antes do recorte de data.
        # O filtro é slot__agenda__data - Agendamento NÃO tem campo "agenda".
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
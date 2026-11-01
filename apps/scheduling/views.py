"""Views da agenda (grade HTMX).

Padrão: view fina, service gorda. As views apenas:
  1. leem parâmetros da request;
  2. chamam o service layer (que concentra toda a regra de negócio);
  3. capturam AgendaError e traduzem em feedback (messages);
  4. devolvem o fragmento HTMX atualizado.

RBAC (grupos):
  - Ver a grade e operar a agenda: Administrador, Recepcionista, Fisioterapeuta
  - Gerar/reconciliar a grade (criar slots): Administrador, Recepcionista

"""

from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.constants import (
    GRUPOS_ATENDIMENTOS_CONCLUIR,
    GRUPOS_ATENDIMENTOS_INICIAR,
    GRUPOS_CLINICO_EDITAR,
)
from apps.accounts.permissions import (
    GRUPOS_AGENDA,
    GRUPOS_GERACAO_GRADE,
    grupos_requeridos,
)

from apps.attendance.exceptions import AtendimentoError
from apps.attendance.models import Atendimento
from apps.attendance.services import finalizar_atendimento, iniciar_atendimento
from apps.clinic.models import Sala, TipoAtendimento
from apps.patients.models import Paciente
from apps.professionals.models import Profissional
from apps.scheduling.exceptions import AgendaError
from apps.scheduling.models import Agenda, Agendamento, SlotAgenda
from apps.scheduling.services import (
    alterar_status,
    cancelar_agendamento,
    gerar_slots_periodo,
    remarcar_agendamento,
    reservar_slot,
)
from apps.scheduling.services.geracao_slots import (
    garantir_grade_do_dia,
    liberar_funcionamento_feriado,
    reverter_excecao_feriado,
)
from apps.scheduling.services.grade_visual import montar_dia_mesclado

DIAS_DA_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
NUM_DIAS = 6  # segunda a sábado - ajuste conforme o expediente da clínica

# Horizonte da geração manual e sob demanda (alinhado ao job diário).
HORIZONTE_GRADE_DIAS = 45

# Limite máximo de antecedência para gerar grade sob demanda.
# Datas além disso não são reserváveis (dias_max_antecedencia da Configuracao),
# portanto não faz sentido materializar slots para elas.
LIMITE_GERACAO_DIAS = 120

# Status que mantêm o slot OCUPADO e exibem o paciente na grade.
# Esta é a única fonte de verdade para o Prefetch dos agendamentos.
STATUS_OCUPAM_SLOT = (
    Agendamento.Status.AGENDADO,
    Agendamento.Status.CONFIRMADO,
    Agendamento.Status.EM_ATENDIMENTO,
    Agendamento.Status.ATENDIDO,
    Agendamento.Status.FALTOU,
)

# Mantido por compatibilidade: outros módulos podem importar daqui.
STATUS_ATIVOS = STATUS_OCUPAM_SLOT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inicio_da_semana(data):
    """Segunda-feira da semana que contém `data`."""
    return data - timedelta(days=data.weekday())


def _obter_profissional(profissional_id):
    profissionais = Profissional.objects.filter(status=Profissional.Status.ATIVO)
    if profissional_id:
        return get_object_or_404(profissionais, pk=profissional_id)
    return profissionais.order_by("nome_completo").first()


def _pode_gerar_grade(usuario):
    return usuario.is_superuser or usuario.groups.filter(
        name__in=GRUPOS_GERACAO_GRADE
    ).exists()

def _pode_atender(usuario):
    """Permite abrir a ficha do atendimento a partir da grade."""
    if not getattr(usuario, "is_authenticated", False):
        return False
    if usuario.is_superuser:
        return True
    return usuario.groups.filter(
        name__in=list(GRUPOS_ATENDIMENTOS_INICIAR) + list(GRUPOS_ATENDIMENTOS_CONCLUIR)
    ).exists()

def _garantir_grade_da_semana(profissional, data_inicio):
    """Geração sob demanda: materializa a grade dos dias exibidos que ainda
    não existem (idempotente). Cobertura para datas além do horizonte do job -
    a recepção navega para D+60 e a grade daquele dia é criada na hora.

    Otimização: uma única query detecta os dias já processados; só os dias
    faltantes passam pelo gerador, e todos compartilham a mesma Configuracao.
    """
    hoje = timezone.localdate()
    limite = hoje + timedelta(days=LIMITE_GERACAO_DIAS)
    datas = [
        data_inicio + timedelta(days=offset)
        for offset in range(NUM_DIAS)
        if data_inicio + timedelta(days=offset) <= limite
    ]
    if not datas:
        return
    existentes = set(
        Agenda.objects.filter(
            profissional=profissional, data__in=datas
        ).values_list("data", flat=True)
    )
    faltantes = [dia for dia in datas if dia not in existentes]
    if not faltantes:
        return

    from apps.scheduling.services import validacoes as V

    configuracao = V.obter_configuracao()
    for dia in faltantes:
        garantir_grade_do_dia(profissional, dia, configuracao)


def _queryset_agendamentos_para_grade():
    """Agendamentos que ocupam slot, já com tudo que a grade consome.

    `select_related` cobre os FKs que o card do agendamento exibe -
    sem isso, cada card gera uma query por campo acessado no template.
    `slots_ocupados` é prefetchado porque `montar_dia_mesclado` monta o
    bloco a partir dele.
    """
    return (
        Agendamento.objects.filter(status__in=STATUS_OCUPAM_SLOT)
        .select_related(
            "paciente",
            "tipo_atendimento",
            "sala",
            "profissional__user",
        )
        .prefetch_related(
            Prefetch(
                "slots_ocupados",
                queryset=SlotAgenda.objects.order_by("hora_inicio"),
            ),
            Prefetch(
                "atendimento",
                queryset=Atendimento.objects.select_related("sala"),
            ),
        )
        .order_by("created_at")
    )

def _contexto_grade(usuario, profissional, data_inicio):
    """Monta o contexto da grade semanal (página e fragmentos HTMX).

    Estratégia de carregamento - 4 queries fixas, independente do volume:

      1. agendas da semana           → 1 query
      2. slots de todas as agendas   → 1 query
      3. agendamentos que tocam qualquer slot da semana (FK ou bloco) → 1 query
      4. slots_ocupados desses agendamentos (Prefetch no helper)    → 1 query

    O cache (`_agendamentos_ativos` / `_agendamentos_bloco`) é injetado
    manualmente em cada slot. Isso evita o `Prefetch` aninhado dentro de
    `Prefetch`, que o ORM degrada para um nível por agenda (N queries
    em vez de 1).
    """
    data_inicio = _inicio_da_semana(data_inicio)
    _garantir_grade_da_semana(profissional, data_inicio)

    agendas = list(
        Agenda.objects.filter(
            profissional=profissional,
            data__gte=data_inicio,
            data__lt=data_inicio + timedelta(days=NUM_DIAS),
        ).order_by("data")
    )
    agendas_por_data = {agenda.data: agenda for agenda in agendas}
    agenda_ids = [agenda.pk for agenda in agendas]

    slots = list(
        SlotAgenda.objects.filter(agenda_id__in=agenda_ids)
        .select_related("agenda")
        .order_by("hora_inicio")
    )
    slot_pks = [slot.pk for slot in slots]

    agendamentos = (
        list(
            _queryset_agendamentos_para_grade()
            .filter(Q(slot_id__in=slot_pks) | Q(slots_ocupados__in=slot_pks))
            .distinct()
        )
        if slot_pks
        else []
    )

    # Mapa de ocupação: FK principal e M2M de bloco.
    por_fk, por_bloco = {}, {}
    for agendamento in agendamentos:
        por_fk.setdefault(agendamento.slot_id, []).append(agendamento)
        for slot_bloco in agendamento.slots_ocupados.all():
            por_bloco.setdefault(slot_bloco.pk, []).append(agendamento)

    slots_por_agenda = {}
    for slot in slots:
        slot._agendamentos_ativos = por_fk.get(slot.pk, [])
        slot._agendamentos_bloco = por_bloco.get(slot.pk, [])
        slots_por_agenda.setdefault(slot.agenda_id, []).append(slot)

    horarios = sorted({slot.hora_inicio for slot in slots})

    dias = []
    for offset in range(NUM_DIAS):
        dia_data = data_inicio + timedelta(days=offset)
        agenda = agendas_por_data.get(dia_data)
        celulas, cobertos = montar_dia_mesclado(
            agenda,
            slots=slots_por_agenda.get(agenda.pk) if agenda else None,
        )
        dias.append({
            "data": dia_data,
            "rotulo": DIAS_DA_SEMANA[offset],
            "agenda": agenda,
            "celulas": celulas,
            "cobertos": cobertos,
        })

    return {
        "profissionais": (
            Profissional.objects.filter(status=Profissional.Status.ATIVO)
            .order_by("nome_completo")
        ),
        "profissional": profissional,
        "dias": dias,
        "grade_horarios": horarios,
        "data_inicio": data_inicio,
        "semana_anterior": data_inicio - timedelta(days=7),
        "semana_proxima": data_inicio + timedelta(days=7),
        "pode_gerar_grade": _pode_gerar_grade(usuario),
        "pode_atender": _pode_atender(usuario),        
        "tipos_atendimento": TipoAtendimento.objects.all().order_by("nome"),
        "salas": Sala.objects.all().order_by("nome"),
        "pacientes": (
            Paciente.objects.filter(status=Paciente.Status.ATIVO)
            .order_by("nome_completo")
        ),
    }


def _grade_fragment(request, agenda):
    """Fragmento HTMX da semana do slot/agenda informado."""
    contexto = _contexto_grade(request.user, agenda.profissional, agenda.data)
    return render(request, "scheduling/_grade.html", contexto)


# ---------------------------------------------------------------------------
# Grade
# ---------------------------------------------------------------------------

@require_GET
@grupos_requeridos(*GRUPOS_AGENDA)
def grade_semanal(request):
    """Grade semanal de um profissional (GET). Query params:
    `profissional` (id) e `data_inicio` (AAAA-MM-DD, segunda-feira)."""
    profissional = _obter_profissional(request.GET.get("profissional"))
    if profissional is None:
        return render(request, "scheduling/grade_semanal.html", {
            "sem_profissionais": True,
        })

    data_inicio = _inicio_da_semana(timezone.localdate())
    if request.GET.get("data_inicio"):
        try:
            data_inicio = _inicio_da_semana(
                date.fromisoformat(request.GET["data_inicio"])
            )
        except ValueError:
            return HttpResponseBadRequest("Data inválida. Use AAAA-MM-DD.")

    contexto = _contexto_grade(request.user, profissional, data_inicio)
    if request.headers.get("HX-Request"):
        return render(request, "scheduling/_grade.html", contexto)
    return render(request, "scheduling/grade_semanal.html", contexto)


@require_POST
@grupos_requeridos(*GRUPOS_GERACAO_GRADE)
def gerar_grade_view(request, profissional_id):
    """Gera/reconcilia os slots do horizonte padrão do profissional."""
    profissional = get_object_or_404(Profissional, pk=profissional_id)
    agendas = gerar_slots_periodo(
        profissional, timezone.localdate(), dias=HORIZONTE_GRADE_DIAS
    )
    messages.success(
        request,
        f"Grade gerada: {len(agendas)} dia(s) com expediente "
        f"nos próximos {HORIZONTE_GRADE_DIAS} dias.",
    )
    if agendas:
        return _grade_fragment(request, agendas[0])
    contexto = _contexto_grade(request.user, profissional, timezone.localdate())
    return render(request, "scheduling/_grade.html", contexto)


# ---------------------------------------------------------------------------
# Reserva
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_AGENDA)
def reservar_slot_view(request, slot_id):
    """GET: formulário de reserva (modal). POST: executa a reserva."""
    if request.method == "GET":
        return _reservar_slot_form(request, slot_id)
    return _reservar_slot_submit(request, slot_id)


@require_GET
def _reservar_slot_form(request, slot_id):
    slot = get_object_or_404(
        SlotAgenda.objects.select_related("agenda__profissional"),
        pk=slot_id,
    )
    contexto = {
        "slot": slot,
        "pacientes": (
            Paciente.objects.filter(status=Paciente.Status.ATIVO)
            .order_by("nome_completo")
        ),
        "tipos_atendimento": TipoAtendimento.objects.all().order_by("nome"),
        "salas": Sala.objects.all().order_by("nome"),
    }
    return render(request, "scheduling/_reserva_form.html", contexto)


@require_POST
def _reservar_slot_submit(request, slot_id):
    slot = get_object_or_404(
        SlotAgenda.objects.select_related("agenda"),
        pk=slot_id,
    )
    paciente_id = request.POST.get("paciente")
    tipo_id = request.POST.get("tipo_atendimento")
    if not paciente_id or not tipo_id:
        messages.error(request, "Paciente e tipo de atendimento são obrigatórios.")
        return _grade_fragment(request, slot.agenda)

    paciente = get_object_or_404(Paciente, pk=paciente_id)
    tipo_atendimento = get_object_or_404(TipoAtendimento, pk=tipo_id)
    sala_id = request.POST.get("sala")
    sala = get_object_or_404(Sala, pk=sala_id) if sala_id else None

    try:
        reservar_slot(
            slot_id=slot_id,
            paciente=paciente,
            tipo_atendimento=tipo_atendimento,
            sala=sala,
            usuario=request.user if request.user.is_authenticated else None,
            observacoes=request.POST.get("observacoes", ""),
        )
    except AgendaError as erro:
        messages.error(request, str(erro))
        return _grade_fragment(request, slot.agenda)

    messages.success(
        request,
        f"{paciente.nome_completo} agendado para "
        f"{slot.agenda.data:%d/%m/%Y} às {slot.hora_inicio:%H:%M}.",
    )
    resposta = _grade_fragment(request, slot.agenda)
    resposta["X-Reserva-OK"] = "1"
    return resposta


# ---------------------------------------------------------------------------
# Cancelamento e transição de status
# ---------------------------------------------------------------------------

@require_POST
@grupos_requeridos(*GRUPOS_AGENDA)
def cancelar_agendamento_view(request, agendamento_id):
    agendamento = get_object_or_404(
        Agendamento.objects.select_related("slot__agenda"),
        pk=agendamento_id,
    )
    try:
        cancelar_agendamento(
            agendamento_id,
            request.POST.get("motivo", ""),
            usuario=request.user if request.user.is_authenticated else None,
        )
    except AgendaError as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, "Agendamento cancelado e horário liberado.")
    return _grade_fragment(request, agendamento.slot.agenda)


@require_POST
@grupos_requeridos(*GRUPOS_AGENDA)
def alterar_status_view(request, agendamento_id, novo_status):
    agendamento = get_object_or_404(
        Agendamento.objects.select_related("slot__agenda"),
        pk=agendamento_id,
    )
    try:
        alterar_status(
            agendamento_id,
            novo_status,
            usuario=request.user if request.user.is_authenticated else None,
        )
    except AgendaError as erro:
        messages.error(request, str(erro))
    else:
        agendamento.refresh_from_db()
        messages.success(
            request,
            f"Status atualizado para {agendamento.get_status_display()}.",
        )
    return _grade_fragment(request, agendamento.slot.agenda)


# ---------------------------------------------------------------------------
# Atendimento (check-in / check-out)
# ---------------------------------------------------------------------------

@require_POST
@grupos_requeridos(*GRUPOS_ATENDIMENTOS_INICIAR)
def iniciar_atendimento_view(request, agendamento_id):
    """Check-in: cria o Atendimento e move o agendamento para EM_ATENDIMENTO."""
    agendamento = get_object_or_404(
        Agendamento.objects.select_related("slot__agenda", "paciente"),
        pk=agendamento_id,
    )
    try:
        iniciar_atendimento(
            agendamento_id=agendamento_id,
            usuario=request.user if request.user.is_authenticated else None,
        )
    except AtendimentoError as erro:
        messages.error(request, str(erro))
    else:
        messages.success(
            request,
            f"Atendimento iniciado para {agendamento.paciente.nome_completo}.",
        )
    return _grade_fragment(request, agendamento.slot.agenda)


@login_required
@require_POST
@grupos_requeridos(*GRUPOS_ATENDIMENTOS_CONCLUIR)
def finalizar_atendimento_view(request, uuid):
    """Check-out: finaliza o atendimento e avisa se ficou sem evolução.

    Modo duplo: HTMX (modal da grade) recebe a grade atualizada - o
    fragmento embute as mensagens via hx-swap-oob. POST comum (sem JS)
    recebe o redirect PRG para onde o usuário estava (ex.: prontuário,
    via ?next=) ou para a ficha do atendimento.
    """
    # A URL expõe o uuid público (anti-IDOR, spec 1.3). O service espera
    # o PK interno (id inteiro) - resolva uuid → registro → pk.
    atendimento = get_object_or_404(
        Atendimento.objects.select_related("agendamento__slot__agenda"),
        uuid=uuid,
    )

    try:
        atendimento = finalizar_atendimento(
            atendimento_id=atendimento.pk,   # ← PK inteiro, NUNCA o uuid
            usuario=request.user,
        )
        if getattr(atendimento, "sem_evolucao", False):
            messages.warning(
                request,
                "Check-out concluído sem evolução registrada. "
                "Registre a evolução SOAP desta sessão no prontuário do paciente.",
            )
        else:
            messages.success(request, "Atendimento finalizado.")
    except AtendimentoError as erro:
        messages.error(request, str(erro))

    if request.headers.get("HX-Request"):
        # HTMX (modal da grade): devolve a grade atualizada com as mensagens OOB.
        return _grade_fragment(request, atendimento.agendamento.slot.agenda)

    # POST comum (fallback sem JS): volta para onde o usuário estava
    # (ex.: prontuário, via ?next=) ou cai na ficha do atendimento.
    # url_has_allowed_host_and_scheme bloqueia open redirect -
    # só URLs do próprio domínio passam.
    next_url = request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}
    ):
        return redirect(next_url)
    return redirect("scheduling:ficha_atendimento", uuid=uuid)


@grupos_requeridos(*GRUPOS_AGENDA)
def ficha_atendimento(request, uuid):
    """Ficha do atendimento: dados da sessão executada e do agendamento de origem."""
    atendimento = get_object_or_404(
        Atendimento.objects.select_related(
            "agendamento__slot__agenda",
            "paciente",
            "profissional",
            "sala",
            "tipo_atendimento",
        ),
        uuid=uuid,
    )
    pode_evoluir = (
        request.user.is_superuser
        or request.user.groups.filter(name__in=GRUPOS_CLINICO_EDITAR).exists()
    )
    return render(request, "scheduling/atendimento_ficha.html", {
        "atendimento": atendimento,
        "pode_evoluir": pode_evoluir,
    })


@require_GET
@grupos_requeridos(*GRUPOS_AGENDA)
def modal_atendimento(request, uuid):
    """Fragmento HTMX do atendimento para exibição em modal na grade."""
    atendimento = get_object_or_404(
        Atendimento.objects.select_related(
            "agendamento__slot__agenda",
            "paciente",
            "profissional",
            "sala",
            "tipo_atendimento",
        ),
        uuid=uuid,
    )
    return render(request, "scheduling/_atendimento_modal.html", {
        "atendimento": atendimento,
    })


# ---------------------------------------------------------------------------
# Feriado - liberar funcionamento (exceção pontual)
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_AGENDA)
def liberar_feriado(request):
    """Formulário + ação: declara exceção de funcionamento em feriado."""
    profissionais = Profissional.objects.filter(
        status=Profissional.Status.ATIVO
    ).order_by("nome_completo")
    data_inicial = request.GET.get("data") or timezone.localdate().isoformat()

    if request.method == "POST":
        profissional = get_object_or_404(
            Profissional, pk=request.POST.get("profissional_id")
        )
        data = parse_date(request.POST.get("data") or "")
        if not data:
            messages.error(request, "Informe a data do feriado.")
            return redirect("scheduling:liberar_feriado")

        agenda = liberar_funcionamento_feriado(profissional, data)
        if agenda:
            messages.success(
                request,
                f"Funcionamento liberado em {data:%d/%m/%Y} para "
                f"{profissional.nome_completo} - grade gerada.",
            )
        else:
            messages.error(
                request,
                f"Não foi possível gerar a grade em {data:%d/%m/%Y} - "
                "verifique disponibilidade, ausência e horário de funcionamento.",
            )
        return redirect("scheduling:grade")

    return render(request, "scheduling/liberar_feriado.html", {
        "profissionais": profissionais,
        "data_inicial": data_inicial,
    })


@require_POST
@grupos_requeridos(*GRUPOS_AGENDA)
def reverter_liberacao(request):
    """Remove a exceção e limpa os slots livres da agenda do feriado."""
    profissional = get_object_or_404(
        Profissional, pk=request.POST.get("profissional_id")
    )
    data = parse_date(request.POST.get("data") or "")
    if not data:
        messages.error(request, "Informe a data.")
        return redirect("scheduling:grade")

    removidos = reverter_excecao_feriado(profissional, data)
    messages.success(
        request,
        f"Exceção removida para {data:%d/%m/%Y} - {removidos} slot(s) livre(s) limpo(s).",
    )
    return redirect("scheduling:grade")


@require_POST
@grupos_requeridos(*GRUPOS_AGENDA)
def remarcar_agendamento_view(request, agendamento_id):
    """Drag and drop: move o agendamento para o slot solto pelo usuário."""
    agendamento = get_object_or_404(
        Agendamento.objects.select_related("slot__agenda"),
        pk=agendamento_id,
    )
    slot_id = request.POST.get("slot_id")
    if not slot_id:
        messages.error(request, "Slot de destino não informado.")
        return _grade_fragment(request, agendamento.slot.agenda)

    try:
        remarcar_agendamento(
            agendamento_id=agendamento_id,
            novo_slot_id=int(slot_id),
            usuario=request.user if request.user.is_authenticated else None,
        )
    except AgendaError as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, "Agendamento remarcado com sucesso.")
    return _grade_fragment(request, agendamento.slot.agenda)
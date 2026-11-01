import json

from apps.accounts.constants import GRUPOS_CLINICO_EDITAR, GRUPOS_CLINICO_VER, GRUPOS_CLINICO_LIBERAR, GRUPOS_DOCUMENTOS_GESTAO
from apps.accounts.permissions import grupos_requeridos

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from apps.documents.views import _pode_gerenciar
from apps.documents.models import Documento
from apps.attendance.models import Atendimento
from apps.clinical.exceptions import (
    AvaliacaoStatusInvalidoError,
    PermissaoClinicaError,
    EvolucaoAtendimentoError,
)

from apps.patients.models import Paciente
from apps.clinical.forms import AvaliacaoForm, EvolucaoForm, FimItemFormSet, GoniometriaMedicaoFormSet, ProntuarioForm
from apps.clinical.models import Avaliacao, Evolucao, Prontuario, FimItem, GoniometriaMedicao

from apps.clinical.services import (    
    criar_evolucao as service_criar_evolucao,
    inativar_avaliacao as service_inativar_avaliacao,
    liberar_avaliacao as service_liberar_avaliacao,
    registrar_acesso_prontuario,
    salvar_avaliacao as service_salvar_avaliacao,
    salvar_evolucao as service_salvar_evolucao,
    pode_editar_evolucao as pode_editar_evolucao,
    editar_prontuario as service_editar_prontuario,
    atendimento_em_curso,    
)


MOTIVO_PADRAO_ACESSO = "Visualização do prontuário no módulo clínico"


def _profissional_do_usuario(usuario):
    """Resolve o Profissional vinculado ao usuário (OneToOne)."""
    return getattr(usuario, "profissional", None)


@grupos_requeridos(*GRUPOS_CLINICO_VER)
def detalhe_prontuario(request, paciente_id):
    """Hub do prontuário com abas: dados, avaliacoes, evolucoes."""
    paciente = get_object_or_404(Paciente, pk=paciente_id)
    prontuario = registrar_acesso_prontuario(
        request.user, paciente, motivo=MOTIVO_PADRAO_ACESSO, request=request
    )
    aba = request.GET.get("aba", "dados")
    if aba not in {"dados", "avaliacoes", "evolucoes", "documentos"}:
        aba = "dados"

    avaliacoes = (
        Avaliacao.objects.filter(paciente=paciente)
        .select_related("profissional")
        .order_by("-data")
    )
    evolucoes = (
        Evolucao.objects.filter(paciente=paciente)
        .select_related("profissional")
        .order_by("-created_at")
    )

    atendimento_aberto = (
        Atendimento.objects
        .filter(paciente_id=paciente_id, status=Atendimento.Status.EM_ANDAMENTO)
        .order_by("-data_inicio")
        .first()
    )

    editaveis = {
        ev.pk for ev in evolucoes if pode_editar_evolucao(ev, request.user)
    }
    
    documentos = (
        Documento.objects.filter(paciente=paciente)   # objects já oculta os soft-deletados
        .select_related("profissional")
        .order_by("-created_at")
    )
    #pode_gerenciar = request.user.groups.filter(name__in=GRUPOS_DOCUMENTOS_GESTAO).exists()    
       
    contexto = {
        "paciente": paciente,
        "prontuario": prontuario,
        "aba": aba,
        "avaliacoes": avaliacoes,
        "evolucoes": evolucoes,
        "evolucoes_editaveis": editaveis,
        "atendimento_aberto": atendimento_aberto,
        "documentos": documentos,
        "pode_gerenciar": _pode_gerenciar(request.user),
        "paciente_escopo": paciente.pk,
    }
    return render(request, "clinical/prontuario_detalhe.html", contexto)
    

ITENS_FIM_PADRAO = [
    {"item": i[0], "dominio": "MOTOR" if idx < 13 else "COGNITIVO"}
    for idx, i in enumerate(FimItem.Item.choices)
]


@login_required
def criar_avaliacao(request, paciente_id):
    paciente = get_object_or_404(Paciente, pk=paciente_id)
    profissional = _profissional_do_usuario(request.user)
    if profissional is None:
        messages.error(request, "Seu usuário não está vinculado a um profissional.")
        return redirect("clinical:detalhe_prontuario", paciente_id=paciente.pk)

    if request.method == "POST":
        form = AvaliacaoForm(request.POST)
        fim_set = FimItemFormSet(request.POST)
        gonio_set = GoniometriaMedicaoFormSet(request.POST)

        if form.is_valid() and fim_set.is_valid() and gonio_set.is_valid():
            avaliacao = form.save(commit=False)
            avaliacao.paciente = paciente
            avaliacao.profissional = profissional
            
            with transaction.atomic():
                avaliacao.save()
                fim_set.instance = avaliacao
                fim_set.save()
                gonio_set.instance = avaliacao
                gonio_set.save()

            messages.success(request, "Avaliação registrada (status Pendente).")
            return redirect("clinical:detalhe_prontuario", paciente_id=paciente.pk)
    else:
        form = AvaliacaoForm()
        fim_set = FimItemFormSet(initial=ITENS_FIM_PADRAO)
        gonio_set = GoniometriaMedicaoFormSet()

    return render(request, "clinical/avaliacao_form.html", {
        "form": form,
        "paciente": paciente,
        "fim_set": fim_set,
        "gonio_set": gonio_set,
    })      


@login_required
def criar_evolucao(request, paciente_id):
    paciente = get_object_or_404(Paciente, pk=paciente_id)
    profissional = _profissional_do_usuario(request.user)
    if profissional is None:
        messages.error(request, "Seu usuário não está vinculado a um profissional.")
        return redirect("clinical:detalhe_prontuario", paciente_id=paciente.pk)

    atendimento = None
    atendimento_id = request.POST.get("atendimento") or request.GET.get("atendimento")
    if atendimento_id:
        atendimento = Atendimento.objects.filter(pk=atendimento_id).first()

    if request.method == "POST":
        form = EvolucaoForm(request.POST)
        if form.is_valid():
            service_criar_evolucao(
                request.user, paciente,
                atendimento=atendimento, **form.cleaned_data,
            )
            messages.success(request, "Evolução registrada.")
            return redirect("clinical:detalhe_prontuario", paciente_id=paciente.pk)
    else:
        form = EvolucaoForm()

    return render(request, "clinical/evolucao_form.html",
                  {"form": form, "paciente": paciente, "atendimento": atendimento})


@login_required  # ←  mantenha o decorator que a view já usa hoje
def nova_evolucao(request, paciente_id):
    """View canônica de registro de evolução (SOAP).

    Fonte do atendimento, em ordem de prioridade:
      1. ?atendimento=<id> explícito (botão na ficha da sessão)
      2. atendimento_em_curso() - a sessão aberta do profissional
    """
    paciente = get_object_or_404(Paciente, pk=paciente_id)
    profissional = getattr(request.user, "profissional", None)

    atendimento = None
    atendimento_id = request.POST.get("atendimento") or request.GET.get("atendimento")
    if atendimento_id:
        # A sessão informada precisa pertencer ao mesmo paciente
        atendimento = Atendimento.objects.filter(
            pk=atendimento_id, paciente=paciente
        ).first()

    if atendimento is None and profissional is not None:
        atendimento = atendimento_em_curso(profissional, paciente)

    form = EvolucaoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            service_criar_evolucao(
                request.user, paciente,
                atendimento=atendimento,
                **form.cleaned_data,
            )
            messages.success(request, "Evolução registrada.")
            return redirect("clinical:detalhe_prontuario", paciente.pk)
        except (PermissaoClinicaError, EvolucaoAtendimentoError) as erro:
            messages.error(request, str(erro))

    return render(request, "clinical/evolucao_form.html", {
        "form": form,
        "paciente": paciente,
        "atendimento": atendimento,
    })


@login_required
@require_POST
@grupos_requeridos(*GRUPOS_CLINICO_LIBERAR)
def liberar_avaliacao(request, pk):
    """Libera a avaliação (P → L) e avisa se o FIM estiver incompleto."""
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    try:
        # Captura o retorno: é NESSA instância (select_for_update) que o
        # service anexa o flag "fim_aviso" quando o FIM está incompleto.
        avaliacao_liberada = service_liberar_avaliacao(pk, request.user)

        aviso = getattr(avaliacao_liberada, "fim_aviso", None)
        if aviso:
            messages.warning(
                request,
                f"Avaliação liberada - {aviso}. "
                "Confira se a pontuação está completa.",
            )
        else:
            messages.success(request, "Avaliação liberada.")
    except (AvaliacaoStatusInvalidoError, PermissaoClinicaError) as erro:
        messages.error(request, str(erro))
    return redirect("clinical:detalhe_prontuario", paciente_id=avaliacao.paciente_id)


@login_required
@require_POST
def inativar_avaliacao(request, pk):
    avaliacao = get_object_or_404(Avaliacao, pk=pk)
    motivo = request.POST.get("motivo", "")
    try:
        service_inativar_avaliacao(pk, request.user, motivo=motivo or None)
        messages.success(request, "Avaliação inativada.")
    except (AvaliacaoStatusInvalidoError, PermissaoClinicaError) as erro:
        messages.error(request, str(erro))
    return redirect("clinical:detalhe_prontuario", paciente_id=avaliacao.paciente_id)


@login_required
def detalhe_avaliacao(request, pk):
    """Visualização somente-leitura da avaliação, em qualquer status."""
    avaliacao = get_object_or_404(
        Avaliacao.objects.select_related(
            "paciente", "profissional", "liberado_por", "inativado_por"
        ),
        pk=pk,
    )
    return render(request, "clinical/avaliacao_detalhe.html", {
        "avaliacao": avaliacao,
        "paciente": avaliacao.paciente,
        "pode_editar": avaliacao.status == Avaliacao.Status.PENDENTE,
    })    


@login_required
def editar_evolucao(request, pk):
    evolucao = get_object_or_404(
        Evolucao.objects.select_related("paciente", "profissional"), pk=pk
    )

    if not pode_editar_evolucao(evolucao, request.user):
        messages.warning(
            request,
            "Esta evolução não pode mais ser editada (somente pelo autor, "
            "até 24h após a criação)."
        )
        return redirect("clinical:detalhe_prontuario",
                        paciente_id=evolucao.paciente_id)

    if request.method == "POST":
        form = EvolucaoForm(request.POST, instance=evolucao)
        if form.is_valid():
            service_salvar_evolucao(evolucao, request.user, form.cleaned_data)
            messages.success(request, "Evolução atualizada.")
            return redirect("clinical:detalhe_prontuario",
                            paciente_id=evolucao.paciente_id)
    else:
        form = EvolucaoForm(instance=evolucao)

    return render(request, "clinical/evolucao_form.html",
                  {"form": form, "paciente": evolucao.paciente,
                   "evolucao": evolucao,
                   "atendimento": evolucao.atendimento})

             

@grupos_requeridos(*GRUPOS_CLINICO_EDITAR)
def editar_prontuario(request, paciente_id):
    paciente = get_object_or_404(Paciente, pk=paciente_id)
    prontuario = get_object_or_404(Prontuario, paciente=paciente)

    if request.method == "POST":
        form = ProntuarioForm(request.POST, instance=prontuario)
        if form.is_valid():
            try:
                service_editar_prontuario(prontuario, request.user,
                                          form.cleaned_data)
                messages.success(request, "Prontuário atualizado.")
                return redirect("clinical:detalhe_prontuario",
                                paciente_id=paciente.pk)
            except PermissaoClinicaError as erro:
                messages.error(request, str(erro))
                return redirect("clinical:detalhe_prontuario",
                                paciente_id=paciente.pk)
    else:
        form = ProntuarioForm(instance=prontuario)

    return render(request, "clinical/prontuario_form.html",
                  {"form": form, "paciente": paciente,
                   "prontuario": prontuario})


@login_required
def editar_avaliacao(request, pk):
    avaliacao = get_object_or_404(
        Avaliacao.objects.select_related("paciente"), pk=pk
    )

    if avaliacao.status != Avaliacao.Status.PENDENTE:
        messages.warning(
            request,
            "Esta avaliação não pode mais ser editada (status: "
            f"{avaliacao.get_status_display()})."
        )
        return redirect("clinical:detalhe_prontuario",
                        paciente_id=avaliacao.paciente_id)

    if request.method == "POST":
        form = AvaliacaoForm(request.POST, instance=avaliacao)
        fim_set = FimItemFormSet(request.POST, instance=avaliacao)
        gonio_set = GoniometriaMedicaoFormSet(request.POST, instance=avaliacao)
        if form.is_valid() and fim_set.is_valid() and gonio_set.is_valid():
            with transaction.atomic():
                service_salvar_avaliacao(avaliacao, request.user,
                                         form.cleaned_data)
                fim_set.save()
                gonio_set.save()
            messages.success(request, "Avaliação salva.")
            return redirect("clinical:detalhe_prontuario",
                            paciente_id=avaliacao.paciente_id)
    else:
        form = AvaliacaoForm(instance=avaliacao)
        fim_set = FimItemFormSet(instance=avaliacao)
        gonio_set = GoniometriaMedicaoFormSet(instance=avaliacao)

    return render(request, "clinical/avaliacao_form.html",
                  {"form": form, "paciente": avaliacao.paciente,
                   "avaliacao": avaliacao,
                   "fim_set": fim_set, "gonio_set": gonio_set})




#grafico de evolução de goniometria
PALETA = ["#0d6efd", "#dc3545", "#198754", "#ffc107",
          "#6f42c1", "#fd7e14", "#20c997", "#0dcaf0"]

@login_required
def evolucao_goniometria(request, paciente_id):
    paciente = get_object_or_404(Paciente, pk=paciente_id)

    # 1) Todas as medições do paciente, ordenadas pela data da avaliação
    medicoes = (
        GoniometriaMedicao.objects
        .filter(avaliacao__paciente=paciente)
        .select_related("avaliacao")
        .order_by("avaliacao__data", "articulacao", "movimento", "lado")
    )

    # 2) Agrupa por série: "Ombro · Flexão · Direito" é uma série
    grupos = {}
    for m in medicoes:
        rotulo = (f"{m.get_articulacao_display()} · "
                  f"{m.get_movimento_display()} · "
                  f"{m.get_lado_display()}")
        grupos.setdefault(rotulo, []).append({
            "data": m.avaliacao.data.strftime("%d/%m/%Y"),
            "graus": m.graus,
        })

    # 3) Converte para o formato que o Chart.js entende
    series = [
        {"rotulo": rotulo, "cor": PALETA[i % len(PALETA)], "pontos": pontos}
        for i, (rotulo, pontos) in enumerate(grupos.items())
    ]

    return render(request, "clinical/evolucao_goniometria.html", {
        "paciente": paciente,
        "series_json": json.dumps(series),
    })
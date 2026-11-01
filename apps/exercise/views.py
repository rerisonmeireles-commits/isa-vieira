from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from apps.accounts.constants import GRUPOS_EXERCICIOS_EDITAR, GRUPOS_EXERCICIOS_VER
from apps.accounts.decorators import grupos_requeridos
from django.views.decorators.http import require_POST

from apps.exercise.forms import (
    ExecucaoExercicioForm,
    ExercicioForm,
    PrescricaoExercicioFormSet,
    PrescricaoForm,
)
from apps.exercise.models import (
    ExecucaoExercicio,
    Exercicio,
    Prescricao,
    PrescricaoExercicio,
)
from apps.exercise.services import (
    ExercicioStatusInvalidoError,
    PermissaoExercicioError,
    atualizar_exercicio as service_atualizar_exercicio,
    cancelar_prescricao as service_cancelar_prescricao,
    criar_exercicio as service_criar_exercicio,
    criar_prescricao as service_criar_prescricao,
    encerrar_prescricao as service_encerrar_prescricao,
    inativar_exercicio as service_inativar_exercicio,
    normalizar_ordem,
    registrar_execucao_clinica as service_registrar_execucao,
    reordenar_itens as service_reordenar,
    editar_prescricao as service_editar_prescricao,
)

# ---------------------------------------------------------------------------
# Catálogo de exercícios
# ---------------------------------------------------------------------------
@grupos_requeridos(*GRUPOS_EXERCICIOS_VER)
def lista_exercicios(request):
    exercicios = Exercicio.objects.all().order_by("categoria", "nome")
    categoria = request.GET.get("categoria", "")
    if categoria:
        exercicios = exercicios.filter(categoria=categoria)
    return render(request, "exercise/exercicio_lista.html", {
        "exercicios": exercicios,
        "categoria_atual": categoria,
        "categorias": Exercicio.Categoria.choices,
    })



@grupos_requeridos(*GRUPOS_EXERCICIOS_EDITAR)
def form_exercicio(request, pk=None):
    exercicio = get_object_or_404(Exercicio, pk=pk) if pk else None
    form = ExercicioForm(request.POST or None,
                         request.FILES or None, instance=exercicio)
    if request.method == "POST" and form.is_valid():
        try:
            if exercicio:
                service_atualizar_exercicio(exercicio, request.user,
                                            form.cleaned_data)
                messages.success(request, "Exercício atualizado.")
            else:
                service_criar_exercicio(request.user, form.cleaned_data)
                messages.success(request, "Exercício cadastrado.")
            return redirect("exercise:lista_exercicios")
        except PermissaoExercicioError as erro:
            messages.error(request, str(erro))
    return render(request, "exercise/exercicio_form.html", {
        "form": form, "exercicio": exercicio,
    })

@require_POST
@grupos_requeridos(*GRUPOS_EXERCICIOS_EDITAR)
def inativar_exercicio(request, pk):
    exercicio = get_object_or_404(Exercicio, pk=pk)
    if request.method == "POST":
        try:
            service_inativar_exercicio(exercicio, request.user)
            messages.success(request, "Exercício inativado.")
        except PermissaoExercicioError as erro:
            messages.error(request, str(erro))
    return redirect("exercise:lista_exercicios")


# ---------------------------------------------------------------------------
# Prescrições
# ---------------------------------------------------------------------------
@grupos_requeridos(*GRUPOS_EXERCICIOS_VER)
def lista_prescricoes(request):
    prescricoes = (
        Prescricao.objects
        .select_related("paciente", "profissional")
        .order_by("-data")
    )
    status = request.GET.get("status", "")
    if status:
        prescricoes = prescricoes.filter(status=status)
    return render(request, "exercise/prescricao_lista.html", {
        "prescricoes": prescricoes,
        "status_atual": status,
        "status_opcoes": Prescricao.Status.choices,
    })


@grupos_requeridos(*GRUPOS_EXERCICIOS_VER)
def detalhe_prescricao(request, pk):
    prescricao = get_object_or_404(
        Prescricao.objects.select_related("paciente", "profissional"), pk=pk
    )
    return render(request, "exercise/prescricao_detalhe.html", {
        "prescricao": prescricao,
    })


@grupos_requeridos(*GRUPOS_EXERCICIOS_EDITAR)
def form_prescricao(request, pk=None):
    prescricao = get_object_or_404(
        Prescricao.objects.select_related("paciente"), pk=pk
    ) if pk else None

    if prescricao and prescricao.status != Prescricao.Status.ATIVA:
        messages.warning(
            request,
            "Apenas prescrições Ativas podem ser editadas. "
            f"Status atual: {prescricao.get_status_display()}."
        )
        return redirect("exercise:detalhe_prescricao", pk=prescricao.pk)

    form = PrescricaoForm(request.POST or None, instance=prescricao)
    item_set = PrescricaoExercicioFormSet(
        request.POST or None, instance=prescricao
    )

    if request.method == "POST" and form.is_valid() and item_set.is_valid():
        try:
            with transaction.atomic():
                if prescricao:
                    prescricao = service_editar_prescricao(
                        request.user, prescricao, form.cleaned_data
                    )
                else:
                    prescricao = service_criar_prescricao(
                        request.user, form.cleaned_data
                    )
                item_set.instance = prescricao
                item_set.save()
                normalizar_ordem(prescricao)
            messages.success(request, "Prescrição salva.")
            return redirect("exercise:detalhe_prescricao", pk=prescricao.pk)
        except (PermissaoExercicioError, ExercicioStatusInvalidoError) as erro:
            messages.error(request, str(erro))

    return render(request, "exercise/prescricao_form.html", {
        "form": form, "item_set": item_set, "prescricao": prescricao,
    })

@require_POST
@grupos_requeridos(*GRUPOS_EXERCICIOS_EDITAR)
def encerrar_prescricao(request, pk):
    prescricao = get_object_or_404(Prescricao, pk=pk)
    if request.method == "POST":
        try:
            service_encerrar_prescricao(
                prescricao, request.user,
                motivo=request.POST.get("motivo", ""),
            )
            messages.success(request, "Prescrição encerrada.")
        except (PermissaoExercicioError, ExercicioStatusInvalidoError) as erro:
            messages.error(request, str(erro))
    return redirect("exercise:detalhe_prescricao", pk=prescricao.pk)

@require_POST
@grupos_requeridos(*GRUPOS_EXERCICIOS_EDITAR)
def cancelar_prescricao(request, pk):
    prescricao = get_object_or_404(Prescricao, pk=pk)
    if request.method == "POST":
        try:
            service_cancelar_prescricao(
                prescricao, request.user,
                motivo=request.POST.get("motivo", ""),
            )
            messages.success(request, "Prescrição cancelada.")
        except (PermissaoExercicioError, ExercicioStatusInvalidoError) as erro:
            messages.error(request, str(erro))
    return redirect("exercise:detalhe_prescricao", pk=prescricao.pk)

@require_POST
@grupos_requeridos(*GRUPOS_EXERCICIOS_EDITAR)
def reordenar_itens(request, pk):
    prescricao = get_object_or_404(Prescricao, pk=pk)
    if request.method == "POST":
        nova_ordem = request.POST.getlist("ordem")
        try:
            service_reordenar(prescricao, request.user, nova_ordem)
            messages.success(request, "Itens reordenados.")
        except (PermissaoExercicioError, ExercicioStatusInvalidoError) as erro:
            messages.error(request, str(erro))
    return redirect("exercise:detalhe_prescricao", pk=prescricao.pk)


# ---------------------------------------------------------------------------
# Execução (clínica)
# ---------------------------------------------------------------------------

@grupos_requeridos(*GRUPOS_EXERCICIOS_EDITAR)
def registrar_execucao(request, item_pk):
    item = get_object_or_404(
        PrescricaoExercicio.objects.select_related(
            "prescricao", "prescricao__paciente"
        ),
        pk=item_pk,
    )
    form = ExecucaoExercicioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            service_registrar_execucao(
                request.user, item, item.prescricao.paciente,
                form.cleaned_data,
            )
            messages.success(request, "Execução registrada.")
            return redirect("exercise:detalhe_prescricao",
                            pk=item.prescricao_id)
        except PermissaoExercicioError as erro:
            messages.error(request, str(erro))
    return render(request, "exercise/execucao_form.html", {
        "form": form, "item": item,
    })
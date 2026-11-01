"""Regras de negócio do fluxo de Atendimento (check-in / check-out).

Camada de domínio puro - SEM RBAC (autorização vive nas views do app
scheduling, via @grupos_requeridos + GRUPOS_AGENDA).

Contrato:
    iniciar_atendimento(*, agendamento_id, usuario=None)
        Check-in: cria o Atendimento EM_ANDAMENTO a partir de um
        Agendamento CONFIRMADO e move o agendamento para EM_ATENDIMENTO.
    finalizar_atendimento(*, atendimento_id, observacoes="", usuario=None)
        Check-out: conclui o Atendimento, move o agendamento para ATENDIDO
        e dispara gerar_conta_do_atendimento na mesma transação.

Nota: o caminho de falta (FALTOU) é tratado apenas no Agendamento via
alterar_status - não cria Atendimento com NAO_REALIZADO.
"""
from django.db import transaction
from django.utils import timezone

from apps.attendance.exceptions import AtendimentoError
from apps.attendance.models import Atendimento
from apps.scheduling.models import Agendamento
from apps.financial.services import gerar_conta_do_atendimento


@transaction.atomic
def iniciar_atendimento(*, agendamento_id, usuario=None):
    """Check-in: cria o Atendimento e move o agendamento para EM_ATENDIMENTO.

    Regras:
      - Apenas agendamentos CONFIRMADOS iniciam atendimento.
      - Um agendamento só pode ter UM atendimento (OneToOne).
    """
    agendamento = (
        Agendamento.objects
        .select_for_update(of=("self",))   # ← adicionar of=("self",)
        .select_related("paciente", "profissional", "sala", "tipo_atendimento")
        .get(pk=agendamento_id)
    )    

    if agendamento.status != Agendamento.Status.CONFIRMADO:
        raise AtendimentoError(
            f"Agendamento {agendamento.get_status_display()} não pode iniciar "
            "atendimento - apenas agendamentos CONFIRMADOS."
        )

    if hasattr(agendamento, "atendimento"):
        raise AtendimentoError("Este agendamento já possui um atendimento registrado.")

    atendimento = Atendimento.objects.create(
        agendamento=agendamento,
        paciente=agendamento.paciente,
        profissional=agendamento.profissional,
        sala=agendamento.sala,
        tipo_atendimento=agendamento.tipo_atendimento,
        data_inicio=timezone.now(),
        status=Atendimento.Status.EM_ANDAMENTO,
    )

    agendamento.status = Agendamento.Status.EM_ATENDIMENTO
    agendamento.save(update_fields=["status", "updated_at"])

    return atendimento


@transaction.atomic
def finalizar_atendimento(*, atendimento_id, observacoes="", usuario=None):
    """Check-out: finaliza o Atendimento e move o agendamento para ATENDIDO.

    Regras:
      - Apenas atendimentos EM_ANDAMENTO são finalizados.
      - O agendamento vinculado vai para ATENDIDO na mesma transação.

    TODO(fase financeiro): ao finalizar, gerar a ContaReceber do atendimento
    (valor do tipo_atendimento ou do convênio) - o hook entra aqui.
    """
    atendimento = (
        Atendimento.objects
        .select_for_update(of=("self",))
        .select_related("agendamento__slot__agenda")
        .get(pk=atendimento_id)
    )

    if atendimento.status != Atendimento.Status.EM_ANDAMENTO:
        raise AtendimentoError(
            f"Atendimento {atendimento.get_status_display()} não pode ser "
            "finalizado - apenas atendimentos EM ANDAMENTO."
        )

    atendimento.status = Atendimento.Status.CONCLUIDO
    atendimento.data_fim = timezone.now()
    if observacoes:
        atendimento.observacoes = observacoes
    atendimento.save(update_fields=["status", "data_fim", "observacoes", "updated_at"])

    agendamento = atendimento.agendamento
    agendamento.status = Agendamento.Status.ATENDIDO
    agendamento.save(update_fields=["status", "updated_at"])

    # Gera a conta a receber (faturamento) na mesma transação.
    gerar_conta_do_atendimento(atendimento=atendimento)

    atendimento.sem_evolucao = not atendimento.evolucoes.exists()   
    
    return atendimento
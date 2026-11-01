"""Exceções do domínio de atendimento (check-in/check-out)."""

from apps.base.exceptions import AppError


class AtendimentoError(AppError):
    """Erro do fluxo de atendimento - estado inválido do agendamento
    ou do atendimento."""
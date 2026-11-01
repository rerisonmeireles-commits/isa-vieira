"""Exceções de negócio do domínio de agenda.

Erros de negócio são exceções - nunca retornos silenciosos. A view captura
AgendaError e devolve a mensagem ao usuário; qualquer outra exceção é bug.
"""


class AgendaError(Exception):
    """Erro de negócio base do domínio de agenda."""
    codigo = "AGENDA_ERRO"

    def __init__(self, mensagem, detalhes=None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhes = detalhes or {}

    def __str__(self):
        return self.mensagem


class SlotIndisponivelError(AgendaError):
    codigo = "SLOT_INDISPONIVEL"


class ConflitoProfissionalError(AgendaError):
    codigo = "CONFLITO_PROFISSIONAL"


class ConflitoSalaError(AgendaError):
    codigo = "CONFLITO_SALA"


class ForaDoHorarioFuncionamentoError(AgendaError):
    codigo = "FORA_HORARIO_FUNCIONAMENTO"


class ProfissionalIndisponivelError(AgendaError):
    codigo = "PROFISSIONAL_INDISPONIVEL"


class AgendaBloqueadaError(AgendaError):
    codigo = "AGENDA_BLOQUEADA"


class FeriadoError(AgendaError):
    codigo = "FERIADO"


class DuracaoIncompativelError(AgendaError):
    codigo = "DURACAO_INCOMPATIVEL"


class ForaDaJanelaAgendamentoError(AgendaError):
    codigo = "FORA_JANELA_AGENDAMENTO"


class TransicaoStatusInvalidaError(AgendaError):
    codigo = "TRANSICAO_INVALIDA"
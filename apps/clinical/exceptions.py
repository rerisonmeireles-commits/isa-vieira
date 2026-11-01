"""Exceções base do projeto - raiz única de todos os domínios.

Todo app define suas exceções herdando de AppError. Nenhum app
importa exceções de outro app - a única dependência permitida é
apps.base, que não depende de ninguém.
"""


"""Exceções do domínio clínico."""

from apps.base.exceptions import AppError


class ClinicalError(AppError):
    """Erro base do domínio clínico."""


class AvaliacaoStatusInvalidoError(ClinicalError):
    """Transição de status da Avaliação não permitida."""


class PermissaoClinicaError(ClinicalError):
    """Usuário sem permissão para a ação clínica solicitada
    (editar avaliação/prontuário, liberar, inativar, evoluir)."""


class ProntuarioInexistenteError(ClinicalError):
    """Paciente sem prontuário (não deveria ocorrer com o signal ativo)."""


class EvolucaoAtendimentoError(ClinicalError):
    """Vínculo evolução ↔ atendimento inválido (posse ou estado da sessão)."""
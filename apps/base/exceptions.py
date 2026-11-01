"""Exceções base do projeto - raiz única de todos os domínios.

Todo app define suas exceções herdando de AppError. Nenhum app
importa exceções de outro app - a única dependência permitida é
apps.base, que não depende de ninguém.
"""


class AppError(Exception):
    """Erro base de todos os domínios do sistema."""
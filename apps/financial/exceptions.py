"""Exceções de negócio do domínio Financeiro."""


class FinanceiroError(Exception):
    """Erro de regra de negócio com mensagem amigável para o usuário."""

    def __init__(self, mensagem):
        self.mensagem = mensagem
        super().__init__(mensagem)
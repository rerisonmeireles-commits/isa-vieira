"""Filtros de máscara para exibição de telefones no template."""

import re

from django import template

register = template.Library()


def _so_digitos(valor):
    """Extrai apenas os dígitos - aceita número cru ou já com máscara."""
    return re.sub(r"\D", "", valor or "")


@register.filter
def telefone(valor):
    """Formata um número para exibição:
    (11) 98765-4321 (celular com DDD) | (11) 3322-4455 (fixo com DDD)
    98765-4321 (celular sem DDD)     | 3322-4455 (fixo sem DDD)
    Se não reconhecer o padrão, devolve o valor original.
    """
    digitos = _so_digitos(valor)
    if len(digitos) == 11:      # celular com DDD
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    if len(digitos) == 10:      # fixo com DDD
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    if len(digitos) == 9:       # celular sem DDD
        return f"{digitos[:5]}-{digitos[5:]}"
    if len(digitos) == 8:       # fixo sem DDD
        return f"{digitos[:4]}-{digitos[4:]}"
    return valor
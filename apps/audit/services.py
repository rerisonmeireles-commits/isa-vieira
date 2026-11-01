"""Serviço de registro de trilha de auditoria.

Complementa o django-simple-history: o simple_history registra alterações
de campo por campo automaticamente; este serviço registra EVENTOS de
negócio com contexto (quem, de onde, por quê).
"""
from __future__ import annotations

import logging

from apps.audit.models import LogAuditoria

logger = logging.getLogger(__name__)


def _extrair_ip(request) -> str | None:
    """IP real do cliente, respeitando proxy reverso."""
    if request is None:
        return None
    encaminhado = request.META.get("HTTP_X_FORWARDED_FOR")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def registrar_auditoria(
    *,
    usuario,
    acao: str,
    tabela: str,
    registro_id: int,
    dados_antes: dict | None = None,
    dados_depois: dict | None = None,
    motivo: str = "",
    request=None,
) -> LogAuditoria:
    """Registra um evento de negócio na trilha de auditoria.

    NÃO levanta exceção em caso de falha: auditoria é best-effort e nunca
    pode derrubar a operação de negócio que ela observa. Falhas vão para
    o log estruturado.
    """
    try:
        return LogAuditoria.objects.create(
            usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
            acao=acao,
            tabela=tabela,
            registro_id=registro_id,
            dados_antes=dict(dados_antes or {}),   # cópia defensiva
            dados_depois=dict(dados_depois or {}),
            motivo=motivo[:255],
            ip=_extrair_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT", "")[:1000] if request else ""),
        )
    except Exception:
        logger.exception(
            "Falha ao registrar auditoria acao=%s tabela=%s registro_id=%s",
            acao, tabela, registro_id,
        )
        return None
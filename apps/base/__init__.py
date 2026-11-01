"""Pacote base do projeto - modelos fundamentais e exceções raiz."""

from .models import (
    TimeStampedModel,
    SoftDeleteModel,
    SoftDeleteQuerySet,
    SoftDeleteManager,
)
from .exceptions import AppError

__all__ = [
    "TimeStampedModel",
    "SoftDeleteModel",
    "SoftDeleteQuerySet",
    "SoftDeleteManager",
    "AppError",
]
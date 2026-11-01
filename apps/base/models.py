"""Modelos fundamentais do projeto: auditoria temporal e soft delete.

IMPORTANTE - este módulo NÃO é registrado em INSTALLED_APPS e não deve ser.
Todos os modelos aqui são abstratos: não geram tabela, não precisam de
app_label. Registrar `apps.base` quebra o boot porque o `__init__.py`
importa este módulo durante `AppConfig.create()`, quando o registry ainda
não está pronto (AppRegistryNotReady).
"""

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Adiciona created_at e updated_at automaticamente em todas as tabelas."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Mantido aqui por compatibilidade de schema: Agenda, SlotAgenda e
    # BloqueioAgenda já possuem esta coluna no banco. Apenas Agendamento
    # usa o comportamento de soft delete de fato.
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet com soft delete reversível."""

    def delete(self):
        """Soft delete em massa: marca deleted_at, nunca remove a linha."""
        return self.update(deleted_at=timezone.now())

    def restore(self):
        """Reverte o soft delete em massa."""
        return self.update(deleted_at=None)

    def hard_delete(self):
        """Exclusão física - uso restrito a rotinas de saneamento."""
        return super().delete()


class SoftDeleteManager(models.Manager):
    """Manager default: esconde registros soft-deletados em toda consulta."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(
            deleted_at__isnull=True
        )


class SoftDeleteModel(TimeStampedModel):
    """Soft delete: dados clínicos/financeiros nunca são apagados (LGPD/COFFITO)."""

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        # ⚠️ OBRIGATÓRIO. Sem abstract = True, o Django trata esta classe
        # como modelo concreto e exige app_label - erro que derrubou o boot.
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """Soft delete unitário. Não dispara DELETE físico."""
        self.deleted_at = timezone.now()
        self.save(using=using)

    def restore(self, using=None):
        """Reverte o soft delete unitário."""
        self.deleted_at = None
        self.save(using=using)

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)
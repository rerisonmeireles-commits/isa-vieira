"""Reconstrói o M2M slots_ocupados de agendamentos legados.

Escopo: registros CANCELADO/REMARCADO com slots_ocupados vazio, ressonância
do período em que cancelar_agendamento() chamava slots_ocupados.clear().
Não altera status de slot - apenas restaura o vínculo histórico.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.scheduling.models import Agendamento, SlotAgenda
from apps.scheduling.services.agendamento import _calcular_bloco


class Command(BaseCommand):
    help = "Reconstrói slots_ocupados de agendamentos legados com bloco vazio."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", default=False)
        parser.add_argument("--pk", type=int, nargs="*", default=None)

    def handle(self, *args, **opts):
        qs = (Agendamento.all_objects
              .filter(status__in=Agendamento.STATUS_LIBERAM_SLOT,
                      slots_ocupados__isnull=True)
              .select_related("slot", "slot__agenda", "tipo_atendimento")
              .order_by("pk"))
        if opts["pk"]:
            qs = qs.filter(pk__in=opts["pk"])

        aplicados, pulados = 0, 0
        with transaction.atomic():
            for ag in qs:
                dur = ag.duracao_minutos or ag.tipo_atendimento.duracao_minutos
                try:
                    bloco = _calcular_bloco(ag.slot, dur)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f"ag {ag.pk} NAO reconstruivel: {type(e).__name__}"))
                    pulados += 1
                    continue

                ids = [s.pk for s in bloco]
                bloqueantes = (
                    SlotAgenda.objects.filter(pk__in=ids)
                    .exclude(status=SlotAgenda.Status.LIVRE)
                    .exists()
                    or SlotAgenda.objects.filter(pk__in=ids)
                    .filter(agendamentos_bloco__in=Agendamento.objects.exclude(
                        status__in=Agendamento.STATUS_LIBERAM_SLOT))
                    .exclude(agendamentos_bloco__pk=ag.pk)
                    .exists()
                )
                if bloqueantes:
                    self.stdout.write(self.style.WARNING(
                        f"ag {ag.pk} PULADO: bloco nao integralmente livre"))
                    pulados += 1
                    continue

                self.stdout.write(
                    f"ag {ag.pk} -> {len(bloco)} slots "
                    f"{bloco[0].hora_inicio}-{bloco[-1].hora_fim}")

                if not opts["dry_run"]:
                    ag.slots_ocupados.set(bloco)
                aplicados += 1

            if opts["dry_run"]:
                transaction.set_rollback(True)

        rotulo = "SIMULADOS" if opts["dry_run"] else "APLICADOS"
        self.stdout.write(self.style.SUCCESS(
            f"{rotulo}: {aplicados} | pulados: {pulados}"))
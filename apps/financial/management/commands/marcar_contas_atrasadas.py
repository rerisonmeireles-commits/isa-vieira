from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.financial.models import ContaReceber
from apps.financial.services import _recalcular_status_conta


class Command(BaseCommand):
    help = "Recalcula contas vencidas e não pagas → ATRASADA (ideal: diário)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Apenas conta; não altera nada."
        )

    def handle(self, *args, **options):
        hoje = timezone.localdate()
        alvo = (
            ContaReceber.objects
            .filter(
                status__in=[
                    ContaReceber.Status.ABERTA,
                    ContaReceber.Status.PARCIAL,
                    ContaReceber.Status.ATRASADA,
                ],
                data_vencimento__lt=hoje,
            )
            .prefetch_related("pagamentos")
        )

        if options["dry_run"]:
            self.stdout.write(f"{alvo.count()} conta(s) vencida(s) seriam recalculada(s).")
            return

        total = 0
        for conta in alvo:
            _recalcular_status_conta(conta)
            total += 1
        self.stdout.write(self.style.SUCCESS(f"{total} conta(s) recalculada(s)."))
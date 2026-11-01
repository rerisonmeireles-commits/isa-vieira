from django.core.management.base import BaseCommand
from django.db.models import Prefetch
from django.utils import timezone

from apps.scheduling.models import Agendamento, SlotAgenda

ATIVOS = [
    Agendamento.Status.AGENDADO,
    Agendamento.Status.CONFIRMADO,
    Agendamento.Status.EM_ATENDIMENTO,
    Agendamento.Status.ATENDIDO,
    Agendamento.Status.FALTOU,
]


class Command(BaseCommand):
    help = "Libera slots OCUPADO sem agendamento ativo. Padrão: dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--gravar", action="store_true", help="Aplica a correção.")
        parser.add_argument(
            "--incluir-futuros", action="store_true",
            help="Inclui slots de datas futuras.",
        )

    def handle(self, *args, **opts):
        hoje = timezone.localdate()
        qs = (
            SlotAgenda.objects.filter(status=SlotAgenda.Status.OCUPADO)
            .select_related("agenda")
            .prefetch_related(
                Prefetch(
                    "agendamentos",
                    queryset=Agendamento.objects.filter(status__in=ATIVOS),
                    to_attr="_agendamentos_ativos",
                ),
                Prefetch(
                    "agendamentos_bloco",
                    queryset=Agendamento.objects.filter(status__in=ATIVOS),
                    to_attr="_agendamentos_bloco",
                ),
            )
        )
        if not opts["incluir_futuros"]:
            qs = qs.filter(agenda__data__lt=hoje)

        # Órfão real = sem dono NOS DOIS lados (FK principal e M2M bloco).
        alvos = [
            s for s in qs
            if not getattr(s, "_agendamentos_ativos", None)
            and not getattr(s, "_agendamentos_bloco", None)
        ]

        if not alvos:
            self.stdout.write(self.style.SUCCESS("Nenhum slot órfão encontrado."))
            return

        for s in alvos:
            self.stdout.write(f"  {s.pk} {s.agenda.data} {s.hora_inicio}")

        if not opts["gravar"]:
            self.stdout.write(self.style.WARNING(
                f"DRY-RUN: {len(alvos)} slot(s) seriam liberados. Use --gravar."
            ))
            return

        n = SlotAgenda.objects.filter(
            pk__in=[s.pk for s in alvos], status=SlotAgenda.Status.OCUPADO
        ).update(status=SlotAgenda.Status.LIVRE)
        self.stdout.write(self.style.SUCCESS(f"Liberados: {n}"))
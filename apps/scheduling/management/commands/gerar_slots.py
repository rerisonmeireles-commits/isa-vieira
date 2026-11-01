"""Materializa a grade dos próximos N dias.

Rode diariamente (cron / Task Scheduler / systemd timer). Exemplo:
    python manage.py gerar_slots --dias 30
"""

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.scheduling.services import gerar_slots_todos_profissionais


class Command(BaseCommand):
    help = "Gera os slots de agenda dos próximos N dias a partir da disponibilidade."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=30, help="Horizonte em dias (padrão: 30).")
        parser.add_argument("--inicio", type=str, default=None, help="Data inicial AAAA-MM-DD (padrão: hoje).")
        parser.add_argument("--profissional", type=int, default=None, help="ID de um profissional específico.")

    def handle(self, *args, **options):
        data_inicio = None
        if options["inicio"]:
            try:
                data_inicio = datetime.strptime(options["inicio"], "%Y-%m-%d").date()
            except ValueError:
                raise CommandError("Formato de data inválido. Use AAAA-MM-DD.")

        resultado = gerar_slots_todos_profissionais(
            data_inicio=data_inicio,
            dias=options["dias"],
            profissional_id=options["profissional"],
        )

        self.stdout.write(self.style.SUCCESS(
            f"Grade gerada: {resultado['agendas']} agendas "
            f"para {resultado['profissionais']} profissional(is)."
        ))
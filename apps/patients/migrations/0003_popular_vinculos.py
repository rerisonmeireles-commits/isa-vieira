"""Popula paciente_profissional a partir dos agendamentos existentes.

Cada par (paciente, profissional) que já teve agendamento ganha um
vínculo ativo com papel EQUIPE. Idempotente: get_or_create evita
duplicata se a migração rodar duas vezes.

Separado do 0002 (estrutura) para que uma falha na população não
reverta a criação da tabela.
"""
from django.db import migrations


def popular_vinculos(apps, schema_editor):
    Agendamento = apps.get_model("scheduling", "Agendamento")
    PacienteProfissional = apps.get_model("patients", "PacienteProfissional")

    pares = (
        Agendamento.objects.filter(deleted_at__isnull=True)
        .values_list("paciente_id", "profissional_id")
        .distinct()
    )

    criados = 0
    for paciente_id, profissional_id in pares.iterator(chunk_size=500):
        _, criado = PacienteProfissional.objects.get_or_create(
            paciente_id=paciente_id,
            profissional_id=profissional_id,
            ativo=True,
            defaults={"papel": "E"},
        )
        if criado:
            criados += 1

    print(f"\n  → {criados} vínculos criados a partir de agendamentos.")


def reverter(apps, schema_editor):
    """Reverte apenas os vínculos criados por esta migração.

    Não apaga vínculos manuais criados depois — só os que têm
    papel EQUIPE e foram criados sem criado_por (marca da migração).
    """
    PacienteProfissional = apps.get_model("patients", "PacienteProfissional")
    PacienteProfissional.objects.filter(
        papel="E", criado_por__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0002_paciente_profissional"),
        ("scheduling", "0010_uq_slot_agenda_hora_parcial"),
    ]

    operations = [
        migrations.RunPython(popular_vinculos, reverter),
    ]
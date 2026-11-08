"""Adiciona ck_vinculo_ativo_sem_fim.

Fecha a invariante: ativo=True implica fim_vigencia IS NULL.
Antes desta migração, era possível ter vínculo ativo com data de
encerramento preenchida — estado contraditório.
"""
from django.db import migrations, models


def sanear_vinculos_inconsistentes(apps, schema_editor):
    """Zera fim_vigencia de vínculos ativos que o tenham preenchido.

    Roda antes da CHECK para que a constraint possa ser criada sem
    falhar em dados legados.
    """
    PacienteProfissional = apps.get_model("patients", "PacienteProfissional")
    PacienteProfissional.objects.filter(
        ativo=True, fim_vigencia__isnull=False,
    ).update(fim_vigencia=None)


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0003_popular_vinculos"),
    ]

    operations = [
        migrations.RunPython(sanear_vinculos_inconsistentes, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="pacienteprofissional",
            constraint=models.CheckConstraint(
                check=models.Q(ativo=False) | models.Q(fim_vigencia__isnull=True),
                name="ck_vinculo_ativo_sem_fim",
            ),
        ),
    ]
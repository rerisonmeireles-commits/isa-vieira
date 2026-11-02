import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinical", "0011_imutabilidade_filhos_avaliacao"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Status com default PENDENTE (evoluções existentes nascem pendentes)
        migrations.AddField(
            model_name="evolucao",
            name="status",
            field=models.CharField(
                choices=[
                    ("L", "Liberada"),
                    ("P", "Pendente de Liberação"),
                    ("I", "Inativada"),
                ],
                default="P",
                max_length=1,
            ),
        ),
        # 2. Rastreio de liberação
        migrations.AddField(
            model_name="evolucao",
            name="liberado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="evolucoes_liberadas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="evolucao",
            name="liberado_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        # 3. Rastreio de inativação
        migrations.AddField(
            model_name="evolucao",
            name="inativado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="evolucoes_inativadas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="evolucao",
            name="inativado_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        # 4. Constraints espelhando a Avaliacao
        migrations.AddConstraint(
            model_name="evolucao",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        status="L",
                        liberado_por__isnull=False,
                        liberado_em__isnull=False,
                    )
                    | ~models.Q(status="L")
                ),
                name="ck_evolucao_liberada_com_rastreio",
            ),
        ),
        migrations.AddConstraint(
            model_name="evolucao",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        status="I",
                        inativado_por__isnull=False,
                        inativado_em__isnull=False,
                    )
                    | ~models.Q(status="I")
                ),
                name="ck_evolucao_inativada_com_rastreio",
            ),
        ),
    ]
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinical", "0016_evolucao_retificacao"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="evolucao",
            constraint=models.UniqueConstraint(
                fields=["retifica_evolucao"],
                condition=models.Q(retifica_evolucao__isnull=False),
                name="ck_evolucao_retificacao_unica",
            ),
        ),
    ]
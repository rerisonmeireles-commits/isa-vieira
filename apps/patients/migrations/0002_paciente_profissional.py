# apps/patients/migrations/0002_paciente_profissional.py
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0001_initial"),
        ("professionals", "0003_alter_profissional_options_ausencia_deleted_at_and_more"),
        ("accounts", "0003_perfis_iniciais"),
    ]

    operations = [
        migrations.CreateModel(
            name="PacienteProfissional",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("papel", models.CharField(choices=[("R", "Profissional de referência"), ("E", "Equipe de atendimento"), ("I", "Interconsulta")], default="E", max_length=1)),
                ("ativo", models.BooleanField(default=True)),
                ("inicio_vigencia", models.DateField(default=django.utils.timezone.localdate)),
                ("fim_vigencia", models.DateField(blank=True, null=True)),
                ("observacoes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="accounts.usuario")),
                ("paciente", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="vinculos_profissionais", to="patients.paciente")),
                ("profissional", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="vinculos_pacientes", to="professionals.profissional")),
            ],
            options={
                "verbose_name": "Vínculo paciente-profissional",
                "verbose_name_plural": "Vínculos paciente-profissional",
            },
        ),
        migrations.AddConstraint(
            model_name="pacienteprofissional",
            constraint=models.UniqueConstraint(
                condition=models.Q(("ativo", True), ("deleted_at__isnull", True)),
                fields=("paciente", "profissional"),
                name="uq_vinculo_ativo_paciente_profissional",
            ),
        ),
        migrations.AddConstraint(
            model_name="pacienteprofissional",
            constraint=models.CheckConstraint(
                check=models.Q(("fim_vigencia__isnull", True)) | models.Q(("fim_vigencia__gte", models.F("inicio_vigencia"))),
                name="ck_vinculo_vigencia_coerente",
            ),
        ),
        migrations.AddIndex(
            model_name="pacienteprofissional",
            index=models.Index(fields=["paciente", "ativo"], name="ix_vinculo_paciente_ativo"),
        ),
        migrations.AddIndex(
            model_name="pacienteprofissional",
            index=models.Index(fields=["profissional", "ativo"], name="ix_vinculo_profissional_ativo"),
        ),
    ]
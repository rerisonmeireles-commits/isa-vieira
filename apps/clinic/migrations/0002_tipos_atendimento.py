"""Data migration: tipos de atendimento padrão da clínica."""

from django.db import migrations


TIPOS_ATENDIMENTO = [
    {"nome": "Avaliação Inicial", "descricao": "Anamnese, exame físico e definição do plano terapêutico.", "duracao_minutos": 60},
    {"nome": "Sessão de Fisioterapia", "descricao": "Sessão padrão de reabilitação.", "duracao_minutos": 45},
    {"nome": "Reavaliação", "descricao": "Reavaliação periódica do quadro clínico.", "duracao_minutos": 45},
    {"nome": "Pilates Clínico", "descricao": "Pilates com foco terapêutico.", "duracao_minutos": 50},
    {"nome": "Drenagem Linfática", "descricao": "Drenagem linfática manual.", "duracao_minutos": 60},
    {"nome": "Eletroterapia", "descricao": "Recursos eletroterapêuticos (TENS, FES, ultrassom).", "duracao_minutos": 30},
    {"nome": "Terapia Manual", "descricao": "Técnicas manuais de mobilização e liberação.", "duracao_minutos": 45},
    {"nome": "Hidroterapia", "descricao": "Reabilitação em meio aquático.", "duracao_minutos": 45},
]


def create_tipos(apps, schema_editor):
    TipoAtendimento = apps.get_model("clinic", "TipoAtendimento")
    for item in TIPOS_ATENDIMENTO:
        TipoAtendimento.objects.get_or_create(nome=item["nome"], defaults=item)


def remove_tipos(apps, schema_editor):
    TipoAtendimento = apps.get_model("clinic", "TipoAtendimento")
    TipoAtendimento.objects.filter(nome__in=[t["nome"] for t in TIPOS_ATENDIMENTO]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_tipos, remove_tipos),
    ]
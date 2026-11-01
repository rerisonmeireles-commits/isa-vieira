"""
Data migration: dados mestres - conselhos profissionais, especialidades
e feriados nacionais.
"""

from django.db import migrations


CONSELHOS = [
    {"sigla": "CREFITO-1", "nome": "CREFITO-1 (PE, BA, SE, AL, PB, RN, CE, PI, MA)", "uf": "PE"},
    {"sigla": "CREFITO-2", "nome": "CREFITO-2 (RJ)", "uf": "RJ"},
    {"sigla": "CREFITO-3", "nome": "CREFITO-3 (SP)", "uf": "SP"},
    {"sigla": "CREFITO-4", "nome": "CREFITO-4 (MG)", "uf": "MG"},
    {"sigla": "CREFITO-5", "nome": "CREFITO-5 (RS)", "uf": "RS"},
    {"sigla": "CREFITO-6", "nome": "CREFITO-6 (PR)", "uf": "PR"},
    {"sigla": "CREFITO-7", "nome": "CREFITO-7 (DF, GO, MT, MS, TO)", "uf": "DF"},
    {"sigla": "CREFITO-8", "nome": "CREFITO-8 (PA, AM, AC, RO, RR, AP)", "uf": "PA"},
    {"sigla": "CREFITO-9", "nome": "CREFITO-9 (ES)", "uf": "ES"},
    {"sigla": "CREFITO-10", "nome": "CREFITO-10 (SC)", "uf": "SC"},
]

ESPECIALIDADES = [
    {"nome": "Ortopedia e Traumatologia", "descricao": "Reabilitação de disfunções musculoesqueléticas e pós-operatórias."},
    {"nome": "Neurologia", "descricao": "Reabilitação de disfunções neurológicas (AVC, Parkinson, lesão medular)."},
    {"nome": "Respiratória", "descricao": "Fisioterapia cardiorrespiratória e reabilitação pulmonar."},
    {"nome": "Esportiva", "descricao": "Prevenção e reabilitação de lesões esportivas."},
    {"nome": "Geriatria", "descricao": "Reabilitação do idoso, prevenção de quedas e sarcopenia."},
    {"nome": "Pediatria", "descricao": "Fisioterapia infantil e neuropediatria."},
    {"nome": "Dermatofuncional", "descricao": "Recuperação de lesões de pele, queimados e pós-cirurgias estéticas."},
    {"nome": "Saúde da Mulher", "descricao": "Reabilitação do assoalho pélvico, gestação e pós-parto."},
    {"nome": "Aquática", "descricao": "Hidroterapia e reabilitação em meio aquático."},
    {"nome": "Reumatologia", "descricao": "Tratamento de doenças reumáticas e autoimunes."},
]

# Feriados de 2026 com recorrente=True: o sistema replica o feriado em
# todos os anos usando o mês/dia da data armazenada como referência.
FERIADOS_NACIONAIS = [
    {"data": "2026-01-01", "descricao": "Confraternização Universal"},
    {"data": "2026-02-16", "descricao": "Carnaval (ponto facultativo)"},
    {"data": "2026-02-17", "descricao": "Carnaval (ponto facultativo)"},
    {"data": "2026-04-03", "descricao": "Sexta-feira Santa"},
    {"data": "2026-04-21", "descricao": "Tiradentes"},
    {"data": "2026-05-01", "descricao": "Dia do Trabalho"},
    {"data": "2026-06-04", "descricao": "Corpus Christi (ponto facultativo)"},
    {"data": "2026-09-07", "descricao": "Independência do Brasil"},
    {"data": "2026-10-12", "descricao": "Nossa Senhora Aparecida"},
    {"data": "2026-11-02", "descricao": "Finados"},
    {"data": "2026-11-15", "descricao": "Proclamação da República"},
    {"data": "2026-12-25", "descricao": "Natal"},
]


def create_master_data(apps, schema_editor):
    ConselhoProfissional = apps.get_model("registry", "ConselhoProfissional")
    Especialidade = apps.get_model("registry", "Especialidade")
    Feriado = apps.get_model("registry", "Feriado")

    for item in CONSELHOS:
        ConselhoProfissional.objects.get_or_create(sigla=item["sigla"], defaults=item)

    for item in ESPECIALIDADES:
        Especialidade.objects.get_or_create(nome=item["nome"], defaults=item)

    for item in FERIADOS_NACIONAIS:
        Feriado.objects.get_or_create(
            data=item["data"],
            defaults={**item, "tipo": "NACIONAL", "recorrente": True},
        )


def remove_master_data(apps, schema_editor):
    ConselhoProfissional = apps.get_model("registry", "ConselhoProfissional")
    Especialidade = apps.get_model("registry", "Especialidade")
    Feriado = apps.get_model("registry", "Feriado")

    ConselhoProfissional.objects.filter(sigla__in=[c["sigla"] for c in CONSELHOS]).delete()
    Especialidade.objects.filter(nome__in=[e["nome"] for e in ESPECIALIDADES]).delete()
    Feriado.objects.filter(data__in=[f["data"] for f in FERIADOS_NACIONAIS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_master_data, remove_master_data),
    ]
"""
Data migration: perfis iniciais (grupos) e permissões.

Cria os 5 grupos (Administrador, Recepção, Fisioterapeuta, Financeiro,
Paciente) e atribui as permissões de cada perfil.

Depende de TODAS as migrações 0001_initial para que as permissões de
todos os apps existam quando os grupos forem populados.
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

# ---------------------------------------------------------------------------
# Matriz de permissões por perfil
# Formato: codename da permissão (add_/change_/delete_/view_ + <modelo>)
# ---------------------------------------------------------------------------

# Administrador: None = recebe TODAS as permissões do sistema
ADMIN_CODENAMES = None

RECEPCAO_CODENAMES = [
    # Pacientes (CRUD)
    "view_paciente", "add_paciente", "change_paciente",
    "view_endereco", "add_endereco", "change_endereco",
    "view_contato", "add_contato", "change_contato",
    "view_contatoemergencia", "add_contatoemergencia", "change_contatoemergencia",
    # Agenda (cria e gerencia agendamentos, sem excluir)
    "view_agenda", "view_slotagenda",
    "view_agendamento", "add_agendamento", "change_agendamento",
    "view_bloqueioagenda", "add_bloqueioagenda", "change_bloqueioagenda",
    # Convênios (leitura + vínculo do paciente)
    "view_convenio", "view_plano",
    "view_pacienteconvenio", "add_pacienteconvenio", "change_pacienteconvenio",
    # Estrutura e cadastros (somente leitura)
    "view_clinica", "view_configuracao", "view_sala", "view_tipoatendimento",
    "view_especialidade", "view_conselhoprofissional", "view_feriado",
    "view_profissional", "view_disponibilidade", "view_ausencia",
    # Clínico (somente leitura)
    "view_atendimento", "view_prontuario", "view_avaliacao", "view_evolucao",
    "view_exercicio", "view_prescricao", "view_prescricaexercicio",
    "view_execucaexercicio",
    # Documentos (leitura + upload)
    "view_documento", "add_documento",
    # Financeiro (leitura + recebimento)
    "view_contareceber", "add_contareceber",
    "view_pagamento", "add_pagamento",
    "view_faturamento",
    # Comunicação e auditoria
    "view_mensagem", "add_mensagem",
    "view_notificacao", "add_notificacao",
    "view_logauditoria",
]

FISIOTERAPEUTA_CODENAMES = [
    # Pacientes (leitura)
    "view_paciente", "view_endereco", "view_contato", "view_contatoemergencia",
    # Agenda (leitura)
    "view_agenda", "view_slotagenda", "view_agendamento", "view_bloqueioagenda",
    # Profissionais e estrutura (leitura)
    "view_profissional", "view_disponibilidade", "view_ausencia",
    "view_sala", "view_tipoatendimento", "view_especialidade", "view_feriado",
    # Atendimento (registro de execução)
    "view_atendimento", "change_atendimento",
    # Prontuário (leitura + edição)
    "view_prontuario", "change_prontuario",
    # Avaliações (criar/editar; liberação via service layer)
    "view_avaliacao", "add_avaliacao", "change_avaliacao",
    # Evoluções SOAP
    "view_evolucao", "add_evolucao", "change_evolucao",
    # Exercícios e prescrições
    "view_exercicio",
    "view_prescricao", "add_prescricao", "change_prescricao",
    "view_prescricaexercicio", "add_prescricaexercicio", "change_prescricaexercicio",
    "view_execucaexercicio", "add_execucaexercicio", "change_execucaexercicio",
    # Documentos
    "view_documento", "add_documento", "change_documento",
    # Financeiro (leitura)
    "view_contareceber", "view_pagamento", "view_faturamento",
    # Comunicação
    "view_mensagem", "add_mensagem",
    "view_notificacao", "add_notificacao",
]

FINANCEIRO_CODENAMES = [
    # Financeiro (gestão completa, sem exclusão)
    "view_contareceber", "add_contareceber", "change_contareceber",
    "view_pagamento", "add_pagamento", "change_pagamento",
    "view_faturamento", "add_faturamento", "change_faturamento",
    # Contexto (leitura)
    "view_paciente", "view_convenio", "view_plano", "view_pacienteconvenio",
    "view_agendamento", "view_atendimento",
    "view_clinica", "view_configuracao",
    "view_notificacao", "add_notificacao",
]

PACIENTE_CODENAMES = [
    # Somente leitura do que é visível no portal. A regra de propriedade
    # (cada paciente só vê os PRÓPRIOS dados) é aplicada no service layer
    # - nunca confie só na permissão para impedir IDOR.
    "view_agendamento", "view_avaliacao", "view_evolucao",
    "view_prescricao", "view_prescricaexercicio", "view_execucaexercicio",
    "view_exercicio", "view_documento", "view_notificacao",
]


def _force_create_permissions(apps, schema_editor):
    """Garante que todas as permissões existam antes de atribuí-las aos grupos.

    Dentro de uma data migration, o parâmetro `apps` é um registro histórico
    de AppConfigStub (sem o atributo models_module). Iteramos sobre o registro
    global real (django.apps.apps) para descobrir quais apps têm models, mas
    passamos o `apps` histórico ao create_permissions - assim as permissões
    são criadas para os modelos históricos da migration.
    """
    for app_config in global_apps.get_app_configs():
        if app_config.models_module is not None:
            create_permissions(app_config, apps=apps, verbosity=0)

def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    _force_create_permissions(apps, schema_editor)

    # Administrador: todas as permissões do sistema
    admin_group, _ = Group.objects.get_or_create(name="Administrador")
    admin_group.permissions.set(Permission.objects.all())

    # Demais perfis: conjuntos específicos
    perfis = {
        "Recepção": RECEPCAO_CODENAMES,
        "Fisioterapeuta": FISIOTERAPEUTA_CODENAMES,
        "Financeiro": FINANCEIRO_CODENAMES,
        "Paciente": PACIENTE_CODENAMES,
    }
    for nome, codenames in perfis.items():
        grupo, _ = Group.objects.get_or_create(name=nome)
        grupo.permissions.set(Permission.objects.filter(codename__in=codenames))


def remove_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(
        name__in=["Administrador", "Recepção", "Fisioterapeuta", "Financeiro", "Paciente"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_initial"),
        # As 0002_initial dos demais apps garantem que os modelos históricos
        # existam e que as permissões possam ser criadas para todos eles.
        ("clinic", "0001_initial"),
        ("registry", "0001_initial"),
        ("professionals", "0001_initial"),
        ("patients", "0001_initial"),
        ("insurance", "0001_initial"),
        ("scheduling", "0001_initial"),
        ("attendance", "0001_initial"),
        ("clinical", "0001_initial"),
        ("exercise", "0001_initial"),
        ("documents", "0001_initial"),
        ("financial", "0001_initial"),
        ("communication", "0001_initial"),
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_groups, remove_groups),
    ]
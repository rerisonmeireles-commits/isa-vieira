"""Mapa de navegação do portal por perfil (RBAC do menu).

Cada grupo tem sua lista de itens. Para adicionar um módulo ao menu de um
perfil, basta acrescentar um item à lista correspondente. O Administrador
recebe a visão completa (todas as áreas + auditoria/configurações).
"""

from django.urls import reverse_lazy

from apps.accounts.constants import (
    GRUPO_ADMINISTRADOR,
    GRUPO_FINANCEIRO,
    GRUPO_FISIOTERAPEUTA,
    GRUPO_RECEPCAO,
)


def _item(rotulo, url_name, icone, **kwargs):
    return {
        "rotulo": rotulo,
        "url": reverse_lazy(url_name, **kwargs),
        "icone": icone,
    }


def _modulo(rotulo, slug, icone):
    """Item que aponta para o placeholder de módulo ainda não implementado."""
    return _item(rotulo, "conta:em_breve", icone, kwargs={"slug": slug})


MENU_POR_GRUPO = {
    GRUPO_RECEPCAO: [
        _item("Agenda", "scheduling:grade", "bi-calendar-week"),
        _item("Pacientes + Convênios", "patients:listar", "bi-people"),
        _item("Profissionais", "professionals:listar", "bi-person-badge"),        
        _item("Convênios", "insurance:listar", "bi-hospital"),
        _modulo("Documentos", "documentos", "bi-file-earmark-text"),
        _item("Financeiro (recebimentos)", "financial:listar_contas", "bi-cash-coin"),
        _item("Consentimentos LGPD", "conta:consentimento_lista", "bi-shield-check"),
    ],
    GRUPO_FISIOTERAPEUTA: [
        _item("Agenda", "scheduling:grade", "bi-calendar-week"),
        _item("Pacientes ( Prontuário )", "patients:listar", "bi-people"),
        _item("Exercícios", "exercise:lista_exercicios", "bi-activity"),
        _item("Documentos", "documents:documento_lista", "bi-file-earmark-text"),
    ],
    GRUPO_FINANCEIRO: [
        _item("Contas a Receber", "financial:listar_contas", "bi-cash-stack"),
        _item("Pagamentos", "financial:listar_contas", "bi-credit-card"),
        _item("Faturamento/Convênios", "financial:listar_faturamentos", "bi-receipt"), 
        _item("Pacientes (consulta)", "patients:listar", "bi-people"),
        _item("Convênios", "insurance:listar", "bi-hospital"),
        _modulo("Relatórios", "relatorios", "bi-graph-up"),
    ],
    GRUPO_ADMINISTRADOR: [
        _item("Agenda", "scheduling:grade", "bi-calendar-week"),
        _item("Convênios", "insurance:listar", "bi-hospital"),
        _item("Pacientes", "patients:listar", "bi-people"),        
        _item("Profissionais", "professionals:listar", "bi-person-badge"),
        _item("Documentos", "documents:documento_lista", "bi-file-earmark-text"),                                

        _item("Financeiro", "financial:listar_contas", "bi-cash-coin"),
        _item("Contas a Receber", "financial:listar_contas", "bi-cash-stack"),
        _item("Pagamentos", "financial:listar_contas", "bi-credit-card"),
        _item("Faturamento/Convênios", "financial:listar_faturamentos", "bi-receipt"),        

        _modulo("Cadastros Básicos", "cadastros", "bi-gear"),
        _item("Dados da Clínica", "clinica:dados_clinica", "bi-building"),
        _item("Salas", "clinica:listar_salas", "bi-door-open"),        
        _item("Conselhos Profissionais", "registry:listar_conselhos", "bi-award"),        
        _item("Especialidades", "registry:listar_especialidades", "bi-stars"),       
        _item("Feriados", "registry:listar_feriados", "bi-calendar-x"),                        
        _item("Tipos de Atendimento", "clinica:listar_tipos", "bi-clipboard-pulse"),        
        
        _item("Consentimentos LGPD", "conta:consentimento_lista", "bi-shield-check"),        
        _item("Exercícios", "exercise:lista_exercicios", "bi-activity"),
        _item("Usuários", "conta:usuario_lista", "bi-person-gear"),        

        _modulo("Relatórios", "relatorios", "bi-graph-up"),        
        _modulo("Auditoria (LGPD)", "auditoria", "bi-shield-lock"),                
        
        
                
    ],
}

def menu_do_usuario(usuario):
    """Itens de menu visíveis, na ordem dos grupos do usuário.

    Superusuário recebe o menu de Administrador. A dedupe usa (rótulo, url):
    no Administrador, "Financeiro", "Contas a Receber" e "Pagamentos" apontam
    para financial:listar_contas e são abas distintas da mesma tela -
    deduplicar só por url apagava duas delas silenciosamente.
    """
    if not usuario.is_authenticated:
        return []

    grupos = (
        [GRUPO_ADMINISTRADOR]
        if usuario.is_superuser
        else list(usuario.groups.order_by("name").values_list("name", flat=True))
    )

    itens, vistos = [], set()
    for grupo in grupos:
        for item in MENU_POR_GRUPO.get(grupo, []):
            chave = (item["rotulo"], item["url"])
            if chave not in vistos:
                vistos.add(chave)
                itens.append(item)

    for item in (
        _item("Notificações", "communication:central", "bi-bell"),
        _item("Mensagens", "communication:inbox", "bi-envelope"),
    ):
        chave = (item["rotulo"], item["url"])
        if chave not in vistos:
            vistos.add(chave)
            itens.append(item)

    return itens
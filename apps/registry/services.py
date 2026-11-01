"""Regras de negócio do módulo Registry (cadastros básicos).

Services intencionalmente finos: os modelos são cadastros simples. A camada
existe para manter o padrão do projeto (view fina, service gorda) e dar um
ponto único para regras futuras - ex.: quando o Feriado passar a bloquear
a geração de agendas.
"""


def salvar_especialidade(*, form):
    return form.save()


def alternar_ativa_especialidade(especialidade):
    especialidade.ativa = not especialidade.ativa
    especialidade.save(update_fields=["ativa"])
    return especialidade


def salvar_conselho(*, form):
    return form.save()


def salvar_feriado(*, form):
    feriado = form.save()
    _limpar_slots_do_feriado(feriado.data)
    return feriado


def excluir_feriado(feriado):
    data = feriado.data
    feriado.delete()
    _limpar_slots_do_feriado(data)


def _limpar_slots_do_feriado(data):
    """Importação tardia evita acoplamento no carregamento do módulo."""
    from apps.scheduling.services.geracao_slots import limpar_slots_feriado
    limpar_slots_feriado(data)
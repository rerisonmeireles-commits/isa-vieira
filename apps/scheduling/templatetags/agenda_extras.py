from django import template

register = template.Library()


@register.filter
def get_item(dicionario, chave):
    """Acessa dict[chave] com chave dinâmica no template ({{ d|get_item:k }})."""
    return dicionario.get(chave) if dicionario else None
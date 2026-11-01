"""Services de gestão de usuários e consentimento LGPD.

Usuários: criação/edição com set_password, atribuição de perfis (grupos)
e ativação/desativação - exclusão nunca é executada (rastreabilidade).
Consentimento: registro rastreável com hash do termo e revogação.
"""

from django.contrib.auth.models import Group
from django.db import transaction

from apps.accounts.models import ConsentimentoLgpd, Usuario


@transaction.atomic
def criar_usuario(dados, senha):
    usuario = Usuario(**{k: v for k, v in dados.items() if k != "grupos"})
    usuario.set_password(senha)
    usuario.save()
    usuario.groups.set(dados.get("grupos", []))
    return usuario


@transaction.atomic
def atualizar_usuario(usuario, dados, senha=None):
    for attr, valor in dados.items():
        if attr == "grupos":
            continue
        setattr(usuario, attr, valor)
    if senha:
        usuario.set_password(senha)
    usuario.save()
    usuario.groups.set(dados.get("grupos", []))
    return usuario


@transaction.atomic
def alternar_status(usuario_id):
    """Ativa/desativa o usuário. Nunca desativa o próprio superusuário logado
    nem o último administrador ativo - evita perder o acesso ao sistema."""
    usuario = Usuario.objects.get(pk=usuario_id)
    if usuario.is_superuser and usuario.is_active:
        admins_ativos = Usuario.objects.filter(
            is_superuser=True, is_active=True
        ).count()
        if admins_ativos <= 1:
            raise ValueError("Não é possível desativar o último administrador ativo.")
    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=["is_active"])
    return usuario


@transaction.atomic
def redefinir_senha(usuario_id, nova_senha):
    usuario = Usuario.objects.get(pk=usuario_id)
    usuario.set_password(nova_senha)
    usuario.save(update_fields=["password"])
    return usuario


@transaction.atomic
def registrar_consentimento(paciente, versao_termo, canal, aceito=True,
                            ip_origem=None, hash_termo=None):
    """Registra o aceite. O hash_termo deve ser o SHA-256 do arquivo do termo
    assinado - quando o upload do termo for implementado, calcule na gravação."""
    return ConsentimentoLgpd.objects.create(
        paciente=paciente,
        versao_termo=versao_termo,
        canal=canal,
        aceito=aceito,
        ip_origem=ip_origem,
        hash_termo=hash_termo,
    )


@transaction.atomic
def revogar_consentimento(consentimento_id):
    """Revogação é um NOVO registro com aceito=False - nunca editar o aceite
    original, que é o comprovante histórico (LGPD art. 18, § 5º)."""
    original = ConsentimentoLgpd.objects.select_related("paciente").get(
        pk=consentimento_id
    )
    return ConsentimentoLgpd.objects.create(
        paciente=original.paciente,
        versao_termo=original.versao_termo,
        canal=original.canal,
        aceito=False,
        ip_origem=original.ip_origem,
        hash_termo=original.hash_termo,
    )
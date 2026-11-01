"""Services do app documents.

Registro com integridade (hash SHA-256, mime-type e tamanho calculados no
upload, conforme a especificação do modelo de dados) e exclusão lógica
(soft delete herdado do SoftDeleteModel - histórico preservado).
"""

import hashlib
import mimetypes

from django.db import transaction

from apps.documents.models import Documento


def _calcular_hash_sha256(arquivo):
    """Hash em blocos - não carrega o arquivo inteiro na memória."""
    hash_obj = hashlib.sha256()
    for bloco in arquivo.chunks():
        hash_obj.update(bloco)
    return hash_obj.hexdigest()


def _metadados_do_arquivo(arquivo):
    arquivo.seek(0)  # garante leitura a partir do início
    return {
        "tamanho_bytes": arquivo.size,
        "mime_type": mimetypes.guess_type(arquivo.name)[0] or "application/octet-stream",
        "hash_sha256": _calcular_hash_sha256(arquivo),
    }


@transaction.atomic
def registrar_documento(paciente, arquivo, tipo, titulo, descricao="",
                        profissional=None, atendimento=None, data_emissao=None,
                        visivel_paciente=True, assinado=False):
    """Cria o documento calculando os metadados de integridade no upload."""
    documento = Documento(
        paciente=paciente,
        profissional=profissional,
        atendimento=atendimento,
        tipo=tipo,
        titulo=titulo,
        descricao=descricao,
        arquivo=arquivo,
        data_emissao=data_emissao,
        visivel_paciente=visivel_paciente,
        assinado=assinado,
    )
    for attr, valor in _metadados_do_arquivo(arquivo).items():
        setattr(documento, attr, valor)
    documento.save()
    return documento


@transaction.atomic
def atualizar_documento(documento, arquivo=None, **campos):
    """Aplica alterações; se um novo arquivo for enviado, recalcula os metadados."""
    for attr, valor in campos.items():
        setattr(documento, attr, valor)
    if arquivo is not None:
        documento.arquivo = arquivo
        for attr, valor in _metadados_do_arquivo(arquivo).items():
            setattr(documento, attr, valor)
    documento.save()
    return documento


@transaction.atomic
def excluir_documento(documento_id):
    """Exclusão lógica - o histórico é preservado (LGPD/COFFITO)."""
    documento = Documento.objects.get(pk=documento_id)
    titulo = documento.titulo
    documento.delete()  # soft delete via SoftDeleteModel
    return titulo
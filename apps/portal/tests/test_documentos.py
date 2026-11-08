"""Testes de isolamento do portal do paciente — documentos.

Usa TransactionTestCase (não TestCase) porque o FileField + rollback
em transação atômica no Windows deixa handles abertos e derruba a
conexão do PostgreSQL no teste seguinte.

TransactionTestCase trunca as tabelas no tearDown em vez de fazer
rollback — o arquivo físico é liberado corretamente.
"""
import shutil
import tempfile
import uuid as uuid_lib

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from apps.accounts.constants import GRUPO_PACIENTE
from apps.accounts.models import Usuario
from apps.documents.models import Documento
from apps.patients.models import Paciente


_MEDIA_ROOT = tempfile.mkdtemp(prefix="test_media_")


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class DocumentoPortalIsolamentoTests(TransactionTestCase):
    # TransactionTestCase trunca tabelas — não usa setUpTestData.
    # Os dados são criados em setUp() a cada teste.
    reset_sequences = True

    def setUp(self):
        grupo, _ = Group.objects.get_or_create(name=GRUPO_PACIENTE)

        self.user_a = Usuario.objects.create_user(
            username="pac_a", email="a@test.local", password="x",
        )
        self.user_a.groups.add(grupo)
        self.paciente_a = Paciente.objects.create(
            nome_completo="Paciente A", user=self.user_a,
        )

        self.user_b = Usuario.objects.create_user(
            username="pac_b", email="b@test.local", password="x",
        )
        self.user_b.groups.add(grupo)
        self.paciente_b = Paciente.objects.create(
            nome_completo="Paciente B", user=self.user_b,
        )

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    def _criar_documento(self, paciente, visivel=True):
        nome = f"teste_{uuid_lib.uuid4().hex[:8]}.pdf"
        return Documento.objects.create(
            paciente=paciente,
            visivel_paciente=visivel,
            arquivo=SimpleUploadedFile(
                nome,
                b"%PDF-1.4 conteudo de teste",
                content_type="application/pdf",
            ),
        )

    def _fechar_resposta(self, resposta):
        if getattr(resposta, "streaming", False):
            b"".join(resposta.streaming_content)
        resposta.close()

    # ─────────────────────────────────────────────────────────────
    # Testes
    # ─────────────────────────────────────────────────────────────

    def test_documento_de_outro_paciente_devolve_404(self):
        doc = self._criar_documento(self.paciente_b)
        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:documento_download", kwargs={"uuid": doc.uuid})
        )
        self.assertEqual(resposta.status_code, 404)
        self._fechar_resposta(resposta)

    def test_documento_invisivel_devolve_404(self):
        doc = self._criar_documento(self.paciente_a, visivel=False)
        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:documento_download", kwargs={"uuid": doc.uuid})
        )
        self.assertEqual(resposta.status_code, 404)
        self._fechar_resposta(resposta)

    def test_documento_proprio_visivel_retorna_200(self):
        doc = self._criar_documento(self.paciente_a)
        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:documento_download", kwargs={"uuid": doc.uuid})
        )
        self.assertEqual(resposta.status_code, 200)
        self._fechar_resposta(resposta)

    def test_usuario_sem_vinculo_paciente_recebe_403(self):
        user_sem_vinculo = Usuario.objects.create_user(
            username="sem_vinculo", email="s@test.local", password="x",
        )
        user_sem_vinculo.groups.add(Group.objects.get(name=GRUPO_PACIENTE))
        self.client.force_login(user_sem_vinculo)
        resposta = self.client.get(reverse("portal:documentos"))
        self.assertEqual(resposta.status_code, 403)
        self._fechar_resposta(resposta)
"""Testes de auditoria de acesso do portal do paciente (§1.5).

A §1.5 exige rastreabilidade de acesso a dados sensíveis e prontuário.
Estas views expõem dados pessoais e clínicos:

  - perfil()             → CPF, endereço, contato de emergência
  - evolucao()           → prontuário (registros SOAP)
  - avaliacoes()         → fichas de avaliação física/funcional
  - documento_download() → laudos, atestados, exames

O padrão testado é o mesmo em todas: registrar_auditoria() grava um
LogAuditoria com acao, tabela e registro_id corretos, e o registro é
escopado ao paciente do usuário logado — nunca a um terceiro.

Notas de fixture:
- registrar_auditoria é best-effort: captura exceção, loga e retorna
  None. Por isso os testes verificam o LogAuditoria criado, não a
  resposta HTTP.
- A auditoria de perfil() é por SESSÃO (flag request.session), então
  os testes de duplicação precisam do mesmo client entre requests.
"""
from datetime import time, timedelta

from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.constants import GRUPO_PACIENTE
from apps.accounts.models import Usuario
from apps.audit.models import LogAuditoria
from apps.clinic.models import TipoAtendimento
from apps.clinical.models import Avaliacao, Evolucao
from apps.documents.models import Documento
from apps.patients.models import Paciente
from apps.professionals.models import Profissional
from apps.registry.models import ConselhoProfissional
from apps.scheduling.models import Agenda, SlotAgenda


class AuditoriaPortalBase(TestCase):
    """Dois pacientes, um profissional e fixtures clínicas mínimas."""

    @classmethod
    def setUpTestData(cls):
        grupo, _ = Group.objects.get_or_create(name=GRUPO_PACIENTE)

        # ── Paciente A ──────────────────────────────────────────
        cls.user_a = Usuario.objects.create_user(
            username="pac_aud_a", email="aud_a@test.local", password="x",
        )
        cls.user_a.groups.add(grupo)
        cls.paciente_a = Paciente.objects.create(
            nome_completo="Paciente Auditoria A", user=cls.user_a,
        )

        # ── Paciente B ──────────────────────────────────────────
        cls.user_b = Usuario.objects.create_user(
            username="pac_aud_b", email="aud_b@test.local", password="x",
        )
        cls.user_b.groups.add(grupo)
        cls.paciente_b = Paciente.objects.create(
            nome_completo="Paciente Auditoria B", user=cls.user_b,
        )

        # ── Conselho e profissional ─────────────────────────────
        cls.conselho, _ = ConselhoProfissional.objects.get_or_create(
            sigla="CREFITO",
            defaults={"nome": "Conselho Regional de Fisioterapia"},
        )
        cls.user_prof = Usuario.objects.create_user(
            username="prof_aud", email="prof_aud@test.local", password="x",
        )
        cls.profissional = Profissional.objects.create(
            nome_completo="Fisio Auditoria",
            user=cls.user_prof,
            conselho=cls.conselho,
            registro_conselho="777777-F",
            status=Profissional.Status.ATIVO,
        )

    # ── Helpers de fixture ──────────────────────────────────────

    def _criar_evolucao(self, paciente, status=Evolucao.Status.LIBERADA):
        kwargs = {
            "paciente": paciente,
            "profissional": self.profissional,
            "status": status,
            "subjetivo": "Paciente relata melhora.",
            "objetivo": "Amplitude preservada.",
            "avaliacao": "Boa evolução.",
            "plano": "Manter protocolo.",
        }
        if status == Evolucao.Status.LIBERADA:
            kwargs["liberado_por"] = self.user_prof
            kwargs["liberado_em"] = timezone.now()
        return Evolucao.objects.create(**kwargs)

    def _criar_avaliacao(self, paciente, status=Avaliacao.Status.LIBERADA):
        kwargs = {
            "paciente": paciente,
            "profissional": self.profissional,
            "status": status,
        }
        if status == Avaliacao.Status.LIBERADA:
            kwargs["liberado_por"] = self.user_prof
            kwargs["liberado_em"] = timezone.now()
        return Avaliacao.objects.create(**kwargs)

    def _criar_documento(self, paciente, visivel=True):
        doc = Documento(
            paciente=paciente,
            profissional=self.profissional,
            titulo="Laudo de auditoria",
            visivel_paciente=visivel,
        )
        doc.arquivo.save(
            "laudo_auditoria.txt",
            ContentFile(b"conteudo de teste"),
            save=False,
        )
        doc.save()
        return doc

    def _logs(self, acao, **filtros):
        return LogAuditoria.objects.filter(acao=acao, **filtros)


class PerfilAuditoriaTests(AuditoriaPortalBase):
    """perfil() registra acesso a dados cadastrais sensíveis."""

    def test_perfil_registra_auditoria_de_acesso(self):
        """Acesso ao perfil grava LogAuditoria com o paciente correto."""
        self.client.force_login(self.user_a)
        self.client.get(reverse("portal:perfil"))

        log = self._logs(
            "ACESSO_PERFIL",
            usuario=self.user_a,
            tabela="paciente",
            registro_id=self.paciente_a.pk,
        ).first()

        self.assertIsNotNone(log, "Acesso ao perfil não foi auditado.")
        self.assertEqual(log.ip, "127.0.0.1")

    def test_perfil_audita_uma_vez_por_sessao(self):
        """Recarregar o perfil não duplica o registro na mesma sessão."""
        self.client.force_login(self.user_a)

        self.client.get(reverse("portal:perfil"))
        self.client.get(reverse("portal:perfil"))
        self.client.get(reverse("portal:perfil"))

        total = self._logs(
            "ACESSO_PERFIL", usuario=self.user_a,
        ).count()
        self.assertEqual(
            total, 1,
            "A flag de sessão perfil_auditado não está sendo respeitada.",
        )

    def test_perfil_audita_nova_sessao_apos_logout(self):
        """Nova sessão gera novo registro — a flag não vaza entre sessões."""
        self.client.force_login(self.user_a)
        self.client.get(reverse("portal:perfil"))
        self.client.logout()

        self.client.force_login(self.user_a)
        self.client.get(reverse("portal:perfil"))

        total = self._logs(
            "ACESSO_PERFIL", usuario=self.user_a,
        ).count()
        self.assertEqual(total, 2)

    def test_perfil_nao_audita_paciente_de_outro(self):
        """O registro_id é sempre o paciente do usuário logado."""
        self.client.force_login(self.user_b)
        self.client.get(reverse("portal:perfil"))

        self.assertFalse(
            self._logs(
                "ACESSO_PERFIL", registro_id=self.paciente_a.pk,
            ).exists(),
            "Auditoria registrou o paciente errado.",
        )
        self.assertTrue(
            self._logs(
                "ACESSO_PERFIL", registro_id=self.paciente_b.pk,
            ).exists()
        )

    def test_perfil_sem_vinculo_nao_audita(self):
        """403 do portal_required não chega a registrar auditoria."""
        user_sem_vinculo = Usuario.objects.create_user(
            username="sem_vinculo_aud", password="x",
        )
        user_sem_vinculo.groups.add(Group.objects.get(name=GRUPO_PACIENTE))

        self.client.force_login(user_sem_vinculo)
        resposta = self.client.get(reverse("portal:perfil"))

        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(
            self._logs("ACESSO_PERFIL", usuario=user_sem_vinculo).exists()
        )


class EvolucaoAuditoriaTests(AuditoriaPortalBase):
    """evolucao() registra acesso a prontuário (§1.5)."""

    def test_evolucao_registra_auditoria_de_acesso(self):
        self.client.force_login(self.user_a)
        self.client.get(reverse("portal:evolucao"))

        log = self._logs(
            "ACESSO_EVOLUCAO",
            usuario=self.user_a,
            tabela="paciente",
            registro_id=self.paciente_a.pk,
        ).first()

        self.assertIsNotNone(log, "Acesso à evolução não foi auditado.")

    def test_evolucao_audita_uma_vez_por_sessao(self):
        self.client.force_login(self.user_a)
        self.client.get(reverse("portal:evolucao"))
        self.client.get(reverse("portal:evolucao"))

        total = self._logs(
            "ACESSO_EVOLUCAO", usuario=self.user_a,
        ).count()
        self.assertEqual(total, 1)

    def test_evolucao_nao_audita_paciente_de_outro(self):
        self.client.force_login(self.user_b)
        self.client.get(reverse("portal:evolucao"))

        self.assertFalse(
            self._logs(
                "ACESSO_EVOLUCAO", registro_id=self.paciente_a.pk,
            ).exists()
        )


class AvaliacaoAuditoriaTests(AuditoriaPortalBase):
    """avaliacoes() registra acesso a fichas de avaliação (§1.5)."""

    def test_avaliacoes_registra_auditoria_de_acesso(self):
        self.client.force_login(self.user_a)
        self.client.get(reverse("portal:avaliacoes"))

        log = self._logs(
            "ACESSO_AVALIACAO",
            usuario=self.user_a,
            tabela="paciente",
            registro_id=self.paciente_a.pk,
        ).first()

        self.assertIsNotNone(log, "Acesso às avaliações não foi auditado.")

    def test_avaliacoes_audita_uma_vez_por_sessao(self):
        self.client.force_login(self.user_a)
        self.client.get(reverse("portal:avaliacoes"))
        self.client.get(reverse("portal:avaliacoes"))

        total = self._logs(
            "ACESSO_AVALIACAO", usuario=self.user_a,
        ).count()
        self.assertEqual(total, 1)

    def test_avaliacoes_nao_audita_paciente_de_outro(self):
        self.client.force_login(self.user_b)
        self.client.get(reverse("portal:avaliacoes"))

        self.assertFalse(
            self._logs(
                "ACESSO_AVALIACAO", registro_id=self.paciente_a.pk,
            ).exists()
        )


class DocumentoAuditoriaTests(AuditoriaPortalBase):
    """documento_download() registra acesso a laudos e atestados (§1.5)."""

    def test_download_registra_auditoria(self):
        doc = self._criar_documento(self.paciente_a)

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:documento_download", kwargs={"uuid": doc.uuid})
        )
        self.assertEqual(resposta.status_code, 200)

        log = self._logs(
            "DOWNLOAD_DOCUMENTO",
            usuario=self.user_a,
            tabela="documento",
            registro_id=doc.pk,
        ).first()

        self.assertIsNotNone(log, "Download do documento não foi auditado.")

    def test_download_audita_cada_arquivo_baixado(self):
        """Diferente de perfil(), cada download é um evento distinto."""
        doc = self._criar_documento(self.paciente_a)

        self.client.force_login(self.user_a)
        url = reverse("portal:documento_download", kwargs={"uuid": doc.uuid})
        self.client.get(url)
        self.client.get(url)

        total = self._logs(
            "DOWNLOAD_DOCUMENTO", registro_id=doc.pk,
        ).count()
        self.assertEqual(
            total, 2,
            "Cada download deve gerar um registro — não há flag de sessão.",
        )

    def test_download_de_outro_paciente_nao_audita(self):
        """404 do isolamento não chega a registrar auditoria."""
        doc_b = self._criar_documento(self.paciente_b)

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:documento_download", kwargs={"uuid": doc_b.uuid})
        )
        self.assertEqual(resposta.status_code, 404)

        self.assertFalse(
            self._logs("DOWNLOAD_DOCUMENTO", registro_id=doc_b.pk).exists()
        )

    def test_download_de_documento_invisivel_nao_audita(self):
        doc = self._criar_documento(self.paciente_a, visivel=False)

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:documento_download", kwargs={"uuid": doc.uuid})
        )
        self.assertEqual(resposta.status_code, 404)

        self.assertFalse(
            self._logs("DOWNLOAD_DOCUMENTO", registro_id=doc.pk).exists()
        )


class AuditoriaBestEffortTests(AuditoriaPortalBase):
    """registrar_auditoria nunca derruba a view, mesmo falhando."""

    def test_falha_na_auditoria_nao_quebra_perfil(self):
        """Se LogAuditoria falhar, perfil() continua respondendo 200."""
        from unittest.mock import patch

        with patch(
            "apps.audit.services.LogAuditoria.objects.create",
            side_effect=Exception("falha simulada no banco"),
        ):
            self.client.force_login(self.user_a)
            resposta = self.client.get(reverse("portal:perfil"))

        self.assertEqual(
            resposta.status_code, 200,
            "Falha na auditoria não pode derrubar a view.",
        )
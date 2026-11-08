"""Testes de auditoria das views de detalhe do portal (§1.5).

consulta_detalhe(), avaliacao_detalhe() e treino_detalhe() expõem dados
clínicos e de agendamento. A auditoria aqui é POR ACESSO (não por
sessão) e o registro_id aponta para o RECURSO específico, não para o
paciente — a trilha precisa responder "qual ficha foi aberta".

Padrão testado em cada view:
  1. Acesso próprio gera log com registro_id do recurso.
  2. Dois acessos geram dois logs (por_sessao=False).
  3. 404 por isolamento não gera log.
  4. 404 por status invisível não gera log.
"""
from datetime import time, timedelta

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.constants import GRUPO_PACIENTE
from apps.accounts.models import Usuario
from apps.audit.models import LogAuditoria
from apps.clinic.models import TipoAtendimento
from apps.clinical.models import Avaliacao
from apps.exercise.models import Exercicio, Prescricao, PrescricaoExercicio
from apps.patients.models import Paciente
from apps.professionals.models import Profissional
from apps.registry.models import ConselhoProfissional
from apps.scheduling.models import Agendamento, Agenda, SlotAgenda


class DetalheAuditoriaBase(TestCase):
    """Dois pacientes, profissional, agenda e fixtures clínicas."""

    @classmethod
    def setUpTestData(cls):
        grupo, _ = Group.objects.get_or_create(name=GRUPO_PACIENTE)

        cls.user_a = Usuario.objects.create_user(
            username="det_a", email="det_a@test.local", password="x",
        )
        cls.user_a.groups.add(grupo)
        cls.paciente_a = Paciente.objects.create(
            nome_completo="Paciente Detalhe A", user=cls.user_a,
        )

        cls.user_b = Usuario.objects.create_user(
            username="det_b", email="det_b@test.local", password="x",
        )
        cls.user_b.groups.add(grupo)
        cls.paciente_b = Paciente.objects.create(
            nome_completo="Paciente Detalhe B", user=cls.user_b,
        )

        cls.conselho, _ = ConselhoProfissional.objects.get_or_create(
            sigla="CREFITO",
            defaults={"nome": "Conselho Regional de Fisioterapia"},
        )
        cls.user_prof = Usuario.objects.create_user(
            username="det_prof", email="det_prof@test.local", password="x",
        )
        cls.profissional = Profissional.objects.create(
            nome_completo="Fisio Detalhe",
            user=cls.user_prof,
            conselho=cls.conselho,
            registro_conselho="888888-F",
            status=Profissional.Status.ATIVO,
        )

        cls.tipo = TipoAtendimento.objects.create(
            nome="Fisioterapia Detalhe",
            duracao_minutos=50,
            ativo=True,
        )

        cls.data_agenda = timezone.localdate() + timedelta(days=3)
        cls.agenda = Agenda.objects.create(
            profissional=cls.profissional,
            data=cls.data_agenda,
            status=Agenda.Status.GERADA,
        )
        cls.slot = SlotAgenda.objects.create(
            agenda=cls.agenda,
            hora_inicio=time(10, 0),
            hora_fim=time(10, 50),
            status=SlotAgenda.Status.LIVRE,
        )

    def _criar_agendamento(self, paciente):
        return Agendamento.objects.create(
            paciente=paciente,
            profissional=self.profissional,
            tipo_atendimento=self.tipo,
            slot=self.slot,
            status=Agendamento.Status.AGENDADO,
        )

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

    def _criar_prescricao(self, paciente, status=Prescricao.Status.ATIVA):
        return Prescricao.objects.create(
            paciente=paciente,
            profissional=self.profissional,
            status=status,
        )

    def _logs(self, acao, **filtros):
        return LogAuditoria.objects.filter(acao=acao, **filtros)


class ConsultaDetalheAuditoriaTests(DetalheAuditoriaBase):
    """consulta_detalhe() audita acesso com registro_id do agendamento."""

    def test_acesso_proprio_registra_auditoria(self):
        ag = self._criar_agendamento(self.paciente_a)

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:consulta_detalhe", kwargs={"uuid": ag.uuid})
        )
        self.assertEqual(resposta.status_code, 200)

        log = self._logs(
            "ACESSO_CONSULTA",
            usuario=self.user_a,
            tabela="agendamento",
            registro_id=ag.pk,
        ).first()
        self.assertIsNotNone(log, "Acesso à consulta não foi auditado.")

    def test_dois_acessos_geram_dois_logs(self):
        """por_sessao=False: cada abertura do detalhe é um evento."""
        ag = self._criar_agendamento(self.paciente_a)

        self.client.force_login(self.user_a)
        url = reverse("portal:consulta_detalhe", kwargs={"uuid": ag.uuid})
        self.client.get(url)
        self.client.get(url)

        total = self._logs("ACESSO_CONSULTA", registro_id=ag.pk).count()
        self.assertEqual(total, 2)

    def test_consulta_de_outro_paciente_nao_audita(self):
        ag_b = self._criar_agendamento(self.paciente_b)

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:consulta_detalhe", kwargs={"uuid": ag_b.uuid})
        )
        self.assertEqual(resposta.status_code, 404)

        self.assertFalse(
            self._logs("ACESSO_CONSULTA", registro_id=ag_b.pk).exists(),
            "404 por isolamento não pode gerar log de acesso.",
        )


class AvaliacaoDetalheAuditoriaTests(DetalheAuditoriaBase):
    """avaliacao_detalhe() audita acesso com registro_id da avaliação."""

    def test_acesso_proprio_registra_auditoria(self):
        av = self._criar_avaliacao(self.paciente_a)

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:avaliacao_detalhe", kwargs={"uuid": av.uuid})
        )
        self.assertEqual(resposta.status_code, 200)

        log = self._logs(
            "ACESSO_AVALIACAO_DET",
            usuario=self.user_a,
            tabela="avaliacao",
            registro_id=av.pk,
        ).first()
        self.assertIsNotNone(log, "Acesso à avaliação não foi auditado.")

    def test_dois_acessos_geram_dois_logs(self):
        av = self._criar_avaliacao(self.paciente_a)

        self.client.force_login(self.user_a)
        url = reverse("portal:avaliacao_detalhe", kwargs={"uuid": av.uuid})
        self.client.get(url)
        self.client.get(url)

        total = self._logs("ACESSO_AVALIACAO_DET", registro_id=av.pk).count()
        self.assertEqual(total, 2)

    def test_avaliacao_de_outro_paciente_nao_audita(self):
        av_b = self._criar_avaliacao(self.paciente_b)

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:avaliacao_detalhe", kwargs={"uuid": av_b.uuid})
        )
        self.assertEqual(resposta.status_code, 404)

        self.assertFalse(
            self._logs("ACESSO_AVALIACAO_DET", registro_id=av_b.pk).exists()
        )

    def test_avaliacao_em_rascunho_nao_audita(self):
        """Rascunho não é visível — 404 não gera log de acesso."""
        av = self._criar_avaliacao(
            self.paciente_a, status=Avaliacao.Status.PENDENTE,
        )

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:avaliacao_detalhe", kwargs={"uuid": av.uuid})
        )
        self.assertEqual(resposta.status_code, 404)

        self.assertFalse(
            self._logs("ACESSO_AVALIACAO_DET", registro_id=av.pk).exists()
        )


class TreinoDetalheAuditoriaTests(DetalheAuditoriaBase):
    """treino_detalhe() audita acesso com registro_id da prescrição."""

    def test_acesso_proprio_registra_auditoria(self):
        presc = self._criar_prescricao(self.paciente_a)

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:treino_detalhe", kwargs={"uuid": presc.uuid})
        )
        self.assertEqual(resposta.status_code, 200)

        log = self._logs(
            "ACESSO_TREINO",
            usuario=self.user_a,
            tabela="prescricao",
            registro_id=presc.pk,
        ).first()
        self.assertIsNotNone(log, "Acesso ao treino não foi auditado.")

    def test_dois_acessos_geram_dois_logs(self):
        presc = self._criar_prescricao(self.paciente_a)

        self.client.force_login(self.user_a)
        url = reverse("portal:treino_detalhe", kwargs={"uuid": presc.uuid})
        self.client.get(url)
        self.client.get(url)

        total = self._logs("ACESSO_TREINO", registro_id=presc.pk).count()
        self.assertEqual(total, 2)

    def test_treino_de_outro_paciente_nao_audita(self):
        presc_b = self._criar_prescricao(self.paciente_b)

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:treino_detalhe", kwargs={"uuid": presc_b.uuid})
        )
        self.assertEqual(resposta.status_code, 404)

        self.assertFalse(
            self._logs("ACESSO_TREINO", registro_id=presc_b.pk).exists()
        )

    def test_prescricao_encerrada_nao_audita(self):
        """Prescrição encerrada devolve 404 — não gera log."""
        presc = self._criar_prescricao(
            self.paciente_a, status=Prescricao.Status.ENCERRADA,
        )

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:treino_detalhe", kwargs={"uuid": presc.uuid})
        )
        self.assertEqual(resposta.status_code, 404)

        self.assertFalse(
            self._logs("ACESSO_TREINO", registro_id=presc.pk).exists()
        )


class AcoesDetalheCurtasTests(TestCase):
    """Regressão: nenhuma ação de detalhe excede 20 caracteres."""

    def test_acoes_de_detalhe_cabem_em_20_caracteres(self):
        acoes = [
            "ACESSO_CONSULTA",
            "ACESSO_AVALIACAO_DET",
            "ACESSO_TREINO",
        ]
        for acao in acoes:
            self.assertLessEqual(
                len(acao), 20,
                f"Ação {acao!r} excede 20 caracteres ({len(acao)}).",
            )
"""Testes de isolamento do portal do paciente — consulta, avaliação,
evolução e cancelamento.

Prova o padrão de segurança do portal: toda view filtra por
`paciente=request.paciente` na própria query, devolvendo 404 uniforme
para recurso de outro paciente. Não revela existência do uuid.

Usa TestCase (não TransactionTestCase) porque nenhum teste aqui toca
FileField/FileResponse.

Notas de fixture:
- Avaliacao e Evolucao com status LIBERADA exigem liberado_por e
  liberado_em (CHECK ck_*_liberada_com_rastreio).
- A agenda é criada com 3 dias de antecedência para que
  Agendamento.pode_cancelar não bloqueie por janela mínima.
"""
from datetime import time, timedelta

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.constants import GRUPO_PACIENTE
from apps.accounts.models import Usuario
from apps.clinic.models import TipoAtendimento
from apps.clinical.models import Avaliacao, Evolucao
from apps.patients.models import Paciente, PacienteProfissional
from apps.professionals.models import Profissional
from apps.registry.models import ConselhoProfissional
from apps.scheduling.models import Agendamento, Agenda, SlotAgenda


class PortalIsolamentoBase(TestCase):
    """Setup compartilhado: dois pacientes, profissional, tipo de
    atendimento, agenda e slot."""

    @classmethod
    def setUpTestData(cls):
        grupo, _ = Group.objects.get_or_create(name=GRUPO_PACIENTE)

        # ── Paciente A ──────────────────────────────────────────
        cls.user_a = Usuario.objects.create_user(
            username="pac_a", email="a@test.local", password="x",
        )
        cls.user_a.groups.add(grupo)
        cls.paciente_a = Paciente.objects.create(
            nome_completo="Paciente A", user=cls.user_a,
        )

        # ── Paciente B ──────────────────────────────────────────
        cls.user_b = Usuario.objects.create_user(
            username="pac_b", email="b@test.local", password="x",
        )
        cls.user_b.groups.add(grupo)
        cls.paciente_b = Paciente.objects.create(
            nome_completo="Paciente B", user=cls.user_b,
        )

        # ── Conselho (obrigatório para Profissional) ────────────
        cls.conselho, _ = ConselhoProfissional.objects.get_or_create(
            sigla="CREFITO",
            defaults={"nome": "Conselho Regional de Fisioterapia"},
        )

        # ── Profissional ────────────────────────────────────────
        cls.user_prof = Usuario.objects.create_user(
            username="prof", email="p@test.local", password="x",
        )
        cls.profissional = Profissional.objects.create(
            nome_completo="Fisio Teste",
            user=cls.user_prof,
            conselho=cls.conselho,
            registro_conselho="123456-F",
            status=Profissional.Status.ATIVO,
        )

        # ── Tipo de atendimento ─────────────────────────────────
        cls.tipo = TipoAtendimento.objects.create(
            nome="Fisioterapia Motora",
            duracao_minutos=50,
            ativo=True,
        )

        # ── Agenda e slot ───────────────────────────────────────
        # 3 dias de antecedência: Agendamento.pode_cancelar costuma
        # exigir janela mínima (24h/48h). Com 1 dia o teste falha
        # por bloqueio de política, não por bug de view.
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

    def _criar_agendamento(self, paciente, slot=None):
        """Cria agendamento ocupando o slot informado."""
        slot = slot or self.slot
        agendamento = Agendamento.objects.create(
            paciente=paciente,
            profissional=self.profissional,
            tipo_atendimento=self.tipo,
            slot=slot,
            status=Agendamento.Status.AGENDADO,
        )
        slot.status = SlotAgenda.Status.OCUPADO
        slot.save(update_fields=["status", "updated_at"])
        return agendamento


class ConsultaIsolamentoTests(PortalIsolamentoBase):
    """Isolamento em consultas (agendamentos)."""

    def test_consulta_de_outro_paciente_devolve_404(self):
        ag = self._criar_agendamento(self.paciente_b)
        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:consulta_detalhe", kwargs={"uuid": ag.uuid})
        )
        self.assertEqual(resposta.status_code, 404)

    def test_consulta_propria_retorna_200(self):
        ag = self._criar_agendamento(self.paciente_a)
        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:consulta_detalhe", kwargs={"uuid": ag.uuid})
        )
        self.assertEqual(resposta.status_code, 200)

    def test_listagem_so_mostra_consultas_do_paciente(self):
        ag_a = self._criar_agendamento(self.paciente_a)

        slot_b = SlotAgenda.objects.create(
            agenda=self.agenda,
            hora_inicio=time(11, 0),
            hora_fim=time(11, 50),
            status=SlotAgenda.Status.LIVRE,
        )
        ag_b = self._criar_agendamento(self.paciente_b, slot=slot_b)

        self.client.force_login(self.user_a)
        resposta = self.client.get(reverse("portal:consultas"))
        self.assertEqual(resposta.status_code, 200)

        consultas = list(resposta.context["consultas"])
        self.assertIn(ag_a, consultas)
        self.assertNotIn(ag_b, consultas)


class CancelamentoIsolamentoTests(PortalIsolamentoBase):
    """Isolamento no cancelamento — POST de outro paciente deve dar 404."""

    def test_cancelar_consulta_de_outro_paciente_devolve_404(self):
        ag = self._criar_agendamento(self.paciente_b)
        self.client.force_login(self.user_a)
        resposta = self.client.post(
            reverse("portal:cancelar_consulta", kwargs={"uuid": ag.uuid}),
            {"motivo": "Teste de invasão"},
        )
        self.assertEqual(resposta.status_code, 404)

        ag.refresh_from_db()
        self.assertEqual(ag.status, Agendamento.Status.AGENDADO)

    def test_cancelar_consulta_propria_funciona(self):
        ag = self._criar_agendamento(self.paciente_a)

        # Pré-condição: o agendamento precisa estar cancelável.
        # Se falhar aqui, é política de janela mínima — ajuste a
        # antecedência em PortalIsolamentoBase.setUpTestData.
        self.assertTrue(
            ag.pode_cancelar,
            f"Agendamento não cancelável: {ag.motivo_bloqueio_cancelamento}",
        )

        self.client.force_login(self.user_a)
        resposta = self.client.post(
            reverse("portal:cancelar_consulta", kwargs={"uuid": ag.uuid}),
            {"motivo": "Imprevisto pessoal"},
        )
        self.assertIn(resposta.status_code, (200, 302))

        ag.refresh_from_db()
        self.assertEqual(ag.status, Agendamento.Status.CANCELADO)

    def test_cancelar_sem_motivo_nao_cancela(self):
        ag = self._criar_agendamento(self.paciente_a)
        self.client.force_login(self.user_a)
        resposta = self.client.post(
            reverse("portal:cancelar_consulta", kwargs={"uuid": ag.uuid}),
            {"motivo": ""},
        )
        self.assertIn(resposta.status_code, (200, 302))

        ag.refresh_from_db()
        self.assertEqual(ag.status, Agendamento.Status.AGENDADO)


class AvaliacaoIsolamentoTests(PortalIsolamentoBase):
    """Isolamento em avaliações — só liberadas e só do próprio paciente."""

    def _criar_avaliacao(self, paciente, status=Avaliacao.Status.LIBERADA):
        kwargs = {
            "paciente": paciente,
            "profissional": self.profissional,
            "status": status,
        }
        # CHECK ck_avaliacao_liberada_com_rastreio: status='L' exige
        # liberado_por e liberado_em preenchidos.
        if status == Avaliacao.Status.LIBERADA:
            kwargs["liberado_por"] = self.user_prof
            kwargs["liberado_em"] = timezone.now()
        return Avaliacao.objects.create(**kwargs)

    def test_avaliacao_de_outro_paciente_devolve_404(self):
        av = self._criar_avaliacao(self.paciente_b)
        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:avaliacao_detalhe", kwargs={"uuid": av.uuid})
        )
        self.assertEqual(resposta.status_code, 404)

    def test_avaliacao_propria_liberada_retorna_200(self):
        av = self._criar_avaliacao(self.paciente_a)
        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:avaliacao_detalhe", kwargs={"uuid": av.uuid})
        )
        self.assertEqual(resposta.status_code, 200)

    def test_avaliacao_em_rascunho_devolve_404(self):
        """Rascunho nunca é visível no portal, mesmo do próprio paciente."""
        av = self._criar_avaliacao(
            self.paciente_a, status=Avaliacao.Status.PENDENTE,
        )
        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:avaliacao_detalhe", kwargs={"uuid": av.uuid})
        )
        self.assertEqual(resposta.status_code, 404)

    def test_listagem_so_mostra_avaliacoes_liberadas(self):
        av_liberada = self._criar_avaliacao(self.paciente_a)
        av_rascunho = self._criar_avaliacao(
            self.paciente_a, status=Avaliacao.Status.PENDENTE,
        )

        self.client.force_login(self.user_a)
        resposta = self.client.get(reverse("portal:avaliacoes"))
        self.assertEqual(resposta.status_code, 200)

        avaliacoes = list(resposta.context["avaliacoes"])
        self.assertIn(av_liberada, avaliacoes)
        self.assertNotIn(av_rascunho, avaliacoes)


class EvolucaoIsolamentoTests(PortalIsolamentoBase):
    """Isolamento em evoluções — só liberadas e só do próprio paciente."""

    def _criar_evolucao(self, paciente, status=Evolucao.Status.LIBERADA):
        kwargs = {
            "paciente": paciente,
            "profissional": self.profissional,
            "status": status,
            "subjetivo": "Paciente relata melhora.",
            "objetivo": "Amplitude de movimento preservada.",
            "avaliacao": "Boa evolução.",
            "plano": "Manter protocolo.",
        }
        # CHECK ck_evolucao_liberada_com_rastreio: status='L' exige
        # liberado_por e liberado_em preenchidos.
        if status == Evolucao.Status.LIBERADA:
            kwargs["liberado_por"] = self.user_prof
            kwargs["liberado_em"] = timezone.now()
        return Evolucao.objects.create(**kwargs)

    def test_listagem_so_mostra_evolucoes_liberadas(self):
        ev_liberada = self._criar_evolucao(self.paciente_a)
        ev_rascunho = self._criar_evolucao(
            self.paciente_a, status=Evolucao.Status.PENDENTE,
        )

        self.client.force_login(self.user_a)
        resposta = self.client.get(reverse("portal:evolucao"))
        self.assertEqual(resposta.status_code, 200)

        evolucoes = list(resposta.context["evolucoes"])
        self.assertIn(ev_liberada, evolucoes)
        self.assertNotIn(ev_rascunho, evolucoes)

    def test_listagem_nao_mostra_evolucao_de_outro_paciente(self):
        ev_b = self._criar_evolucao(self.paciente_b)

        self.client.force_login(self.user_a)
        resposta = self.client.get(reverse("portal:evolucao"))
        self.assertEqual(resposta.status_code, 200)

        evolucoes = list(resposta.context["evolucoes"])
        self.assertNotIn(ev_b, evolucoes)


class AcessoBasicoTests(PortalIsolamentoBase):
    """Guarda de acesso: usuário sem vínculo e não autenticado."""

    def test_usuario_sem_vinculo_recebe_403(self):
        user_sem_vinculo = Usuario.objects.create_user(
            username="sem_vinculo", email="s@test.local", password="x",
        )
        user_sem_vinculo.groups.add(Group.objects.get(name=GRUPO_PACIENTE))
        self.client.force_login(user_sem_vinculo)
        resposta = self.client.get(reverse("portal:consultas"))
        self.assertEqual(resposta.status_code, 403)

    def test_anonimo_redireciona_para_login(self):
        resposta = self.client.get(reverse("portal:consultas"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/conta/", resposta.url)

    def test_contato_nao_permite_destinatario_arbitrario(self):
        """O paciente só pode enviar mensagem para profissionais da sua equipe."""
        profissional_externo = Profissional.objects.create(
            nome_completo="Fisio Externo",
            user=Usuario.objects.create_user(username="ext", password="x"),
            conselho=self.conselho,
            registro_conselho="999999-F",
            status=Profissional.Status.ATIVO,
        )
        self.client.force_login(self.user_a)
        resposta = self.client.post(reverse("portal:contato"), {
            "destinatario": profissional_externo.pk,
            "corpo": "Mensagem indevida",
        })
        # Hoje isso passa. Deveria ser bloqueado.
        self.assertNotEqual(resposta.status_code, 302)   
             
    def test_contato_permite_destinatario_da_equipe(self):
        PacienteProfissional.objects.create(
            paciente=self.paciente_a,
            profissional=self.profissional,
            ativo=True,
        )
        self.client.force_login(self.user_a)
        resposta = self.client.post(reverse("portal:contato"), {
            "destinatario": self.profissional.pk,
            "corpo": "Gostaria de remarcar minha sessão.",
        })
        self.assertEqual(resposta.status_code, 302) 
"""Testes de isolamento do portal do paciente.

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
- Notificacao NÃO tem FK para paciente: o escopo é por `destinatario`
  (Usuario). Como Paciente.user é OneToOneField, um user = um paciente,
  então o contador de home() é seguro por construção.
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
from apps.communication.models import Notificacao
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

    def _criar_slot_extra(self, hora_inicio, hora_fim):
        """Cria slot adicional na mesma agenda (para o segundo paciente)."""
        return SlotAgenda.objects.create(
            agenda=self.agenda,
            hora_inicio=hora_inicio,
            hora_fim=hora_fim,
            status=SlotAgenda.Status.LIVRE,
        )


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
        slot_b = self._criar_slot_extra(time(11, 0), time(11, 50))
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
    """Guarda de acesso: usuário sem vínculo, soft-deletado e anônimo."""

    def test_usuario_sem_vinculo_recebe_403(self):
        user_sem_vinculo = Usuario.objects.create_user(
            username="sem_vinculo", email="s@test.local", password="x",
        )
        user_sem_vinculo.groups.add(Group.objects.get(name=GRUPO_PACIENTE))

        self.client.force_login(user_sem_vinculo)
        resposta = self.client.get(reverse("portal:consultas"))
        self.assertEqual(resposta.status_code, 403)

    def test_paciente_soft_deletado_recebe_403(self):
        """Paciente com deleted_at preenchido é tratado como sem vínculo."""
        self.paciente_a.deleted_at = timezone.now()
        self.paciente_a.save(update_fields=["deleted_at"])

        self.client.force_login(self.user_a)
        resposta = self.client.get(reverse("portal:consultas"))
        self.assertEqual(resposta.status_code, 403)

    def test_anonimo_redireciona_para_login(self):
        resposta = self.client.get(reverse("portal:consultas"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/conta/", resposta.url)

    def test_contato_nao_permite_destinatario_arbitrario(self):
        """Profissional fora da equipe é rejeitado — view re-renderiza
        com erro e NÃO cria notificação para o destinatário."""
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

        # Re-renderiza o formulário com erro — não redireciona.
        self.assertEqual(resposta.status_code, 200)
        # E o bloqueio é real: nenhuma notificação foi criada.
        self.assertFalse(
            Notificacao.objects.filter(
                destinatario=profissional_externo.user,
            ).exists()
        )

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


class HomePerfilIsolamentoTests(PortalIsolamentoBase):
    """home() e perfil() não vazam dados entre pacientes.

    Notificacao não tem FK para paciente: o escopo é por `destinatario`.
    Como Paciente.user é OneToOneField, um user = um paciente — então
    o contador por destinatario já é seguro por construção.
    """

    def _criar_notificacao(self, destinatario, lida=False, titulo="Notificação"):
        return Notificacao.objects.create(
            destinatario=destinatario,
            tipo=Notificacao.Tipo.SISTEMA,
            titulo=titulo,
            mensagem="Mensagem de teste.",
            lida=lida,
        )

    def test_home_conta_apenas_notificacoes_nao_lidas_do_usuario(self):
        """O contador reflete só notificações não lidas do user logado."""
        self._criar_notificacao(self.user_a, lida=False, titulo="A não lida")
        self._criar_notificacao(self.user_a, lida=True, titulo="A lida")
        self._criar_notificacao(self.user_b, lida=False, titulo="B não lida")

        self.client.force_login(self.user_a)
        resposta = self.client.get(reverse("portal:home"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["nao_lidas"], 1)

    def test_home_nao_mostra_agendamento_de_outro_paciente(self):
        """Agendamento de B não aparece como 'próximo' para A."""
        self._criar_agendamento(self.paciente_b)

        self.client.force_login(self.user_a)
        resposta = self.client.get(reverse("portal:home"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(resposta.context["proximo"])

    def test_home_mostra_agendamento_do_proprio_paciente(self):
        """Par positivo do teste acima: sem ele, o negativo passa mesmo
        se home() estiver quebrada e nunca mostrar nada."""
        ag = self._criar_agendamento(self.paciente_a)

        self.client.force_login(self.user_a)
        resposta = self.client.get(reverse("portal:home"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["proximo"], ag)

    def test_perfil_exibe_paciente_do_usuario_logado(self):
        self.client.force_login(self.user_a)
        resposta = self.client.get(reverse("portal:perfil"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["paciente"], self.paciente_a)

    def test_perfil_de_outro_paciente_nao_e_acessivel(self):
        """perfil() não aceita uuid — sempre o do usuário logado."""
        self.client.force_login(self.user_b)
        resposta = self.client.get(reverse("portal:perfil"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["paciente"], self.paciente_b)
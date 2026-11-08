"""Testes da frente de Treinos no portal do paciente.

Prova o isolamento por paciente (uuid público + filtro de dono na
query), o filtro por status da prescrição e o registro de execução
com criado_via=PORTAL.

Notas de model:
- Prescricao tem deleted_at e uuid.
- PrescricaoExercicio NÃO tem deleted_at — usa só o flag ativo.
- ExecucaoExercicio tem deleted_at, mas NÃO tem uuid.
"""
from datetime import timedelta

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.constants import GRUPO_PACIENTE
from apps.accounts.models import Usuario
from apps.exercise.models import (
    Exercicio,
    ExecucaoExercicio,
    Prescricao,
    PrescricaoExercicio,
)
from apps.patients.models import Paciente
from apps.professionals.models import Profissional
from apps.registry.models import ConselhoProfissional


class TreinosBase(TestCase):
    """Setup: dois pacientes, um profissional, um exercício."""

    @classmethod
    def setUpTestData(cls):
        grupo, _ = Group.objects.get_or_create(name=GRUPO_PACIENTE)

        cls.user_a = Usuario.objects.create_user(
            username="pa", email="a@t.local", password="x",
        )
        cls.user_a.groups.add(grupo)
        cls.paciente_a = Paciente.objects.create(
            nome_completo="Paciente A", user=cls.user_a,
        )

        cls.user_b = Usuario.objects.create_user(
            username="pb", email="b@t.local", password="x",
        )
        cls.user_b.groups.add(grupo)
        cls.paciente_b = Paciente.objects.create(
            nome_completo="Paciente B", user=cls.user_b,
        )

        cls.conselho, _ = ConselhoProfissional.objects.get_or_create(
            sigla="CREFITO",
            defaults={"nome": "Conselho Regional de Fisioterapia"},
        )
        cls.profissional = Profissional.objects.create(
            nome_completo="Fisio Teste",
            conselho=cls.conselho,
            registro_conselho="123456-F",
            status=Profissional.Status.ATIVO,
        )

        cls.exercicio = Exercicio.objects.create(
            nome="Flexão de joelho", ativo=True,
        )

    def _criar_prescricao(self, paciente, status=None, validade=None):
        return Prescricao.objects.create(
            paciente=paciente,
            profissional=self.profissional,
            status=status or Prescricao.Status.ATIVA,
            data_validade=validade,
        )

    def _criar_item(self, prescricao, ativo=True, exercicio=None):
        """Cria item com ordem sequencial — uq_prescricao_exercicio_ordem
        impede duas linhas com a mesma (prescricao, exercicio, ordem)."""
        exercicio = exercicio or self.exercicio
        proxima_ordem = (
            PrescricaoExercicio.objects.filter(prescricao=prescricao)
            .count() + 1
        )
        return PrescricaoExercicio.objects.create(
            prescricao=prescricao,
            exercicio=exercicio,
            ordem=proxima_ordem,
            series=3,
            repeticoes="10",
            ativo=ativo,
        )


class TreinosIsolamentoTests(TreinosBase):
    """Listagem e detalhe respeitam o dono e o status."""

    def test_listagem_so_mostra_prescricoes_do_paciente(self):
        p_a = self._criar_prescricao(self.paciente_a)
        p_b = self._criar_prescricao(self.paciente_b)

        self.client.force_login(self.user_a)
        resposta = self.client.get(reverse("portal:treinos"))
        self.assertEqual(resposta.status_code, 200)

        prescricoes = list(resposta.context["prescricoes"])
        self.assertIn(p_a, prescricoes)
        self.assertNotIn(p_b, prescricoes)

    def test_treino_de_outro_paciente_devolve_404(self):
        p_b = self._criar_prescricao(self.paciente_b)
        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:treino_detalhe", kwargs={"uuid": p_b.uuid})
        )
        self.assertEqual(resposta.status_code, 404)

    def test_treino_proprio_retorna_200(self):
        p_a = self._criar_prescricao(self.paciente_a)
        self._criar_item(p_a)

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:treino_detalhe", kwargs={"uuid": p_a.uuid})
        )
        self.assertEqual(resposta.status_code, 200)

    def test_prescricao_encerrada_nao_aparece(self):
        p = self._criar_prescricao(
            self.paciente_a, status=Prescricao.Status.ENCERRADA,
        )
        self.client.force_login(self.user_a)
        resposta = self.client.get(reverse("portal:treinos"))
        self.assertNotIn(p, list(resposta.context["prescricoes"]))

    def test_prescricao_cancelada_nao_aparece(self):
        p = self._criar_prescricao(
            self.paciente_a, status=Prescricao.Status.CANCELADA,
        )
        self.client.force_login(self.user_a)
        resposta = self.client.get(reverse("portal:treinos"))
        self.assertNotIn(p, list(resposta.context["prescricoes"]))

    def test_prescricao_vencida_nao_aparece(self):
        p = self._criar_prescricao(
            self.paciente_a,
            validade=timezone.localdate() - timedelta(days=1),
        )
        self.client.force_login(self.user_a)
        resposta = self.client.get(reverse("portal:treinos"))
        self.assertNotIn(p, list(resposta.context["prescricoes"]))

    def test_prescricao_vencendo_hoje_aparece(self):
        """Validade hoje ainda é válida — o filtro é >= hoje."""
        p = self._criar_prescricao(
            self.paciente_a, validade=timezone.localdate(),
        )
        self.client.force_login(self.user_a)
        resposta = self.client.get(reverse("portal:treinos"))
        self.assertIn(p, list(resposta.context["prescricoes"]))

    def test_treino_detalhe_nao_lista_item_inativo(self):
        p_a = self._criar_prescricao(self.paciente_a)
        item_ativo = self._criar_item(p_a, ativo=True)
        item_inativo = self._criar_item(p_a, ativo=False)

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:treino_detalhe", kwargs={"uuid": p_a.uuid})
        )
        itens = list(resposta.context["itens"])
        self.assertIn(item_ativo, itens)
        self.assertNotIn(item_inativo, itens)


class ExecucaoIsolamentoTests(TreinosBase):
    """Registro de execução respeita dono e cria com criado_via=PORTAL."""

    def test_executar_item_de_outro_paciente_devolve_404(self):
        p_b = self._criar_prescricao(self.paciente_b)
        item_b = self._criar_item(p_b)

        self.client.force_login(self.user_a)
        resposta = self.client.post(
            reverse("portal:executar_exercicio", kwargs={
                "uuid": p_b.uuid, "item_id": item_b.pk,
            }),
            {"series_feitas": "3", "repeticoes_feitas": "10"},
        )
        self.assertEqual(resposta.status_code, 404)
        self.assertFalse(
            ExecucaoExercicio.objects.filter(
                prescricao_exercicio=item_b,
            ).exists()
        )

    def test_executar_item_proprio_cria_execucao(self):
        p_a = self._criar_prescricao(self.paciente_a)
        item_a = self._criar_item(p_a)

        self.client.force_login(self.user_a)
        resposta = self.client.post(
            reverse("portal:executar_exercicio", kwargs={
                "uuid": p_a.uuid, "item_id": item_a.pk,
            }),
            {
                "series_feitas": "3",
                "repeticoes_feitas": "12",
                "percepcao_esforco": "7",
                "dor_eva": "2",
                "observacoes": "Sem dor durante o movimento.",
            },
        )
        self.assertEqual(resposta.status_code, 302)

        execucao = ExecucaoExercicio.objects.get(
            prescricao_exercicio=item_a,
        )
        self.assertEqual(execucao.paciente, self.paciente_a)
        self.assertEqual(execucao.series_feitas, 3)
        self.assertEqual(execucao.repeticoes_feitas, "12")
        self.assertEqual(execucao.percepcao_esforco, 7)
        self.assertEqual(execucao.dor_eva, 2)
        self.assertEqual(execucao.criado_via, ExecucaoExercicio.CriadoVia.PORTAL)
        self.assertTrue(execucao.realizado)
        self.assertEqual(execucao.data, timezone.localdate())

    def test_executar_item_inativo_devolve_404(self):
        p_a = self._criar_prescricao(self.paciente_a)
        item = self._criar_item(p_a, ativo=False)

        self.client.force_login(self.user_a)
        resposta = self.client.post(
            reverse("portal:executar_exercicio", kwargs={
                "uuid": p_a.uuid, "item_id": item.pk,
            }),
            {"series_feitas": "3"},
        )
        self.assertEqual(resposta.status_code, 404)

    def test_executar_prescricao_encerrada_devolve_404(self):
        p = self._criar_prescricao(
            self.paciente_a, status=Prescricao.Status.ENCERRADA,
        )
        item = self._criar_item(p)

        self.client.force_login(self.user_a)
        resposta = self.client.post(
            reverse("portal:executar_exercicio", kwargs={
                "uuid": p.uuid, "item_id": item.pk,
            }),
            {"series_feitas": "3"},
        )
        self.assertEqual(resposta.status_code, 404)

    def test_executar_sem_autenticacao_redireciona(self):
        p_a = self._criar_prescricao(self.paciente_a)
        item_a = self._criar_item(p_a)
        resposta = self.client.post(
            reverse("portal:executar_exercicio", kwargs={
                "uuid": p_a.uuid, "item_id": item_a.pk,
            }),
            {"series_feitas": "3"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/conta/", resposta.url)

    def test_executar_com_get_nao_permite(self):
        p_a = self._criar_prescricao(self.paciente_a)
        item_a = self._criar_item(p_a)
        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:executar_exercicio", kwargs={
                "uuid": p_a.uuid, "item_id": item_a.pk,
            })
        )
        self.assertEqual(resposta.status_code, 405)

    def test_executar_com_campos_vazios_nao_quebra(self):
        """Campos opcionais vazios viram None, não erro."""
        p_a = self._criar_prescricao(self.paciente_a)
        item_a = self._criar_item(p_a)

        self.client.force_login(self.user_a)
        resposta = self.client.post(
            reverse("portal:executar_exercicio", kwargs={
                "uuid": p_a.uuid, "item_id": item_a.pk,
            }),
            {"series_feitas": "", "repeticoes_feitas": ""},
        )
        self.assertEqual(resposta.status_code, 302)

        execucao = ExecucaoExercicio.objects.get(
            prescricao_exercicio=item_a,
        )
        self.assertIsNone(execucao.series_feitas)
        self.assertIsNone(execucao.repeticoes_feitas)
        self.assertTrue(execucao.realizado)


class ExecutadosSetTests(TreinosBase):
    """O set de executados alimenta o badge 'Feito' no template."""

    def test_treino_detalhe_marca_item_executado(self):
        p_a = self._criar_prescricao(self.paciente_a)
        item_a = self._criar_item(p_a)

        ExecucaoExercicio.objects.create(
            prescricao_exercicio=item_a,
            paciente=self.paciente_a,
            realizado=True,
            series_feitas=3,
            criado_via=ExecucaoExercicio.CriadoVia.PORTAL,
        )

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:treino_detalhe", kwargs={"uuid": p_a.uuid})
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(item_a.pk, resposta.context["executados"])

    def test_treino_detalhe_nao_marca_item_sem_execucao(self):
        p_a = self._criar_prescricao(self.paciente_a)
        item_a = self._criar_item(p_a)

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:treino_detalhe", kwargs={"uuid": p_a.uuid})
        )
        self.assertNotIn(item_a.pk, resposta.context["executados"])

    def test_execucao_soft_deleted_nao_marca_item(self):
        """Execução com deleted_at preenchido não conta como feita."""
        p_a = self._criar_prescricao(self.paciente_a)
        item_a = self._criar_item(p_a)

        ExecucaoExercicio.objects.create(
            prescricao_exercicio=item_a,
            paciente=self.paciente_a,
            realizado=True,
            deleted_at=timezone.now(),
            criado_via=ExecucaoExercicio.CriadoVia.PORTAL,
        )

        self.client.force_login(self.user_a)
        resposta = self.client.get(
            reverse("portal:treino_detalhe", kwargs={"uuid": p_a.uuid})
        )
        self.assertNotIn(item_a.pk, resposta.context["executados"])
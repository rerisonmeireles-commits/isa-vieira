"""Testes do vínculo paciente-profissional.

Prova o ciclo de vida do vínculo: unicidade do ativo, histórico de
encerrados, coerência de vigência e integração com o portal.
"""
from datetime import timedelta

from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.constants import GRUPO_PACIENTE
from apps.accounts.models import Usuario
from apps.patients.models import Paciente, PacienteProfissional
from apps.professionals.models import Profissional
from apps.registry.models import ConselhoProfissional


class VinculoBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        grupo, _ = Group.objects.get_or_create(name=GRUPO_PACIENTE)

        cls.user_pac = Usuario.objects.create_user(
            username="pac", email="p@test.local", password="x",
        )
        cls.user_pac.groups.add(grupo)
        cls.paciente = Paciente.objects.create(
            nome_completo="Paciente Teste", user=cls.user_pac,
        )

        cls.conselho, _ = ConselhoProfissional.objects.get_or_create(
            sigla="CREFITO",
            defaults={"nome": "Conselho Regional de Fisioterapia"},
        )

        cls.user_prof = Usuario.objects.create_user(
            username="prof", email="pr@test.local", password="x",
        )
        cls.profissional = Profissional.objects.create(
            nome_completo="Fisio Teste",
            user=cls.user_prof,
            conselho=cls.conselho,
            registro_conselho="123456-F",
            status=Profissional.Status.ATIVO,
        )


class UnicidadeVinculoTests(VinculoBase):
    """O índice único parcial garante um só vínculo ativo por par."""

    def test_nao_permite_dois_vinculos_ativos(self):
        PacienteProfissional.objects.create(
            paciente=self.paciente,
            profissional=self.profissional,
            ativo=True,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PacienteProfissional.objects.create(
                    paciente=self.paciente,
                    profissional=self.profissional,
                    ativo=True,
                )

    def test_permite_vinculo_historico_encerrado(self):
        hoje = timezone.localdate()
        PacienteProfissional.objects.create(
            paciente=self.paciente, profissional=self.profissional,
            ativo=False,
            inicio_vigencia=hoje - timedelta(days=90),
            fim_vigencia=hoje - timedelta(days=30),
        )
        PacienteProfissional.objects.create(
            paciente=self.paciente, profissional=self.profissional,
            ativo=False,
            inicio_vigencia=hoje - timedelta(days=30),
            fim_vigencia=hoje - timedelta(days=10),
        )
        PacienteProfissional.objects.create(
            paciente=self.paciente, profissional=self.profissional,
            ativo=True,
            inicio_vigencia=hoje - timedelta(days=10),
        )
        self.assertEqual(
            PacienteProfissional.objects.filter(
                paciente=self.paciente, profissional=self.profissional,
            ).count(),
            3,
        )

    def test_permite_vinculo_ativo_apos_encerrar_anterior(self):
        """Encerrar o ativo e criar outro: o índice parcial libera."""
        v1 = PacienteProfissional.objects.create(
            paciente=self.paciente,
            profissional=self.profissional,
            ativo=True,
        )
        v1.ativo = False
        v1.fim_vigencia = timezone.localdate()
        v1.save()

        v2 = PacienteProfissional.objects.create(
            paciente=self.paciente,
            profissional=self.profissional,
            ativo=True,
        )
        self.assertNotEqual(v1.pk, v2.pk)


class VigenciaVinculoTests(VinculoBase):
    """A CHECK constraint impede vigência incoerente."""

    def test_fim_anterior_ao_inicio_viola_check(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PacienteProfissional.objects.create(
                    paciente=self.paciente,
                    profissional=self.profissional,
                    inicio_vigencia=timezone.localdate(),
                    fim_vigencia=timezone.localdate() - timedelta(days=1),
                )

    def test_fim_igual_ao_inicio_e_valido(self):
        """Vínculo de um dia só: fim == início é permitido.

        Precisa de ativo=False: ck_vinculo_ativo_sem_fim proíbe
        vínculo ativo com fim_vigencia preenchido.
        """
        hoje = timezone.localdate()
        v = PacienteProfissional.objects.create(
            paciente=self.paciente,
            profissional=self.profissional,
            ativo=False,
            inicio_vigencia=hoje,
            fim_vigencia=hoje,
        )
        self.assertEqual(v.fim_vigencia, hoje)
        self.assertFalse(v.ativo)

class PortalUsaVinculoTests(VinculoBase):
    """O contato() do portal filtra por vínculo, não por agendamento."""

    def test_contato_lista_apenas_profissionais_vinculados(self):
        PacienteProfissional.objects.create(
            paciente=self.paciente,
            profissional=self.profissional,
            ativo=True,
        )
        self.client.force_login(self.user_pac)
        resposta = self.client.get(reverse("portal:contato"))
        self.assertEqual(resposta.status_code, 200)

        profissionais = list(resposta.context["profissionais"])
        self.assertIn(self.profissional, profissionais)

    def test_contato_nao_lista_profissional_sem_vinculo(self):
        self.client.force_login(self.user_pac)
        resposta = self.client.get(reverse("portal:contato"))
        self.assertEqual(resposta.status_code, 200)

        profissionais = list(resposta.context["profissionais"])
        self.assertNotIn(self.profissional, profissionais)

    def test_contato_nao_lista_vinculo_encerrado(self):
        hoje = timezone.localdate()
        PacienteProfissional.objects.create(
            paciente=self.paciente, profissional=self.profissional,
            ativo=False,
            inicio_vigencia=hoje - timedelta(days=30),
            fim_vigencia=hoje - timedelta(days=1),
        )
        self.client.force_login(self.user_pac)
        resposta = self.client.get(reverse("portal:contato"))
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn(self.profissional, list(resposta.context["profissionais"]))  


class EncerrarVinculoTests(VinculoBase):
    """O método encerrar() mantém a invariante ativo/fim."""

    def test_encerrar_seta_fim_e_desativa(self):
        v = PacienteProfissional.objects.create(
            paciente=self.paciente, profissional=self.profissional, ativo=True,
        )
        v.encerrar()
        v.refresh_from_db()
        self.assertFalse(v.ativo)
        self.assertEqual(v.fim_vigencia, timezone.localdate())

    def test_encerrar_e_idempotente(self):
        v = PacienteProfissional.objects.create(
            paciente=self.paciente, profissional=self.profissional, ativo=True,
        )
        v.encerrar()
        primeira_data = v.fim_vigencia
        v.encerrar()  # segunda chamada não muda nada
        v.refresh_from_db()
        self.assertEqual(v.fim_vigencia, primeira_data)

    def test_reativar_limpa_fim(self):
        v = PacienteProfissional.objects.create(
            paciente=self.paciente, profissional=self.profissional, ativo=True,
        )
        v.encerrar()
        v.reativar()
        v.refresh_from_db()
        self.assertTrue(v.ativo)
        self.assertIsNone(v.fim_vigencia)

    def test_ativo_com_fim_viola_check(self):
        """ck_vinculo_ativo_sem_fim impede estado contraditório."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PacienteProfissional.objects.create(
                    paciente=self.paciente,
                    profissional=self.profissional,
                    ativo=True,
                    inicio_vigencia=timezone.localdate() - timedelta(days=10),
                    fim_vigencia=timezone.localdate(),
                )

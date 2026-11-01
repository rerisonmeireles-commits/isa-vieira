"""Testes de cancelamento de consulta pelo portal do paciente.

Cobre os caminhos que decidem o comportamento do endpoint: libera o slot,
bloqueia por prazo de 24h, bloqueia por status não cancelável, exige motivo,
recusa GET e devolve 404 para consulta de outro paciente.

Todos usam TestCase (rollback por transação) - a suíte roda em ~12s em vez
de ~80s. Se algum dia for escrito um teste de CONCORRÊNCIA real (dois
requests disputando o mesmo slot), ele precisa ser TransactionTestCase:
select_for_update dentro de TestCase não bloqueia de fato, porque a
transação do teste já está aberta.
"""
import os
import tempfile
import shutil

from datetime import date, datetime, time, timedelta

from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.constants import GRUPOS_DOCUMENTOS
from apps.audit.models import LogAuditoria
from apps.clinic.models import TipoAtendimento
from apps.patients.models import Paciente
from apps.professionals.models import Profissional
from apps.registry.models import ConselhoProfissional as Conselho
from apps.scheduling.models import Agenda, Agendamento, SlotAgenda
from apps.clinical.models import Avaliacao
from apps.documents.models import Documento

Usuario = get_user_model()


class CancelamentoBase:
    """Mixin com setUp e helpers compartilhados.

    NÃO herda de TestCase de propósito: sem herança, o unittest não coleta
    esta classe e os testes rodam apenas nas subclasses concretas.
    """

    def setUp(self):
        self.user = Usuario.objects.create_user(
            username="paciente_teste",
            email="paciente@teste.com",
            password="senha123",
        )
        self.outro_user = Usuario.objects.create_user(
            username="outro_paciente",
            email="outro@teste.com",
            password="senha123",
        )

        self.paciente = self._criar_paciente(
            self.user, "Paciente Teste", "11111111111"
        )
        self.outro_paciente = self._criar_paciente(
            self.outro_user, "Outro Paciente", "22222222222"
        )

        self.conselho = self._criar_conselho()
        self.profissional = self._criar_profissional(self.conselho)

        self.tipo = TipoAtendimento.objects.create(
            nome="Fisioterapia Motora",
            duracao_minutos=30,
        )

        self.client.force_login(self.user)

    def _criar_paciente(self, usuario, nome, cpf):
        """Paciente.user é OneToOneField direto - não há vínculo reverso."""
        return Paciente.objects.create(
            user=usuario,
            nome_completo=nome,
            cpf=cpf,
            data_nascimento=date(1990, 1, 1),
            sexo="F",
            email=usuario.email,
        )

    def _criar_conselho(self):
        """Conselho é FK obrigatória do Profissional."""
        conselho, _ = Conselho.objects.get_or_create(
            sigla="CREFITO",
            defaults={
                "nome": "Conselho Regional de Fisioterapia e Terapia Ocupacional",
            },
        )
        return conselho

    def _criar_profissional(self, conselho):
        return Profissional.objects.create(
            nome_completo="Fisioterapeuta Teste",
            registro_conselho="123456-F",
            conselho=conselho,
        )

    def _montar_consulta(
        self,
        *,
        horas_no_futuro=72,
        status=None,
        paciente=None,
        hora_inicio=time(10, 0),
    ):
        """Agenda + slot + agendamento coerentes.

        Três decisões não óbvias:
        - hora fixa às 10:00: a CheckConstraint hora_fim > hora_inicio torna
          inválido slot que cruze meia-noite, o que acontecia ao derivar a
          hora de "agora". Teste que falha só à noite é o pior tipo.
        - get_or_create na Agenda: uq_agenda_prof_data impede duas agendas
          para (profissional, data). Com get_or_create, dois agendamentos
          no mesmo dia coexistem em slots diferentes.
        - agenda=agenda (o objeto), NUNCA agenda_id=agenda: sem `.pk` o ORM
          escreve a instância na coluna inteira e estoura TypeError.
        """
        paciente = paciente or self.paciente
        hora_fim = (
            datetime.combine(date.min, hora_inicio) + timedelta(minutes=30)
        ).time()

        agora = timezone.localtime()
        if horas_no_futuro <= 24:
            # hoje às 10:00 se ainda não passou; senão amanhã. Nesse ramo a
            # distância máxima é 23h59 - sempre dentro da janela de bloqueio.
            dia = (
                agora.date()
                if agora.time() < hora_inicio
                else agora.date() + timedelta(days=1)
            )
        else:
            dia = (agora + timedelta(hours=horas_no_futuro)).date()

        agenda, _ = Agenda.objects.get_or_create(
            profissional=self.profissional,
            data=dia,
            defaults={"status": Agenda.Status.GERADA},
        )

        slot, _ = SlotAgenda.objects.get_or_create(
            agenda=agenda,
            hora_inicio=hora_inicio,
            defaults={
                "hora_fim": hora_fim,
                "status": SlotAgenda.Status.OCUPADO,
            },
        )
        if slot.status != SlotAgenda.Status.OCUPADO:
            slot.status = SlotAgenda.Status.OCUPADO
            slot.save(update_fields=["status", "updated_at"])

        consulta = Agendamento.objects.create(
            slot=slot,
            duracao_minutos=30,
            paciente=paciente,
            profissional=self.profissional,
            tipo_atendimento=self.tipo,
            status=status or Agendamento.Status.AGENDADO,
            origem=Agendamento.Origem.PORTAL,
            criado_por=self.user,
        )
        consulta.slots_ocupados.add(slot)
        return consulta

    def _criar_documento(self, *, paciente, visivel=True):
        """Documento com os campos obrigatórios do modelo real.

        `arquivo` é FileField obrigatório, mas os testes de 403 e 404
        esperam a resposta ANTES de abrir o arquivo - o path fictício
        nunca é lido do disco. Só o teste de 200 precisa de arquivo real.
        """
        return Documento.objects.create(
            paciente=paciente,
            profissional=self.profissional,
            tipo=Documento.Tipo.ATESTADO,
            titulo="Atestado de teste",
            arquivo="documentos/teste.pdf",
            visivel_paciente=visivel,
        ) 

    
class CancelamentoCaminhosTests(CancelamentoBase, TestCase):
    """Caminho feliz e bloqueios de regra de negócio."""

    def _url(self, consulta):
        return reverse("portal:cancelar_consulta", args=[consulta.uuid])

    def test_cancela_e_libera_o_slot(self):
        consulta = self._montar_consulta()

        resposta = self.client.post(
            self._url(consulta),
            {"motivo": "Viagem agendada"},
        )
        self.assertRedirects(
            resposta,
            reverse("portal:consultas"),
            fetch_redirect_response=False,
        )

        consulta.refresh_from_db()
        self.assertEqual(consulta.status, Agendamento.Status.CANCELADO)
        self.assertEqual(consulta.cancelado_por, self.user)
        self.assertEqual(consulta.motivo_cancelamento, "Viagem agendada")

        slot = SlotAgenda.objects.get(pk=consulta.slot_id)
        self.assertEqual(slot.status, SlotAgenda.Status.LIVRE)

    def test_bloqueia_por_prazo_de_24h(self):
        # 2h no futuro: dentro da janela de bloqueio.
        consulta = self._montar_consulta(horas_no_futuro=2)

        resposta = self.client.post(
            self._url(consulta),
            {"motivo": "Imprevisto"},
            follow=True,
        )

        consulta.refresh_from_db()
        self.assertEqual(consulta.status, Agendamento.Status.AGENDADO)
        self.assertIsNone(consulta.cancelado_por)

        slot = SlotAgenda.objects.get(pk=consulta.slot_id)
        self.assertEqual(slot.status, SlotAgenda.Status.OCUPADO)

        # A mensagem de bloqueio tem de chegar ao paciente.
        mensagens = [str(m) for m in resposta.context["messages"]]
        self.assertTrue(
            any("24h" in m for m in mensagens),
            f"mensagem de prazo ausente: {mensagens}",
        )

    def test_bloqueia_status_nao_cancelavel(self):
        consulta = self._montar_consulta(
            horas_no_futuro=72,
            status=Agendamento.Status.ATENDIDO,
        )

        resposta = self.client.post(
            self._url(consulta),
            {"motivo": "Tentativa indevida"},
            follow=True,
        )

        consulta.refresh_from_db()
        self.assertEqual(consulta.status, Agendamento.Status.ATENDIDO)

        mensagens = [str(m) for m in resposta.context["messages"]]
        self.assertTrue(any("realizada" in m for m in mensagens))

    def test_exige_motivo(self):
        consulta = self._montar_consulta()

        self.client.post(self._url(consulta), {"motivo": "   "})

        consulta.refresh_from_db()
        self.assertEqual(consulta.status, Agendamento.Status.AGENDADO)

    def test_get_nao_cancela(self):
        """require_POST: link em e-mail ou prefetch não dispara a ação."""
        consulta = self._montar_consulta()

        resposta = self.client.get(self._url(consulta))
        self.assertEqual(resposta.status_code, 405)

        consulta.refresh_from_db()
        self.assertEqual(consulta.status, Agendamento.Status.AGENDADO)

    def test_cancelamento_registra_auditoria(self):
        """Cancelar pelo portal grava LogAuditoria com contexto completo."""
        consulta = self._montar_consulta()

        resposta = self.client.post(
            self._url(consulta),
            {"motivo": "Imprevisto pessoal"},
        )
        self.assertEqual(resposta.status_code, 302)

        log = LogAuditoria.objects.get(
            acao="CANCELAMENTO_PORTAL",
            tabela="agendamento",
            registro_id=consulta.pk,
        )
        self.assertEqual(log.usuario, self.user)
        self.assertEqual(log.dados_antes["status"], "AGENDADO")
        self.assertEqual(log.dados_depois["status"], "CANCELADO")
        self.assertEqual(log.motivo, "Imprevisto pessoal")
        self.assertIsNotNone(log.ip)

##################################################################################################
###NOVOS TESTES
##################################################################################################
class IsolamentoViewsTests(CancelamentoBase, TestCase):
    """Paciente A não acessa recurso de B nas views do PORTAL."""

    def test_consulta_detalhe_de_outro_paciente_devolve_404(self):
        consulta_alheia = self._montar_consulta(paciente=self.outro_paciente)
        resposta = self.client.get(
            reverse("portal:consulta_detalhe", args=[consulta_alheia.uuid])
        )
        self.assertEqual(resposta.status_code, 404)

    def test_avaliacao_detalhe_de_outro_paciente_devolve_404(self):
        avaliacao_alheia = self._criar_avaliacao(paciente=self.outro_paciente)
        resposta = self.client.get(
            reverse("portal:avaliacao_detalhe", args=[avaliacao_alheia.uuid])
        )
        self.assertEqual(resposta.status_code, 404)


    def _criar_avaliacao(self, *, paciente, status=None):
        """Avaliação com os campos obrigatórios do modelo real.

        ck_avaliacao_liberada_com_rastreio: status='L' exige liberado_em e
        liberado_por NOT NULL.
        ck_avaliacao_inativada_com_rastreio: status='I' exige inativado_em e
        inativado_por NOT NULL.

        status=LIBERADA por padrão: o teste de isolamento precisa que o 404
        venha do filtro de paciente, não do filtro de status. Se ficasse
        PENDENTE, o teste passaria por motivo errado.
        """
        agora = timezone.now()
        dados = {
            "paciente": paciente,
            "profissional": self.profissional,
            "tipo": Avaliacao.Tipo.INICIAL,
            "status": status or Avaliacao.Status.LIBERADA,
        }
        if dados["status"] == Avaliacao.Status.LIBERADA:
            dados["liberado_em"] = agora
            dados["liberado_por"] = self.user
        elif dados["status"] == Avaliacao.Status.INATIVADA:
            dados["inativado_em"] = agora
            dados["inativado_por"] = self.user
        return Avaliacao.objects.create(**dados)    
    
class DocumentoDownloadPermissaoTests(CancelamentoBase, TestCase):
    """documento_download é view de STAFF: o controle é o grupo, não o dono."""

    def setUp(self):
        super().setUp()

        self.operador = Usuario.objects.create_user(
            username="operador_docs",
            email="operador@teste.com",
            password="senha123",
        )
        grupo, _ = Group.objects.get_or_create(name=GRUPOS_DOCUMENTOS[0])
        self.operador.groups.add(grupo)

        self.sem_grupo = Usuario.objects.create_user(
            username="sem_grupo",
            email="semgrupo@teste.com",
            password="senha123",
        )

        # ... criar paciente, profissional, documento

    def test_operador_com_grupo_baixa_qualquer_documento(self):
        """Cenário 1: o grupo dá acesso amplo - não há filtro por paciente."""
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)

        with override_settings(MEDIA_ROOT=media_root):
            documento = Documento.objects.create(
                paciente=self.paciente,
                profissional=self.profissional,
                tipo=Documento.Tipo.ATESTADO,
                titulo="Atestado de teste",
                arquivo=SimpleUploadedFile(
                    "atestado.pdf", b"%PDF-1.4 conteudo",
                    content_type="application/pdf",
                ),
                visivel_paciente=True,
            )
            self.client.force_login(self.operador)

            resposta = self.client.get(
                reverse("documents:documento_download", args=[documento.uuid])
            )

        self.assertEqual(resposta.status_code, 200)

    def test_operador_sem_grupo_recebe_403(self):
        """O grupo é o único controle de acesso desta view."""
        documento = self._criar_documento(paciente=self.paciente)
        self.client.force_login(self.sem_grupo)

        resposta = self.client.get(
            reverse("documents:documento_download", args=[documento.uuid])
        )

        self.assertEqual(resposta.status_code, 403)

    def test_documento_excluido_devolve_404(self):
        """Soft delete precisa valer no download, não só na listagem."""
        documento = self._criar_documento(paciente=self.paciente)
        documento.deleted_at = timezone.now()
        documento.save(update_fields=["deleted_at"])
        self.client.force_login(self.operador)

        resposta = self.client.get(
            reverse("documents:documento_download", args=[documento.uuid])
        )

        self.assertEqual(resposta.status_code, 404)
    
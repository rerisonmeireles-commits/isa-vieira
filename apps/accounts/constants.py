"""Fonte única dos nomes de grupos e perfis do portal.

⚠️ Os nomes precisam bater EXATAMENTE com o Django Admin (acentuação incluída).
"""
GRUPO_ADMINISTRADOR = "Administrador"
GRUPO_RECEPCAO = "Recepção"
GRUPO_FISIOTERAPEUTA = "Fisioterapeuta"
GRUPO_FINANCEIRO = "Financeiro"
GRUPO_PACIENTE = "Paciente"

# Grupos que operam a agenda no portal clínico (ver grade, confirmar,
# cancelar, marcar falta, reservar slot).
GRUPOS_AGENDA = (GRUPO_ADMINISTRADOR, GRUPO_RECEPCAO, GRUPO_FISIOTERAPEUTA)

# Grupos autorizados a gerar/reconciliar a grade (criar slots).
GRUPOS_GERACAO_GRADE = (GRUPO_ADMINISTRADOR, GRUPO_RECEPCAO)

# Todos os grupos com acesso ao portal clínico (exclui Paciente - portal próprio).
GRUPOS_PORTAL = (
    GRUPO_ADMINISTRADOR,
    GRUPO_RECEPCAO,
    GRUPO_FISIOTERAPEUTA,
    GRUPO_FINANCEIRO,
)

# Pacientes: quem visualiza e quem edita.
# Financeiro = consulta (só leitura); edição restrita aos perfis operacionais.
GRUPOS_PACIENTES_VER = GRUPOS_PORTAL
GRUPOS_PACIENTES_EDITAR = (GRUPO_ADMINISTRADOR, GRUPO_RECEPCAO, GRUPO_FISIOTERAPEUTA)

# Profissionais: apenas Administrador e Recepção operam o cadastro.
GRUPOS_PROFISSIONAIS_VER = (GRUPO_ADMINISTRADOR, GRUPO_RECEPCAO)
GRUPOS_PROFISSIONAIS_EDITAR = (GRUPO_ADMINISTRADOR, GRUPO_RECEPCAO)

# Convênios: catálogo de operadoras e planos.
GRUPOS_CONVENIOS_VER = (GRUPO_ADMINISTRADOR, GRUPO_RECEPCAO, GRUPO_FINANCEIRO)
GRUPOS_CONVENIOS_EDITAR = (GRUPO_ADMINISTRADOR, GRUPO_FINANCEIRO)

# Financeiro: contas a receber, pagamentos e faturamento.
GRUPOS_FINANCEIRO_VER = (GRUPO_ADMINISTRADOR, GRUPO_FINANCEIRO, GRUPO_RECEPCAO)
GRUPOS_FINANCEIRO_EDITAR = (GRUPO_ADMINISTRADOR, GRUPO_FINANCEIRO)

# Registry: cadastros básicos (Conselhos, Especialidades, Feriados).
GRUPOS_REGISTRY_VER = (GRUPO_ADMINISTRADOR,)
GRUPOS_REGISTRY_EDITAR = (GRUPO_ADMINISTRADOR,)

# Clinic/Estrutura: dados da clínica, configuração, salas e tipos de atendimento.
GRUPOS_CLINICA_VER = (GRUPO_ADMINISTRADOR,)
GRUPOS_CLINICA_EDITAR = (GRUPO_ADMINISTRADOR,)

GRUPOS_DOCUMENTOS = [GRUPO_ADMINISTRADOR, GRUPO_RECEPCAO, GRUPO_FISIOTERAPEUTA]
GRUPOS_DOCUMENTOS_GESTAO = [GRUPO_ADMINISTRADOR, GRUPO_FISIOTERAPEUTA]

# Gestão de usuários: exclusivo do Administrador
GRUPOS_USUARIOS_GESTAO = [GRUPO_ADMINISTRADOR]

# Consentimento LGPD: recepção registra, administrador revoga
GRUPOS_CONSENTIMENTO = [GRUPO_ADMINISTRADOR, GRUPO_RECEPCAO]
GRUPOS_CONSENTIMENTO_GESTAO = [GRUPO_ADMINISTRADOR]
VERSAO_TERMO_VIGENTE = "v1.0-2026"

# Atendimento (sessões clínicas): check-in e check-out são DECISÃO CLÍNICA.
# Decisão de 09/10/2026: a Recepção opera o balcão da agenda (confirmar,
# cancelar, falta), mas não inicia nem finaliza sessão.
GRUPOS_ATENDIMENTOS_INICIAR = (GRUPO_ADMINISTRADOR, GRUPO_FISIOTERAPEUTA)
GRUPOS_ATENDIMENTOS_CONCLUIR = (GRUPO_ADMINISTRADOR, GRUPO_FISIOTERAPEUTA)

# Prontuário clínico (prontuário, avaliações e evoluções).
# Acesso EXCLUSIVO dos perfis clínicos - dado de saúde sensível (LGPD).
# A Recepção NÃO visualiza o prontuário: opera dado administrativo/agenda.
# Decisão de 07/10/2026 - validada por smoke test de RBAC.
GRUPOS_CLINICO_VER = (GRUPO_ADMINISTRADOR, GRUPO_FISIOTERAPEUTA)
GRUPOS_CLINICO_EDITAR = (GRUPO_ADMINISTRADOR, GRUPO_FISIOTERAPEUTA)
GRUPOS_CLINICO_LIBERAR = (GRUPO_ADMINISTRADOR, GRUPO_FISIOTERAPEUTA)

# Exercícios: catálogo cinesiológico e prescrições.
# Atividade clínica do Fisioterapeuta - reutiliza os grupos clínicos.
GRUPOS_EXERCICIOS_VER = (GRUPO_ADMINISTRADOR, GRUPO_FISIOTERAPEUTA)
GRUPOS_EXERCICIOS_EDITAR = (GRUPO_ADMINISTRADOR, GRUPO_FISIOTERAPEUTA)
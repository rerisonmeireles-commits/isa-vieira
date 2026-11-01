-- ============================================================
-- Configuração de roles do PostgreSQL
-- Sistema de Gestão para Clínica de Fisioterapia
--
-- Executar como superuser 'postgres', conectado ao banco db_fisio:
--
--   psql -U postgres -d db_fisio ^
--        -v owner_password="SENHA_OWNER" ^
--        -v app_password="SENHA_APP" ^
--        -f scripts/roles_postgres.sql
--
-- As senhas NUNCA ficam neste arquivo. Elas vêm da linha de comando
-- e não são registradas no histórico do Git.
-- ============================================================

\set ON_ERROR_STOP on

-- ------------------------------------------------------------
-- PASSO 1 — Criar as roles
-- ------------------------------------------------------------
-- fisio_owner: dono do schema, roda migrações, tem DDL
-- fisio_app:   runtime da aplicação, só DML
--
-- CREATEDB no fisio_app é exigência do runner de testes do Django:
-- a criação do banco de teste usa as credenciais do alias 'default'.
-- Revogar em produção com: ALTER ROLE fisio_app NOCREATEDB;

CREATE ROLE fisio_owner LOGIN PASSWORD :'owner_password';
CREATE ROLE fisio_app   LOGIN PASSWORD :'app_password';

ALTER ROLE fisio_owner CREATEDB;
ALTER ROLE fisio_app   CREATEDB;

GRANT CONNECT ON DATABASE db_fisio TO fisio_owner;
GRANT CONNECT ON DATABASE db_fisio TO fisio_app;

-- ------------------------------------------------------------
-- PASSO 2 — Owner assume o schema public
-- ------------------------------------------------------------
ALTER SCHEMA public OWNER TO fisio_owner;
GRANT ALL ON SCHEMA public TO fisio_owner;

-- App usa o schema, mas NÃO cria objetos nele
GRANT USAGE ON SCHEMA public TO fisio_app;
REVOKE CREATE ON SCHEMA public FROM fisio_app;

-- ------------------------------------------------------------
-- PASSO 3 — Transferir propriedade das tabelas e sequências
-- ------------------------------------------------------------
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    LOOP
        EXECUTE format('ALTER TABLE public.%I OWNER TO fisio_owner', r.tablename);
    END LOOP;

    FOR r IN SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'
    LOOP
        EXECUTE format('ALTER SEQUENCE public.%I OWNER TO fisio_owner', r.sequencename);
    END LOOP;
END $$;

-- ------------------------------------------------------------
-- PASSO 4 — Conceder DML ao fisio_app
-- ------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO fisio_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO fisio_app;

-- O app não pode alterar privilégios (evita escalada)
REVOKE GRANT OPTION FOR ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM fisio_app;

-- ------------------------------------------------------------
-- PASSO 5 — ALTER DEFAULT PRIVILEGES (tabelas futuras)
-- ------------------------------------------------------------
-- Sem isso, toda tabela criada numa migração futura nasce
-- inacessível ao fisio_app — e o erro é 'permission denied'
-- sem causa aparente.
ALTER DEFAULT PRIVILEGES FOR ROLE fisio_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO fisio_app;

ALTER DEFAULT PRIVILEGES FOR ROLE fisio_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO fisio_app;

-- ------------------------------------------------------------
-- PASSO 6 — Log de auditoria: só leitura e inserção
-- ------------------------------------------------------------
-- Agora o REVOKE funciona de verdade: o fisio_app NÃO é o dono
-- da tabela, então o privilégio é realmente removido.
-- Esta é a segunda camada de proteção, complementar ao trigger
-- trg_audit_log_imutavel criado na migração 0002.
REVOKE UPDATE, DELETE ON audit_logauditoria FROM fisio_app;

-- ------------------------------------------------------------
-- PASSO 7 — Verificação
-- ------------------------------------------------------------
\echo ''
\echo '=== Verificação final ==='
SELECT rolname, rolcreatedb, rolcreaterole, rolsuper
FROM pg_roles WHERE rolname LIKE 'fisio%' ORDER BY rolname;

SELECT grantee, privilege_type
FROM information_schema.role_table_grants
WHERE table_name = 'audit_logauditoria' AND grantee LIKE 'fisio%'
ORDER BY grantee, privilege_type;
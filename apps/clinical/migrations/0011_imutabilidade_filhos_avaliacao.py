from django.db import migrations


def tornar_filhos_imutaveis(apps, schema_editor):
    """Bloqueia INSERT/UPDATE/DELETE em FimItem e GoniometriaMedicao
    quando a Avaliacao pai está liberada.

    Abordagem A: bloqueio puro, sem sincronizar fim_total no banco.
    O fim_total continua sendo property calculada em Python enquanto
    o pai está pendente; uma vez liberado, ninguém altera os itens.

    O SELECT usa FOR SHARE para evitar deadlock com transações que
    atualizam a Avaliacao concorrentemente.

    NOTA: o '%%' no RAISE EXCEPTION é obrigatório. O schema_editor.execute()
    passa o SQL pelo mogrify do psycopg, que interpreta '%' como marcador
    de parâmetro. Duplicar faz o psycopg entregar '%' ao PostgreSQL.
    """
    FimItem = apps.get_model("clinical", "FimItem")
    Goniometria = apps.get_model("clinical", "GoniometriaMedicao")
    Avaliacao = apps.get_model("clinical", "Avaliacao")

    tabela_fim = FimItem._meta.db_table
    tabela_gonio = Goniometria._meta.db_table
    tabela_aval = Avaliacao._meta.db_table

    # Função compartilhada: recebe o avaliacao_id e bloqueia se liberada.
    schema_editor.execute(f"""
        CREATE OR REPLACE FUNCTION fn_avaliacao_pai_liberada(p_avaliacao_id BIGINT)
        RETURNS BOOLEAN AS $$
        DECLARE
            v_liberado_em TIMESTAMPTZ;
        BEGIN
            SELECT liberado_em INTO v_liberado_em
            FROM {tabela_aval}
            WHERE id = p_avaliacao_id
            FOR SHARE;

            RETURN v_liberado_em IS NOT NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Trigger para FimItem
    schema_editor.execute(f"""
        CREATE OR REPLACE FUNCTION fn_fimitem_imutavel()
        RETURNS TRIGGER AS $$
        DECLARE
            v_avaliacao_id BIGINT;
        BEGIN
            -- Em DELETE, usa OLD; em INSERT/UPDATE, usa NEW.
            IF TG_OP = 'DELETE' THEN
                v_avaliacao_id := OLD.avaliacao_id;
            ELSE
                v_avaliacao_id := NEW.avaliacao_id;
            END IF;

            IF fn_avaliacao_pai_liberada(v_avaliacao_id) THEN
                RAISE EXCEPTION
                    'FimItem da Avaliacao %% está bloqueado: avaliação liberada.',
                    v_avaliacao_id
                    USING ERRCODE = 'check_violation';
            END IF;

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_fimitem_imutavel
        BEFORE INSERT OR UPDATE OR DELETE ON {tabela_fim}
        FOR EACH ROW EXECUTE FUNCTION fn_fimitem_imutavel();
    """)

    # Trigger para GoniometriaMedicao
    schema_editor.execute(f"""
        CREATE OR REPLACE FUNCTION fn_goniometria_imutavel()
        RETURNS TRIGGER AS $$
        DECLARE
            v_avaliacao_id BIGINT;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                v_avaliacao_id := OLD.avaliacao_id;
            ELSE
                v_avaliacao_id := NEW.avaliacao_id;
            END IF;

            IF fn_avaliacao_pai_liberada(v_avaliacao_id) THEN
                RAISE EXCEPTION
                    'GoniometriaMedicao da Avaliacao %% está bloqueada: avaliação liberada.',
                    v_avaliacao_id
                    USING ERRCODE = 'check_violation';
            END IF;

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_goniometria_imutavel
        BEFORE INSERT OR UPDATE OR DELETE ON {tabela_gonio}
        FOR EACH ROW EXECUTE FUNCTION fn_goniometria_imutavel();
    """)


def reverter_imutabilidade(apps, schema_editor):
    FimItem = apps.get_model("clinical", "FimItem")
    Goniometria = apps.get_model("clinical", "GoniometriaMedicao")

    schema_editor.execute(f"""
        DROP TRIGGER IF EXISTS trg_fimitem_imutavel ON {FimItem._meta.db_table};
        DROP FUNCTION IF EXISTS fn_fimitem_imutavel();

        DROP TRIGGER IF EXISTS trg_goniometria_imutavel ON {Goniometria._meta.db_table};
        DROP FUNCTION IF EXISTS fn_goniometria_imutavel();

        DROP FUNCTION IF EXISTS fn_avaliacao_pai_liberada(BIGINT);
    """)


class Migration(migrations.Migration):
    dependencies = [
        ("clinical", "0010_imutabilidade_avaliacao"),
    ]

    operations = [
        migrations.RunPython(tornar_filhos_imutaveis, reverter_imutabilidade),
    ]
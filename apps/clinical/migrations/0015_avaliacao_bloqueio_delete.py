from django.db import migrations


def recriar_trigger_avaliacao_com_delete(apps, schema_editor):
    """Recria o trigger da Avaliacao incluindo DELETE.

    A 0010 aplicou a versão que só interceptava UPDATE. Como o Django já
    a marca como aplicada, esta migração recria a função e o trigger com
    BEFORE UPDATE OR DELETE, preservando integralmente a lógica de UPDATE
    (bloqueio de alteração em liberada + transição L -> I permitida).

    Regra de DELETE: bloqueia se liberado_em NOT NULL, permite se rascunho.
    Mesma decisão de negócio adotada na Evolucao (0014).

    Idempotente: DROP TRIGGER IF EXISTS + CREATE OR REPLACE FUNCTION
    permitem rodar em bancos onde a 0010 já está na versão correta.

    NOTA: o '%%' no RAISE EXCEPTION é obrigatório — o schema_editor.execute()
    passa o SQL pelo mogrify do psycopg, que interpreta '%' como marcador
    de parâmetro. Duplicar faz o psycopg entregar '%' ao PostgreSQL, onde
    ele volta a ser o placeholder do format() do RAISE.
    """
    Avaliacao = apps.get_model("clinical", "Avaliacao")
    tabela = Avaliacao._meta.db_table

    schema_editor.execute(f"""
        CREATE OR REPLACE FUNCTION fn_avaliacao_imutavel()
        RETURNS TRIGGER AS $$
        BEGIN
            -- DELETE: bloqueia se liberada, permite se rascunho.
            IF TG_OP = 'DELETE' THEN
                IF OLD.liberado_em IS NOT NULL THEN
                    RAISE EXCEPTION
                        'Avaliacao %% está liberada e não pode ser excluída. '
                        'Use o fluxo de inativação.',
                        OLD.id
                        USING ERRCODE = 'check_violation';
                END IF;
                RETURN OLD;
            END IF;

            -- UPDATE em rascunho: livre (edição ou liberação).
            IF OLD.liberado_em IS NULL THEN
                RETURN NEW;
            END IF;

            -- Transição permitida: L -> I, com rastreio completo.
            IF NEW.status = 'I'
               AND OLD.status = 'L'
               AND NEW.inativado_por_id IS NOT NULL
               AND NEW.inativado_em IS NOT NULL
            THEN
                RETURN NEW;
            END IF;

            -- Qualquer outra alteração em registro liberado é bloqueada.
            RAISE EXCEPTION
                'Avaliacao %% está liberada e não pode ser alterada. '
                'Use o fluxo de inativação ou registre uma retificação.',
                OLD.id
                USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_avaliacao_imutavel ON {tabela};

        CREATE TRIGGER trg_avaliacao_imutavel
        BEFORE UPDATE OR DELETE ON {tabela}
        FOR EACH ROW EXECUTE FUNCTION fn_avaliacao_imutavel();
    """)


def reverter(apps, schema_editor):
    """Volta à versão só-UPDATE da 0010."""
    Avaliacao = apps.get_model("clinical", "Avaliacao")
    tabela = Avaliacao._meta.db_table

    schema_editor.execute(f"""
        DROP TRIGGER IF EXISTS trg_avaliacao_imutavel ON {tabela};
        CREATE TRIGGER trg_avaliacao_imutavel
        BEFORE UPDATE ON {tabela}
        FOR EACH ROW EXECUTE FUNCTION fn_avaliacao_imutavel();
    """)


class Migration(migrations.Migration):
    dependencies = [
        ("clinical", "0014_evolucao_bloqueio_delete"),
    ]

    operations = [
        migrations.RunPython(recriar_trigger_avaliacao_com_delete, reverter),
    ]
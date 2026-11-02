from django.db import migrations


def recriar_trigger_com_delete(apps, schema_editor):
    """Recria o trigger da Evolucao incluindo DELETE.

    A 0013 foi aplicada com a versão que só interceptava UPDATE. Como o
    Django já a marca como aplicada, esta migração corretiva recria a
    função e o trigger com BEFORE UPDATE OR DELETE.

    Idempotente: DROP TRIGGER IF EXISTS + CREATE OR REPLACE FUNCTION
    permitem rodar em bancos onde a 0013 já está na versão correta.

    NOTA: o '%%' no RAISE EXCEPTION é obrigatório — o schema_editor.execute()
    passa o SQL pelo mogrify do psycopg, que interpreta '%' como marcador
    de parâmetro.
    """
    Evolucao = apps.get_model("clinical", "Evolucao")
    tabela = Evolucao._meta.db_table

    schema_editor.execute(f"""
        CREATE OR REPLACE FUNCTION fn_evolucao_imutavel()
        RETURNS TRIGGER AS $$
        BEGIN
            -- DELETE: bloqueia se liberada, permite se rascunho.
            IF TG_OP = 'DELETE' THEN
                IF OLD.liberado_em IS NOT NULL THEN
                    RAISE EXCEPTION
                        'Evolucao %% está liberada e não pode ser excluída. '
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
                'Evolucao %% está liberada e não pode ser alterada. '
                'Registre uma retificação ou inative o registro.',
                OLD.id
                USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_evolucao_imutavel ON {tabela};

        CREATE TRIGGER trg_evolucao_imutavel
        BEFORE UPDATE OR DELETE ON {tabela}
        FOR EACH ROW EXECUTE FUNCTION fn_evolucao_imutavel();
    """)


def reverter(apps, schema_editor):
    """Volta à versão só-UPDATE da 0013."""
    Evolucao = apps.get_model("clinical", "Evolucao")
    tabela = Evolucao._meta.db_table

    schema_editor.execute(f"""
        DROP TRIGGER IF EXISTS trg_evolucao_imutavel ON {tabela};
        CREATE TRIGGER trg_evolucao_imutavel
        BEFORE UPDATE ON {tabela}
        FOR EACH ROW EXECUTE FUNCTION fn_evolucao_imutavel();
    """)


class Migration(migrations.Migration):
    dependencies = [
        ("clinical", "0013_imutabilidade_evolucao"),
    ]

    operations = [
        migrations.RunPython(recriar_trigger_com_delete, reverter),
    ]
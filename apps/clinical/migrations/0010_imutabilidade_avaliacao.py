from django.db import migrations


def tornar_avaliacao_imutavel(apps, schema_editor):
    """Bloqueia UPDATE em Avaliacao liberada, exceto a transição L -> I.

    Deriva o nome da tabela via _meta.db_table em vez de hardcodar: se o
    Meta do modelo mudar, a migração continua correta.

    Regra:
      - Se liberado_em era NULL antes do UPDATE, o UPDATE é a própria
        liberação (ou edição de registro pendente) e passa.
      - Se liberado_em já estava preenchido, só a transição L -> I é
        permitida, exigindo inativado_por e inativado_em preenchidos.
      - Qualquer outra alteração em registro liberado é bloqueada.

    Complementa a CheckConstraint ck_avaliacao_liberada_com_rastreio,
    que valida o estado final da linha. O trigger valida a TRANSIÇÃO,
    que a constraint não consegue enxergar.

    IMPORTANTE: o RAISE EXCEPTION usa %% (escape do psycopg via
    schema_editor.execute). Um % solto levanta
    psycopg.ProgrammingError: incomplete placeholder.
    """
    Avaliacao = apps.get_model("clinical", "Avaliacao")
    tabela = Avaliacao._meta.db_table

    schema_editor.execute("""
        CREATE OR REPLACE FUNCTION fn_avaliacao_imutavel()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.liberado_em IS NULL THEN
                RETURN NEW;
            END IF;

            IF NEW.status = 'I'
               AND OLD.status = 'L'
               AND NEW.inativado_por_id IS NOT NULL
               AND NEW.inativado_em IS NOT NULL
            THEN
                RETURN NEW;
            END IF;

            RAISE EXCEPTION
                'Avaliacao %% está liberada e não pode ser alterada. '
                'Use o fluxo de inativação ou registre uma retificação.',
                OLD.id
                USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql;
    """)


def reverter_imutabilidade(apps, schema_editor):
    Avaliacao = apps.get_model("clinical", "Avaliacao")
    tabela = Avaliacao._meta.db_table

    schema_editor.execute(f"""
        DROP TRIGGER IF EXISTS trg_avaliacao_imutavel ON {tabela};
        DROP FUNCTION IF EXISTS fn_avaliacao_imutavel();
    """)


class Migration(migrations.Migration):
    dependencies = [
        ("clinical", "0009_remove_avaliacao_ck_avaliacao_fim_and_more"),
    ]

    operations = [
        migrations.RunPython(tornar_avaliacao_imutavel, reverter_imutabilidade),
    ]
from django.db import migrations


def tornar_evolucao_imutavel(apps, schema_editor):
    """Bloqueia UPDATE em Evolucao liberada, exceto a transição L -> I.

    Espelha a lógica da 0010 (Avaliacao), com uma diferença: a Evolucao
    é o registro diário do ato clínico, então o bloqueio cobre também
    os campos SOAP individualmente — não só o registro como um todo.

    Regra:
      - Se liberado_em era NULL antes do UPDATE, o UPDATE é a própria
        liberação (ou edição de rascunho) e passa.
      - Se liberado_em já estava preenchido, só a transição L -> I é
        permitida, exigindo inativado_por e inativado_em preenchidos.
      - Qualquer outra alteração em registro liberado é bloqueada.

    NOTA: o '%%' no RAISE EXCEPTION é obrigatório. O schema_editor.execute()
    passa o SQL pelo mogrify do psycopg, que interpreta '%' como marcador
    de parâmetro. Duplicar faz o psycopg entregar '%' ao PostgreSQL.
    """
    Evolucao = apps.get_model("clinical", "Evolucao")
    tabela = Evolucao._meta.db_table

    schema_editor.execute(f"""
        CREATE OR REPLACE FUNCTION fn_evolucao_imutavel()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Registro ainda não liberado: UPDATE livre (edição ou liberação).
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

        CREATE TRIGGER trg_evolucao_imutavel
        BEFORE UPDATE ON {tabela}
        FOR EACH ROW EXECUTE FUNCTION fn_evolucao_imutavel();
    """)


def reverter_imutabilidade(apps, schema_editor):
    Evolucao = apps.get_model("clinical", "Evolucao")
    tabela = Evolucao._meta.db_table

    schema_editor.execute(f"""
        DROP TRIGGER IF EXISTS trg_evolucao_imutavel ON {tabela};
        DROP FUNCTION IF EXISTS fn_evolucao_imutavel();
    """)


class Migration(migrations.Migration):
    dependencies = [
        ("clinical", "0012_evolucao_ciclo_de_vida"),
    ]

    operations = [
        migrations.RunPython(tornar_evolucao_imutavel, reverter_imutabilidade),
    ]
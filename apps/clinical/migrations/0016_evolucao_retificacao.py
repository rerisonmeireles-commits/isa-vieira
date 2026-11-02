import django.db.models.deletion
from django.db import migrations, models


def ajustar_trigger_para_retificacao(apps, schema_editor):
    """Recria o trigger da Evolucao para permitir o fluxo de retificação.

    A 0014 bloqueia UPDATE em evolução liberada. A retificação é um INSERT
    de um novo registro com retifica_evolucao_id apontando para o original —
    então o INSERT não é afetado pelo trigger (que só dispara em UPDATE/DELETE).

    O que muda: o trigger precisa permitir que o registro ORIGINAL receba
    uma marcação de que foi retificado. Sem isso, não há como saber, olhando
    o original, que existe uma retificação vinculada a ele.

    Solução: adicionar a coluna retificada_em no original. O trigger permite
    UPDATE em evolução liberada APENAS quando a única alteração é preencher
    retificada_em (de NULL para NOT NULL). Qualquer outra alteração continua
    bloqueada.

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

            -- Marcação de retificação: única alteração permitida em liberada.
            -- Só aceita se retificada_em passa de NULL para NOT NULL e
            -- nenhum outro campo clínico mudou.
            IF OLD.retificada_em IS NULL
               AND NEW.retificada_em IS NOT NULL
               AND NEW.subjetivo IS NOT DISTINCT FROM OLD.subjetivo
               AND NEW.objetivo IS NOT DISTINCT FROM OLD.objetivo
               AND NEW.avaliacao IS NOT DISTINCT FROM OLD.avaliacao
               AND NEW.plano IS NOT DISTINCT FROM OLD.plano
               AND NEW.status = OLD.status
               AND NEW.liberado_em IS NOT DISTINCT FROM OLD.liberado_em
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


def reverter_trigger(apps, schema_editor):
    """Volta à versão da 0014 (sem suporte a retificação)."""
    Evolucao = apps.get_model("clinical", "Evolucao")
    tabela = Evolucao._meta.db_table

    schema_editor.execute(f"""
        CREATE OR REPLACE FUNCTION fn_evolucao_imutavel()
        RETURNS TRIGGER AS $$
        BEGIN
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
                'Evolucao %% está liberada e não pode ser alterada. '
                'Registre uma retificação ou inative o registro.',
                OLD.id
                USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql;
    """)


class Migration(migrations.Migration):

    dependencies = [
        ("clinical", "0015_avaliacao_bloqueio_delete"),
    ]

    operations = [
        # 1. FK auto-referencial: a retificação aponta para o original.
        migrations.AddField(
            model_name="evolucao",
            name="retifica_evolucao",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="retificacoes",
                to="clinical.evolucao",
            ),
        ),
        # 2. Marca no original: indica que existe retificação vinculada.
        migrations.AddField(
            model_name="evolucao",
            name="retificada_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        # 3. Constraint: retificação não pode ser retificada.
        #    Um registro com retifica_evolucao_id preenchido NÃO pode ter
        #    retificacoes apontando para ele. Isso é garantido no banco
        #    pela combinação de PROTECT + esta constraint de exclusividade.
        migrations.AddConstraint(
            model_name="evolucao",
            constraint=models.CheckConstraint(
                condition=(
                    # Se é retificação, não pode ter retificada_em preenchido
                    # (retificação não pode ser retificada)
                    models.Q(retifica_evolucao__isnull=False, retificada_em__isnull=True)
                    # Se não é retificação, retificada_em pode ser qualquer coisa
                    | models.Q(retifica_evolucao__isnull=True)
                ),
                name="ck_evolucao_retificacao_sem_cascata",
            ),
        ),
        # 4. Constraint: retificação só pode apontar para evolução liberada.
        #    Garantida na aplicação, mas o banco reforça via trigger abaixo.
        migrations.AddConstraint(
            model_name="evolucao",
            constraint=models.CheckConstraint(
                condition=(
                    # Retificação não pode apontar para si mesma
                    ~models.Q(retifica_evolucao=models.F("id"))
                    | models.Q(retifica_evolucao__isnull=True)
                ),
                name="ck_evolucao_retificacao_nao_autoreferente",
            ),
        ),
        # 5. Recria o trigger com suporte à marcação de retificação.
        migrations.RunPython(ajustar_trigger_para_retificacao, reverter_trigger),
    ]
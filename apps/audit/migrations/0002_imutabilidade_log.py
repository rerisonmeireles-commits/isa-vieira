from django.db import migrations


def tornar_log_imutavel(apps, schema_editor):
    """Aplica REVOKE + trigger usando o nome real da tabela.

    Deriva o nome via _meta.db_table em vez de hardcodar: se o Meta do
    modelo mudar, a migração continua correta.
    """
    LogAuditoria = apps.get_model("audit", "LogAuditoria")
    tabela = LogAuditoria._meta.db_table

    schema_editor.execute(f"""
        REVOKE UPDATE, DELETE ON audit_logauditoria FROM CURRENT_USER;

        CREATE OR REPLACE FUNCTION audit_log_imutavel()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_log_auditoria é imutável: UPDATE e DELETE bloqueados';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_audit_log_imutavel
        BEFORE UPDATE OR DELETE ON audit_logauditoria
        FOR EACH ROW EXECUTE FUNCTION audit_log_imutavel();
    """)


def reverter_imutabilidade(apps, schema_editor):
    LogAuditoria = apps.get_model("audit", "LogAuditoria")
    tabela = LogAuditoria._meta.db_table

    schema_editor.execute(f"""
        DROP TRIGGER IF EXISTS trg_audit_log_imutavel ON audit_logauditoria;
        DROP FUNCTION IF EXISTS audit_log_imutavel();
        GRANT UPDATE, DELETE ON audit_logauditoria TO CURRENT_USER;
    """)


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(tornar_log_imutavel, reverter_imutabilidade),
    ]
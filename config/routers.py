class TestDatabaseRouter:
    """Impede que o alias 'migrations' seja usado em testes.

    O Django cria dois bancos de teste quando há dois aliases — um para
    'default' e outro para 'migrations'. Como o 'migrations' aponta para
    o fisio_owner, ele tenta criar um segundo banco e falha. Este router
    força o uso do 'default' em testes.
    """

    def db_for_read(self, model, **hints):
        return None

    def db_for_write(self, model, **hints):
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Em testes, só o 'default' é migrado
        import sys
        if "test" in sys.argv:
            return db == "default"
        return None
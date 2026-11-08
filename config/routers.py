class TestDatabaseRouter:
    """Em testes, tudo vai para o alias 'default'.

    O TestCase do Django só gerencia transações no 'default'. Se o router
    devolver 'migrations' durante os testes, a conexão desse alias é
    fechada entre testes e o seguinte falha com
    OperationalError: the connection is closed.
    """

    def _is_testing(self):
        import sys
        return "test" in sys.argv

    def db_for_read(self, model, **hints):
        if self._is_testing():
            return "default"
        return None

    def db_for_write(self, model, **hints):
        if self._is_testing():
            return "default"
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if self._is_testing():
            return db == "default"
        return None
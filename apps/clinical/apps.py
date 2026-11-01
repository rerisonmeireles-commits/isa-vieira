from django.apps import AppConfig


class ClinicalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = "apps.clinical"

    def ready(self):
        # Importa os signals para registrá-los (post_save do Paciente → Prontuário)
        from apps.clinical import signals  # noqa: F401    
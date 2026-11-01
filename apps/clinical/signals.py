from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.patients.models import Paciente
from apps.clinical.models import Prontuario


@receiver(post_save, sender=Paciente)
def criar_prontuario_automatico(sender, instance, created, **kwargs):
    if created:
        Prontuario.objects.get_or_create(paciente=instance)
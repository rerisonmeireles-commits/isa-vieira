# smoke_limpeza.py — limpeza segura dos dados SMOKE (respeita ON DELETE PROTECT)
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.exercise.models import (
    ExecucaoExercicio, Exercicio, Prescricao, PrescricaoExercicio,
)

# 1. Execuções (referenciam os itens — devem sair primeiro)
n1 = ExecucaoExercicio.objects.filter(
    prescricao_exercicio__prescricao__objetivo__startswith="SMOKE"
).delete()
# 2. Itens de prescrição
n2 = PrescricaoExercicio.objects.filter(
    exercicio__nome__startswith="SMOKE"
).delete()
# 3. Prescrições
n3 = Prescricao.objects.filter(objetivo__startswith="SMOKE").delete()
# 4. Exercícios do catálogo
n4 = Exercicio.objects.filter(nome__startswith="SMOKE").delete()

print(f"Execuções: {n1[0]} | Itens: {n2[0]} | Prescrições: {n3[0]} | Exercícios: {n4[0]}")
print("Limpeza concluída.")
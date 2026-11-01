from apps.clinical.models import GoniometriaMedicao
from collections import defaultdict

grupos = defaultdict(list)
for m in GoniometriaMedicao.objects.select_related('avaliacao').order_by('avaliacao__data'):
    chave = f"{m.get_articulacao_display()} · {m.get_movimento_display()} · {m.get_lado_display()}"
    grupos[chave].append((m.avaliacao.data, m.graus))

for chave, pontos in grupos.items():
    print(chave, '->', pontos)

print('Total de séries:', len(grupos))
print('Total de medições:', GoniometriaMedicao.objects.count())

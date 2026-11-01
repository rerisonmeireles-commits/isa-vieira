"""Rotas do módulo Financeiro. Usa o id sequencial - os modelos não possuem uuid."""
from django.urls import path
from apps.financial import views

app_name = "financial"

urlpatterns = [
    path("", views.listar_contas, name="listar_contas"),
    path("conta/nova/", views.criar_conta, name="criar_conta"),
    path("conta/<int:pk>/", views.ficha_conta, name="ficha_conta"),
    path("conta/<int:pk>/pagamento/", views.baixa_pagamento, name="baixa_pagamento"),
    path("conta/<int:pk>/reparcelar/", views.reparcelar_conta_view, name="reparcelar_conta"),
    
    path("faturamentos/", views.listar_faturamentos, name="listar_faturamentos"),
    path("faturamentos/novo/", views.criar_faturamento, name="criar_faturamento"),
    path("faturamentos/preview/", views.preview_lote, name="preview_lote"),
    path("faturamentos/<int:pk>/", views.ficha_faturamento, name="ficha_faturamento"),

    path("pagamento/<int:pk>/confirmar/", views.confirmar_pagamento_view, name="confirmar_pagamento"),
    path("pagamento/<int:pk>/editar/", views.editar_pagamento_view, name="editar_pagamento"),
    path("pagamentos/<int:pk>/estornar/", views.estornar_pagamento_view, name="estornar_pagamento"),
]
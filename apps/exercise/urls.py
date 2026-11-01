from django.urls import path

from apps.exercise import views

app_name = "exercise"

urlpatterns = [
    # Catálogo
    path("exercicios/", views.lista_exercicios, name="lista_exercicios"),
    path("exercicios/novo/", views.form_exercicio, name="novo_exercicio"),
    path("exercicios/<int:pk>/editar/", views.form_exercicio,
         name="editar_exercicio"),
    path("exercicios/<int:pk>/inativar/", views.inativar_exercicio,
         name="inativar_exercicio"),

    # Prescrições
    path("prescricoes/", views.lista_prescricoes, name="lista_prescricoes"),
    path("prescricoes/nova/", views.form_prescricao, name="nova_prescricao"),
    path("prescricoes/<int:pk>/", views.detalhe_prescricao,
         name="detalhe_prescricao"),
    path("prescricoes/<int:pk>/editar/", views.form_prescricao,
         name="editar_prescricao"),
    path("prescricoes/<int:pk>/encerrar/", views.encerrar_prescricao,
         name="encerrar_prescricao"),
    path("prescricoes/<int:pk>/cancelar/", views.cancelar_prescricao,
         name="cancelar_prescricao"),
    path("prescricoes/<int:pk>/reordenar/", views.reordenar_itens,
         name="reordenar_itens"),

    # Execução
    path("itens/<int:item_pk>/execucao/", views.registrar_execucao,
         name="registrar_execucao"),
]
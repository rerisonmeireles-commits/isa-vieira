"""Rotas do módulo Clinic (Estrutura). Usa o id sequencial."""

from django.urls import path

from apps.clinic import views

app_name = "clinica"

urlpatterns = [
    path("", views.dados_clinica, name="dados_clinica"),
    path("salas/", views.listar_salas, name="listar_salas"),
    path("salas/nova/", views.criar_sala, name="criar_sala"),
    path("salas/<int:pk>/editar/", views.editar_sala, name="editar_sala"),
    path("tipos/", views.listar_tipos, name="listar_tipos"),
    path("tipos/novo/", views.criar_tipo, name="criar_tipo"),
    path("tipos/<int:pk>/editar/", views.editar_tipo, name="editar_tipo"),
    path("tipos/<int:pk>/ativo/", views.alternar_tipo_ativo_view, name="alternar_tipo_ativo"),
]
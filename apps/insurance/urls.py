"""Rotas do módulo de Convênios. Usa o id sequencial - o modelo não possui uuid."""

from django.urls import path

from apps.insurance import views

app_name = "insurance"

urlpatterns = [
    path("", views.listar, name="listar"),
    path("novo/", views.criar, name="criar"),
    path("<int:pk>/", views.ficha, name="ficha"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/ativo/", views.alternar_ativo_view, name="alternar_ativo"),
]
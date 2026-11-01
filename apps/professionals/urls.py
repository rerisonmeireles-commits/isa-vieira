"""Rotas do módulo de Profissionais. Usa o id sequencial - o modelo não possui uuid."""

from django.urls import path

from apps.professionals import views

app_name = "professionals"

urlpatterns = [
    path("", views.listar, name="listar"),
    path("novo/", views.criar, name="criar"),
    path("<int:pk>/", views.ficha, name="ficha"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/status/", views.alternar_status_view, name="alternar_status"),
]
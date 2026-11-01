"""Rotas do módulo de Pacientes. O identificador público é o uuid (anti-IDOR)."""

from django.urls import path

from apps.patients import views

app_name = "patients"

urlpatterns = [
    path("", views.listar, name="listar"),
    path("novo/", views.criar, name="criar"),
    path("<uuid:uuid>/", views.ficha, name="ficha"),
    path("<uuid:uuid>/editar/", views.editar, name="editar"),
    path("<uuid:uuid>/status/", views.alternar_status_view, name="alternar_status"),
    path("<uuid:uuid>/convenio/novo/", views.vincular_convenio, name="vincular_convenio"),
    path("<uuid:uuid>/convenio/<int:vinculo_id>/editar/", views.editar_convenio, name="editar_convenio"),
    path("<uuid:uuid>/convenio/<int:vinculo_id>/remover/", views.remover_convenio, name="remover_convenio"),
]
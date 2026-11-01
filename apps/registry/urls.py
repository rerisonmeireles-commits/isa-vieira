"""Rotas do módulo Registry (cadastros básicos). Usa o id sequencial."""

from django.urls import path

from apps.registry import views

app_name = "registry"

urlpatterns = [
    path("especialidades/", views.listar_especialidades, name="listar_especialidades"),
    path("especialidades/nova/", views.criar_especialidade, name="criar_especialidade"),
    path("especialidades/<int:pk>/editar/", views.editar_especialidade, name="editar_especialidade"),
    path("especialidades/<int:pk>/ativa/", views.alternar_ativa, name="alternar_ativa"),
    path("conselhos/", views.listar_conselhos, name="listar_conselhos"),
    path("conselhos/novo/", views.criar_conselho, name="criar_conselho"),
    path("conselhos/<int:pk>/editar/", views.editar_conselho, name="editar_conselho"),
    path("feriados/", views.listar_feriados, name="listar_feriados"),
    path("feriados/novo/", views.criar_feriado, name="criar_feriado"),
    path("feriados/<int:pk>/editar/", views.editar_feriado, name="editar_feriado"),
    path("feriados/<int:pk>/excluir/", views.excluir_feriado, name="excluir_feriado"),
]
from django.urls import path

from apps.documents import views

app_name = "documents"

urlpatterns = [
    path("", views.documento_lista, name="documento_lista"),
    path("novo/", views.documento_criar, name="documento_criar"),
    path("<int:pk>/editar/", views.documento_editar, name="documento_editar"),
    path("<int:pk>/excluir/", views.documento_excluir, name="documento_excluir"),
    path("<uuid:uuid>/baixar/", views.documento_download, name="documento_download"),
]
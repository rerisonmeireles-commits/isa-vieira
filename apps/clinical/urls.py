from django.urls import path

from apps.clinical import views

app_name = "clinical"

urlpatterns = [
    path("prontuario/<int:paciente_id>/", views.detalhe_prontuario,
         name="detalhe_prontuario"),
    path("prontuario/<int:paciente_id>/avaliacao/nova/", views.criar_avaliacao,
         name="criar_avaliacao"),
    path("avaliacao/<int:pk>/liberar/", views.liberar_avaliacao,
         name="liberar_avaliacao"),
    path("avaliacao/<int:pk>/inativar/", views.inativar_avaliacao,
         name="inativar_avaliacao"),
    path("avaliacao/<int:pk>/editar/", views.editar_avaliacao,
         name="editar_avaliacao"),         
    path("avaliacao/<int:pk>/", views.detalhe_avaliacao,
         name="detalhe_avaliacao"),         
    path("evolucao/<int:pk>/editar/", views.editar_evolucao,
         name="editar_evolucao"),         
    path("prontuario/<int:paciente_id>/evolucao/nova/",
          views.nova_evolucao, name="nova_evolucao"),         
    path("prontuario/<int:paciente_id>/editar/", views.editar_prontuario,
         name="editar_prontuario"),         
    path("paciente/<int:paciente_id>/evolucao-goniometria/", views.evolucao_goniometria, 
         name="evolucao_goniometria"),


]
from django.urls import path

from apps.communication import views

app_name = "communication"

urlpatterns = [
    path("", views.central_notificacoes, name="central"),
    path("notificacao/<int:pk>/ler/", views.notificacao_marcar_lida, name="notificacao_ler"),
    path("mensagens/", views.inbox, name="inbox"),
    path("mensagens/nova/", views.mensagem_nova, name="mensagem_nova"),
    path("mensagens/<int:pk>/", views.mensagem_detalhe, name="mensagem_detalhe"),
    path("mensagens/<int:pk>/responder/", views.mensagem_responder, name="mensagem_responder"),    
]
from django.urls import path

from apps.portal import views

app_name = "portal"

urlpatterns = [
    path("", views.home, name="home"),
    path("consultas/", views.consultas, name="consultas"),
    path("consultas/<uuid:uuid>/", views.consulta_detalhe, name="consulta_detalhe"),    
    path("consultas/<uuid:uuid>/cancelar/",views.cancelar_consulta,name="cancelar_consulta"),

    path("documentos/", views.documentos, name="documentos"),
    path("documentos/<uuid:uuid>/download/", views.documento_download, name="documento_download"),
    path("evolucao/", views.evolucao, name="evolucao"),
    path("avaliacoes/", views.avaliacoes, name="avaliacoes"),
    path("avaliacoes/<uuid:uuid>/", views.avaliacao_detalhe, name="avaliacao_detalhe"),
    path("equipe/", views.equipe, name="equipe"),
    path("contato/", views.contato, name="contato"),
    path("perfil/", views.perfil, name="perfil"),

    path("agendar/", views.agendar, name="agendar"),
    path("agendamentos/", views.AgendamentosFuturosView.as_view(), name="agendamentos_futuros"),
    path("agendar/<int:tipo_id>/profissional/", views.agendar_profissional, name="agendar_profissional"),
    path("agendar/<int:tipo_id>/profissional/<int:profissional_id>/", views.agendar_horario, name="agendar_horario"),
    path("agendar/<int:tipo_id>/profissional/<int:profissional_id>/<str:data>/slots/", views.agendar_slots, name="agendar_slots"),
    path("agendar/confirmar/", views.agendar_confirmar, name="agendar_confirmar"),

    path("treinos/", views.treinos, name="treinos"),
    path("treinos/<uuid:uuid>/", views.treino_detalhe, name="treino_detalhe"),
    path("treinos/<uuid:uuid>/executar/<int:item_id>/",views.executar_exercicio,name="executar_exercicio"),    

    path("notificacoes/", views.em_breve, name="notificacoes"),
]
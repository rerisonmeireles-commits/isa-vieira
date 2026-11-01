from django.urls import path

from apps.scheduling import views

app_name = "scheduling"

urlpatterns = [
    path("agenda/", views.grade_semanal, name="grade"),
    path("agenda/gerar/<int:profissional_id>/", views.gerar_grade_view, name="gerar_grade"),
    path("agenda/slot/<int:slot_id>/reservar/", views.reservar_slot_view, name="reservar_slot"),
    path("agenda/agendamento/<int:agendamento_id>/cancelar/", views.cancelar_agendamento_view, name="cancelar_agendamento"),
    path("agenda/agendamento/<int:agendamento_id>/status/<str:novo_status>/", views.alterar_status_view, name="alterar_status"),
    path("agendamento/<int:agendamento_id>/iniciar/", views.iniciar_atendimento_view, name="iniciar_atendimento"),
    path("atendimento/<uuid:uuid>/finalizar/", views.finalizar_atendimento_view, name="finalizar_atendimento"),   
    path("atendimento/<uuid:uuid>/", views.ficha_atendimento, name="ficha_atendimento"),    
    path("atendimento/<uuid:uuid>/modal/", views.modal_atendimento, name="modal_atendimento"),    
    path("feriado/liberar/", views.liberar_feriado, name="liberar_feriado"),
    path("feriado/reverter/", views.reverter_liberacao, name="reverter_liberacao"),    
    path("agendamentos/<int:agendamento_id>/remarcar/", views.remarcar_agendamento_view, name="remarcar_agendamento"),    
]
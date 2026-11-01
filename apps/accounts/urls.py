from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path
from apps.accounts import views
from apps.accounts.views import pos_login

app_name = "conta"

urlpatterns = [
    path("", views.home, name="home"),
    path(
        "login/",
        LoginView.as_view(
            template_name="accounts/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("modulo/<slug:slug>/", views.em_breve, name="em_breve"),
    path("usuarios/", views.usuario_lista, name="usuario_lista"),
    path("usuarios/novo/", views.usuario_criar, name="usuario_criar"),
    path("usuarios/<int:pk>/editar/", views.usuario_editar, name="usuario_editar"),
    path("usuarios/<int:pk>/alternar-status/", views.usuario_alternar_status, name="usuario_alternar_status"),
    path("consentimentos/", views.consentimento_lista, name="consentimento_lista"),
    path("consentimentos/novo/", views.consentimento_criar, name="consentimento_criar"),
    path("consentimentos/<int:pk>/revogar/", views.consentimento_revogar, name="consentimento_revogar"),
    path("pos-login/", pos_login, name="pos_login"),        
]
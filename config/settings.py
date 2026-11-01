import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------
# Leitura do .env
# ------------------------------------------------------------
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")


def env_required(nome):
    """Lê variável obrigatória; falha na inicialização se ausente.

    Falhar cedo é melhor que rodar com credencial de fallback: um erro
    no startup é visível; uma conexão com senha do código-fonte não é.
    """
    valor = os.environ.get(nome)
    if not valor:
        raise RuntimeError(
            f"Variável de ambiente obrigatória ausente: {nome}. "
            f"Defina-a no .env antes de iniciar o projeto."
        )
    return valor


# ------------------------------------------------------------
# Segurança base
# ------------------------------------------------------------
SECRET_KEY = env_required("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_extensions",
    # Meus Apps do projeto
    "apps.accounts",
    "apps.clinic",
    "apps.registry",
    "apps.professionals",
    "apps.patients",
    "apps.insurance",
    "apps.scheduling",
    "apps.attendance",
    "apps.clinical",
    "apps.exercise",
    "apps.documents",
    "apps.financial",
    "apps.communication",
    "apps.audit",
    "apps.portal",
    # Histórico clínico
    "simple_history",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.csrf",
                "apps.accounts.context_processors.portal",
                "apps.accounts.context_processors.permissoes",
                "apps.clinic.context_processors.clinica_global",
                "apps.communication.context_processors.badge_notificacoes",
            ],
        },
    },
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

AUTH_USER_MODEL = "accounts.Usuario"

# ------------------------------------------------------------
# Banco de dados — PostgreSQL
# ------------------------------------------------------------
# Separar owner (migrações) de app_user (runtime) é o próximo passo:
# hoje o REVOKE do log de auditoria é decorativo porque o usuário do
# Django é o dono da tabela. Ver notas no fim do arquivo.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_required("DB_NAME"),
        "USER": env_required("DB_USER"),
        "PASSWORD": env_required("DB_PASSWORD"),
        "HOST": env_required("DB_HOST"),
        "PORT": env("DB_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "connect_timeout": 10,
        },
    }
}

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------
# E-mail
# ------------------------------------------------------------
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env("EMAIL_USE_TLS", default=True)

# ------------------------------------------------------------
# Autenticação e RBAC
# ------------------------------------------------------------
LOGIN_URL = "conta:login"
LOGIN_REDIRECT_URL = "conta:pos_login"
LOGOUT_REDIRECT_URL = "conta:login"

# ------------------------------------------------------------
# Mídia
# ------------------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ------------------------------------------------------------
# Segurança condicional — só vale fora de DEBUG
# ------------------------------------------------------------
# Em desenvolvimento (runserver + HTTP) essas flags quebram o login
# local. Em produção são obrigatórias. O bloco condicional evita
# ter dois settings.py divergentes.
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 ano — irreversível no cliente
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("conta/", include("apps.accounts.urls")),
    path("pacientes/", include("apps.patients.urls")),
    path("profissionais/", include("apps.professionals.urls")),
    path("convenios/", include("apps.insurance.urls")),
    path("", include("apps.scheduling.urls")),
    path("financeiro/", include("apps.financial.urls")),    
    path("cadastros/", include("apps.registry.urls")),
    path("clinica/", include("apps.clinic.urls")),    
    path("documentos/", include("apps.documents.urls")),     
    path("clinical/", include("apps.clinical.urls")),    
    path("exercicios/", include("apps.exercise.urls")),
    path("comunicacao/", include("apps.communication.urls")),
    path("portal/", include("apps.portal.urls")),        
]

# Serve os arquivos de mídia apenas em desenvolvimento.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
                   
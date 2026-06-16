"""Top-level URL configuration for ALT-Identity.

The project exposes two main route groups:

* ``/`` for the demo relying-party application in ``aot``
* ``/auth/`` for the identity provider endpoints in ``auth_server``
"""
from django.contrib import admin
from django.urls import path, include

from auth_server import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('.well-known/openid-configuration', auth_views.openid_configuration, name='openid_configuration'),
    path('.well-known/jwks.json', auth_views.jwks, name='jwks'),
    path('', include('aot.urls')),
    path('auth/', include('auth_server.urls')),
]

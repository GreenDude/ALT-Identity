"""Top-level URL configuration for ALT-Identity.

The project exposes two main route groups:

* ``/`` for the demo relying-party application in ``aot``
* ``/auth/`` for the identity provider endpoints in ``auth_server``
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('aot.urls')),
    path('auth/', include('auth_server.urls')),
]

"""URL routes for the demo relying-party application."""

from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('callback', views.aot_callback, name='aot_callback'),
    path('profile', views.aot_request_profile, name='aot_request_profile'),
    path('tokens', views.aot_token_viewer, name='aot_token_viewer'),
]

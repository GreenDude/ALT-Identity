"""URL routes for the local identity provider endpoints."""

from django.urls import path
from . import views

urlpatterns = [
    path('authorize', views.authorize, name='authorize'),
    path('token', views.token, name='token'),
    path('login', views.login_view, name='login'),
    path('register', views.register_view, name='register'),
    path('api/register', views.register_api, name='register_api'),
    path('logout', views.logout_view, name='logout'),
    path('userinfo', views.userinfo, name='userinfo'),
]

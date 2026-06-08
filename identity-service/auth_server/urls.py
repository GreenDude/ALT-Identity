from django.urls import path
from . import views

urlpatterns = [
    path('session', views.check_session_cookie, name='check_session_cookie'),
    path('authorize', views.authorize, name='authorize'),
    path('login', views.login, name='login'),
]
from django.urls import path
from . import views

urlpatterns = [
    path('authorize', views.authorize, name='authorize'),
    path('token', views.token, name='token'),
    path('login', views.login_view, name='login'),
    path('logout', views.logout_view, name='logout'),
    path('profile', views.request_profile_details, name='profile'),
]
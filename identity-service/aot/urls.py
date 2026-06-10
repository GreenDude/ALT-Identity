from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('callback', views.aot_callback, name='callback'),
]
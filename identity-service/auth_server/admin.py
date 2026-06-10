from django.contrib import admin

from .models import AuthCode, UserProfile

admin.site.register(AuthCode)
admin.site.register(UserProfile)
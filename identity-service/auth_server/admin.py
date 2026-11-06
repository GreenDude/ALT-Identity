from django.contrib import admin

from .models import AuthCode, UserProfile, Token, Client

admin.site.register(AuthCode)
admin.site.register(UserProfile)
admin.site.register(Token)
admin.site.register(Client)
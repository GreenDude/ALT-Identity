from django.contrib.auth.models import User
from django.db import models

class AuthCode(models.Model):

    auth_code = models.CharField(max_length=64, unique=True)
    user_name = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    expiry = models.DateTimeField()
    scope = models.TextField(blank=True, null=True)
    used = models.BooleanField(default=False)
    redirect_uri = models.URLField(blank=True, null=True)


class Token(models.Model):

    access_token = models.CharField(max_length=255, unique=True)
    refresh_token = models.CharField(max_length=255, unique=True)
    token_type = models.CharField(max_length=32, default="Bearer")
    user_name = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    expires_in = models.IntegerField()
    scope = models.TextField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    learning_goal = models.TextField(null=True)

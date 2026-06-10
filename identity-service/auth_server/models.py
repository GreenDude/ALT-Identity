"""Persistence models for authorization and profile data."""

from django.contrib.auth.models import User
from django.db import models

class AuthCode(models.Model):
    """Stores a short-lived, single-use authorization code.

    The code links a logged-in user to a client and redirect URI so the token
    endpoint can validate the authorization-code exchange. When PKCE is used,
    the stored challenge is matched against the verifier presented at the token
    endpoint.
    """

    auth_code = models.CharField(max_length=64, unique=True)
    user_name = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    expiry = models.DateTimeField()
    scope = models.TextField(blank=True, null=True)
    used = models.BooleanField(default=False)
    redirect_uri = models.URLField(blank=True, null=True)
    code_challenge = models.CharField(max_length=255, blank=True, null=True)
    code_challenge_method = models.CharField(max_length=16, blank=True, null=True)


class Token(models.Model):
    """Stores access and refresh token material issued to a client."""

    access_token = models.CharField(max_length=255, unique=True)
    refresh_token = models.CharField(max_length=255, unique=True)
    token_type = models.CharField(max_length=32, default="Bearer")
    user_name = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    expires_in = models.IntegerField()
    scope = models.TextField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)


class UserProfile(models.Model):
    """Extends Django's built-in user with demo profile information."""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    learning_goal = models.TextField(null=True)

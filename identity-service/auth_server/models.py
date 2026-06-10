from django.db import models

# Create your models here.
class AuthCodes(models.Model):
    """
        `user_name`: str
        `client_id`: str
        `expires_in`: datetime
        `scopes`: str
    """
    user_name = models.CharField()
    client_id = models.CharField()
    auth_code = models.CharField()
    expiry = models.DateTimeField()
    scope = models.TextField()

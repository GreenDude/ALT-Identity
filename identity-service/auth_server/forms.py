"""Forms for local identity-provider account management."""

from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django import forms

from .models import UserProfile


class RegistrationForm(UserCreationForm):
    """Create a local test user with OIDC profile claim fields."""

    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    learning_goal = forms.CharField(required=False, widget=forms.Textarea)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "learning_goal", "password1", "password2")

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]

        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                learning_goal=self.cleaned_data.get("learning_goal") or None,
            )

        return user

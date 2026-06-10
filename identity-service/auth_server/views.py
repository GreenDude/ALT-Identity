"""Views for the local identity provider.

This app intentionally implements a compact subset of an OIDC/OAuth-style
identity server so early-stage projects can exercise login, authorization-code,
token, and profile retrieval flows during development and automated testing.
"""

import base64
import datetime
import hashlib
import uuid

from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from config.http_logging import log_inbound_request, log_response

from .models import AuthCode, Token, UserProfile


def _apply_login_field_ids(form: AuthenticationForm) -> AuthenticationForm:
    """Attach stable DOM ids to login form fields for Selenium-style tests."""
    form.fields["username"].widget.attrs["id"] = "username-field"
    form.fields["password"].widget.attrs["id"] = "password-field"
    return form


def _create_pkce_challenge(verifier: str, method: str) -> str | None:
    """Derive a code challenge from a PKCE verifier for a supported method."""
    if method == "plain":
        return verifier

    if method == "S256":
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    return None


def login_view(request: HttpRequest) -> HttpResponse:
    """Render and process the username/password login form."""
    log_inbound_request(request)
    if request.method == "GET":
        form = _apply_login_field_ids(AuthenticationForm())
        return log_response(
            render(request, "auth_server/login.html", {"form": form}),
            source="auth_server.login_view",
        )

    if request.method == "POST":
        # process the request form
        form = _apply_login_field_ids(AuthenticationForm(request, data=request.POST))

        if form.is_valid():
            user = form.get_user()
            login(request, user)

            pending_authorization = request.session.pop("pending_authorization", None)
            if pending_authorization:
                return log_response(
                    redirect(pending_authorization),
                    source="auth_server.login_view",
                )

            return log_response(redirect("/"), source="auth_server.login_view")
        else:
            return log_response(
                render(request, "auth_server/login.html", {"form": form}),
                source="auth_server.login_view",
            )

    else:
        return log_response(
            HttpResponseNotAllowed(["GET", "POST"]),
            source="auth_server.login_view",
        )


def authorize(request: HttpRequest) -> HttpResponse | None | HttpResponseRedirect | HttpResponseNotAllowed:
    """Issue a single-use authorization code for an authenticated user.

    The request is deliberately small in scope and expects the standard query
    parameters used by the demo client: ``client_id``, ``redirect_uri``,
    ``response_type=code``, and an optional ``scope`` string.
    """
    log_inbound_request(request)
    client_id = request.GET.get("client_id")
    redirect_uri = request.GET.get("redirect_uri")
    response_type = request.GET.get("response_type")
    scope = request.GET.get("scope")
    code_challenge = request.GET.get("code_challenge")
    code_challenge_method = request.GET.get("code_challenge_method")

    if request.method == "GET":
        if request.user.is_authenticated:
            if not client_id:
                return log_response(HttpResponse("Client ID not provided", status=400), source="auth_server.authorize")
            if response_type != "code":
                return log_response(HttpResponse("Incorrect response type", status=400), source="auth_server.authorize")
            if not redirect_uri:
                return log_response(HttpResponse("Redirect URL not provided", status=400), source="auth_server.authorize")
            if code_challenge and not code_challenge_method:
                return log_response(HttpResponse("Code challenge method not provided", status=400), source="auth_server.authorize")
            if code_challenge_method and code_challenge_method not in {"plain", "S256"}:
                return log_response(HttpResponse("Unsupported code challenge method", status=400), source="auth_server.authorize")
            if code_challenge_method and not code_challenge:
                return log_response(HttpResponse("Code challenge not provided", status=400), source="auth_server.authorize")

            auth_code = uuid.uuid4().hex

            AuthCode.objects.create(
                user_name = request.user.username,
                client_id = client_id,
                scope = scope,
                expiry = timezone.now() + datetime.timedelta(minutes=5),
                auth_code = auth_code,
                redirect_uri = redirect_uri,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
            ).save()

            return log_response(
                redirect(f"{redirect_uri}?code={auth_code}"),
                source="auth_server.authorize",
            )

        else:
            # redirect to login page
            request.session["pending_authorization"] = request.get_full_path()
            return log_response(
                redirect(f"{reverse('login')}"),
                source="auth_server.authorize",
            )

    else:
        return log_response(
            HttpResponseNotAllowed(["GET"]),
            source="auth_server.authorize",
        )


@csrf_exempt
def token(request: HttpRequest) -> HttpResponse:
    """Exchange a valid authorization code for bearer-style token data."""
    log_inbound_request(request)
    if request.method == "POST":
        grant_type = request.POST.get("grant_type")
        code = request.POST.get("code")
        redirect_uri = request.POST.get("redirect_uri")
        client_id = request.POST.get("client_id")
        code_verifier = request.POST.get("code_verifier")

        now = timezone.now()

        if grant_type != "authorization_code":
            return log_response(
                JsonResponse({"error": "invalid_grant"}, status=400),
                source="auth_server.token",
            )

        authentication = AuthCode.objects.filter(
            auth_code=code,
            client_id=client_id,
            used=False,
            expiry__gt=now,
            redirect_uri=redirect_uri
        ).first()

        if authentication:
            if authentication.code_challenge:
                if not code_verifier:
                    return log_response(
                        JsonResponse({"error": "invalid_request"}, status=400),
                        source="auth_server.token",
                    )

                expected_challenge = _create_pkce_challenge(
                    code_verifier,
                    authentication.code_challenge_method or "plain",
                )
                if expected_challenge is None or expected_challenge != authentication.code_challenge:
                    return log_response(
                        JsonResponse({"error": "invalid_grant"}, status=400),
                        source="auth_server.token",
                    )

            authentication.used = True
            authentication.save()

            new_token = Token.objects.create(
                access_token = uuid.uuid4().hex,
                refresh_token = uuid.uuid4().hex,
                token_type ="Bearer",
                user_name = authentication.user_name,
                client_id = client_id,
                expires_in = 3600,
                scope = authentication.scope

            )
            new_token.save()

            return log_response(
                JsonResponse({
                    "access_token": new_token.access_token,
                    "refresh_token": new_token.refresh_token,
                    "token_type": new_token.token_type,
                    "expires_in": new_token.expires_in,
                    "scope": new_token.scope
                }),
                source="auth_server.token",
            )

        else:
            return log_response(
                JsonResponse({"error": "invalid_grant"}, status=400),
                source="auth_server.token",
            )

    return log_response(
        HttpResponseNotAllowed(["POST"]),
        source="auth_server.token",
    )


def request_profile_details(request: HttpRequest) -> HttpResponse:
    """Return the authenticated user's simple profile as JSON.

    This endpoint expects a bearer token in the ``Authorization`` header and
    currently exposes only the username and ``learning_goal`` fields.
    """
    log_inbound_request(request)
    authorization = request.headers.get("Authorization")

    if not authorization:
        return log_response(
            JsonResponse({"error": "missing_authorization_header"}, status=401),
            source="auth_server.request_profile_details",
        )

    if not authorization.startswith("Bearer "):
        return log_response(
            JsonResponse({"error": "invalid_authorization_header"}, status=401),
            source="auth_server.request_profile_details",
        )

    requested_token = authorization.removeprefix("Bearer ").strip()

    auth_token = Token.objects.filter(access_token=requested_token).first()

    if not auth_token:
        return log_response(
            JsonResponse({"error": "invalid_token"}, status=401),
            source="auth_server.request_profile_details",
        )

    user = User.objects.filter(username=auth_token.user_name).first()

    if not user:
        return log_response(
            JsonResponse({"error": "user_not_found"}, status=404),
            source="auth_server.request_profile_details",
        )

    profile = UserProfile.objects.filter(user=user).first()

    if not profile:
        return log_response(
            JsonResponse({"error": "profile_not_found"}, status=404),
            source="auth_server.request_profile_details",
        )

    return log_response(
        JsonResponse({
            "user_name": profile.user.username,
            "learning_goal": profile.learning_goal,
        }),
        source="auth_server.request_profile_details",
    )


def logout_view(request: HttpRequest) -> HttpResponse:
    """Log the current browser session out and return to the landing page."""
    log_inbound_request(request)
    logout(request)
    return log_response(redirect("/"), source="auth_server.logout_view")

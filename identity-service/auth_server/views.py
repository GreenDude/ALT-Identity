"""Views for the local OpenID Connect provider."""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import logging
import uuid
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from config.http_logging import log_inbound_request, log_response

from .models import AuthCode, Client, Token, UserProfile
from .oidc import build_jwks, get_issuer, sign_jwt


LOGGER = logging.getLogger("alt_identity.http")


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


def _wants_html(request: HttpRequest) -> bool:
    """Best-effort check for direct browser visits."""
    accept = request.headers.get("Accept", "")
    return "text/html" in accept


def _parse_scopes(scope_value: str | None) -> set[str]:
    if not scope_value:
        return set()
    return {scope for scope in scope_value.split() if scope}


def _profile_claims(user: User, profile: UserProfile | None) -> dict[str, str]:
    claims = {}

    if user.first_name:
        claims["given_name"] = user.first_name
    if user.last_name:
        claims["family_name"] = user.last_name

    full_name = user.get_full_name()
    if full_name:
        claims["name"] = full_name

    if profile and profile.learning_goal:
        claims["learning_goal"] = profile.learning_goal

    return claims


def _append_query_params(url: str, params: dict[str, str]) -> str:
    parsed = urlsplit(url)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_params.update(params)
    return urlunsplit(parsed._replace(query=urlencode(query_params)))


def _oauth_error_response(
    error: str,
    description: str,
    redirect_uri: str | None = None,
    state: str | None = None,
    status: int = 400,
) -> HttpResponse:
    payload = {"error": error, "error_description": description}
    if state:
        payload["state"] = state

    if redirect_uri:
        return HttpResponseRedirect(_append_query_params(redirect_uri, payload), status=302)

    return JsonResponse(payload, status=status)


def _endpoint_examples(request: HttpRequest) -> dict[str, str]:
    """Build stable endpoint examples for the demo templates."""
    authorize_url = request.build_absolute_uri(reverse("authorize"))
    callback_url = request.build_absolute_uri(reverse("aot_callback"))
    return {
        "authorize_example": (
            f"{authorize_url}?client_id=awesome-service&redirect_uri={callback_url}"
            "&response_type=code&scope=openid+profile&state=demo-state&nonce=demo-nonce"
            "&code_challenge=demo-challenge&code_challenge_method=S256"
        ),
        "userinfo_url": request.build_absolute_uri(reverse("userinfo")),
        "configuration_url": request.build_absolute_uri(reverse("openid_configuration")),
    }


def _load_client(client_id: str | None) -> Client | None:
    if not client_id:
        return None
    return Client.objects.filter(client_id=client_id).first()


def _redirect_uri_is_registered(client: Client | None, redirect_uri: str | None) -> bool:
    return bool(client and redirect_uri and redirect_uri in client.registered_redirect_uris())


def _build_id_token(user: User, auth_code: AuthCode) -> str:
    issued_at = int(timezone.now().timestamp())
    expires_at = issued_at + 3600
    claims: dict[str, Any] = {
        "iss": get_issuer(),
        "sub": str(user.pk),
        "aud": auth_code.client_id,
        "exp": expires_at,
        "iat": issued_at,
    }
    if auth_code.nonce:
        claims["nonce"] = auth_code.nonce
    return sign_jwt(claims)


def login_view(request: HttpRequest) -> HttpResponse:
    """Render and process the username/password login form."""
    log_inbound_request(request)
    if request.method == "GET":
        form = _apply_login_field_ids(AuthenticationForm())
        return log_response(
            render(
                request,
                "auth_server/login.html",
                {
                    "form": form,
                    "pending_authorization": request.session.get("pending_authorization"),
                },
            ),
            source="auth_server.login_view",
        )

    if request.method == "POST":
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

        return log_response(
            render(
                request,
                "auth_server/login.html",
                {
                    "form": form,
                    "pending_authorization": request.session.get("pending_authorization"),
                },
            ),
            source="auth_server.login_view",
        )

    return log_response(
        HttpResponseNotAllowed(["GET", "POST"]),
        source="auth_server.login_view",
    )


def authorize(request: HttpRequest) -> HttpResponse | HttpResponseRedirect | HttpResponseNotAllowed:
    """Issue a single-use authorization code for an authenticated user."""
    log_inbound_request(request)
    if request.method != "GET":
        return log_response(
            HttpResponseNotAllowed(["GET"]),
            source="auth_server.authorize",
        )

    if not request.GET:
        return log_response(
            render(
                request,
                "auth_server/authorize.html",
                {
                    "endpoint_examples": _endpoint_examples(request),
                    "request_params": [],
                },
            ),
            source="auth_server.authorize",
        )

    client_id = request.GET.get("client_id")
    redirect_uri = request.GET.get("redirect_uri")
    response_type = request.GET.get("response_type")
    scope = request.GET.get("scope")
    state = request.GET.get("state")
    nonce = request.GET.get("nonce")
    code_challenge = request.GET.get("code_challenge")
    code_challenge_method = request.GET.get("code_challenge_method")

    client = _load_client(client_id)
    if not client:
        return log_response(
            _oauth_error_response("invalid_client", "Unknown client_id.", status=400),
            source="auth_server.authorize",
        )

    if not _redirect_uri_is_registered(client, redirect_uri):
        return log_response(
            _oauth_error_response("invalid_request", "Unregistered redirect_uri.", status=400),
            source="auth_server.authorize",
        )

    requested_scopes = _parse_scopes(scope)
    allowed_scopes = client.allowed_scope_set()

    if response_type != "code":
        return log_response(
            _oauth_error_response(
                "unsupported_response_type",
                "Only response_type=code is supported.",
                redirect_uri=redirect_uri,
                state=state,
            ),
            source="auth_server.authorize",
        )
    if not state:
        return log_response(
            _oauth_error_response(
                "invalid_request",
                "Missing required state parameter.",
                redirect_uri=redirect_uri,
            ),
            source="auth_server.authorize",
        )
    if "openid" not in requested_scopes:
        return log_response(
            _oauth_error_response(
                "invalid_scope",
                "The openid scope is required.",
                redirect_uri=redirect_uri,
                state=state,
            ),
            source="auth_server.authorize",
        )
    if not requested_scopes.issubset(allowed_scopes):
        return log_response(
            _oauth_error_response(
                "invalid_scope",
                "One or more requested scopes are not allowed for this client.",
                redirect_uri=redirect_uri,
                state=state,
            ),
            source="auth_server.authorize",
        )
    if not nonce:
        return log_response(
            _oauth_error_response(
                "invalid_request",
                "Missing required nonce parameter.",
                redirect_uri=redirect_uri,
                state=state,
            ),
            source="auth_server.authorize",
        )
    if not client.is_confidential and not code_challenge:
        return log_response(
            _oauth_error_response(
                "invalid_request",
                "Public clients must send a PKCE code_challenge.",
                redirect_uri=redirect_uri,
                state=state,
            ),
            source="auth_server.authorize",
        )
    if code_challenge and not code_challenge_method:
        return log_response(
            _oauth_error_response(
                "invalid_request",
                "Code challenge method not provided.",
                redirect_uri=redirect_uri,
                state=state,
            ),
            source="auth_server.authorize",
        )
    if code_challenge_method and code_challenge_method not in {"plain", "S256"}:
        return log_response(
            _oauth_error_response(
                "invalid_request",
                "Unsupported code challenge method.",
                redirect_uri=redirect_uri,
                state=state,
            ),
            source="auth_server.authorize",
        )

    if not request.user.is_authenticated:
        request.session["pending_authorization"] = request.get_full_path()
        LOGGER.info(
            "OIDC authorization pending login: %s",
            json.dumps(
                {
                    "kind": "oidc_authorization_pending_login",
                    "client_id": client.client_id,
                    "redirect_uri": redirect_uri,
                    "state": state,
                    "nonce_present": bool(nonce),
                    "code_challenge_method": code_challenge_method,
                    "session_key": request.session.session_key,
                    "session_cookie_present": bool(request.COOKIES.get(settings.SESSION_COOKIE_NAME)),
                    "pending_authorization": request.session.get("pending_authorization"),
                },
                sort_keys=True,
            ),
        )
        return log_response(
            redirect(reverse("login")),
            source="auth_server.authorize",
        )

    auth_code = uuid.uuid4().hex
    AuthCode.objects.create(
        user_name=request.user.username,
        client_id=client.client_id,
        scope=" ".join(sorted(requested_scopes)),
        expiry=timezone.now() + datetime.timedelta(minutes=5),
        auth_code=auth_code,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        state=state,
        nonce=nonce,
    ).save()
    callback_url = _append_query_params(redirect_uri, {"code": auth_code, "state": state})

    LOGGER.info(
        "OIDC authorization redirect issued: %s",
        json.dumps(
            {
                "kind": "oidc_authorization_redirect_issued",
                "client_id": client.client_id,
                "redirect_uri": redirect_uri,
                "callback_url": callback_url,
                "state": state,
                "nonce_present": bool(nonce),
                "scope": " ".join(sorted(requested_scopes)),
                "code_challenge_method": code_challenge_method,
                "auth_code": auth_code,
                "user": request.user.username,
                "session_key": request.session.session_key,
                "session_cookie_present": bool(request.COOKIES.get(settings.SESSION_COOKIE_NAME)),
            },
            sort_keys=True,
        ),
    )

    return log_response(
        redirect(callback_url),
        source="auth_server.authorize",
    )


@csrf_exempt
def token(request: HttpRequest) -> HttpResponse:
    """Exchange a valid authorization code for bearer-style token data."""
    log_inbound_request(request)
    if request.method != "POST":
        return log_response(
            HttpResponseNotAllowed(["POST"]),
            source="auth_server.token",
        )

    grant_type = request.POST.get("grant_type")
    code = request.POST.get("code")
    redirect_uri = request.POST.get("redirect_uri")
    client_id = request.POST.get("client_id")
    code_verifier = request.POST.get("code_verifier")

    if grant_type != "authorization_code":
        return log_response(
            JsonResponse({"error": "unsupported_grant_type"}, status=400),
            source="auth_server.token",
        )

    client = _load_client(client_id)
    if not _redirect_uri_is_registered(client, redirect_uri):
        return log_response(
            JsonResponse({"error": "invalid_client"}, status=400),
            source="auth_server.token",
        )

    now = timezone.now()
    authentication = AuthCode.objects.filter(
        auth_code=code,
        client_id=client_id,
        used=False,
        expiry__gt=now,
        redirect_uri=redirect_uri,
    ).first()

    if not authentication:
        return log_response(
            JsonResponse({"error": "invalid_grant"}, status=400),
            source="auth_server.token",
        )

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
        access_token=uuid.uuid4().hex,
        refresh_token=uuid.uuid4().hex,
        token_type="Bearer",
        user_name=authentication.user_name,
        client_id=client.client_id,
        expires_in=3600,
        scope=authentication.scope,
    )
    new_token.save()

    response_body: dict[str, Any] = {
        "access_token": new_token.access_token,
        "refresh_token": new_token.refresh_token,
        "token_type": new_token.token_type,
        "expires_in": new_token.expires_in,
        "scope": new_token.scope,
    }

    if "openid" in _parse_scopes(authentication.scope):
        user = User.objects.filter(username=authentication.user_name).first()
        if not user:
            return log_response(
                JsonResponse({"error": "server_error"}, status=500),
                source="auth_server.token",
            )
        try:
            response_body["id_token"] = _build_id_token(user, authentication)
        except ImproperlyConfigured:
            return log_response(
                JsonResponse({"error": "server_error"}, status=500),
                source="auth_server.token",
            )

    return log_response(
        JsonResponse(response_body),
        source="auth_server.token",
    )


def userinfo(request: HttpRequest) -> HttpResponse:
    """Return the authenticated user's OIDC userinfo document."""
    log_inbound_request(request)
    authorization = request.headers.get("Authorization")

    if request.method != "GET":
        return log_response(
            HttpResponseNotAllowed(["GET"]),
            source="auth_server.userinfo",
        )

    if not authorization and _wants_html(request):
        return log_response(
            render(
                request,
                "auth_server/profile_endpoint.html",
                {
                    "endpoint_examples": _endpoint_examples(request),
                },
            ),
            source="auth_server.userinfo",
        )

    if not authorization:
        response = JsonResponse({"error": "missing_authorization_header"}, status=401)
        response["WWW-Authenticate"] = 'Bearer error="invalid_token"'
        return log_response(response, source="auth_server.userinfo")

    if not authorization.startswith("Bearer "):
        response = JsonResponse({"error": "invalid_authorization_header"}, status=401)
        response["WWW-Authenticate"] = 'Bearer error="invalid_token"'
        return log_response(response, source="auth_server.userinfo")

    requested_token = authorization.removeprefix("Bearer ").strip()
    auth_token = Token.objects.filter(access_token=requested_token).first()

    if not auth_token or auth_token.is_expired():
        response = JsonResponse({"error": "invalid_token"}, status=401)
        response["WWW-Authenticate"] = 'Bearer error="invalid_token"'
        return log_response(response, source="auth_server.userinfo")

    if "openid" not in _parse_scopes(auth_token.scope):
        response = JsonResponse({"error": "insufficient_scope"}, status=403)
        response["WWW-Authenticate"] = 'Bearer error="insufficient_scope", scope="openid"'
        return log_response(response, source="auth_server.userinfo")

    user = User.objects.filter(username=auth_token.user_name).first()
    if not user:
        return log_response(
            JsonResponse({"error": "user_not_found"}, status=404),
            source="auth_server.userinfo",
        )

    profile = UserProfile.objects.filter(user=user).first()
    claims: dict[str, str] = {
        "sub": str(user.pk),
        "preferred_username": user.username,
    }
    if "profile" in _parse_scopes(auth_token.scope):
        claims.update(_profile_claims(user, profile))

    return log_response(
        JsonResponse(claims),
        source="auth_server.userinfo",
    )


def openid_configuration(request: HttpRequest) -> HttpResponse:
    """Publish OIDC discovery metadata."""
    log_inbound_request(request)
    if request.method != "GET":
        return log_response(
            HttpResponseNotAllowed(["GET"]),
            source="auth_server.openid_configuration",
        )

    issuer = get_issuer()
    metadata = {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}{reverse('authorize')}",
        "token_endpoint": f"{issuer}{reverse('token')}",
        "userinfo_endpoint": f"{issuer}{reverse('userinfo')}",
        "jwks_uri": f"{issuer}{reverse('jwks')}",
        "scopes_supported": ["openid", "profile"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["plain", "S256"],
        "claims_supported": ["sub", "preferred_username", "name", "given_name", "family_name", "learning_goal"],
    }
    return log_response(
        JsonResponse(metadata),
        source="auth_server.openid_configuration",
    )


def jwks(request: HttpRequest) -> HttpResponse:
    """Publish the public signing key as JWKS."""
    log_inbound_request(request)
    if request.method != "GET":
        return log_response(
            HttpResponseNotAllowed(["GET"]),
            source="auth_server.jwks",
        )

    try:
        document = build_jwks()
    except ImproperlyConfigured:
        return log_response(
            JsonResponse({"error": "server_error"}, status=500),
            source="auth_server.jwks",
        )
    return log_response(
        JsonResponse(document),
        source="auth_server.jwks",
    )


def logout_view(request: HttpRequest) -> HttpResponse:
    """Log the current browser session out and return to the landing page."""
    log_inbound_request(request)
    if request.method == "GET":
        return log_response(
            render(
                request,
                "auth_server/logout.html",
                {"is_authenticated": request.user.is_authenticated},
            ),
            source="auth_server.logout_view",
        )

    logout(request)
    return log_response(redirect("/"), source="auth_server.logout_view")

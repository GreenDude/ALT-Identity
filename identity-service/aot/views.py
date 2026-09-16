"""Views for the relying-party demo application.

The ``aot`` app plays the role of a very small client application that uses the
local identity service. It demonstrates the happy-path authorization code flow:

1. redirect the browser to the authorization endpoint,
2. receive an authorization code on the callback URL,
3. exchange that code for tokens, and
4. call the protected profile endpoint with the access token.

The resulting profile response is rendered as HTML so developers can inspect the
payload manually and automate the flow with browser-based tests.
"""

import base64
import json
import logging
import secrets
from hashlib import sha256
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse

from auth_server.models import Client
from config.http_logging import log_inbound_request, log_outbound_request, log_outbound_response, log_response


LOGGER = logging.getLogger("alt_identity.http")
DEMO_CLIENT_ID = "awesome-service"


def _generate_pkce_verifier() -> str:
    """Create a high-entropy PKCE code verifier for the demo client."""
    return secrets.token_urlsafe(64)


def _generate_state() -> str:
    """Create a stable anti-forgery state value for the auth redirect."""
    return secrets.token_urlsafe(32)


def _generate_nonce() -> str:
    """Create a nonce value that will be bound into the resulting id_token."""
    return secrets.token_urlsafe(32)


def _generate_pkce_challenge(verifier: str) -> str:
    """Create an RFC 7636 S256 code challenge from a verifier."""
    digest = sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _build_absolute_url(request: HttpRequest, route_name: str) -> str:
    """Build an absolute URL for the current host and a named route."""
    return request.build_absolute_uri(reverse(route_name))


def _ensure_demo_client_redirect_uri(redirect_uri: str) -> None:
    """Keep the bundled demo client usable on the current development host."""
    client, _ = Client.objects.get_or_create(
        client_id=DEMO_CLIENT_ID,
        defaults={
            "name": "Bundled Demo Client",
            "redirect_uris": redirect_uri,
            "allowed_scopes": "openid profile",
            "is_confidential": False,
        },
    )
    redirect_uris = client.registered_redirect_uris()
    if redirect_uri in redirect_uris:
        return

    redirect_uris.append(redirect_uri)
    client.redirect_uris = "\n".join(redirect_uris)
    client.save(update_fields=["redirect_uris"])


def _build_authorize_redirect_url(
    request: HttpRequest,
    code_challenge: str,
    state: str,
    nonce: str,
) -> str:
    """Build the authorization redirect URL using the current request host."""
    redirect_uri = _build_absolute_url(request, "aot_callback")
    _ensure_demo_client_redirect_uri(redirect_uri)
    query = urlencode(
        {
            "client_id": DEMO_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{_build_absolute_url(request, 'authorize')}?{query}"


def _build_demo_flow_steps(request: HttpRequest) -> list[dict[str, str | bool]]:
    """Describe the demo flow with links and simple completion state."""
    return [
        {
            "title": "1. Start at the client",
            "description": "The relying-party app sends the browser into the authorization-code flow.",
            "href": reverse("index"),
            "status": True,
        },
        {
            "title": "2. Authenticate",
            "description": "The identity server presents the local username and password form.",
            "href": reverse("login"),
            "status": request.user.is_authenticated,
        },
        {
            "title": "3. Exchange code for tokens",
            "description": "The callback swaps the single-use auth code for bearer-style tokens.",
            "href": reverse("aot_callback"),
            "status": bool(request.session.get("access_token")),
        },
        {
            "title": "4. Read the protected profile",
            "description": "The demo client calls the protected userinfo endpoint and renders the response.",
            "href": reverse("aot_request_profile"),
            "status": bool(request.session.get("access_token")),
        },
    ]


def index(request: HttpRequest) -> HttpResponse:
    """Render the landing page for the demo relying-party application."""
    log_inbound_request(request)
    return log_response(
        render(
            request,
            "aot/index.html",
            {
                "demo_flow_steps": _build_demo_flow_steps(request),
                "access_token_present": bool(request.session.get("access_token")),
                "refresh_token_present": bool(request.session.get("refresh_token")),
                "id_token_present": bool(request.session.get("id_token")),
                "pkce_verifier_present": bool(request.session.get("pkce_code_verifier")),
                "state_present": bool(request.session.get("oidc_state")),
                "nonce_present": bool(request.session.get("oidc_nonce")),
            },
        ),
        source="aot.index",
    )


def aot_service(request: HttpRequest) -> HttpResponse:
    """Placeholder for future demo functionality beyond the profile example."""
    log_inbound_request(request)
    if request.method == 'GET':
        if request.session.session_key:
            # Get access token from DB and request the needed stuff
            # if token is expired
                # use refresh token ot access the new one
            pass
        else:
            # Redirect to login page

            pass

        return log_response(render(request, 'aot/aot_service.html'), source="aot.aot_service")

    return log_response(HttpResponse("Not implemented", status=501), source="aot.aot_service")


def aot_callback(request: HttpRequest) -> HttpResponse:
    """Exchange an authorization code for tokens and store them in the session."""
    log_inbound_request(request)
    auth_code = request.GET.get("code")
    returned_state = request.GET.get("state")
    code_verifier = request.session.get("pkce_code_verifier")
    expected_state = request.session.get("oidc_state")
    if not auth_code:
        return log_response(
            render(
                request,
                "aot/callback.html",
                {
                    "callback_status": "Waiting for authorization response",
                    "callback_message": "Open this route through the authorize flow so it receives a `code` query parameter.",
                    "query_params": request.GET.urlencode(),
                },
                status=400,
            ),
            source="aot.aot_callback",
        )
    if not returned_state or not expected_state or returned_state != expected_state:
        LOGGER.warning(
            "Invalid OIDC state on callback: %s",
            json.dumps(
                {
                    "kind": "oidc_state_verification_failed",
                    "path": request.path,
                    "query_string": request.META.get("QUERY_STRING", ""),
                    "returned_state": returned_state,
                    "expected_state": expected_state,
                    "auth_code_present": bool(auth_code),
                    "session_key": request.session.session_key,
                    "session_has_pkce_verifier": bool(code_verifier),
                    "session_has_nonce": bool(request.session.get("oidc_nonce")),
                    "session_cookie_present": request.COOKIES.get(settings.SESSION_COOKIE_NAME) is not None,
                },
                sort_keys=True,
            ),
        )
        return log_response(
            render(
                request,
                "aot/callback.html",
                {
                    "callback_status": "State verification failed",
                    "callback_message": "The callback did not include the expected OIDC state value.",
                    "query_params": request.GET.urlencode(),
                },
                status=400,
            ),
            source="aot.aot_callback",
        )
    if not code_verifier:
        return log_response(
            render(
                request,
                "aot/callback.html",
                {
                    "callback_status": "Missing PKCE verifier",
                    "callback_message": "The browser session does not contain the PKCE verifier needed for the token exchange.",
                    "query_params": request.GET.urlencode(),
                },
                status=400,
            ),
            source="aot.aot_callback",
        )

    token_endpoint_url = _build_absolute_url(request, "token")
    token_form_data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "client_id": DEMO_CLIENT_ID,
        "redirect_uri": _build_absolute_url(request, "aot_callback"),
        "code_verifier": code_verifier,
    }
    payload = urlencode(token_form_data).encode("utf-8")
    token_request = Request(
        token_endpoint_url,
        data=payload,
        method="POST",
    )
    log_outbound_request(
        "POST",
        token_endpoint_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=token_form_data,
    )

    try:
        with urlopen(token_request, timeout=5) as response:
            token_status = response.status
            token_body = response.read().decode("utf-8")
    except HTTPError as exc:
        token_status = exc.code
        token_body = exc.read().decode("utf-8")
    except URLError as exc:
        return log_response(
            render(
                request,
                "aot/callback.html",
                {
                    "callback_status": "Token endpoint unavailable",
                    "callback_message": f"Unable to reach token endpoint: {exc.reason}",
                    "query_params": request.GET.urlencode(),
                },
                status=502,
            ),
            source="aot.aot_callback",
        )
    log_outbound_response(
        method="POST",
        url=token_endpoint_url,
        status_code=token_status,
        body=token_body,
    )

    try:
        token_data = json.loads(token_body)
    except ValueError:
        return log_response(
            render(
                request,
                "aot/callback.html",
                {
                    "callback_status": "Unexpected token response",
                    "callback_message": "The token endpoint returned a non-JSON response.",
                    "raw_response": token_body,
                    "query_params": request.GET.urlencode(),
                },
                status=token_status,
            ),
            source="aot.aot_callback",
        )

    if token_status != 200:
        return log_response(
            JsonResponse(token_data, status=token_status),
            source="aot.aot_callback",
        )

    request.session["access_token"] = token_data["access_token"]
    request.session["refresh_token"] = token_data.get("refresh_token")
    request.session["id_token"] = token_data.get("id_token")
    request.session.pop("pkce_code_verifier", None)
    request.session.pop("oidc_state", None)
    request.session.pop("oidc_nonce", None)

    return log_response(redirect("aot_request_profile"), source="aot.aot_callback")


def aot_request_profile(request: HttpRequest) -> HttpResponse:
    """Request the authenticated user's profile and render it as HTML.

    When no access token is present, or when the current token is rejected, the
    browser is sent back through the authorization flow to obtain a fresh code.
    """
    log_inbound_request(request)
    access_token = request.session.get("access_token")

    if not access_token:
        code_verifier = _generate_pkce_verifier()
        state = _generate_state()
        nonce = _generate_nonce()
        request.session["pkce_code_verifier"] = code_verifier
        request.session["oidc_state"] = state
        request.session["oidc_nonce"] = nonce
        code_challenge = _generate_pkce_challenge(code_verifier)
        return log_response(
            redirect(_build_authorize_redirect_url(request, code_challenge, state, nonce)),
            source="aot.aot_request_profile",
        )

    profile_endpoint_url = _build_absolute_url(request, "userinfo")
    profile_request = Request(
        profile_endpoint_url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    log_outbound_request(
        "GET",
        profile_endpoint_url,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    try:
        with urlopen(profile_request, timeout=5) as response:
            profile_status = response.status
            profile_body = response.read().decode("utf-8")
    except HTTPError as exc:
        profile_status = exc.code
        profile_body = exc.read().decode("utf-8")
    except URLError as exc:
        return log_response(
            HttpResponse(f"Unable to reach profile endpoint: {exc.reason}", status=502),
            source="aot.aot_request_profile",
        )
    log_outbound_response(
        method="GET",
        url=profile_endpoint_url,
        status_code=profile_status,
        body=profile_body,
    )

    if profile_status == 401:
        request.session.pop("access_token", None)
        request.session.pop("refresh_token", None)
        request.session.pop("id_token", None)
        code_verifier = _generate_pkce_verifier()
        state = _generate_state()
        nonce = _generate_nonce()
        request.session["pkce_code_verifier"] = code_verifier
        request.session["oidc_state"] = state
        request.session["oidc_nonce"] = nonce
        code_challenge = _generate_pkce_challenge(code_verifier)

        return log_response(
            redirect(_build_authorize_redirect_url(request, code_challenge, state, nonce)),
            source="aot.aot_request_profile",
        )

    try:
        profile_data = json.loads(profile_body)
    except ValueError:
        return log_response(
            HttpResponse(
                f"Profile endpoint returned non-JSON response:\n\n{profile_body}",
                status=profile_status,
            ),
            source="aot.aot_request_profile",
        )

    return log_response(
        render(
            request,
            "aot/profile.html",
            {
                "profile_data": profile_data,
                "formatted_json": json.dumps(profile_data, indent=2, sort_keys=True),
                "response_status": profile_status,
                "access_token_present": bool(request.session.get("access_token")),
                "refresh_token_present": bool(request.session.get("refresh_token")),
                "id_token_present": bool(request.session.get("id_token")),
            },
            status=profile_status,
        ),
        source="aot.aot_request_profile",
    )

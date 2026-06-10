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
import secrets
from hashlib import sha256
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect


def _generate_pkce_verifier() -> str:
    """Create a high-entropy PKCE code verifier for the demo client."""
    return secrets.token_urlsafe(64)


def _generate_pkce_challenge(verifier: str) -> str:
    """Create an RFC 7636 S256 code challenge from a verifier."""
    digest = sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def index(request: HttpRequest) -> HttpResponse:
    """Render the landing page for the demo relying-party application."""
    return render(request, 'aot/index.html')


def aot_service(request: HttpRequest) -> HttpResponse:
    """Placeholder for future demo functionality beyond the profile example."""
    if request.method == 'GET':
        if request.session.session_key:
            # Get access token from DB and request the needed stuff
            # if token is expired
                # use refresh token ot access the new one
            pass
        else:
            # Redirect to login page

            pass

        return render(request, 'aot/aot_service.html')

    return HttpResponse("Not implemented", status=501)


def aot_callback(request: HttpRequest) -> HttpResponse:
    """Exchange an authorization code for tokens and store them in the session."""
    auth_code = request.GET.get("code")
    code_verifier = request.session.get("pkce_code_verifier")
    if not auth_code:
        return HttpResponse("Missing authorization code", status=400)
    if not code_verifier:
        return HttpResponse("Missing PKCE code verifier in session", status=400)

    payload = urlencode(
        {
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": "awesome-service",
            "redirect_uri": "http://localhost:8000/callback",
            "code_verifier": code_verifier,
        }
    ).encode("utf-8")
    token_request = Request(
        "http://localhost:8000/auth/token",
        data=payload,
        method="POST",
    )

    try:
        with urlopen(token_request, timeout=5) as response:
            token_status = response.status
            token_body = response.read().decode("utf-8")
    except HTTPError as exc:
        token_status = exc.code
        token_body = exc.read().decode("utf-8")
    except URLError as exc:
        return HttpResponse(f"Unable to reach token endpoint: {exc.reason}", status=502)

    try:
        token_data = json.loads(token_body)
    except ValueError:
        return HttpResponse(
            f"Token endpoint returned non-JSON response:\n\n{token_body}",
            status=token_status,
        )

    if token_status != 200:
        return JsonResponse(token_data, status=token_status)

    request.session["access_token"] = token_data["access_token"]
    request.session["refresh_token"] = token_data.get("refresh_token")
    request.session.pop("pkce_code_verifier", None)

    return redirect("aot_request_profile")


def aot_request_profile(request: HttpRequest) -> HttpResponse:
    """Request the authenticated user's profile and render it as HTML.

    When no access token is present, or when the current token is rejected, the
    browser is sent back through the authorization flow to obtain a fresh code.
    """
    access_token = request.session.get("access_token")

    if not access_token:
        code_verifier = _generate_pkce_verifier()
        request.session["pkce_code_verifier"] = code_verifier
        code_challenge = _generate_pkce_challenge(code_verifier)
        return redirect(
            "http://localhost:8000/auth/authorize"
            "?client_id=awesome-service"
            "&redirect_uri=http://localhost:8000/callback"
            "&response_type=code"
            "&scope=profile.read"
            f"&code_challenge={code_challenge}"
            "&code_challenge_method=S256"
        )

    profile_request = Request(
        "http://localhost:8000/auth/profile",
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )

    try:
        with urlopen(profile_request, timeout=5) as response:
            profile_status = response.status
            profile_body = response.read().decode("utf-8")
    except HTTPError as exc:
        profile_status = exc.code
        profile_body = exc.read().decode("utf-8")
    except URLError as exc:
        return HttpResponse(f"Unable to reach profile endpoint: {exc.reason}", status=502)

    if profile_status == 401:
        request.session.pop("access_token", None)
        request.session.pop("refresh_token", None)
        code_verifier = _generate_pkce_verifier()
        request.session["pkce_code_verifier"] = code_verifier
        code_challenge = _generate_pkce_challenge(code_verifier)

        return redirect(
            "http://localhost:8000/auth/authorize"
            "?client_id=awesome-service"
            "&redirect_uri=http://localhost:8000/callback"
            "&response_type=code"
            "&scope=profile.read"
            f"&code_challenge={code_challenge}"
            "&code_challenge_method=S256"
        )

    try:
        profile_data = json.loads(profile_body)
    except ValueError:
        return HttpResponse(
            f"Profile endpoint returned non-JSON response:\n\n{profile_body}",
            status=profile_status,
        )

    return render(
        request,
        "aot/profile.html",
        {
            "profile_data": profile_data,
            "formatted_json": json.dumps(profile_data, indent=2, sort_keys=True),
            "response_status": profile_status,
        },
        status=profile_status,
    )

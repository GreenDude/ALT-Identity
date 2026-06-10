import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect


def index(request: HttpRequest) -> HttpResponse:
    return render(request, 'aot/index.html')


def aot_service(request: HttpRequest) -> HttpResponse:
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
    auth_code = request.GET.get("code")
    if not auth_code:
        return HttpResponse("Missing authorization code", status=400)

    payload = urlencode(
        {
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": "awesome-service",
            "redirect_uri": "http://localhost:8000/callback",
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

    return redirect("aot_request_profile")


def aot_request_profile(request: HttpRequest) -> HttpResponse:
    access_token = request.session.get("access_token")

    if not access_token:
        return redirect(
            "http://localhost:8000/auth/authorize"
            "?client_id=awesome-service"
            "&redirect_uri=http://localhost:8000/callback"
            "&response_type=code"
            "&scope=profile.read"
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

        return redirect(
            "http://localhost:8000/auth/authorize"
            "?client_id=awesome-service"
            "&redirect_uri=http://localhost:8000/callback"
            "&response_type=code"
            "&scope=profile.read"
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

import requests

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
    token_response = requests.post(
        "http://localhost:8000/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": "awesome-service",
            "redirect_uri": "http://localhost:8000/callback",
        },
        timeout=5,
    )

    try:
        token_data = token_response.json()
    except ValueError:
        return HttpResponse(
            f"Token endpoint returned non-JSON response:\n\n{token_response.text}",
            status=token_response.status_code,
        )

    if token_response.status_code != 200:
        return JsonResponse(token_data, status=token_response.status_code)

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

    profile_response = requests.get(
        "http://localhost:8000/auth/profile",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        timeout=5,
    )

    if profile_response.status_code == 401:
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
        profile_data = profile_response.json()
    except ValueError:
        return HttpResponse(
            f"Profile endpoint returned non-JSON response:\n\n{profile_response.text}",
            status=profile_response.status_code,
        )

    return JsonResponse(profile_data, status=profile_response.status_code)
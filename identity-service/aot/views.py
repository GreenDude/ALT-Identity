import requests

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

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
        response_data = token_response.json()
    except ValueError:
        return HttpResponse(
            f"Token endpoint returned non-JSON response:\n\n{token_response.text}",
            status=token_response.status_code,
        )
    return JsonResponse(response_data, status=token_response.status_code)
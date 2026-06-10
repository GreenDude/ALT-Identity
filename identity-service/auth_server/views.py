import datetime
import uuid

from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import AuthCode, Token, UserProfile

def login_view(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        form = AuthenticationForm()
        return render(request, "auth_server/login.html", {"form": form})

    if request.method == "POST":
        # process the request form
        form = AuthenticationForm(request, data=request.POST)

        if form.is_valid():
            user = form.get_user()
            login(request, user)

            pending_authorization = request.session.pop("pending_authorization", None)
            if pending_authorization:
                return redirect(pending_authorization)

            return redirect("/")
        else:
            return render(request, "auth_server/login.html", {"form": form})

    else:
        return HttpResponseNotAllowed(["GET", "POST"])


def authorize(request: HttpRequest) -> HttpResponse | None | HttpResponseRedirect | HttpResponseNotAllowed:
    client_id = request.GET.get("client_id")
    redirect_uri = request.GET.get("redirect_uri")
    response_type = request.GET.get("response_type")
    scope = request.GET.get("scope")

    if request.method == "GET":
        if request.user.is_authenticated:
            if not client_id:
                return HttpResponse("Client ID not provided", status=400)
            if response_type != "code":
                return HttpResponse("Incorrect response type", status=400)
            if not redirect_uri:
                return HttpResponse("Redirect URL not provided", status=400)

            auth_code = uuid.uuid4().hex

            AuthCode.objects.create(
                user_name = request.user.username,
                client_id = client_id,
                scope = scope,
                expiry = timezone.now() + datetime.timedelta(minutes=5),
                auth_code = auth_code,
                redirect_uri = redirect_uri,
            ).save()

            return redirect(f"{redirect_uri}?code={auth_code}")

        else:
            # redirect to login page
            request.session["pending_authorization"] = request.get_full_path()
            return redirect(f"{reverse('login')}")

    else:
        return HttpResponseNotAllowed(["GET"])


@csrf_exempt
def token(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        grant_type = request.POST.get("grant_type")
        code = request.POST.get("code")
        redirect_uri = request.POST.get("redirect_uri")
        client_id = request.POST.get("client_id")

        now = timezone.now()

        if grant_type != "authorization_code":
            return JsonResponse({"error": "invalid_grant"}, status=400)

        authentication = AuthCode.objects.filter(
            auth_code=code,
            client_id=client_id,
            used=False,
            expiry__gt=now,
            redirect_uri=redirect_uri
        ).first()

        if authentication:
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

            return JsonResponse({
                "access_token": new_token.access_token,
                "refresh_token": new_token.refresh_token,
                "token_type": new_token.token_type,
                "expires_in": new_token.expires_in,
                "scope": new_token.scope
            })

        else:
            return JsonResponse({"error": "invalid_grant"}, status=400)

    return HttpResponseNotAllowed(["POST"])


def request_profile_details(request: HttpRequest) -> HttpResponse:
    authorization = request.headers.get("Authorization")

    if not authorization:
        return JsonResponse({"error": "missing_authorization_header"}, status=401)

    if not authorization.startswith("Bearer "):
        return JsonResponse({"error": "invalid_authorization_header"}, status=401)

    requested_token = authorization.removeprefix("Bearer ").strip()

    auth_token = Token.objects.filter(access_token=requested_token).first()

    if not auth_token:
        return JsonResponse({"error": "invalid_token"}, status=401)

    user = User.objects.filter(username=auth_token.user_name).first()

    if not user:
        return JsonResponse({"error": "user_not_found"}, status=404)

    profile = UserProfile.objects.filter(user=user).first()

    if not profile:
        return JsonResponse({"error": "profile_not_found"}, status=404)

    return JsonResponse({
        "user_name": profile.user.username,
        "learning_goal": profile.learning_goal,
    })


def logout_view(request: HttpRequest) -> HttpResponse:

    logout(request)
    return redirect("/")
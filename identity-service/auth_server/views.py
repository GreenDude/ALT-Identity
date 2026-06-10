import datetime
import uuid

from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone

from .models import AuthCodes

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

            AuthCodes.objects.create(
                user_name = request.user.username,
                client_id = client_id,
                scope = scope,
                expiry = timezone.now() + datetime.timedelta(minutes=5),
                auth_code = auth_code,
            ).save()

            return redirect(f"{redirect_uri}?code={auth_code}")

        else:
            # redirect to login page
            request.session["pending_authorization"] = request.get_full_path()
            return redirect(f"{reverse('login')}")

    else:
        return HttpResponseNotAllowed(["GET"])


def token(request: HttpRequest) -> HttpResponse:

    return HttpResponse("Not implemented", status=500)
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import render, redirect


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
            next_url = request.GET.get("next")
            if next_url:
                return redirect(next_url)

            return redirect("/")
        else:
            return render(request, "auth_server/login.html", {"form": form})

    else:
        return HttpResponseNotAllowed(["GET", "POST"])


# Create your views here.
def authorize(request: HttpRequest) -> HttpResponse:
    client_id = request.GET.get("client_id")
    redirect_uri = request.GET.get("redirect_uri")
    response_type = request.GET.get("response_type")

    if request.method == "GET":
        if request.user.is_authenticated:
            pass
            # Authorized -> redirect page

            # Not authorized -> Grant permission page

        else:
            pass


        pass
    elif request.method == "POST":

        pass
    return HttpResponse("Not implemented", status=500)


def token(request: HttpRequest) -> HttpResponse:

    return HttpResponse("Not implemented", status=500)
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def login(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        # render login page
        pass
    if request.method == "POST":
        # process the request form
        pass

    return HttpResponse("Not implemented", status=500)


# Create your views here.
def authorize(request: HttpRequest) -> HttpResponse:
    client_id = request.GET.get("client_id")
    redirect_uri = request.GET.get("redirect_uri")
    response_code = request.GET.get("response_code")

    if request.method == "GET":
        if 'sessionid' in request.COOKIES:
            pass
            # Authorized -> redirect page

            # Not authorized -> Grant permission page

        else:
            pass


        pass
    elif request.method == "POST":

        pass
    return HttpResponse("Not implemented", status=500)


# Purely for example. TODO: Remove when done with view implementation
def check_session_cookie(request):
    # Check if the 'sessionid' cookie exists in the request
    if 'sessionid' in request.COOKIES:
        session_key = request.COOKIES['sessionid']
        return HttpResponse(f"Session cookie found! ID: {session_key}")
    else:
        return HttpResponse("No session cookie present.")

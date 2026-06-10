from django.http import HttpRequest, HttpResponse
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
    auth_code = request.GET.get('code')
    return HttpResponse(f"Auth Code: {auth_code}")
    # create new session
    # exchange auth_code for tokens
    # store tokens in db

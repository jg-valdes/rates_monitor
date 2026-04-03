import hmac

from django.conf import settings
from django.core import signing
from django.shortcuts import redirect

EXEMPT_PATHS = {"/login/", "/logout/"}


class PasscodeMiddleware:
    """
    Blocks all views unless a valid signed cookie is present.
    Disabled when ACCESS_PASSCODE is not set (development convenience).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        passcode = getattr(settings, "ACCESS_PASSCODE", "")
        if not passcode:
            return self.get_response(request)

        if request.path in EXEMPT_PATHS or request.path.startswith("/admin/"):
            return self.get_response(request)

        token = request.COOKIES.get("rm_access")
        if token:
            try:
                signing.loads(token, max_age=86400)
                return self.get_response(request)
            except (signing.BadSignature, signing.SignatureExpired):
                pass

        next_url = request.get_full_path()
        return redirect(f"/login/?next={next_url}")

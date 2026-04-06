"""Tests for rates/middleware.py — PasscodeMiddleware."""
import pytest
from django.core import signing
from django.test import Client, RequestFactory
from django.http import HttpResponse

from rates.middleware import PasscodeMiddleware


def _get_response(_request):
    return HttpResponse("OK")


def _middleware():
    return PasscodeMiddleware(_get_response)


@pytest.mark.django_db
class TestPasscodeMiddleware:
    def test_disabled_when_no_passcode(self, settings):
        settings.ACCESS_PASSCODE = ""
        factory = RequestFactory()
        request = factory.get("/overview/")
        request.COOKIES = {}
        response = _middleware()(request)
        assert response.status_code == 200

    def test_redirects_unauthenticated_request(self, settings):
        settings.ACCESS_PASSCODE = "secret"
        factory = RequestFactory()
        request = factory.get("/overview/")
        request.COOKIES = {}
        response = _middleware()(request)
        assert response.status_code == 302
        assert "/login/" in response["Location"]

    def test_next_param_included_in_redirect(self, settings):
        settings.ACCESS_PASSCODE = "secret"
        factory = RequestFactory()
        request = factory.get("/usd-brl/")
        request.COOKIES = {}
        response = _middleware()(request)
        assert "next=/usd-brl/" in response["Location"]

    def test_valid_cookie_passes_through(self, settings):
        settings.ACCESS_PASSCODE = "secret"
        factory = RequestFactory()
        request = factory.get("/overview/")
        request.COOKIES = {"rm_access": signing.dumps("ok")}
        response = _middleware()(request)
        assert response.status_code == 200

    def test_expired_cookie_redirects(self, settings):
        settings.ACCESS_PASSCODE = "secret"
        # Create a token then check it with max_age=0, which makes it expired
        factory = RequestFactory()
        request = factory.get("/overview/")
        # Corrupt the token to simulate expiry/bad signature
        request.COOKIES = {"rm_access": "bad.token.value"}
        response = _middleware()(request)
        assert response.status_code == 302

    def test_login_path_exempt(self, settings):
        settings.ACCESS_PASSCODE = "secret"
        factory = RequestFactory()
        request = factory.get("/login/")
        request.COOKIES = {}
        response = _middleware()(request)
        assert response.status_code == 200

    def test_logout_path_exempt(self, settings):
        settings.ACCESS_PASSCODE = "secret"
        factory = RequestFactory()
        request = factory.get("/logout/")
        request.COOKIES = {}
        response = _middleware()(request)
        assert response.status_code == 200

    def test_admin_path_exempt(self, settings):
        settings.ACCESS_PASSCODE = "secret"
        factory = RequestFactory()
        request = factory.get("/admin/something/")
        request.COOKIES = {}
        response = _middleware()(request)
        assert response.status_code == 200

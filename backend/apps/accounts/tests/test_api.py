from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_token_login_me_logout_flow(settings):
    settings.AUTH_TOKEN_TTL_SECONDS = 3 * 60 * 60
    user = get_user_model().objects.create_user(username="alice", password="strong-pass-123")
    client = APIClient()
    login = client.post(reverse("auth-login"), {"username": "alice", "password": "strong-pass-123"})
    assert login.status_code == 200
    assert login.json()["user"] == {"id": user.id, "username": "alice", "is_staff": False}
    assert login.json()["expires_in"] == 10800
    assert login.json()["expires_at"]
    token = login.json()["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    assert client.get(reverse("auth-me")).json()["username"] == "alice"
    assert client.post(reverse("auth-logout")).status_code == 204
    assert client.get(reverse("auth-me")).status_code == 401


@pytest.mark.django_db
def test_private_endpoint_rejects_anonymous_access():
    assert APIClient().get(reverse("watchlist")).status_code == 401


@pytest.mark.django_db
def test_register_creates_isolated_user_and_returns_token():
    response = APIClient().post(
        reverse("auth-register"),
        {
            "username": "new-user",
            "password": "A-strong-password-90210",
            "password_confirm": "A-strong-password-90210",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["token"]
    user = get_user_model().objects.get(username="new-user")
    assert user.check_password("A-strong-password-90210")


@pytest.mark.django_db
def test_expired_token_is_rejected_and_deleted(settings):
    settings.AUTH_TOKEN_TTL_SECONDS = 3 * 60 * 60
    user = get_user_model().objects.create_user(username="expired", password="strong-pass-123")
    token = Token.objects.create(user=user)
    Token.objects.filter(pk=token.pk).update(created=timezone.now() - timedelta(hours=3, seconds=1))

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    response = client.get(reverse("auth-me"))

    assert response.status_code == 401
    assert not Token.objects.filter(key=token.key).exists()


@pytest.mark.django_db
def test_login_rotates_an_expired_token(settings):
    settings.AUTH_TOKEN_TTL_SECONDS = 3 * 60 * 60
    user = get_user_model().objects.create_user(username="renewed", password="strong-pass-123")
    old_token = Token.objects.create(user=user)
    Token.objects.filter(pk=old_token.pk).update(
        created=timezone.now() - timedelta(hours=3, seconds=1)
    )

    response = APIClient().post(
        reverse("auth-login"), {"username": "renewed", "password": "strong-pass-123"}
    )

    assert response.status_code == 200
    assert response.json()["token"] != old_token.key
    assert response.json()["expires_in"] == 10800


@pytest.mark.django_db
def test_register_rejects_duplicate_username_and_mismatched_passwords():
    get_user_model().objects.create_user(username="Existing", password="A-strong-password-90210")
    client = APIClient()
    duplicate = client.post(
        reverse("auth-register"),
        {
            "username": "existing",
            "password": "A-strong-password-90210",
            "password_confirm": "A-strong-password-90210",
        },
        format="json",
    )
    mismatch = client.post(
        reverse("auth-register"),
        {
            "username": "another-user",
            "password": "A-strong-password-90210",
            "password_confirm": "not-the-same-password",
        },
        format="json",
    )
    assert duplicate.status_code == 400
    assert mismatch.status_code == 400

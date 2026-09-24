"""Authentication on the built-in django.contrib.auth views."""

import pytest
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import User
from django.db import connection
from django.urls import reverse


def login_errors(client, username, password):
    """Submit the login form and return the non-field errors."""
    response = client.post(
        reverse("login"), {"username": username, "password": password}
    )
    assert response.status_code == 200
    return list(response.context["form"].non_field_errors())


def test_login_page_is_public(client):
    response = client.get(reverse("login"))

    assert response.status_code == 200
    assert "registration/login.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_login_success_redirects_to_home(client, plain_user, password):
    response = client.post(
        reverse("login"),
        {"username": plain_user.username, "password": password},
    )

    assert response.status_code == 302
    assert response.url == reverse("home")
    assert client.session[SESSION_KEY] == str(plain_user.pk)


@pytest.mark.django_db
def test_login_with_wrong_password_fails(client, plain_user):
    errors = login_errors(client, plain_user.username, "wrong-password")

    assert errors
    assert SESSION_KEY not in client.session


@pytest.mark.django_db
def test_login_error_does_not_leak_whether_user_exists(client, plain_user):
    """The message is identical for an unknown login and a wrong password."""
    unknown_user_errors = login_errors(client, "no-such-user", "wrong-password")
    wrong_password_errors = login_errors(client, plain_user.username, "wrong-password")

    assert unknown_user_errors == wrong_password_errors
    assert plain_user.username not in " ".join(unknown_user_errors)


@pytest.mark.django_db
def test_inactive_user_cannot_login(client, plain_user, password):
    plain_user.is_active = False
    plain_user.save(update_fields=["is_active"])

    errors = login_errors(client, plain_user.username, password)

    assert errors == login_errors(client, "no-such-user", "wrong-password")
    assert SESSION_KEY not in client.session


@pytest.mark.django_db
def test_password_is_stored_hashed(settings, password):
    """auth_user stores a hash, not the password. Uses the real hasher."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
    user = User.objects.create_user(username="hashcheck", password=password)

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT password FROM auth_user WHERE username = %s",
            [user.username],
        )
        stored = cursor.fetchone()[0]

    assert password not in stored
    assert stored.startswith("pbkdf2_sha256$")
    assert check_password(password, stored)


@pytest.mark.django_db
def test_logout_clears_session(client, plain_user):
    client.force_login(plain_user)

    response = client.post(reverse("logout"))

    assert response.status_code == 302
    assert response.url == reverse("login")
    assert SESSION_KEY not in client.session


@pytest.mark.django_db
def test_home_requires_login(client):
    response = client.get(reverse("home"))

    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next={reverse('home')}"


@pytest.mark.django_db
def test_home_shows_username_and_roles(client, plain_user):
    client.force_login(plain_user)

    response = client.get(reverse("home"))

    assert response.status_code == 200
    content = response.content.decode()
    assert plain_user.username in content
    assert "user" in content
    # A regular user does not see the link to the panel.
    assert reverse("panel:user_list") not in content


@pytest.mark.django_db
def test_create_user_never_stores_plaintext(password):
    user = User.objects.create_user(username="temp", password=password)

    assert user.password != password
    assert user.check_password(password)

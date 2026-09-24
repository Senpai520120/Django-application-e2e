"""File manager views: access, limits, and path safety."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

FILE_URLS = [
    ("files:browse", {}),
    ("files:rename", {"path": "anything"}),
    ("files:delete", {"path": "anything"}),
    ("files:download", {"path": "anything.txt"}),
]


@pytest.fixture
def file_root(tmp_path, settings):
    """Each test works in its own folder, so leftovers never travel between tests."""
    settings.FILE_MANAGER = {
        **settings.FILE_MANAGER,
        "BACKEND": "local",
        "ROOT": str(tmp_path / "storage"),
    }
    return tmp_path / "storage"


@pytest.fixture
def user_client(client, plain_user, file_root):
    client.force_login(plain_user)
    return client


def browse(client, path=""):
    return client.get(reverse("files:browse"), {"path": path} if path else {})


@pytest.mark.django_db
@pytest.mark.parametrize(("url_name", "params"), FILE_URLS)
def test_anonymous_is_redirected_to_login(client, file_root, url_name, params):
    url = reverse(url_name)

    response = client.get(url, params)

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_anonymous_cannot_post(client, file_root):
    for url_name in ("files:folder_create", "files:upload"):
        response = client.post(reverse(url_name), {"path": "", "name": "hack"})

        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_logged_in_user_sees_empty_root(user_client):
    response = browse(user_client)

    assert response.status_code == 200
    assert response.context["entries"] == []
    assert "Folder is empty" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path", ["../etc/passwd", "/etc/passwd", "docs/../../secret", "c:/windows"]
)
def test_traversal_in_query_gives_400(user_client, path):
    """A path leading outside is a bad request, not a 500 and not silent access."""
    response = browse(user_client, path)

    assert response.status_code == 400


@pytest.mark.django_db
def test_create_folder_and_enter_it(user_client):
    response = user_client.post(
        reverse("files:folder_create"), {"path": "", "name": "docs"}, follow=True
    )

    assert response.status_code == 200
    assert [entry.name for entry in response.context["entries"]] == ["docs"]

    inside = browse(user_client, "docs")
    assert inside.status_code == 200
    assert inside.context["crumbs"] == [("docs", "docs")]


@pytest.mark.django_db
def test_duplicate_folder_shows_error(user_client):
    user_client.post(reverse("files:folder_create"), {"path": "", "name": "docs"})

    response = user_client.post(
        reverse("files:folder_create"), {"path": "", "name": "docs"}, follow=True
    )

    assert response.status_code == 200
    messages = [str(message) for message in response.context["messages"]]
    assert any("already exists" in message for message in messages)


@pytest.mark.django_db
def test_folder_with_traversal_name_is_rejected(user_client):
    response = user_client.post(
        reverse("files:folder_create"), {"path": "", "name": "../escape"}, follow=True
    )

    assert response.status_code == 200
    assert response.context["entries"] == []
    assert [str(message) for message in response.context["messages"]]


@pytest.mark.django_db
def test_upload_file(user_client):
    payload = SimpleUploadedFile("notes.txt", b"hello world")

    response = user_client.post(
        reverse("files:upload"), {"path": "", "files": payload}, follow=True
    )

    assert response.status_code == 200
    assert [entry.name for entry in response.context["entries"]] == ["notes.txt"]


@pytest.mark.django_db
def test_upload_several_files_at_once(user_client):
    response = user_client.post(
        reverse("files:upload"),
        {
            "path": "",
            "files": [
                SimpleUploadedFile("one.txt", b"1"),
                SimpleUploadedFile("two.txt", b"2"),
            ],
        },
        follow=True,
    )

    assert sorted(entry.name for entry in response.context["entries"]) == [
        "one.txt",
        "two.txt",
    ]


@pytest.mark.django_db
def test_upload_over_the_limit_is_refused(user_client, settings):
    settings.FILE_MANAGER = {**settings.FILE_MANAGER, "MAX_FILE_SIZE": 10}
    payload = SimpleUploadedFile("big.bin", b"x" * 50)

    response = user_client.post(
        reverse("files:upload"), {"path": "", "files": payload}, follow=True
    )

    assert response.status_code == 200
    assert response.context["entries"] == []
    messages = [str(message) for message in response.context["messages"]]
    assert any("larger than the allowed" in message for message in messages)


@pytest.mark.django_db
def test_upload_over_total_limit_is_refused(user_client, settings):
    settings.FILE_MANAGER = {**settings.FILE_MANAGER, "MAX_TOTAL_SIZE": 5}
    payload = SimpleUploadedFile("big.bin", b"x" * 50)

    response = user_client.post(
        reverse("files:upload"), {"path": "", "files": payload}, follow=True
    )

    assert response.context["entries"] == []
    messages = [str(message) for message in response.context["messages"]]
    assert any("storage limit" in message for message in messages)


@pytest.mark.django_db
def test_download_returns_attachment(user_client):
    user_client.post(
        reverse("files:upload"),
        {"path": "", "files": SimpleUploadedFile("notes.txt", b"payload")},
    )

    response = user_client.get(reverse("files:download"), {"path": "notes.txt"})

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment;")
    assert b"".join(response.streaming_content) == b"payload"


@pytest.mark.django_db
def test_executable_upload_is_served_as_attachment(user_client):
    """A dangerous extension is served as an attachment, not run by the browser."""
    user_client.post(
        reverse("files:upload"),
        {
            "path": "",
            "files": SimpleUploadedFile("payload.html", b"<script>x</script>"),
        },
    )

    response = user_client.get(reverse("files:download"), {"path": "payload.html"})

    assert response["Content-Disposition"].startswith("attachment;")


@pytest.mark.django_db
def test_download_of_folder_is_404(user_client):
    user_client.post(reverse("files:folder_create"), {"path": "", "name": "docs"})

    response = user_client.get(reverse("files:download"), {"path": "docs"})

    assert response.status_code == 404


@pytest.mark.django_db
def test_rename_file(user_client):
    user_client.post(
        reverse("files:upload"),
        {"path": "", "files": SimpleUploadedFile("old.txt", b"data")},
    )

    response = user_client.post(
        reverse("files:rename"), {"path": "old.txt", "new_name": "new.txt"}, follow=True
    )

    assert [entry.name for entry in response.context["entries"]] == ["new.txt"]


@pytest.mark.django_db
def test_rename_page_shows_current_name(user_client):
    user_client.post(reverse("files:folder_create"), {"path": "", "name": "docs"})

    response = user_client.get(reverse("files:rename"), {"path": "docs"})

    assert response.status_code == 200
    assert response.context["name"] == "docs"
    assert response.context["is_dir"] is True


@pytest.mark.django_db
def test_delete_asks_for_confirmation_first(user_client):
    user_client.post(
        reverse("files:upload"),
        {"path": "", "files": SimpleUploadedFile("notes.txt", b"data")},
    )

    confirm = user_client.get(reverse("files:delete"), {"path": "notes.txt"})

    assert confirm.status_code == 200
    # GET deletes nothing, the file is still there.
    assert [entry.name for entry in browse(user_client).context["entries"]] == [
        "notes.txt"
    ]

    deleted = user_client.post(
        reverse("files:delete"), {"path": "notes.txt"}, follow=True
    )

    assert deleted.context["entries"] == []


@pytest.mark.django_db
def test_delete_folder_removes_content(user_client):
    user_client.post(reverse("files:folder_create"), {"path": "", "name": "docs"})
    user_client.post(
        reverse("files:upload"),
        {"path": "docs", "files": SimpleUploadedFile("inner.txt", b"data")},
    )

    response = user_client.post(reverse("files:delete"), {"path": "docs"}, follow=True)

    assert response.context["entries"] == []


@pytest.mark.django_db
def test_delete_warns_that_folder_is_removed_with_content(user_client):
    user_client.post(reverse("files:folder_create"), {"path": "", "name": "docs"})

    response = user_client.get(reverse("files:delete"), {"path": "docs"})

    assert "with everything inside" in response.content.decode()


@pytest.mark.django_db
def test_delete_of_missing_path_is_404(user_client):
    response = user_client.get(reverse("files:delete"), {"path": "nope.txt"})

    assert response.status_code == 404

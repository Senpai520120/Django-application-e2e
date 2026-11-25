"""File manager views: access, limits, and path safety."""

import duckdb
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.uploadhandler import TemporaryFileUploadHandler
from django.urls import reverse

from files.models import GroupingRule
from files.pipeline import AGGREGATIONS

FILE_URLS = [
    ("files:browse", {}),
    ("files:rename", {"path": "anything"}),
    ("files:delete", {"path": "anything"}),
    ("files:download", {"path": "anything.txt"}),
]


@pytest.fixture
def file_root(tmp_path, settings):
    """Each test works in its own folder, so leftovers never travel between tests."""
    settings.STORAGES = {
        **settings.STORAGES,
        "filemanager": {
            "BACKEND": "files.storage.LocalFileStorage",
            "OPTIONS": {"location": str(tmp_path / "storage")},
        },
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
def test_oversized_upload_never_reaches_the_disk(user_client, settings, monkeypatch):
    """The limit stops a file while it arrives, not after it was written."""
    settings.FILE_MANAGER = {**settings.FILE_MANAGER, "MAX_FILE_SIZE": 10}
    settings.FILE_UPLOAD_MAX_MEMORY_SIZE = 0  # every upload goes to a temp file
    written = []
    original = TemporaryFileUploadHandler.receive_data_chunk

    def counting(self, raw_data, start):
        written.append(len(raw_data))
        return original(self, raw_data, start)

    monkeypatch.setattr(TemporaryFileUploadHandler, "receive_data_chunk", counting)

    user_client.post(
        reverse("files:upload"),
        {"path": "", "files": SimpleUploadedFile("big.bin", b"x" * 50)},
    )

    assert written == []


@pytest.mark.django_db
def test_one_oversized_file_refuses_the_whole_batch(user_client, settings):
    settings.FILE_MANAGER = {**settings.FILE_MANAGER, "MAX_FILE_SIZE": 10}
    files = [
        SimpleUploadedFile("small.txt", b"ok"),
        SimpleUploadedFile("big.bin", b"x" * 50),
    ]

    response = user_client.post(
        reverse("files:upload"), {"path": "", "files": files}, follow=True
    )

    assert response.context["entries"] == []
    messages = [str(message) for message in response.context["messages"]]
    assert any("big.bin is larger than the allowed" in m for m in messages)


@pytest.mark.django_db
def test_upload_without_files_asks_for_one(user_client):
    response = user_client.post(reverse("files:upload"), {"path": ""}, follow=True)

    messages = [str(message) for message in response.context["messages"]]
    assert any("required" in message for message in messages)


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
def test_rename_of_missing_path_is_404(user_client):
    """The same answer as the delete page gives: nothing there, nothing to rename."""
    response = user_client.get(reverse("files:rename"), {"path": "nope.txt"})

    assert response.status_code == 404


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


TOKEN = "pipeline-token"

SEO = (
    b"query,device,clicks,impressions,ctr\n"
    b"django,mobile,12,300,0.04\n"
    b"django,desktop,9,150,0.06\n"
    b"airflow,mobile,7,120,\n"
)


@pytest.fixture
def pipeline_on(settings):
    settings.PIPELINE_API_TOKEN = TOKEN


def rules():
    return {
        rule.path: (rule.group_by, rule.aggregations, rule.configured)
        for rule in GroupingRule.objects.all()
    }


def upload(client, path, *files):
    return client.post(
        reverse("files:upload"), {"path": path, "files": list(files)}, follow=True
    )


def grouping(client, path, **data):
    """POST the grouping page; `aggregations` is a list of "op:index"."""
    return client.post(reverse("files:grouping"), {"path": path, **data}, follow=True)


# --- upload: a draft rule, then the grouping page ---


@pytest.mark.django_db
def test_table_upload_makes_a_draft_and_opens_the_grouping_page(
    user_client, pipeline_on
):
    user_client.post(reverse("files:folder_create"), {"path": "", "name": "reports"})

    response = upload(user_client, "reports", SimpleUploadedFile("seo.csv", SEO))

    assert rules() == {"reports/seo.csv": ("", [], False)}
    assert response.redirect_chain[-1][0] == (
        reverse("files:grouping") + "?path=reports%2Fseo.csv"
    )
    page = response.content.decode()
    assert "Uploaded files: 1." in page
    assert [row["name"] for row in response.context["rows"]] == [
        "query",
        "device",
        "clicks",
        "impressions",
        "ctr",
    ]


@pytest.mark.django_db
def test_several_table_files_stay_in_the_list(user_client, pipeline_on):
    response = upload(
        user_client,
        "",
        SimpleUploadedFile("a.csv", SEO),
        SimpleUploadedFile("b.csv", SEO),
    )

    assert response.redirect_chain[-1][0] == reverse("files:browse")
    assert "Grouping next to it" in response.content.decode()
    assert rules() == {"a.csv": ("", [], False), "b.csv": ("", [], False)}
    statuses = [row["grouping"] for row in response.context["rows"]]
    assert statuses == ["waiting for a grouping column"] * 2


@pytest.mark.django_db
def test_rule_has_the_name_the_file_is_stored_under(user_client, pipeline_on):
    upload(user_client, "", SimpleUploadedFile("my sales.csv", SEO))

    assert list(rules()) == ["my_sales.csv"]


@pytest.mark.django_db
def test_other_uploads_get_no_rule(user_client, pipeline_on):
    response = upload(user_client, "", SimpleUploadedFile("notes.txt", b"hello"))

    assert rules() == {}
    assert response.redirect_chain[-1][0] == reverse("files:browse")


@pytest.mark.django_db
def test_no_rules_without_the_pipeline(user_client, settings):
    settings.PIPELINE_API_TOKEN = ""

    upload(user_client, "", SimpleUploadedFile("sales.csv", SEO))

    assert rules() == {}


@pytest.mark.django_db
def test_refused_upload_keeps_the_old_rule(user_client, pipeline_on):
    upload(user_client, "", SimpleUploadedFile("sales.csv", SEO))
    grouping(user_client, "sales.csv", group_by="device")

    response = upload(user_client, "", SimpleUploadedFile("sales.csv", b"other"))

    assert rules() == {"sales.csv": ("device", [], True)}
    assert "already exists" in response.content.decode()


# --- the grouping page ---


@pytest.mark.django_db
def test_grouping_page_offers_the_file_columns(user_client, pipeline_on):
    upload(user_client, "", SimpleUploadedFile("seo.csv", SEO))

    response = user_client.get(reverse("files:grouping"), {"path": "seo.csv"})

    rows = {row["name"]: row for row in response.context["rows"]}
    # The first text column is the suggestion, as in the DAG.
    assert [name for name, row in rows.items() if row["group_checked"]] == ["query"]

    def allowed(name):
        return [cell["op"] for cell in rows[name]["cells"] if cell["allowed"]]

    assert allowed("device") == ["count"]
    assert allowed("clicks") == ["sum", "avg", "min", "max", "count"]
    page = response.content.decode()
    assert 'aria-label="sum of clicks"' in page
    assert 'aria-label="sum of device"' not in page
    assert "how much in total" in page


@pytest.mark.django_db
def test_saving_the_grouping_configures_the_rule(user_client, pipeline_on):
    upload(user_client, "", SimpleUploadedFile("seo.csv", SEO))

    response = grouping(
        user_client,
        "seo.csv",
        group_by="device",
        # clicks is column 2, impressions 3, query 0.
        aggregations=["avg:3", "sum:2", "count:0"],
    )

    # Stored in table order: by column, then by op.
    assert rules() == {
        "seo.csv": (
            "device",
            [
                {"op": "count", "column": "query"},
                {"op": "sum", "column": "clicks"},
                {"op": "avg", "column": "impressions"},
            ],
            True,
        )
    }
    assert response.redirect_chain[-1][0] == reverse("files:browse")
    page = response.content.decode()
    assert (
        "seo.csv will be grouped by device with count(query), sum(clicks), "
        "avg(impressions) within a minute."
    ) in page
    assert response.context["rows"][0]["grouping"] == (
        "by device, count(query), sum(clicks), avg(impressions)"
    )


@pytest.mark.django_db
def test_grouping_page_shows_the_saved_choice(user_client, pipeline_on):
    upload(user_client, "", SimpleUploadedFile("seo.csv", SEO))
    grouping(user_client, "seo.csv", group_by="device", aggregations=["max:2"])

    response = user_client.get(reverse("files:grouping"), {"path": "seo.csv"})

    rows = {row["name"]: row for row in response.context["rows"]}
    assert rows["device"]["group_checked"]
    checked = [
        (name, cell["op"])
        for name, row in rows.items()
        for cell in row["cells"]
        if cell["checked"]
    ]
    assert checked == [("clicks", "max")]


@pytest.mark.django_db
def test_changing_the_grouping_updates_the_rule(user_client, pipeline_on):
    upload(user_client, "", SimpleUploadedFile("seo.csv", SEO))
    grouping(user_client, "seo.csv", group_by="device", aggregations=["sum:2"])

    grouping(user_client, "seo.csv", group_by="query", aggregations=[])

    assert rules() == {"seo.csv": ("query", [], True)}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "data",
    [
        # sum of a text column is not offered, so not accepted either.
        {"group_by": "device", "aggregations": ["sum:1"]},
        # A column the file does not have.
        {"group_by": "price", "aggregations": []},
        {"group_by": "device", "aggregations": ["sum:99"]},
        # Anything but "op:index" of the file.
        {"group_by": "device", "aggregations": ['sum"); DROP TABLE x; --:2']},
        {"group_by": "device", "aggregations": ["median:2"]},
        # No column chosen.
        {"aggregations": ["sum:2"]},
    ],
)
def test_bad_choices_are_refused(user_client, pipeline_on, data):
    upload(user_client, "", SimpleUploadedFile("seo.csv", SEO))

    response = grouping(user_client, "seo.csv", **data)

    assert response.status_code == 200
    assert response.context["form"].errors
    assert rules() == {"seo.csv": ("", [], False)}


@pytest.mark.django_db
def test_too_many_aggregations_are_refused(user_client, pipeline_on):
    upload(user_client, "", SimpleUploadedFile("seo.csv", SEO))
    every = [f"{op}:{index}" for index in (2, 3, 4) for op in AGGREGATIONS]

    response = grouping(user_client, "seo.csv", group_by="device", aggregations=every)

    assert "At most 10 aggregations." in response.content.decode()
    assert not GroupingRule.objects.get().configured


@pytest.mark.django_db
def test_every_table_format_offers_its_columns(user_client, pipeline_on, tmp_path):
    with duckdb.connect() as con:
        con.execute("INSTALL excel")
        con.execute("LOAD excel")
        con.execute(
            "CREATE TABLE t AS SELECT * FROM (VALUES ('books', 10)) v(category, qty)"
        )
        for ext, options in [
            ("json", "FORMAT json, ARRAY true"),
            ("parquet", "FORMAT parquet"),
            ("xlsx", "FORMAT xlsx, HEADER true"),
        ]:
            con.execute(f"COPY t TO '{tmp_path / ('t.' + ext)}' ({options})")
    for ext in ("json", "parquet", "xlsx"):
        payload = SimpleUploadedFile(f"t.{ext}", (tmp_path / f"t.{ext}").read_bytes())

        response = upload(user_client, "", payload)

        kinds = [(row["name"], row["kind"]) for row in response.context["rows"]]
        assert kinds == [("category", "text"), ("qty", "number")], ext


@pytest.mark.django_db
def test_broken_table_file_says_so(user_client, pipeline_on):
    upload(user_client, "", SimpleUploadedFile("broken.parquet", b"not parquet"))

    response = user_client.get(reverse("files:grouping"), {"path": "broken.parquet"})

    assert response.status_code == 422
    assert "cannot be read as a table" in response.content.decode()
    assert not GroupingRule.objects.get().configured


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["", "nope.csv", "notes.txt", "docs"])
def test_grouping_page_is_only_for_existing_table_files(user_client, pipeline_on, path):
    upload(user_client, "", SimpleUploadedFile("notes.txt", b"hello"))
    user_client.post(reverse("files:folder_create"), {"path": "", "name": "docs"})

    response = user_client.get(reverse("files:grouping"), {"path": path})

    assert response.status_code == 404


@pytest.mark.django_db
def test_grouping_page_is_off_without_the_pipeline(user_client, settings):
    settings.PIPELINE_API_TOKEN = ""
    upload(user_client, "", SimpleUploadedFile("seo.csv", SEO))

    response = user_client.get(reverse("files:grouping"), {"path": "seo.csv"})

    assert response.status_code == 404


@pytest.mark.django_db
def test_anonymous_cannot_open_the_grouping_page(client, file_root, pipeline_on):
    response = client.get(reverse("files:grouping"), {"path": "seo.csv"})

    assert response.status_code == 302
    assert "login" in response["Location"]


@pytest.mark.django_db
def test_file_list_links_table_files_to_their_grouping(user_client, pipeline_on):
    upload(user_client, "", SimpleUploadedFile("notes.txt", b"hello"))
    upload(user_client, "", SimpleUploadedFile("seo.csv", SEO))

    page = user_client.get(reverse("files:browse")).content.decode()

    assert 'aria-label="Grouping seo.csv"' in page
    assert 'aria-label="Grouping notes.txt"' not in page
    assert "waiting for a grouping column" in page


# --- rules follow their file ---


@pytest.mark.django_db
def test_rename_takes_the_rule_along(user_client, pipeline_on):
    upload(user_client, "", SimpleUploadedFile("a.csv", SEO))
    grouping(user_client, "a.csv", group_by="device")

    user_client.post(reverse("files:rename"), {"path": "a.csv", "new_name": "b.csv"})

    assert rules() == {"b.csv": ("device", [], True)}


@pytest.mark.django_db
def test_renamed_folder_takes_the_rules_of_its_files(user_client, pipeline_on):
    user_client.post(reverse("files:folder_create"), {"path": "", "name": "q1"})
    user_client.post(reverse("files:folder_create"), {"path": "", "name": "q10"})
    upload(user_client, "q1", SimpleUploadedFile("a.csv", SEO))
    upload(user_client, "q10", SimpleUploadedFile("b.csv", SEO))

    user_client.post(reverse("files:rename"), {"path": "q1", "new_name": "spring"})

    assert set(rules()) == {"spring/a.csv", "q10/b.csv"}


@pytest.mark.django_db
def test_delete_removes_the_rules(user_client, pipeline_on):
    user_client.post(reverse("files:folder_create"), {"path": "", "name": "q1"})
    upload(user_client, "q1", SimpleUploadedFile("a.csv", SEO))
    upload(user_client, "", SimpleUploadedFile("b.csv", SEO))

    user_client.post(reverse("files:delete"), {"path": "q1"})

    assert set(rules()) == {"b.csv"}


# --- the rules API ---


def get_rules(client, **headers):
    return client.get(reverse("files:grouping_rules"), headers=headers)


@pytest.mark.django_db
def test_rules_api_gives_every_rule_to_the_right_token(client, pipeline_on):
    GroupingRule.objects.create(
        path="reports/sales.csv",
        group_by="category",
        aggregations=[{"op": "sum", "column": "qty"}],
        configured=True,
    )
    GroupingRule.objects.create(path="seo.csv")

    response = get_rules(client, authorization=f"Bearer {TOKEN}")

    assert response.status_code == 200
    assert response.json() == [
        {
            "path": "reports/sales.csv",
            "group_by": "category",
            "aggregations": [{"op": "sum", "column": "qty"}],
            "configured": True,
            "revision": 0,
        },
        # A draft is sent too, so Airflow knows to wait for it.
        {
            "path": "seo.csv",
            "group_by": "",
            "aggregations": [],
            "configured": False,
            "revision": 0,
        },
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "header", [None, "Bearer wrong", f"Basic {TOKEN}", TOKEN, "Bearer "]
)
def test_rules_api_refuses_without_the_token(client, pipeline_on, header):
    headers = {"authorization": header} if header is not None else {}

    response = get_rules(client, **headers)

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"


@pytest.mark.django_db
def test_rules_api_is_off_without_a_token_setting(client, settings):
    settings.PIPELINE_API_TOKEN = ""

    assert get_rules(client, authorization="Bearer ").status_code == 404


@pytest.mark.django_db
def test_table_file_rules_are_shown_when_processing_is_on(user_client, pipeline_on):
    page = user_client.get(reverse("files:browse")).content.decode()

    assert 'data-testid="table-rules"' in page
    assert "<code>.xlsx</code>" in page


@pytest.mark.django_db
def test_table_file_rules_are_hidden_without_processing(user_client, settings):
    settings.PIPELINE_API_TOKEN = ""

    page = user_client.get(reverse("files:browse")).content.decode()

    assert 'data-testid="table-rules"' not in page


# --- edge cases found by comparing with another implementation ---


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["../seo.csv", "a/../../seo.csv"])
def test_grouping_page_refuses_paths_outside_the_store(user_client, pipeline_on, path):
    upload(user_client, "", SimpleUploadedFile("seo.csv", SEO))

    response = user_client.get(reverse("files:grouping"), {"path": path})

    # files.paths refuses it before any storage call, as on every other page.
    assert response.status_code == 400


@pytest.mark.django_db
def test_table_file_without_a_rule_can_be_configured(user_client, settings):
    # Uploaded while grouping was off: the file has no rule at all.
    settings.PIPELINE_API_TOKEN = ""
    upload(user_client, "", SimpleUploadedFile("seo.csv", SEO))
    settings.PIPELINE_API_TOKEN = TOKEN

    page = user_client.get(reverse("files:grouping"), {"path": "seo.csv"})
    grouping(user_client, "seo.csv", group_by="device", aggregations=["sum:2"])

    assert page.status_code == 200
    assert rules() == {"seo.csv": ("device", [{"op": "sum", "column": "clicks"}], True)}


@pytest.mark.django_db
def test_rules_api_is_one_query_however_many_rules(
    client, pipeline_on, django_assert_num_queries
):
    for number in range(5):
        GroupingRule.objects.create(
            path=f"f{number}.csv",
            group_by="city",
            aggregations=[{"op": "sum", "column": "qty"}],
            configured=True,
        )

    # The aggregations live in the rule's own row: no query per rule.
    with django_assert_num_queries(1):
        response = get_rules(client, authorization=f"Bearer {TOKEN}")

    assert len(response.json()) == 5


# --- review fixes: retry on a second save, files with no rule wait ---


@pytest.mark.django_db
def test_saving_the_same_grouping_again_makes_a_new_revision(user_client, pipeline_on):
    upload(user_client, "", SimpleUploadedFile("seo.csv", SEO))

    grouping(user_client, "seo.csv", group_by="device")
    first = GroupingRule.objects.get().revision
    response = grouping(user_client, "seo.csv", group_by="device")

    # Nothing changed but the revision: that is what makes Airflow retry a
    # file that failed, so the "within a minute" message holds.
    assert GroupingRule.objects.get().revision == first + 1
    assert "will be grouped by device" in response.content.decode()


@pytest.mark.django_db
def test_table_file_renamed_from_text_waits_for_a_grouping(user_client, pipeline_on):
    upload(user_client, "", SimpleUploadedFile("report.txt", SEO))

    user_client.post(
        reverse("files:rename"), {"path": "report.txt", "new_name": "report.csv"}
    )
    page = user_client.get(reverse("files:browse")).content.decode()

    # No rule: Airflow skips it, and the list says it waits for a choice.
    assert rules() == {}
    assert "waiting for a grouping column" in page

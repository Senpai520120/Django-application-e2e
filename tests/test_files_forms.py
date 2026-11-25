"""File manager forms checked directly, without a view in between.

The view tests prove the forms are wired in; these pin down the edges the
mutation run showed nobody checked: exact size limits, the file name a browser
sends with a whole path, the error texts the user reads, and the grouping
page's starting choice.
"""

from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.defaultfilters import filesizeformat
from django.test import override_settings
from django.utils.datastructures import MultiValueDict

from files.forms import FolderForm, GroupingForm, RenameForm, UploadForm
from files.paths import MAX_NAME_LENGTH
from files.pipeline import MAX_AGGREGATIONS

LIMIT = 10


def upload(*files, oversized=(), path=""):
    form = UploadForm(
        data={"path": path},
        files=MultiValueDict({"files": list(files)}),
        oversized=oversized,
    )
    form.is_valid()
    return form


def a_file(name, size=1):
    return SimpleUploadedFile(name, b"x" * size)


def test_path_field_is_optional_and_reports_why_a_path_is_bad():
    assert FolderForm(data={"name": "docs"}).is_valid()

    form = FolderForm(data={"path": "/etc", "name": "docs"})
    assert not form.is_valid()
    assert form.errors["path"] == ["Absolute paths are not allowed."]

    assert not RenameForm(data={"new_name": "b"}).is_valid()


def test_name_field_strips_limits_and_reports_why_a_name_is_bad():
    form = FolderForm(data={"name": "  report  "})
    assert form.is_valid()
    assert form.cleaned_data["name"] == "report"

    assert form.fields["name"].max_length == MAX_NAME_LENGTH
    too_long = FolderForm(data={"name": "x" * (MAX_NAME_LENGTH + 1)})
    assert not too_long.is_valid()

    bad = FolderForm(data={"name": "a<b"})
    assert not bad.is_valid()
    assert bad.errors["name"] == ["The name contains forbidden characters."]


@override_settings(FILE_MANAGER={"MAX_FILE_SIZE": LIMIT})
def test_upload_accepts_a_file_of_exactly_the_limit():
    form = upload(a_file("a.txt", LIMIT), a_file("b.txt"))
    assert form.is_valid()
    assert [f.name for f in form.cleaned_data["files"]] == ["a.txt", "b.txt"]


@override_settings(FILE_MANAGER={"MAX_FILE_SIZE": LIMIT})
def test_upload_rejects_a_file_one_byte_over_the_limit():
    form = upload(a_file("a.txt"), a_file("big.txt", LIMIT + 1))
    assert form.errors["files"] == [
        f"File big.txt is larger than the allowed {filesizeformat(LIMIT)}."
    ]


@override_settings(FILE_MANAGER={"MAX_FILE_SIZE": LIMIT})
def test_upload_names_the_file_dropped_while_arriving():
    form = upload(oversized=["huge.iso"])
    assert form.errors["files"] == [
        f"File huge.iso is larger than the allowed {filesizeformat(LIMIT)}."
    ]


def test_upload_without_files_is_required():
    form = upload()
    assert form.errors.as_data()["files"][0].code == "required"


@pytest.mark.parametrize(
    "name", ["C:\\Users\\me\\report.csv", "folder/report.csv", "report.csv"]
)
def test_upload_checks_only_the_last_part_of_a_browser_path(name):
    assert upload(a_file(name)).is_valid()


def test_upload_says_which_file_has_a_bad_name():
    form = upload(a_file("ok.txt"), a_file("con.txt"))
    assert form.errors["files"] == [
        "File con.txt: The name 'con.txt' is reserved by the system."
    ]


SCHEMA = [("amount", "DOUBLE"), ("city", "VARCHAR"), ("note", "varchar")]


def grouping(data, schema=SCHEMA):
    form = GroupingForm(data={"path": "t.csv", **data}, schema=schema)
    form.is_valid()
    return form


def test_grouping_requires_a_column_with_its_own_message():
    form = grouping({})
    assert form.errors["group_by"] == ["Choose the column to group by."]
    assert form.fields["aggregations"].required is False


def test_grouping_keeps_table_order_up_to_the_limit():
    schema = [(f"n{i}", "BIGINT") for i in range(3)]
    chosen = [f"{op}:{i}" for i in range(3) for op in ("sum", "max", "min", "avg")]
    exactly = grouping(
        {"group_by": "n0", "aggregations": chosen[:MAX_AGGREGATIONS]}, schema
    )
    assert exactly.is_valid(), exactly.errors
    # Sent as sum, max, min, avg; kept in the order of AGGREGATIONS.
    assert exactly.cleaned_data["aggregations"][:4] == [
        {"op": op, "column": "n0"} for op in ("sum", "avg", "min", "max")
    ]

    over = grouping(
        {"group_by": "n0", "aggregations": chosen[: MAX_AGGREGATIONS + 1]}, schema
    )
    assert over.errors["aggregations"] == [f"At most {MAX_AGGREGATIONS} aggregations."]


def rule(group_by="city", aggregations=None, configured=True):
    return SimpleNamespace(
        group_by=group_by, aggregations=aggregations or [], configured=configured
    )


def test_initial_choice_starts_from_the_first_text_column():
    assert GroupingForm.initial_for(SCHEMA, None) == {
        "group_by": "city",
        "aggregations": [],
    }
    numbers = [("a", "BIGINT"), ("b", "DOUBLE")]
    assert GroupingForm.initial_for(numbers, None)["group_by"] == "a"
    assert GroupingForm.initial_for([], None)["group_by"] == ""
    # An unconfigured rule or a column that is gone falls back the same way.
    unconfigured = rule("note", configured=False)
    assert GroupingForm.initial_for(SCHEMA, unconfigured)["group_by"] == "city"
    assert GroupingForm.initial_for(SCHEMA, rule("gone"))["group_by"] == "city"


def test_initial_choice_shows_the_saved_rule_and_skips_broken_items():
    saved = [
        {"op": "sum", "column": "amount"},
        {"op": "count", "column": "note"},
        {"op": "drop", "column": "amount"},
        {"op": "sum", "column": "gone"},
        "not a dict",
    ]
    assert GroupingForm.initial_for(SCHEMA, rule("note", saved)) == {
        "group_by": "note",
        "aggregations": ["sum:0", "count:2"],
    }
    broken = rule("note", aggregations=None)
    broken.aggregations = "sum:amount"
    assert GroupingForm.initial_for(SCHEMA, broken)["aggregations"] == []

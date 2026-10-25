"""What the landscape pages do with a bundle (`v1-e39-t17` ac3, data-use policy E39 gate item 11).

* **Five minutes.** Through the real `S3EvidenceObjectStore` over a moto bucket, a deleted school view
  and a republished report each show on the pages once the shelf is five minutes old, and not
  before; no older snapshot's view is ever shown in a deleted one's place. A bucket that stops
  answering after five minutes gives 503, never the old bundle.
* **Untrusted text.** Raw HTML in a bundle is escaped; a `javascript:` link, a `data:` image, an
  off-site link, a bare address and a team page in `report.md` are text, and so is a team-page
  address on another caselist, or one the team-page rule would not build, in `schools.md`.
* **The audit.** Each page view writes one `landscape-viewed` record, naming the page's kind and
  its bundle's caselist and snapshot, and never a school, team code or position. A record that
  cannot be written stops the page.
* **The logs.** No log record the app writes, at any level, holds a school's anchor, a position id,
  a school or a team code (the PM's condition on putting a school's anchor in a path).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Final

import boto3
import pytest
from moto import mock_aws

from debate_core.application.tub.audit import AuditAction
from debate_core.domain.landscape_pages import LandscapePage
from debate_core.integrations.s3 import S3EvidenceObjectStore

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

BUCKET: Final = "debate-test-evidence-landscape"
NEWEST: Final = "reports/landscape/synthpolicy26/2026-10-20"
SCHOOL_VIEW: Final = "/landscape/synthpolicy26/schools"
NEITHER_SIDE: Final = "/landscape/synthpolicy26/report/neither-side"
JUST_UNDER_FIVE_MINUTES: Final = timedelta(minutes=4, seconds=59)
_STANDARD_RECORD_FIELDS: Final = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)))


@pytest.fixture
def bucket(monkeypatch: pytest.MonkeyPatch, landscape_files: dict[str, bytes]) -> Iterator[S3Client]:
    """A versioned moto bucket holding the synthetic bundles, under fake credentials and no profile."""
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_EC2_METADATA_DISABLED": "true",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        client.create_bucket(Bucket=BUCKET)
        client.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
        for key, content in landscape_files.items():
            client.put_object(Bucket=BUCKET, Key=key, Body=content)
        yield client


@pytest.fixture
def over_moto(bucket: S3Client, make_world: Any) -> Iterator[Any]:
    world = make_world(landscape_objects=S3EvidenceObjectStore(bucket=BUCKET, client=bucket))
    world.signed_in_student()
    yield world
    world.services.search_index.close()


@pytest.fixture
def student(world: Any) -> Any:
    world.signed_in_student()
    return world


def body(world: Any, path: str) -> tuple[int, str]:
    response = world.browser.get(path)
    return response.status_code, response.text.split('<main id="main">', 1)[1].split("</main>", 1)[0]


def with_files(make_world: Any, landscape_store: Any, files: dict[str, bytes], **changes: str) -> Any:
    """A signed-in world whose bucket holds `files` with each named file's text replaced."""
    planted = dict(files)
    for name, text in changes.items():
        planted[f"{NEWEST}/{name.replace('_', '.')}"] = text.encode()
    world = make_world(landscape_objects=landscape_store(planted))
    world.signed_in_student()
    return world


# --------------------------------------------------------------------------------------------
# Held no longer than five minutes, in a moto bucket
# --------------------------------------------------------------------------------------------


def test_a_deleted_school_view_shows_within_five_minutes_and_no_older_view_replaces_it(
    over_moto: Any, bucket: S3Client
) -> None:
    assert body(over_moto, "/landscape/synthpolicy26/schools/ashgrove")[0] == 200

    bucket.delete_object(Bucket=BUCKET, Key=f"{NEWEST}/schools.md")
    over_moto.clock.advance(JUST_UNDER_FIVE_MINUTES)
    held_status, held = body(over_moto, SCHOOL_VIEW)
    over_moto.clock.advance(timedelta(seconds=1))
    status, removed = body(over_moto, SCHOOL_VIEW)
    school_status, school = body(over_moto, "/landscape/synthpolicy26/schools/ashgrove")
    listing = body(over_moto, "/landscape")[1]

    assert (held_status, "Ashgrove" in held) == (200, True)
    assert status == 200
    assert "<h1>No positions by school this week</h1>" in removed
    assert "Oldfield" not in removed and "2026-10-13" not in removed
    assert (school_status, "Ashgrove" in school, "Oldfield" in school) == (404, False, False)
    assert "/landscape/synthpolicy26/schools" not in listing


def test_a_republished_report_shows_within_five_minutes(over_moto: Any, bucket: S3Client) -> None:
    assert "2 of 10 cards were not placed." in body(over_moto, NEITHER_SIDE)[1]

    republished = (
        "# Argument landscape: synthpolicy26 through 2026-10-20\n\n## Unclassified\n\n"
        "3 of 11 cards were not placed after the republish.\n"
    )
    bucket.put_object(Bucket=BUCKET, Key=f"{NEWEST}/report.md", Body=republished.encode())
    over_moto.clock.advance(JUST_UNDER_FIVE_MINUTES)
    held = body(over_moto, NEITHER_SIDE)[1]
    over_moto.clock.advance(timedelta(seconds=1))
    fresh = body(over_moto, "/landscape/synthpolicy26")[1]
    gone_status, gone = body(over_moto, NEITHER_SIDE)

    assert "2 of 10 cards were not placed." in held
    # The republished report has no # parts, so it is all front page, and the old part is gone.
    assert "3 of 11 cards were not placed after the republish." in fresh
    assert "2 of 10" not in fresh
    assert gone_status == 404 and "2 of 10" not in gone


def test_a_newer_snapshot_replaces_the_one_shown_within_five_minutes(
    over_moto: Any, bucket: S3Client
) -> None:
    assert "through 2026-10-20" in body(over_moto, "/landscape")[1]
    newer = "# Argument landscape: synthpolicy26 through 2026-10-27\n\n## Overviews\n\nThe newer week.\n"
    bucket.put_object(
        Bucket=BUCKET, Key="reports/landscape/synthpolicy26/2026-10-27/report.md", Body=newer.encode()
    )
    over_moto.clock.advance(JUST_UNDER_FIVE_MINUTES)
    held = body(over_moto, "/landscape")[1]
    over_moto.clock.advance(timedelta(seconds=1))
    status, view = body(over_moto, SCHOOL_VIEW)

    assert "through 2026-10-20" in held and "2026-10-27" not in held
    assert "through 2026-10-27" in body(over_moto, "/landscape")[1]
    # The newer snapshot has no schools.md yet, so its view is none: the older one's is not shown.
    assert status == 200 and "No positions by school this week" in view and "Ashgrove" not in view


def test_the_bucket_is_listed_once_in_five_minutes_and_an_unchanged_bundle_is_not_read_again(
    student: Any,
) -> None:
    objects = student.landscape_objects
    for path in ("/landscape", "/landscape/synthpolicy26", SCHOOL_VIEW, "/landscape/synthld26"):
        assert student.browser.get(path).status_code == 200
    first_reads = list(objects.reads)
    student.clock.advance(timedelta(minutes=5))
    assert student.browser.get("/landscape").status_code == 200

    assert objects.listings == 2
    assert sorted(first_reads) == [
        "reports/landscape/synthld26/2026-10-19/report.md",
        "reports/landscape/synthpolicy26/2026-10-20/report.md",
        "reports/landscape/synthpolicy26/2026-10-20/schools.md",
    ]
    assert objects.reads == first_reads


def test_a_bucket_that_stops_answering_after_five_minutes_gives_no_page_not_the_old_bundle(
    student: Any,
) -> None:
    assert student.browser.get("/landscape/synthpolicy26").status_code == 200
    student.landscape_objects.failing = True
    student.clock.advance(JUST_UNDER_FIVE_MINUTES)
    held = student.browser.get("/landscape/synthpolicy26")
    student.clock.advance(timedelta(seconds=1))
    gone = student.browser.get("/landscape/synthpolicy26")

    assert held.status_code == 200
    assert gone.status_code == 503
    assert "The landscape reports are not available right now" in gone.text
    assert "Invented DA" not in gone.text


# --------------------------------------------------------------------------------------------
# A bundle's text is untrusted
# --------------------------------------------------------------------------------------------

PLANTED_REPORT: Final = """# Argument landscape: synthpolicy26 through 2026-10-20

## About this report

<script>alert("planted")</script>

A paragraph with <img src="x" onerror="alert(1)"> and <a href="https://evil.example/raw">raw</a> in it.

[run this](javascript:alert(1)) and [also this](JAVASCRIPT:alert(2))

![a planted pixel](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk)

[somewhere else](https://evil.example/landing) and <https://evil.example/autolink> and https://evil.example/bare

[a team page](https://opencaselist.com/synthpolicy26/Ashgrove/AB) and [a missing heading](#nowhere)
"""

PLANTED_SCHOOL_VIEW: Final = """# Positions by school: synthpolicy26 through 2026-10-20

<b onmouseover="alert(1)">planted</b>

## By school

### Ashgrove <script>alert(3)</script>

| Team code | Side | Position | Rounds | Team page |
|---|---|---|---|---|
| AB | neg | `invented-da` | 1 | [another caselist](https://opencaselist.com/otherpolicy26/Ashgrove/AB) |
| AB | neg | `invented-da` | 1 | [a deeper path](https://opencaselist.com/synthpolicy26/Ashgrove/AB/rounds) |
| AB | neg | `invented-da` | 1 | [the real one](https://opencaselist.com/synthpolicy26/Ashgrove/AB) |

## By position

### Disadvantages

#### `invented-da`

| School | Team code | Side | Rounds | Team page |
|---|---|---|---|---|
| Ashgrove | AB | neg | 1 | [another caselist](https://opencaselist.com/otherpolicy26/Ashgrove/AB) |
| Ashgrove | AB | neg | 1 | [with a query](https://opencaselist.com/synthpolicy26/Ashgrove/AB?x=1) |
| Birch Hollow | CD | neg | 1 | [a display name](https://opencaselist.com/synthpolicy26/Birch%20Hollow/CD) |
| Ashgrove | AB | neg | 1 | [a deeper path](https://opencaselist.com/synthpolicy26/Ashgrove/AB/rounds) |
| Ashgrove | AB | neg | 1 | [plain http](http://opencaselist.com/synthpolicy26/Ashgrove/AB) |
| Ashgrove | AB | neg | 1 | [the real one](https://opencaselist.com/synthpolicy26/Ashgrove/AB) |
"""


def test_raw_html_in_a_bundle_is_escaped_never_markup(
    make_world: Any, landscape_store: Any, landscape_files: dict[str, bytes]
) -> None:
    world = with_files(
        make_world, landscape_store, landscape_files, report_md=PLANTED_REPORT, schools_md=PLANTED_SCHOOL_VIEW
    )
    pages = {
        path: world.browser.get(path).text
        for path in (
            "/landscape/synthpolicy26",
            SCHOOL_VIEW,
            "/landscape/synthpolicy26/schools/ashgrove-scriptalert3script",
        )
    }

    report, front, school = pages.values()
    assert "&lt;script&gt;alert(&quot;planted&quot;)&lt;/script&gt;" in report
    assert "&lt;img src=&quot;x&quot; onerror=&quot;alert(1)&quot;&gt;" in report
    assert "&lt;b onmouseover=&quot;alert(1)&quot;&gt;planted&lt;/b&gt;" in front
    assert "<h1>Ashgrove &lt;script&gt;alert(3)&lt;/script&gt;</h1>" in school
    for text in pages.values():
        assert re.findall(r"<script\b[^>]*>", text) == [
            f'<script src="{world.app.state.pilot.app_script.path}" defer>'
        ]
        assert "<img" not in text and "<b " not in text
        assert re.search(r"\son[a-z]+=", "".join(re.findall(r"<[a-zA-Z][^>]*>", text))) is None
    world.services.search_index.close()


def test_every_link_but_a_same_page_heading_is_text_in_the_report(
    make_world: Any, landscape_store: Any, landscape_files: dict[str, bytes]
) -> None:
    world = with_files(make_world, landscape_store, landscape_files, report_md=PLANTED_REPORT)
    report = body(world, "/landscape/synthpolicy26")[1].split('<div class="landscape-body">', 1)[1]

    assert re.findall(r'<a href="([^"]*)"', report) == []
    assert "[run this](javascript:alert(1))" in report
    assert "[also this](JAVASCRIPT:alert(2))" in report
    assert "a planted pixel" in report and "data:image" not in report
    assert "somewhere else and https://evil.example/autolink and https://evil.example/bare" in report
    assert "a team page and a missing heading" in report
    world.services.search_index.close()


def test_a_team_page_link_the_rule_would_not_build_is_text_in_the_school_view(
    make_world: Any, landscape_store: Any, landscape_files: dict[str, bytes]
) -> None:
    world = with_files(make_world, landscape_store, landscape_files, schools_md=PLANTED_SCHOOL_VIEW)
    position = body(world, "/landscape/synthpolicy26/positions/invented-da")[1]
    school = body(world, "/landscape/synthpolicy26/schools/ashgrove-scriptalert3script")[1]

    assert re.findall(r'<a href="([^"]*)"', position) == [
        "/landscape/synthpolicy26/schools",
        "https://opencaselist.com/synthpolicy26/Ashgrove/AB",
    ]
    for words in ("another caselist", "with a query", "a display name", "a deeper path", "plain http"):
        assert f"<td>{words}</td>" in position, words
    assert "otherpolicy26" not in position and "?x=1" not in position
    # The by-school table's team page column is checked by the same rule (`v1-e32-t23`).
    assert re.findall(r'<a href="([^"]*)"', school) == [
        "/landscape/synthpolicy26/schools",
        "https://opencaselist.com/synthpolicy26/Ashgrove/AB",
    ]
    for words in ("another caselist", "a deeper path"):
        assert f"<td>{words}</td>" in school, words
    assert "otherpolicy26" not in school and "/rounds" not in school
    world.services.search_index.close()


# --------------------------------------------------------------------------------------------
# The audit
# --------------------------------------------------------------------------------------------

EXPECTED_RECORDS: Final = [
    ("/landscape", {"page": "caselists"}),
    ("/landscape/synthpolicy26", {"page": "report", "caselist": "synthpolicy26", "snapshot": "2026-10-20"}),
    (
        "/landscape/synthpolicy26/report/negative",
        {"page": "report-part", "caselist": "synthpolicy26", "snapshot": "2026-10-20"},
    ),
    (SCHOOL_VIEW, {"page": "school-view", "caselist": "synthpolicy26", "snapshot": "2026-10-20"}),
    (
        "/landscape/synthpolicy26/schools/birch-hollow-2",
        {"page": "school", "caselist": "synthpolicy26", "snapshot": "2026-10-20"},
    ),
    (
        "/landscape/synthpolicy26/positions/invented-da",
        {"page": "position", "caselist": "synthpolicy26", "snapshot": "2026-10-20"},
    ),
    (
        "/landscape/synthld26/schools",
        {"page": "school-view", "caselist": "synthld26", "snapshot": "2026-10-19"},
    ),
]


@pytest.mark.parametrize(("path", "named"), EXPECTED_RECORDS, ids=[path for path, _ in EXPECTED_RECORDS])
def test_each_page_view_writes_one_record_of_its_kind_and_bundle_and_nothing_else(
    student: Any, path: str, named: dict[str, str]
) -> None:
    session = student.session_cookie()
    before = len(student.audit.records)

    assert student.browser.get(path).status_code == 200
    written = student.audit.records[before:]

    assert [record.action for record in written] == [AuditAction.LANDSCAPE_VIEWED]
    assert json.loads(written[0].to_json()) == {
        "format_version": 1,
        "time": "2026-11-02T15:00:00Z",
        "action": "landscape-viewed",
        "actor_role": "student",
        "actor_subject": session.subject,
        **named,
    }


def test_no_record_names_a_school_team_code_or_position(student: Any) -> None:
    for path, _ in EXPECTED_RECORDS:
        student.browser.get(path)
    lines = [record.to_json() for record in student.audit.records]

    assert len(lines) == len(EXPECTED_RECORDS)
    for line in lines:
        values = [str(value) for value in json.loads(line).values()]
        for word in (
            "ashgrove",
            "birch",
            "invented",
            '"ab"',
            '"ef"',
            '"cd"',
            "schools/",
            "positions/",
            "negative",
        ):
            assert all(word not in value.lower() for value in values), (word, line)


@pytest.mark.parametrize(
    "path",
    [
        "/landscape/nocaselist26",
        "/landscape/synthpolicy26/schools/oldfield",
        "/landscape/synthpolicy26/positions/no-such-position",
        "/landscape/synthpolicy26/report/no-such-part",
    ],
)
def test_a_page_not_in_the_newest_bundle_writes_no_record(student: Any, path: str) -> None:
    assert student.browser.get(path).status_code == 404
    assert [record.action for record in student.audit.records] == []


@pytest.mark.parametrize("path", [path for path, _ in EXPECTED_RECORDS])
def test_a_record_that_cannot_be_written_stops_the_page(student: Any, path: str) -> None:
    student.audit.failing = True

    response = student.browser.get(path)

    assert response.status_code == 503
    assert "The landscape reports are not available right now" in response.text
    assert "synthpolicy26 through" not in response.text and "<td>" not in response.text


def test_the_record_kind_is_the_pages_and_its_bundle_is_the_one_shown(student: Any) -> None:
    student.browser.get("/landscape/synthpolicy26/schools/ashgrove")
    record = student.audit.records[-1]

    assert (record.page, record.caselist, record.snapshot) == (
        LandscapePage.SCHOOL,
        "synthpolicy26",
        date(2026, 10, 20),
    )


# --------------------------------------------------------------------------------------------
# The logs
# --------------------------------------------------------------------------------------------


def test_no_log_record_at_any_level_holds_a_school_anchor_position_id_school_or_team_code(
    over_moto: Any, bucket: S3Client, caplog: pytest.LogCaptureFixture
) -> None:
    paths = [path for path, _ in EXPECTED_RECORDS] + [
        "/landscape/synthpolicy26/schools/ashgrove",
        "/landscape/synthpolicy26/schools/birch-hollow",
        "/landscape/synthpolicy26/positions/invented-aff",
        "/landscape/synthpolicy26/schools/oldfield",
    ]
    with caplog.at_level(logging.NOTSET):
        logging.getLogger().setLevel(logging.NOTSET)
        for path in paths:
            over_moto.browser.get(path)
        bucket.delete_object(Bucket=BUCKET, Key=f"{NEWEST}/schools.md")
        over_moto.clock.advance(timedelta(minutes=5))
        over_moto.browser.get("/landscape/synthpolicy26/schools/birch-hollow-2")

    # httpx's own records are the test client's requests, made in this process: the app cannot log
    # through httpx, which an import contract keeps out of debate_api.
    logged = [
        " ".join(
            [record.name, record.getMessage()]
            + [f"{key}={value}" for key, value in vars(record).items() if key not in _STANDARD_RECORD_FIELDS]
        )
        for record in caplog.records
        if not record.name.startswith(("httpx", "httpcore"))
    ]
    assert any(record.name.startswith("botocore") for record in caplog.records), "botocore logged nothing"
    forbidden = [
        "ashgrove",
        "birch-hollow",
        "birch hollow",
        "oldfield",
        "invented-da",
        "invented-aff",
        "|ab|",
        " ab ",
        " ef ",
    ]
    for line in logged:
        for word in forbidden:
            assert word not in line.lower(), (word, line[:300])

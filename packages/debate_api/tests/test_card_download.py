"""Download .docx and the download cart, through the app's route (`v1-e39-t08`).

The criteria: ac1 (a downloaded card re-parses as its source), ac2 (the cart cap, a refused card's
message, and dropping it to build the rest), ac3 (download off on a parser mismatch; one audit record
per download), ac5 (a cart too large for the buffered response is refused before building), ac6 and
ac7 (no provenance line; a camp card from its `raw/openev/2026` store) and ac8 (a card suppressed
after its page was rendered, and an audit record that cannot be written, both refuse the download).

Every download goes through the real app, the real index holder and the real E33 writer, over the
synthetic sources of `conftest.py` in recording stores; no test reaches a network. What a file must
hold is written out here by hand from those sources (working agreement 6), never read from a
download.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date, timedelta
from typing import Any, Final, cast
from xml.etree import ElementTree

import pytest

from debate_api.download import DOCX_MEDIA_TYPE
from debate_core.application.card_download import DOWNLOAD_FILE_MAX_BYTES
from debate_core.application.ports.evidence_file_writer import (
    BuiltEvidenceFile,
    CardRefusal,
    CardRefusalCode,
    FileBuildRefusal,
    FileBuildRequest,
)
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.application.tub.audit import AuditAction
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.file_provenance import formatting_sha256
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.testing.search_index import published_index

W: Final = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CASELIST_STORE: Final = "raw/caselist/hsld26"
CAMP_STORE: Final = "raw/openev/2026"

CASELIST_HEADER: Final = (
    "Disclosed cards (FILE_IMPORT) from hsld26, each copied from the file that disclosed it and not "
    "verified by this platform."
)
MIXED_HEADER: Final = (
    "Disclosed and camp cards (FILE_IMPORT) from hsld26 and OpenEv, each copied from its source file and "
    "not verified by this platform."
)
HEADINGS: Final = ["Team evidence search", "Downloaded cards"]

DOWNLOAD_PARAGRAPHS: Final = [
    "Gabbro ridges slow upland erosion",
    "Thorvaldsen 26, Fellow, Synthetic Geology Review, 2026",
    "Upland soils hold behind gabbro ridges a stressed warrant for decades.",
]
"""The `download` card as its source holds it, paragraph by paragraph: tag, cite, evidence."""

CAMP_PARAGRAPHS: Final = [
    "Tuff walls shelter seedlings",
    "Okafor 26, Ecologist, Synthetic Seedling Review, 2026",
    "Seedlings survive behind tuff walls a stressed warrant in dry years.",
]

PROVENANCE_WORDS: Final = (
    "[Disclosed",
    "[OpenEv",
    "Maple Grove",
    "QX",
    "Invented Invitational",
    "Round 4",
    "Cascade Institute",
    "Invented Camp File",
)
"""What a provenance line would put in a file: its brackets, the school, team code, tournament, round,
camp and camp file title the test world's occurrences carry."""

UNAVAILABLE: Final = "The download could not be made right now. Try again in a minute."


@pytest.fixture
def student(world: Any) -> Any:
    world.signed_in_student()
    return world


def paragraphs(docx: bytes) -> list[str]:
    """Every paragraph's text in the file's `word/document.xml`, in order."""
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    return ["".join(text.text or "" for text in paragraph.iter(f"{W}t")) for paragraph in root.iter(f"{W}p")]


def reparsed(world: Any, docx: bytes) -> ParsedDocument:
    """The downloaded file as the E31 parser reads it."""
    document = SourceDocument(
        sha256="0" * 64,
        byte_size=len(docx),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="hsld26",
        first_seen_snapshot=date(2026, 10, 13),
        last_seen_snapshot=date(2026, 10, 13),
    )
    parsed = world.parser().parse(docx, document, source_path="downloaded.docx")
    assert isinstance(parsed, ParsedDocument), parsed
    return parsed


def downloads(world: Any) -> list[Any]:
    return [record for record in world.audit.records if record.action is AuditAction.CARDS_DOWNLOADED]


def source_reads(world: Any) -> dict[str, list[str]]:
    return {prefix: store.reads for prefix, store in world.source_stores.items()}


def suppress(world: Any, name: str, *, whole_source: bool) -> None:
    """A removal of the named card's source, or of its one disclosure, as `caselist remove` appends it."""
    document = next(one for one in world.corpus if one.doc_id == world.cards[name])
    occurrence = document.occurrences[0]
    world.index_source.append_suppression(
        SuppressionEntry(
            action=SuppressionAction.SUPPRESS,
            sha256=occurrence.source_sha256,
            disclosure=None if whole_source else occurrence.disclosure,
            recorded_at=world.clock(),
            reason=ReasonCode.REQUESTED_BY_TEAM,
            request_id="RM-2026-08",
        )
    )


# ------------------------------------------------------------------------------------------------
# ac1 and ac7: one card, through the route, re-parses as its source and carries no provenance line
# ------------------------------------------------------------------------------------------------


def test_download_of_one_card_through_the_route_re_parses_as_its_source(student: Any) -> None:
    response = student.download("download")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == DOCX_MEDIA_TYPE
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="team-evidence-cards-2026-11-02.docx"'
    )
    assert response.headers["cache-control"] == "private, no-store"
    (card,) = reparsed(student, response.content).cards
    source = student.source_card("download")
    assert card.tag == "Gabbro ridges slow upland erosion" == source.tag
    assert card.full_cite == "Thorvaldsen 26, Fellow, Synthetic Geology Review, 2026" == source.full_cite
    assert card.evidence_text == DOWNLOAD_PARAGRAPHS[2] == source.evidence_text
    assert formatting_sha256(card.formatting_spans, card.font_size_spans) == formatting_sha256(
        source.formatting_spans, source.font_size_spans
    )
    assert {emphasis.emphasis.value for emphasis in card.formatting_spans} >= {
        "UNDERLINE",
        "HIGHLIGHT",
        "EMPHASIS",
    }


def test_download_of_one_card_holds_no_provenance_line_and_the_header_without_its_old_sentence(
    student: Any,
) -> None:
    response = student.download("download")

    assert paragraphs(response.content) == [CASELIST_HEADER, *HEADINGS, *DOWNLOAD_PARAGRAPHS]
    text = "\n".join(paragraphs(response.content))
    for word in PROVENANCE_WORDS:
        assert word not in text, word
    assert "below its cite" not in text


def test_download_sends_the_docx_alone_and_never_its_sidecar(student: Any) -> None:
    response = student.download("download")

    assert response.content == student.built[-1]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == [
            "[Content_Types].xml",
            "_rels/.rels",
            "docProps/core.xml",
            "word/_rels/document.xml.rels",
            "word/document.xml",
            "word/settings.xml",
            "word/styles.xml",
        ]
    assert b"provenance_line" not in response.content and b"builder_version" not in response.content


def test_download_reads_only_the_cards_sources_and_writes_nothing(student: Any) -> None:
    student.download("download", "download second")

    assert source_reads(student) == {
        CASELIST_STORE: [student.sources()["disclosed"].sha256],
        CAMP_STORE: [],
    }, "two cards of one source read it once; RecordingSourceStore refuses every write"


# ------------------------------------------------------------------------------------------------
# ac6 and ac7: a camp card, from its raw/openev/<year> store, in a cart with a caselist card
# ------------------------------------------------------------------------------------------------


def test_download_cart_with_a_camp_card_reads_it_from_raw_openev_2026_with_no_provenance_line(
    student: Any,
) -> None:
    response = student.download("download", "camp download")

    assert response.status_code == 200, response.text
    assert source_reads(student) == {
        CASELIST_STORE: [student.sources()["disclosed"].sha256],
        CAMP_STORE: [student.sources()["camp"].sha256],
    }
    assert paragraphs(response.content) == [MIXED_HEADER, *HEADINGS, *DOWNLOAD_PARAGRAPHS, *CAMP_PARAGRAPHS]
    camp = reparsed(student, response.content).cards[1]
    assert (camp.tag, camp.full_cite, camp.evidence_text) == tuple(CAMP_PARAGRAPHS)
    text = "\n".join(paragraphs(response.content))
    for word in PROVENANCE_WORDS:
        assert word not in text, word


# ------------------------------------------------------------------------------------------------
# ac2: the cart cap, a refused card's message, and dropping it to build the rest
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def capped(make_world: Any) -> Any:
    made = make_world(download_card_cap=2)
    made.signed_in_student()
    yield made
    made.services.search_index.close()


def test_cart_over_the_cap_is_refused_before_a_card_is_looked_up_or_a_source_read(capped: Any) -> None:
    response = capped.download("download", "download second", "download other")

    assert response.status_code == 409
    assert response.json() == {
        "message": "A download holds up to 2 cards. Remove some from the cart and try again."
    }
    assert source_reads(capped) == {CASELIST_STORE: [], CAMP_STORE: []}
    assert capped.built == [] and downloads(capped) == []


def test_cart_at_the_cap_downloads(capped: Any) -> None:
    response = capped.download("download", "download other")

    assert response.status_code == 200, response.text
    assert len(reparsed(capped, response.content).cards) == 2


def test_cart_shows_its_cap_on_every_signed_in_page(capped: Any) -> None:
    page = capped.browser.get("/").text

    assert (
        '<section class="cart" data-tub-cart data-tub-cart-cap="2" aria-label="Download cart" hidden>' in page
    )
    assert "in your download cart, up to 2.</p>" in page


def test_cart_naming_a_card_twice_downloads_it_once(student: Any) -> None:
    reference = student.card_reference("download")

    response = student.download(cards=f"{reference},{reference}")

    assert response.status_code == 200
    assert len(reparsed(student, response.content).cards) == 1
    assert [record.cards for record in downloads(student)] == [(reference,)]


@pytest.mark.parametrize(
    "cards",
    [
        "hsld26/not-a-cluster",
        f"hsld26/{27:064x}/extra",
        f"../hsld26/{27:064x}",
        f"HSLD26/{27:064x}",
        f"hsld26/{27:064X}",
        ",".join([f"hsld26/{27:064x}"] * 50),
    ],
    ids=["no-cluster", "extra-part", "dot-dot", "upper-store", "upper-cluster", "too-long"],
)
def test_cart_that_is_not_a_list_of_card_references_is_refused_whole(student: Any, cards: str) -> None:
    response = student.download(cards=cards)

    assert response.status_code == 400
    assert response.json() == {
        "message": "That cart could not be read. Empty the cart and add the cards again."
    }
    assert source_reads(student) == {CASELIST_STORE: [], CAMP_STORE: []}
    assert downloads(student) == []


def test_cart_that_is_empty_or_sent_twice_in_one_body_is_refused(student: Any) -> None:
    empty = student.download(cards="")
    session = student.session_cookie()
    twice = student.post(
        "/download",
        {"cards": student.card_reference("download")},
        csrf_token=session.csrf_token,
    )
    body = f"cards={student.card_reference('download')}&cards={student.card_reference('camp download')}"
    doubled = student.browser.post(
        "/download",
        content=body.encode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRF-Token": session.csrf_token,
            "Origin": student.public_origin,
            "Sec-Fetch-Site": "same-origin",
        },
    )

    assert (empty.status_code, empty.json()["message"]) == (
        400,
        "There is no card to download. Add a card to the cart from its page.",
    )
    assert twice.status_code == 200
    assert doubled.status_code == 400


def test_cart_with_a_refused_card_names_it_with_a_plain_reason_and_builds_nothing(student: Any) -> None:
    response = student.download("download", "picture")

    assert response.status_code == 409
    assert response.json() == {
        "message": "Some cards cannot be downloaded.",
        "refused": [
            {
                "card": student.card_reference("picture"),
                "position": 2,
                "name": "Andesite slopes hold snow",
                "reason": (
                    "It holds a picture, a table, a text box or a footnote that cannot be copied exactly. "
                    "Copy card copies its text."
                ),
            }
        ],
    }
    assert student.built == [] and downloads(student) == []


def test_cart_without_its_refused_card_builds_the_rest(student: Any) -> None:
    refused = student.download("download", "picture", "camp download").json()["refused"]
    dropped = {card["card"] for card in refused}
    rest = [
        name
        for name in ("download", "picture", "camp download")
        if student.card_reference(name) not in dropped
    ]

    response = student.download(*rest)

    assert rest == ["download", "camp download"]
    assert response.status_code == 200
    assert paragraphs(response.content) == [MIXED_HEADER, *HEADINGS, *DOWNLOAD_PARAGRAPHS, *CAMP_PARAGRAPHS]


def test_cart_with_a_card_whose_source_is_lost_names_it(student: Any) -> None:
    response = student.download("lost source", "download")

    assert response.status_code == 409
    assert response.json()["refused"] == [
        {
            "card": student.card_reference("lost source"),
            "position": 1,
            "name": "Rhyolite domes vent slowly",
            "reason": "Its file could not be read. Try again later.",
        }
    ]
    assert downloads(student) == []


def test_download_refused_by_the_writers_read_back_names_the_card(make_world: Any) -> None:
    """READBACK_MISMATCH is the writer's own check: a writer reporting it stands in for one that found it."""

    class ReadBackRefuses:
        async def build(self, request: FileBuildRequest) -> FileBuildRefusal:
            first = request.resolved.cards[1]
            return FileBuildRefusal(
                (CardRefusal(first.path, first.fingerprint, CardRefusalCode.READBACK_MISMATCH, "cite"),)
            )

    world = make_world(download_writer=lambda sources: ReadBackRefuses())
    world.signed_in_student()
    try:
        response = world.download("download", "download other")
    finally:
        world.services.search_index.close()

    assert response.status_code == 409
    assert response.json()["refused"] == [
        {
            "card": world.card_reference("download other"),
            "position": 2,
            "name": "Scoria fields warm faster",
            "reason": (
                "It did not come out exactly as it is in its file, so it was left out. "
                "Copy card copies its text."
            ),
        }
    ]
    assert downloads(world) == []


# ------------------------------------------------------------------------------------------------
# ac3: a parser mismatch switches download off; each download writes one audit record
# ------------------------------------------------------------------------------------------------


def republished(world: Any, path: Any, *, parser_version: str, without: int = 25) -> Any:
    """The world's corpus less one filler, so a new index id, under `parser_version`'s manifest."""
    kept = [document for document in world.corpus if document.doc_id != without]
    sink = SqliteSearchIndexWriter().create(path)
    for document in kept:
        sink.add(document)
    sink.finish()
    stores: dict[str, int] = {}
    for document in kept:
        stores[document.caselist] = stores.get(document.caselist, 0) + 1
    return published_index(path.read_bytes(), documents_by_store=stores, parser_version=parser_version)


def test_download_is_switched_off_with_a_message_when_the_index_was_built_by_another_parser(
    student: Any, tmp_path: Any
) -> None:
    older = republished(student, tmp_path / "older.sqlite", parser_version="2026.10.18-docx-5")
    student.index_source.publish(older)
    student.clock.advance(timedelta(minutes=5))

    response = student.download("download", "camp download")
    page = student.browser.get(student.card_path("download")).text

    assert student.services.search_index.loaded_index_id == older.index_id != student.index.index_id
    assert response.status_code == 503
    assert response.json() == {
        "message": "Download is off until the search's next weekly update. Copy card still works."
    }
    assert source_reads(student) == {CASELIST_STORE: [], CAMP_STORE: []}
    assert student.built == [] and downloads(student) == []
    assert "data-tub-download=" not in page and "data-tub-cart-add=" not in page
    assert (
        '<p class="download-off">Download is off until the search\'s next weekly update. '
        "Copy card still works.</p>"
    ) in page
    assert "data-tub-copy=" in page


def test_download_comes_back_on_when_an_index_of_the_functions_parser_is_published(
    student: Any, tmp_path: Any
) -> None:
    student.index_source.publish(
        republished(student, tmp_path / "older.sqlite", parser_version="2026.10.18-docx-5")
    )
    student.clock.advance(timedelta(minutes=5))
    assert student.download("download").status_code == 503

    student.index_source.publish(
        republished(
            student, tmp_path / "rebuilt.sqlite", parser_version=student.parser().parser_version, without=24
        )
    )
    student.clock.advance(timedelta(minutes=5))

    assert student.download("download").status_code == 200


def test_download_card_page_offers_download_and_the_cart_when_the_parsers_agree(student: Any) -> None:
    page = student.browser.get(student.card_path("download")).text
    reference = student.card_reference("download")

    assert f'<button type="button" data-tub-download="{reference}">Download .docx</button>' in page
    assert (
        f'<button type="button" class="secondary" data-tub-cart-add="{reference}">Add to cart</button>'
        in page
    )
    assert "download-off" not in page


def test_download_writes_one_cards_downloaded_record_naming_every_card_in_order(student: Any) -> None:
    before = len(student.audit.records)

    student.download("camp download", "download")

    written = student.audit.records[before:]
    assert [record.action for record in written] == [AuditAction.CARDS_DOWNLOADED]
    assert written[0].cards == (student.card_reference("camp download"), student.card_reference("download"))
    assert written[0].actor_subject == student.session_cookie().subject
    record = written[0].to_json()
    for word in ("Gabbro", "Tuff", "Maple Grove", "QX", "Thorvaldsen", "team-evidence-cards"):
        assert word not in record, word


def test_download_refused_for_any_reason_writes_no_record(student: Any) -> None:
    student.download("download", "picture")
    student.download(cards="hsld26/not-a-cluster")
    student.download(cards="")

    assert downloads(student) == []


# ------------------------------------------------------------------------------------------------
# ac5: a cart whose file would pass the buffered-response limit, or whose sources are too large to
# read in time, is refused before building
# ------------------------------------------------------------------------------------------------


def test_download_cart_whose_files_pass_the_fetch_ceiling_is_refused_before_building(
    make_world: Any,
) -> None:
    world = make_world()
    sources = world.sources()
    ceiling = len(sources["disclosed"].content) + len(sources["other"].content) - 1
    world.services.search_index.close()
    world = make_world(download_fetch_bytes=ceiling)
    world.signed_in_student()
    try:
        under = world.download("download", "download second")
        over = world.download("download", "download other")
    finally:
        world.services.search_index.close()

    assert under.status_code == 200
    assert over.status_code == 409
    assert over.json() == {
        "message": (
            "These cards come from files too large to read in one download. Download fewer cards at a time, "
            "or a card from a large file on its own."
        )
    }
    assert len(world.built) == 1 and len(downloads(world)) == 1


def test_download_file_built_past_the_buffered_limit_is_refused_and_never_sent(make_world: Any) -> None:
    """The estimate is an upper bound for every measured card; a writer past it anyway is still caught."""

    class TooLarge:
        async def build(self, request: FileBuildRequest) -> BuiltEvidenceFile:
            return BuiltEvidenceFile(
                docx=b"x" * (DOWNLOAD_FILE_MAX_BYTES + 1), manifest=cast(Any, None), manifest_json=b""
            )

    world = make_world(download_writer=lambda sources: TooLarge())
    world.signed_in_student()
    try:
        response = world.download("download")
    finally:
        world.services.search_index.close()

    assert response.status_code == 409
    assert response.json()["message"] == (
        "These cards would make a file too large to download at once. Download fewer cards at a time."
    )
    assert downloads(world) == []


# ------------------------------------------------------------------------------------------------
# ac8: a card suppressed after its page was rendered is refused and named; an unwritten record
# refuses the download
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("whole_source", [True, False], ids=["its-source", "its-disclosure"])
def test_download_of_a_card_suppressed_after_its_page_was_rendered_is_refused_and_named(
    student: Any, whole_source: bool
) -> None:
    page = student.browser.get(student.card_path("download")).text
    assert f'data-tub-download="{student.card_reference("download")}"' in page

    suppress(student, "download", whole_source=whole_source)
    student.clock.advance(timedelta(minutes=5))
    response = student.download("camp download", "download")

    assert response.status_code == 409
    assert response.json() == {
        "message": "Some cards cannot be downloaded.",
        "refused": [
            {
                "card": student.card_reference("download"),
                "position": 2,
                "name": None,
                "reason": "It is no longer in the search.",
            }
        ],
    }
    assert source_reads(student) == {CASELIST_STORE: [], CAMP_STORE: []}
    assert student.built == [] and downloads(student) == []


def test_download_without_the_suppressed_card_builds_the_rest(student: Any) -> None:
    suppress(student, "download", whole_source=True)
    student.clock.advance(timedelta(minutes=5))

    response = student.download("camp download")

    assert response.status_code == 200
    assert paragraphs(response.content)[3:] == CAMP_PARAGRAPHS


def test_download_whose_audit_record_cannot_be_written_is_refused_and_sends_no_file(student: Any) -> None:
    student.audit.failing = True

    response = student.download("download")

    assert response.status_code == 503
    assert response.json() == {"message": UNAVAILABLE}
    assert response.headers["content-type"] == "application/json"
    assert len(student.built) == 1, "the file was built, and then not sent"
    assert downloads(student) == []


def test_download_while_the_suppression_list_cannot_be_read_is_refused(student: Any) -> None:
    from debate_core.application.errors import StoreUnavailable

    student.index_source.suppression_list_failure = StoreUnavailable("GetObject", "list", "synthetic outage")
    student.clock.advance(timedelta(minutes=5))

    response = student.download("download")

    assert (response.status_code, response.json()) == (503, {"message": UNAVAILABLE})
    assert student.built == []


# ------------------------------------------------------------------------------------------------
# The gate's rules hold for the download as for every POST
# ------------------------------------------------------------------------------------------------


def test_download_without_the_sessions_csrf_token_is_refused_by_the_gate(student: Any) -> None:
    response = student.download("download", csrf_token="not-the-sessions-token")

    assert response.status_code == 403
    assert student.built == []


def test_download_logs_no_card_reference_tag_or_cite(student: Any, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG")

    student.download("download", "camp download")
    student.download("download", "picture")

    logged = "\n".join(
        record.getMessage() for record in caplog.records if not record.name.startswith(("httpx", "httpcore"))
    )
    for word in ("gabbro", "andesite", "tuff", "thorvaldsen", "maple grove", f"{27:064x}"):
        assert word not in logged.lower(), word
    assert not re.search(r"[0-9a-f]{64}", logged)


# ------------------------------------------------------------------------------------------------
# The body as sent, and the two download settings
# ------------------------------------------------------------------------------------------------


def _post_body(world: Any, body: str) -> Any:
    session = world.session_cookie()
    return world.browser.post(
        "/download",
        content=body.encode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRF-Token": session.csrf_token,
            "Origin": world.public_origin,
            "Sec-Fetch-Site": "same-origin",
        },
    )


def test_download_body_longer_than_any_cart_is_refused_unread(student: Any) -> None:
    body = f"cards={student.card_reference('download')}&padding={'p' * 4096}"

    response = _post_body(student, body)

    assert response.status_code == 400
    assert source_reads(student) == {CASELIST_STORE: [], CAMP_STORE: []}


def test_download_body_with_more_fields_than_a_download_sends_is_refused_not_failed(student: Any) -> None:
    response = _post_body(student, f"cards={student.card_reference('download')}&a=1&b=2")

    assert (response.status_code, response.json()["message"]) == (
        400,
        "That cart could not be read. Empty the cart and add the cards again.",
    )


def test_download_cart_whose_files_are_exactly_the_fetch_ceiling_downloads(make_world: Any) -> None:
    probe = make_world()
    sources = probe.sources()
    probe.services.search_index.close()
    world = make_world(download_fetch_bytes=len(sources["disclosed"].content) + len(sources["other"].content))
    world.signed_in_student()
    try:
        response = world.download("download", "download other")
    finally:
        world.services.search_index.close()

    assert response.status_code == 200


REQUIRED_ENVIRONMENT: Final = {
    "TUB_ENVIRONMENT": "dev",
    "TUB_PUBLIC_ORIGIN": "https://tub.example.test",
    "TUB_LOGIN_ORIGIN": "https://auth.tub.example.test",
    "TUB_USER_POOL_ID": "us-east-1_SyntheticPool",
    "TUB_CLIENT_ID": "synthetic-client-id",
    "TUB_CLIENT_SECRET_PARAMETER": "/debate-dev-tub/client-secret",
    "TUB_COOKIE_KEYS_PARAMETER": "/debate-dev-tub/cookie-keys",
    "TUB_AUDIT_LOG_GROUP": "debate-dev-tub-audit",
    "TUB_EVIDENCE_BUCKET": "debate-dev-evidence-synthetic",
}


@pytest.mark.parametrize(
    ("variable", "value", "expected"),
    [
        ("TUB_DOWNLOAD_CARD_CAP", None, 8),
        ("TUB_DOWNLOAD_CARD_CAP", "", 8),
        ("TUB_DOWNLOAD_CARD_CAP", "1", 1),
        ("TUB_DOWNLOAD_CARD_CAP", " 30 ", 30),
        ("TUB_DOWNLOAD_SOURCE_XML_BYTES", None, 20_000_000),
        ("TUB_DOWNLOAD_SOURCE_XML_BYTES", "3500000", 3_500_000),
    ],
)
def test_download_caps_are_read_from_the_environment(variable: str, value: str | None, expected: int) -> None:
    from debate_api.configuration import PilotConfiguration

    environ = dict(REQUIRED_ENVIRONMENT)
    if value is not None:
        environ[variable] = value
    configuration = PilotConfiguration.from_environment(environ)

    read = {
        "TUB_DOWNLOAD_CARD_CAP": configuration.download_card_cap,
        "TUB_DOWNLOAD_SOURCE_XML_BYTES": configuration.download_source_xml_bytes,
    }
    assert read[variable] == expected


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("TUB_DOWNLOAD_CARD_CAP", "0"),
        ("TUB_DOWNLOAD_CARD_CAP", "31"),
        ("TUB_DOWNLOAD_CARD_CAP", "eight"),
        ("TUB_DOWNLOAD_CARD_CAP", "-1"),
        ("TUB_DOWNLOAD_SOURCE_XML_BYTES", "0"),
        ("TUB_DOWNLOAD_SOURCE_XML_BYTES", "2e6"),
        ("TUB_DOWNLOAD_SOURCE_XML_BYTES", "20,000,000"),
        ("TUB_DOWNLOAD_SOURCE_XML_BYTES", "100000001"),
    ],
)
def test_download_cap_that_is_not_a_whole_number_in_range_is_refused(variable: str, value: str) -> None:
    from debate_api.configuration import ConfigurationMissing, PilotConfiguration

    with pytest.raises(ConfigurationMissing, match=variable):
        PilotConfiguration.from_environment({**REQUIRED_ENVIRONMENT, variable: value})


# ------------------------------------------------------------------------------------------------
# The PM's review, condition 2: a card whose own source is over the budget is a refused card
# ------------------------------------------------------------------------------------------------

TOO_LARGE_ALONE: Final = "Its file is too large to download. Copy card still works."


def test_download_setting_renamed_the_old_source_bytes_variable_is_not_read() -> None:
    """`TUB_DOWNLOAD_SOURCE_BYTES` was never deployed; `TUB_DOWNLOAD_SOURCE_XML_BYTES` replaced it."""
    from debate_api.configuration import PilotConfiguration

    configuration = PilotConfiguration.from_environment(
        {**REQUIRED_ENVIRONMENT, "TUB_DOWNLOAD_SOURCE_BYTES": "not a number"}
    )

    assert configuration.download_source_xml_bytes == 20_000_000
    assert not hasattr(configuration, "download_source_bytes")


@pytest.fixture
def tight(make_world: Any) -> Any:
    """A `document.xml` budget of exactly the `other` source's: `disclosed`'s is over it alone, and
    `camp`'s and `other`'s are each at it, so together they are over (the PM's ruling of 2026-10-22)."""
    probe = make_world()
    budget = probe.document_bytes("other")
    assert probe.document_bytes("disclosed") > budget == probe.document_bytes("camp")
    probe.services.search_index.close()
    made = make_world(download_source_xml_bytes=budget)
    made.signed_in_student()
    yield made
    made.services.search_index.close()


def test_cart_with_a_card_whose_own_file_is_over_the_source_budget_names_it(tight: Any) -> None:
    response = tight.download("camp download", "download")

    assert response.status_code == 409
    assert response.json() == {
        "message": "Some cards cannot be downloaded.",
        "refused": [
            {
                "card": tight.card_reference("download"),
                "position": 2,
                "name": "Gabbro ridges slow upland erosion",
                "reason": TOO_LARGE_ALONE,
            }
        ],
    }
    assert tight.built == [] and downloads(tight) == []


def test_cart_without_the_card_whose_own_file_is_too_large_builds_the_rest(tight: Any) -> None:
    refused = tight.download("camp download", "download", "download second").json()["refused"]

    assert [card["position"] for card in refused] == [2, 3]
    assert {card["reason"] for card in refused} == {TOO_LARGE_ALONE}
    response = tight.download("camp download")
    assert response.status_code == 200
    assert paragraphs(response.content)[3:] == CAMP_PARAGRAPHS


def test_cart_whose_sources_only_add_up_past_the_budget_keeps_the_sources_message(tight: Any) -> None:
    response = tight.download("camp download", "download other")

    assert response.status_code == 409
    assert response.json() == {
        "message": (
            "These cards come from files too large to read in one download. Download fewer cards at a time, "
            "or a card from a large file on its own."
        )
    }
    assert tight.built == []


# ------------------------------------------------------------------------------------------------
# The PM's ruling of 2026-10-22: the budget is document.xml bytes, with a ceiling on fetched bytes
# ------------------------------------------------------------------------------------------------


def test_download_cart_whose_document_parts_are_exactly_the_budget_downloads(make_world: Any) -> None:
    probe = make_world()
    budget = probe.document_bytes("camp") + probe.document_bytes("other")
    probe.services.search_index.close()
    at = make_world(download_source_xml_bytes=budget)
    over = make_world(download_source_xml_bytes=budget - 1)
    for world in (at, over):
        world.signed_in_student()
    try:
        at_response = at.download("camp download", "download other")
        over_response = over.download("camp download", "download other")
    finally:
        at.services.search_index.close()
        over.services.search_index.close()

    assert at_response.status_code == 200
    assert over_response.status_code == 409
    assert over_response.json() == {
        "message": (
            "These cards come from files too large to read in one download. Download fewer cards at a time, "
            "or a card from a large file on its own."
        )
    }
    assert over.built == []


def test_download_budget_counts_document_parts_not_file_bytes(make_world: Any) -> None:
    """A budget below both files' bytes, at their two document parts' sum: the cart downloads."""
    probe = make_world()
    sources = probe.sources()
    budget = probe.document_bytes("camp") + probe.document_bytes("other")
    assert budget < len(sources["camp"].content) + len(sources["other"].content)
    probe.services.search_index.close()
    world = make_world(download_source_xml_bytes=budget)
    world.signed_in_student()
    try:
        response = world.download("camp download", "download other")
    finally:
        world.services.search_index.close()

    assert response.status_code == 200


def test_download_of_one_file_past_the_fetch_ceiling_gets_the_files_message_not_a_named_card(
    make_world: Any,
) -> None:
    probe = make_world()
    ceiling = len(probe.sources()["disclosed"].content) - 1
    probe.services.search_index.close()
    world = make_world(download_fetch_bytes=ceiling)
    world.signed_in_student()
    try:
        response = world.download("download")
    finally:
        world.services.search_index.close()

    assert response.status_code == 409
    assert response.json() == {
        "message": (
            "These cards come from files too large to read in one download. Download fewer cards at a time, "
            "or a card from a large file on its own."
        )
    }
    assert world.built == []


def test_download_of_a_file_that_understates_its_document_part_passes_the_budget_and_is_refused_by_the_parser(
    make_world: Any,
) -> None:
    """The zip directory claims 1,000 bytes for a `word/document.xml` that holds far more. The budget
    reads the claim and lets it through; the parser never inflates past the claim, its CRC fails, and
    the card is refused as no longer matching the search, nothing built."""
    probe = make_world()
    assert probe.document_bytes("understated") == 1000
    probe.services.search_index.close()
    world = make_world(download_source_xml_bytes=1000)
    world.signed_in_student()
    try:
        response = world.download("understated")
    finally:
        world.services.search_index.close()

    assert response.status_code == 409
    assert response.json()["refused"] == [
        {
            "card": world.card_reference("understated"),
            "position": 1,
            "name": "Tephra plumes travel far downwind",
            "reason": (
                "Its file no longer matches the search. It can be downloaded after the next weekly update."
            ),
        }
    ]
    assert world.built == [] and downloads(world) == []

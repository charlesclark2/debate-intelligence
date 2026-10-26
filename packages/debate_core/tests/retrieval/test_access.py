"""The access classifier: status mapping, paywall and challenge markers, truncation (v1-e04-t03).

Test names carry the plan node they belong to, so each node's criterion selects its own:
`-k mapping` (status-mapping, ac1), `-k marker` (paywall-markers, ac2 and ac4), `-k truncat`
(truncation-heuristic, ac3). The saved-sample suite at the end runs the HTML extractor over the
pages in `tests/fixtures/access/` and checks each against its hand-written expected status.

Expected statuses here are written from the spec and the documented mapping, never copied from a
classifier run (working agreement 6). Property tests use `event()` labels, visible with
`--hypothesis-show-statistics`.
"""

from __future__ import annotations

import hashlib
import json
import os
import typing
from datetime import UTC, datetime
from importlib import resources
from typing import Final

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from tests.fixtures.access.samples import load_expected_statuses, sample_bytes

from debate_core.domain import AccessStatus
from debate_core.integrations.html_extractor import TrafilaturaExtractor
from debate_core.retrieval.access import (
    PAYWALL_RULES_FILE,
    AccessClassifier,
    AccessDecision,
    AccessEvidence,
    AccessThresholds,
    ClassOrIdMarker,
    DeclaredLengthSource,
    HeaderMarker,
    InlineScriptMarker,
    Marker,
    MarkerCategory,
    MetaMarker,
    PaywallRules,
    ScriptSourceMarker,
    TitleMarker,
    VisibleTextMarker,
    bundled_paywall_rules,
)
from debate_core.retrieval.extraction import (
    DocumentTooLarge,
    EncryptedDocument,
    ExtractedContent,
    ExtractionError,
    ExtractionQuality,
    PaywallMarkerFound,
    TooManyPages,
    UnreadableDocument,
    UnsupportedContentType,
)
from debate_core.retrieval.fetch_types import (
    FetchError,
    FetchErrorBase,
    FetchResult,
    HttpStatusError,
    NonPublicAddress,
    RobotsDisallowed,
    RobotsRefusalReason,
    Timeout,
    TimeoutPhase,
    TooLarge,
    TooManyRedirects,
    TransportError,
    UnsupportedScheme,
)

URL: Final = "https://news.example.org/2026/10/story"
WHEN: Final = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
HTML: Final = "text/html; charset=utf-8"
PDF_BODY: Final = b"%PDF-1.7\n1 0 obj\n(subscribe to continue reading) Tj\n"

RULES_VERSION: Final = "paywall_rules.v1"
RULES_SHA256: Final = "PIN-ME"
"""The bundled rules file's hash. A change to the file without a new version fails here."""

PROPERTY_SETTINGS = settings(
    max_examples=int(os.environ.get("ACCESS_PROPERTY_EXAMPLES", "200")),
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

ACCESSIBLE: Final = AccessStatus.ACCESSIBLE
PAYWALLED: Final = AccessStatus.PAYWALLED
BLOCKED: Final = AccessStatus.BLOCKED
ROBOTS_DISALLOWED: Final = AccessStatus.ROBOTS_DISALLOWED
NOT_FOUND: Final = AccessStatus.NOT_FOUND
UNSUPPORTED_TYPE: Final = AccessStatus.UNSUPPORTED_TYPE
ERROR: Final = AccessStatus.ERROR


# ---------------------------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------------------------


def page(*, title: str = "A story", head: str = "", body: str = "", word_count: object = None) -> bytes:
    """A small HTML page; `word_count` becomes a NewsArticle JSON-LD `wordCount` when given."""
    json_ld = (
        '<script type="application/ld+json">'
        + json.dumps({"@context": "https://schema.org", "@type": "NewsArticle", "wordCount": word_count})
        + "</script>"
        if word_count is not None
        else ""
    )
    return (
        f"<!DOCTYPE html><html><head><title>{title}</title>{json_ld}{head}</head>"
        f"<body><article><h1>A story</h1><p>Words of the story.</p></article>{body}</body></html>"
    ).encode()


def response(
    status_code: int | None = 200,
    body: bytes = b"",
    *,
    content_type: str | None = HTML,
    headers: dict[str, str] | None = None,
) -> FetchResult:
    """A response that arrived; a 4xx or 5xx carries the HttpStatusError the fetcher would attach."""
    error = (
        HttpStatusError(url=URL, message=f"news.example.org answered {status_code}", status_code=status_code, attempts=1)
        if status_code is not None and status_code >= 400
        else None
    )
    return FetchResult(
        requested_url=URL,
        final_url=URL,
        status_code=status_code,
        headers=headers or {},
        content_type=content_type,
        body=body,
        elapsed_ms=1.0,
        fetched_at=WHEN,
        error=error,
    )


def failure(error: FetchErrorBase) -> FetchResult:
    """A fetch that produced no response, as the fetcher reports it."""
    robots = isinstance(error, RobotsDisallowed)
    return FetchResult.model_validate(
        {
            "requested_url": URL,
            "final_url": URL,
            "elapsed_ms": 1.0,
            "fetched_at": WHEN,
            "error": error,
            "access_status": AccessStatus.ROBOTS_DISALLOWED if robots else AccessStatus.UNKNOWN,
        }
    )


def text_of_words(words: int, *, per_paragraph: int = 80) -> ExtractedContent:
    """Extracted text of exactly `words` five-letter words: 6 * words - (paragraphs) characters."""
    sizes = [per_paragraph] * (words // per_paragraph) + ([words % per_paragraph] if words % per_paragraph else [])
    paragraphs = tuple(" ".join(["river"] * size) for size in sizes)
    return ExtractedContent(
        paragraphs=paragraphs,
        extractor_name="test-extractor",
        extractor_version="test-1",
        quality=ExtractionQuality(
            character_count=sum(len(paragraph) for paragraph in paragraphs),
            paragraph_count=len(paragraphs),
            fallback_used=not paragraphs,
        ),
    )


LONG_TEXT: Final = text_of_words(400)
"""Enough text for any default threshold: 400 words, 2398 characters."""


def classify(
    fetched: FetchResult,
    extraction: ExtractedContent | ExtractionError | None = LONG_TEXT,
    *,
    thresholds: AccessThresholds | None = None,
) -> AccessDecision:
    return AccessClassifier(thresholds=thresholds).classify(fetched, extraction)


def marker_id(decision: AccessDecision) -> str | None:
    return decision.evidence.marker.marker_id if decision.evidence.marker is not None else None


# ---------------------------------------------------------------------------------------------
# Status mapping (plan node status-mapping, ac1)
# ---------------------------------------------------------------------------------------------

FETCH_ERRORS: Final[list[tuple[FetchErrorBase, AccessStatus]]] = [
    (
        Timeout(url=URL, message="news.example.org went quiet", phase=TimeoutPhase.READ, limit_seconds=10),
        ERROR,
    ),
    (TooLarge(url=URL, message="news.example.org sent too much", limit_bytes=10, received_bytes=11), ERROR),
    (
        TooManyRedirects(url=URL, message="news.example.org redirected too often", limit=5, redirect_chain=(URL,)),
        ERROR,
    ),
    (
        RobotsDisallowed(
            url=URL,
            message="news.example.org's robots.txt disallows this path",
            robots_url="https://news.example.org/robots.txt",
            reason=RobotsRefusalReason.DISALLOWED,
        ),
        ROBOTS_DISALLOWED,
    ),
    (UnsupportedScheme(url=URL, message="news.example.org redirected to ftp", scheme="ftp"), ERROR),
    (NonPublicAddress(url="http://127.0.0.1/admin", message="127.0.0.1 is not public", host="127.0.0.1"), ERROR),
    (TransportError(url=URL, message="news.example.org refused the connection", reason="ConnectError"), ERROR),
]


def test_mapping_table_covers_every_fetch_error_type() -> None:
    """A ninth error type added to t02's union fails here until the mapping covers it."""
    union = typing.get_args(typing.get_args(FetchError.__value__)[0])
    assert {type(error) for error, _ in FETCH_ERRORS} | {HttpStatusError} == set(union)


@pytest.mark.parametrize(("error", "expected"), FETCH_ERRORS, ids=lambda value: getattr(value, "kind", ""))
def test_mapping_of_each_fetch_error(error: FetchErrorBase, expected: AccessStatus) -> None:
    decision = classify(failure(error), None)
    assert decision.status is expected
    assert decision.evidence.fetch_error == error.kind
    assert error.message in decision.reason
    assert decision.rules_version == RULES_VERSION


@pytest.mark.parametrize("reason", list(RobotsRefusalReason))
def test_mapping_every_robots_refusal_is_robots_disallowed(reason: RobotsRefusalReason) -> None:
    error = RobotsDisallowed(
        url=URL, message="robots.txt says no", robots_url="https://news.example.org/robots.txt", reason=reason
    )
    assert classify(failure(error), None).status is ROBOTS_DISALLOWED


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (400, ERROR),
        (401, PAYWALLED),
        (402, PAYWALLED),
        (403, BLOCKED),
        (404, NOT_FOUND),
        (405, ERROR),
        (408, ERROR),
        (410, NOT_FOUND),
        (418, ERROR),
        (429, ERROR),
        (451, BLOCKED),
        (500, ERROR),
        (502, ERROR),
        (503, ERROR),
        (504, ERROR),
        (599, ERROR),
    ],
)
def test_mapping_of_error_statuses_with_a_plain_body(status_code: int, expected: AccessStatus) -> None:
    decision = classify(response(status_code, page(title="Error")), None)
    assert decision.status is expected
    assert decision.evidence.status_code == status_code
    assert str(status_code) in decision.reason


@pytest.mark.parametrize("status_code", [401, 403, 429, 503])
def test_mapping_a_challenge_page_on_a_refusal_status_is_blocked(status_code: int) -> None:
    decision = classify(response(status_code, page(title="Just a moment...")), None)
    assert decision.status is BLOCKED
    assert marker_id(decision) == "cloudflare-interstitial-title"


@pytest.mark.parametrize("status_code", [404, 410, 402, 451, 500])
def test_mapping_a_challenge_marker_does_not_change_a_definite_status(status_code: int) -> None:
    decision = classify(response(status_code, page(title="Just a moment...")), None)
    assert decision.status is classify(response(status_code, page()), None).status
    assert decision.evidence.marker is None


def test_mapping_a_403_with_a_paywall_overlay_is_paywalled() -> None:
    body = page(body='<div class="paywall"><p>Subscribe to continue reading.</p></div>')
    decision = classify(response(403, body), None)
    assert decision.status is PAYWALLED
    assert marker_id(decision) == "paywall-element"


@pytest.mark.parametrize("status_code", [404, 410])
def test_mapping_a_missing_page_with_a_site_wide_meter_is_not_found(status_code: int) -> None:
    body = page(head='<script src="https://experience.tinypass.com/load"></script>', body="<p>Subscribe to keep reading</p>")
    assert classify(response(status_code, body), None).status is NOT_FOUND


@pytest.mark.parametrize("status_code", [429, 503])
def test_mapping_a_plain_throttle_or_outage_is_an_error_not_a_block(status_code: int) -> None:
    assert classify(response(status_code, b""), None).status is ERROR


@pytest.mark.parametrize(
    ("status_code", "words"),
    [(204, "no content"), (205, "no content"), (206, "partial"), (304, "304"), (300, "300"), (None, "no response")],
)
def test_mapping_a_response_without_a_whole_document_is_an_error(status_code: int | None, words: str) -> None:
    decision = classify(response(status_code, page()), LONG_TEXT)
    assert decision.status is ERROR
    assert words in decision.reason.lower()


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"\x89PNG\r\n\x1a\n\x00\x00", "image/png"),
        (b"PK\x03\x04\x14\x00", "application/zip"),
        (b'{"story": "words"}', "application/json"),
        (b"plain words", "text/plain"),
        (b"plain words", None),
        (b"\x89PNG\r\n\x1a\n\x00\x00", "text/html"),
    ],
)
def test_mapping_a_type_no_extractor_reads_is_unsupported(body: bytes, content_type: str | None) -> None:
    decision = classify(response(200, body, content_type=content_type), None)
    assert decision.status is UNSUPPORTED_TYPE


REFUSALS: Final[list[tuple[ExtractionError, AccessStatus]]] = [
    (UnsupportedContentType("application/zip", "application/zip"), UNSUPPORTED_TYPE),
    (EncryptedDocument(), UNSUPPORTED_TYPE),
    (PaywallMarkerFound("isAccessibleForFree=false in JSON-LD"), PAYWALLED),
    (DocumentTooLarge(20, 10), ERROR),
    (TooManyPages(600, 500), ERROR),
    (UnreadableDocument("the page is not valid utf-8; no character is guessed"), ERROR),
]


def _subclasses(base: type[ExtractionError]) -> set[type[ExtractionError]]:
    found: set[type[ExtractionError]] = set()
    for child in base.__subclasses__():
        if child.__module__ == "debate_core.retrieval.extraction":
            found |= {child} | _subclasses(child)
    return found


def test_mapping_table_covers_every_extraction_refusal() -> None:
    assert {type(refusal) for refusal, _ in REFUSALS} == _subclasses(ExtractionError)


@pytest.mark.parametrize(("refusal", "expected"), REFUSALS, ids=lambda value: type(value).__name__)
def test_mapping_of_each_extraction_refusal(refusal: ExtractionError, expected: AccessStatus) -> None:
    body, content_type = (PDF_BODY, "application/pdf") if isinstance(refusal, EncryptedDocument) else (page(), HTML)
    decision = classify(response(200, body, content_type=content_type), refusal)
    assert decision.status is expected
    assert decision.evidence.extraction_refusal == type(refusal).__name__


def test_mapping_an_unknown_extraction_refusal_is_an_error() -> None:
    class NewRefusal(ExtractionError):
        pass

    decision = classify(response(200, page()), NewRefusal("something new"))
    assert decision.status is ERROR
    assert decision.evidence.extraction_refusal == "NewRefusal"


def test_mapping_an_unextracted_page_is_never_accessible() -> None:
    decision = classify(response(200, page()), None)
    assert decision.status is ERROR


def test_mapping_an_open_page_with_enough_text_is_accessible() -> None:
    decision = classify(response(200, page()), LONG_TEXT)
    assert decision.status is ACCESSIBLE
    assert decision.evidence.status_code == 200
    assert decision.rules_version == RULES_VERSION


def test_mapping_an_open_pdf_is_accessible_and_its_bytes_are_not_read_for_markers() -> None:
    decision = classify(response(200, PDF_BODY, content_type="application/pdf"), LONG_TEXT)
    assert decision.status is ACCESSIBLE


def test_mapping_a_decision_is_never_unknown() -> None:
    with pytest.raises(ValidationError, match="UNKNOWN"):
        AccessDecision(
            status=AccessStatus.UNKNOWN, reason="no", evidence=AccessEvidence(), rules_version=RULES_VERSION
        )


BODY_KINDS: Final = ("empty", "plain", "challenge", "paywall")
BODIES: Final = {
    "empty": b"",
    "plain": page(title="Error"),
    "challenge": page(title="Just a moment..."),
    "paywall": page(body='<div class="regwall">Log in to continue reading</div>'),
}


def documented_status(status_code: int, body_kind: str) -> AccessStatus:
    """The documented table, written out by hand for the property below."""
    if status_code in (404, 410):
        return NOT_FOUND
    if status_code == 402:
        return PAYWALLED
    if status_code == 451:
        return BLOCKED
    if status_code in (401, 403, 429, 503) and body_kind == "challenge":
        return BLOCKED
    if status_code == 401:
        return PAYWALLED
    if status_code == 403:
        return PAYWALLED if body_kind == "paywall" else BLOCKED
    return ERROR


@PROPERTY_SETTINGS
@given(status_code=st.integers(400, 599), body_kind=st.sampled_from(BODY_KINDS))
def test_mapping_property_every_error_status_maps_as_documented(status_code: int, body_kind: str) -> None:
    decision = classify(response(status_code, BODIES[body_kind]), None)
    event(f"status: {decision.status.value}")
    assert decision.status is documented_status(status_code, body_kind)


# ---------------------------------------------------------------------------------------------
# Paywall and challenge markers (plan node paywall-markers, ac2 and ac4)
# ---------------------------------------------------------------------------------------------


def planted(marker: Marker) -> tuple[bytes, dict[str, str]]:
    """An otherwise open page carrying `marker`, written the way a site would, in mixed case."""
    match marker:
        case HeaderMarker():
            return page(), {marker.name: f"managed {marker.contains}"}
        case ScriptSourceMarker():
            return page(head=f'<script async src="https://static.example/{marker.contains}/v2/load.js"></script>'), {}
        case InlineScriptMarker():
            return page(body=f"<script>(function(){{window.{marker.contains} = {{ray: 'X'}};}}());</script>"), {}
        case ClassOrIdMarker():
            return page(body=f'<div class="Overlay {marker.token.upper()} fade-in"><p>Hello.</p></div>'), {}
        case MetaMarker():
            return page(head=f'<meta property="{marker.name.upper()}" content="{marker.content.upper()}">'), {}
        case TitleMarker():
            return page(title=f"  {marker.equals.upper()}  "), {}
        case VisibleTextMarker():
            return page(body=f"<div><p>{marker.phrase.capitalize().replace(' ', '\n  ')}.</p></div>"), {}


def all_markers() -> list[tuple[MarkerCategory, Marker]]:
    rules = bundled_paywall_rules()
    return [(MarkerCategory.CHALLENGE, marker) for marker in rules.challenge_markers] + [
        (MarkerCategory.PAYWALL, marker) for marker in rules.paywall_markers
    ]


@pytest.mark.parametrize(("category", "marker"), all_markers(), ids=lambda value: getattr(value, "id", ""))
def test_marker_each_rule_is_detected_on_a_200_page(category: MarkerCategory, marker: Marker) -> None:
    """ac2: every marker in the file, planted in an open page with plenty of text."""
    body, headers = planted(marker)
    decision = classify(response(200, body, headers=headers), LONG_TEXT)
    assert decision.status is (BLOCKED if category is MarkerCategory.CHALLENGE else PAYWALLED)
    assert decision.evidence.marker is not None
    assert (decision.evidence.marker.category, decision.evidence.marker.marker_id) == (category, marker.id)
    assert marker.id in decision.reason


def test_marker_the_extractors_is_accessible_for_free_refusal_is_paywalled() -> None:
    """ac2: schema.org isAccessibleForFree=false, read by the HTML extractor (t04), is mapped here."""
    decision = classify(response(200, page()), PaywallMarkerFound("isAccessibleForFree=false in JSON-LD"))
    assert decision.status is PAYWALLED
    assert marker_id(decision) == "extractor-is-accessible-for-free"
    assert "isAccessibleForFree=false in JSON-LD" in decision.reason
    assert decision.evidence.marker is not None
    assert decision.evidence.marker.pattern == "isAccessibleForFree=false in JSON-LD"


@pytest.mark.parametrize(
    ("head", "body", "expected_id"),
    [
        ('<script src="https://experience.tinypass.com/xbuilder/experience/load?aid=X"></script>', "", "piano-tinypass-script"),
        ('<script src="https://cdn.piano.io/api/tinypass.min.js"></script>', "", "piano-cdn-tinypass-script"),
        ('<meta property="article:content_tier" content="locked">', "", "content-tier-locked-meta"),
        ('<meta name="article:content_tier" content="metered">', "", "content-tier-metered-meta"),
        ("", '<div id="paywall"></div>', "paywall-element"),
        ("", '<section class="tp-modal tp-active"></section>', "piano-modal-overlay"),
        ("", "<p>Subscribe to continue reading</p>", "subscribe-to-continue-reading-text"),
        ("", "<p>You\N{RIGHT SINGLE QUOTATION MARK}ve reached your <b>free article</b> limit.</p>", "free-article-limit-text"),
        ("", "<p>Sign in to\ncontinue   reading</p>", "sign-in-to-continue-reading-text"),
    ],
)
def test_marker_examples_as_publishers_write_them(head: str, body: str, expected_id: str) -> None:
    decision = classify(response(200, page(head=head, body=body)), LONG_TEXT)
    assert decision.status is PAYWALLED
    assert marker_id(decision) == expected_id


@pytest.mark.parametrize(
    ("head", "body", "title"),
    [
        ("", '<div class="no-paywall paywall-free"></div>', "A story"),
        ("", "<p>Subscribe to our newsletter for the day's top stories.</p>", "A story"),
        ("", "<p>Our reporters read tinypass.com documentation.</p>", "A story"),
        ("", "<!-- paywall: subscribe to continue reading -->", "A story"),
        ("", "<script>var notice = 'subscribe to continue reading';</script>", "A story"),
        ("", "<style>.paywall { display: none }</style>", "A story"),
        ("", "<template><p>Subscribe to continue reading</p></template>", "A story"),
        ('<meta property="article:content_tier" content="free">', "", "A story"),
        ("", "", "Just a moment... of silence"),
        ("", "", "Access denied to the archives: a history"),
        ("", "<p>Researchers studied the _cf_chl_opt object.</p>", "A story"),
        ('<script src="https://www.google.com/recaptcha/api.js"></script>', "", "A story"),
    ],
)
def test_marker_near_misses_do_not_match(head: str, body: str, title: str) -> None:
    decision = classify(response(200, page(title=title, head=head, body=body)), LONG_TEXT)
    assert decision.status is ACCESSIBLE
    assert decision.evidence.marker is None


def test_marker_challenge_is_tried_before_paywall() -> None:
    body = page(title="Just a moment...", body='<div class="paywall"></div>')
    decision = classify(response(200, body), LONG_TEXT)
    assert decision.status is BLOCKED
    assert marker_id(decision) == "cloudflare-interstitial-title"


def test_marker_the_extractors_refusal_is_recorded_before_the_rules() -> None:
    body = page(body='<div class="paywall"></div>')
    decision = classify(response(200, body), PaywallMarkerFound("isAccessibleForFree=false in microdata"))
    assert marker_id(decision) == "extractor-is-accessible-for-free"


def test_marker_a_header_marker_applies_to_a_pdf_body() -> None:
    decision = classify(
        response(200, PDF_BODY, content_type="application/pdf", headers={"cf-mitigated": "challenge"}), LONG_TEXT
    )
    assert decision.status is BLOCKED
    assert marker_id(decision) == "cloudflare-mitigated-header"


def test_marker_a_page_in_utf16_with_a_byte_order_mark_is_read() -> None:
    body = "\N{ZERO WIDTH NO-BREAK SPACE}".encode("utf-16-le") + page(
        body="<p>Subscribe to keep reading</p>"
    ).decode().encode("utf-16-le")
    decision = classify(response(200, body, content_type="text/html"), LONG_TEXT)
    assert marker_id(decision) == "subscribe-to-keep-reading-text"


# ac4: the rules file is versioned, and every result carries its version.


def test_marker_rules_file_is_versioned_and_pinned() -> None:
    raw = resources.files("debate_core.retrieval").joinpath(PAYWALL_RULES_FILE).read_bytes()
    rules = bundled_paywall_rules()
    assert rules.version == RULES_VERSION == PAYWALL_RULES_FILE.removesuffix(".json")
    assert hashlib.sha256(raw).hexdigest() == RULES_SHA256, (
        "paywall_rules changed: give it a new version (file name, version field) and pin the new hash"
    )


def test_marker_rules_version_is_on_every_result() -> None:
    rules = bundled_paywall_rules().evolve(version="paywall_rules.test-9")
    classifier = AccessClassifier(rules=rules)
    outcomes = [
        classifier.classify(response(200, page()), LONG_TEXT),
        classifier.classify(response(404, page()), None),
        classifier.classify(failure(FETCH_ERRORS[0][0]), None),
        classifier.classify(response(200, page(body='<div class="paywall"></div>')), LONG_TEXT),
        classifier.classify(response(200, page()), text_of_words(3)),
    ]
    assert {decision.rules_version for decision in outcomes} == {"paywall_rules.test-9"}


def test_marker_rules_from_another_file_are_the_ones_used() -> None:
    rules = PaywallRules(
        version="paywall_rules.test-1",
        description="One marker of each list.",
        challenge_markers=(TitleMarker(id="custom-challenge", description="A test title.", equals="hold on"),),
        paywall_markers=(ClassOrIdMarker(id="custom-wall", description="A test class.", token="members-only"),),
    )
    classifier = AccessClassifier(rules=rules)
    walled = classifier.classify(response(200, page(body='<div class="members-only"></div>')), LONG_TEXT)
    held = classifier.classify(response(200, page(title="Hold on")), LONG_TEXT)
    bundled_marker = classifier.classify(response(200, page(body='<div class="paywall"></div>')), LONG_TEXT)
    assert (walled.status, marker_id(walled)) == (PAYWALLED, "custom-wall")
    assert (held.status, marker_id(held)) == (BLOCKED, "custom-challenge")
    assert bundled_marker.status is ACCESSIBLE


@pytest.mark.parametrize(
    "change",
    [
        {"paywall_markers": [{"id": "x", "kind": "class_or_id", "token": "Paywall", "description": "d"}]},
        {"paywall_markers": [{"id": "x", "kind": "visible_text", "phrase": "two  spaces", "description": "d"}]},
        {"paywall_markers": [{"id": "x", "kind": "script_src", "contains": " pad", "description": "d"}]},
        {"paywall_markers": [{"id": "X_1", "kind": "class_or_id", "token": "a", "description": "d"}]},
        {"paywall_markers": [{"id": "x", "kind": "selector", "token": "a", "description": "d"}]},
        {"paywall_markers": [{"id": "x", "kind": "class_or_id", "token": "a", "description": "d", "weight": 2}]},
        {"paywall_markers": [{"id": "cloudflare-interstitial-title", "kind": "class_or_id", "token": "a", "description": "d"}]},
        {"paywall_markers": []},
        {"version": " "},
    ],
)
def test_marker_rules_refuse_a_malformed_file(change: dict[str, object]) -> None:
    raw = json.loads(resources.files("debate_core.retrieval").joinpath(PAYWALL_RULES_FILE).read_text("utf-8"))
    with pytest.raises(ValidationError):
        PaywallRules.model_validate({**raw, **change})


NEAR_MISSES: Final = (
    '<p class="byline">By A. Writer</p>',
    "<p>Subscribe to our newsletter.</p>",
    '<div class="no-paywall"></div>',
    "<!-- paywall -->",
    "<script>var s = 'subscribe to continue reading';</script>",
    '<a href="https://tinypass.com">a story about tinypass.com</a>',
    '<img src="/img/tp-modal.png" alt="tp-modal">',
    "<p>The incapsula incident was resolved.</p>",
)


@PROPERTY_SETTINGS
@given(
    category_and_marker=st.sampled_from(all_markers()),
    before=st.lists(st.sampled_from(NEAR_MISSES), max_size=4),
    after=st.lists(st.sampled_from(NEAR_MISSES), max_size=4),
    words=st.integers(0, 3000),
    status_code=st.sampled_from([200, 203]),
)
def test_marker_property_a_planted_marker_is_found_among_near_misses(
    category_and_marker: tuple[MarkerCategory, Marker],
    before: list[str],
    after: list[str],
    words: int,
    status_code: int,
) -> None:
    category, marker = category_and_marker
    body, headers = planted(marker)
    text = body.decode()
    text = text.replace("<body>", "<body>" + "".join(before)).replace("</body>", "".join(after) + "</body>")
    decision = classify(response(status_code, text.encode(), headers=headers), text_of_words(words))
    event(f"marker kind: {marker.kind}")
    assert decision.status is (BLOCKED if category is MarkerCategory.CHALLENGE else PAYWALLED)
    assert marker_id(decision) == marker.id


@PROPERTY_SETTINGS
@given(snippets=st.lists(st.sampled_from(NEAR_MISSES), max_size=8), status_code=st.sampled_from([200, 203]))
def test_marker_property_near_misses_alone_leave_an_open_page_accessible(
    snippets: list[str], status_code: int
) -> None:
    event(f"near misses: {min(len(snippets), 3)}{'+' if len(snippets) >= 3 else ''}")
    decision = classify(response(status_code, page(body="".join(snippets))), LONG_TEXT)
    assert decision.status is ACCESSIBLE


# ---------------------------------------------------------------------------------------------
# Truncated-text heuristic (plan node truncation-heuristic, ac3)
# ---------------------------------------------------------------------------------------------


def test_truncation_against_a_declared_word_count_is_paywalled() -> None:
    decision = classify(response(200, page(word_count=1200)), text_of_words(150))
    assert decision.status is PAYWALLED
    assert decision.evidence.declared_words == 1200
    assert decision.evidence.extracted_words == 150
    assert decision.evidence.declared_length_source is DeclaredLengthSource.JSON_LD_WORD_COUNT
    assert decision.evidence.thresholds == AccessThresholds()
    assert "150" in decision.reason and "1200" in decision.reason


def test_truncation_against_a_declared_article_body_counts_its_words_and_never_keeps_them() -> None:
    article_body = " ".join(["Quillwort"] * 900)
    head = (
        '<script type="application/ld+json">'
        + json.dumps({"@type": "Article", "articleBody": article_body})
        + "</script>"
    )
    decision = classify(response(200, page(head=head)), text_of_words(200))
    assert decision.status is PAYWALLED
    assert decision.evidence.declared_words == 900
    assert decision.evidence.declared_length_source is DeclaredLengthSource.JSON_LD_ARTICLE_BODY
    assert "quillwort" not in decision.model_dump_json().lower()


def test_truncation_takes_the_longest_declared_length() -> None:
    head = (
        '<script type="application/ld+json">'
        + json.dumps(
            {"@graph": [{"@type": "WebPage", "wordCount": 100}, {"@type": "NewsArticle", "wordCount": "2,000"}]}
        )
        + "</script>"
        + '<script type="application/ld+json">'
        + json.dumps([{"@type": "Article", "wordCount": 1500}])
        + "</script>"
    )
    decision = classify(response(200, page(head=head)), text_of_words(900))
    assert decision.status is PAYWALLED
    assert decision.evidence.declared_words == 2000


@pytest.mark.parametrize(("extracted", "expected"), [(499, PAYWALLED), (500, ACCESSIBLE), (501, ACCESSIBLE)])
def test_truncation_boundary_is_the_ratio_of_the_declared_length(extracted: int, expected: AccessStatus) -> None:
    decision = classify(response(200, page(word_count=1000)), text_of_words(extracted))
    assert decision.status is expected


@pytest.mark.parametrize(("characters", "expected"), [(499, ERROR), (500, ACCESSIBLE), (501, ACCESSIBLE)])
def test_truncation_without_a_declared_length_the_minimum_decides(characters: int, expected: AccessStatus) -> None:
    paragraph = ("x" * (characters - 1)) + "."
    content = ExtractedContent(
        paragraphs=(paragraph,),
        extractor_name="test-extractor",
        extractor_version="test-1",
        quality=ExtractionQuality(character_count=characters, paragraph_count=1),
    )
    decision = classify(response(200, page()), content)
    assert decision.status is expected
    assert decision.evidence.declared_words is None
    assert decision.evidence.extracted_characters == characters


@pytest.mark.parametrize(("word_count", "expected"), [(None, ERROR), (900, PAYWALLED)])
def test_truncation_an_empty_extraction_is_never_accessible(word_count: int | None, expected: AccessStatus) -> None:
    """t04's empty extraction: no paragraphs, 0 characters, fallback_used true."""
    empty = text_of_words(0)
    assert (empty.quality.character_count, empty.quality.fallback_used) == (0, True)
    decision = classify(response(200, page(word_count=word_count)), empty)
    assert decision.status is expected
    assert decision.evidence.extracted_characters == 0


def test_truncation_an_empty_pdf_extraction_is_an_error() -> None:
    decision = classify(response(200, PDF_BODY, content_type="application/pdf"), text_of_words(0))
    assert decision.status is ERROR


def test_truncation_a_short_declared_article_still_meets_the_minimum() -> None:
    decision = classify(response(200, page(word_count=40)), text_of_words(40))
    assert decision.status is ERROR


@pytest.mark.parametrize("word_count", ["many", 0, -5, True, 12.5, "", {"value": 900}, [900]])
def test_truncation_an_unusable_declared_length_is_ignored(word_count: object) -> None:
    decision = classify(response(200, page(word_count=word_count)), text_of_words(150))
    assert decision.status is ACCESSIBLE
    assert decision.evidence.declared_words is None


def test_truncation_malformed_json_ld_is_ignored() -> None:
    head = '<script type="application/ld+json">{"wordCount": 5000,</script>'
    assert classify(response(200, page(head=head)), text_of_words(150)).status is ACCESSIBLE


def test_truncation_thresholds_are_configurable() -> None:
    strict = AccessThresholds(minimum_characters=3000, truncation_ratio=0.9)
    lenient = AccessThresholds(minimum_characters=10, truncation_ratio=0.1)
    fetched = response(200, page(word_count=1000))
    assert classify(fetched, text_of_words(400), thresholds=strict).status is PAYWALLED
    assert classify(fetched, text_of_words(400), thresholds=lenient).status is ACCESSIBLE
    assert classify(response(200, page()), text_of_words(400), thresholds=strict).status is ERROR


@pytest.mark.parametrize(
    "values",
    [{"minimum_characters": 0}, {"truncation_ratio": 0}, {"truncation_ratio": 1.5}, {"minimum_characters": -1}],
)
def test_truncation_thresholds_refuse_nonsense(values: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        AccessThresholds.model_validate(values)


@PROPERTY_SETTINGS
@given(
    declared=st.none() | st.integers(1, 6000),
    extracted=st.integers(0, 3000),
    ratio=st.floats(0.05, 1.0),
    minimum=st.integers(1, 6000),
)
def test_truncation_property_accessible_only_with_enough_of_the_declared_text_and_the_minimum(
    declared: int | None, extracted: int, ratio: float, minimum: int
) -> None:
    content = text_of_words(extracted)
    thresholds = AccessThresholds(minimum_characters=minimum, truncation_ratio=ratio)
    decision = classify(response(200, page(word_count=declared)), content, thresholds=thresholds)
    if declared is not None and extracted < ratio * declared:
        expected = PAYWALLED
    elif content.quality.character_count < minimum:
        expected = ERROR
    else:
        expected = ACCESSIBLE
    event(f"expected: {expected.value}")
    assert decision.status is expected


# ---------------------------------------------------------------------------------------------
# Saved samples (plan node sample-suite)
# ---------------------------------------------------------------------------------------------

SAMPLES: Final = load_expected_statuses()


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_saved_sample_gets_its_expected_status(name: str) -> None:
    """Each synthetic sample, served as `expected_statuses.json` says, through the real HTML extractor."""
    entry = SAMPLES[name]
    fetched = response(entry["status_code"], sample_bytes(entry["file"]), headers=entry["headers"])
    extraction: ExtractedContent | ExtractionError | None = None
    if entry["extracted"]:
        try:
            extraction = TrafilaturaExtractor().extract(fetched)
        except ExtractionError as refusal:
            extraction = refusal
    decision = AccessClassifier().classify(fetched, extraction)
    assert decision.status is AccessStatus(entry["status"])
    assert marker_id(decision) == entry["marker_id"]
    assert decision.evidence.declared_words == entry["declared_words"]
    assert decision.rules_version == RULES_VERSION
    if isinstance(extraction, ExtractedContent):
        recorded = decision.model_dump_json()
        assert not [paragraph for paragraph in extraction.paragraphs if paragraph[:40] in recorded]

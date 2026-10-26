"""Access classification: one AccessStatus for every retrieval outcome (v1-e04-t03).

:class:`AccessClassifier` reads what the fetcher returned
(:class:`~debate_core.retrieval.fetch_types.FetchResult`, v1-e04-t02) and, for a fetched document,
what extraction made of it (an
:class:`~debate_core.retrieval.extraction.ExtractedContent` or the
:class:`~debate_core.retrieval.extraction.ExtractionError` it raised, v1-e04-t04), and answers with
exactly one :class:`~debate_core.domain.AccessStatus` in an :class:`AccessDecision`: the status, a
sentence for a person, the evidence it rests on, and the version of the marker rules it used.

**It classifies and does nothing else.** It makes no request, retries nothing, and never tries other
headers, cookies, archive mirrors or any other way round a wall. A page that is not plainly open is
not ACCESSIBLE, and there is no partly readable answer: a metered or truncated page is PAYWALLED.
Reasons and evidence hold status codes, counts, marker ids and the fetcher's and extractor's own
messages (which name hosts and types), never a word of the page.

## The mapping

A fetch that produced no response is decided by its error:

| Fetch error | Status |
|---|---|
| `RobotsDisallowed` (disallowed, robots.txt denied or unreachable) | ROBOTS_DISALLOWED |
| `Timeout`, `TooLarge`, `TooManyRedirects`, `TransportError` | ERROR |
| `UnsupportedScheme` (a redirect left http and https) | ERROR |
| `NonPublicAddress` (the platform does not fetch private addresses) | ERROR |

A 4xx or 5xx (`HttpStatusError`) is decided by its status, and for four statuses by the markers in
its body:

| Status | Status given |
|---|---|
| 404, 410 | NOT_FOUND, whatever the page carries |
| 402 | PAYWALLED |
| 451 | BLOCKED |
| 401 | BLOCKED on a challenge marker, else PAYWALLED (a login wall) |
| 403 | BLOCKED on a challenge marker, PAYWALLED on a paywall marker, else BLOCKED |
| 429, 503 | BLOCKED on a challenge marker, else ERROR (a throttle or an outage) |
| any other 4xx or 5xx | ERROR |

Any other response without a whole document is ERROR: no response at all, a 1xx or 3xx, a 204 or
205 (no content) and a 206 (part of a document). A 2xx document then goes through these steps, and
the first that answers decides:

1. A challenge marker (headers, and the page when it is HTML): BLOCKED.
2. Bytes no extractor reads (:func:`~debate_core.retrieval.extraction.document_kind`): UNSUPPORTED_TYPE.
3. The extractor's :class:`~debate_core.retrieval.extraction.PaywallMarkerFound` (schema.org
   `isAccessibleForFree: false`, which t04 reads and refuses on): PAYWALLED.
4. A paywall marker in an HTML page: PAYWALLED.
5. Any other extraction refusal: UNSUPPORTED_TYPE for `UnsupportedContentType` and for
   `EncryptedDocument` (proposed in the session report; the PM decides), ERROR for
   `DocumentTooLarge`, `TooManyPages`, `UnreadableDocument` and any refusal not listed.
6. No extraction at all: ERROR, since nothing says the text is complete.
7. The truncation heuristic (below): PAYWALLED or ERROR.
8. Otherwise ACCESSIBLE.

## Markers

The markers are data, in the versioned `paywall_rules.v1.json` beside this module, and every
decision carries the file's version. Each marker matches one thing a page is read for: a response
header, a `<script src>`, an inline script, a class token or id, a `<meta>` name or property with its
content, the title, or a phrase of visible text (outside scripts, styles, templates and the title).
Everything but an inline script is compared lower-cased with runs of whitespace as one space, and
a right single quotation mark read as an apostrophe. Within each list the first marker that
matches is the one recorded.

A page is decoded for markers only, never for its text: by its byte-order mark, else as UTF-8 with
undecodable bytes replaced. Every marker is ASCII, so a page in any ASCII-compatible encoding reads
the same. It is parsed with the standard library's `html.parser`, because lxml stays inside the
adapters (the import contracts in the workspace root).

## The truncation heuristic

The declared article length is the page's own: the largest of its JSON-LD nodes' `wordCount`
(an integer, or a string of digits with optional thousands commas) and the word count of their
`articleBody`, read from top-level JSON-LD nodes and `@graph` members. Only the count is kept. A
value that is not a positive whole number is no declaration. Then:

* with a declared length, fewer extracted words than `truncation_ratio` times that length is
  PAYWALLED: the page says there is more than it gave;
* with or without one, fewer extracted characters than `minimum_characters` is ERROR: too little
  text to be an article, and nothing on the page to say why. t04's empty extraction (no paragraphs,
  0 characters, `fallback_used`) lands here, or on the first rule when a length is declared.

With no declared length the minimum is the only test of length, and a page passes it only with no
marker and enough text; a length is never estimated. The thresholds are an :class:`AccessThresholds`
given to the classifier, which ArticleService (v1-e04-t05) builds from settings.
"""

from __future__ import annotations

import functools
import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from html.parser import HTMLParser
from importlib import resources
from typing import Annotated, Any, Final, Literal, Self, cast

from pydantic import AfterValidator, Field, model_validator

from debate_core.domain import AccessStatus, DomainModel, NonEmptyText
from debate_core.retrieval.extraction import (
    DocumentKind,
    DocumentTooLarge,
    EncryptedDocument,
    ExtractedContent,
    ExtractionError,
    PaywallMarkerFound,
    TooManyPages,
    UnreadableDocument,
    UnsupportedContentType,
    document_kind,
)
from debate_core.retrieval.fetch_types import (
    FetchErrorBase,
    FetchResult,
    HttpStatusError,
    NonPublicAddress,
    RobotsDisallowed,
    Timeout,
    TooLarge,
    TooManyRedirects,
    TransportError,
    UnsupportedScheme,
)

__all__ = [
    "EXTRACTOR_MARKER_ID",
    "PAYWALL_RULES_FILE",
    "AccessClassifier",
    "AccessDecision",
    "AccessEvidence",
    "AccessThresholds",
    "ClassOrIdMarker",
    "DeclaredLengthSource",
    "HeaderMarker",
    "InlineScriptMarker",
    "Marker",
    "MarkerCategory",
    "MatchedMarker",
    "MetaMarker",
    "PaywallRules",
    "ScriptSourceMarker",
    "TitleMarker",
    "VisibleTextMarker",
    "bundled_paywall_rules",
]

PAYWALL_RULES_FILE: Final = "paywall_rules.v1.json"
"""The bundled marker rules. A change to the markers is a new file, with a new version inside it."""

EXTRACTOR_MARKER_ID: Final = "extractor-is-accessible-for-free"
"""The marker id recorded when the HTML extractor refused a page for `isAccessibleForFree: false`."""


# --------------------------------------------------------------------------------------------
# The marker rules
# --------------------------------------------------------------------------------------------


def _normalized(value: str) -> str:
    if not value or value != " ".join(value.lower().split()):
        raise ValueError(
            f"{value!r} must be non-empty, lower-case and single-spaced, with no space at either end"
        )
    return value


type Normalized = Annotated[str, AfterValidator(_normalized)]
"""A marker pattern as the rules file must write it: already in the form the page is compared in."""


class MarkerCategory(StrEnum):
    """What a matched marker says about the page."""

    PAYWALL = "paywall"
    """A subscription, metering, registration or login wall: PAYWALLED."""

    CHALLENGE = "challenge"
    """A bot challenge, CAPTCHA or block page in place of the page: BLOCKED."""


class _MarkerBase(DomainModel):
    id: Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")] = Field(
        description="Stable name, recorded in the decision's reason and evidence."
    )
    description: NonEmptyText = Field(description="What the marker is, for a person reading a decision.")


class HeaderMarker(_MarkerBase):
    """A response header whose value contains a string."""

    kind: Literal["header"] = "header"
    name: Normalized = Field(description="The header's name, lower-case.")
    contains: Normalized


class ScriptSourceMarker(_MarkerBase):
    """A `<script src>` containing a string, such as a paywall vendor's host."""

    kind: Literal["script_src"] = "script_src"
    contains: Normalized


class InlineScriptMarker(_MarkerBase):
    """An inline `<script>` containing a string, compared as written (script is case-sensitive)."""

    kind: Literal["inline_script"] = "inline_script"
    contains: NonEmptyText


class ClassOrIdMarker(_MarkerBase):
    """An element with this class token or this id."""

    kind: Literal["class_or_id"] = "class_or_id"
    token: Normalized


class MetaMarker(_MarkerBase):
    """A `<meta>` with this `name` or `property` and exactly this content."""

    kind: Literal["meta"] = "meta"
    name: Normalized
    content: Normalized


class TitleMarker(_MarkerBase):
    """A page whose whole title is this."""

    kind: Literal["title"] = "title"
    equals: Normalized


class VisibleTextMarker(_MarkerBase):
    """A phrase anywhere in the page's visible text."""

    kind: Literal["visible_text"] = "visible_text"
    phrase: Normalized


type Marker = Annotated[
    HeaderMarker
    | ScriptSourceMarker
    | InlineScriptMarker
    | ClassOrIdMarker
    | MetaMarker
    | TitleMarker
    | VisibleTextMarker,
    Field(discriminator="kind"),
]
"""Any one marker, told apart by `kind` in the rules file."""


class PaywallRules(DomainModel):
    """The versioned marker lists the classifier reads pages with."""

    version: NonEmptyText = Field(description="Carried by every decision made with these rules.")
    description: NonEmptyText
    challenge_markers: tuple[Marker, ...] = Field(
        min_length=1, description="Tried first; a match is BLOCKED."
    )
    paywall_markers: tuple[Marker, ...] = Field(min_length=1, description="A match is PAYWALLED.")

    @model_validator(mode="after")
    def _check_ids_are_unique(self) -> Self:
        ids = [marker.id for marker in (*self.challenge_markers, *self.paywall_markers)]
        duplicates = sorted({marker_id for marker_id in ids if ids.count(marker_id) > 1})
        if duplicates:
            raise ValueError(f"marker ids must be unique; repeated: {', '.join(duplicates)}")
        return self


@functools.cache
def bundled_paywall_rules() -> PaywallRules:
    """The rules shipped with this package, read once per process."""
    text = resources.files("debate_core.retrieval").joinpath(PAYWALL_RULES_FILE).read_text(encoding="utf-8")
    return PaywallRules.model_validate_json(text)


# --------------------------------------------------------------------------------------------
# The decision
# --------------------------------------------------------------------------------------------


class AccessThresholds(DomainModel):
    """The truncation heuristic's two numbers; ArticleService (v1-e04-t05) passes them from settings."""

    minimum_characters: int = Field(
        default=500, ge=1, description="Fewer extracted characters than this is too little to be an article."
    )
    truncation_ratio: float = Field(
        default=0.5,
        gt=0,
        le=1,
        description="Fewer extracted words than this share of the declared length is a truncated page.",
    )


class DeclaredLengthSource(StrEnum):
    """Where a page's declared article length was read."""

    JSON_LD_WORD_COUNT = "json_ld_word_count"
    """schema.org `wordCount` in the page's JSON-LD."""

    JSON_LD_ARTICLE_BODY = "json_ld_article_body"
    """The number of words in the JSON-LD `articleBody`; its text is never kept."""


class MatchedMarker(DomainModel):
    """The marker that decided a page."""

    category: MarkerCategory
    marker_id: NonEmptyText = Field(description=f"The rule's id, or `{EXTRACTOR_MARKER_ID}`.")
    pattern: NonEmptyText = Field(description="What the rule looks for, or the extractor's description.")


class AccessEvidence(DomainModel):
    """What a decision rests on. Counts, codes and ids only; never page text."""

    status_code: int | None = Field(default=None, description="The response's status, when one arrived.")
    fetch_error: str | None = Field(default=None, description="The fetch error's `kind`, when there was one.")
    extraction_refusal: str | None = Field(default=None, description="The extraction error's type name.")
    marker: MatchedMarker | None = None
    extracted_characters: int | None = Field(default=None, ge=0)
    extracted_words: int | None = Field(default=None, ge=0)
    declared_words: int | None = Field(default=None, ge=1, description="The page's declared article length.")
    declared_length_source: DeclaredLengthSource | None = None
    thresholds: AccessThresholds | None = Field(
        default=None, description="The thresholds the truncation heuristic used, when it ran."
    )


class AccessDecision(DomainModel):
    """One retrieval outcome's access status, why, on what evidence, under which rules."""

    status: AccessStatus
    reason: NonEmptyText = Field(description="One sentence for a person.")
    evidence: AccessEvidence
    rules_version: NonEmptyText = Field(description="The marker rules' version.")

    @model_validator(mode="after")
    def _check_status_is_a_decision(self) -> Self:
        if self.status is AccessStatus.UNKNOWN:
            raise ValueError("an access decision is never UNKNOWN; that is the state before a fetch")
        return self


# --------------------------------------------------------------------------------------------
# The tables
# --------------------------------------------------------------------------------------------

_FETCH_ERRORS: Final[Mapping[type[FetchErrorBase], tuple[AccessStatus, str]]] = {
    RobotsDisallowed: (AccessStatus.ROBOTS_DISALLOWED, "robots.txt keeps the platform from this URL"),
    Timeout: (AccessStatus.ERROR, "The fetch ran out of time"),
    TooLarge: (AccessStatus.ERROR, "The document is larger than the fetcher's limit"),
    TooManyRedirects: (AccessStatus.ERROR, "The URL redirected too many times"),
    UnsupportedScheme: (AccessStatus.ERROR, "A redirect left http and https"),
    NonPublicAddress: (AccessStatus.ERROR, "The URL names an address that is not public"),
    TransportError: (AccessStatus.ERROR, "The connection failed"),
}

_REFUSALS: Final[Mapping[type[ExtractionError], AccessStatus]] = {
    UnsupportedContentType: AccessStatus.UNSUPPORTED_TYPE,
    EncryptedDocument: AccessStatus.UNSUPPORTED_TYPE,
    DocumentTooLarge: AccessStatus.ERROR,
    TooManyPages: AccessStatus.ERROR,
    UnreadableDocument: AccessStatus.ERROR,
}

_NOT_FOUND: Final = frozenset({404, 410})
_MARKER_STATUSES: Final = frozenset({401, 403, 429, 503})
"""Refusals whose body can be a challenge page, which is a different answer from the refusal."""
_STATUS_REASONS: Final = {
    401: "The server requires a login (401)",
    402: "The server requires payment (402)",
    403: "The server refused the request (403)",
    404: "The server has no document at this URL (404)",
    410: "The server says the document is gone (410)",
    429: "The server is turning away requests (429, too many requests)",
    451: "The server withholds the document for legal reasons (451)",
}
_NO_CONTENT: Final = frozenset({204, 205})
_PARTIAL_CONTENT: Final = 206

_WORD_COUNT: Final = re.compile(r"\d{1,3}(?:,\d{3})+|\d+")


# --------------------------------------------------------------------------------------------
# The classifier
# --------------------------------------------------------------------------------------------


class AccessClassifier:
    """Gives every retrieval outcome exactly one AccessStatus. Reads values; makes no request."""

    def __init__(
        self, *, rules: PaywallRules | None = None, thresholds: AccessThresholds | None = None
    ) -> None:
        self._rules = rules if rules is not None else bundled_paywall_rules()
        self._thresholds = thresholds if thresholds is not None else AccessThresholds()

    @property
    def rules_version(self) -> str:
        return self._rules.version

    def classify(
        self, fetched: FetchResult, extraction: ExtractedContent | ExtractionError | None
    ) -> AccessDecision:
        """The access decision for `fetched`.

        `extraction` is what the extractor returned or raised for a 2xx document, or None when it
        was not run. It is not read for any other response.
        """
        error = fetched.error
        evidence = AccessEvidence(
            status_code=fetched.status_code, fetch_error=error.kind if error is not None else None
        )
        if error is not None and not isinstance(error, HttpStatusError):
            status, headline = _FETCH_ERRORS[type(error)]
            return self._decision(status, f"{headline}: {error.message}", evidence)
        code = fetched.status_code
        if code is None:
            return self._decision(
                AccessStatus.ERROR, "No response arrived, and the fetcher recorded no error", evidence
            )
        if code >= 400:
            return self._error_status(fetched, code, evidence)
        if not 200 <= code < 300:
            return self._decision(AccessStatus.ERROR, f"The response was {code}, not a document", evidence)
        if code in _NO_CONTENT:
            return self._decision(AccessStatus.ERROR, f"The response was {code}, with no content", evidence)
        if code == _PARTIAL_CONTENT:
            return self._decision(
                AccessStatus.ERROR,
                "The response was 206, partial content: part of a document is not one",
                evidence,
            )
        return self._document(fetched, extraction, evidence)

    def _error_status(self, fetched: FetchResult, code: int, evidence: AccessEvidence) -> AccessDecision:
        reason = _STATUS_REASONS.get(code, f"The server answered {code}")
        if code in _NOT_FOUND:
            return self._decision(AccessStatus.NOT_FOUND, reason, evidence)
        if code == 402:
            return self._decision(AccessStatus.PAYWALLED, reason, evidence)
        if code == 451:
            return self._decision(AccessStatus.BLOCKED, reason, evidence)
        if code in _MARKER_STATUSES:
            page = _PageSignals.read(fetched, html=_is_html(fetched))
            challenge = _first_match(self._rules.challenge_markers, page)
            if challenge is not None:
                return self._marked(MarkerCategory.CHALLENGE, challenge, evidence, f"{reason}, with")
            if code == 401:
                return self._decision(AccessStatus.PAYWALLED, reason, evidence)
            if code == 403:
                wall = _first_match(self._rules.paywall_markers, page)
                if wall is not None:
                    return self._marked(MarkerCategory.PAYWALL, wall, evidence, f"{reason}, with")
                return self._decision(AccessStatus.BLOCKED, reason, evidence)
        return self._decision(AccessStatus.ERROR, reason, evidence)

    def _document(
        self,
        fetched: FetchResult,
        extraction: ExtractedContent | ExtractionError | None,
        evidence: AccessEvidence,
    ) -> AccessDecision:
        try:
            kind: DocumentKind | None = document_kind(fetched)
            unsupported = None
        except UnsupportedContentType as refusal:
            kind, unsupported = None, refusal
        page = _PageSignals.read(fetched, html=kind is DocumentKind.HTML)
        challenge = _first_match(self._rules.challenge_markers, page)
        if challenge is not None:
            return self._marked(
                MarkerCategory.CHALLENGE, challenge, evidence, "A bot challenge was served, with"
            )
        if unsupported is not None:
            return self._decision(AccessStatus.UNSUPPORTED_TYPE, _sentence(str(unsupported)), evidence)
        if isinstance(extraction, ExtractionError):
            evidence = evidence.evolve(extraction_refusal=type(extraction).__name__)
        if isinstance(extraction, PaywallMarkerFound):
            found = MatchedMarker(
                category=MarkerCategory.PAYWALL, marker_id=EXTRACTOR_MARKER_ID, pattern=extraction.marker
            )
            return self._decision(
                AccessStatus.PAYWALLED,
                f"The page declares itself paywalled ({extraction.marker}, found by the HTML extractor)",
                evidence.evolve(marker=found),
            )
        wall = _first_match(self._rules.paywall_markers, page)
        if wall is not None:
            return self._marked(MarkerCategory.PAYWALL, wall, evidence, "The page is behind a paywall:")
        if isinstance(extraction, ExtractionError):
            status = _REFUSALS.get(type(extraction), AccessStatus.ERROR)
            return self._decision(
                status, _sentence(f"the extractor refused the document: {extraction}"), evidence
            )
        if extraction is None:
            return self._decision(
                AccessStatus.ERROR,
                "The document was not extracted, so nothing shows its text is complete",
                evidence,
            )
        return self._truncation(extraction, page, evidence)

    def _truncation(
        self, content: ExtractedContent, page: _PageSignals, evidence: AccessEvidence
    ) -> AccessDecision:
        thresholds = self._thresholds
        words = len(content.text.split())
        characters = content.quality.character_count
        declared = _declared_length(page.json_ld)
        evidence = evidence.evolve(
            extracted_characters=characters,
            extracted_words=words,
            declared_words=declared[0] if declared else None,
            declared_length_source=declared[1] if declared else None,
            thresholds=thresholds,
        )
        if declared is not None and words < thresholds.truncation_ratio * declared[0]:
            return self._decision(
                AccessStatus.PAYWALLED,
                f"The page declares {declared[0]} words and {words} were extracted, under "
                f"{thresholds.truncation_ratio:.0%} of them: the rest is withheld",
                evidence,
            )
        if characters < thresholds.minimum_characters:
            return self._decision(
                AccessStatus.ERROR,
                f"Only {characters} characters were extracted, under the {thresholds.minimum_characters}-"
                "character minimum for an article",
                evidence,
            )
        of_declared = f" of {declared[0]} declared" if declared else ""
        return self._decision(
            AccessStatus.ACCESSIBLE, f"The text was extracted: {words} words{of_declared}", evidence
        )

    def _marked(
        self, category: MarkerCategory, marker: Marker, evidence: AccessEvidence, lead: str
    ) -> AccessDecision:
        status = AccessStatus.BLOCKED if category is MarkerCategory.CHALLENGE else AccessStatus.PAYWALLED
        found = MatchedMarker(category=category, marker_id=marker.id, pattern=_pattern(marker))
        noun = "challenge" if category is MarkerCategory.CHALLENGE else "paywall"
        return self._decision(
            status,
            f"{lead} {noun} marker {marker.id} ({marker.description.rstrip('.')})",
            evidence.evolve(marker=found),
        )

    def _decision(self, status: AccessStatus, reason: str, evidence: AccessEvidence) -> AccessDecision:
        return AccessDecision(
            status=status, reason=reason, evidence=evidence, rules_version=self._rules.version
        )


def _sentence(text: str) -> str:
    """`text` with its first letter capitalized and nothing else changed."""
    return text[:1].upper() + text[1:]


def _is_html(fetched: FetchResult) -> bool:
    try:
        return document_kind(fetched) is DocumentKind.HTML
    except UnsupportedContentType:
        return False


def _pattern(marker: Marker) -> str:
    match marker:
        case HeaderMarker():
            return f"header {marker.name} contains {marker.contains}"
        case ScriptSourceMarker():
            return f"script src contains {marker.contains}"
        case InlineScriptMarker():
            return f"inline script contains {marker.contains}"
        case ClassOrIdMarker():
            return f"class or id {marker.token}"
        case MetaMarker():
            return f"meta {marker.name} = {marker.content}"
        case TitleMarker():
            return f"title is {marker.equals}"
        case VisibleTextMarker():
            return f"text {marker.phrase}"


# --------------------------------------------------------------------------------------------
# Reading a page
# --------------------------------------------------------------------------------------------

_UTF16_BOMS: Final = ((b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"))
_HIDDEN: Final = frozenset({"template"})
"""Elements whose content is markup but not shown. Script and style are raw text to the parser."""


def _comparable(text: str) -> str:
    return " ".join(text.lower().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'").split())


@dataclass(frozen=True)
class _PageSignals:
    """What the markers are matched against, read once per page."""

    headers: Mapping[str, str]
    script_sources: tuple[str, ...] = ()
    inline_scripts: tuple[str, ...] = ()
    tokens: frozenset[str] = frozenset()
    metas: frozenset[tuple[str, str]] = frozenset()
    title: str | None = None
    visible_text: str = ""
    json_ld: tuple[str, ...] = ()

    @classmethod
    def read(cls, fetched: FetchResult, *, html: bool) -> _PageSignals:
        headers = {name.lower(): _comparable(value) for name, value in fetched.headers.items()}
        if not html:
            return cls(headers=headers)
        reader = _PageReader()
        reader.feed(_decode_for_markers(fetched.body))
        reader.close()
        return cls(
            headers=headers,
            script_sources=tuple(reader.script_sources),
            inline_scripts=tuple(reader.inline_scripts),
            tokens=frozenset(reader.tokens),
            metas=frozenset(reader.metas),
            title=_comparable(reader.title) if reader.title is not None else None,
            visible_text=_comparable(" ".join(reader.visible)),
            json_ld=tuple(reader.json_ld),
        )


def _decode_for_markers(body: bytes) -> str:
    for bom, encoding in _UTF16_BOMS:
        if body.startswith(bom):
            return body[len(bom) :].decode(encoding, errors="replace")
    return body.decode("utf-8", errors="replace").removeprefix("\N{ZERO WIDTH NO-BREAK SPACE}")


class _PageReader(HTMLParser):
    """Collects the parts of a page the markers look at."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.script_sources: list[str] = []
        self.inline_scripts: list[str] = []
        self.tokens: set[str] = set()
        self.metas: set[tuple[str, str]] = set()
        self.title: str | None = None
        self.visible: list[str] = []
        self.json_ld: list[str] = []
        self._in_raw_text = False
        self._raw_text_target: list[str] | None = None
        self._in_title = False
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        self.tokens.update(values.get("class", "").lower().split())
        if values.get("id", "").strip():
            self.tokens.add(values["id"].strip().lower())
        if tag == "script":
            if values.get("src", "").strip():
                self.script_sources.append(values["src"].strip().lower())
            is_json_ld = values.get("type", "").strip().lower() == "application/ld+json"
            target = self.json_ld if is_json_ld else self.inline_scripts
            target.append("")
            self._in_raw_text, self._raw_text_target = True, target
        elif tag == "style":
            self._in_raw_text, self._raw_text_target = True, None
        elif tag == "meta":
            content = _comparable(values.get("content", ""))
            for attribute in ("name", "property"):
                if values.get(attribute, "").strip():
                    self.metas.add((_comparable(values[attribute]), content))
        elif tag == "title" and self.title is None:
            self._in_title, self.title = True, ""
        elif tag in _HIDDEN:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._in_raw_text, self._raw_text_target = False, None
        elif tag == "title":
            self._in_title = False
        elif tag in _HIDDEN and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_raw_text:
            if self._raw_text_target is not None:
                self._raw_text_target[-1] += data
        elif self._in_title:
            self.title = (self.title or "") + data
        elif not self._hidden_depth:
            self.visible.append(data)


# --------------------------------------------------------------------------------------------
# Matching and the declared length
# --------------------------------------------------------------------------------------------


def _first_match(markers: tuple[Marker, ...], page: _PageSignals) -> Marker | None:
    return next((marker for marker in markers if _matches(marker, page)), None)


def _matches(marker: Marker, page: _PageSignals) -> bool:
    match marker:
        case HeaderMarker():
            return marker.contains in page.headers.get(marker.name, "")
        case ScriptSourceMarker():
            return any(marker.contains in source for source in page.script_sources)
        case InlineScriptMarker():
            return any(marker.contains in script for script in page.inline_scripts)
        case ClassOrIdMarker():
            return marker.token in page.tokens
        case MetaMarker():
            return (marker.name, marker.content) in page.metas
        case TitleMarker():
            return page.title == marker.equals
        case VisibleTextMarker():
            return marker.phrase in page.visible_text


def _declared_length(json_ld: tuple[str, ...]) -> tuple[int, DeclaredLengthSource] | None:
    """The longest length the page's JSON-LD declares, and where it was read; None when it declares none."""
    best: tuple[int, DeclaredLengthSource] | None = None
    for node in _json_ld_nodes(json_ld):
        for words, source in (
            (_word_count(node.get("wordCount")), DeclaredLengthSource.JSON_LD_WORD_COUNT),
            (_body_words(node.get("articleBody")), DeclaredLengthSource.JSON_LD_ARTICLE_BODY),
        ):
            if words is not None and (best is None or words > best[0]):
                best = (words, source)
    return best


def _json_ld_nodes(blocks: tuple[str, ...]) -> Iterator[dict[str, Any]]:
    """Every top-level JSON-LD node, `@graph` members included; a block that is not JSON is skipped."""
    for block in blocks:
        try:
            parsed: object = json.loads(block)
        except ValueError:
            continue
        for node in cast(list[object], parsed) if isinstance(parsed, list) else [parsed]:
            if isinstance(node, dict):
                typed = cast(dict[str, Any], node)
                yield typed
                graph = typed.get("@graph")
                if isinstance(graph, list):
                    members = cast(list[object], graph)
                    yield from (
                        cast(dict[str, Any], member) for member in members if isinstance(member, dict)
                    )


def _word_count(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and _WORD_COUNT.fullmatch(value.strip()):
        count = int(value.strip().replace(",", ""))
        return count if count > 0 else None
    return None


def _body_words(value: object) -> int | None:
    return (len(value.split()) or None) if isinstance(value, str) else None

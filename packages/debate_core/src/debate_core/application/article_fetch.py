"""`debate-research fetch`'s use case: one retrieval or one pasted text, reported (v1-e04-t06).

:class:`~debate_core.application.article_service.ArticleService` (v1-e04-t05) decides everything:
whether a page is readable, what is stored, and why not. :class:`ArticleFetch` asks it one question
per run and turns the answer into a :class:`FetchReport`, the one shape the command prints for a
person and for a program. It adds two things the outcome does not carry:

* **The paragraph count**, read from the snapshot as stored. The snapshot is loaded through
  :meth:`~debate_core.application.snapshot_service.SnapshotService.load`, which re-hashes both blobs
  against the record, so a report that names a snapshot names one that is on this machine and whose
  hashes hold. A snapshot that fails that check is the
  :class:`~debate_core.application.errors.SnapshotIntegrityError` it raises, never a report.
* **The connection's lifetime.** The fetcher holds an HTTP client, which belongs to the event loop
  that used it; :class:`ArticleFetch` is an async context manager that closes it on the way out.

## What a report holds

URLs, the title the article is stored under, its identifiers, the access status with the
classifier's reason, rules version and evidence (status codes, counts, marker ids: never page text,
v1-e04-t03), and the snapshot's id, hashes, versions and paragraph count. Never a word of the page or
of the pasted text: evidence text is not output (architecture proposal §8).

## The published result

:func:`render_fetch_result_schema` is the JSON Schema of the command's `--json` output, written to
`packages/debate_core/schemas/fetch_result.v1.json` by `scripts/export_schemas.py`, beside
`verify_result.v1.json`.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import Any, Final, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from debate_core.application.article_service import (
    ArticleService,
    InvalidSourceUrl,
    RetrievalOutcome,
    UserTextNotAttested,
    UserTextRejected,
)
from debate_core.application.errors import ProviderUnavailable, error_code_of_class
from debate_core.application.snapshot_service import SnapshotService
from debate_core.domain import AccessStatus, ArticleIdentifiers, ProvenanceMode
from debate_core.domain.schema_export import JSON_SCHEMA_DIALECT
from debate_core.retrieval.access import AccessEvidence

__all__ = [
    "FETCH_RESULT_SCHEMA_FILENAME",
    "SOURCE_NOT_ACCESSIBLE_CODE",
    "ArticleFetch",
    "Closeable",
    "FetchReport",
    "SnapshotSummary",
    "render_fetch_result_schema",
]

FETCH_RESULT_SCHEMA_FILENAME: Final = "fetch_result.v1.json"
"""The committed schema of `debate-research --json fetch`'s output, in `packages/debate_core/schemas/`."""

SOURCE_NOT_ACCESSIBLE_CODE: Final = "SOURCE_NOT_ACCESSIBLE"
"""The error code of a retrieval whose status is not ACCESSIBLE; the status itself is in the report.

One code for every status, because the statuses' own names are taken: `NOT_FOUND` is already the
code of :class:`~debate_core.application.errors.NotFound`, a record this machine does not have.
"""

_REFUSAL_CODES: Final = tuple(
    error_code_of_class(refusal) for refusal in (InvalidSourceUrl, UserTextNotAttested, UserTextRejected)
)
"""The error codes of ArticleService's three refusals (exit 1): `INVALID_SOURCE_URL` and the two others."""


class Closeable(Protocol):
    """What holds the fetcher's connections: closed when the run is done."""

    async def aclose(self) -> None: ...


class SnapshotSummary(BaseModel):
    """The stored snapshot a report names: ids, hashes, versions and counts, no text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: str
    provenance_mode: ProvenanceMode = Field(
        description="PUBLISHER_RETRIEVED, or USER_SUPPLIED for pasted text."
    )
    access_status: AccessStatus = Field(description="The status recorded on the snapshot.")
    sha256: str = Field(description="SHA-256 of the raw bytes, as stored.")
    normalized_text_hash: str = Field(description="SHA-256 of the normalized text.")
    paragraph_count: int = Field(ge=0, description="Paragraphs in the normalized text, as stored.")
    extractor_version: str
    normalizer_version: str
    content_type: str | None
    byte_size: int | None
    retrieved_at: AwareDatetime
    reused: bool = Field(description="Whether the snapshot was already stored before this run.")


class FetchReport(BaseModel):
    """One run of `debate-research fetch`: the article, its access status and the snapshot, if any."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    correlation_id: str
    requested_url: str = Field(description="The URL as given (the source URL, for pasted text).")
    canonical_url: str = Field(description="The identity key the article is stored under.")
    final_url: str | None = Field(
        description="The URL that answered, after redirects; null when nothing was fetched."
    )
    article_id: str
    title: str = Field(
        description="The article's stored title: the page's own, or its URL when it gave none."
    )
    identifiers: ArticleIdentifiers
    access_status: AccessStatus
    reason: str = Field(description="One sentence for a person: why this status, or why no fetch was needed.")
    rules_version: str | None = Field(description="The paywall marker rules that classified the page.")
    evidence: AccessEvidence | None = Field(
        description="What the classification rests on; null when nothing was classified."
    )
    fetched: bool = Field(description="Whether the publisher was asked.")
    provenance_mode: ProvenanceMode | None = Field(
        description="The snapshot's provenance; null with no snapshot."
    )
    snapshot: SnapshotSummary | None = Field(
        description="The stored snapshot; null for every status but ACCESSIBLE."
    )


class ArticleFetch:
    """Retrieves one URL, or stores one pasted text, through ArticleService, and reports it."""

    def __init__(
        self, *, articles: ArticleService, snapshots: SnapshotService, connection: Closeable
    ) -> None:
        self._articles = articles
        self._snapshots = snapshots
        self._connection = connection

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._connection.aclose()

    async def retrieve(self, url: str, *, refresh: bool = False) -> FetchReport:
        """Retrieve `url`; `refresh` asks the publisher even when a stored snapshot is fresh.

        A refused or failed retrieval is a report with its status and no snapshot. Raises
        :class:`~debate_core.application.article_service.InvalidSourceUrl` for a URL with no
        canonical form.
        """
        return await self._report(await self._articles.retrieve(url, refresh=refresh))

    async def ingest_pasted(self, *, source_url: str, text: str, attested: bool) -> FetchReport:
        """Store `text` as USER_SUPPLIED under the article for `source_url`; nothing is fetched.

        Raises what :meth:`ArticleService.ingest_user_text` raises, and then nothing is stored:
        `UserTextNotAttested` unless `attested` is True, `InvalidSourceUrl`, `UserTextRejected`.
        """
        outcome = await self._articles.ingest_user_text(source_url=source_url, text=text, attested=attested)
        return await self._report(outcome)

    async def _report(self, outcome: RetrievalOutcome) -> FetchReport:
        snapshot = outcome.snapshot
        summary = None
        if snapshot is not None:
            loaded = await self._snapshots.load(snapshot)
            summary = SnapshotSummary(
                snapshot_id=snapshot.snapshot_id,
                provenance_mode=snapshot.provenance_mode,
                access_status=snapshot.access_status,
                sha256=snapshot.sha256,
                normalized_text_hash=snapshot.normalized_text_hash,
                paragraph_count=len(loaded.normalized.paragraphs),
                extractor_version=snapshot.extractor_version,
                normalizer_version=snapshot.normalizer_version,
                content_type=snapshot.content_type,
                byte_size=snapshot.byte_size,
                retrieved_at=snapshot.retrieved_at,
                reused=outcome.snapshot_reused,
            )
        return FetchReport(
            correlation_id=outcome.correlation_id,
            requested_url=outcome.requested_url,
            canonical_url=outcome.canonical_url,
            final_url=outcome.final_url,
            article_id=outcome.article.article_id,
            title=outcome.article.title,
            identifiers=outcome.article.identifiers,
            access_status=outcome.access_status,
            reason=outcome.reason,
            rules_version=outcome.rules_version,
            evidence=outcome.decision.evidence if outcome.decision is not None else None,
            fetched=outcome.fetched,
            provenance_mode=snapshot.provenance_mode if snapshot is not None else None,
            snapshot=summary,
        )


def render_fetch_result_schema() -> dict[str, Any]:
    """The JSON Schema of `debate-research --json fetch`'s output, for every outcome but a bug.

    The CLI's standard envelope (``debate_cli.output``, ``schema_version`` 1) with this command's
    payloads in it: the report under ``data`` for an ACCESSIBLE page or stored pasted text (exit 0);
    the same report under ``error.details`` for any other status (exit 3); a refusal's facts for an
    invalid URL, unattested or rejected text (exit 1); and the CLI-wide shapes of a usage error
    (exit 2) and a fetcher that could not run (exit 3). The exit codes are numbers because
    ``debate_core`` cannot import the CLI's ``ExitCode``; the CLI's tests hold the two together.
    """
    report = FetchReport.model_json_schema(mode="serialization")
    definitions: dict[str, Any] = report.pop("$defs")
    definitions["FetchReport"] = report
    report_ref = {"$ref": "#/$defs/FetchReport"}
    accessible = {
        "allOf": [
            report_ref,
            {
                "properties": {"snapshot": {"$ref": "#/$defs/SnapshotSummary"}},
                "anyOf": [
                    {"properties": {"access_status": {"const": AccessStatus.ACCESSIBLE.value}}},
                    {"properties": {"provenance_mode": {"const": ProvenanceMode.USER_SUPPLIED.value}}},
                ],
            },
        ]
    }
    not_accessible = {
        "allOf": [
            report_ref,
            {
                "properties": {
                    "access_status": {"not": {"const": AccessStatus.ACCESSIBLE.value}},
                    "snapshot": {"type": "null"},
                    "provenance_mode": {"type": "null"},
                }
            },
        ]
    }

    def failure(code: Any, exit_code: int, details: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["code", "message", "exit_code", "details", "hint"],
            "properties": {
                "code": code,
                "message": {"type": "string"},
                "exit_code": {"const": exit_code},
                "details": details,
                "hint": {"type": ["string", "null"]},
            },
        }

    def outcome(title: str, status: str, data: Mapping[str, Any], error: Mapping[str, Any]) -> dict[str, Any]:
        return {"title": title, "properties": {"status": {"const": status}, "data": data, "error": error}}

    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "title": "debate-research fetch --json output",
        "description": (
            "One JSON object on stdout per run. Exit 0: the page is ACCESSIBLE, or pasted text was "
            "stored as USER_SUPPLIED; the report is under data. Exit 3: any other access status, with "
            "the report and no snapshot under error.details, or a fetcher that could not run. Exit 1: "
            "the URL names no source, or pasted text was not attested or was rejected; nothing was "
            "stored. Exit 2: usage error."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "status", "command", "data", "error"],
        "properties": {
            "schema_version": {"const": 1},
            "status": {"enum": ["ok", "error"]},
            "command": {"type": ["string", "null"]},
            "data": True,
            "error": True,
        },
        "oneOf": [
            outcome("Readable, or pasted text stored (exit 0)", "ok", accessible, {"type": "null"}),
            outcome(
                "Not accessible (exit 3)",
                "error",
                {"type": "null"},
                failure({"const": SOURCE_NOT_ACCESSIBLE_CODE}, 3, not_accessible),
            ),
            outcome(
                "Refused: no source URL, unattested or rejected text (exit 1)",
                "error",
                {"type": "null"},
                failure({"enum": list(_REFUSAL_CODES)}, 1, {"type": "object"}),
            ),
            outcome(
                "Usage error (exit 2)",
                "error",
                {"type": "null"},
                failure({"const": "USAGE_ERROR"}, 2, {"type": "object"}),
            ),
            outcome(
                "The fetcher could not run (exit 3)",
                "error",
                {"type": "null"},
                failure({"const": error_code_of_class(ProviderUnavailable)}, 3, {"type": "object"}),
            ),
        ],
        "$defs": definitions,
    }

"""PlanTextService: each affirmative source's plan text, read from its own bytes and cached (`v1-e32-t09`).

The parsed card store keeps cards only, and a plan text is almost always an analytic, so the PM ruled
on 2026-10-24 to read the raw sources again in this task, through the
:class:`~debate_core.application.ports.debate_files.DebateFileParser` port, read-only. One run:

1. looks each source up in the caselist's plan-text cache, under (digest, parser version, vocabulary
   digest);
2. parses only the sources not there, through a
   :class:`~debate_core.application.caselist.parse_workers.ParseRunner` (a process pool for a real
   corpus), reading each source's bytes from this machine's blob store and checking they hash to
   their name, as `caselist parse` does;
3. keeps what :func:`~debate_core.arguments.landscape.plan_text.read_plan_texts` derives from each
   (never the text) and writes the cache back when anything changed, keeping every reading under the
   current parser and vocabulary and dropping those under any other;
4. returns each source's verdict
   (:func:`~debate_core.arguments.landscape.plan_text.document_plan_text`) with counts.

Beside t09's plan texts it reads and caches the plan texts under a transition label (`v1-e32-t24`,
:func:`~debate_core.arguments.landscape.plan_text.read_transition_plan_texts`) and returns their verdict
per source apart from t09's (:attr:`PlanTextRun.transition`), which they never change.

A source the parser refused is `UNREAD` and cached as unreadable. One whose bytes could not be read,
or whose worker failed, is `UNREAD` and not cached, so the next run tries it again. The parser is given
a placeholder path, never the disclosure's, so no school or team code reaches it.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_workers import LoadableJob, ParseJob, ParseRunner, SourceLoadError
from debate_core.application.caselist.publish_plan import local_blob_key
from debate_core.application.ports.debate_files import DebateFileParser
from debate_core.application.ports.parsed_store import PipelineFailureReason
from debate_core.application.ports.plan_text_store import (
    CachedKritikalMarker,
    CachedPlanText,
    CachedPlanTextParagraph,
    PlanTextStore,
)
from debate_core.arguments.landscape.kritikal_aff import (
    KritikalMarker,
    KritikalReading,
    read_kritikal_markers,
)
from debate_core.arguments.landscape.matcher import tag_words
from debate_core.arguments.landscape.plan_text import (
    DocumentPlanText,
    PlanTextParagraph,
    PlanTextVerdict,
    PlanTextVocabulary,
    document_plan_text,
    paragraphs_of,
    read_back_plan_texts,
    read_plan_texts,
    read_transition_plan_texts,
    sheet_plan_texts,
)
from debate_core.domain.caselist import SourceDocument
from debate_core.domain.debate_files import ParsedDocument, ParseFailure

__all__ = [
    "PLAN_TEXT_SOURCE_PATH",
    "PlanTextCounts",
    "PlanTextRun",
    "PlanTextService",
    "PlanTextWordsRun",
    "blob_jobs",
]

PLAN_TEXT_SOURCE_PATH: Final = "plan-text-reading.docx"
"""The path the parser is given in place of a disclosure path, which names a school and a team."""


@dataclass(frozen=True, slots=True)
class PlanTextCounts:
    sources: int
    hits: int
    parsed: int
    """Sources the parser read in this run."""
    refused: int
    """Sources the parser refused, in this run or cached."""
    unread: int
    """Sources whose bytes could not be read or whose worker failed in this run; not cached."""
    verdicts: dict[str, int]
    cache_written: bool


@dataclass(frozen=True, slots=True)
class PlanTextRun:
    parser_version: str
    vocabulary_digest: str
    verdicts: dict[str, DocumentPlanText] = field(repr=False)
    """Each source's verdict, by digest."""
    readings: dict[str, tuple[PlanTextParagraph, ...]] = field(repr=False)
    """What was read of each readable source's plan texts, by digest."""
    counts: PlanTextCounts
    kritikal: dict[str, KritikalReading] = field(default_factory=dict[str, KritikalReading], repr=False)
    """Each readable source's K-aff markers and heading families, by digest (`v1-e32-t17`)."""
    transition: dict[str, DocumentPlanText] = field(default_factory=dict[str, DocumentPlanText], repr=False)
    """Each readable source's verdict over its plan texts under a transition label, by digest
    (`v1-e32-t24`)."""


@dataclass(frozen=True, slots=True)
class PlanTextWordsRun:
    """The words of each source's sheet plan texts, for the coach's sheet only. Held in memory."""

    words: dict[str, tuple[str, ...]] = field(repr=False)
    parsed: int
    without_plan_text: int
    """Sources with no plan text the sheet shows; not parsed."""
    mismatched: int
    """Sources whose paragraphs no longer read as their reading says; left off the sheet."""
    unread: int
    texts: dict[str, tuple[str, ...]] = field(default_factory=dict[str, tuple[str, ...]], repr=False)
    """The same plan texts word for word, as the files hold them (data-use policy 1.13)."""


class PlanTextService:
    """Reads plan texts from a caselist's sources, parsing only what its cache does not hold."""

    def __init__(
        self, *, parser: DebateFileParser, runner: ParseRunner, store: PlanTextStore, local: LocalEvidence
    ) -> None:
        self._parser = parser
        self._runner = runner
        self._store = store
        self._local = local

    def without_writes(self) -> PlanTextService:
        """The same reading over a view of the cache that is never written: what a dry run reads with."""
        return PlanTextService(
            parser=self._parser,
            runner=self._runner,
            store=_UnwrittenPlanTexts(self._store),
            local=self._local,
        )

    async def read(
        self, caselist: str, sources: Sequence[SourceDocument], vocabulary: PlanTextVocabulary
    ) -> PlanTextRun:
        """Each source's verdict, parsing only those not cached under this parser and these words."""
        parser_version = self._parser.parser_version
        current = (parser_version, vocabulary.digest)
        everything = await self._store.read(caselist)
        cached = {
            entry.source_sha256: entry
            for entry in everything
            if (entry.parser_version, entry.vocabulary_digest) == current
        }
        stale = len(everything) - len(cached)
        wanted = {source.sha256: source for source in sources}
        missing = [source for sha, source in sorted(wanted.items()) if sha not in cached]
        written: dict[str, CachedPlanText] = {}
        unread: set[str] = set()
        for job, result in self._runner.run(
            self._parser, blob_jobs(missing, self._local, PLAN_TEXT_SOURCE_PATH)
        ):
            sha = job.source.sha256
            if isinstance(result, ParsedDocument):
                paragraphs, in_cards = paragraphs_of(result)
                found = read_plan_texts(paragraphs, in_cards, vocabulary)
                markers = read_kritikal_markers(paragraphs, vocabulary.kritikal)
                under_transition = read_transition_plan_texts(paragraphs, in_cards, vocabulary)
                written[sha] = _entry(
                    sha, parser_version, vocabulary.digest, found, markers, under_transition
                )
            elif isinstance(result, ParseFailure):
                written[sha] = CachedPlanText(
                    source_sha256=sha,
                    parser_version=parser_version,
                    vocabulary_digest=vocabulary.digest,
                    readable=False,
                )
            else:
                unread.add(sha)
        changed = bool(written) or stale > 0
        if changed:
            await self._store.replace(caselist, [*cached.values(), *written.values()])
        held = {**cached, **written}
        verdicts: dict[str, DocumentPlanText] = {}
        readings: dict[str, tuple[PlanTextParagraph, ...]] = {}
        kritikal: dict[str, KritikalReading] = {}
        transition: dict[str, DocumentPlanText] = {}
        for sha in sorted(wanted):
            entry = held.get(sha)
            if entry is None or not entry.readable:
                verdicts[sha] = DocumentPlanText(PlanTextVerdict.UNREAD)
                continue
            readings[sha] = tuple(_paragraph(one) for one in entry.paragraphs)
            verdicts[sha] = document_plan_text(readings[sha], vocabulary)
            kritikal[sha] = KritikalReading(
                markers=tuple(_marker(one) for one in entry.kritikal_markers),
                heading_families=entry.heading_families,
            )
            transition[sha] = document_plan_text(
                tuple(_paragraph(one) for one in entry.transition_paragraphs), vocabulary
            )
        refused = sum(1 for sha in wanted if (entry := held.get(sha)) is not None and not entry.readable)
        return PlanTextRun(
            parser_version=parser_version,
            vocabulary_digest=vocabulary.digest,
            verdicts=verdicts,
            readings=readings,
            counts=PlanTextCounts(
                sources=len(wanted),
                hits=sum(1 for sha in wanted if sha in cached),
                parsed=len(written),
                refused=refused,
                unread=len(unread),
                verdicts=dict(sorted(Counter(one.verdict.value for one in verdicts.values()).items())),
                cache_written=changed,
            ),
            kritikal=kritikal,
            transition=transition,
        )

    async def words(
        self, caselist: str, sources: Sequence[SourceDocument], run: PlanTextRun
    ) -> PlanTextWordsRun:
        """The words and the text of each source's sheet plan texts, parsed again and never written.

        Only sources whose reading in `run` holds a plan text the sheet shows are parsed.
        """
        wanted = {
            source.sha256: (source, shown)
            for source in sources
            if (shown := sheet_plan_texts(run.readings.get(source.sha256, ())))
        }
        words: dict[str, tuple[str, ...]] = {}
        texts: dict[str, tuple[str, ...]] = {}
        mismatched = unread = parsed = 0
        jobs = blob_jobs(
            [source for source, _ in (wanted[sha] for sha in sorted(wanted))],
            self._local,
            PLAN_TEXT_SOURCE_PATH,
        )
        for job, result in self._runner.run(self._parser, jobs):
            if not isinstance(result, ParsedDocument):
                unread += 1
                continue
            parsed += 1
            paragraphs, _ = paragraphs_of(result)
            found = read_back_plan_texts(paragraphs, wanted[job.source.sha256][1])
            if found is None:
                mismatched += 1
            else:
                texts[job.source.sha256] = found
                words[job.source.sha256] = tuple(word for text in found for word in tag_words(text).split())
        return PlanTextWordsRun(
            words=dict(sorted(words.items())),
            parsed=parsed,
            without_plan_text=len({source.sha256 for source in sources}) - len(wanted),
            mismatched=mismatched,
            unread=unread,
            texts=dict(sorted(texts.items())),
        )


def blob_jobs(
    sources: Sequence[SourceDocument], local: LocalEvidence, source_path: str
) -> Iterator[LoadableJob]:
    """A parse job per source, its bytes read from this machine's blob store and checked against its name.

    The parser is given `source_path`, a placeholder, never the disclosure's path. A source of a format the
    parser cannot read loads no bytes, so the parser refuses it by format. `v1-e32-t11`'s analytic texts are
    read the same way.
    """
    for source in sources:
        job = ParseJob(source=source, source_path=source_path, snapshot=source.last_seen_snapshot, camp=None)
        yield job, _loader(source, local)


def _loader(source: SourceDocument, local: LocalEvidence) -> Callable[[], bytes]:
    def load() -> bytes:
        if not source.is_parsable:
            return b""  # refused by format; the parser never reads the bytes
        path_for = local.blob_path_for
        if path_for is None:
            raise SourceLoadError(PipelineFailureReason.SOURCE_MISSING, "no local blob path")
        try:
            content = path_for(local_blob_key(source.sha256)).read_bytes()
        except FileNotFoundError:
            raise SourceLoadError(
                PipelineFailureReason.SOURCE_MISSING, "not in this machine's blob store"
            ) from None
        if hashlib.sha256(content).hexdigest() != source.sha256:
            raise SourceLoadError(
                PipelineFailureReason.SOURCE_INTEGRITY, "the blob does not hash to its name"
            )
        return content

    return load


class _UnwrittenPlanTexts:
    """The plan-text cache as it is, read; every write dropped (`v1-e32-t05`'s dry run)."""

    def __init__(self, inner: PlanTextStore) -> None:
        self._inner = inner

    async def read(self, caselist: str) -> tuple[CachedPlanText, ...]:
        return await self._inner.read(caselist)

    async def replace(self, caselist: str, entries: Sequence[CachedPlanText]) -> None:
        return None


def _entry(
    sha: str,
    parser_version: str,
    vocabulary_digest: str,
    found: Sequence[PlanTextParagraph],
    kritikal: KritikalReading,
    transition: Sequence[PlanTextParagraph],
) -> CachedPlanText:
    return CachedPlanText(
        source_sha256=sha,
        parser_version=parser_version,
        vocabulary_digest=vocabulary_digest,
        readable=True,
        paragraphs=tuple(_cached(one) for one in found),
        kritikal_markers=tuple(
            CachedKritikalMarker(kind=one.kind, form=one.form, element_index=one.element_index, unit=one.unit)
            for one in kritikal.markers
        ),
        heading_families=kritikal.heading_families,
        transition_paragraphs=tuple(_cached(one) for one in transition),
    )


def _cached(one: PlanTextParagraph) -> CachedPlanTextParagraph:
    return CachedPlanTextParagraph(
        label_element_index=one.label_element_index,
        element_index=one.element_index,
        unit=one.unit,
        kept=one.kept,
        shaped=one.shaped,
        digest=one.digest,
        named=one.named,
    )


def _marker(one: CachedKritikalMarker) -> KritikalMarker:
    return KritikalMarker(kind=one.kind, form=one.form, element_index=one.element_index, unit=one.unit)


def _paragraph(one: CachedPlanTextParagraph) -> PlanTextParagraph:
    return PlanTextParagraph(
        label_element_index=one.label_element_index,
        element_index=one.element_index,
        unit=one.unit,
        kept=one.kept,
        shaped=one.shaped,
        digest=one.digest,
        named=one.named,
    )

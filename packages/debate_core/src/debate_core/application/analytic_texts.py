"""AnalyticTextService: CP texts, alternatives, roles of the ballot and overviews, read again (`v1-e32-t11`).

The parsed card store keeps cards only, and most of these texts are analytics, so they are read from each
source's own bytes as `v1-e32-t09` reads plan texts (the PM's context for `v1-e32-t11`: reuse, don't
rebuild), through the :class:`~debate_core.application.ports.debate_files.DebateFileParser` port, read-only,
under a placeholder path. One run:

1. looks each source up in the caselist's analytic-text cache, under (digest, parser version, rules
   digest), the rules digest covering the labels, the reading rules, the CP texts' actors, the taxonomy's
   positions and the coach's overrides (the PM's ruling 5 of 2026-10-24);
2. parses only the sources not there, through a
   :class:`~debate_core.application.caselist.parse_workers.ParseRunner`, reading each source's bytes from
   this machine's blob store and checking they hash to their name
   (:func:`~debate_core.application.plan_texts.blob_jobs`);
3. keeps what :func:`~debate_core.arguments.landscape.analytic_texts.read_analytic_texts` derives from each,
   placed under its position, never the text, and writes the cache back when anything changed.

Then, for the report, :meth:`AnalyticTextService.quote` reads again, in memory, only the sources holding a
CP text, plank, alternative or role of the ballot placed under a position of its kind, and returns each
such text word for word when its paragraph still hashes to the digest kept for it. Nothing it reads is
written. Overviews are never read again: they are counted only.

A source the parser refused is cached as unreadable; one whose bytes could not be read, or whose worker
failed, is not cached, so the next run tries it again.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_sources import enumerate_sources
from debate_core.application.caselist.parse_workers import ParseRunner
from debate_core.application.landscape_seeding import SeedReading
from debate_core.application.plan_texts import blob_jobs
from debate_core.application.ports.analytic_text_store import AnalyticTextStore, CachedAnalyticTexts
from debate_core.application.ports.debate_files import DebateFileParser
from debate_core.arguments.landscape.analytic_texts import (
    AnalyticTextInputs,
    AnalyticTextRules,
    CounterplanActors,
    read_analytic_texts,
    read_back_texts,
    section_paragraphs_of,
)
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.caselist import SourceDocument
from debate_core.domain.debate_files import ParsedDocument, ParseFailure
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import OverrideRules, PositionRole
from debate_core.domain.landscape_texts import POSITION_KIND_OF, AnalyticTextReading, TextPlacement

__all__ = [
    "ANALYTIC_TEXT_SOURCE_PATH",
    "AnalyticTextCounts",
    "AnalyticTextRun",
    "AnalyticTextService",
    "AnalyticTextsForReport",
    "QuotedTextsRun",
]

ANALYTIC_TEXT_SOURCE_PATH: Final = "analytic-text-reading.docx"
"""The path the parser is given in place of a disclosure path, which names a school and a team."""


@dataclass(frozen=True, slots=True)
class AnalyticTextCounts:
    sources: int
    hits: int
    parsed: int
    """Sources the parser read in this run."""
    refused: int
    """Sources the parser refused, in this run or cached."""
    unread: int
    """Sources whose bytes could not be read or whose worker failed in this run; not cached."""
    readings: dict[str, int]
    """Readings of the sources asked for, by kind."""
    placed: dict[str, int]
    """Of those, the readings placed under a position, by kind."""
    refused_by_guard: int
    cache_written: bool
    planks_refused_by_guard: int = 0
    """List planks left out because their CP text fails the actor guard (`v1-e32-t16`)."""
    plank_labels: int = 0
    """List paragraphs that are only an advantage's alias, naming the plank after them."""


@dataclass(frozen=True, slots=True)
class AnalyticTextRun:
    parser_version: str
    rules_digest: str
    readings: dict[str, tuple[AnalyticTextReading, ...]] = field(repr=False)
    """What was read of each readable source, by digest."""
    refused_by_guard: dict[str, int] = field(repr=False)
    counts: AnalyticTextCounts
    planks_refused_by_guard: dict[str, int] = field(default_factory=dict[str, int], repr=False)
    plank_labels: dict[str, int] = field(default_factory=dict[str, int], repr=False)


@dataclass(frozen=True, slots=True)
class QuotedTextsRun:
    """The texts the report may quote, read again. Held in memory only."""

    texts: dict[tuple[str, int], str] = field(repr=False)
    """By (source digest, paragraph)."""
    sources: int
    """Sources holding a text to quote: the sources read again."""
    wanted: int
    """Texts to quote."""
    mismatched: int
    """Texts whose paragraph no longer reads as it was read, in sources that parsed."""
    unread: int
    """Sources that could not be parsed again."""


@dataclass(frozen=True, slots=True)
class AnalyticTextsForReport:
    """What a landscape run gives the report, with the counts of how it was read."""

    inputs: AnalyticTextInputs
    read: AnalyticTextCounts
    quoted: QuotedTextsRun


class AnalyticTextService:
    """Reads analytic texts from a caselist's sources, parsing only what its cache does not hold."""

    def __init__(
        self,
        *,
        parser: DebateFileParser,
        runner: ParseRunner,
        store: AnalyticTextStore,
        local: LocalEvidence,
        writes: bool = True,
    ) -> None:
        self._parser = parser
        self._runner = runner
        self._store = store if writes else _UnwrittenAnalyticTexts(store)
        self._local = local
        self._writes = writes

    def without_writes(self) -> AnalyticTextService:
        """The same reading over a view of the cache that is never written: what a dry run reads with."""
        return AnalyticTextService(
            parser=self._parser, runner=self._runner, store=self._store, local=self._local, writes=False
        )

    async def read(
        self,
        caselist: str,
        sources: Sequence[SourceDocument],
        rules: AnalyticTextRules,
        *,
        own_names: Mapping[str, Sequence[str]] | None = None,
        caselist_names: Mapping[str, Sequence[str]] | None = None,
    ) -> AnalyticTextRun:
        """Each source's readings, parsing only those not cached under this parser and these rules.

        `own_names` are each source's disclosing teams' school and team code, by digest, and
        `caselist_names` every school of the caselist: both are taken out of a heading before it is placed.
        """
        parser_version = self._parser.parser_version
        current = (parser_version, rules.digest)
        everything = await self._store.read(caselist)
        cached = {
            entry.source_sha256: entry
            for entry in everything
            if (entry.parser_version, entry.rules_digest) == current
        }
        stale = len(everything) - len(cached)
        wanted = {source.sha256: source for source in sources}
        missing = [source for sha, source in sorted(wanted.items()) if sha not in cached]
        names = own_names or {}
        schools = CaselistNames(caselist_names or {})
        written: dict[str, CachedAnalyticTexts] = {}
        unread = 0
        jobs = blob_jobs(missing, self._local, ANALYTIC_TEXT_SOURCE_PATH)
        for job, result in self._runner.run(self._parser, jobs):
            sha = job.source.sha256
            if isinstance(result, ParsedDocument):
                found = read_analytic_texts(
                    section_paragraphs_of(result), rules, own_names=names.get(sha, ()), caselist=schools
                )
                written[sha] = CachedAnalyticTexts(
                    source_sha256=sha,
                    parser_version=parser_version,
                    rules_digest=rules.digest,
                    readable=True,
                    readings=found.readings,
                    refused_by_guard=found.refused_by_guard,
                    planks_refused_by_guard=found.planks_refused_by_guard,
                    plank_labels=found.plank_labels,
                )
            elif isinstance(result, ParseFailure):
                written[sha] = CachedAnalyticTexts(
                    source_sha256=sha,
                    parser_version=parser_version,
                    rules_digest=rules.digest,
                    readable=False,
                )
            else:
                unread += 1
        changed = bool(written) or stale > 0
        if changed:
            await self._store.replace(caselist, [*cached.values(), *written.values()])
        held = {**cached, **written}
        readable = {sha: held[sha] for sha in sorted(wanted) if sha in held and held[sha].readable}
        readings = {sha: entry.readings for sha, entry in readable.items()}
        refused = {sha: entry.refused_by_guard for sha, entry in readable.items() if entry.refused_by_guard}
        planks_refused = {
            sha: entry.planks_refused_by_guard
            for sha, entry in readable.items()
            if entry.planks_refused_by_guard
        }
        labels = {sha: entry.plank_labels for sha, entry in readable.items() if entry.plank_labels}
        every = [one for found in readings.values() for one in found]
        return AnalyticTextRun(
            parser_version=parser_version,
            rules_digest=rules.digest,
            readings=readings,
            refused_by_guard=refused,
            planks_refused_by_guard=planks_refused,
            plank_labels=labels,
            counts=AnalyticTextCounts(
                sources=len(wanted),
                hits=sum(1 for sha in wanted if sha in cached),
                parsed=len(written),
                refused=sum(1 for sha in wanted if sha in held and not held[sha].readable),
                unread=unread,
                readings=dict(sorted(Counter(one.kind.value for one in every).items())),
                placed=dict(
                    sorted(
                        Counter(
                            one.kind.value for one in every if one.placement is TextPlacement.PLACED
                        ).items()
                    )
                ),
                refused_by_guard=sum(refused.values()),
                cache_written=changed and self._writes,
                planks_refused_by_guard=sum(planks_refused.values()),
                plank_labels=sum(labels.values()),
            ),
        )

    async def quote(
        self, caselist: str, sources: Sequence[SourceDocument], run: AnalyticTextRun, taxonomy: Taxonomy
    ) -> QuotedTextsRun:
        """Each text the report may quote, word for word, read again from its source and never written.

        Only a CP text, a plank, an alternative or a role of the ballot placed under a position of its kind,
        READS, is read again; an overview never is. A text is returned only when its paragraph still hashes
        to the digest kept for it.
        """
        wanted = {
            sha: shown
            for sha, found in run.readings.items()
            if (shown := tuple(one for one in found if _to_quote(one, taxonomy)))
        }
        by_sha = {source.sha256: source for source in sources}
        to_read = [by_sha[sha] for sha in sorted(wanted) if sha in by_sha]
        texts: dict[tuple[str, int], str] = {}
        mismatched = unread = 0
        for job, result in self._runner.run(
            self._parser, blob_jobs(to_read, self._local, ANALYTIC_TEXT_SOURCE_PATH)
        ):
            sha = job.source.sha256
            if not isinstance(result, ParsedDocument):
                unread += 1
                continue
            back = read_back_texts(section_paragraphs_of(result).paragraphs, wanted[sha])
            mismatched += len(wanted[sha]) - len(back)
            texts.update({(sha, index): text for index, text in back.items()})
        return QuotedTextsRun(
            texts=dict(sorted(texts.items())),
            sources=len(to_read),
            wanted=sum(len(wanted[source.sha256]) for source in to_read),
            mismatched=mismatched,
            unread=unread,
        )

    async def report_inputs(
        self,
        *,
        reading: SeedReading,
        taxonomy: Taxonomy,
        overrides: OverrideRules,
        actors: CounterplanActors | None,
        writes: bool,
    ) -> AnalyticTextsForReport:
        """A landscape run's seam: the readings and quoted texts of the run's own reading.

        Every on-topic source of the reading is read, on either side: overviews are counted on both. Each
        heading is placed with its disclosing teams' own names and the caselist's schools taken out.
        `writes` False reads through a cache that is never written, for a dry run.
        """
        on_topic = {source.sha256: source for source in reading.sources}
        documents = [
            one.source_document()
            for one in await enumerate_sources(self._local, reading.caselist)
            if one.sha256 in on_topic
        ]
        service = self if writes else self.without_writes()
        run = await service.read(
            reading.caselist,
            documents,
            AnalyticTextRules(taxonomy, overrides, actors),
            own_names={
                sha: tuple(name for team in source.teams for name in team.names if name.strip())
                for sha, source in on_topic.items()
            },
            caselist_names=reading.caselist_names,
        )
        quoted = await self.quote(reading.caselist, documents, run, taxonomy)
        return AnalyticTextsForReport(
            inputs=AnalyticTextInputs(
                readings=run.readings,
                texts=quoted.texts,
                caselist_names=reading.caselist_names,
                refused_by_guard=run.refused_by_guard,
                planks_refused_by_guard=run.planks_refused_by_guard,
                plank_labels=run.plank_labels,
            ),
            read=run.counts,
            quoted=quoted,
        )


def _to_quote(reading: AnalyticTextReading, taxonomy: Taxonomy) -> bool:
    """A quoted kind's text placed under a position of its kind that the team reads."""
    kind = POSITION_KIND_OF.get(reading.kind)
    if kind is None or reading.position_id is None or reading.role is not PositionRole.READS:
        return False
    try:
        return taxonomy.resolve(reading.position_id).kind is kind
    except KeyError:
        return False


class _UnwrittenAnalyticTexts:
    """The analytic-text cache as it is, read; every write dropped (a landscape dry run)."""

    def __init__(self, inner: AnalyticTextStore) -> None:
        self._inner = inner

    async def read(self, caselist: str) -> tuple[CachedAnalyticTexts, ...]:
        return await self._inner.read(caselist)

    async def replace(self, caselist: str, entries: Sequence[CachedAnalyticTexts]) -> None:
        return None

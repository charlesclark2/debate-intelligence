"""The parse stage of `caselist pull`: the parse pipeline, as the weekly run uses it.

`v1-e34-t17-pull-parses-new-sources`. :class:`PullParseStage` is
:class:`~debate_core.application.caselist_sync.CaselistParseStage` over the two things
`debate-research caselist parse` runs, :class:`~debate_core.application.caselist_parse.CaselistParseService`
and :class:`~debate_core.application.caselist.parsed_publish.ParsedStorePublisher`
(`v1-e31-t06-parse-pipeline`), and it adds nothing to either. One caselist's parse here is
`caselist parse --caselist <slug>`, and its publish is the `--publish` that follows.

Every decision about the stage is the run's
(:meth:`~debate_core.application.caselist_sync.CaselistSyncService._parse_stage`, and "The parse
stage" in that module's docstring): which caselists, whether a publish may follow, and what a
failure does. What is decided here is only how a pipeline report becomes the run's counts.

## The caselist, never a snapshot

:meth:`PullParseStage.parse_new_sources` plans over the whole caselist, with no snapshot and no
`--reparse`. The pipeline's skip key (a source's SHA-256, the parser version and the profile
version) is then what makes the parse incremental: a source already recorded under the running
versions is not parsed again, so a steady week parses that week's new sources. Nothing from the
full-archive namespace is ever among them, because the pipeline's enumeration does not read it, and
this module does not enumerate.

## What is logged

Nothing of its own. The pipeline and the publisher each log one line of counts, the caselist and
the version (and, for an object the bucket did not confirm, its key, which is a caselist, a version
and a digest). No path, school, team code, file name or card text is in either.
"""

from __future__ import annotations

from debate_core.application.caselist.parsed_publish import ParsedStorePublisher
from debate_core.application.caselist.publish_service import SourceResult
from debate_core.application.caselist_parse import CaselistParseService
from debate_core.application.caselist_sync import ParsedCaselist, PublishedParsedStore

__all__ = ["PullParseStage"]


class PullParseStage:
    """The parse pipeline and the parsed store's publisher, one caselist at a time.

    Args:
        parse: The parse pipeline. Built over the suppression list the pull itself was built with
            (required by the pipeline, with no default), so that the run can tell when the list was
            read from this machine's copy alone.
        publisher: The copy of the parsed store to the environment's bucket, or `None` for an
            environment that names no bucket, where the run never asks for a publish.
    """

    def __init__(self, *, parse: CaselistParseService, publisher: ParsedStorePublisher | None) -> None:
        self._parse = parse
        self._publisher = publisher

    async def parse_new_sources(self, caselist: str) -> ParsedCaselist:
        """Parse every source of `caselist` not yet parsed under the running versions, and rebuild
        its aggregates."""
        plan = await self._parse.plan(caselist)
        report = await self._parse.run(plan)
        return ParsedCaselist(
            version=plan.version,
            attempted=report.attempted,
            skipped=plan.skipped,
            unsupported=sum(report.unsupported.values()),
            failed=sum(report.failed.values()),
            cards=report.cards,
            tried=report.tried,
            # Nothing was recorded under this run's skip key, so everything was parsed: a first
            # parse, or the first after the parser or the profile version changed.
            full_parse=bool(plan.to_parse) and plan.skipped == 0,
            failure_rate_exceeded=report.exceeds_threshold,
        )

    async def publish(self, caselist: str, version: str) -> PublishedParsedStore:
        """Copy `caselist`'s version directory to the bucket: what it lacks, or holds differently."""
        if self._publisher is None:
            raise ValueError("this environment names no evidence bucket, so no parsed store is published")
        published = await self._publisher.publish(caselist, version)
        return PublishedParsedStore(
            uploaded=published.count(SourceResult.UPLOADED), failure_codes=published.failure_codes
        )

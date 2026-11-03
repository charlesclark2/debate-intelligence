"""Has every store the weekly run will index been parsed by this build's parser?

`v1-e34-t30`. The weekly run's search index stage (`v1-e39-t09`) indexes the run's caselists plus
`openev`, each from its version directory of the running parser. A store with no such directory
fails the stage, under its PM ruling Q3, and one parsed only by another parser skips it; either way
the run ends without a current index. On a fresh installation that is the first Wednesday, found on
Wednesday. :class:`SearchIndexStoreCheck` finds it before, and `debate-research doctor
--search-index` runs it; `ops/launchd/install.sh --check-launchd` runs it under launchd with the
agent's caselists.

## Which stores

Exactly the stage's: :func:`~debate_core.application.caselist_sync.search_index_stores` of the
run's caselists, the function the stage itself enumerates them with. The caselists are the ones a
`caselist pull` with no `--caselist` follows, `caselist.sync_caselists`; the launchd check sets that
setting to the agent's own.

## When it applies

When the run has the stage at all:
:func:`~debate_core.application.caselist_sync.why_no_search_index_stage`, the rule the composition
root wires the stage by. Without the stage the check reads nothing, says why it does not apply, and
passes.

## What "parsed" means

That the store has a version directory of the running parser version, of any generation
(`<parser version>` or `<parser version>_reparse-<n>`). A store whose directories are all another
parser's, older or newer, is not parsed by this build. Nothing else is checked: whether a version
directory is complete is not this check's question.

## What a finding may hold

A store's name, which is a caselist slug or `openev`, the parser version and the command that
parses it. Never a path, a school, a team code or a file name.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from debate_core.application.caselist_sync import search_index_stores, why_no_search_index_stage
from debate_core.application.ports.parsed_store import ParsedStore, parse_version_directory

__all__ = [
    "SearchIndexStoreCheck",
    "SearchIndexStoreFindings",
    "StoreFinding",
    "parse_command",
]


def parse_command(store: str) -> str:
    """The command that parses `store` with this build: the fix for a store it has not parsed."""
    return f"debate-research caselist parse --caselist {store}"


@dataclass(frozen=True, slots=True)
class StoreFinding:
    """One store the stage would index, and whether this build's parser has parsed it."""

    store: str
    parsed: bool

    @property
    def fix(self) -> str | None:
        return None if self.parsed else parse_command(self.store)

    def as_json(self) -> dict[str, object]:
        return {"store": self.store, "parsed": self.parsed, "fix": self.fix}


@dataclass(frozen=True, slots=True)
class SearchIndexStoreFindings:
    """What the check found: why it does not apply, or each store in the order the stage indexes them."""

    parser_version: str
    caselists: tuple[str, ...]
    """The run's caselists, as configured; the stores are these and `openev`."""

    does_not_apply: str | None = None
    """Why the run has no search index stage, in the words its summary records; `None` when it has one."""

    stores: tuple[StoreFinding, ...] = ()

    @property
    def applies(self) -> bool:
        return self.does_not_apply is None

    @property
    def unparsed(self) -> tuple[StoreFinding, ...]:
        return tuple(one for one in self.stores if not one.parsed)

    def as_json(self) -> dict[str, object]:
        """The findings as `doctor --json` reports them."""
        return {
            "applies": self.applies,
            "does_not_apply": self.does_not_apply,
            "parser_version": self.parser_version,
            "caselists": list(self.caselists),
            "stores": [one.as_json() for one in self.stores],
            "unparsed": [one.store for one in self.unparsed],
        }


class SearchIndexStoreCheck:
    """Asks, for each store the weekly run's search index stage would index, whether it is parsed.

    Args:
        caselists: The run's caselists, `caselist.sync_caselists`.
        bucket_named: Whether this environment names an evidence bucket.
        refresh_search_index: `caselist.refresh_search_index`.
        parsed_store: This machine's parsed store. Only its version directories are listed.
        parser_version: The parser version this build runs.
    """

    def __init__(
        self,
        *,
        caselists: Sequence[str],
        bucket_named: bool,
        refresh_search_index: bool,
        parsed_store: ParsedStore,
        parser_version: str,
    ) -> None:
        self._caselists = tuple(caselists)
        self._bucket_named = bucket_named
        self._refresh_search_index = refresh_search_index
        self._parsed_store = parsed_store
        self._parser_version = parser_version

    async def run(self) -> SearchIndexStoreFindings:
        """Each store's finding, or why the check does not apply. Reads nothing when it does not."""
        absent = why_no_search_index_stage(
            bucket_named=self._bucket_named, refresh_search_index=self._refresh_search_index
        )
        if absent is not None:
            return SearchIndexStoreFindings(self._parser_version, self._caselists, does_not_apply=absent)
        stores = [
            StoreFinding(store=store, parsed=await self._parsed(store))
            for store in search_index_stores(self._caselists)
        ]
        return SearchIndexStoreFindings(self._parser_version, self._caselists, stores=tuple(stores))

    async def _parsed(self, store: str) -> bool:
        """Whether `store` has a version directory, of any generation, of the running parser version."""
        return any(
            parse_version_directory(name)[0] == self._parser_version
            for name in await self._parsed_store.version_directories(store)
        )

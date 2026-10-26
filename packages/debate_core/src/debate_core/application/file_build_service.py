"""FileBuildService: one recipe to a built evidence file, its sidecar and its quality report (`v1-e33-t03`).

`debate-research files build <recipe>` and `files check <file>` are thin wrappers over this. One build:

1. **Loads** the recipe (`v1-e33-t01`), reporting every
   :class:`~debate_core.application.file_recipes.RecipeError`.
2. **Refuses a draft** unless the build allows one; a file built from a draft says DRAFT in its header.
3. **Refuses a store another build parsed** (PM amendment 2026-10-19). The writer finds each card by
   re-parsing its source with the running parser, so a store of another parser or fingerprint version
   would give `OCCURRENCE_MISMATCH` for every card. Before anything is resolved, every caselist the
   recipe reads is compared with the running build, and one refusal names both versions and the
   re-parse.
4. **Refuses an output directory inside a git working tree** (PM amendment 2026-10-21): a built file
   holds card text and its sidecar names who disclosed each card, and neither is ever committed.
5. **Resolves** every card to one occurrence, listing every error at once.
6. **Names every card resolved to an unattributed occurrence** (PM amendment 2026-10-19), before any
   source is read or anything written.
7. **Finds every source** in this machine's blob store by SHA-256. A missing one fails its cards with
   `SOURCE_MISSING` and the `debate-research store get` that fetches it, and nothing is built.
8. **Writes** `<name>.docx` and `<name>.docx.provenance.json` through the lossless writer (`v1-e33-t02`),
   which refuses the whole file rather than build part of one.
9. **Checks** the written file with the :class:`~debate_core.application.file_quality_service.
   FileQualityService` it was given (`v1-e33-t04`), which the composition root wires, writing
   `.quality.json` and `.quality.md` beside it. A FAIL keeps the files for inspection and says which
   checks failed.

Steps 1 to 7 write nothing. No model is called, nothing reaches the network or a bucket: the parsed
store, the caselist records, the suppression list and the blob store are this machine's.

## What a result never holds

Card text, a school, a team code or a path. An unattributed card is named by its place in the recipe
and its fingerprint; a missing source by its SHA-256 and the bucket key `store get` fetches.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

from debate_core.application.caselist.publish_plan import source_key
from debate_core.application.file_quality_service import CheckedFile, FileQualityService
from debate_core.application.file_recipes import (
    OccurrenceStoreNotReady,
    RecipeError,
    RecipeResolver,
    ResolvedCard,
    ResolvedRecipe,
    load_recipe,
)
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.evidence_file_writer import (
    BuiltEvidenceFile,
    EvidenceFileWriter,
    FileBuildRefusal,
)
from debate_core.application.ports.evidence_file_writer import (
    FileBuildRequest as WriterRequest,
)
from debate_core.application.ports.parsed_store import OPENEV_STORE, ParsedStore, parse_version_directory
from debate_core.application.ports.persistence import SnapshotStore
from debate_core.application.ports.suppression import SuppressionList
from debate_core.domain.file_provenance import provenance_sidecar_name
from debate_core.domain.file_recipe import FileRecipe, RecipeStatus
from debate_core.evidence.file_checks.report import CheckStatus, FileQualityReport, QualityCheck
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

__all__ = [
    "BUILT_DIRECTORY",
    "PROVENANCE_LINE_WRITERS",
    "SOURCE_MISSING",
    "BuildCounts",
    "BuildFileRequest",
    "BuildRefusal",
    "BuildRefusalCode",
    "BuildStatus",
    "BuiltFiles",
    "CardProblem",
    "FileBuildResult",
    "FileBuildService",
    "FileCheckResult",
    "UnattributedCard",
    "inside_a_git_working_tree",
    "rebuild_notes",
    "unattributed_cards",
]

BUILT_DIRECTORY: Final = "built"
"""Under the files directory: where a build writes by default, one directory per topic."""

SOURCE_MISSING: Final = "SOURCE_MISSING"
"""A card's code when its source is not in this machine's blob store (ac4)."""

PROVENANCE_LINE_WRITERS: Final = frozenset({"2026.10.19-file-writer-1", "2026.10.19-file-writer-2"})
"""The writer versions that put a provenance line below each cite (until `v1-e33-t08`).

Since data-use policy version 1.11 a built file carries none, and `provenance-complete` fails a file
that does; a rebuild over the same recipe writes it without them. Named here, not read from the
writer, because the application layer does not import an adapter."""


class BuildStatus(StrEnum):
    """How a build ended."""

    BUILT = "BUILT"
    """Written, and every quality check passed or only warned."""

    QUALITY_FAILED = "QUALITY_FAILED"
    """Written and kept for inspection, and a quality check failed."""

    REFUSED = "REFUSED"
    """Nothing written: see :attr:`FileBuildResult.refusal`."""


class BuildRefusalCode(StrEnum):
    """Why a build wrote nothing, in the order a build asks."""

    RECIPE_INVALID = "RECIPE_INVALID"
    """The recipe does not load: every error is in :attr:`FileBuildResult.recipe_errors`."""

    DRAFT_NOT_ALLOWED = "DRAFT_NOT_ALLOWED"
    """`status: draft`, and the build was not told to allow one."""

    STORE_PARSED_BY_ANOTHER_VERSION = "STORE_PARSED_BY_ANOTHER_VERSION"
    """A caselist the recipe reads was parsed, or fingerprinted, by another build (ac8)."""

    STORE_NOT_PARSED = "STORE_NOT_PARSED"
    """A caselist the recipe reads has no parsed store on this machine, or no occurrence table."""

    OUTPUT_IN_A_GIT_WORKING_TREE = "OUTPUT_IN_A_GIT_WORKING_TREE"
    """The output directory is inside a git working tree (ac10)."""

    RECIPE_UNRESOLVED = "RECIPE_UNRESOLVED"
    """A card did not resolve: every error is in :attr:`FileBuildResult.recipe_errors`."""

    SOURCE_MISSING = "SOURCE_MISSING"
    """A source is not in this machine's blob store: see :attr:`FileBuildResult.card_problems` (ac4)."""

    WRITER_REFUSED = "WRITER_REFUSED"
    """The writer could not copy a card losslessly: see :attr:`FileBuildResult.card_problems`."""


@dataclass(frozen=True, slots=True)
class BuildRefusal:
    code: BuildRefusalCode
    message: str
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class CardProblem:
    """One card that stopped the file: its place in the recipe, its fingerprint, and what to do.

    `code` is `SOURCE_MISSING`, or the writer's own refusal code. `detail` names digests, element
    indices and kinds of content only.
    """

    path: str
    fingerprint: str
    code: str
    detail: str
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class UnattributedCard:
    """A card resolved to an occurrence with no disclosure (or camp release) on record."""

    path: str
    fingerprint: str
    caselist: str


@dataclass(frozen=True, slots=True)
class BuildCounts:
    cards_placed: int
    sources_used: int
    tag_overrides: int
    analytics: int


@dataclass(frozen=True, slots=True)
class BuiltFiles:
    docx: Path
    provenance: Path
    quality_json: Path
    quality_markdown: Path


@dataclass(frozen=True, slots=True)
class BuildFileRequest:
    """What to build: the recipe's file, where to write (None for the default), and whether a draft may be."""

    recipe_path: Path
    out_dir: Path | None = None
    allow_draft: bool = False


@dataclass(frozen=True, slots=True)
class FileBuildResult:
    """Everything a build found and did. Nothing in it holds card text, a school, a team or a path."""

    recipe_path: Path
    status: BuildStatus
    recipe_hash: str | None = None
    refusal: BuildRefusal | None = None
    recipe_errors: tuple[RecipeError, ...] = ()
    card_problems: tuple[CardProblem, ...] = ()
    unattributed: tuple[UnattributedCard, ...] = ()
    files: BuiltFiles | None = None
    counts: BuildCounts | None = None
    warnings: tuple[str, ...] = ()
    quality: FileQualityReport | None = field(default=None, repr=False)

    @property
    def failing_checks(self) -> tuple[QualityCheck, ...]:
        if self.quality is None:
            return ()
        return tuple(one.check for one in self.quality.checks if one.status is CheckStatus.FAIL)


@dataclass(frozen=True, slots=True)
class FileCheckResult:
    """`files check`: the wired quality check's report, where it was written, and what explains it."""

    checked: CheckedFile
    notes: tuple[str, ...] = ()


def inside_a_git_working_tree(directory: Path) -> bool:
    """Whether `directory`, or a directory above it, holds a `.git`: a working tree or a worktree."""
    resolved = directory.expanduser().resolve()
    return any((parent / ".git").exists() for parent in (resolved, *resolved.parents))


def unattributed_cards(resolved: ResolvedRecipe) -> tuple[UnattributedCard, ...]:
    """Each card resolved to an occurrence whose provenance has nothing on record to name it from."""
    return tuple(
        UnattributedCard(path=card.path, fingerprint=card.fingerprint, caselist=card.occurrence.caselist)
        for card in resolved.cards
        if not _attributed(card)
    )


def _attributed(card: ResolvedCard) -> bool:
    if card.occurrence.caselist == OPENEV_STORE:
        return card.camp_file is not None
    return card.disclosure is not None


class FileBuildService:
    """Builds one recipe into a file, its sidecar and its quality report, or says why it will not.

    `files_dir` is where built files go by default (`<files_dir>/built/<topic>/`). `parser_version`
    is the running parser's, the one the writer and the quality check read with. `clock` stamps the
    sidecar's `built_at`; the `.docx` carries no time.
    """

    def __init__(
        self,
        *,
        parsed_store: ParsedStore,
        caselists: CaselistRepository,
        suppression: SuppressionList,
        blobs: SnapshotStore,
        writer: EvidenceFileWriter,
        quality: FileQualityService,
        parser_version: str,
        profile_version: str,
        files_dir: Path,
        clock: Callable[[], datetime],
    ) -> None:
        self._store = parsed_store
        self._blobs = blobs
        self._writer = writer
        self._quality = quality
        self._parser_version = parser_version
        self._profile_version = profile_version
        self._files_dir = files_dir
        self._clock = clock
        self._resolver = RecipeResolver(
            parsed_store=parsed_store,
            caselists=caselists,
            suppression=suppression,
            parser_version=parser_version,
        )

    async def build(
        self,
        request: BuildFileRequest,
        *,
        on_unattributed: Callable[[Sequence[UnattributedCard]], None] | None = None,
    ) -> FileBuildResult:
        """Build the recipe at `request.recipe_path`. `on_unattributed` hears of unattributed cards first."""
        path = request.recipe_path
        loaded = load_recipe(path.read_text(encoding="utf-8"))
        if loaded.recipe is None or loaded.errors:
            return _refused(
                path,
                BuildRefusalCode.RECIPE_INVALID,
                f"the recipe does not load: {len(loaded.errors)} error(s)",
                recipe_errors=loaded.errors,
            )
        recipe, recipe_hash = loaded.recipe, loaded.recipe_hash
        if recipe.status is RecipeStatus.DRAFT and not request.allow_draft:
            return _refused(
                path,
                BuildRefusalCode.DRAFT_NOT_ALLOWED,
                "the recipe is a draft (status: draft), and a draft is built only when asked",
                hint="Set status: ready once you have edited it, or build it as it is with --allow-draft; "
                "the file's header will then say DRAFT.",
                recipe_hash=recipe_hash,
            )
        refusal = await self._store_refusal(recipe)
        if refusal is not None:
            return _refused(path, refusal.code, refusal.message, hint=refusal.hint, recipe_hash=recipe_hash)
        directory = self._out_dir(request, recipe)
        if inside_a_git_working_tree(directory):
            return _refused(
                path,
                BuildRefusalCode.OUTPUT_IN_A_GIT_WORKING_TREE,
                f"{directory} is inside a git working tree; a built file holds card text and its sidecar "
                "names who disclosed each card, and neither is ever committed",
                hint=f"Write it outside any checkout, or leave --out out for {self._built_root}.",
                recipe_hash=recipe_hash,
            )
        try:
            resolved = await self._resolver.resolve(recipe, lines=loaded.lines)
        except OccurrenceStoreNotReady as not_ready:
            return _refused(
                path,
                BuildRefusalCode.STORE_NOT_PARSED,
                str(not_ready),
                hint=_reparse_hint([not_ready.caselist]),
                recipe_hash=recipe_hash,
            )
        if not resolved.ok:
            return _refused(
                path,
                BuildRefusalCode.RECIPE_UNRESOLVED,
                f"{len(resolved.errors)} card reference(s) did not resolve",
                recipe_hash=resolved.recipe_hash,
                recipe_errors=resolved.errors,
            )
        unattributed = unattributed_cards(resolved)
        if unattributed and on_unattributed is not None:
            on_unattributed(unattributed)
        missing = await self._missing_sources(resolved)
        if missing:
            sources = len({problem.hint for problem in missing})
            return _refused(
                path,
                BuildRefusalCode.SOURCE_MISSING,
                f"{sources} source file(s) of {len(missing)} card(s) are not in this machine's evidence "
                "store, so no file was built",
                hint="Fetch each with the `debate-research store get` beside its card, then build again.",
                recipe_hash=resolved.recipe_hash,
                card_problems=missing,
                unattributed=unattributed,
            )
        built = await self._writer.build(WriterRequest(resolved, self._clock()))
        if isinstance(built, FileBuildRefusal):
            return _refused(
                path,
                BuildRefusalCode.WRITER_REFUSED,
                f"the writer could not copy {len(built.refusals)} card(s) losslessly, so no file was built",
                recipe_hash=resolved.recipe_hash,
                card_problems=tuple(
                    CardProblem(one.path, one.fingerprint, str(one.code), one.detail)
                    for one in built.refusals
                ),
                unattributed=unattributed,
            )
        directory = self._out_dir(request, recipe)
        files = await self._write(directory, f"{path.stem}.docx", built)
        report = files[1].report
        return FileBuildResult(
            recipe_path=path,
            status=BuildStatus.BUILT if report.status is CheckStatus.PASS else BuildStatus.QUALITY_FAILED,
            recipe_hash=resolved.recipe_hash,
            unattributed=unattributed,
            files=files[0],
            counts=_counts(recipe, resolved, built),
            warnings=built.warnings,
            quality=report,
        )

    async def check(self, built_path: Path) -> FileCheckResult:
        """Run the wired quality check on a built file, and say what explains a FAIL it knows the cause of."""
        checked = await self._quality.check(built_path)
        return FileCheckResult(checked=checked, notes=rebuild_notes(checked.report))

    async def _store_refusal(self, recipe: FileRecipe) -> BuildRefusal | None:
        """One refusal for every caselist the recipe reads that this build did not parse, or `None`.

        A caselist's store is the version of its newest directory, which the store lists by parser
        version and then generation. It must be this build's parser version, and its occurrence table
        must be stamped with this build's fingerprint version and no other.
        """
        other: list[str] = []
        unparsed: list[str] = []
        reparse: list[str] = []
        for caselist in sorted(
            {recipe.caselist} | {ref.pin.caselist for _, ref in recipe.card_refs() if ref.pin}
        ):
            directories = await self._store.version_directories(caselist)
            if not directories:
                unparsed.append(f"{caselist} has no parsed store on this machine")
                reparse.append(caselist)
                continue
            newest = directories[-1]
            parsed_by = parse_version_directory(newest)[0]
            if parsed_by != self._parser_version:
                other.append(
                    f"{caselist} was parsed by parser {parsed_by}, and this build's parser is "
                    f"{self._parser_version}"
                )
                reparse.append(caselist)
                continue
            stamps = await self._store.read_occurrence_stamps(caselist, newest)
            if stamps is None:
                unparsed.append(
                    f"{caselist} {newest} has no occurrence table (a removal deletes it until the next parse)"
                )
                reparse.append(caselist)
                continue
            stamped = sorted(stamps - {FINGERPRINT_VERSION})
            if stamped:
                other.append(
                    f"{caselist}'s occurrence table is stamped {', '.join(stamped)}, and this build's "
                    f"fingerprint version is {FINGERPRINT_VERSION}"
                )
                reparse.append(caselist)
        if not reparse:
            return None
        code = (
            BuildRefusalCode.STORE_PARSED_BY_ANOTHER_VERSION if other else BuildRefusalCode.STORE_NOT_PARSED
        )
        reason = "this machine's parsed store was not built by this build" if other else "a store is missing"
        return BuildRefusal(code, f"{reason}: {'; '.join(other + unparsed)}", _reparse_hint(reparse))

    async def _missing_sources(self, resolved: ResolvedRecipe) -> tuple[CardProblem, ...]:
        """Each card whose source is not in the blob store, with the `store get` that fetches it."""
        present: dict[str, bool] = {}
        problems: list[CardProblem] = []
        for card in resolved.cards:
            row = card.occurrence
            sha = row.source_sha256
            if sha not in present:
                present[sha] = await self._blobs.exists(sha)
            if not present[sha]:
                problems.append(
                    CardProblem(
                        path=card.path,
                        fingerprint=card.fingerprint,
                        code=SOURCE_MISSING,
                        detail=f"source {sha[:12]} is not in this machine's evidence store",
                        hint=f"debate-research store get {source_key(row.caselist, row.snapshot, sha)}",
                    )
                )
        return tuple(problems)

    @property
    def _built_root(self) -> Path:
        return self._files_dir / BUILT_DIRECTORY

    def _out_dir(self, request: BuildFileRequest, recipe: FileRecipe) -> Path:
        if request.out_dir is not None:
            return request.out_dir.expanduser().resolve()
        return self._built_root / recipe.topic

    async def _write(
        self, directory: Path, name: str, built: BuiltEvidenceFile
    ) -> tuple[BuiltFiles, CheckedFile]:
        directory.mkdir(parents=True, exist_ok=True)
        docx_path = directory / name
        sidecar_path = directory / provenance_sidecar_name(name)
        _write_whole(sidecar_path, built.manifest_json)
        _write_whole(docx_path, built.docx)
        checked = await self._quality.check(docx_path)
        return (
            BuiltFiles(
                docx=docx_path,
                provenance=sidecar_path,
                quality_json=checked.json_path,
                quality_markdown=checked.markdown_path,
            ),
            checked,
        )


def rebuild_notes(report: FileQualityReport) -> tuple[str, ...]:
    """What explains a report's FAIL when its cause is known: a file built by a writer of provenance lines."""
    if report.builder_version in PROVENANCE_LINE_WRITERS and report.failed(QualityCheck.PROVENANCE_COMPLETE):
        return (
            f"This file was built by {report.builder_version}, which wrote a provenance line below each "
            "cite. Since data-use policy version 1.11 a built file carries none, so provenance-complete "
            "fails it. Rebuild it with `debate-research files build` over the same recipe"
            + (f" (recipe hash {report.recipe_hash[:12]})" if report.recipe_hash else "")
            + "; the sidecar keeps every card's provenance.",
        )
    return ()


def _counts(recipe: FileRecipe, resolved: ResolvedRecipe, built: BuiltEvidenceFile) -> BuildCounts:
    return BuildCounts(
        cards_placed=len(built.manifest.cards),
        sources_used=len({entry.source_sha256 for entry in built.manifest.cards}),
        tag_overrides=sum(card.tag_override is not None for card in resolved.cards),
        analytics=sum(1 for _, item in recipe.walk_items() if not hasattr(item, "fingerprint")),
    )


def _refused(
    path: Path,
    code: BuildRefusalCode,
    message: str,
    *,
    hint: str | None = None,
    recipe_hash: str | None = None,
    recipe_errors: Iterable[RecipeError] = (),
    card_problems: Iterable[CardProblem] = (),
    unattributed: Iterable[UnattributedCard] = (),
) -> FileBuildResult:
    return FileBuildResult(
        recipe_path=path,
        status=BuildStatus.REFUSED,
        recipe_hash=recipe_hash,
        refusal=BuildRefusal(code, message, hint),
        recipe_errors=tuple(recipe_errors),
        card_problems=tuple(card_problems),
        unattributed=tuple(unattributed),
    )


def _write_whole(target: Path, body: bytes) -> None:
    """Write to a second name beside `target`, then rename it over: no reader sees half a file."""
    incoming = target.with_name(f".{target.name}.incoming")
    with incoming.open("wb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(incoming, target)


def _reparse_hint(caselists: Sequence[str]) -> str:
    commands = " and ".join(f"`debate-research caselist parse --caselist {one}`" for one in caselists)
    return f"Re-parse with this build: {commands}, then build again."

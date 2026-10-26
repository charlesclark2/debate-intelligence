"""FilePublishService: built evidence files to the evidence bucket's `files/` prefix (`v1-e33-t05`).

`debate-research files publish <built.docx|dir>` is a thin wrapper over this. For each built file it
first decides, on this machine and without the bucket, whether the file may be published
(:meth:`FilePublishService.plan`), and then puts every file that may under its prefix
(:meth:`FilePublishService.publish`). The layout and the `metadata.json` contract are
:mod:`debate_core.domain.built_file_metadata`'s and `docs/data/built-file-metadata.md`'s.

## The gate, in the order it asks

Nothing of a file is uploaded unless every step passes, and each refusal names what failed:

1. **A quality report beside it** (`<file>.docx.quality.json`, `v1-e33-t04`) that this build can read:
   `QUALITY_REPORT_MISSING` otherwise.
2. **For these bytes.** The report's `docx_sha256` is the SHA-256 of the `.docx` as read now:
   `QUALITY_REPORT_STALE` otherwise.
3. **Not built from a draft** (PM amendment 2026-10-24). The sidecar records the recipe's status;
   `draft` is `BUILT_FROM_A_DRAFT` and a sidecar that records none, written before the status was, is
   `RECIPE_STATUS_UNRECORDED`. Whatever the quality status.
4. **PASS** (PM amendment 2026-10-21). The report's status is PASS: `QUALITY_FAILED` otherwise, with
   the failing checks as `files check` and `FileBuildResult.failing_checks` name them. A warning
   never blocks; it is printed and recorded in `metadata.json`.
5. **PASS again, for the exact bytes uploaded.** The wired
   :class:`~debate_core.application.file_quality_service.FileQualityService` checks the bytes read in
   step 2 and the sidecar's bytes once more, so a source suppressed since the report was written stops
   the file. The report uploaded is this one, for these bytes.
6. **A slug** that makes a key (`SLUG_INVALID`), and **the recipe** the file was built from:
   `<files dir>/recipes/<topic>/<slug>.yaml` by default, or `<recipes dir>/<slug>.yaml`, whose hash is
   the sidecar's (`RECIPE_NOT_FOUND`, `RECIPE_CHANGED`).

The bytes read in step 2 are the bytes uploaded, from a staging directory of this publish's own: a
file rewritten while it is checked cannot be published in place of the one checked.

## The recipe as published (PM amendment 2026-10-19, data-use policy version 1.15)

`recipe.yaml` is the recipe rendered from its model with every pin's `side`, `tournament`, `round`,
`school` and `team_code` removed, and without the original's comments. The amendment names the last
four; the policy says a published recipe "loses every such field", and its list of them begins with
the side, so the side goes too (this task's session report, Deviations). A pin keeps its caselist,
source SHA-256, element index and snapshot, and the provenance sidecar beside it carries the
attribution. Before anything is uploaded, every card's pin is checked to name the sidecar's source
and element for that card.

## Uploading

The five objects go up in order, `metadata.json` last, each through the
:class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore` port. An object whose
recorded SHA-256 in the bucket is already the one to write is skipped, so an unchanged file is
`SKIPPED` and writes nothing. Each object written is checked twice: the digest of the bytes the store
says it wrote, then the digest a `head` reads back. A difference stops the publish
(:class:`PublishedObjectMismatch`), before `metadata.json`, so the tub never indexes a file whose
objects are not the ones it names.

A dry run plans and stops: it never builds a bucket client, and names every key that would be written.

## Finding files by their sources

:meth:`FilePublishService.find_by_source` reads every `metadata.json` under `files/` and returns the
published files with a card from a source SHA-256: what a takedown (`v1-e30-t07`, `v2-e35-t05`)
flags. :meth:`FilePublishService.find_by_disclosure` finds them by a school, a team code or both,
over the published provenance sidecars instead (PM ruling 2026-10-25): the data-use policy names the
sidecar as a place those may live, and as what a removal request is matched against (Attribution rule
3), and `metadata.json` holds neither. Nothing here deletes.

## What a result never holds

Card text, a school or a team code. Files are named by their slug and local path, sources by SHA-256.
"""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import ValidationError

from debate_core.application.errors import DomainError, NotFound
from debate_core.application.file_quality_service import FileQualityService
from debate_core.application.file_recipes import load_recipe
from debate_core.application.ports.evidence_store import EvidenceObjectStore
from debate_core.domain.built_file_metadata import (
    FILES_PREFIX,
    METADATA_NAME,
    BuiltFileKeys,
    BuiltFileMetadata,
    PublishedObject,
    built_file_keys,
    built_file_prefix,
    published_sources,
)
from debate_core.domain.caselist import Event, Side
from debate_core.domain.file_provenance import (
    PROVENANCE_SIDECAR_SUFFIX,
    FileProvenanceManifest,
    provenance_sidecar_name,
)
from debate_core.domain.file_recipe import FileRecipe, RecipeStatus, render_location
from debate_core.evidence.file_checks.report import (
    CheckStatus,
    FileQualityReport,
    QualityCheck,
    quality_report_names,
)

__all__ = [
    "RECIPES_DIRECTORY",
    "STRIPPED_PIN_FIELDS",
    "FilePlan",
    "FilePublishService",
    "FileRefusal",
    "FileRefusalCode",
    "FoundBuiltFile",
    "PublishOutcome",
    "PublishPlan",
    "PublishRequest",
    "PublishResult",
    "PublishStatus",
    "PublishedObjectMismatch",
    "SourceLookup",
    "DisclosureLookup",
    "built_files_in",
    "published_recipe",
]

RECIPES_DIRECTORY: Final = "recipes"
"""Under the files directory: where recipes are, one directory per topic (`files suggest` writes there)."""

STRIPPED_PIN_FIELDS: Final = ("side", "tournament", "round", "school", "team_code")
"""What a published recipe's pins never hold: data-use policy 1.15's list (PM amendment 2026-10-19)."""


class FileRefusalCode(StrEnum):
    """Why a built file is not published, in the order the gate asks."""

    QUALITY_REPORT_MISSING = "QUALITY_REPORT_MISSING"
    QUALITY_REPORT_STALE = "QUALITY_REPORT_STALE"
    BUILT_FROM_A_DRAFT = "BUILT_FROM_A_DRAFT"
    RECIPE_STATUS_UNRECORDED = "RECIPE_STATUS_UNRECORDED"
    QUALITY_FAILED = "QUALITY_FAILED"
    SLUG_INVALID = "SLUG_INVALID"
    RECIPE_NOT_FOUND = "RECIPE_NOT_FOUND"
    RECIPE_CHANGED = "RECIPE_CHANGED"


class PublishStatus(StrEnum):
    PUBLISHED = "PUBLISHED"
    """At least one object was written."""

    SKIPPED = "SKIPPED"
    """Every object was already in the bucket, byte for byte."""

    REFUSED = "REFUSED"
    """Nothing of the file was uploaded: see :attr:`PublishOutcome.refusal`."""

    WOULD_PUBLISH = "WOULD_PUBLISH"
    """A dry run: the file passed the gate, and these keys would be written."""


class PublishedObjectMismatch(DomainError):
    """An object landed in the bucket with another digest than the bytes sent; nothing more is written."""

    def __init__(self, key: str, expected: str, found: str | None) -> None:
        self.key = key
        self.expected = expected
        self.found = found
        super().__init__(
            f"{key} landed in the bucket as {found[:12] if found else 'an object with no recorded digest'}, "
            f"not {expected[:12]}; metadata.json was not written, so the file is not indexed"
        )


@dataclass(frozen=True, slots=True)
class FileRefusal:
    code: FileRefusalCode
    message: str
    hint: str | None = None
    failing_checks: tuple[QualityCheck, ...] = ()


@dataclass(frozen=True, slots=True)
class PublishRequest:
    """What to publish: a built `.docx`, or a directory of them; where the recipes are; whether to write."""

    path: Path
    recipes_dir: Path | None = None
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class _Staged:
    """One file's five objects, staged as the bytes to upload, in upload order."""

    keys: BuiltFileKeys
    bodies: tuple[bytes, bytes, bytes, bytes, bytes]

    def pairs(self) -> tuple[tuple[str, bytes], ...]:
        return tuple(zip(self.keys.in_order, self.bodies, strict=True))


@dataclass(frozen=True, slots=True)
class FilePlan:
    """One built file after the gate: refused, or ready to upload under `keys` with its metadata."""

    docx: Path
    slug: str
    refusal: FileRefusal | None = None
    keys: BuiltFileKeys | None = None
    metadata: BuiltFileMetadata | None = field(default=None, repr=False)
    staged: _Staged | None = field(default=None, repr=False)
    warned_checks: tuple[QualityCheck, ...] = ()

    @property
    def refused(self) -> bool:
        return self.refusal is not None


@dataclass(frozen=True, slots=True)
class PublishPlan:
    files: tuple[FilePlan, ...]

    @property
    def publishable(self) -> tuple[FilePlan, ...]:
        return tuple(one for one in self.files if not one.refused)


@dataclass(frozen=True, slots=True)
class PublishOutcome:
    """What happened to one file: its status, the keys it has under `files/`, and what was written."""

    docx: Path
    slug: str
    status: PublishStatus
    refusal: FileRefusal | None = None
    keys: tuple[str, ...] = ()
    written: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    warned_checks: tuple[QualityCheck, ...] = ()


@dataclass(frozen=True, slots=True)
class PublishResult:
    outcomes: tuple[PublishOutcome, ...]
    dry_run: bool

    @property
    def refused(self) -> tuple[PublishOutcome, ...]:
        return tuple(one for one in self.outcomes if one.status is PublishStatus.REFUSED)


@dataclass(frozen=True, slots=True)
class FoundBuiltFile:
    """A published file a lookup found: where its objects are, and its metadata."""

    key_prefix: str
    metadata: BuiltFileMetadata = field(repr=False)


@dataclass(frozen=True, slots=True)
class SourceLookup:
    """Every published file with a card from the source asked about, and every metadata.json not read."""

    found: tuple[FoundBuiltFile, ...]
    unreadable: tuple[str, ...] = ()
    """Keys of `metadata.json` objects this build could not read: a takedown looks at each by hand."""


@dataclass(frozen=True, slots=True)
class DisclosureLookup:
    """The key prefix of every published file with a card a school or team disclosed. Names neither."""

    found: tuple[str, ...]
    unreadable: tuple[str, ...] = ()
    """Keys of provenance sidecars this build could not read: a takedown looks at each by hand."""


def built_files_in(path: Path) -> tuple[Path, ...]:
    """`path` itself when it is a file; else every `*.docx` directly in it, by name, hidden ones left out."""
    if path.is_file():
        return (path,)
    return tuple(sorted(one for one in path.glob("*.docx") if one.is_file() and not one.name.startswith(".")))


def published_recipe(recipe: FileRecipe) -> bytes:
    """The recipe as published: its model as YAML, every pin without :data:`STRIPPED_PIN_FIELDS`.

    Rendered from the model, so the original's comments, which can name anything, are not carried
    either. Field order is the model's; `None` fields are left out, as the recipe hash leaves them.
    """
    document: dict[str, Any] = recipe.model_dump(mode="json", exclude_none=True)
    for pocket in document["structure"]:
        for hat in pocket.get("hats", ()):
            _strip_blocks(hat["blocks"])
        _strip_blocks(pocket.get("blocks", ()))
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode("utf-8")


def _strip_blocks(blocks: Sequence[Mapping[str, Any]]) -> None:
    for block in blocks:
        for item in block["items"]:
            pin = item.get("pin")
            if isinstance(pin, dict):
                for name in STRIPPED_PIN_FIELDS:
                    pin.pop(name, None)  # pyright: ignore[reportUnknownMemberType]


class FilePublishService:
    """Gates built files on their quality reports and publishes those that pass to one bucket's `files/`.

    `bucket` builds the store for this environment's bucket; it is called only to upload or look up,
    never by a dry run. `quality` is the quality check `files build` and `files check` run. `files_dir`
    is where recipes are looked for by default (`<files_dir>/recipes/<topic>/<slug>.yaml`).
    """

    def __init__(
        self,
        *,
        bucket: Callable[[], EvidenceObjectStore],
        quality: FileQualityService,
        files_dir: Path,
    ) -> None:
        self._bucket = bucket
        self._quality = quality
        self._files_dir = files_dir

    async def run(self, request: PublishRequest) -> PublishResult:
        """:meth:`plan`, then, unless a dry run, :meth:`publish`."""
        plan = await self.plan(request)
        if request.dry_run:
            return PublishResult(outcomes=tuple(_planned(one) for one in plan.files), dry_run=True)
        return await self.publish(plan)

    async def plan(self, request: PublishRequest) -> PublishPlan:
        """Every built file at `request.path` through the gate. Reads this machine only."""
        return PublishPlan(
            files=tuple(
                [await self._plan_one(docx, request.recipes_dir) for docx in built_files_in(request.path)]
            )
        )

    async def publish(self, plan: PublishPlan) -> PublishResult:
        """Upload every file the plan lets through, metadata last; refused files as they were planned."""
        bucket = self._bucket() if plan.publishable else None
        outcomes: list[PublishOutcome] = []
        for one in plan.files:
            if one.staged is None or bucket is None:
                outcomes.append(_planned(one))
                continue
            outcomes.append(await self._upload(bucket, one))
        return PublishResult(outcomes=tuple(outcomes), dry_run=False)

    async def find_by_source(self, source_sha256: str) -> SourceLookup:
        """Every published file whose `metadata.json` lists `source_sha256`, by key prefix."""
        bucket = self._bucket()
        found: list[FoundBuiltFile] = []
        unreadable: list[str] = []
        listing = await bucket.list_objects(FILES_PREFIX)
        with tempfile.TemporaryDirectory(prefix="files-lookup-") as scratch:
            for index, info in enumerate(one for one in listing if one.key.endswith(f"/{METADATA_NAME}")):
                landed = Path(scratch) / f"{index}.json"
                await bucket.get_file(info.key, landed)
                try:
                    metadata = BuiltFileMetadata.model_validate_json(landed.read_bytes())
                except ValidationError:
                    unreadable.append(info.key)
                    continue
                if source_sha256 in metadata.source_sha256s:
                    found.append(FoundBuiltFile(key_prefix=metadata.key_prefix, metadata=metadata))
        return SourceLookup(found=tuple(found), unreadable=tuple(unreadable))

    async def find_by_disclosure(
        self, *, school: str | None = None, team_code: str | None = None
    ) -> DisclosureLookup:
        """Every published file whose sidecar has a card disclosed by `school`, `team_code`, or both.

        Read over the `.provenance.json` objects under `files/`, sidecars of files whose `metadata.json`
        never landed included, since their cards are in the bucket all the same. Matched exactly as
        disclosed, never folded or expanded. With both, one card must name both. The result names
        prefixes and keys only.
        """
        if school is None and team_code is None:
            raise ValueError("find_by_disclosure is asked for a school, a team code, or both")
        bucket = self._bucket()
        found: list[str] = []
        unreadable: list[str] = []
        listing = await bucket.list_objects(FILES_PREFIX)
        sidecars = [one.key for one in listing if one.key.endswith(f".docx{PROVENANCE_SIDECAR_SUFFIX}")]
        with tempfile.TemporaryDirectory(prefix="files-lookup-") as scratch:
            for index, key in enumerate(sidecars):
                landed = Path(scratch) / f"{index}.json"
                await bucket.get_file(key, landed)
                manifest = _read_manifest(landed.read_bytes())
                if manifest is None:
                    unreadable.append(key)
                    continue
                if any(
                    (school is None or card.school == school)
                    and (team_code is None or card.team_code == team_code)
                    for card in manifest.cards
                ):
                    found.append(key.rsplit("/", 1)[0] + "/")
        return DisclosureLookup(found=tuple(found), unreadable=tuple(unreadable))

    # -- the gate ---------------------------------------------------------------------------------

    async def _plan_one(self, docx_path: Path, recipes_dir: Path | None) -> FilePlan:
        slug = docx_path.name.removesuffix(".docx")
        docx = docx_path.read_bytes()
        docx_sha256 = hashlib.sha256(docx).hexdigest()
        sidecar_path = docx_path.with_name(provenance_sidecar_name(docx_path.name))
        sidecar = sidecar_path.read_bytes() if sidecar_path.is_file() else None

        def refused(refusal: FileRefusal) -> FilePlan:
            return FilePlan(docx=docx_path, slug=slug, refusal=refusal)

        report_path = docx_path.with_name(quality_report_names(docx_path.name)[0])
        report = _read_report(report_path)
        if report is None:
            return refused(
                FileRefusal(
                    FileRefusalCode.QUALITY_REPORT_MISSING,
                    f"{report_path.name} is missing or is not a quality report this build reads",
                    hint=f"Check it with `debate-research files check {docx_path}`, then publish again.",
                )
            )
        if report.docx_sha256 != docx_sha256:
            return refused(
                FileRefusal(
                    FileRefusalCode.QUALITY_REPORT_STALE,
                    f"{report_path.name} is the report for {report.docx_sha256[:12]}, and the file is "
                    f"{docx_sha256[:12]}: the file changed after it was checked",
                    hint=f"Check it again with `debate-research files check {docx_path}`, then publish.",
                )
            )
        manifest = _read_manifest(sidecar)
        if manifest is not None and manifest.recipe_status is not RecipeStatus.READY:
            draft = manifest.recipe_status is RecipeStatus.DRAFT
            return refused(
                FileRefusal(
                    FileRefusalCode.BUILT_FROM_A_DRAFT if draft else FileRefusalCode.RECIPE_STATUS_UNRECORDED,
                    "the file was built from a draft recipe (status: draft), and a draft is never published"
                    if draft
                    else "the sidecar does not record the recipe's status: the file was built before it was",
                    hint="Mark the recipe status: ready once it is edited, build it again, then publish."
                    if draft
                    else "Build it again with `debate-research files build` over the same recipe.",
                )
            )
        if report.status is not CheckStatus.PASS:
            return refused(_quality_refusal(report, docx_path, fresh=False))
        fresh = await self._quality.check_file(docx, sidecar)
        if fresh.status is not CheckStatus.PASS or manifest is None:
            return refused(_quality_refusal(fresh, docx_path, fresh=True))
        try:
            prefix = built_file_prefix(
                topic=manifest.topic,
                side=Side(manifest.side),
                position=manifest.position,
                slug=slug,
                recipe_hash=manifest.recipe_hash,
            )
        except ValueError as error:
            return refused(
                FileRefusal(
                    FileRefusalCode.SLUG_INVALID,
                    f"{docx_path.name} does not make a key: {error}",
                    hint="Name the recipe in kebab-case (politics-da-answers.yaml) and build it again.",
                )
            )
        recipe_or_refusal = self._recipe(manifest, slug, recipes_dir)
        if isinstance(recipe_or_refusal, FileRefusal):
            return refused(recipe_or_refusal)
        recipe = recipe_or_refusal
        _check_pins_name_the_sidecars_cards(recipe, manifest)

        keys = built_file_keys(prefix, slug)
        bodies = (docx, sidecar or b"", fresh.to_json_bytes(), published_recipe(recipe))
        objects = tuple(
            PublishedObject(
                name=key.removeprefix(prefix), bytes=len(body), sha256=hashlib.sha256(body).hexdigest()
            )
            for key, body in zip(keys.in_order[:-1], bodies, strict=True)
        )
        warned = tuple(one.check for one in fresh.checks if one.warnings)
        metadata = BuiltFileMetadata(
            key_prefix=prefix,
            slug=slug,
            title=manifest.title,
            topic=manifest.topic,
            format=Event(manifest.format),
            caselist=manifest.caselist,
            position=manifest.position,
            side=Side(manifest.side),
            card_count=len(manifest.cards),
            recipe_hash=manifest.recipe_hash,
            recipe_status=RecipeStatus.READY,
            builder_version=manifest.builder_version,
            parser_version=fresh.parser_version,
            style_profile_version=fresh.style_profile_version,
            fingerprint_version=fresh.fingerprint_version,
            checker_version=fresh.checker_version,
            quality_status="PASS",
            quality_warnings=sum(one.warnings for one in fresh.checks),
            warned_checks=tuple(str(one) for one in warned),
            built_at=manifest.built_at,
            docx_sha256=docx_sha256,
            objects=objects,
            sources=published_sources(manifest.cards),
            caselists=tuple(sorted({card.caselist for card in manifest.cards})),
            source_sha256s=tuple(sorted({card.source_sha256 for card in manifest.cards})),
        )
        return FilePlan(
            docx=docx_path,
            slug=slug,
            keys=keys,
            metadata=metadata,
            staged=_Staged(keys=keys, bodies=(*bodies, metadata.to_json_bytes())),
            warned_checks=warned,
        )

    def _recipe(
        self, manifest: FileProvenanceManifest, slug: str, recipes_dir: Path | None
    ) -> FileRecipe | FileRefusal:
        directory = (
            recipes_dir if recipes_dir is not None else self._files_dir / RECIPES_DIRECTORY / manifest.topic
        )
        path = directory / f"{slug}.yaml"
        if not path.is_file():
            return FileRefusal(
                FileRefusalCode.RECIPE_NOT_FOUND,
                f"no recipe {path.name} in {directory}",
                hint="Name the directory the recipe is in with --recipes.",
            )
        loaded = load_recipe(path.read_text(encoding="utf-8"))
        if loaded.recipe is None or loaded.recipe_hash != manifest.recipe_hash:
            return FileRefusal(
                FileRefusalCode.RECIPE_CHANGED,
                f"{path.name} is not the recipe the file was built from (its hash is "
                f"{(loaded.recipe_hash or 'unreadable')[:12]}, the sidecar's {manifest.recipe_hash[:12]})",
                hint="Build the file again from the recipe as it is now, then publish.",
            )
        return loaded.recipe

    # -- uploading --------------------------------------------------------------------------------

    async def _upload(self, bucket: EvidenceObjectStore, plan: FilePlan) -> PublishOutcome:
        assert plan.staged is not None and plan.keys is not None
        written: list[str] = []
        skipped: list[str] = []
        with tempfile.TemporaryDirectory(prefix="files-publish-") as scratch:
            for index, (key, body) in enumerate(plan.staged.pairs()):
                expected = hashlib.sha256(body).hexdigest()
                if await _recorded_digest(bucket, key) == expected:
                    skipped.append(key)
                    continue
                staged = Path(scratch) / str(index)
                staged.write_bytes(body)
                stored = await bucket.put_file(key, staged)
                if stored.sha256 != expected:
                    raise PublishedObjectMismatch(key, expected, stored.sha256)
                read_back = await _recorded_digest(bucket, key)
                if read_back != expected:
                    raise PublishedObjectMismatch(key, expected, read_back)
                written.append(key)
        return PublishOutcome(
            docx=plan.docx,
            slug=plan.slug,
            status=PublishStatus.PUBLISHED if written else PublishStatus.SKIPPED,
            keys=plan.keys.in_order,
            written=tuple(written),
            skipped=tuple(skipped),
            warned_checks=plan.warned_checks,
        )


def _planned(plan: FilePlan) -> PublishOutcome:
    if plan.refusal is not None:
        return PublishOutcome(
            docx=plan.docx, slug=plan.slug, status=PublishStatus.REFUSED, refusal=plan.refusal
        )
    assert plan.keys is not None
    return PublishOutcome(
        docx=plan.docx,
        slug=plan.slug,
        status=PublishStatus.WOULD_PUBLISH,
        keys=plan.keys.in_order,
        warned_checks=plan.warned_checks,
    )


async def _recorded_digest(bucket: EvidenceObjectStore, key: str) -> str | None:
    try:
        return (await bucket.head(key)).sha256
    except NotFound:
        return None


def _read_report(path: Path) -> FileQualityReport | None:
    if not path.is_file():
        return None
    try:
        return FileQualityReport.model_validate_json(path.read_bytes())
    except ValidationError:
        return None


def _read_manifest(sidecar: bytes | None) -> FileProvenanceManifest | None:
    if sidecar is None:
        return None
    try:
        return FileProvenanceManifest.model_validate_json(sidecar)
    except ValidationError:
        return None


def _quality_refusal(report: FileQualityReport, docx_path: Path, *, fresh: bool) -> FileRefusal:
    failing = tuple(one.check for one in report.checks if one.status is CheckStatus.FAIL)
    when = "checked again now" if fresh else "as its quality report records it"
    return FileRefusal(
        FileRefusalCode.QUALITY_FAILED,
        f"the file does not PASS, {when}: {', '.join(str(one) for one in failing) or 'no sidecar'} failed",
        hint=f"See `debate-research files check {docx_path}`; only a PASS file is published.",
        failing_checks=failing,
    )


def _check_pins_name_the_sidecars_cards(recipe: FileRecipe, manifest: FileProvenanceManifest) -> None:
    """Every pin, stripped, still names its card's source and first element as the sidecar records them.

    The sidecar was built from this recipe (its hash is the sidecar's), so a difference is a bug, not a
    condition: it raises :class:`AssertionError` rather than publish a recipe that names other cards.
    """
    by_path = {entry.recipe_path: entry for entry in manifest.cards}
    for location, ref in recipe.card_refs():
        if ref.pin is None:
            continue
        entry = by_path.get(render_location(location))
        assert entry is not None, f"the sidecar has no card at {render_location(location)}"
        assert (ref.pin.caselist, ref.pin.source_sha256, ref.pin.element_index) == (
            entry.caselist,
            entry.source_sha256,
            entry.first_element_index,
        ), f"the pin at {render_location(location)} names another card than the sidecar does"

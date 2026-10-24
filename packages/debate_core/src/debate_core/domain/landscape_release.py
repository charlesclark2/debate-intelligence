"""The position ids a published landscape report has released, and the rules that keep them.

A landscape report names positions by id and says which `taxonomy_version` it counted under
(`v1-e32-t03`). Once a report under a version is published, its ids are *released*: a reader of
that report, or a later report comparing weeks, must still find each id meaning the same argument.
So a released id is never deleted or reused (`docs/guides/landscape-taxonomy.md`, "Ids are
forever"); it is retired with `deprecated: true`, and `merged_into` when it was renamed or merged.

`v1-e32-t08-released-position-ids` enforces that. The released form of each topic is recorded in a
committed lock file, `config/landscape/released.yaml`, a :class:`ReleaseLock`: per topic and
released version, each position id with its kind and side, and nothing else (no labels, no
counts). The operator writes it with `scripts/release_landscape_taxonomy.py` when a report under a
new version is first published; CI compares the committed taxonomy files with it and needs neither
the network nor git history.

What a release records is what a report under that version counted against: the topic's own
positions with generic.yaml's for its event (:meth:`Taxonomy.with_generic`), retired ones included.
So a generic position a report used is held to the same rule as the topic's own.

:func:`release_findings` and :func:`merged_into_findings` return every break of the rules, each a
:class:`ReleaseFinding` naming the topic, the id and the :class:`ReleaseRule`; the adapter that
reads the files puts the file's name on each. A label may change (a rename that still names the
same argument); only the id, its kind and its side are fixed.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from debate_core.domain.base import DomainModel
from debate_core.domain.landscape import PositionId, PositionKind, PositionSide, Taxonomy, TaxonomyVersion

__all__ = [
    "RULE_TEXT",
    "ReleaseFinding",
    "ReleaseLock",
    "ReleaseRule",
    "ReleasedPosition",
    "TaxonomyRelease",
    "merged_into_findings",
    "release_findings",
]


class ReleaseRule(StrEnum):
    """Which rule a finding breaks; :data:`RULE_TEXT` says each in a sentence."""

    RELEASED_ID_MISSING = "released-id-missing"
    KIND_OR_SIDE_CHANGED = "kind-or-side-changed"
    CHANGED_WITHOUT_BUMP = "changed-without-bump"
    VERSION_BELOW_RELEASED = "version-below-released"
    MERGED_INTO_RETIRED = "merged-into-retired"


RULE_TEXT: Final[Mapping[ReleaseRule, str]] = {
    ReleaseRule.RELEASED_ID_MISSING: "a released id is retired with deprecated or merged_into, never deleted",
    ReleaseRule.KIND_OR_SIDE_CHANGED: (
        "a released id keeps its kind and side; a different argument gets a new id"
    ),
    ReleaseRule.CHANGED_WITHOUT_BUMP: (
        "a released version's positions are fixed; a change bumps taxonomy_version here and in topics.yaml"
    ),
    ReleaseRule.VERSION_BELOW_RELEASED: "taxonomy_version only moves forward from a released version",
    ReleaseRule.MERGED_INTO_RETIRED: "merged_into names a position that is not retired",
}


class ReleasedPosition(DomainModel):
    """One released id, with the kind and side it was released as."""

    id: PositionId
    kind: PositionKind
    side: PositionSide


class TaxonomyRelease(DomainModel):
    """One topic's positions as a report under `taxonomy_version` counted against them."""

    topic_id: PositionId = Field(description="The topic, as topics.yaml names it.")
    taxonomy_version: TaxonomyVersion = Field(
        description="The version the first published report counted under."
    )
    positions: tuple[ReleasedPosition, ...] = Field(
        description="Every position of the merged taxonomy, retired ones included, in file order."
    )

    @model_validator(mode="after")
    def _check_ids(self) -> Self:
        seen: set[str] = set()
        for one in self.positions:
            if one.id in seen:
                raise ValueError(f"{self.topic_id} {self.taxonomy_version} lists {one.id} twice")
            seen.add(one.id)
        return self

    @classmethod
    def of(cls, taxonomy: Taxonomy) -> TaxonomyRelease:
        """The release of `taxonomy`, a topic's merged taxonomy, at its own version."""
        return cls(
            topic_id=taxonomy.topic_id,
            taxonomy_version=taxonomy.taxonomy_version,
            positions=tuple(
                ReleasedPosition(id=one.id, kind=one.kind, side=one.side) for one in taxonomy.positions
            ),
        )


class ReleaseLock(DomainModel):
    """`config/landscape/released.yaml`: every released (topic, version), in the order released."""

    schema_version: Literal[1] = Field(default=1, description="Version of this file's shape.")
    releases: tuple[TaxonomyRelease, ...] = Field(
        default=(), description="Empty until a report is published."
    )

    @model_validator(mode="after")
    def _check_releases(self) -> Self:
        seen: set[tuple[str, str]] = set()
        for release in self.releases:
            key = (release.topic_id, release.taxonomy_version)
            if key in seen:
                raise ValueError(f"{release.topic_id} {release.taxonomy_version} is released twice")
            seen.add(key)
        return self

    def releases_of(self, topic_id: str) -> tuple[TaxonomyRelease, ...]:
        """The topic's releases, in the order released."""
        return tuple(release for release in self.releases if release.topic_id == topic_id)

    def with_release(self, taxonomy: Taxonomy, version: str) -> ReleaseLock:
        """This lock with `taxonomy` (a topic's merged taxonomy) released at `version`.

        Refused when the taxonomy is not at `version`, so a lock written late cannot record a later
        edit, and when `version` is already released, since a released version is never rewritten.
        """
        if taxonomy.taxonomy_version != version:
            raise ValueError(f"{taxonomy.topic_id} is at {taxonomy.taxonomy_version}, not {version}")
        if any(one.taxonomy_version == version for one in self.releases_of(taxonomy.topic_id)):
            raise ValueError(
                f"{taxonomy.topic_id} {version} is already released; a release is never rewritten"
            )
        return self.model_copy(update={"releases": (*self.releases, TaxonomyRelease.of(taxonomy))})


class ReleaseFinding(DomainModel):
    """One break of a release rule: the topic, the id (when the rule is about one) and the rule."""

    topic_id: str
    position_id: str | None
    rule: ReleaseRule
    detail: str = Field(description="What is wrong, in words, without the rule's sentence.")

    @property
    def message(self) -> str:
        subject = f"{self.position_id} " if self.position_id is not None else ""
        return f"{subject}{self.detail}. Rule ({self.rule.value}): {RULE_TEXT[self.rule]}"


def release_findings(lock: ReleaseLock, taxonomies: Mapping[str, Taxonomy]) -> tuple[ReleaseFinding, ...]:
    """Every way the current merged taxonomies (by topic id) break what `lock` released.

    For each released topic: a released id the taxonomy no longer has, or has with another kind or
    side; a taxonomy version below the topic's latest release; and, when the taxonomy is at a
    released version, every id that differs from that release.
    """
    findings: list[ReleaseFinding] = []
    for topic_id in dict.fromkeys(release.topic_id for release in lock.releases):
        releases = lock.releases_of(topic_id)
        current = taxonomies.get(topic_id)
        if current is None:
            versions = ", ".join(release.taxonomy_version for release in releases)
            findings.append(
                ReleaseFinding(
                    topic_id=topic_id,
                    position_id=None,
                    rule=ReleaseRule.RELEASED_ID_MISSING,
                    detail=f"{topic_id} was released in {versions} and has no taxonomy now",
                )
            )
            continue
        findings += _released_ids_kept(topic_id, releases, current)
        findings += _version_findings(topic_id, releases, current)
    return tuple(findings)


def _released_ids_kept(
    topic_id: str, releases: tuple[TaxonomyRelease, ...], current: Taxonomy
) -> list[ReleaseFinding]:
    """Each released id, at the first release that has it, still present with its kind and side."""
    now = {one.id: one for one in current.positions}
    findings: list[ReleaseFinding] = []
    seen: set[str] = set()
    for release in releases:
        for released in release.positions:
            if released.id in seen:
                continue
            seen.add(released.id)
            where = f"was released in {topic_id} {release.taxonomy_version}"
            found = now.get(released.id)
            if found is None:
                findings.append(
                    ReleaseFinding(
                        topic_id=topic_id,
                        position_id=released.id,
                        rule=ReleaseRule.RELEASED_ID_MISSING,
                        detail=f"{where} and is missing",
                    )
                )
            elif (found.kind, found.side) != (released.kind, released.side):
                findings.append(
                    ReleaseFinding(
                        topic_id=topic_id,
                        position_id=released.id,
                        rule=ReleaseRule.KIND_OR_SIDE_CHANGED,
                        detail=(
                            f"{where} as kind {released.kind.value}, side {released.side.value} "
                            f"and is now kind {found.kind.value}, side {found.side.value}"
                        ),
                    )
                )
    return findings


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _version_findings(
    topic_id: str, releases: tuple[TaxonomyRelease, ...], current: Taxonomy
) -> list[ReleaseFinding]:
    """A version below the latest release, or a released version whose positions have changed."""
    latest = max(releases, key=lambda release: _version_key(release.taxonomy_version))
    if _version_key(current.taxonomy_version) < _version_key(latest.taxonomy_version):
        return [
            ReleaseFinding(
                topic_id=topic_id,
                position_id=None,
                rule=ReleaseRule.VERSION_BELOW_RELEASED,
                detail=(
                    f"is at {current.taxonomy_version}, below {topic_id}'s released {latest.taxonomy_version}"
                ),
            )
        ]
    same = next((one for one in releases if one.taxonomy_version == current.taxonomy_version), None)
    if same is None:
        return []
    released = {one.id: one for one in same.positions}
    now = {one.id: one for one in TaxonomyRelease.of(current).positions}
    lock_of = f"the lock of {topic_id} {same.taxonomy_version}"
    findings: list[ReleaseFinding] = []
    for position_id in dict.fromkeys([*released, *now]):
        if position_id not in released:
            detail = f"is not in {lock_of}"
        elif position_id not in now:
            detail = f"is in {lock_of} and not in the file at that version"
        elif released[position_id] != now[position_id]:
            detail = f"differs from {lock_of} in kind or side"
        else:
            continue
        findings.append(
            ReleaseFinding(
                topic_id=topic_id,
                position_id=position_id,
                rule=ReleaseRule.CHANGED_WITHOUT_BUMP,
                detail=detail,
            )
        )
    return findings


def merged_into_findings(taxonomy: Taxonomy) -> tuple[ReleaseFinding, ...]:
    """Every retired position of one file whose `merged_into` names another retired position.

    A merge points a reader of an earlier report at the position the argument is counted under now,
    so it names an active one; when that one is retired in turn, the merge is moved on to its
    successor in the same edit.
    """
    return tuple(
        ReleaseFinding(
            topic_id=taxonomy.topic_id,
            position_id=one.id,
            rule=ReleaseRule.MERGED_INTO_RETIRED,
            detail=f"is merged into {one.merged_into}, which is retired",
        )
        for one in taxonomy.positions
        if one.merged_into is not None and taxonomy.position(one.merged_into).deprecated
    )

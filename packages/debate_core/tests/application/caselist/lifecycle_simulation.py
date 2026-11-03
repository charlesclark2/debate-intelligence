"""S3 lifecycle rules run by hand against moto's bucket, which never runs them itself (`v1-e31-t16`).

moto stores a lifecycle configuration and does nothing with it. These tests need to see one run:
a retired directory's current versions expire, the grace period passes, the delete markers left
behind are removed, and a restored object is left alone. So :class:`LifecycleSimulation` applies the
bucket's own configuration, read back from moto, one simulated day at a time, as AWS documents it:

* `Expiration` with `Days`: a current object version older than that many days, counted from its
  creation, is expired: a delete marker is put in front of it. A current delete marker with no
  version behind it that the rule's filter matches, and that is old enough, is removed ("When you
  specify the Days tag, Amazon S3 automatically performs ExpiredObjectDeleteMarker cleanup").
* `Expiration` with `ExpiredObjectDeleteMarker`: a current delete marker with no version behind it is
  removed.
* `NoncurrentVersionExpiration` with `NoncurrentDays`: a noncurrent version, delete markers among
  them, that many days after it became noncurrent, is deleted for good.
* A filter matches on the key's prefix and on every tag it names, compared with the version's own
  tags. A delete marker has no tags, so a rule with a tag filter never matches one.
* One action per version per run, decided from the bucket as it stood at the start of the run.

Ages are in simulated days. moto's timestamps are all "now", so this class records the day it
first saw each version, and the day it first saw each version noncurrent; a test calls
:meth:`LifecycleSimulation.observe` after acting on the bucket, at the day it acted. It leaves out
what these tests never meet: transitions, `Date`, `NewerNoncurrentVersions`, size filters and
rounding to midnight UTC. Written from the AWS user guide's "Expiring objects" and "Examples of S3
Lifecycle configurations" pages, never from what the code under test does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client


@dataclass(frozen=True, slots=True)
class StoredVersion:
    key: str
    version_id: str
    is_latest: bool
    is_delete_marker: bool


@dataclass
class LifecycleSimulation:
    """The bucket's lifecycle configuration, run on demand. Construct it, then :meth:`observe` day 0."""

    client: S3Client
    bucket: str
    day: int = 0
    created_on: dict[str, int] = field(default_factory=dict[str, int])
    noncurrent_since: dict[str, int] = field(default_factory=dict[str, int])

    def observe(self, day: int) -> None:
        """Record every version not yet seen as created on `day`, and every newly noncurrent one."""
        self.day = day
        for version in self.versions():
            self.created_on.setdefault(version.version_id, day)
            if not version.is_latest:
                self.noncurrent_since.setdefault(version.version_id, day)

    def run(self, day: int) -> list[tuple[str, str]]:
        """One lifecycle run on `day`. Returns what it did, as `(action, key)` pairs."""
        self.observe(day)
        rules = [
            rule
            for rule in self.client.get_bucket_lifecycle_configuration(Bucket=self.bucket)["Rules"]
            if rule.get("Status") == "Enabled"
        ]
        stored = self.versions()
        by_key: dict[str, list[StoredVersion]] = {}
        for version in stored:
            by_key.setdefault(version.key, []).append(version)
        done: list[tuple[str, str]] = []
        for version in stored:
            action = self._action(version, rules, alone=len(by_key[version.key]) == 1)
            if action == "expire":
                self.client.delete_object(Bucket=self.bucket, Key=version.key)
            elif action is not None:
                self.client.delete_object(Bucket=self.bucket, Key=version.key, VersionId=version.version_id)
            if action is not None:
                done.append((action, version.key))
        self.observe(day)
        return done

    def versions(self, prefix: str = "") -> list[StoredVersion]:
        found: list[StoredVersion] = []
        for page in self.client.get_paginator("list_object_versions").paginate(
            Bucket=self.bucket, Prefix=prefix
        ):
            for item in page.get("Versions", []):
                found.append(
                    StoredVersion(
                        item.get("Key", ""), item.get("VersionId", ""), item.get("IsLatest", False), False
                    )
                )
            for item in page.get("DeleteMarkers", []):
                found.append(
                    StoredVersion(
                        item.get("Key", ""), item.get("VersionId", ""), item.get("IsLatest", False), True
                    )
                )
        return found

    # -- the rules, as AWS documents them --------------------------------------------------------

    def _action(self, version: StoredVersion, rules: list[Any], *, alone: bool) -> str | None:
        tags = {} if version.is_delete_marker else self._tags(version)
        for rule in rules:
            if not _matches(rule.get("Filter", {}), version.key, tags):
                continue
            expiration = rule.get("Expiration", {})
            old_enough = "Days" in expiration and self._age(version) >= expiration["Days"]
            if version.is_latest and not version.is_delete_marker and old_enough:
                return "expire"
            removes_markers = expiration.get("ExpiredObjectDeleteMarker") is True or old_enough
            if version.is_latest and version.is_delete_marker and alone and removes_markers:
                return "remove-expired-delete-marker"
            noncurrent = rule.get("NoncurrentVersionExpiration", {})
            noncurrent_for = (
                None if version.is_latest else self.day - self.noncurrent_since[version.version_id]
            )
            if noncurrent_for is not None and noncurrent_for >= noncurrent.get(
                "NoncurrentDays", noncurrent_for + 1
            ):
                return "delete-noncurrent"
        return None

    def _age(self, version: StoredVersion) -> int:
        """Days since the version was created: what `Expiration` with `Days` counts."""
        return self.day - self.created_on[version.version_id]

    def _tags(self, version: StoredVersion) -> dict[str, str]:
        tag_set = self.client.get_object_tagging(
            Bucket=self.bucket, Key=version.key, VersionId=version.version_id
        )
        return {tag["Key"]: tag["Value"] for tag in tag_set["TagSet"]}


def _matches(rule_filter: Any, key: str, tags: dict[str, str]) -> bool:
    """A lifecycle filter: a prefix, a tag, or `And` of a prefix and tags. Every named tag must match."""
    combined = rule_filter.get("And", rule_filter)
    wanted = list(combined.get("Tags", []))
    if "Tag" in rule_filter:
        wanted.append(rule_filter["Tag"])
    return key.startswith(combined.get("Prefix", "")) and all(
        tags.get(tag["Key"]) == tag["Value"] for tag in wanted
    )

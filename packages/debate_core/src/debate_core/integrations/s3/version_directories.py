"""The parsed store's version directories in the bucket, where retiring one tags it (`v1-e31-t16`).

The bucket implementation of
:class:`~debate_core.application.ports.version_directories.VersionDirectoryPlace`, over
`parsed/<caselist>/<version>/`. It deletes nothing and cannot: it runs as the everyday
`EvidenceOperator` profile, which has no `s3:DeleteObject` (PM ruling, 2026-10-15). Retiring a
directory puts the retirement tag on each of its current objects, keeping any other tag the object
has, and the bucket's lifecycle rule on `parsed/` expires what carries it after the grace period
(`infrastructure/modules/evidence_bucket/main.tf`). Restoring sets the tag to `restored`, which the
rule does not match.

The calls are the three the permission set grants under `parsed/`: `ListBucket` with a prefix,
`GetObjectTagging` and `PutObjectTagging`. A directory holds thousands of per-source files, one
request each, so they run on a small pool of threads, all through one client.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Final

from debate_core.application.ports.evidence_store import validate_object_key
from debate_core.application.ports.parsed_store import PARSED_PREFIX
from debate_core.application.ports.version_directories import (
    RESTORED_TAG_VALUE,
    RETIREMENT_TAG_KEY,
    RETIREMENT_TAG_VALUE,
    DirectoryContents,
    RetirementMethod,
)
from debate_core.integrations.s3.client import build_s3_client
from debate_core.integrations.s3.errors import S3Call, mapped_s3_errors

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client
    from mypy_boto3_s3.type_defs import TagTypeDef

__all__ = ["DEFAULT_TAGGING_THREADS", "S3VersionDirectories"]

DEFAULT_TAGGING_THREADS: Final = 16
"""Tagging requests in flight at once. A directory of 10,000 objects is then a minute or two."""

_ENTITY: Final = "parsed store object"


class S3VersionDirectories:
    """`parsed/` in one bucket, as a place whose superseded version directories are tagged.

    Args:
        bucket: The environment's evidence bucket.
        profile: The profile the client was built with: always the everyday one, never the takedown's.
        profile_setting: The setting `profile`'s name came from, for a profile the config lacks.
        login_hint: What a missing or expired session names instead of `aws sso login`, or `None` for
            that command (`v1-e40-t28`). The composition root gives the cloud run's.
        client: An already-built client. The tests pass moto's.
        region: Used only when `client` is not given.
        threads: Tagging requests in flight at once.
    """

    def __init__(
        self,
        *,
        bucket: str,
        profile: str | None = None,
        profile_setting: str | None = None,
        login_hint: str | None = None,
        client: S3Client | None = None,
        region: str | None = None,
        threads: int = DEFAULT_TAGGING_THREADS,
    ) -> None:
        self._bucket = bucket
        self._profile = profile
        self._profile_setting = profile_setting
        self._login_hint = login_hint
        self._threads = threads
        self._client = (
            client
            if client is not None
            else build_s3_client(region=region, profile=profile, profile_setting=profile_setting)
        )

    @property
    def location(self) -> str:
        return f"s3://{self._bucket}"

    @property
    def method(self) -> RetirementMethod:
        return RetirementMethod.TAG

    async def caselists(self) -> tuple[str, ...]:
        return await asyncio.to_thread(self._directories_under, f"{PARSED_PREFIX}/")

    async def version_directories(self, caselist: str) -> tuple[str, ...]:
        return await asyncio.to_thread(self._directories_under, self._prefix(caselist))

    async def contents(self, caselist: str, version: str, *, count_tagged: bool) -> DirectoryContents:
        return await asyncio.to_thread(self._contents, self._prefix(caselist, version), count_tagged)

    async def retire(self, caselist: str, version: str) -> int:
        return await asyncio.to_thread(self._retag, self._prefix(caselist, version), _with_retirement_tag)

    async def restore(self, caselist: str, version: str) -> int:
        return await asyncio.to_thread(self._retag, self._prefix(caselist, version), _without_retirement_tag)

    # ------------------------------------------------------------------------------------------
    # The blocking implementations, each run in a worker thread by the methods above
    # ------------------------------------------------------------------------------------------

    def _prefix(self, *names: str) -> str:
        for name in names:
            if not name or name in {".", ".."} or "/" in name:
                raise ValueError(f"not a caselist or version directory name: {name!r}")
        return "/".join((PARSED_PREFIX, *names)) + "/"

    def _directories_under(self, prefix: str) -> tuple[str, ...]:
        found: list[str] = []
        with mapped_s3_errors(self._call("ListObjectsV2", prefix)):
            pages = self._client.get_paginator("list_objects_v2").paginate(
                Bucket=self._bucket, Prefix=prefix, Delimiter="/"
            )
            for page in pages:
                for common in page.get("CommonPrefixes", []):
                    name = common.get("Prefix", "")[len(prefix) :].rstrip("/")
                    if name:
                        found.append(name)
        return tuple(sorted(found))

    def _objects(self, prefix: str) -> list[tuple[str, int]]:
        listed: list[tuple[str, int]] = []
        with mapped_s3_errors(self._call("ListObjectsV2", prefix)):
            pages = self._client.get_paginator("list_objects_v2").paginate(Bucket=self._bucket, Prefix=prefix)
            for page in pages:
                for stored in page.get("Contents", []):
                    key = stored.get("Key")
                    if key is not None:
                        listed.append((key, stored.get("Size", 0)))
        return listed

    def _contents(self, prefix: str, count_tagged: bool) -> DirectoryContents:
        listed = self._objects(prefix)
        tagged = (
            sum(self._each([key for key, _ in listed], lambda key: _is_retired(self._tags(key))))
            if count_tagged
            else None
        )
        return DirectoryContents(objects=len(listed), bytes=sum(size for _, size in listed), tagged=tagged)

    def _retag(self, prefix: str, change: Callable[[list[TagTypeDef]], list[TagTypeDef] | None]) -> int:
        """Apply `change` to each object's tag set, writing only those it changes. Counts the writes."""

        def one(key: str) -> bool:
            changed = change(self._tags(key))
            if changed is None:
                return False
            with mapped_s3_errors(self._call("PutObjectTagging", key)):
                self._client.put_object_tagging(Bucket=self._bucket, Key=key, Tagging={"TagSet": changed})
            return True

        return sum(self._each([key for key, _ in self._objects(prefix)], one))

    def _tags(self, key: str) -> list[TagTypeDef]:
        with mapped_s3_errors(self._call("GetObjectTagging", key)):
            return list(
                self._client.get_object_tagging(Bucket=self._bucket, Key=validate_object_key(key))["TagSet"]
            )

    def _each(self, keys: list[str], work: Callable[[str], bool]) -> list[bool]:
        if not keys:
            return []
        with ThreadPoolExecutor(max_workers=self._threads) as pool:
            return list(pool.map(work, keys))

    def _call(self, operation: str, key: str) -> S3Call:
        return S3Call(
            operation=operation,
            bucket=self._bucket,
            entity=_ENTITY,
            key=key,
            s3_key=key or None,
            profile=self._profile,
            profile_setting=self._profile_setting,
            given_login_hint=self._login_hint,
        )


def _is_retired(tags: list[TagTypeDef]) -> bool:
    return any(tag["Key"] == RETIREMENT_TAG_KEY and tag["Value"] == RETIREMENT_TAG_VALUE for tag in tags)


def _with_retirement_tag(tags: list[TagTypeDef]) -> list[TagTypeDef] | None:
    if _is_retired(tags):
        return None
    kept = [tag for tag in tags if tag["Key"] != RETIREMENT_TAG_KEY]
    return [*kept, {"Key": RETIREMENT_TAG_KEY, "Value": RETIREMENT_TAG_VALUE}]


def _without_retirement_tag(tags: list[TagTypeDef]) -> list[TagTypeDef] | None:
    if not _is_retired(tags):
        return None
    kept = [tag for tag in tags if tag["Key"] != RETIREMENT_TAG_KEY]
    return [*kept, {"Key": RETIREMENT_TAG_KEY, "Value": RESTORED_TAG_VALUE}]

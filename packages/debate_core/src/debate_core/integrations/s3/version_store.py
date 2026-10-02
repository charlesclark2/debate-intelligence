"""Every version of an evidence object in the bucket, and deleting them: the takedown's S3 adapter.

The bucket implementation of
:class:`~debate_core.application.ports.evidence_versions.EvidenceVersionStore`. Built by the
composition root twice, for two different credentials, and the difference matters:

* With the **`EvidenceRemoval`** profile (`DEBATE_REMOVAL_PROFILE`): `ListObjectVersions`,
  `GetObject` by version and `DeleteObject` by version are all granted under the five removable
  prefixes. This is what `caselist remove --execute` deletes with.
* With the everyday **`EvidenceOperator`** profile: none of them is granted, and :meth:`list_versions`
  raises :class:`~debate_core.application.errors.StoreAccessDenied`. A dry run builds one anyway,
  so that it counts versions the moment the operator profile is granted `s3:ListBucketVersions`
  and says "not counted" until then (the session report's proposal for `v1-e29-t03`).

Deletes are one `DeleteObject` per version, with the version id, which is the only form of delete
that removes a version rather than hiding it behind a delete marker. A takedown deletes tens of
versions, not thousands, so one request each keeps every failure attributable to one key.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from debate_core.application.ports.evidence_store import validate_object_key
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.integrations.s3.client import build_s3_client
from debate_core.integrations.s3.errors import S3Call, mapped_s3_errors

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

__all__ = ["S3EvidenceVersionStore"]

_ENTITY = "evidence object version"


class S3EvidenceVersionStore:
    """An :class:`~debate_core.application.ports.evidence_versions.EvidenceVersionStore` on a bucket.

    Args:
        bucket: The environment's evidence bucket, from Terraform's `evidence_bucket_name`.
        profile: The profile the client was built with, for the `aws sso login` hint.
        client: An already-built client. The tests pass moto's.
        region: Used only when `client` is not given.
    """

    def __init__(
        self,
        *,
        bucket: str,
        profile: str | None = None,
        client: S3Client | None = None,
        region: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._profile = profile
        self._client = client if client is not None else build_s3_client(region=region, profile=profile)

    @property
    def location(self) -> str:
        return f"s3://{self._bucket}"

    @property
    def profile(self) -> str | None:
        return self._profile

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        return await asyncio.to_thread(self._list_versions, prefix)

    async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
        await asyncio.to_thread(self._get_version_file, version, destination)

    async def delete_versions(self, versions: Sequence[ObjectVersion]) -> int:
        return await asyncio.to_thread(self._delete_versions, tuple(versions))

    # ------------------------------------------------------------------------------------------
    # The blocking implementations, each run in a worker thread by the methods above
    # ------------------------------------------------------------------------------------------

    def _list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        found: list[ObjectVersion] = []
        with mapped_s3_errors(self._call("ListObjectVersions", prefix)):
            pages = self._client.get_paginator("list_object_versions").paginate(
                Bucket=self._bucket, Prefix=prefix
            )
            for page in pages:
                for stored in page.get("Versions", []):
                    key = stored.get("Key")
                    if key is None:
                        continue
                    found.append(
                        ObjectVersion(
                            key=key,
                            version_id=stored.get("VersionId"),
                            size=stored.get("Size", 0),
                            is_latest=stored.get("IsLatest", False),
                        )
                    )
                for marker in page.get("DeleteMarkers", []):
                    key = marker.get("Key")
                    if key is None:
                        continue
                    found.append(
                        ObjectVersion(
                            key=key,
                            version_id=marker.get("VersionId"),
                            is_latest=marker.get("IsLatest", False),
                            is_delete_marker=True,
                        )
                    )
        return tuple(
            sorted(found, key=lambda version: (version.key, not version.is_latest, version.version_id or ""))
        )

    def _get_version_file(self, version: ObjectVersion, destination: Path) -> None:
        key = validate_object_key(version.key)
        arguments = {"Bucket": self._bucket, "Key": key}
        if version.version_id is not None:
            arguments["VersionId"] = version.version_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        with mapped_s3_errors(self._call("GetObject", key)):
            body = self._client.get_object(**arguments)["Body"]  # pyright: ignore[reportArgumentType]
            with destination.open("wb") as stream:
                for chunk in iter(lambda: body.read(1024 * 1024), b""):
                    stream.write(chunk)

    def _delete_versions(self, versions: tuple[ObjectVersion, ...]) -> int:
        for version in versions:
            key = validate_object_key(version.key)
            with mapped_s3_errors(self._call("DeleteObject", key)):
                if version.version_id is None:
                    # An unversioned bucket, or one versioned after this object was written: S3 names
                    # that version "null", and deleting by it removes the object rather than marking it.
                    self._client.delete_object(Bucket=self._bucket, Key=key, VersionId="null")
                else:
                    self._client.delete_object(Bucket=self._bucket, Key=key, VersionId=version.version_id)
        return len(versions)

    def _call(self, operation: str, key: str) -> S3Call:
        return S3Call(
            operation=operation,
            bucket=self._bucket,
            entity=_ENTITY,
            key=key,
            s3_key=key or None,
            profile=self._profile,
        )

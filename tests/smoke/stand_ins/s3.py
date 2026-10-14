"""The S3 stand-in, as a check sees it: moto's server, its endpoint, and what it was asked.

The installed build is pointed at :attr:`S3StandIn.endpoint` with `storage.s3.endpoint_url`, the
dev-only setting `v1-e01-t21` adds. The check itself builds its own clients with :meth:`client`, to
create the bucket, sign profiles in as roles and read what the command left, and reads
:meth:`requests` to say what the command asked for. :meth:`refuse` makes the bucket answer a
request with an error, and :meth:`backdate` gives a version an earlier time, both from the server
process's side (`s3_server.py`).

Credentials are moto's documented test credentials (`testing`), which sign requests moto accepts
and AWS would not: nothing here is, or looks like, a real key.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
from tests.smoke.stand_ins.process import StandInProcess

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

__all__ = ["MOTO_TEST_CREDENTIALS", "S3Request", "S3StandIn"]

SERVER = Path(__file__).with_name("s3_server.py")

MOTO_TEST_CREDENTIALS = {"aws_access_key_id": "testing", "aws_secret_access_key": "testing"}
"""moto's documented test credentials. The check's own clients sign with them."""

REGION = "us-east-1"


@dataclass(frozen=True)
class S3Request:
    """One request the stand-in served: what was asked, of what, and which access key signed it."""

    service: str | None
    operation: str
    bucket: str | None
    key: str | None
    version_id: str | None
    access_key: str | None


class S3StandIn:
    """A running moto server, reached at :attr:`endpoint`."""

    def __init__(self, process: StandInProcess) -> None:
        self.process = process
        host, port = process.address("s3")
        self.endpoint = f"http://{host}:{port}"

    @classmethod
    def start(cls, log: Path) -> S3StandIn:
        return cls(StandInProcess.start(SERVER, log=log))

    def stop(self) -> None:
        self.process.stop()

    @property
    def addresses(self) -> Sequence[tuple[str, int]]:
        return self.process.addresses

    def client(self, service: str = "s3", **credentials: str) -> Any:
        """A boto3 client for `service` at the stand-in, signed with moto's test credentials by default."""
        untyped: Any = boto3  # boto3-stubs types `s3` alone here
        return untyped.client(
            service, endpoint_url=self.endpoint, region_name=REGION, **(credentials or MOTO_TEST_CREDENTIALS)
        )

    def versioned_bucket(self, name: str) -> S3Client:
        """Create `name` with versioning on, as every evidence bucket has it, and return a client for it."""
        client: S3Client = self.client("s3")
        client.create_bucket(Bucket=name)
        client.put_bucket_versioning(Bucket=name, VersioningConfiguration={"Status": "Enabled"})
        return client

    def requests(self) -> list[S3Request]:
        """Every request served so far, in order, the check's own included."""
        return [S3Request(**one) for one in self._control("GET", "requests")]

    def requests_since(self, mark: int) -> list[S3Request]:
        """The requests served after the first `mark`: take `len(stand_in.requests())` before a command."""
        return self.requests()[mark:]

    def refuse(
        self,
        operation: str,
        *,
        status: int,
        code: str,
        message: str,
        key: str | None = None,
        key_contains: str | None = None,
        after: int = 0,
    ) -> None:
        """Answer `operation` (on `key`, or a key holding `key_contains`) with an S3 error, from then on.

        The first `after` matching requests are let through. A later call replaces every rule, and
        :meth:`stop_refusing` clears them.
        """
        rule = {
            "operation": operation,
            "status": status,
            "code": code,
            "message": message,
            "key": key,
            "key_contains": key_contains,
            "after": after,
        }
        self._control("PUT", "faults", [rule])

    def stop_refusing(self) -> None:
        self._control("PUT", "faults", [])

    @contextmanager
    def refusing(self, operation: str, **rule: Any) -> Iterator[None]:
        self.refuse(operation, **rule)
        try:
            yield
        finally:
            self.stop_refusing()

    def backdate(self, bucket: str, key: str, version_id: str, last_modified: datetime) -> None:
        """Give one version of `key` an earlier `LastModified`: what an older write would have left."""
        self._control(
            "POST",
            "backdate",
            {
                "bucket": bucket,
                "key": key,
                "version_id": version_id,
                "last_modified": last_modified.isoformat(),
            },
        )

    def _control(self, method: str, route: str, payload: object = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(f"{self.endpoint}/_stand_in/{route}", data=data, method=method)
        with _DIRECT.open(request, timeout=10) as answered:
            return json.loads(answered.read())


_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
"""Straight to the stand-in: a proxy named in pytest's own environment is never asked."""

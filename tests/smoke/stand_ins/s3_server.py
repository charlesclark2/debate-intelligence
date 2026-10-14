"""The S3 stand-in's process: moto in server mode on 127.0.0.1 and an ephemeral port (`v1-e01-t21`).

Started by :class:`tests.smoke.stand_ins.s3.S3StandIn`, never by hand. The installed build reaches
it over loopback, through `storage.s3.endpoint_url`; moto answers S3 and STS (and IAM, which the
test side uses to create the roles a profile signs in as). Nothing here patches the build: it is a
server, and the build is a client of it, exactly as it is of AWS.

moto alone would make a faithful bucket. Three things are added in front of it, each under
`/_stand_in/`, a prefix no S3 key or STS action can reach because moto is never asked for it:

* **A record of every request served** (`GET /_stand_in/requests`): the operation, the bucket and
  key, whether a version was named, and which access key signed it. A check reads it to say what
  the command asked the bucket for, and with which profile, instead of patching the adapter to spy.
  The signature itself, the session token and every body stay out of it.
* **Faults** (`PUT /_stand_in/faults`): rules that answer a matching request with the error S3
  would send, a 403 `AccessDenied` or a 503 `SlowDown`, before moto sees it. What a bucket that
  refuses or fails a call looks like, through botocore's own error path.
* **A backdated version** (`POST /_stand_in/backdate`): one version of a key given an earlier
  `LastModified`, which moto keeps as an attribute and S3 never lets a client set.

The first line on stdout is `{"s3": <port>}`; after it, everything goes to stderr, which the
fixture sends to a log file.
"""

from __future__ import annotations

import io
import json
import logging
import sys
import threading
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, unquote

from moto.core.models import DEFAULT_ACCOUNT_ID
from moto.moto_server.werkzeug_app import DomainDispatcherApplication, create_backend_app
from moto.s3.models import s3_backends
from werkzeug.serving import make_server

LOOPBACK = "127.0.0.1"
CONTROL = "/_stand_in/"

type Environ = dict[str, Any]
type StartResponse = Any


def operation_of(method: str, path: str, query: dict[str, list[str]], headers: dict[str, str]) -> str:
    """The S3 operation a path-style request is, by its method, its query and whether it names a key."""
    bucket, _, key = path.lstrip("/").partition("/")
    if not bucket:
        return "ListBuckets"
    if not key:
        bucket_level = {
            ("GET", "versions"): "ListObjectVersions",
            ("GET", "list-type"): "ListObjectsV2",
            ("GET", "versioning"): "GetBucketVersioning",
            ("PUT", "versioning"): "PutBucketVersioning",
            ("POST", "delete"): "DeleteObjects",
        }
        for (verb, flag), name in bucket_level.items():
            if method == verb and flag in query:
                return name
        return {"PUT": "CreateBucket", "HEAD": "HeadBucket", "GET": "ListObjects"}.get(method, method)
    if method == "PUT" and "x-amz-copy-source" in headers:
        return "CopyObject"
    if method == "PUT" and "uploadId" in query:
        return "UploadPart"
    if method == "POST" and "uploads" in query:
        return "CreateMultipartUpload"
    if method == "POST" and "uploadId" in query:
        return "CompleteMultipartUpload"
    return {"GET": "GetObject", "HEAD": "HeadObject", "PUT": "PutObject", "DELETE": "DeleteObject"}.get(
        method, method
    )


def signer_of(authorization: str) -> tuple[str | None, str | None]:
    """`(access key id, service)` from a SigV4 `Authorization` header; nothing else of it is kept."""
    marker = "Credential="
    if marker not in authorization:
        return None, None
    scope = authorization.split(marker, 1)[1].split(",", 1)[0].split("/")
    return scope[0], (scope[3] if len(scope) > 3 else None)


class StandIn:
    """moto's application, with a request record, fault rules and a backdating hook in front of it."""

    def __init__(self) -> None:
        self.moto = DomainDispatcherApplication(create_backend_app)
        self.lock = threading.Lock()
        self.served: list[dict[str, Any]] = []
        self.faults: list[dict[str, Any]] = []

    def __call__(self, environ: Environ, start_response: StartResponse) -> Any:
        path = unquote(environ.get("PATH_INFO", ""))
        if path.startswith(CONTROL):
            return self.control(environ, start_response, path[len(CONTROL) :])
        method = environ["REQUEST_METHOD"]
        query = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
        headers = {
            name[5:].replace("_", "-").lower(): value
            for name, value in environ.items()
            if name.startswith("HTTP_")
        }
        access_key, service = signer_of(headers.get("authorization", ""))
        action = self._form_action(environ) if method == "POST" else None
        bucket, _, key = path.lstrip("/").partition("/")
        record = {
            "service": service,
            "operation": action or operation_of(method, path, query, headers),
            "bucket": bucket or None,
            "key": key or None,
            "version_id": query.get("versionId", [None])[0],
            "access_key": access_key,
        }
        with self.lock:
            self.served.append(record)
            fault = self._fault_for(record)
        if fault is not None:
            return self._refuse(fault, method, start_response)
        return self.moto(environ, start_response)

    @staticmethod
    def _form_action(environ: Environ) -> str | None:
        """STS and IAM name their operation in a form body; read it and put the body back for moto."""
        if "application/x-www-form-urlencoded" not in environ.get("CONTENT_TYPE", ""):
            return None
        length = int(environ.get("CONTENT_LENGTH") or 0)
        body = environ["wsgi.input"].read(length)
        environ["wsgi.input"] = io.BytesIO(body)
        return parse_qs(body.decode("utf-8", "replace")).get("Action", [None])[0]

    def _fault_for(self, record: dict[str, Any]) -> dict[str, Any] | None:
        for fault in self.faults:
            if fault["operation"] != record["operation"]:
                continue
            key = record["key"] or ""
            if fault.get("key") is not None and key != fault["key"]:
                continue
            if fault.get("key_contains") is not None and fault["key_contains"] not in key:
                continue
            fault["matched"] = fault.get("matched", 0) + 1
            if fault["matched"] > fault.get("after", 0):
                return fault
        return None

    @staticmethod
    def _refuse(fault: dict[str, Any], method: str, start_response: StartResponse) -> list[bytes]:
        status = int(fault["status"])
        body = (
            b""
            if method == "HEAD"
            else (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                f"<Error><Code>{fault['code']}</Code><Message>{fault['message']}</Message>"
                "<RequestId>stand-in</RequestId></Error>"
            ).encode()
        )
        reason = {403: "Forbidden", 503: "Service Unavailable"}.get(status, "Error")
        start_response(
            f"{status} {reason}",
            [
                ("Content-Type", "application/xml"),
                ("Content-Length", str(len(body))),
                ("x-amz-request-id", "stand-in"),
            ],
        )
        return [body]

    def control(self, environ: Environ, start_response: StartResponse, route: str) -> list[bytes]:
        method = environ["REQUEST_METHOD"]
        length = int(environ.get("CONTENT_LENGTH") or 0)
        payload = json.loads(environ["wsgi.input"].read(length) or b"null")
        with self.lock:
            if (method, route) == ("GET", "requests"):
                answer: Any = list(self.served)
            elif (method, route) == ("PUT", "faults"):
                self.faults = [dict(rule) for rule in payload]
                answer = self.faults
            elif (method, route) == ("POST", "backdate"):
                answer = self._backdate(**payload)
            else:
                start_response("404 Not Found", [("Content-Type", "text/plain")])
                return [b"no such stand-in control"]
        body = json.dumps(answer).encode()
        start_response("200 OK", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
        return [body]

    @staticmethod
    def _backdate(bucket: str, key: str, version_id: str, last_modified: str) -> dict[str, str]:
        """Give one stored version an earlier `LastModified`, and keep moto's versions in that order.

        moto lists versions by the attribute and serves the last one stored, so the stored order is
        made to follow it, as it would on S3.
        """
        stored = s3_backends[DEFAULT_ACCOUNT_ID]["aws"].get_bucket(bucket).keys.getlist(key)
        (version,) = [one for one in stored if one.version_id == version_id]
        version.last_modified = datetime.fromisoformat(last_modified).astimezone(UTC).replace(tzinfo=None)
        stored.sort(key=lambda one: one.last_modified)
        return {"key": key, "version_id": version_id}


def main() -> None:
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    server = make_server(LOOPBACK, 0, StandIn(), threaded=True)
    sys.stdout.write(json.dumps({"s3": server.server_port}) + "\n")
    sys.stdout.flush()
    sys.stdout = sys.stderr
    server.serve_forever()


if __name__ == "__main__":
    main()

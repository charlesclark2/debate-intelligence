"""The OpenCaselist stand-in, as a check sees it: two https servers, the site they serve, what was asked.

The installed build is pointed at :attr:`OpenCaselistStandIn.api_base_url` with
`caselist.api_base_url`, which a dev installation accepts and prod refuses unless it is the
documented API (`v1-e01-t21`). It trusts the stand-in's certificate through `SSL_CERT_FILE`, which
httpx reads: the client's rule that every request is https, and that the token goes to the API host
alone, is untouched.

A check describes the site with :meth:`serve_json`, :meth:`serve_file` and :meth:`serve_api_file`,
which write the routes to the site file the server reads on every request, and reads what the build
asked for with :meth:`requests`. Responses are made from the invented fixtures in `tests/fixtures/`
and follow the shapes of the client's own recorded fixtures
(`packages/debate_core/tests/fixtures/opencaselist/`).

:func:`make_certificate` makes the run's certificate: a CA, and a leaf for 127.0.0.1 it signs.
Neither key leaves the temporary directory it is written to.
"""

from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from tests.smoke.stand_ins.opencaselist_server import route_key
from tests.smoke.stand_ins.process import StandInProcess

__all__ = ["CaselistRequest", "OpenCaselistStandIn", "StandInCertificate", "make_certificate"]

SERVER = Path(__file__).with_name("opencaselist_server.py")


@dataclass(frozen=True)
class StandInCertificate:
    """The run's CA, which the build trusts, and the leaf the stand-in serves with."""

    authority: Path
    certificate: Path
    key: Path


def make_certificate(directory: Path) -> StandInCertificate:
    """A CA and a leaf for 127.0.0.1 and localhost, valid for a day, written under `directory`."""
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    authority_key = ec.generate_private_key(ec.SECP256R1())
    authority_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "debate smoke stand-in CA")])
    authority = (
        x509.CertificateBuilder()
        .subject_name(authority_name)
        .issuer_name(authority_name)
        .public_key(authority_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )  # fmt: skip
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(authority_key.public_key()), critical=False)
        .sign(authority_key, hashes.SHA256())
    )
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")]))
        .issuer_name(authority_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1")), x509.DNSName("localhost")]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(authority_key.public_key()), critical=False
        )
        .sign(authority_key, hashes.SHA256())
    )
    paths = StandInCertificate(
        directory / "authority.pem", directory / "certificate.pem", directory / "key.pem"
    )
    paths.authority.write_bytes(authority.public_bytes(serialization.Encoding.PEM))
    paths.certificate.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    paths.key.write_bytes(
        leaf_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    paths.key.chmod(0o600)
    return paths


@dataclass(frozen=True)
class CaselistRequest:
    """One request a stand-in server answered. `authenticated` says whether the token cookie came."""

    server: str
    method: str
    path: str
    query: dict[str, str]
    authenticated: bool


class OpenCaselistStandIn:
    """A running API and file host, and the site file they serve from."""

    def __init__(
        self, process: StandInProcess, site: Path, log: Path, certificate: StandInCertificate
    ) -> None:
        self.process = process
        self.site = site
        self.log = log
        self.certificate = certificate
        api_host, api_port = process.address("api")
        files_host, files_port = process.address("files")
        self.api_base_url = f"https://{api_host}:{api_port}/v1"
        self.files_url = f"https://{files_host}:{files_port}"

    @classmethod
    def start(cls, directory: Path, certificate: StandInCertificate) -> OpenCaselistStandIn:
        directory.mkdir(parents=True, exist_ok=True)
        site, log = directory / "site.json", directory / "requests.jsonl"
        site.write_text(json.dumps({"api": {}, "files": {}}), encoding="utf-8")
        process = StandInProcess.start(
            SERVER,
            "--certificate", str(certificate.certificate),
            "--key", str(certificate.key),
            "--site", str(site),
            "--log", str(log),
            log=directory / "stand-in.log",
        )  # fmt: skip
        return cls(process, site, log, certificate)

    def stop(self) -> None:
        self.process.stop()

    @property
    def addresses(self) -> list[tuple[str, int]]:
        return list(self.process.addresses)

    def serve_json(
        self, route: str, body: Any, *, query: dict[str, str] | None = None, status: int = 200
    ) -> None:
        """Answer `GET /v1<route>` (with exactly `query`, when given) with `body` as JSON."""
        self._route("api", route_key(f"/v1{route}", query or {}), {"status": status, "json": body})

    def serve_file(self, name: str, content: Path) -> str:
        """Serve `content`'s bytes from the file host as `/<name>`, unauthenticated; return its URL.

        What an archive listing points at: the site's object store, which never sees the token.
        """
        self._route("files", f"/{name}", {"status": 200, "file": str(content)})
        return f"{self.files_url}/{name}"

    def serve_api_file(self, route: str, content: Path, *, query: dict[str, str]) -> None:
        """Serve `content`'s bytes from the API's own `GET /v1<route>` with `query`, authenticated.

        What OpenEv's `/download?path=...` is.
        """
        self._route("api", route_key(f"/v1{route}", query), {"status": 200, "file": str(content)})

    def requests(self) -> list[CaselistRequest]:
        """Every request the two servers answered, in order."""
        if not self.log.exists():
            return []
        return [
            CaselistRequest(**json.loads(line))
            for line in self.log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _route(self, server: str, key: str, response: dict[str, Any]) -> None:
        site = json.loads(self.site.read_text(encoding="utf-8"))
        site[server][key] = response
        written = self.site.with_suffix(".json.writing")
        written.write_text(json.dumps(site), encoding="utf-8")
        written.replace(self.site)

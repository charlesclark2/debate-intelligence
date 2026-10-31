"""The pilot app's composition root: the only module in debate_api that builds an adapter.

It reads :class:`~debate_api.configuration.PilotConfiguration` from the environment, reads the
client secret and the cookie keys from Parameter Store once (a cold start), refuses the
placeholder keys, and wires the Cognito, audit and parameter adapters from
`debate_core.integrations` into the two use cases. It also builds the search index holder over the
evidence bucket (`v1-e39-t06`), which fetches nothing until the first search: a cold start reads
only the two parameters. The holder re-reads the suppression list through the same bucket adapter,
and the access audit writes to the same audit stream as the account page (`v1-e39-t07`). The card
download (`v1-e39-t08`) builds files with the E33 writer and its parser, reading each source from the
evidence bucket through an `S3SnapshotStore` per `raw/` prefix (`raw/caselist/<slug>`, or a camp
file's `raw/openev/<year>`), on the same client; it writes nothing anywhere. The landscape pages
(`v1-e39-t17`) read `reports/landscape/` through an `S3EvidenceObjectStore` on the same client, held
by a :class:`~debate_core.application.tub.landscape_pages.LandscapeShelf` that renders each newest
bundle once with :func:`~debate_api.landscape_markdown.render_bundle`. Routes
ask `app.state.pilot` for the use cases and never import an adapter (the import contracts and
`scripts/check_thin_handlers.py` hold them to that).

uvicorn's app factory is here too, :func:`create_app_from_environment` (`v1-e39-t23`), so that
:mod:`debate_api.app` never imports this module: a test that builds the app with its own services
then reaches none of the adapters above.

The function's role allows exactly what is built here and nothing more (ADR-0019, The function's
role): `ssm:GetParameter` on the two parameters, `logs:CreateLogStream` and `logs:PutLogEvents` on
its audit group, `s3:GetObject` under `reports/tub/search/` for the index, which the holder
reads to a directory of its own in the function's ephemeral storage, `/tmp/tub-index`, and
`s3:GetObject` on `manifests/_suppression/suppression-list.jsonl` and on current objects under `raw/`,
for a download's sources, and `s3:ListBucket` limited to the prefix `reports/landscape/` with
`s3:GetObject` under it, for the landscape pages. The Cognito
calls need no IAM grant: the token-authorized ones send the student's access token through an
unsigned client, and the OAuth endpoints take the client secret.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from fastapi import FastAPI

from debate_api.app import create_app
from debate_api.app_logging import configure_app_logging
from debate_api.configuration import PilotConfiguration, parse_cookie_keys
from debate_api.landscape_markdown import render_bundle
from debate_api.state import PilotServices
from debate_core.application.card_download import CardDownloadService
from debate_core.application.evidence_search import EvidenceSearchService
from debate_core.application.ports.persistence import SnapshotStore
from debate_core.application.search_index_holder import SearchIndexHolder
from debate_core.application.tub.access_audit import AccessAuditService
from debate_core.application.tub.account_page import AccountPageService
from debate_core.application.tub.landscape_pages import LandscapeShelf
from debate_core.application.tub.sign_in import SignInService
from debate_core.integrations.cloudwatch_audit import CloudWatchAuditSink, build_logs_client
from debate_core.integrations.cognito import (
    CognitoIdTokenVerifier,
    CognitoOAuthClient,
    CognitoSelfService,
    PublishedKeySet,
    UrllibTransport,
    build_cognito_self_service_client,
    issuer_for,
)
from debate_core.integrations.docx_file_writer.base_template import load_base_template
from debate_core.integrations.docx_file_writer.writer import DocxEvidenceFileWriter
from debate_core.integrations.docx_parser.package import declared_document_bytes
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader
from debate_core.integrations.parameter_store import build_ssm_client, read_secure_parameter
from debate_core.integrations.s3 import (
    S3EvidenceObjectStore,
    S3SearchIndexSource,
    S3SnapshotStore,
    build_s3_client,
)

__all__ = ["INDEX_DIRECTORY_NAME", "build_pilot_services", "create_app_from_environment"]

INDEX_DIRECTORY_NAME = "tub-index"
"""The holder's own directory under the function's `/tmp`, which nothing else writes to."""


def _now() -> datetime:
    return datetime.now(UTC)


def create_app_from_environment() -> FastAPI:
    """The function's app, as uvicorn's `--factory` builds it: its services from this process's environment.

    Building them reads the client secret and the cookie keys from Parameter Store, and refuses to
    go on if the cookie keys are still Terraform's placeholder
    (:class:`~debate_api.configuration.CookieKeysNotSet`), so a misconfigured function never starts.
    It first sends the function's log lines to stderr, its app log (:mod:`debate_api.app_logging`).
    """
    configure_app_logging()
    return create_app(build_pilot_services(os.environ))


def build_pilot_services(environ: Mapping[str, str]) -> PilotServices:
    """The app's services for this function, from its environment and its two parameters."""
    configuration = PilotConfiguration.from_environment(environ)
    parameters = build_ssm_client(region=configuration.region)
    cookie_keys = parse_cookie_keys(read_secure_parameter(parameters, configuration.cookie_keys_parameter))
    client_secret = read_secure_parameter(parameters, configuration.client_secret_parameter)

    transport = UrllibTransport()
    issuer = issuer_for(configuration.region, configuration.user_pool_id)
    identity_provider = CognitoOAuthClient(
        login_origin=configuration.login_origin,
        public_origin=configuration.public_origin,
        client_id=configuration.client_id,
        client_secret=client_secret,
        id_tokens=CognitoIdTokenVerifier(
            issuer=issuer,
            client_id=configuration.client_id,
            key_set=PublishedKeySet(issuer=issuer, transport=transport),
            clock=_now,
        ),
        transport=transport,
    )
    self_service = CognitoSelfService(client=build_cognito_self_service_client(region=configuration.region))
    # One stream per execution environment, made the first time it writes: the role may create
    # streams in its own audit group, and streams never collide between environments.
    audit = CloudWatchAuditSink(
        client=build_logs_client(profile=None, region=configuration.region),
        log_group=configuration.audit_log_group,
        log_stream=f"tub-app-{_now():%Y-%m-%d}-{uuid.uuid4().hex}",
        create_stream=True,
    )
    s3 = build_s3_client(region=configuration.region)
    evidence = S3SearchIndexSource(bucket=configuration.evidence_bucket, client=s3)
    search_index = SearchIndexHolder(
        evidence,
        directory=Path(tempfile.gettempdir()) / INDEX_DIRECTORY_NAME,
        open_reader=_open_index,
        clock=_now,
        build_service=partial(
            EvidenceSearchService,
            count_cap=configuration.result_count_cap,
            passage_share_percent=configuration.passage_share_percent,
        ),
        suppression_list=evidence,
    )
    access_audit = AccessAuditService(audit=audit, clock=_now)
    parser = DebateDocxParser()
    base = load_base_template()
    source_stores: dict[str, SnapshotStore] = {}

    def source_store(prefix: str) -> SnapshotStore:
        if prefix not in source_stores:
            source_stores[prefix] = S3SnapshotStore(
                bucket=configuration.evidence_bucket, prefix=prefix, client=s3
            )
        return source_stores[prefix]

    return PilotServices(
        configuration=configuration,
        cookie_keys=cookie_keys,
        sign_in=SignInService(
            identity_provider=identity_provider, self_service=self_service, audit=audit, clock=_now
        ),
        account_page=AccountPageService(
            identity_provider=identity_provider,
            self_service=self_service,
            audit=audit,
            clock=_now,
            authenticator_issuer=configuration.authenticator_issuer,
        ),
        search_index=search_index,
        access_audit=access_audit,
        card_download=CardDownloadService(
            search_index=search_index,
            writer=lambda sources: DocxEvidenceFileWriter(snapshots=sources, parser=parser, base=base),
            source_stores=source_store,
            access_audit=access_audit,
            parser_version=parser.parser_version,
            profile_version=parser.profile_version,
            clock=_now,
            card_cap=configuration.download_card_cap,
            source_xml_bytes=configuration.download_source_xml_bytes,
            document_size=declared_document_bytes,
        ),
        landscape=LandscapeShelf(
            S3EvidenceObjectStore(bucket=configuration.evidence_bucket, client=s3),
            prepare=render_bundle,
            clock=_now,
        ),
        clock=_now,
    )


def _open_index(path: Path, index_id: str) -> SqliteSearchIndexReader:
    """One checked index file, opened read-only and immutable."""
    return SqliteSearchIndexReader(path, index_id=index_id)

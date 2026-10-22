"""The pilot app's composition root: the only module in debate_api that builds an adapter.

It reads :class:`~debate_api.configuration.PilotConfiguration` from the environment, reads the
client secret and the cookie keys from Parameter Store once (a cold start), refuses the
placeholder keys, and wires the Cognito, audit and parameter adapters from
`debate_core.integrations` into the two use cases. It also builds the search index holder over the
evidence bucket (`v1-e39-t06`), which fetches nothing until the first search: a cold start reads
only the two parameters. The holder re-reads the suppression list through the same bucket adapter,
and the access audit writes to the same audit stream as the account page (`v1-e39-t07`). Routes ask `app.state.pilot` for the use cases
and never import an adapter (the import contracts and `scripts/check_thin_handlers.py` hold them
to that).

The function's role allows exactly what is built here and nothing more (ADR-0019, The function's
role): `ssm:GetParameter` on the two parameters, `logs:CreateLogStream` and `logs:PutLogEvents` on
its audit group, `s3:GetObject` under `reports/tub/search/` for the index, which the holder
reads to a directory of its own in the function's ephemeral storage, `/tmp/tub-index`, and
`s3:GetObject` on `manifests/_suppression/suppression-list.jsonl`. The Cognito
calls need no IAM grant: the token-authorized ones send the student's access token through an
unsigned client, and the OAuth endpoints take the client secret.
"""

from __future__ import annotations

import tempfile
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from debate_api.configuration import PilotConfiguration, parse_cookie_keys
from debate_api.state import PilotServices
from debate_core.application.search_index_holder import SearchIndexHolder
from debate_core.application.tub.access_audit import AccessAuditService
from debate_core.application.tub.account_page import AccountPageService
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
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader
from debate_core.integrations.parameter_store import build_ssm_client, read_secure_parameter
from debate_core.integrations.s3 import S3SearchIndexSource

__all__ = ["INDEX_DIRECTORY_NAME", "build_pilot_services"]

INDEX_DIRECTORY_NAME = "tub-index"
"""The holder's own directory under the function's `/tmp`, which nothing else writes to."""


def _now() -> datetime:
    return datetime.now(UTC)


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
    evidence = S3SearchIndexSource(bucket=configuration.evidence_bucket, region=configuration.region)
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
        search_index=SearchIndexHolder(
            evidence,
            directory=Path(tempfile.gettempdir()) / INDEX_DIRECTORY_NAME,
            open_reader=_open_index,
            clock=_now,
            suppression_list=evidence,
        ),
        access_audit=AccessAuditService(audit=audit, clock=_now),
        clock=_now,
    )


def _open_index(path: Path, index_id: str) -> SqliteSearchIndexReader:
    """One checked index file, opened read-only and immutable."""
    return SqliteSearchIndexReader(path, index_id=index_id)

"""Every value the platform reads from outside its own code, in one place.

A data directory, an API key, a per-host crawl delay, which model a task class routes to: none of
these belong in a literal somewhere in the call stack, and none of them belong in a global that a
module reads at import time. They are loaded here, once, into a :class:`Settings` object that the
composition root hands to the services that need it (architecture proposal §6, §10, §11, §14).

This module is the **only** place in the platform that reads `os.environ` or a `.env` file. A
service that wants the crawl delay takes it as a constructor argument; it does not reach for the
environment, which is what keeps the same service usable from the CLI, the API, a worker and a
test without any of them agreeing on process-wide state.

## Where a value comes from

Five layers, highest priority first. Every layer is optional; a field that no layer sets keeps its
declared default.

| Layer | Source label | Set by |
|---|---|---|
| Explicit override | `cli` | `load_settings(overrides=...)` — a command-line flag |
| Process environment | `env:DEBATE_HTTP__MAX_RETRIES` | `DEBATE_`-prefixed variables, `__` to nest |
| `.env` file | `dotenv:.env` | the operator's own machine; never committed |
| Environment profile | `profile:config/profiles/dev.toml` | committed per-environment defaults |
| Built-in profile | `built-in:dev` | :data:`BUILTIN_PROFILES`, so dev/prod/test differ even with no files |
| Field default | `default` | the declarations below |

:meth:`Settings.field_sources` reports the label for every field, which is what
`debate-research config show` prints in its `Source` column. It is there because the first
question about surprising behaviour is "which of the six places did that value come from", and
answering it by reading code and guessing at shell state wastes an afternoon.

## Environments

`DEBATE_ENV` selects the profile and accepts exactly `dev`, `prod` and `test`
(`docs/process/branching-and-environments.md`). A local source checkout with `DEBATE_ENV` unset
resolves to `dev`: nothing a developer runs by accident should touch the production data
directory. `test` is for CI and unit tests — it enables no network provider, points `data_dir`
at a temporary directory, and sets the daily model budget to zero.

## Build channels (`v1-e01-t09-dev-prerelease-channel`)

An installed build knows which channel it came from, and with `DEBATE_ENV` unset that decides the
environment: a dev pre-release (`vX.Y.Z-dev.N`) runs as `dev`, a stable release as `prod`
(:func:`environment_for_build_channel`). An explicit `DEBATE_ENV`, or one in `.env`, still wins.
A source checkout is channel `local` and keeps the `dev` default above.

An installed build also carries the committed `config/` files inside its wheel, and
`load_settings(bundled_config_root=...)` reads its profiles and routing files from there rather
than from whichever checkout the working directory happens to be in. That is what makes a
scheduled job that runs from `$HOME` get the `[caselist]` gate and budget its build was tested
with. `DEBATE_PROFILE_DIR` still overrides both.

Each environment also names the evidence bucket it syncs to, in :class:`S3StorageSettings` under
`storage.s3` (`v1-e29-t05-evidence-sync-cli`). Those values are not invented here: they are the
environment root's Terraform outputs — `evidence_bucket_name`, `evidence_operator_profile_name`
and `aws_region` in `infrastructure/envs/<env>/outputs.tf` — written into the committed profile
files, which is possible only because the bucket suffix is itself a committed constant
(`docs/architecture/evidence-store-layout.md`). `test` names no bucket at all, so a test that
reaches for one gets a refusal rather than somebody's real store.

## Secrets

Anything sensitive is a :class:`~pydantic.SecretStr`, comes from the environment or `.env`, and is
never read from a committed profile file — `.toml` files under `config/profiles/` are in the
repository, so a secret written into one is a secret published. :meth:`Settings.redacted_dict` is
the only supported way to render settings for a human or a log, and it replaces every
`SecretStr` with :data:`SECRET_PLACEHOLDER` whether or not the caller remembered to.

## Failures

A bad value raises :class:`ConfigurationError`, which names the field. It derives from
:class:`~debate_core.application.errors.DomainError` so that the CLI's existing error handler
reports it the way it reports any other deterministic failure — a rendered message and exit code
`1` — rather than as an unhandled exception and exit `70`, which would tell a user that a typo in
their `DEBATE_ENV` is a bug in the program.
"""

from __future__ import annotations

import os
import re
import tempfile
import tomllib
from collections.abc import Callable, Iterator, Mapping
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, cast
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from debate_core.application.errors import DomainError
from debate_core.domain.caselist import CASELIST_SLUG_PATTERN, Event
from debate_core.domain.model_contracts import ModelProvider

__all__ = [
    "BUILTIN_PROFILES",
    "DEV_DAILY_BUDGET_CAP_USD",
    "EVIDENCE_BUCKET_SUFFIX",
    "ENVIRONMENT_VARIABLE",
    "ENV_NESTED_DELIMITER",
    "ENV_PREFIX",
    "PROFILE_DIRECTORY_VARIABLE",
    "PROFILE_SUBDIRECTORY",
    "SECRET_PLACEHOLDER",
    "FIRST_BACKFILE_SEASON_START",
    "MAX_CASELIST_BULK_DOWNLOADS_PER_DAY",
    "MAX_CASELIST_DOWNLOADS_PER_MINUTE",
    "OPENCASELIST_API_BASE_URL",
    "ArticleSettings",
    "CardFingerprintSettings",
    "CaselistTokenBackend",
    "ConfigurationError",
    "Environment",
    "HttpSettings",
    "CaselistSettings",
    "ModelSettings",
    "ParseSettings",
    "ProviderSettings",
    "S3StorageSettings",
    "SearchProviderName",
    "Settings",
    "StorageSettings",
    "RunStateMode",
    "SNS_TOPIC_ARN_PATTERN",
    "SyncNotifierKind",
    "environment_for_build_channel",
    "find_repository_root",
    "load_settings",
    "profile_path_for",
    "resolve_environment",
]

ENV_PREFIX: Final = "DEBATE_"
"""Prefix on every environment variable this module reads."""

ENV_NESTED_DELIMITER: Final = "__"
"""What separates a settings group from a field: `DEBATE_HTTP__REQUEST_TIMEOUT_SECONDS`."""

ENVIRONMENT_VARIABLE: Final = "DEBATE_ENV"
"""The variable that selects the environment profile."""

PROFILE_DIRECTORY_VARIABLE: Final = "DEBATE_PROFILE_DIR"
"""Overrides where profile files are looked for; needed by installed builds and by tests."""

PROFILE_SUBDIRECTORY: Final = Path("config") / "profiles"
"""Where profiles live inside a source checkout, relative to the repository root."""

SECRET_PLACEHOLDER: Final = "***"
"""What a secret renders as. The real value never leaves this module."""

OPENCASELIST_API_BASE_URL: Final = "https://api.opencaselist.com/v1"
"""The documented OpenCaselist API, and the only one a prod installation will call (`v1-e01-t21`)."""

LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "localhost", "::1"})
"""The host names an endpoint on this machine may be spelled with."""

DEV_DAILY_BUDGET_CAP_USD: Final = 2.0
"""The documented ceiling on the dev environment's daily model spend, in USD.

Dev is where untested prompts run, so its budget is small by policy
(`docs/process/branching-and-environments.md`, "Model spend"). The committed dev profile and the
built-in dev profile both stay at or under it, which `test_settings_environments.py` checks; an
operator can still set a lower value, or a higher one through `DEBATE_MODELS__BUDGET_USD_DAILY` on
their own machine, and `config show` names where it came from.
"""

MONTHLY_MODEL_BUDGET_CEILING_USD: Final = 50.0
"""The coach's ceiling on model spend, in USD a calendar month, across dev and prod (2026-10-27).

`models.budget_usd_monthly` holds a month to it, in America/Chicago (v1-e05-t15). Both bundled
profiles set exactly this until the promotion, because only one environment calls models today, and
prod's daily limit is it over thirty days, rounded down to $1.50. No committed profile sets a model
budget above it, which `test_settings_environments.py` checks. The AWS Budgets alarm
(v1-e05-t16) watches the account's real total, which no one machine's usage log can see.
"""

type SourceLabeller = Callable[[str], str]
"""A layer that labels itself per field, given the field's dotted path."""


class ConfigurationError(DomainError):
    """Configuration could not be loaded, or a value in it is not usable.

    Carries `field` (dotted, e.g. `"http.per_host_interval_seconds"`) and `source` when the
    failure is about one setting, so a caller can point at the line to fix instead of printing a
    validation dump. Both are `None` for a failure about the configuration as a whole, such as a
    profile file that is not valid TOML.
    """

    def __init__(self, message: str, *, field: str | None = None, source: str | None = None) -> None:
        self.field = field
        """Dotted path of the offending setting, when the failure is about one setting."""
        self.source = source
        """Where the offending value came from: a file path, an environment variable name."""
        super().__init__(message)


class Environment(StrEnum):
    """The environment a run belongs to: `docs/process/branching-and-environments.md`.

    There are exactly three and they are not interchangeable. `prod` is the team's real data,
    `dev` is the pre-release channel a tester runs on their own machine, and `test` is CI and the
    unit suite, which never reach the network.
    """

    DEV = "dev"
    PROD = "prod"
    TEST = "test"

    @classmethod
    def parse(cls, value: str, *, source: str) -> Environment:
        """Return the environment named by `value`, or raise naming what is allowed."""
        try:
            return cls(value.strip().lower())
        except ValueError:
            allowed = ", ".join(member.value for member in cls)
            raise ConfigurationError(
                f"{ENVIRONMENT_VARIABLE} must be one of {allowed}; got {value!r}",
                field="environment",
                source=source,
            ) from None


class SearchProviderName(StrEnum):
    """The discovery providers that can be switched on in configuration.

    A closed set rather than free strings, so `DEBATE_PROVIDERS__ENABLED='["openalexx"]'` fails at
    startup instead of silently searching nothing. The adapters themselves are E07; the registry
    that maps a name to an adapter is `v1-e07-t01-search-provider-contract`, and a provider added
    there is added here in the same change.
    """

    OPENALEX = "openalex"
    CROSSREF = "crossref"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    RSS = "rss"
    GOOGLE_NEWS = "google_news"
    GDELT = "gdelt"


class SettingsGroup(BaseModel):
    """Base for the nested groups: frozen, validated, and closed to unknown keys.

    `extra="forbid"` is what turns a misspelled key in a profile file or an environment variable
    into a startup failure that names it, which is acceptance criterion 1's "fail fast with a
    message naming the field".
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        validate_assignment=True,
        # `model_routing_file` and friends are ordinary names here, not Pydantic's reserved space.
        protected_namespaces=(),
    )


class S3StorageSettings(SettingsGroup):
    """The evidence bucket this environment syncs to, and the credential that reaches it.

    Read by `debate-research store` (v1-e29-t05) and by nothing else: the S3 adapters take a
    bucket, a region and a profile as constructor arguments and read no settings of their own
    (:mod:`debate_core.integrations.s3`). This group is where the composition root gets them.

    **Every value here comes from the environment root's Terraform outputs**, not from a name
    somebody thought of: `bucket` is `evidence_bucket_name`, `aws_profile` is
    `evidence_operator_profile_name`, `region` is `aws_region`
    (`infrastructure/envs/<env>/outputs.tf`). They are written into the committed profile files
    because the bucket suffix is a committed constant, so a runbook, a takedown and this CLI can
    name the bucket without reading Terraform state
    (`docs/architecture/evidence-store-layout.md`) — but the *source* of the name is the apply,
    and none of it is a literal anywhere in Python.

    Nothing here is a secret. A bucket name and an SSO profile name are not credentials: the
    credential is the SSO session `aws sso login --profile <aws_profile>` puts in the operator's
    own AWS config, which this platform never reads, stores or prints.

    The KMS key is deliberately absent. Each evidence bucket has the environment's
    customer-managed key as its default encryption (`v1-e29-t03`), so an upload that names no key
    is still encrypted with the right one — and the key's ARN contains the account id, which does
    not belong in a committed file.
    """

    bucket: str | None = Field(
        default=None,
        description=(
            "Evidence bucket for this environment, from the evidence_bucket_name Terraform "
            "output. None means this environment has no bucket configured and `store` commands "
            "refuse to run rather than guessing at one."
        ),
    )
    region: str = Field(
        default="us-east-1",
        description="Region the bucket is in. ADR-0010 pins every environment to us-east-1.",
    )
    aws_profile: str | None = Field(
        default=None,
        description=(
            "Profile in the operator's shared AWS config, from the "
            "evidence_operator_profile_name Terraform output (debate-dev-evidence / "
            "debate-prod-evidence). None uses botocore's standard credential chain, which is "
            "what a role on an instance or a task is."
        ),
    )
    multipart_threshold_mb: int = Field(
        default=64,
        ge=5,
        le=4096,
        description=(
            "Size above which a transfer is split into parts. Below S3's own 5 MiB minimum part "
            "size there is nothing to split, so that is the floor."
        ),
    )
    endpoint_url: str | None = Field(
        default=None,
        description=(
            "Where the evidence store's S3 and STS requests go instead of AWS: a stand-in on this "
            "machine's loopback address, such as the moto server the installed-build smoke checks "
            "run (v1-e01-t21). Accepted in the dev environment only; prod and test refuse it. None, "
            "everywhere by default, is AWS."
        ),
    )

    @property
    def multipart_threshold_bytes(self) -> int:
        """:attr:`multipart_threshold_mb` in the bytes the S3 adapters take."""
        return self.multipart_threshold_mb * 1024 * 1024

    @field_validator("aws_profile")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        """An empty value is no profile: botocore's credential chain, the task role in the cloud.

        The committed dev and prod profiles name the operator's SSO profile, and an environment
        variable can only override a value, never remove one. So the cloud run sets
        `DEBATE_STORAGE__S3__AWS_PROFILE=` to sign with its task role (ADR-0020 (5)); botocore
        itself would take an empty name for a profile called "" and refuse it.
        """
        if value is not None and not value.strip():
            return None
        return value

    @field_validator("endpoint_url")
    @classmethod
    def _on_this_machine(cls, value: str | None) -> str | None:
        """Loopback only, even in dev: a dev session's token travels with every request it signs."""
        if value is None:
            return None
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or parts.hostname not in LOOPBACK_HOSTS:
            raise ValueError(
                "must be an http:// or https:// URL on this machine's loopback address "
                f"({', '.join(sorted(LOOPBACK_HOSTS))}); every request carries the session's token"
            )
        return value.rstrip("/")


class StorageSettings(SettingsGroup):
    """Where this environment keeps its local data, and which bucket it syncs to.

    Only the root of the local store is configured. The layout inside it — the blob store, the
    SQLite file, exports — is `v1-e02-t03-local-repositories`' to define, and it derives its paths
    from `data_dir` rather than taking its own setting, so one environment is one directory and
    nothing escapes it.
    """

    data_dir: Path = Field(
        description="Root directory for this environment's evidence store, database and exports."
    )
    s3: S3StorageSettings = Field(
        default_factory=S3StorageSettings,
        description="The cloud evidence store for this environment, or the defaults when it has none.",
    )
    volume_warning_percent: int | None = Field(
        default=None,
        ge=1,
        le=99,
        description=(
            "Past this share of the data directory's volume used after any stage, `caselist pull` "
            "warns in its summary. The cloud run sets 70 for its fixed ephemeral volume (ADR-0020 "
            "(1) 2). Unset, the default, reads no volume: a laptop's disk is not the run's to judge."
        ),
    )

    @field_validator("data_dir")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        """Expand `~` and make the path absolute, so two spellings of one directory compare equal."""
        return Path(os.path.expandvars(str(value))).expanduser().absolute()


class HttpSettings(SettingsGroup):
    """How politely the platform retrieves a source.

    Consumed by `v1-e04-t02-http-fetcher`. The defaults are deliberately conservative: this is a
    high-school team's research tool making requests to publishers who owe it nothing, and a
    crawler that identifies itself and waits a second between requests to the same host is one
    that stays welcome. The platform never circumvents an access control (§14); these settings
    tune the rate of requests it is allowed to make, never whether it is allowed to make them.
    """

    user_agent_product: str = Field(
        default="debate-research",
        min_length=1,
        description="Product token in the User-Agent header.",
    )
    contact_url: str = Field(
        default="https://github.com/charlesclark2/debate-intelligence",
        min_length=1,
        description="Where a site owner can reach the operator; sent in every User-Agent.",
    )
    request_timeout_seconds: float = Field(
        default=30.0, gt=0, le=600, description="Deadline for one complete request."
    )
    connect_timeout_seconds: float = Field(
        default=10.0, gt=0, le=600, description="Deadline for establishing the connection."
    )
    per_host_interval_seconds: float = Field(
        default=1.0, ge=0, le=3600, description="Minimum wait between two requests to one host."
    )
    max_retries: int = Field(
        default=2, ge=0, le=10, description="Retries for an idempotent request that failed transiently."
    )
    backoff_base_seconds: float = Field(
        default=1.0,
        gt=0,
        le=60,
        description="First backoff wait when the server gives no Retry-After; doubles per retry, jittered.",
    )
    backoff_max_seconds: float = Field(
        default=30.0, gt=0, le=600, description="Ceiling on one backoff wait the fetcher chose itself."
    )
    max_retry_wait_seconds: float = Field(
        default=120.0,
        ge=0,
        le=3600,
        description=(
            "Longest Retry-After the fetcher will sit through. A longer one ends the fetch with the "
            "server's answer instead of being slept on."
        ),
    )
    max_response_bytes: int = Field(
        default=25 * 1024 * 1024,
        ge=1024,
        le=512 * 1024 * 1024,
        description="Largest body the fetcher reads; a larger one is abandoned, never truncated.",
    )
    max_redirects: int = Field(
        default=5, ge=0, le=20, description="Redirects one fetch may follow; each one is a new request."
    )

    @field_validator("contact_url")
    @classmethod
    def _must_be_http_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("must be an http:// or https:// URL a site owner can open")
        return value

    def user_agent(self, version: str) -> str:
        """The `User-Agent` header value, e.g. `debate-research/0.1.0 (+https://example.org/debate)`.

        Takes the version rather than looking it up, because reading installed package metadata is
        the delivery layer's business and this module stays free of it.
        """
        return f"{self.user_agent_product}/{version} (+{self.contact_url})"


class ProviderSettings(SettingsGroup):
    """Which discovery providers are on, and the credentials they need.

    Every credential is a `SecretStr` that comes from the environment or `.env`. None of them may
    be written into `config/profiles/*.toml`: those files are committed.
    """

    enabled: tuple[SearchProviderName, ...] = Field(
        default=(), description="Discovery providers this environment may call, in no order."
    )
    timeout_seconds: float = Field(
        default=10.0, gt=0, le=120, description="How long one discovery call may take before it is cancelled."
    )
    breaker_failure_threshold: int = Field(
        default=3, ge=1, le=100, description="Consecutive failures after which a provider is skipped."
    )
    breaker_cooldown_seconds: float = Field(
        default=60.0,
        gt=0,
        le=3600,
        description="How long a skipped provider waits before one probe call is let through.",
    )
    contact_email: SecretStr | None = Field(
        default=None,
        description=(
            "Address sent to Crossref for its polite pool. Redacted like a secret: it is not one, "
            "but it is a person's email address (§14). OpenAlex retired its polite pool in "
            "February 2026 and is not sent it."
        ),
    )
    openalex_api_key: SecretStr | None = Field(
        default=None,
        description=(
            "OpenAlex API key, free from openalex.org. Optional: without one OpenAlex allows about "
            "100 searches a day, with one about 1,000 (PM ruling 2026-10-21)."
        ),
    )
    semantic_scholar_api_key: SecretStr | None = Field(
        default=None, description="Semantic Scholar API key, if the account has one."
    )
    caselist_token: SecretStr | None = Field(
        default=None,
        description=(
            "OpenCaselist session cookie, obtained by `caselist auth login` "
            "(v1-e34-t01-caselist-api-client). Never committed and never logged."
        ),
    )


MAX_CASELIST_DOWNLOADS_PER_MINUTE: Final = 10
"""The OpenCaselist maintainer's rate limit: file downloads per minute (policy clause 12)."""

FIRST_BACKFILE_SEASON_START: Final = 2021
"""The first season data-use policy 1.17 keeps as a backfile, 2021-22, by the year it starts.

Seasons before it are not imported (Retention). A caselist slug ends in the two digits of the year
its season starts: `hspolicy21` is 2021-22."""

MAX_CASELIST_BULK_DOWNLOADS_PER_DAY: Final = 5
"""OpenCaselist's own ceiling on bulk archive downloads per user per day.

Found in the upstream source by `v1-e34-t01` (`weeklyLimiter`), separate from the per-minute limit
above. The scheduled sync budgets for it across the configured caselists (`v1-e34-t02`), and this
is a ceiling rather than a default: a setting above it would only be refused by the server.
"""


class CaselistTokenBackend(StrEnum):
    """Where the operator's caselist_token is kept between runs."""

    AUTO = "auto"
    """The OS keychain when one is usable, otherwise the file."""
    KEYRING = "keyring"
    """The OS keychain (the macOS login keychain on the operator's Mac), through `keyring`."""
    FILE = "file"
    """A 0600 file under a gitignored `secrets/` directory."""
    SECRETSMANAGER = "secretsmanager"
    """The environment's AWS Secrets Manager secret, `debate-<env>-caselist-token`, which the weekly
    cloud run reads (ADR-0020 (2)). Never chosen by `auto`."""


class SyncNotifierKind(StrEnum):
    """How an unattended `caselist pull` tells the operator it needs attention (v1-e34-t03)."""

    AUTO = "auto"
    """macOS Notification Centre on a Mac, nothing elsewhere. Never notifies in `test`."""
    MACOS = "macos"
    """Always `osascript` `display notification`."""
    NONE = "none"
    """Nothing: the run log and `caselist runs` only."""
    SNS = "sns"
    """The environment's alert topic, `debate-<env>-caselist-run-alerts`, which emails the coach
    (`v1-e40-t05`, ADR-0020 (6)): what the cloud run and the cloud login set. Needs
    `caselist.alert_topic_arn`. Never chosen by `auto`."""


SNS_TOPIC_ARN_PATTERN: Final = r"^arn:aws[a-z-]*:sns:[a-z0-9-]+:[0-9]{12}:[A-Za-z0-9_-]{1,256}$"
"""An SNS topic's ARN: partition, region, account and name. The region is the topic's, and the
`sns` notifier publishes there."""


class RunStateMode(StrEnum):
    """Where a caselist run's state is kept between runs (`v1-e40-t04`, ADR-0020 (3) and (4))."""

    LOCAL = "local"
    """In this machine's data directory, as every run before the cloud run kept it. The default."""
    BUCKET = "bucket"
    """In the evidence bucket: a run restores a working copy at its start, saves its state back,
    and every command that writes to the bucket takes the bucket's run lock first. Only the cloud
    run sets it until the cutover (`v1-e40-t06`)."""


class CaselistSettings(SettingsGroup):
    """What the caselist importers will read, and how large an archive they will open.

    Two ceilings, and they guard different things. `max_archive_bytes` is the size of the file on
    disk: a weekly HS LD archive is a few hundred megabytes, and something an order of magnitude
    larger is a wrong path rather than a big week. `max_unpacked_bytes` is the total the zip's own
    directory says its members come to, checked *before* anything is extracted, which is what
    stops a small archive that claims to unpack to a terabyte (v1-e30-t03 ac5).

    Both are refusals, not warnings. An import that has already written half a corpus before
    noticing the archive was wrong is worse than one that never started.
    """

    max_archive_bytes: int = Field(
        default=2 * 1024 * 1024 * 1024,
        gt=0,
        description=(
            "Largest archive file the importer will open, in bytes. The default is 2 GiB: several "
            "times the largest weekly open-source archive, and far below a mistyped path to a "
            "backup volume."
        ),
    )
    max_unpacked_bytes: int = Field(
        default=8 * 1024 * 1024 * 1024,
        gt=0,
        description=(
            "Largest total the members of an archive may claim to unpack to, in bytes, read from "
            "the zip's directory before any member is extracted."
        ),
    )
    # A complete archive (`<slug>-all-<date>.zip`, v1-e34-t04) is every file still attached to a
    # round, so it is at least the caselist's distinct files. Measured after the backfill
    # (docs/data/caselist-backfill-2026-09.md, dedupe table): hspf26's 3,906 distinct files are
    # 1,755,226,582 bytes after 13 weeks, already 82% of the 2 GiB weekly ceiling, and PDFs and
    # .docx files do not compress. At that rate a season of about 40 weeks is about 5.4 GB, so the
    # file ceiling is 8 GiB. The unpacked ceiling is twice that: documents that do not compress
    # unpack to about their zipped size, and the ceiling is there to stop an archive claiming far
    # more. The weekly ceilings are unchanged.
    max_full_archive_bytes: int = Field(
        default=8 * 1024 * 1024 * 1024,
        gt=0,
        description=(
            "Largest complete archive (`<slug>-all-<date>.zip`) the pull will download or open, in "
            "bytes. 8 GiB: a whole season of the largest caselist measured so far, with room. A "
            "weekly archive is still held to max_archive_bytes."
        ),
    )
    max_full_archive_unpacked_bytes: int = Field(
        default=16 * 1024 * 1024 * 1024,
        gt=0,
        description=(
            "Largest total a complete archive's members may claim to unpack to, in bytes, read from "
            "the zip's directory before any member is extracted."
        ),
    )

    # --- The OpenCaselist API client (v1-e34-t01-caselist-api-client) ---------------------------
    #
    # docs/policies/caselist-data-use.md governs every value below. The API is off until an
    # operator turns it on; the download rate is the maintainer's, not ours to raise; and the
    # token itself is never a setting in a committed file (see `providers.caselist_token`).

    api_enabled: bool = Field(
        default=False,
        description=(
            "Whether this installation may call the OpenCaselist API at all. Off by default: the "
            "data-use policy's E34 gate is a decision an operator makes, and an installation that "
            "has not made it refuses rather than reaching the network."
        ),
    )
    api_base_url: str = Field(
        default=OPENCASELIST_API_BASE_URL,
        min_length=1,
        description=(
            "Root of the documented OpenCaselist API. Never the opencaselist.com site. Another "
            "https URL is accepted in dev and test, for a stand-in; prod refuses any other value "
            "(v1-e01-t21)."
        ),
    )
    downloads_per_minute: int = Field(
        default=8,
        ge=1,
        description=(
            "File downloads (archives and OpenEv files together) allowed in any rolling 60 "
            "seconds. The maintainer's limit is 10 (policy clause 12); the default stays under it "
            "and anything above it is refused."
        ),
    )
    min_request_interval_seconds: float = Field(
        default=1.0,
        ge=0.5,
        le=600,
        description="Minimum wait between the start of any two requests to OpenCaselist.",
    )
    max_attempts: int = Field(
        default=4,
        ge=1,
        le=8,
        description="Attempts for a request answered 429, 502, 503 or 504, the first included.",
    )
    backoff_base_seconds: float = Field(
        default=2.0,
        gt=0,
        le=60,
        description="First backoff wait when the server gives no Retry-After; doubles per retry.",
    )
    max_retry_wait_seconds: float = Field(
        default=300.0,
        gt=0,
        le=3600,
        description=(
            "Longest single wait the client will sit through. A Retry-After longer than this is "
            "reported as a rate-limit failure immediately instead of being slept on."
        ),
    )
    token_backend: CaselistTokenBackend = Field(
        default=CaselistTokenBackend.AUTO,
        description=(
            "Where `caselist auth login` keeps the caselist_token: the OS keychain, a 0600 file, "
            "`auto` (the keychain when one is usable, otherwise the file), or `secretsmanager`, the "
            "environment's Secrets Manager secret the weekly cloud run reads."
        ),
    )
    secret_file: Path | None = Field(
        default=None,
        description=(
            "The token file for the `file` backend. Unset means `<storage.data_dir>/secrets/"
            "caselist_token`. Any path named `caselist_token`, or under a `secrets/` directory, is "
            "gitignored."
        ),
    )
    token_secret_id: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "The Secrets Manager secret the `secretsmanager` backend keeps the caselist_token in. "
            "Unset means `debate-<environment>-caselist-token`, the secret Terraform creates "
            "(ADR-0020 (2)). A name, not a credential."
        ),
    )
    password_secret_id: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "The Secrets Manager secret holding the Tabroom username and password, which "
            "`caselist auth set-password` writes and the scheduled login (`caselist auth renew`) "
            "reads. Unset means `debate-<environment>-caselist-tabroom-password`. A name, not a "
            "credential: the value is never in a setting."
        ),
    )
    secrets_region: str = Field(
        default="us-east-1",
        min_length=1,
        description="Region of the two caselist secrets. ADR-0010 pins everything to us-east-1.",
    )

    # --- The weekly scheduled sync (v1-e34-t02-scheduled-sync) ----------------------------------
    #
    # Which caselists the weekly pull covers, where its downloads land, and how many bulk downloads
    # it may spend in a day. No slug is a default: a caselist is a decision an operator records in
    # a profile or types on the command line, not something a release of this package ships.

    sync_caselists: tuple[str, ...] = Field(
        default=(),
        description=(
            "Caselist slugs `caselist pull` covers when no --caselist is given. Empty by default: "
            "which caselists this installation follows is the operator's decision, and a hardcoded "
            "slug in a committed file would make it ours. A list in a profile file; JSON in the "
            "environment, as every list setting is: "
            'DEBATE_CASELIST__SYNC_CASELISTS=["hsld26","hspolicy26"].'
        ),
    )
    backfile_caselists: tuple[str, ...] = Field(
        default=(),
        description=(
            "Caselist slugs kept as backfiles (data-use policy 1.17, Permitted uses 8): earlier "
            "seasons, from 2021-22 on, imported once from their complete archive by `caselist "
            "backfile-import`. `caselist pull` and the weekly run never pull one, `landscape report` "
            "never reads one, and the annual purge keeps them. Never one of sync_caselists. A list in "
            'a profile file; JSON in the environment: DEBATE_CASELIST__BACKFILE_CASELISTS=["hspolicy25"].'
        ),
    )
    inbox_dir: Path | None = Field(
        default=None,
        description=(
            "Where `caselist pull` puts what it downloads, and where it reads archives from. Unset "
            "means `<storage.data_dir>/inbox`."
        ),
    )
    bulk_downloads_per_day: int = Field(
        default=MAX_CASELIST_BULK_DOWNLOADS_PER_DAY,
        ge=1,
        description=(
            "Bulk archive downloads one run may spend in a day, budgeted across the configured "
            "caselists. OpenCaselist's own ceiling is 5; anything above it is refused."
        ),
    )
    openev_event: Event | None = Field(
        default=None,
        description=(
            "Which event to file an OpenEv camp file under when its own tags do not say. Unset "
            "means such a file is listed and left alone rather than filed under a guess."
        ),
    )
    openev_year: int | None = Field(
        default=None,
        ge=2000,
        le=9999,
        description="Topic year of the OpenEv release to pull. Unset means the API's current year.",
    )

    # --- The full-archive refresh (v1-e34-t04-full-archive-refresh) -----------------------------
    #
    # The weekly run also refreshes one caselist's complete archive when one is due, after its
    # weeklies and only from what they leave of the day's bulk downloads. No second schedule:
    # E34 gate 4 of the data-use policy allows the weekly run and nothing more often.

    full_archive_rotation: bool = Field(
        default=True,
        description=(
            "Whether the weekly run refreshes complete archives on a rotation: at most one per run, "
            "the caselist refreshed least recently first, only when the run's weeklies leave a bulk "
            "download over. Off, only `caselist pull --full-archive <slug>` fetches one."
        ),
    )
    full_archive_interval_days: int = Field(
        default=30,
        ge=7,
        le=366,
        description=(
            "A caselist's complete archive is due once the newest one this machine holds is more "
            "than this many days old, or when it holds none. At least seven: complete archives are "
            "regenerated weekly, and nothing here fetches more often than they are published."
        ),
    )

    # --- Parsing what a pull imported (v1-e34-t17-pull-parses-new-sources) ----------------------

    parse_imported_sources: bool = Field(
        default=True,
        description=(
            "Whether `caselist pull` parses the sources it imported, rebuilds the aggregates of the "
            "caselists they belong to and, where it publishes, publishes the parsed store too. On "
            "by default: launchd sets the weekly agent no time limit, and the stage's roughly 20 "
            "minutes (30 after a parser-version bump) is a small part of every bound a run does "
            "have; docs/runbooks/caselist-scheduled-sync.md gives the arithmetic. Off, the stage is "
            "skipped with this setting's name as the reason, and `caselist parse` does the same "
            "work by hand. DEBATE_CASELIST__PARSE_IMPORTED_SOURCES=false in the agent's plist turns "
            "it off for the schedule without a new build."
        ),
    )

    # --- The search pilot's weekly index (v1-e39-t09-weekly-index-refresh) ----------------------

    refresh_search_index: bool = Field(
        default=True,
        description=(
            "Whether `caselist pull` keeps the student search pilot's index current where the "
            "environment names a bucket: rebuilt when the parsed store changed, and published to "
            "this environment's bucket when current.json is behind it. On by default and in the "
            "dev and prod profiles, which is what the installed agent reads. Off, the stage is "
            "still in the run summary and `caselist runs`, skipped with this setting's name as the "
            "reason; `tub index build` and `tub index publish` do the same work by hand."
        ),
    )
    search_index_minimum_share_percent: int = Field(
        default=90,
        ge=0,
        le=100,
        description=(
            "The share of each store's documents in the published search index that a new index "
            "must keep, in percent, for `tub index publish` and the weekly run to publish it "
            "(v1-e39-t14). Below it, or at 0 documents for a store the current index holds, the "
            "publish is refused and current.json stays; `tub index publish --allow-shrink "
            '"<reason>"` publishes a real shrink by hand. An index built from a store whose '
            "aggregates hold no rows is refused whatever this says."
        ),
    )

    # --- Where a run keeps its state (v1-e40-t04, ADR-0020 (3) and (4)) -------------------------

    run_state: RunStateMode = Field(
        default=RunStateMode.LOCAL,
        description=(
            "Where `caselist pull` keeps its state between runs: `local`, this machine's data "
            "directory, or `bucket`, the evidence bucket, restored at a run's start and saved back, "
            "with every command that writes to the bucket holding its run lock "
            "(reports/sync/run-lock.json). The cloud run sets `bucket`; the Mac stays `local` until "
            "the cutover."
        ),
    )

    # --- Monitoring the weekly sync (v1-e34-t03-sync-monitoring) ------------------------------

    notifier: SyncNotifierKind = Field(
        default=SyncNotifierKind.AUTO,
        description=(
            "Where a failed or stuck `caselist pull` is announced: `macos` (Notification Centre), "
            "`sns` (the alert topic, which emails the coach; the cloud run and login), `none`, or "
            "`auto` (macOS on a Mac, never in the test environment)."
        ),
    )
    alert_topic_arn: str | None = Field(
        default=None,
        pattern=SNS_TOPIC_ARN_PATTERN,
        description=(
            "The SNS topic the `sns` notifier publishes to: debate-<environment>-caselist-run-alerts, "
            "which Terraform creates with the coach's email as its one subscription (ADR-0020 (6)). "
            "Required by `notifier = sns` and read by nothing else. An ARN, not a credential."
        ),
    )
    stale_after_days: int = Field(
        default=8,
        ge=1,
        le=366,
        description=(
            "A landscape report is stale when the newest snapshot of its caselist is more than "
            "this many days older than the report. Eight: one weekly archive, plus a day of grace."
        ),
    )

    @field_validator("bulk_downloads_per_day")
    @classmethod
    def _within_the_sites_daily_limit(cls, value: int) -> int:
        if value > MAX_CASELIST_BULK_DOWNLOADS_PER_DAY:
            raise ValueError(
                f"OpenCaselist allows {MAX_CASELIST_BULK_DOWNLOADS_PER_DAY} bulk downloads per user "
                f"per day (upstream `weeklyLimiter`, found by v1-e34-t01); {value} is above it"
            )
        return value

    @field_validator("sync_caselists", "backfile_caselists", mode="before")
    @classmethod
    def _one_slug_or_many(cls, value: object) -> object:
        """Accept a bare slug as well as a list, so `sync_caselists = "hsld26"` in a profile works.

        The environment still takes JSON: pydantic-settings decodes a list-valued variable before
        any validator here sees it, which is true of every list setting in this module.
        """
        return (value,) if isinstance(value, str) else value

    @field_validator("backfile_caselists")
    @classmethod
    def _backfiles_from_2021_22_on(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for slug in value:
            if not re.fullmatch(CASELIST_SLUG_PATTERN, slug):
                raise ValueError(f"{slug!r} is not a caselist slug")
            if 2000 + int(slug[-2:]) < FIRST_BACKFILE_SEASON_START:
                raise ValueError(
                    f"{slug} is of a season before 2021-22, which data-use policy 1.17 does not import"
                )
        return value

    def is_backfile(self, caselist: str) -> bool:
        """Whether `caselist` is kept as a backfile: what pull, the landscape and the purge each ask."""
        return caselist in self.backfile_caselists

    @field_validator("inbox_dir")
    @classmethod
    def _expand_inbox(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        return Path(os.path.expandvars(str(value))).expanduser().absolute()

    @field_validator("downloads_per_minute")
    @classmethod
    def _within_the_maintainers_limit(cls, value: int) -> int:
        if value > MAX_CASELIST_DOWNLOADS_PER_MINUTE:
            raise ValueError(
                f"the OpenCaselist maintainer's limit is {MAX_CASELIST_DOWNLOADS_PER_MINUTE} file "
                "downloads per minute (docs/policies/caselist-data-use.md, clause 12); "
                f"{value} is above it"
            )
        return value

    @field_validator("api_base_url")
    @classmethod
    def _must_be_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("must be an https:// URL; the caselist_token is never sent in clear")
        return value.rstrip("/")

    @field_validator("secret_file")
    @classmethod
    def _expand_secret_file(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        return Path(os.path.expandvars(str(value))).expanduser().absolute()

    @model_validator(mode="after")
    def _a_backfile_is_never_pulled(self) -> CaselistSettings:
        """A slug in both lists would be pulled weekly and classified: refused at startup (`v1-e34-t34`)."""
        both = sorted(set(self.sync_caselists) & set(self.backfile_caselists))
        if both:
            raise ValueError(
                f"caselist.backfile_caselists and caselist.sync_caselists both name {', '.join(both)}; "
                "a backfile is never pulled by the weekly run"
            )
        return self

    @model_validator(mode="after")
    def _sns_needs_its_topic(self) -> CaselistSettings:
        """`notifier = sns` with no topic would announce nothing, silently: refused at startup."""
        if self.notifier is SyncNotifierKind.SNS and self.alert_topic_arn is None:
            raise ValueError(
                "caselist.notifier = sns needs caselist.alert_topic_arn, the environment's alert "
                "topic (debate-<environment>-caselist-run-alerts)"
            )
        return self


class CardFingerprintSettings(SettingsGroup):
    """When two card bodies count as one card (`v1-e31-t04-card-fingerprints`).

    Only the confirmation thresholds are settings. Shingle size, the number of MinHash functions and
    the LSH banding are constants of :mod:`debate_core.evidence.near_duplicates`, because they decide
    which pairs are ever compared and belong with the code that is versioned alongside them.
    """

    near_duplicate_jaccard: float = Field(
        default=0.8,
        gt=0.0,
        le=1.0,
        description="A candidate pair is one card when its shingle Jaccard similarity reaches this.",
    )
    near_duplicate_containment: float = Field(
        default=0.9,
        gt=0.0,
        le=1.0,
        description=(
            "Or when this share of the shorter body's shingles is inside the longer one: what keeps a "
            "card cut a paragraph shorter in its cluster."
        ),
    )


class ParseSettings(SettingsGroup):
    """How `caselist parse` runs on the operator's machine (`v1-e31-t06-parse-pipeline`).

    Sized for a Mac that is doing other things while a corpus parses: by default one worker fewer
    than the machine has cores, and never more than `worker_cap`, so the parse never takes the whole
    machine. `DEBATE_PARSE__WORKERS=2` slows it down for a day when the laptop is needed.
    """

    workers: int | None = Field(
        default=None,
        ge=1,
        le=64,
        description=(
            "Parse processes to run at once. Unset: the machine's cores minus one, at most `worker_cap`."
        ),
    )
    worker_cap: int = Field(
        default=6,
        ge=1,
        le=64,
        description="The most processes an unset `workers` will choose, however many cores there are.",
    )
    per_file_timeout_seconds: float = Field(
        default=120.0,
        gt=0,
        description=(
            "A source still parsing after this long is stopped and recorded as TIMEOUT. A 300-page "
            "file parses in about a second, so this is for the pathological file, not the large one."
        ),
    )
    failure_rate_threshold: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description=(
            "`caselist parse` exits non-zero when more than this share of the sources it tried to read "
            "failed. Unsupported formats (PDF, legacy .doc) are an outcome, not a failure, and are "
            "counted in neither the failures nor the sources tried."
        ),
    )
    failure_rate_minimum_sources: int = Field(
        default=100,
        ge=1,
        description=(
            "The failure rate is judged only in a run that tried at least this many sources, "
            "unsupported formats not counted. In a smaller run the failures are reported and never "
            "fail it. 100, from the store the first full parse left "
            "(docs/runbooks/caselist-scheduled-sync.md, The parse stage): the most unreadable "
            "files one week has delivered is 5, all exports of one program, which is over 5% of "
            "any run under 100 sources and exactly 5%, so not above it, of one of 100; and 100 is "
            "the size of a camp release, the smallest run the rate has been read from. "
            "Raise it with the threshold if the threshold is lowered: at a threshold `t`, a run of "
            "fewer than `1/t` sources fails on one file."
        ),
    )

    def worker_count(self, cpu_count: int | None) -> int:
        """`workers` when set; otherwise `cpu_count` minus one, at least one and at most `worker_cap`."""
        if self.workers is not None:
            return self.workers
        return max(1, min(self.worker_cap, (cpu_count or 2) - 1))


class ModelSettings(SettingsGroup):
    """What the ModelRouter is allowed to do and which file tells it where to route.

    The routing file itself is validated by :mod:`debate_core.integrations.models.routing_policy`; this
    group only says which file to read, what the day may cost, and whether the router is a real
    provider or the offline fake.
    """

    provider: ModelProvider = Field(
        default=ModelProvider.BEDROCK,
        description=(
            "`fake` answers every call from committed fixtures and never reaches a model; `bedrock` "
            "routes through the routing file, and then whether a call is recorded, replayed or made "
            "live is the --model-mode option or DEBATE_MODEL_MODE, never a setting "
            "(debate_core.integrations.models.factory, v1-e05-t03-fake-replay-models)."
        ),
    )
    routing_file: Path = Field(description="YAML file mapping each model task class to a route.")
    budget_usd_daily: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Ceiling on model spend per local day, across every run on this machine, in USD; unset is "
            "no limit. Enforced by the BudgetGuard (debate_core.application.budget, v1-e05-t07) "
            "against the day's usage log; the dev and prod values are set by "
            "v1-e01-t09-dev-prerelease-channel. With a limit, a model with no price in "
            "config/model_pricing.yaml is refused rather than treated as free."
        ),
    )
    budget_usd_monthly: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Ceiling on model spend per calendar month in America/Chicago, across every run on this "
            "machine, in USD; unset is no limit. Enforced by the BudgetGuard as the daily limit is, "
            "against every record of the month in the usage log, each placed by its own timestamp "
            "(v1-e05-t15). With a limit, a model with no price in config/model_pricing.yaml is "
            "refused rather than treated as free."
        ),
    )
    budget_usd_per_run: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Ceiling on model spend by one run (one command), in USD; unset is no limit. A command's "
            "--max-cost option sets it for that command (v1-e05-t07)."
        ),
    )
    aws_profile: str | None = Field(
        default=None,
        description=(
            "Profile in the operator's shared AWS config that every Bedrock call is signed with, from "
            "the bedrock_profile_name Terraform output (debate-dev-bedrock / debate-prod-bedrock, "
            "v1-e05-t08). The Bedrock client is built from this and never from AWS_PROFILE. None uses "
            "botocore's credential chain with AWS_PROFILE ignored, which is what a role on an "
            "instance or a task is."
        ),
    )

    @field_validator("routing_file")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        return Path(os.path.expandvars(str(value))).expanduser()

    @field_validator("aws_profile")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        """An empty value is no profile, as it is for `storage.s3.aws_profile`: an environment
        variable can override the committed profile but never remove it, so a run with a role of its
        own sets `DEBATE_MODELS__AWS_PROFILE=`."""
        if value is not None and not value.strip():
            return None
        return value


class ArticleSettings(SettingsGroup):
    """How ArticleService retrieves, classifies and extracts a source (`v1-e04-t05-article-service`).

    Three kinds of value. `refetch_after_hours` is the re-fetch policy: a source retrieved more
    recently than that is answered from its stored snapshot without asking the publisher again,
    unless the caller asks for a refresh. The two `access_*` values are the access classifier's
    truncation heuristic (`debate_core.retrieval.access.AccessThresholds`, v1-e04-t03), which
    ArticleService builds from them. The `html_*` and `pdf_*` values are the extractors' fallback
    minimum and limits (`debate_core.integrations.html_extractor` and `pdf_extractor`, v1-e04-t04),
    which the composition root passes to them (v1-e04-t06). Every default is the value those tasks
    chose as their own default.
    """

    refetch_after_hours: float = Field(
        default=168.0,
        gt=0,
        le=24 * 365,
        description=(
            "A source whose last retrieval was readable and is younger than this is not fetched again; "
            "its stored snapshot is the answer. `--refresh` fetches it anyway."
        ),
    )
    access_minimum_characters: int = Field(
        default=500,
        ge=1,
        le=1_000_000,
        description="Fewer extracted characters than this is too little to be an article: ERROR.",
    )
    access_truncation_ratio: float = Field(
        default=0.5,
        gt=0,
        le=1,
        description=(
            "Fewer extracted words than this share of the length the page declares is a truncated "
            "page: PAYWALLED."
        ),
    )
    html_fallback_minimum_characters: int = Field(
        default=250,
        ge=1,
        le=1_000_000,
        description="When trafilatura extracts fewer characters than this, the readability fallback runs.",
    )
    html_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1024,
        le=512 * 1024 * 1024,
        description="An HTML document larger than this is refused before it is parsed (v1-e04-t06).",
    )
    pdf_max_bytes: int = Field(
        default=50 * 1024 * 1024,
        ge=1024,
        le=512 * 1024 * 1024,
        description="A PDF larger than this is refused before it is parsed.",
    )
    pdf_max_pages: int = Field(
        default=500,
        ge=1,
        le=100_000,
        description="A PDF with more pages than this is refused before any is read.",
    )
    pdf_max_stream_bytes: int = Field(
        default=20_000_000,
        ge=1024,
        le=512 * 1024 * 1024,
        description="A PDF stream that expands past this many bytes is refused: the PDF-bomb ceiling.",
    )

    @property
    def refetch_after(self) -> timedelta:
        """`refetch_after_hours` as a duration."""
        return timedelta(hours=self.refetch_after_hours)


class Settings(BaseSettings):
    """Everything the platform was configured with for this run.

    Built by :func:`load_settings`, never by calling this constructor directly: the constructor
    takes an already-merged mapping and has no idea where any of it came from, which is the point
    — layering and source tracking live in one function that can be tested on its own.
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_nested_delimiter=ENV_NESTED_DELIMITER,
        extra="forbid",
        frozen=True,
        validate_default=True,
        case_sensitive=False,
        protected_namespaces=(),
    )

    environment: Environment = Field(
        default=Environment.DEV, description="The environment profile this run resolved to."
    )
    allow_network: bool = Field(
        default=True,
        description=(
            "False forbids every outbound call: no search provider, no fetch, no model. The test "
            "profile sets it so that a test which forgets its fake fails loudly instead of "
            "quietly reaching the internet."
        ),
    )
    removal_profile: str | None = Field(
        default=None,
        description=(
            "The EvidenceRemoval SSO profile `caselist remove --execute` and `caselist unsuppress "
            "--execute` delete and append with (DEBATE_REMOVAL_PROFILE): debate-dev-evidence-removal "
            "or debate-prod-evidence-removal. Unset in every profile on purpose, so that deleting "
            "evidence takes a decision in the shell it runs in; the dry run never needs it "
            "(v1-e30-t07)."
        ),
    )
    storage: StorageSettings
    http: HttpSettings = Field(default_factory=HttpSettings)
    providers: ProviderSettings = Field(default_factory=ProviderSettings)
    models: ModelSettings
    caselist: CaselistSettings = Field(default_factory=CaselistSettings)
    fingerprints: CardFingerprintSettings = Field(default_factory=CardFingerprintSettings)
    parse: ParseSettings = Field(default_factory=ParseSettings)
    articles: ArticleSettings = Field(default_factory=ArticleSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Take values only from the constructor.

        :func:`load_settings` runs the environment, `.env` and profile layers itself so that it
        can record which one supplied each field. Leaving them enabled here as well would read the
        environment twice and would let a stray `DEBATE_*` variable into a `Settings` that a test
        built by hand.
        """
        return (init_settings,)

    _field_sources: dict[str, str] | None = PrivateAttr(default=None)
    """Filled in by :func:`load_settings`; `None` on a model a test constructed by hand."""

    @property
    def field_sources(self) -> Mapping[str, str]:
        """Where each setting came from, keyed by dotted path: `{"storage.data_dir": "profile:..."}`.

        Every field of every group is present. A field no layer supplied — and every field of a
        `Settings` built directly rather than through :func:`load_settings` — reads `default`.
        """
        if self._field_sources is not None:
            return dict(self._field_sources)
        return {path: "default" for path, _ in _walk_fields(self)}

    def attach_field_sources(self, sources: Mapping[str, str]) -> None:
        """Record where each value came from. Called once, by :func:`load_settings`.

        A mutator on a frozen model, and deliberately the only one: the settings themselves are
        immutable, while *where they came from* is bookkeeping the loader knows and the model
        cannot work out for itself. Fields no layer supplied are filled in as `default`.
        """
        self._field_sources = {path: sources.get(path, "default") for path, _ in _walk_fields(self)}

    def redacted_dict(self) -> dict[str, object]:
        """Every setting as a flat, JSON-ready mapping, with secrets replaced.

        The one supported way to render settings. A `SecretStr` becomes
        :data:`SECRET_PLACEHOLDER` and a `Path` becomes its string form; nothing else is
        transformed. Callers do not get to opt out, because the failure mode of an opt-in
        redaction is a token in a log file that is already on someone else's disk.
        """
        return dict(_flatten_for_display(self))


# ------------------------------------------------------------------------------------------------
# Built-in profiles
# ------------------------------------------------------------------------------------------------


def _temporary_data_dir() -> Path:
    """The data directory the `test` environment uses when nothing overrides it.

    A committed `config/profiles/test.toml` cannot name this machine's temporary directory, so the
    value comes from here rather than from the file. A test that wants isolation from other tests
    passes its own `tmp_path` as an override; what this guarantees is only that a forgotten
    override writes to a scratch directory and not to the developer's real evidence store.
    """
    return Path(tempfile.gettempdir()) / "debate-research-test"


EVIDENCE_BUCKET_SUFFIX: Final = "a7508de8"
"""Suffix that makes each evidence bucket name unique in S3's global namespace.

The same committed constant `infrastructure/envs/<env>/variables.tf` declares as
`evidence_bucket_suffix`, repeated here for the same stated reason it is committed there: so that
a runbook, a takedown and `debate-research store` can name the bucket without an operator first
running `terraform output` (`docs/architecture/evidence-store-layout.md`). It is not a secret and
not an account id — it is eight hex characters chosen once so two AWS accounts could not collide.

If the buckets are ever recreated under a new suffix, this constant, the two `variables.tf`
defaults and the layout document change together, and
`test_the_committed_profiles_name_the_buckets_terraform_builds` is what fails if they do not.
"""


def _evidence_bucket_for(environment: Environment) -> dict[str, Any]:
    """The evidence bucket coordinates for one environment, as Terraform builds them.

    Mirrors `module.evidence_store` in `infrastructure/envs/<env>/evidence_store.tf`:
    `${name_prefix}-${environment}-evidence-${bucket_suffix}` for the bucket, and
    `debate-<env>-evidence` for the everyday SSO profile (`operator_profile_name`). `test` is
    absent from this mapping on purpose and gets no bucket.
    """
    return {
        "bucket": f"debate-{environment.value}-evidence-{EVIDENCE_BUCKET_SUFFIX}",
        "region": "us-east-1",
        "aws_profile": f"debate-{environment.value}-evidence",
    }


def _builtin_profiles() -> dict[Environment, dict[str, Any]]:
    """The defaults each environment has before any profile file is read.

    These exist so that `dev`, `prod` and `test` differ in the values that matter — data
    directory, routing file, budget, whether the network may be used — on a machine where
    `config/profiles/` is not present at all: a wheel built without the bundled configuration
    that `v1-e01-t09-dev-prerelease-channel` stamps into published builds.
    """
    return {
        Environment.DEV: {
            "allow_network": True,
            "storage": {
                "data_dir": Path("~/.debate-research/dev"),
                "s3": _evidence_bucket_for(Environment.DEV),
            },
            "models": {
                "routing_file": Path("config/model_routing.dev.yaml"),
                "budget_usd_daily": DEV_DAILY_BUDGET_CAP_USD,
            },
        },
        Environment.PROD: {
            "allow_network": True,
            "storage": {
                "data_dir": Path("~/.debate-research/prod"),
                "s3": _evidence_bucket_for(Environment.PROD),
            },
            "models": {
                "routing_file": Path("config/model_routing.prod.yaml"),
                "budget_usd_daily": 20.0,
            },
        },
        Environment.TEST: {
            "allow_network": False,
            "storage": {"data_dir": _temporary_data_dir()},
            "providers": {"enabled": ()},
            "models": {
                "provider": ModelProvider.FAKE,
                "routing_file": Path("config/model_routing.example.yaml"),
                "budget_usd_daily": 0.0,
            },
        },
    }


BUILTIN_PROFILES: Final[Mapping[Environment, Mapping[str, Any]]] = _builtin_profiles()
"""Per-environment defaults, below the profile files and above the field defaults."""


# ------------------------------------------------------------------------------------------------
# Locating the configuration
# ------------------------------------------------------------------------------------------------


def find_repository_root(start: Path | None = None) -> Path | None:
    """The nearest ancestor of `start` (default: the working directory) that holds `config/profiles`.

    That directory is what makes a source checkout recognisable as one, and it is where the
    committed profiles are, so one walk answers both questions.
    """
    current = (start or Path.cwd()).absolute()
    for candidate in (current, *current.parents):
        if (candidate / PROFILE_SUBDIRECTORY).is_dir():
            return candidate
    return None


def _profile_directory(explicit: Path | None, config_root: Path | None = None) -> Path | None:
    """Where to look for profile files, or `None` when there is nowhere to look.

    In order: `explicit`, then `DEBATE_PROFILE_DIR`, then `config_root` (an installed build's
    bundled configuration), then the source checkout around the working directory. `None` is an
    ordinary outcome, not a failure: a build without profile files runs on
    :data:`BUILTIN_PROFILES`.
    """
    if explicit is not None:
        if not explicit.is_dir():
            raise ConfigurationError(f"profile directory does not exist: {explicit}", source=str(explicit))
        return explicit
    from_environment = os.environ.get(PROFILE_DIRECTORY_VARIABLE)
    if from_environment:
        directory = Path(from_environment).expanduser()
        if not directory.is_dir():
            raise ConfigurationError(
                f"{PROFILE_DIRECTORY_VARIABLE} does not name a directory: {directory}",
                source=PROFILE_DIRECTORY_VARIABLE,
            )
        return directory
    root = config_root if config_root is not None else find_repository_root()
    return root / PROFILE_SUBDIRECTORY if root is not None else None


def profile_path_for(
    environment: Environment, directory: Path | None = None, *, config_root: Path | None = None
) -> Path | None:
    """The profile file for `environment`, or `None` if there is none to read.

    `config_root` is a directory laid out like a checkout (`config/profiles/<env>.toml`) to use
    in place of the checkout around the working directory; see :func:`load_settings`.
    """
    resolved = _profile_directory(directory, config_root)
    if resolved is None:
        return None
    candidate = resolved / f"{environment.value}.toml"
    return candidate if candidate.is_file() else None


def environment_for_build_channel(channel: str | None) -> Environment | None:
    """The environment an installed build of `channel` runs as when `DEBATE_ENV` is unset.

    `dev` (a `vX.Y.Z-dev.N` pre-release) runs as dev and `stable` (a `vX.Y.Z` release) as prod.
    Anything else — `local` for a source checkout, `None` when the caller does not know — has no
    opinion, and the ordinary default applies.
    """
    return _ENVIRONMENT_OF_BUILD_CHANNEL.get((channel or "").strip().lower())


_ENVIRONMENT_OF_BUILD_CHANNEL: Final[Mapping[str, Environment]] = {
    "dev": Environment.DEV,
    "stable": Environment.PROD,
}


def resolve_environment(
    explicit: str | Environment | None = None,
    *,
    env_file: Path | None = None,
    build_channel: str | None = None,
) -> tuple[Environment, str]:
    """Decide which environment this run is, and say where that decision came from.

    Returned as a pair because the answer has to be reportable: `config show` prints the source of
    `environment` like the source of any other setting, and "you are writing to the prod data
    directory because of a variable exported in your shell profile" is the kind of thing a person
    needs told rather than left to deduce.

    `build_channel` is the channel of the installed build doing the asking. It is consulted only
    when nothing else names an environment, and is reported as `build-channel:<channel>`.
    """
    if explicit is not None:
        value = explicit.value if isinstance(explicit, Environment) else explicit
        return Environment.parse(value, source="cli"), "cli"
    from_environment = os.environ.get(ENVIRONMENT_VARIABLE)
    if from_environment:
        return Environment.parse(from_environment, source=ENVIRONMENT_VARIABLE), f"env:{ENVIRONMENT_VARIABLE}"
    from_dotenv_file, dotenv_path = _environment_from_dotenv(env_file)
    if from_dotenv_file is not None:
        return Environment.parse(from_dotenv_file, source=str(dotenv_path)), f"dotenv:{dotenv_path}"
    from_channel = environment_for_build_channel(build_channel)
    if from_channel is not None:
        return from_channel, f"build-channel:{(build_channel or '').strip().lower()}"
    # A local checkout is a developer's machine, and a developer who has said nothing has not
    # asked to touch production.
    return Environment.DEV, "default"


def _environment_from_dotenv(env_file: Path | None) -> tuple[str | None, Path | None]:
    """`DEBATE_ENV` as set in the `.env` file, if there is one and it sets it."""
    path = env_file if env_file is not None else _default_dotenv_path()
    if path is None or not path.is_file():
        return None, None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip().upper() == ENVIRONMENT_VARIABLE:
            return value.strip().strip("\"'"), path
    return None, path


def _default_dotenv_path() -> Path | None:
    """`.env` beside the repository root, or in the working directory outside a checkout."""
    root = find_repository_root()
    candidate = (root or Path.cwd()) / ".env"
    return candidate if candidate.is_file() else None


# ------------------------------------------------------------------------------------------------
# Loading
# ------------------------------------------------------------------------------------------------


def load_settings(
    *,
    overrides: Mapping[str, Any] | None = None,
    environment: str | Environment | None = None,
    profile_dir: Path | None = None,
    env_file: Path | None = None,
    build_channel: str | None = None,
    bundled_config_root: Path | None = None,
) -> Settings:
    """Load the settings for this run, applying every layer in order.

    `overrides` is the highest layer and is how a command-line flag wins over everything else; it
    is nested the way the model is, e.g. `{"storage": {"data_dir": tmp_path}}`. `environment`
    overrides `DEBATE_ENV` the same way. `profile_dir` and `env_file` exist so a test can point
    the loader at its own fixtures instead of at whatever the machine happens to have.

    `build_channel` and `bundled_config_root` are what an installed build passes
    (`debate_cli.build_info`): the channel it was published on, which picks the environment when
    nothing else does, and the directory its wheel carries the committed `config/` in. With a
    bundled root, profiles and relative routing files are read from it instead of from a checkout
    around the working directory; `profile_dir` and `DEBATE_PROFILE_DIR` still win.

    Raises :class:`ConfigurationError` if any layer is unreadable or any value is invalid.
    """
    resolved_environment, environment_source = resolve_environment(
        environment, env_file=env_file, build_channel=build_channel
    )
    dotenv_path = env_file if env_file is not None else _default_dotenv_path()
    repository_root = find_repository_root()
    config_root = bundled_config_root if bundled_config_root is not None else repository_root
    profile_file = profile_path_for(resolved_environment, profile_dir, config_root=config_root)

    layers: list[tuple[str | SourceLabeller, Mapping[str, Any]]] = [
        # The environment was resolved once, above, and that decision is final: a stray
        # DEBATE_ENVIRONMENT must not be able to set the field to something other than the
        # profile that was actually loaded.
        (environment_source, {"environment": resolved_environment}),
        ("cli", dict(overrides or {})),
        (_environment_variable_for, _environment_layer()),
        (f"dotenv:{_readable_path(dotenv_path, repository_root)}", _dotenv_layer(dotenv_path)),
        (f"profile:{_readable_path(profile_file, repository_root)}", _profile_layer(profile_file)),
        (f"built-in:{resolved_environment.value}", dict(BUILTIN_PROFILES[resolved_environment])),
    ]

    merged: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for label, values in layers:
        _merge_into(merged, values)
        _record_sources(sources, values, label)
    _anchor_relative_paths(merged, config_root if config_root is not None else _source_checkout())

    try:
        settings = Settings(**merged)
    except ValidationError as error:
        raise _configuration_error(error, sources) from error

    _refuse_stand_in_endpoints_outside_dev(settings, sources)
    settings.attach_field_sources(sources)
    return settings


def _refuse_stand_in_endpoints_outside_dev(settings: Settings, sources: Mapping[str, str]) -> None:
    """Refuse an endpoint override in an environment that must reach the real services (`v1-e01-t21`).

    The installed-build smoke checks point a dev installation at stand-ins on this machine with
    `storage.s3.endpoint_url` and `caselist.api_base_url`. Neither may redirect prod: a prod
    installation reaches AWS and the documented OpenCaselist API, whatever its environment holds.
    `test` has no bucket and no use for a stand-in, so it refuses the evidence store's too. Checked
    after the model is built, because which environment a value is for is a fact about the whole.
    """
    environment = settings.environment
    if settings.storage.s3.endpoint_url is not None and environment is not Environment.DEV:
        raise _refused_setting(
            "storage.s3.endpoint_url",
            sources,
            f"accepted only in the dev environment, never in {environment.value}",
            "It points the evidence store at a stand-in, which only a smoke check on a dev installation runs",
        )
    if environment is Environment.PROD and settings.caselist.api_base_url != OPENCASELIST_API_BASE_URL:
        raise _refused_setting(
            "caselist.api_base_url",
            sources,
            f"prod reaches OpenCaselist at {OPENCASELIST_API_BASE_URL} and nowhere else",
            "Any other value is an endpoint override, which only a smoke check on a dev installation "
            "has a use for",
        )


def _refused_setting(field: str, sources: Mapping[str, str], refusal: str, reason: str) -> ConfigurationError:
    """A setting this environment refuses, named both ways: its dotted path and its variable."""
    origin = sources.get(field, "default")
    variable = f"{ENV_PREFIX}{field.upper().replace('.', ENV_NESTED_DELIMITER)}"
    return ConfigurationError(
        f"invalid configuration: {field} (from {origin}): {refusal} ({variable}). {reason}",
        field=field,
        source=sources.get(field),
    )


def _source_checkout() -> Path | None:
    """The checkout this module was imported from, when it runs from source rather than a wheel."""
    return find_repository_root(Path(__file__).resolve().parent)


def _anchor_relative_paths(merged: dict[str, Any], config_root: Path | None) -> None:
    """Make a relative `models.routing_file` mean "relative to the configuration", not to the shell.

    `config/model_routing.dev.yaml` in a profile file is written relative to the checkout it is
    committed in, so it has to keep meaning that from whatever directory the command was run in.
    `config_root` is that checkout, or the configuration an installed build carries in its wheel,
    which is laid out the same way. A source checkout's code run from outside any checkout, as
    the smoke tier and the launchd installer run it, passes the checkout it was imported from
    (`v1-e05-t03-fake-replay-models`, where the CLI started validating the routing file at
    startup). With none of these, the value is left alone and is resolved against the working
    directory.
    """
    if config_root is None:
        return
    group = merged.get("models")
    if not isinstance(group, dict):
        return
    models = cast(dict[str, Any], group)
    routing_file = models.get("routing_file")
    if routing_file is None:
        return
    candidate = Path(os.path.expandvars(str(routing_file))).expanduser()
    if not candidate.is_absolute():
        models["routing_file"] = config_root / candidate


def _environment_layer() -> dict[str, Any]:
    """`DEBATE_*` variables from the process environment, nested to match the model."""
    source = EnvSettingsSource(Settings)
    try:
        return dict(source())
    except Exception as error:  # pydantic-settings raises its own SettingsError type here
        raise ConfigurationError(
            f"could not read {ENV_PREFIX}* environment variables: {error}", source="environment"
        ) from error


def _dotenv_layer(path: Path | None) -> dict[str, Any]:
    """`DEBATE_*` assignments from the `.env` file, if there is one."""
    if path is None or not path.is_file():
        return {}
    source = DotEnvSettingsSource(Settings, env_file=path)
    try:
        # DotEnvSettingsSource layers the process environment on top of the file's own entries;
        # the environment is already its own, higher layer here, so only the file's keys are kept.
        from_file = _dotenv_keys(path)
        return {key: value for key, value in dict(source()).items() if key in from_file}
    except ConfigurationError:
        raise
    except Exception as error:
        raise ConfigurationError(f"could not read {path}: {error}", source=str(path)) from error


def _dotenv_keys(path: Path) -> set[str]:
    """Top-level settings names the `.env` file assigns, e.g. `{"storage", "providers"}`."""
    prefix = ENV_PREFIX.lower()
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name = line.partition("=")[0].strip().lower()
        if name.startswith(prefix):
            names.add(name[len(prefix) :].split(ENV_NESTED_DELIMITER, 1)[0])
    return names


def _profile_layer(path: Path | None) -> dict[str, Any]:
    """The environment profile's TOML, or an empty layer when there is no file."""
    if path is None:
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationError(f"{path} is not valid TOML: {error}", source=str(path)) from error
    except OSError as error:
        raise ConfigurationError(f"could not read {path}: {error}", source=str(path)) from error


def _merge_into(target: dict[str, Any], values: Mapping[str, Any]) -> None:
    """Merge `values` under `target`: what is already there was set by a higher layer and wins."""
    for key, value in values.items():
        existing = target.get(key)
        if isinstance(existing, dict) and isinstance(value, Mapping):
            _merge_into(cast(dict[str, Any], existing), cast(Mapping[str, Any], value))
        elif key not in target:
            target[key] = dict(cast(Mapping[str, Any], value)) if isinstance(value, Mapping) else value


def _record_sources(sources: dict[str, str], values: Mapping[str, Any], label: str | SourceLabeller) -> None:
    """Note `label` as the source of every leaf in `values` that no higher layer already supplied.

    A layer whose label depends on the field — the process environment, where the useful answer is
    the variable's own name — passes a callable instead of a string.
    """
    for path, _ in _walk_leaves(values):
        sources.setdefault(path, label(path) if callable(label) else label)


def _readable_path(path: Path | None, repository_root: Path | None) -> str:
    """A path as a source label: repository-relative inside a checkout, absolute outside one.

    `profile:config/profiles/dev.toml` is the spelling a reader can act on; the absolute path of
    the same file in a worktree is forty characters of noise before the part that matters.
    """
    if path is None:
        return "none"
    if repository_root is not None:
        try:
            return str(path.relative_to(repository_root))
        except ValueError:
            pass
    return str(path)


def _environment_variable_for(path: str) -> str:
    """The label for a value the environment supplied: `env:DEBATE_HTTP__MAX_RETRIES`.

    Reconstructed from the dotted path rather than remembered, because it is exactly the variable
    a reader would have to unset or change, spelled the way they would have to spell it.
    """
    return f"env:{ENV_PREFIX}{path.upper().replace('.', ENV_NESTED_DELIMITER)}"


def _walk_leaves(values: Mapping[str, Any], prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Every scalar in a nested mapping, as `("http.max_retries", 2)` pairs."""
    for key, value in values.items():
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            yield from _walk_leaves(cast(Mapping[str, Any], value), f"{path}.")
        else:
            yield path, value


def _configuration_error(error: ValidationError, sources: Mapping[str, str]) -> ConfigurationError:
    """Turn Pydantic's report into one that names the field and where its value came from."""
    problems: list[str] = []
    first_field: str | None = None
    for detail in error.errors():
        field = ".".join(str(part) for part in detail["loc"])
        first_field = first_field or field
        origin = sources.get(field, "default")
        problems.append(f"{field} (from {origin}): {detail['msg']}")
    joined = "; ".join(problems)
    return ConfigurationError(
        f"invalid configuration: {joined}",
        field=first_field,
        source=sources.get(first_field or "", None),
    )


def _walk_fields(model: BaseModel, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Every settings field as a `("providers.caselist_token", value)` pair, groups expanded."""
    for name in type(model).model_fields:
        value = getattr(model, name)
        path = f"{prefix}{name}"
        if isinstance(value, BaseModel):
            yield from _walk_fields(value, f"{path}.")
        else:
            yield path, value


def _flatten_for_display(model: BaseModel, prefix: str = "") -> Iterator[tuple[str, object]]:
    """Flatten a settings model to JSON-ready scalars, replacing every secret."""
    for path, value in _walk_fields(model, prefix):
        yield path, _displayable(value)


def _displayable(value: Any) -> object:
    """One value as `--json` and a Rich table can both carry it."""
    if isinstance(value, SecretStr):
        return SECRET_PLACEHOLDER
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple | list | set):
        return [_displayable(item) for item in cast("tuple[Any, ...] | list[Any] | set[Any]", value)]
    return value

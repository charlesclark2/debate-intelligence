"""The composition root: the only place in the CLI where a service is built.

A command parses its arguments, asks the container for the service it needs, and renders what
comes back. It never constructs an adapter, never reads settings and never reaches for a global,
because the moment a command does any of those the CLI stops being replaceable by the API and the
workers, which wire the same services differently (architecture proposal §6, and
`docs/architecture/ports-and-adapters.md` for the injection pattern the services themselves use).

The first service is wired: :meth:`ServiceContainer.evidence_sync`, which `debate-research store`
runs (`v1-e29-t05-evidence-sync-cli`). The rest of V1's services and their adapters arrive in
E02–E08 and slot in the same way.

## Adding a service

Give the container a typed property that builds it through :meth:`ServiceContainer.singleton`,
add its name to :data:`SERVICE_NAMES`, and construct it from `self.settings` and the adapters that
task owns::

    @property
    def verification(self) -> VerificationService:
        return self.singleton("verification", self._build_verification)

    def _build_verification(self) -> VerificationService:
        return VerificationService(
            snapshots=FilesystemSnapshotStore(self.settings.evidence_dir),
            cards=SqliteCardRepository(self.settings.database_path),
            clock=SystemClock(),
        )

The property is the seam a test replaces: a CLI test builds a `ServiceContainer`, sets the
service it wants to fake, and runs the command against it — no monkeypatching of module globals,
because there are none.

## Settings

`settings` is loaded by a callable handed in at construction rather than by this module, and
:func:`debate_cli.app.root_callback` hands it
:func:`~debate_core.application.settings.load_settings`. The indirection is what lets a test build
a container around settings it made up, and it is why loading is lazy: the callable is not run
until a command actually asks for `settings`, so `--help` and `--version` read no files.

## Why the AWS adapters are imported inside the factory

`debate_core.integrations.s3` is imported where it is used rather than at the top of this module,
and the reason is not style: boto3 is an *optional* dependency of `debate-core`, under the `aws`
extra, so a V1 installation running against a local evidence directory does not have it. A
module-level import here would make `debate-research --help` fail on a machine that has no AWS SDK
and no use for one. Imported inside the factory, the missing dependency arrives only when someone
runs `store`, and it arrives as the `uv sync --extra aws` message that package raises.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, cast

from debate_core.application.evidence_sync import (
    EvidenceSyncService,
    SyncJournal,
    SyncKeyspace,
)
from debate_core.application.settings import ConfigurationError, Environment, Settings
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore

__all__ = [
    "SERVICE_NAMES",
    "EvidenceStoreNotConfigured",
    "ServiceContainer",
    "Settings",
    "SettingsNotConfigured",
]

SERVICE_NAMES: Final[tuple[str, ...]] = ("evidence_sync",)
"""Names of the services this container can build, for `debate-research doctor` to report."""


class EvidenceStoreNotConfigured(ConfigurationError):
    """This environment names no evidence bucket, so there is nothing for `store` to talk to.

    What `DEBATE_ENV=test` gets, and what any environment whose profile has no `storage.s3.bucket`
    gets. A :class:`~debate_core.application.settings.ConfigurationError`, so the root group
    reports it as the deterministic failure it is rather than as a bug.
    """

    def __init__(self, environment: Environment) -> None:
        super().__init__(
            f"the {environment.value} environment names no evidence bucket, so `store` has nothing "
            "to sync with; set DEBATE_ENV to dev or prod, or set storage.s3.bucket for this "
            "environment (config/profiles/<env>.toml)",
            field="storage.s3.bucket",
            source=f"profile:{environment.value}",
        )


class SettingsNotConfigured(RuntimeError):
    """Raised when a service needs settings and the container was built without a loader."""

    def __init__(self) -> None:
        super().__init__(
            "this ServiceContainer was built without a settings loader; pass "
            "settings_loader=load_settings, as debate_cli.app.root_callback does"
        )


class ServiceContainer:
    """Builds and caches the application services the CLI's commands use.

    One container is built per run and reaches commands on the
    :class:`~debate_cli.context.CliContext`. Construction is cheap and does nothing: a service —
    and the settings read, database connection or HTTP client behind it — is built the first time
    a command actually asks for it, so `debate-research --help` and `--version` stay instant.
    """

    def __init__(self, *, settings_loader: Callable[[], Settings] | None = None) -> None:
        self._settings_loader = settings_loader
        self._instances: dict[str, object] = {}

    @property
    def settings_configured(self) -> bool:
        """True when a settings loader was supplied (it may not have been called yet)."""
        return self._settings_loader is not None

    @property
    def settings(self) -> Settings:
        """The settings for this run, loaded once on first use.

        Raises :class:`SettingsNotConfigured` when the container was built without a loader,
        which only happens in a test that does not need settings; every real run has one.
        """
        if self._settings_loader is None:
            raise SettingsNotConfigured
        return self.singleton("settings", self._settings_loader)

    def singleton[ServiceT](self, name: str, factory: Callable[[], ServiceT]) -> ServiceT:
        """Return the instance registered under `name`, building it with `factory` once.

        Services are per-run singletons because they are meant to be: two copies of a repository
        would mean two connections and two caches within one command.
        """
        instance = self._instances.get(name)
        if instance is None:
            instance = factory()
            self._instances[name] = instance
        return cast(ServiceT, instance)

    def override(self, name: str, instance: object) -> None:
        """Register `instance` under `name`, so a test can supply a fake before a command runs."""
        self._instances[name] = instance

    def evidence_sync(self, *, blob_prefix: str | None = None) -> EvidenceSyncService:
        """Build the sync between this environment's local evidence store and its bucket.

        A method rather than a property because `blob_prefix` is a decision of the run, not of the
        environment: a content-addressed key carries no record of which archive it belongs to, so
        the corpus prefix (`raw/caselist/hsld26`, `raw/openev/2026`) comes from the command line
        and the service refuses to move blobs without one
        (:class:`~debate_core.application.evidence_sync.UnsyncableKeyspace`). It is still cached
        per run, keyed by that prefix, so two calls in one command share one S3 client.

        Raises :class:`EvidenceStoreNotConfigured` when this environment names no bucket.
        """
        return self.singleton(
            f"evidence_sync:{blob_prefix or ''}", lambda: self._build_evidence_sync(blob_prefix)
        )

    def _build_evidence_sync(self, blob_prefix: str | None) -> EvidenceSyncService:
        # Imported here, not at module scope: boto3 is an optional dependency and `--help` must
        # work without it. See this module's docstring.
        from debate_core.integrations.s3 import S3EvidenceObjectStore, build_s3_client

        settings = self.settings
        storage = settings.storage
        if not storage.s3.bucket:
            raise EvidenceStoreNotConfigured(settings.environment)

        # One client for both keyspaces: one set of credentials, one connection pool, and one
        # profile name in any `aws sso login` hint the adapters raise.
        client = build_s3_client(region=storage.s3.region, profile=storage.s3.aws_profile)

        def bucket_store() -> S3EvidenceObjectStore:
            return S3EvidenceObjectStore(
                bucket=str(storage.s3.bucket),
                client=client,
                profile=storage.s3.aws_profile,
                multipart_threshold_bytes=storage.s3.multipart_threshold_bytes,
            )

        named_objects = FsEvidenceObjectStore(storage.data_dir)
        blobs = FsEvidenceObjectStore(storage.data_dir, subdirectory=BLOB_DIRECTORY.parent)
        return EvidenceSyncService(
            keyspaces=(
                SyncKeyspace(
                    name="objects",
                    local=named_objects,
                    remote=bucket_store(),
                    local_path_for=named_objects.path_for,
                ),
                SyncKeyspace(
                    name="blobs",
                    local=blobs,
                    remote=bucket_store(),
                    remote_prefix=blob_prefix or "",
                    content_addressed=True,
                    local_path_for=blobs.path_for,
                ),
            ),
            journal=SyncJournal.open(
                storage.data_dir,
                environment=settings.environment.value,
                remote=str(storage.s3.bucket),
            ),
            remote_name=str(storage.s3.bucket),
        )

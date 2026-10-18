"""The composition root: the only place in the CLI where a service is built.

A command parses its arguments, asks the container for the service it needs, and renders what
comes back. It never constructs an adapter, never reads settings and never reaches for a global,
because the moment a command does any of those the CLI stops being replaceable by the API and the
workers, which wire the same services differently (architecture proposal §6, and
`docs/architecture/ports-and-adapters.md` for the injection pattern the services themselves use).

The wired services include :meth:`ServiceContainer.evidence_sync`, which `debate-research store`
runs (`v1-e29-t05-evidence-sync-cli`); :meth:`ServiceContainer.caselist_import`, which
`debate-research caselist import` runs (`v1-e30-t03-archive-importer`);
:meth:`ServiceContainer.openev_import`, which `debate-research caselist import-openev` runs
(`v1-e30-t04-openev-importer`); and
:meth:`ServiceContainer.caselist_token_store` and :meth:`ServiceContainer.opencaselist_client`,
which `debate-research caselist auth` runs (`v1-e34-t01-caselist-api-client`);
and :meth:`ServiceContainer.verify_manifest`, which `debate-research verify` runs
(`v1-e03-t06-verify-command`); and :meth:`ServiceContainer.caselist_sync`, which
`debate-research caselist pull` and the weekly launchd agent run (`v1-e34-t02-scheduled-sync`), recorded by
:meth:`ServiceContainer.caselist_sync_monitor` and read back by
:meth:`ServiceContainer.caselist_sync_history` (`v1-e34-t03-sync-monitoring`); and
:meth:`ServiceContainer.caselist_parse` and :meth:`ServiceContainer.parsed_publisher`, which
`debate-research caselist parse` runs (`v1-e31-t06-parse-pipeline`). The import
commands also read archives and place manifests through it (:meth:`ServiceContainer.read_archive`,
:meth:`ServiceContainer.archive_digest`, :meth:`ServiceContainer.evidence_object_path`), so no
command imports an adapter (`v1-e01-t13-composition-root-cleanup`). The rest of V1's services and
their adapters arrive in E02–E08 and slot in the same way.

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

The root callback wraps its loader in :func:`validating_routing`, so the run's settings arrive with
their model-routing file already loaded and validated. A bad `config/model_routing.*.yaml` stops
every command that reads settings when it first asks for them, before it has done anything, with the
:class:`~debate_core.application.ports.model_router.RoutingConfigError` naming the offending key
(`v1-e05-t03-fake-replay-models` ac6). Plain `doctor`, `--help` and `--version` read no settings and
so no routing file, which the installer and `validate-dev` depend on.

## Which copy of the suppression list a service reads

Every service that can store or publish a caselist source is built with the removal suppression
list (`v1-e30-t07`), and none of them has a default to fall back on. Which *copies* it reads follows
one rule: everything the command can reach without being given anything new to reach. The importers
run offline and read this environment's local copy (:meth:`ServiceContainer.local_suppression_list`);
publish, status, sync and the weekly pull already hold the bucket and read the union of the local
copy and `manifests/_suppression/suppression-list.jsonl` (:meth:`ServiceContainer.suppression_list`).

## The takedown credential

:meth:`ServiceContainer.caselist_removal` is the one service built with two AWS credentials: the
everyday evidence profile for everything a dry run does, and — only when `--execute` asks for it,
through a factory the service calls itself — the `EvidenceRemoval` profile named by
`DEBATE_REMOVAL_PROFILE` (:attr:`~debate_core.application.settings.Settings.removal_profile`). A dry
run therefore never builds a takedown client, and an execution with the variable unset stops with
:class:`~debate_core.application.caselist.removal_service.TakedownNotConfigured` before anything is
read with it, let alone deleted. So does one whose variable names a profile the AWS config does not
define: the adapter raises :class:`~debate_core.application.errors.StoreProfileNotConfigured` naming
the variable (`v1-e29-t07`), and the service reports it as its own preflight failure
(`v1-e29-t08`).

The takedown access also carries a
:class:`~debate_core.application.ports.caller_identity.CallerIdentity`, built from the same
profile, which the preflight asks first: a profile that is not signed in as this environment's
takedown role is refused before it lists or writes (`v1-e29-t08`).

## Checking the profiles ahead of a run

:meth:`ServiceContainer.evidence_profile_check` asks the same question of every profile these
settings name, the everyday one and the takedown one when its variable is set, through the same
port and the same adapter (:meth:`ServiceContainer.caller_identity_for`): is it defined, and
which permission set is it signed in as. `debate-research doctor --evidence-profiles` runs it
(`v1-e34-t22`), so that a setting naming a profile this machine does not have is found by a
person, before the weekly pull finds it.

## Why the AWS adapters are imported inside the factory

`debate_core.integrations.s3` is imported where it is used rather than at the top of this module,
and the reason is not style: boto3 is an *optional* dependency of `debate-core`, under the `aws`
extra, and `debate-research --help` should not depend on it. `debate-cli` itself requires the
extras its wiring needs (`aws`, `docx`, `opencaselist`, v1-e01-t17), so an installed build has
them. If one is missing anyway, the missing dependency arrives only when a command reaches the
factory, and the root error handler reports it with the fix for that kind of installation:
reinstall at a fixed tag for an installed build, `uv sync` for a checkout
(:func:`debate_cli.installation.incomplete_installation_failure`).

## The post-install check reads this module

`python -m debate_cli.installation`, which `scripts/install_channel.sh` runs after every channel
install, imports every `debate_core.integrations` module this file imports, and finds them by
reading this file's import statements. Wire an adapter with an ordinary `import` or `from … import`
statement, here or inside a factory, and it is checked from that day on. A dynamic import, or an
integration's module name in a string, makes the check refuse rather than skip it.
"""

from __future__ import annotations

import functools
import os
import sys
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from debate_cli.exit_codes import codes_exit_as_a_retrieval_failure
from debate_core.application.caselist.evidence_listing import (
    LocalEvidence,
    digests_in_earlier_manifests,
    held_back_digests,
)
from debate_core.application.caselist.import_service import CaselistImportService, EarlierManifestDigests
from debate_core.application.caselist.inbox_purge import CaselistInbox
from debate_core.application.caselist.later_manifests import LaterManifests
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.parse_workers import ProcessPoolParseRunner
from debate_core.application.caselist.parsed_publish import ParsedStorePublisher
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import RemovalPlanner
from debate_core.application.caselist.removal_service import (
    CaselistRemovalService,
    TakedownAccess,
    TakedownNotConfigured,
)
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist.suppression import (
    REMOVAL_LOG_KEY,
    SUPPRESSION_LIST_KEY,
    LocalFallbackSuppressionList,
    ObjectStoreAppendOnlyRecord,
    RecordedRemovalLog,
    RecordedSuppressionList,
)
from debate_core.application.caselist.version_retention import VersionDirectoryRetention
from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.application.caselist_parse import CaselistParseService
from debate_core.application.caselist_pull_parse import PullParseStage
from debate_core.application.caselist_sync import CaselistSyncService, FullArchiveRotation
from debate_core.application.evidence_profiles import ConfiguredProfile, EvidenceProfileCheck
from debate_core.application.evidence_sync import (
    EvidenceSyncService,
    SyncJournal,
    SyncKeyspace,
)
from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.application.ports.archive import ArchiveEntry
from debate_core.application.ports.caller_identity import CallerIdentity
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey
from debate_core.application.ports.notifier import Notifier, NullNotifier
from debate_core.application.ports.suppression import SuppressionList
from debate_core.application.settings import ConfigurationError, Environment, Settings, SyncNotifierKind
from debate_core.application.snapshot_service import SnapshotService
from debate_core.application.sync_runs import (
    SYNC_RUN_LOG_FILENAME,
    SyncRunHistory,
    SyncRunLog,
    SyncRunMonitor,
)
from debate_core.application.verify_manifest import VerifyManifest
from debate_core.domain import new_id
from debate_core.domain.caselist import Event
from debate_core.integrations.local import (
    BLOB_DIRECTORY,
    FsEvidenceObjectStore,
    FsSnapshotStore,
    SqliteArticleRepository,
    SqliteDatabase,
    archive_reader,
)
from debate_core.integrations.local.fs_version_store import FsEvidenceVersionStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.suppression_list import (
    local_removal_log_file,
    local_suppression_list_file,
)
from debate_core.integrations.local.version_directories import LocalVersionDirectories
from debate_core.integrations.models.routing_policy import RoutingPolicy

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only; see the factories
    from mypy_boto3_s3.client import S3Client

    from debate_core.integrations.opencaselist import CaselistTokenStore, OpenCaselistClient

__all__ = [
    "DEFAULT_INBOX_DIRECTORY",
    "SERVICE_NAMES",
    "EvidenceStoreNotConfigured",
    "ServiceContainer",
    "Settings",
    "SettingsNotConfigured",
    "validating_routing",
]

SERVICE_NAMES: Final[tuple[str, ...]] = (
    "caselist_import",
    "caselist_parse",
    "caselist_publish",
    "caselist_removal",
    "caselist_status",
    "caselist_sync",
    "caselist_sync_history",
    "caselist_sync_monitor",
    "caselist_token_store",
    "evidence_profile_check",
    "evidence_sync",
    "openev_import",
    "opencaselist_client",
    "verify_manifest",
)
"""Names of the services this container can build, for `debate-research doctor` to report."""

DEFAULT_INBOX_DIRECTORY: Final = "inbox"
"""Where `caselist pull` puts its downloads when `caselist.inbox_dir` is unset: `<data_dir>/inbox`.

Inside the data directory so that one environment is one directory, exactly as the blob store and
the SQLite file are (`debate_core.integrations.local`): a dev pull can never drop an archive where
a prod import would read it.
"""


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


def validating_routing(settings_loader: Callable[[], Settings]) -> Callable[[], Settings]:
    """`settings_loader`, refusing settings whose model-routing file does not load.

    The loader it returns raises
    :class:`~debate_core.application.ports.model_router.RoutingConfigError`, naming the file and the
    offending key, for a routing file that is missing, unreadable or invalid. The policy is not
    kept: whatever builds a model router loads it again, and a routing file is small.
    """

    def load() -> Settings:
        settings = settings_loader()
        RoutingPolicy.from_settings(settings)
        return settings

    return load


class SettingsNotConfigured(RuntimeError):
    """Raised when a service needs settings and the container was built without a loader."""

    def __init__(self) -> None:
        super().__init__(
            "this ServiceContainer was built without a settings loader; pass "
            "settings_loader=load_settings, as debate_cli.app.root_callback does"
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


class _PortClock:
    """:meth:`ServiceContainer.clock` as the :class:`~debate_core.application.ports.providers.Clock` port."""

    def __init__(self, now: Callable[[], datetime]) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now()


class _PortIdGenerator:
    """Fresh ULIDs, as the :class:`~debate_core.application.ports.providers.IdGenerator` port."""

    def new_id(self) -> str:
        return new_id()


PARSED_DIRECTORY: Final = Path("parsed")
"""Where E31's parse pipeline keeps parsed cards in the data directory (`v1-e31-t06`)."""

_EVERYDAY_PROFILE_SETTING: Final = "storage.s3.aws_profile"
_REMOVAL_PROFILE_SETTING: Final = "DEBATE_REMOVAL_PROFILE"
"""The two settings an AWS profile's name comes from, as an operator would look for them.

Passed to the S3 adapters beside the profile itself, because a profile the AWS config does not
define is reported by the setting to correct, never by the config's path, and only this module
knows which setting a name came from (`v1-e29-t07`).
"""


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

    def clock(self) -> Callable[[], datetime]:
        """Now, in UTC: the one clock `caselist pull` and its run log read.

        The run's timestamps and its rolling 24-hour download window (`v1-e34-t06`) come from it,
        so they cannot disagree, and a CLI test pins them both by overriding `"clock"`.
        """
        return self.singleton("clock", lambda: _utc_now)

    @property
    def database(self) -> SqliteDatabase:
        """This environment's SQLite file, opened and migrated once per run.

        A property on the container rather than a per-service construction, because every local
        repository shares one connection — that is what makes the pragmas, the migration run and
        the transaction boundary singular (see `debate_core.integrations.local.sqlite_db`).
        """
        return self.singleton("database", lambda: SqliteDatabase.open(self.settings.storage.data_dir))

    def read_archive(self, source: Path) -> Iterator[ArchiveEntry]:
        """Read a caselist archive (a `.zip` or a directory) within this installation's size ceilings.

        The local archive reader, bound to `caselist.max_archive_bytes` and
        `caselist.max_unpacked_bytes`: what `caselist import`, `caselist import-openev` and the
        weekly pull all read an archive with.
        """
        caselist = self.settings.caselist
        return archive_reader.read_archive(
            source,
            max_archive_bytes=caselist.max_archive_bytes,
            max_unpacked_bytes=caselist.max_unpacked_bytes,
        )

    def read_full_archive(self, source: Path) -> Iterator[ArchiveEntry]:
        """Read a complete archive (`<slug>-all-<date>.zip`) within its own, larger ceilings (`v1-e34-t04`).

        `caselist.max_full_archive_bytes` and `caselist.max_full_archive_unpacked_bytes`; a weekly
        is still read by :meth:`read_archive`, under the weekly ceilings.
        """
        caselist = self.settings.caselist
        return archive_reader.read_archive(
            source,
            max_archive_bytes=caselist.max_full_archive_bytes,
            max_unpacked_bytes=caselist.max_full_archive_unpacked_bytes,
        )

    def caselist_inbox(self) -> CaselistInbox:
        """The directory `caselist pull` downloads into, as a removal purges it (`v1-e30-t09`).

        The same directory the pull is built with, so the removal cannot purge one inbox while the
        pull reads another; zips are listed and rewritten under the reader's own ceilings.
        """
        settings = self.settings
        caselist = settings.caselist
        return CaselistInbox(
            directory=self._inbox_directory(),
            state_dir=settings.storage.data_dir,
            archives=archive_reader.ZipArchiveRewriter(
                max_archive_bytes=caselist.max_archive_bytes,
                max_unpacked_bytes=caselist.max_unpacked_bytes,
            ),
            full_archives=archive_reader.ZipArchiveRewriter(
                max_archive_bytes=caselist.max_full_archive_bytes,
                max_unpacked_bytes=caselist.max_full_archive_unpacked_bytes,
            ),
        )

    def _inbox_directory(self) -> Path:
        settings = self.settings
        return settings.caselist.inbox_dir or settings.storage.data_dir / DEFAULT_INBOX_DIRECTORY

    def archive_digest(self, source: Path) -> str:
        """The SHA-256 an import records for the archive itself, by the same reader's rules."""
        return archive_reader.archive_digest(source)

    def openev_upstream_paths(self) -> dict[int, str]:
        """What this machine's OpenEv delivery record knows of each id's upstream path, as digests.

        `caselist reimport-openev-metadata` writes it onto release rows imported before they carried
        it (`v1-e30-t14`). The record is the pull's, in the data directory it keeps its state in.
        """
        return self.caselist_inbox().deliveries.upstream_paths()

    def evidence_object_path(self, key: ObjectKey) -> Path:
        """The file this machine's evidence store keeps the named object `key` at: a manifest."""
        return FsEvidenceObjectStore(self.settings.storage.data_dir).path_for(key)

    def caselist_card_stats(self) -> CaselistCardStatsService:
        """Build the card statistics over this machine's recorded disclosures (`v1-e31-t04`).

        Reads only: the local caselist repository for disclosures, and the fingerprint thresholds
        from `settings.fingerprints`.
        """
        return self.singleton(
            "caselist_card_stats",
            lambda: CaselistCardStatsService(
                SqliteCaselistRepository(self.database), self.settings.fingerprints.thresholds()
            ),
        )

    def caselist_parse(self, *, with_bucket: bool) -> CaselistParseService:
        """Build the incremental parse pipeline over this machine's store (`v1-e31-t06`).

        `with_bucket` is whether this run publishes. A run that does reads the suppression list's
        local and bucket copies as one, as every bucket-holding command does; a run that does not is
        offline, like `caselist import`, and reads this machine's copy. The pool is sized by the
        `parse` settings group, for a laptop that is doing other things.
        """
        name = "caselist_parse_publishing" if with_bucket else "caselist_parse"
        return self.singleton(
            name,
            lambda: self._build_caselist_parse(
                self.suppression_list() if with_bucket else self.local_suppression_list()
            ),
        )

    def _build_caselist_parse(self, suppression: SuppressionList) -> CaselistParseService:
        # Imported here, not at module scope: lxml is loaded only by a command that parses.
        from debate_core.integrations.docx_parser import DebateDocxParser

        settings = self.settings
        parse = settings.parse
        return CaselistParseService(
            local=self._local_evidence(),
            store=LocalParsedStore(settings.storage.data_dir),
            parser=DebateDocxParser(),
            runner=ProcessPoolParseRunner(
                workers=parse.worker_count(os.cpu_count()),
                timeout_seconds=parse.per_file_timeout_seconds,
            ),
            suppression=suppression,
            place_cards=self.caselist_card_stats().place,
            failure_rate_threshold=parse.failure_rate_threshold,
            failure_rate_minimum_sources=parse.failure_rate_minimum_sources,
        )

    def parsed_publisher(self) -> ParsedStorePublisher:
        """Build the copy of the parsed card store to this environment's bucket (`v1-e31-t06`).

        Raises :class:`EvidenceStoreNotConfigured` when this environment names no bucket.
        """
        return self.singleton("parsed_publisher", self._build_parsed_publisher)

    def _build_parsed_publisher(self) -> ParsedStorePublisher:
        local = FsEvidenceObjectStore(self.settings.storage.data_dir, subdirectory=PARSED_DIRECTORY)
        return ParsedStorePublisher(
            local=local,
            local_path_for=local.path_for,
            remote=self._evidence_bucket(),
            suppression=self.suppression_list(),
        )

    def version_retention(self, *, bucket: bool) -> VersionDirectoryRetention:
        """Build the retirement of superseded parsed-store version directories (`v1-e31-t16`).

        On this machine without `bucket`; in this environment's bucket with it, signed with the
        everyday profile and never the takedown's: retiring there tags, and deletes nothing.
        Directories are judged against the parser version `caselist parse` runs. Raises
        :class:`EvidenceStoreNotConfigured` for `bucket` when this environment names none.
        """
        name = "version_retention_bucket" if bucket else "version_retention_local"
        return self.singleton(name, lambda: self._build_version_retention(bucket=bucket))

    def _build_version_retention(self, *, bucket: bool) -> VersionDirectoryRetention:
        # Imported here, not at module scope: lxml is loaded only by a command that needs the parser.
        from debate_core.integrations.docx_parser import DebateDocxParser

        parser_version = DebateDocxParser().parser_version
        if not bucket:
            return VersionDirectoryRetention(
                LocalVersionDirectories(self.settings.storage.data_dir), parser_version=parser_version
            )
        # Imported here, not at module scope: boto3 is an optional dependency. See the docstring.
        from debate_core.integrations.s3.version_directories import S3VersionDirectories

        settings = self.settings
        s3 = settings.storage.s3
        if not s3.bucket:
            raise EvidenceStoreNotConfigured(settings.environment)
        place = S3VersionDirectories(
            bucket=str(s3.bucket),
            client=self._s3_client(profile=s3.aws_profile, profile_setting=_EVERYDAY_PROFILE_SETTING),
            profile=s3.aws_profile,
            profile_setting=_EVERYDAY_PROFILE_SETTING,
        )
        return VersionDirectoryRetention(place, parser_version=parser_version)

    def verify_manifest(self) -> VerifyManifest:
        """Build `debate-research verify` over this environment's local evidence store (`v1-e03-t06`).

        The verifier reads snapshot records from the SQLite file and their content from the blob
        store under `storage.data_dir`, through ``SnapshotService.load``: the same records and
        blobs every card on this machine was cut from. Nothing here reaches the network; a snapshot
        that is not in this data directory is a card the verifier reports as ``SNAPSHOT_MISSING``.
        """
        return self.singleton("verify_manifest", self._build_verify_manifest)

    def _build_verify_manifest(self) -> VerifyManifest:
        clock = _PortClock(self.clock())
        snapshots = SnapshotService(
            blobs=FsSnapshotStore(self.settings.storage.data_dir),
            clock=clock,
            # Verification only loads snapshots; it never mints an id. The port is required all the same.
            id_generator=_PortIdGenerator(),
        )
        articles = SqliteArticleRepository(self.database)
        return VerifyManifest(verifier=EvidenceVerifier(articles=articles, snapshots=snapshots, clock=clock))

    def caselist_import(self) -> CaselistImportService:
        """Build the weekly-archive importer over this environment's local evidence store.

        No S3 and no bucket: an import writes to the machine it runs on, and publishing what it
        wrote is a separate, deliberate `debate-research caselist publish` (v1-e30-t05).
        """
        return self.singleton("caselist_import", self._build_caselist_import)

    def _build_caselist_import(self) -> CaselistImportService:
        return CaselistImportService(
            caselists=SqliteCaselistRepository(self.database),
            blobs=FsSnapshotStore(self.settings.storage.data_dir),
            suppression=self.local_suppression_list(),
            earlier_manifest_digests=self._earlier_manifest_digests(),
        )

    def caselist_later_manifests(self) -> LaterManifests:
        """Build what measures the later manifests again after a weekly import (`v1-e30-t18`).

        Over the same local store and suppression list as :meth:`caselist_import`: `caselist import`
        calls it after writing the weekly's manifest, and a weekly imported late leaves no later
        manifest measured without it.
        """
        return LaterManifests(
            caselists=SqliteCaselistRepository(self.database),
            local=self._local_evidence(),
            suppression=self.local_suppression_list(),
        )

    def _earlier_manifest_digests(self) -> EarlierManifestDigests:
        """What a weekly import counts first-seen against: this machine's manifests (`v1-e30-t08`)."""
        return functools.partial(digests_in_earlier_manifests, self._local_evidence())

    def local_suppression_list(self) -> RecordedSuppressionList:
        """This environment's local copy of the suppression list, and nothing else.

        What the offline importers read. Reading it creates nothing: an environment that has never
        had a removal has no `suppression/` directory, and an import does not give it one.
        """
        return self.singleton(
            "local_suppression_list",
            lambda: RecordedSuppressionList(local_suppression_list_file(self.settings.storage.data_dir)),
        )

    def suppression_list(self) -> RecordedSuppressionList:
        """The local copy and the bucket's, read as one: what every bucket-holding command consults.

        Read through the everyday evidence profile, which may read `manifests/_suppression/`.
        Raises :class:`EvidenceStoreNotConfigured` when this environment names no bucket.
        """
        return self.singleton("suppression_list", self._build_suppression_list)

    def _build_suppression_list(self) -> RecordedSuppressionList:
        bucket = self._evidence_bucket()
        return RecordedSuppressionList(
            local_suppression_list_file(self.settings.storage.data_dir),
            ObjectStoreAppendOnlyRecord(
                bucket,
                SUPPRESSION_LIST_KEY,
                location=f"s3://{self.settings.storage.s3.bucket}/{SUPPRESSION_LIST_KEY}",
            ),
        )

    def openev_import(self) -> OpenEvImportService:
        """Build the OpenEv camp-file importer over the same local store as `caselist_import`.

        Same repository, same blob store: that is what lets a camp file and a disclosure with
        identical bytes resolve to one source document (`v1-e30-t04-openev-importer`).
        """
        return self.singleton("openev_import", self._build_openev_import)

    def _build_openev_import(self) -> OpenEvImportService:
        return OpenEvImportService(
            caselists=SqliteCaselistRepository(self.database),
            blobs=FsSnapshotStore(self.settings.storage.data_dir),
            suppression=self.local_suppression_list(),
        )

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
        from debate_core.integrations.s3 import S3EvidenceObjectStore

        settings = self.settings
        storage = settings.storage
        if not storage.s3.bucket:
            raise EvidenceStoreNotConfigured(settings.environment)

        # One client for both keyspaces: one set of credentials, one connection pool, and one
        # profile name in any `aws sso login` hint the adapters raise.
        client = self._s3_client(profile=storage.s3.aws_profile, profile_setting=_EVERYDAY_PROFILE_SETTING)

        def bucket_store() -> S3EvidenceObjectStore:
            return S3EvidenceObjectStore(
                bucket=str(storage.s3.bucket),
                client=client,
                profile=storage.s3.aws_profile,
                profile_setting=_EVERYDAY_PROFILE_SETTING,
                multipart_threshold_bytes=storage.s3.multipart_threshold_bytes,
            )

        named_objects = FsEvidenceObjectStore(storage.data_dir)
        blobs = FsEvidenceObjectStore(storage.data_dir, subdirectory=BLOB_DIRECTORY.parent)
        suppression = RecordedSuppressionList(
            local_suppression_list_file(storage.data_dir),
            ObjectStoreAppendOnlyRecord(
                bucket_store(),
                SUPPRESSION_LIST_KEY,
                location=f"s3://{storage.s3.bucket}/{SUPPRESSION_LIST_KEY}",
            ),
        )
        return EvidenceSyncService(
            suppression=suppression,
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
            # A push leaves out the bytes `caselist publish` does not upload (v1-e30-t22).
            held_back=functools.partial(held_back_digests, self._local_evidence()),
        )

    def caselist_publish(self) -> CaselistPublishService:
        """Build the publisher from this machine's evidence store to this environment's bucket.

        Raises :class:`EvidenceStoreNotConfigured` when this environment names no bucket. Built
        with :meth:`suppression_list`, the local and bucket copies read as one.
        """
        return self.singleton(
            "caselist_publish",
            lambda: CaselistPublishService(
                local=self._local_evidence(),
                remote=self._evidence_bucket(),
                suppression=self.suppression_list(),
            ),
        )

    def caselist_status(self) -> CaselistStatusService:
        """Build the comparison between this machine's caselist snapshots and the bucket's.

        It can also list object versions, for the removal-residue check `caselist status` asks for
        (`v1-e30-t10`). That client is built with the everyday evidence profile, like the bucket's:
        the takedown profile is never read here. The removal log and the scopes beside it are read
        from this machine's copy and the bucket's, as the suppression list is (`v1-e30-t15`). It is
        given the inbox the pull downloads into, which it reads only when asked for the uploads a
        removal's hold covers there (`v1-e30-t21`); the pull never asks.
        """
        return self.singleton("caselist_status", self._build_caselist_status)

    def _build_caselist_status(self) -> CaselistStatusService:
        # Imported here, not at module scope: boto3 is an optional dependency. See the docstring.
        from debate_core.integrations.s3 import S3EvidenceVersionStore

        storage = self.settings.storage
        bucket = self._evidence_bucket()
        return CaselistStatusService(
            local=self._local_evidence(),
            remote=bucket,
            suppression=self.suppression_list(),
            # Both copies of the log, and of the scopes beside it, read as the list is (`v1-e30-t15`).
            removal_log=RecordedRemovalLog(
                local_removal_log_file(storage.data_dir),
                ObjectStoreAppendOnlyRecord(
                    bucket, REMOVAL_LOG_KEY, location=f"s3://{storage.s3.bucket}/{REMOVAL_LOG_KEY}"
                ),
            ),
            environment=self.settings.environment.value,
            inbox=self.caselist_inbox(),
            versions=S3EvidenceVersionStore(
                bucket=str(storage.s3.bucket),
                profile=storage.s3.aws_profile,
                profile_setting=_EVERYDAY_PROFILE_SETTING,
                client=self._s3_client(
                    profile=storage.s3.aws_profile, profile_setting=_EVERYDAY_PROFILE_SETTING
                ),
            ),
        )

    def caselist_removal(self) -> CaselistRemovalService:
        """Build `caselist remove` and `caselist unsuppress` for this environment (`v1-e30-t07`).

        Raises :class:`EvidenceStoreNotConfigured` when this environment names no bucket: a removal
        is from this machine *and* the bucket, never one of them.
        """
        return self.singleton("caselist_removal", self._build_caselist_removal)

    def _build_caselist_removal(self) -> CaselistRemovalService:
        # Imported here, not at module scope: boto3 is an optional dependency. See the docstring.
        from debate_core.integrations.s3 import S3EvidenceVersionStore

        settings = self.settings
        storage = settings.storage
        bucket = self._evidence_bucket()
        data_dir = storage.data_dir
        suppression = self.suppression_list()
        clock = _PortClock(self.clock())
        planner = RemovalPlanner(
            caselists=SqliteCaselistRepository(self.database),
            local=self._local_evidence(),
            local_blobs=FsEvidenceVersionStore(data_dir / BLOB_DIRECTORY.parent),
            local_parsed=FsEvidenceVersionStore(data_dir / PARSED_DIRECTORY),
            remote=bucket,
            # The everyday profile, which may list versions under the removable prefixes
            # (v1-e29-t06). Where that grant is not applied, the plan says they were not counted.
            remote_versions=S3EvidenceVersionStore(
                bucket=str(storage.s3.bucket),
                profile=storage.s3.aws_profile,
                profile_setting=_EVERYDAY_PROFILE_SETTING,
                client=self._s3_client(
                    profile=storage.s3.aws_profile, profile_setting=_EVERYDAY_PROFILE_SETTING
                ),
            ),
            inbox=self.caselist_inbox(),
            suppression=suppression,
            # Both copies of the log, read with the everyday profile as status reads them: the dry
            # run needs the scopes of the request's earlier runs for its sweep (v1-e30-t19).
            removal_log=RecordedRemovalLog(
                local_removal_log_file(data_dir),
                ObjectStoreAppendOnlyRecord(
                    bucket, REMOVAL_LOG_KEY, location=f"s3://{storage.s3.bucket}/{REMOVAL_LOG_KEY}"
                ),
            ),
            clock=clock,
            environment=settings.environment.value,
            bucket=str(storage.s3.bucket),
        )
        return CaselistRemovalService(
            planner=planner,
            caselists=SqliteCaselistRepository(self.database),
            local=self._local_evidence(),
            local_blobs=FsEvidenceVersionStore(data_dir / BLOB_DIRECTORY.parent),
            local_parsed=FsEvidenceVersionStore(data_dir / PARSED_DIRECTORY),
            inbox=self.caselist_inbox(),
            remote=bucket,
            suppression=suppression,
            local_suppression=local_suppression_list_file(data_dir),
            local_removal_log=local_removal_log_file(data_dir),
            takedown=self.takedown_access,
            clock=clock,
            environment=settings.environment.value,
        )

    def takedown_access(self) -> TakedownAccess:
        """The `EvidenceRemoval` profile's reach into this environment's bucket, built on demand.

        Raises :class:`~debate_core.application.caselist.removal_service.TakedownNotConfigured`
        when `DEBATE_REMOVAL_PROFILE` is unset. Overridable as `"takedown_access"` for a test.
        """
        return self.singleton("takedown_access", self._build_takedown_access)

    def _build_takedown_access(self) -> TakedownAccess:
        from debate_core.integrations.s3 import S3EvidenceObjectStore, S3EvidenceVersionStore

        settings = self.settings
        storage = settings.storage
        profile = settings.removal_profile
        if not profile:
            raise TakedownNotConfigured
        if not storage.s3.bucket:
            raise EvidenceStoreNotConfigured(settings.environment)
        client = self._s3_client(profile=profile, profile_setting=_REMOVAL_PROFILE_SETTING)
        return TakedownAccess(
            versions=S3EvidenceVersionStore(
                bucket=str(storage.s3.bucket),
                profile=profile,
                profile_setting=_REMOVAL_PROFILE_SETTING,
                client=client,
            ),
            objects=S3EvidenceObjectStore(
                bucket=str(storage.s3.bucket),
                client=client,
                profile=profile,
                profile_setting=_REMOVAL_PROFILE_SETTING,
                multipart_threshold_bytes=storage.s3.multipart_threshold_bytes,
            ),
            # Asked first, before the profile lists or writes anything (v1-e29-t08): built from the
            # same profile name as the client above, so it answers for the role that would delete.
            caller=self.caller_identity_for(
                ConfiguredProfile(setting=_REMOVAL_PROFILE_SETTING, name=profile, for_takedowns=True)
            ),
            profile=profile,
            bucket=str(storage.s3.bucket),
        )

    def caller_identity_for(self, profile: ConfiguredProfile) -> CallerIdentity:
        """Who `profile` is signed in as, asked of STS: the one place that adapter is built.

        The takedown preflight asks it of the takedown profile (`v1-e29-t08`), and the profile
        check of every profile these settings name (`v1-e34-t22`). Raises
        :class:`~debate_core.application.errors.StoreProfileNotConfigured`, naming the profile's
        setting, when this machine's AWS config does not define it: building the adapter builds a
        session, which is where boto3 refuses one. A test replaces this method to stub the answer.
        """
        from debate_core.integrations.s3 import StsCallerIdentity

        s3 = self.settings.storage.s3
        return StsCallerIdentity(
            bucket=str(s3.bucket or ""),
            profile=profile.name,
            profile_setting=profile.setting,
            region=s3.region,
            endpoint_url=s3.endpoint_url,
            ignore_configured_endpoints=self._ignores_configured_endpoints,
        )

    def evidence_profile_check(self) -> EvidenceProfileCheck:
        """Build the check of every evidence profile this environment is configured with (`v1-e34-t22`).

        The everyday profile, when the settings name one, and the takedown profile, when
        `DEBATE_REMOVAL_PROFILE` is set. An environment with neither, which is what `test` is,
        has nothing to check. Building the check asks nothing and reads no AWS
        config: each profile's adapter is built when the check is run.
        """
        return self.singleton("evidence_profile_check", self._build_evidence_profile_check)

    def _build_evidence_profile_check(self) -> EvidenceProfileCheck:
        settings = self.settings
        s3 = settings.storage.s3
        configured: list[ConfiguredProfile] = []
        if s3.aws_profile:
            configured.append(ConfiguredProfile(setting=_EVERYDAY_PROFILE_SETTING, name=s3.aws_profile))
        if settings.removal_profile:
            configured.append(
                ConfiguredProfile(
                    setting=_REMOVAL_PROFILE_SETTING, name=settings.removal_profile, for_takedowns=True
                )
            )
        return EvidenceProfileCheck(
            profiles=configured,
            caller_for=self.caller_identity_for,
            environment=settings.environment.value,
        )

    def _s3_client(self, *, profile: str | None, profile_setting: str) -> S3Client:
        """An S3 client for this environment's bucket, signed with `profile`: the one place one is built.

        It goes where `storage.s3.endpoint_url` says, which only a dev installation accepts, and
        otherwise to AWS. A prod installation also ignores the endpoints botocore configures for
        itself, so no variable or AWS config entry can send its evidence store elsewhere
        (`v1-e01-t21`).
        """
        # Imported here, not at module scope: boto3 is an optional dependency. See the docstring.
        from debate_core.integrations.s3 import build_s3_client

        s3 = self.settings.storage.s3
        return build_s3_client(
            region=s3.region,
            profile=profile,
            profile_setting=profile_setting,
            endpoint_url=s3.endpoint_url,
            ignore_configured_endpoints=self._ignores_configured_endpoints,
        )

    @property
    def _ignores_configured_endpoints(self) -> bool:
        """Whether botocore's own endpoint routes are ignored: in prod, always."""
        return self.settings.environment is Environment.PROD

    def _local_evidence(self) -> LocalEvidence:
        data_dir = self.settings.storage.data_dir
        objects = FsEvidenceObjectStore(data_dir)
        blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
        return LocalEvidence(
            objects=objects,
            blobs=blobs,
            object_path_for=objects.path_for,
            blob_path_for=blobs.path_for,
        )

    def _evidence_bucket(self) -> EvidenceObjectStore:
        """This environment's bucket through the S3 adapter, one per run for both caselist services."""
        return self.singleton("evidence_bucket", self._build_evidence_bucket)

    def _build_evidence_bucket(self) -> EvidenceObjectStore:
        # Imported here, not at module scope: boto3 is an optional dependency. See the docstring.
        from debate_core.integrations.s3 import S3EvidenceObjectStore

        settings = self.settings
        storage = settings.storage
        if not storage.s3.bucket:
            raise EvidenceStoreNotConfigured(settings.environment)
        return S3EvidenceObjectStore(
            bucket=str(storage.s3.bucket),
            client=self._s3_client(profile=storage.s3.aws_profile, profile_setting=_EVERYDAY_PROFILE_SETTING),
            profile=storage.s3.aws_profile,
            profile_setting=_EVERYDAY_PROFILE_SETTING,
            multipart_threshold_bytes=storage.s3.multipart_threshold_bytes,
        )

    def caselist_sync(self, *, event_for_caselist: Callable[[str], Event | None]) -> CaselistSyncService:
        """Build the weekly pull: the source, both importers, the publisher and the status check.

        `event_for_caselist` is the command's, not this container's: which event a caselist slug
        debates is a table `debate_cli.commands.caselist` keeps, and a composition root that
        imported a command module to reach it would have the dependency the wrong way round.

        The publisher and the status check are `None` when this environment names no bucket, which
        is what `test` is and what a half-configured installation is. The run then records its
        publish stage as skipped, with the reason, instead of failing: the archives are already on
        this machine and `caselist publish` completes them later.

        The parse stage (`v1-e34-t17`) is the pipeline `caselist parse` runs, built over the pull's
        own suppression list and, with a bucket, the parsed store's publisher. It is `None` when
        `caselist.parse_imported_sources` is off, and the run then records the stage as skipped
        with that setting's name. Landscape (`v1-e32-t05`) is `None` because it does not exist yet.

        Raises :class:`~debate_core.application.ports.caselist_source.CaselistApiDisabled` unless
        the operator has turned the API on, which is the data-use policy's E34 gate.
        """
        return self.singleton("caselist_sync", lambda: self._build_caselist_sync(event_for_caselist))

    def _build_caselist_sync(self, event_for_caselist: Callable[[str], Event | None]) -> CaselistSyncService:
        settings = self.settings
        caselist = settings.caselist
        # The bucket first (`v1-e34-t24`). A profile the AWS config does not define stops it being
        # built, and a run stopped there, a dry run included, used to have created the data
        # directory and an empty database on its way. It is one per run, so the services below
        # are handed this same one.
        if settings.storage.s3.bucket:
            self._evidence_bucket()
        repository = SqliteCaselistRepository(self.database)
        blobs = FsSnapshotStore(settings.storage.data_dir)
        publisher: CaselistPublishService | None = None
        status: CaselistStatusService | None = None
        # The pull's importers read the bucket's copy of the list too when there is a bucket: the
        # run is about to publish to it anyway, and an unattended weekly import is exactly the one
        # that must not bring back a file a removal made from another machine took out. When that
        # copy needs a login the run does not have, they read this machine's copy alone and the run
        # says so, so an expired SSO session pends the publish rather than failing the import
        # (v1-e34-t07, PM decision). Safe while one machine imports, as `caselist import`'s local
        # read is (v1-e30-t07 Deviation 7); revisit both the day a second machine imports.
        suppression: SuppressionList = self.local_suppression_list()
        if settings.storage.s3.bucket:
            publisher = self.caselist_publish()
            status = self.caselist_status()
            suppression = LocalFallbackSuppressionList(
                self.suppression_list(), local=self.local_suppression_list()
            )
        return CaselistSyncService(
            source=self.opencaselist_client(),
            archive_importer=CaselistImportService(
                caselists=repository,
                blobs=blobs,
                suppression=suppression,
                earlier_manifest_digests=self._earlier_manifest_digests(),
            ),
            openev_importer=OpenEvImportService(caselists=repository, blobs=blobs, suppression=suppression),
            local=self._local_evidence(),
            read_archive=self.read_archive,
            event_for_caselist=event_for_caselist,
            inbox=self._inbox_directory(),
            state_dir=settings.storage.data_dir,
            # The importers' own list, so the run's skip of a removed camp file (v1-e34-t07) and the
            # importers' refusal of one can never read different copies.
            suppression=suppression,
            publisher=publisher,
            status=status,
            # The pipeline over the very list above, so that a read of it that fell back to this
            # machine's copy is one the run sees, and the parsed store's publisher only where the
            # run publishes at all.
            parse=PullParseStage(
                parse=self._build_caselist_parse(suppression),
                publisher=self.parsed_publisher() if settings.storage.s3.bucket else None,
            )
            if caselist.parse_imported_sources
            else None,
            openev_event=caselist.openev_event,
            openev_year=caselist.openev_year,
            bulk_downloads_per_day=caselist.bulk_downloads_per_day,
            clock=self.clock(),
            # The complete-archive rotation (`v1-e34-t04`): on unless the profile turns it off.
            full_archive_rotation=FullArchiveRotation(
                interval=timedelta(days=caselist.full_archive_interval_days)
            )
            if caselist.full_archive_rotation
            else None,
            read_full_archive=self.read_full_archive,
        )

    def caselist_sync_monitor(self) -> SyncRunMonitor:
        """Build what records and announces every `caselist pull` (`v1-e34-t03-sync-monitoring`).

        The run log lives in this environment's data directory, and the record goes to its bucket
        when it names one. The caselist_token, when it is in the settings, is registered as a
        secret to scrub from every message, as a backstop to messages that never carry it.

        The monitor is handed the command's own rule for which failures a retry may cure
        (:func:`~debate_cli.exit_codes.codes_exit_as_a_retrieval_failure`), so that a failed run's
        notification says "the next run retries it" exactly when the command exits `3`
        (`v1-e34-t19`). `debate_core` never decides that for itself.

        It is handed the bucket to build, not the bucket (`v1-e34-t22`). A profile setting that
        names a profile the AWS config does not define stops the S3 adapter being built
        (`v1-e29-t07`), and a monitor that needed the adapter to exist could not be built either:
        the run ended unrecorded and unannounced. Built this way the monitor always exists, the
        refusal reaches it as the error the run stopped on, and the record it writes here is owed
        to the bucket until a run can build one.
        """
        return self.singleton("caselist_sync_monitor", self._build_caselist_sync_monitor)

    def _build_caselist_sync_monitor(self) -> SyncRunMonitor:
        settings = self.settings
        token = settings.providers.caselist_token
        return SyncRunMonitor(
            state_dir=settings.storage.data_dir,
            environment=settings.environment.value,
            notifier=self.sync_notifier(),
            remote=None,
            build_remote=self._evidence_bucket if settings.storage.s3.bucket else None,
            aws_login_command=self._aws_login_command(),
            secrets=lambda: [token.get_secret_value()] if token is not None else [],
            clock=self.clock(),
            may_succeed_on_retry=codes_exit_as_a_retrieval_failure,
        )

    def caselist_sync_history(self) -> SyncRunHistory:
        """Recent `caselist pull` runs, from this machine's log or (`--remote`) the bucket."""
        return self.singleton("caselist_sync_history", self._build_caselist_sync_history)

    def _build_caselist_sync_history(self) -> SyncRunHistory:
        settings = self.settings
        data_dir = settings.storage.data_dir
        return SyncRunHistory(
            log=SyncRunLog(data_dir / SYNC_RUN_LOG_FILENAME),
            remote=self._evidence_bucket if settings.storage.s3.bucket else None,
            scratch_dir=data_dir,
            overdue_after_days=settings.caselist.stale_after_days,
        )

    def sync_notifier(self) -> Notifier:
        """macOS Notification Centre on the operator's Mac; nothing in `test` or anywhere else.

        `caselist.notifier = "auto"` never notifies in the `test` environment, so no test run can
        put a banner on a developer's screen even with a profile that forgot to say `none`.
        """
        settings = self.settings
        kind = settings.caselist.notifier
        if kind is SyncNotifierKind.NONE:
            return NullNotifier()
        if kind is SyncNotifierKind.AUTO and (
            settings.environment is Environment.TEST or sys.platform != "darwin"
        ):
            return NullNotifier()
        from debate_core.integrations.local.macos_notifier import MacOsNotifier

        return MacOsNotifier()

    def _aws_login_command(self) -> str:
        profile = self.settings.storage.s3.aws_profile
        return f"aws sso login --profile {profile}" if profile else "aws sso login"

    def caselist_token_store(self) -> CaselistTokenStore:
        """Where this environment keeps the operator's caselist_token (v1-e34-t01).

        The keychain item is per environment, and the file fallback lives under this environment's
        data directory, so a dev login never authenticates a prod run.
        """
        return self.singleton("caselist_token_store", self._build_caselist_token_store)

    def _build_caselist_token_store(self) -> CaselistTokenStore:
        from debate_core.integrations.opencaselist import CaselistTokenStore, default_secret_file

        settings = self.settings
        return CaselistTokenStore.for_settings(
            settings.caselist.token_backend,
            account=settings.environment.value,
            secret_file=settings.caselist.secret_file or default_secret_file(settings.storage.data_dir),
        )

    def opencaselist_client(self) -> OpenCaselistClient:
        """The OpenCaselist API client, or the refusal this installation's settings call for.

        Raises :class:`~debate_core.application.ports.caselist_source.CaselistApiDisabled` unless
        `caselist.api_enabled` is set, before any prompt is shown or request built.
        """
        return self.singleton("opencaselist_client", self._build_opencaselist_client)

    def _build_opencaselist_client(self) -> OpenCaselistClient:
        # Imported here for the same reason the S3 adapters are: `--help` should not pay for httpx.
        from debate_cli import package_version
        from debate_core.integrations.opencaselist import OpenCaselistClient

        return OpenCaselistClient.from_settings(
            self.settings,
            token_store=self.caselist_token_store(),
            user_agent_version=package_version(),
        )

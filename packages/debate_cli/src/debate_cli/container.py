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
(`v1-e03-t06-verify-command`); and :meth:`ServiceContainer.article_fetch`, which
`debate-research fetch` runs (`v1-e04-t06-fetch-command`), and :meth:`ServiceContainer.card_cutting`,
which `debate-research cut` runs after it (`v1-e06-t06-cut-command`); and
:meth:`ServiceContainer.caselist_sync`, which
`debate-research caselist pull` and the weekly launchd agent run (`v1-e34-t02-scheduled-sync`), recorded by
:meth:`ServiceContainer.caselist_sync_monitor` and read back by
:meth:`ServiceContainer.caselist_sync_history` (`v1-e34-t03-sync-monitoring`); and
:meth:`ServiceContainer.caselist_parse` and :meth:`ServiceContainer.parsed_publisher`, which
`debate-research caselist parse` runs (`v1-e31-t06-parse-pipeline`); and
:meth:`ServiceContainer.landscape_run`, which `debate-research landscape report` runs
(`v1-e32-t05-landscape-cli`); and :meth:`ServiceContainer.file_build`,
:meth:`ServiceContainer.file_quality` and :meth:`ServiceContainer.file_suggest`, which
`debate-research files build`, `files check` and `files suggest` run (`v1-e33-t03-file-build-cli`), and
:meth:`ServiceContainer.file_publish`, which `files publish` runs (`v1-e33-t05-file-publish`). The import
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

## Why every integration is imported inside its factory

Every `debate_core.integrations` module is imported inside the method that builds with it, never at
the top of this module, so importing this module, or `debate_cli.app`, loads none of them
(`v1-e01-t39`; `packages/debate_cli/tests/test_container_factories.py` holds it). Add an adapter
the same way. There are three reasons, and none is style:

* **Optional dependencies.** boto3 (the `aws` extra), lxml (`docx`), httpx (`http`) and the
  extraction libraries are optional dependencies of `debate-core`, and `debate-research --help`
  should not depend on them. `debate-cli` itself requires the extras its wiring needs (`aws`,
  `docx`, `opencaselist`, v1-e01-t17), so an installed build has them. If one is missing anyway,
  the missing dependency arrives only when a command reaches the factory, and the root error
  handler reports it with the fix for that kind of installation: reinstall at a fixed tag for an
  installed build, `uv sync` for a checkout
  (:func:`debate_cli.installation.incomplete_installation_failure`).
* **Startup.** `--help` and `--version` pay for no adapter, and a command for only its own.
* **Test selection.** Every command module reaches this module through `debate_cli.context`, so
  an integration imported at the top would reach every command, and through `debate_cli.app`
  every test that runs one. `scripts/affected_tests.py` reads an import inside a method as that
  method's, and a command's `cli.services.<name>` as reaching method `<name>`, so a change to an
  adapter selects the tests of the commands whose factories build with it.

An integration that fails to import therefore fails only the commands that build with it. A test
builds every factory under several settings and checks that between them they import every
integration the post-install check below finds, so such a failure still fails `ci` (the PM's
condition of 2026-10-27).

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
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Final, Self, cast

from debate_cli.build_info import bundled_config_root, current_build_info
from debate_cli.exit_codes import codes_exit_as_a_retrieval_failure
from debate_core.application.aff_assignment import AffAssignmentService
from debate_core.application.analytic_texts import AnalyticTextService
from debate_core.application.article_fetch import ArticleFetch, Closeable
from debate_core.application.article_service import ArticleService
from debate_core.application.card_selection import CardSelector
from debate_core.application.card_service import CardService
from debate_core.application.caselist.bucket_run import BucketRun
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
from debate_core.application.caselist.publish_service import CaselistPublishService, withheld_manifest_reason
from debate_core.application.caselist.removal_plan import RemovalPlanner
from debate_core.application.caselist.removal_service import (
    CaselistRemovalService,
    TakedownAccess,
    TakedownNotConfigured,
)
from debate_core.application.caselist.run_home_move import RunHomeMove
from debate_core.application.caselist.run_lock import (
    RUN_LOCK_KEY,
    BucketRunLock,
    BucketWriteGuard,
    HolderKind,
)
from debate_core.application.caselist.run_state import RunState
from debate_core.application.caselist.run_state_restore import DataDirectory, RunStateRestore
from debate_core.application.caselist.run_state_seed import RunStateSeed
from debate_core.application.caselist.run_state_sources import RestoredSources
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
from debate_core.application.caselist_card_stats import CaselistCardStatsService, fingerprint_thresholds
from debate_core.application.caselist_parse import CaselistParseService
from debate_core.application.caselist_pull_parse import PullParseStage
from debate_core.application.caselist_sync import (
    PARSE_OWED_FILENAME,
    CaselistSyncService,
    FullArchiveRotation,
    ParseOwed,
    why_no_search_index_stage,
)
from debate_core.application.citation_service import CitationService
from debate_core.application.environment_data_dirs import profile_data_dir
from debate_core.application.evidence_profiles import (
    MODEL_PROFILE_SETTING,
    ConfiguredProfile,
    EvidenceProfileCheck,
)
from debate_core.application.evidence_sync import (
    EvidenceSyncService,
    SyncJournal,
    SyncKeyspace,
)
from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.application.export_service import ExportService
from debate_core.application.file_build_service import FileBuildService
from debate_core.application.file_publish_service import FilePublishService
from debate_core.application.file_quality_service import FileQualityService
from debate_core.application.file_suggest_service import FileSuggestService
from debate_core.application.landscape_model_evaluation import LandscapeModelEvaluationService
from debate_core.application.landscape_model_stage import (
    CLASSIFY_POSITION_PROMPT_ID,
    ModelClassificationStage,
    ParsedStoreCardTexts,
)
from debate_core.application.landscape_run import LandscapeModelMode, LandscapeRunService
from debate_core.application.landscape_scan import ScanAcceptanceLog
from debate_core.application.plan_texts import PlanTextService
from debate_core.application.ports.archive import ArchiveEntry
from debate_core.application.ports.caller_identity import CallerIdentity
from debate_core.application.ports.card_edit_log import CardEditEntry
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey
from debate_core.application.ports.model_router import ModelRouter, RoutingConfigError
from debate_core.application.ports.notifier import Notifier, NullNotifier
from debate_core.application.ports.suppression import SuppressionList
from debate_core.application.review_queue_order import ReviewQueueOrdering
from debate_core.application.search_index_build import SearchIndexBuildService
from debate_core.application.search_index_prune import SearchIndexPrune
from debate_core.application.search_index_publish import SearchIndexPublishService
from debate_core.application.search_index_refresh import SEARCH_INDEX_DIRECTORY, SearchIndexRefresh
from debate_core.application.search_index_store_check import SearchIndexStoreCheck
from debate_core.application.settings import (
    CaselistTokenBackend,
    ConfigurationError,
    Environment,
    RunStateMode,
    Settings,
    SyncNotifierKind,
    find_repository_root,
)
from debate_core.application.snapshot_service import SnapshotService
from debate_core.application.structured_output import REPAIR_PROMPT_ID, StructuredOutputGuard
from debate_core.application.sync_runs import (
    CLOUD_NO_SESSION_CURE,
    SYNC_RUN_LOG_FILENAME,
    SyncRunHistory,
    SyncRunLog,
    SyncRunMonitor,
)
from debate_core.application.tub.accounts import AccountAdministration
from debate_core.application.verify_manifest import VerifyManifest
from debate_core.domain import new_id
from debate_core.domain.caselist import Event
from debate_core.domain.model_contracts import ModelProvider
from debate_core.evidence.format_profile import (
    FORMAT_PROFILES_DIRECTORY,
    FormatProfileError,
    ResolvedFormatProfile,
    load_format_profiles,
)
from debate_core.retrieval.extraction import ContentTypeDispatcher

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only; see the factories
    from mypy_boto3_s3.client import S3Client

    from debate_core.application.caselist.backfile_import import BackfileImportService
    from debate_core.application.caselist.backfile_survey import BackfileSurvey
    from debate_core.application.caselist.openev_metadata_reimport_in_bucket import (
        OpenEvMetadataReimportInBucket,
    )
    from debate_core.application.caselist_login import ScheduledLogin, SecretText, TabroomPasswordSecret
    from debate_core.integrations.docx_parser import DebateDocxParser
    from debate_core.integrations.local import SqliteDatabase
    from debate_core.integrations.models.model_mode import ModelMode
    from debate_core.integrations.models.prompt_registry import PromptRegistry
    from debate_core.integrations.models.record_replay import CassetteDirectory
    from debate_core.integrations.models.routing_policy import RoutingFileFinding
    from debate_core.integrations.models.usage import UsageLog
    from debate_core.integrations.opencaselist import CaselistTokenStore, OpenCaselistClient

__all__ = [
    "CARD_CASSETTES_DIRECTORY",
    "DEFAULT_INBOX_DIRECTORY",
    "LOCAL_OWNER_ID",
    "SERVICE_NAMES",
    "CardCutting",
    "EvidenceStoreNotConfigured",
    "ServiceContainer",
    "Settings",
    "SettingsNotConfigured",
    "validating_routing",
]

SERVICE_NAMES: Final[tuple[str, ...]] = (
    "article_fetch",
    "bucket_write_guard",
    "card_cutting",
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
    "file_build",
    "file_publish",
    "file_quality",
    "file_suggest",
    "openev_import",
    "opencaselist_client",
    "search_index_build",
    "search_index_publish",
    "search_index_store_check",
    "tub_account_administration",
    "verify_manifest",
)
"""Names of the services this container can build, for `debate-research doctor` to report."""

DEFAULT_INBOX_DIRECTORY: Final = "inbox"
"""Where `caselist pull` puts its downloads when `caselist.inbox_dir` is unset: `<data_dir>/inbox`.

Inside the data directory so that one environment is one directory, exactly as the blob store and
the SQLite file are (`debate_core.integrations.local`): a dev pull can never drop an archive where
a prod import would read it.
"""


CARD_CASSETTES_DIRECTORY: Final = Path("cards") / "model-cassettes"
"""Where `cut`'s model calls are recorded and replayed, in the data directory (`v1-e06-t06`).

Each cassette holds the numbered text of the article it was asked about, so it is this machine's
data, as the landscape's cassettes are: kept under the data directory and never committed."""

LOCAL_OWNER_ID: Final = "00000000000000000000000001"
"""The owner of every card `cut` saves: V1's CLI is one person's tool on one machine (`v1-e06-t06`).

A card always belongs to someone (`Card.owner_id`), and V1 has no accounts to name them by, so the
CLI's cards share one fixed id. It is not a person's identifier and says nothing about anyone; V2's
accounts give cards their owners."""


class CardCutting:
    """What `cut` runs after its fetch: the card service, the exporter, the format profiles (`v1-e06-t06`).

    An async context manager, like :class:`~debate_core.application.article_fetch.ArticleFetch`: the
    citation service's Crossref client holds an HTTP client, which belongs to the event loop that used
    it, and leaving the block closes it.
    """

    def __init__(
        self,
        *,
        cards: CardService,
        export: ExportService,
        profiles: Mapping[str, ResolvedFormatProfile],
        connection: Closeable,
    ) -> None:
        self.cards = cards
        self.export = export
        self.profiles = profiles
        """The format profiles a card can be exported in, by name."""
        self._connection = connection

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._connection.aclose()


class _NoCardEditsYet:
    """The card edit log while no command edits a card: it holds no entries, and refuses one.

    CitationService reads the log only to re-resolve a card a student has edited, and keep their
    changes (`v1-e06-t01`). No V1 command edits a card, so no production log exists yet
    (:mod:`debate_core.application.ports.card_edit_log`), and a card `cut` has just made has no edits.
    """

    async def append(self, entry: CardEditEntry) -> None:
        raise RuntimeError("no V1 command edits a card, so nothing may append to the card edit log")

    async def entries_for(self, card_id: str) -> tuple[CardEditEntry, ...]:
        return ()


def _committed_root(what: str) -> Path:
    """Where `cut` reads the committed format profiles and prompts: an installed build's bundled copy,
    or the source checkout this code is running from; refused when there is neither.

    Not the checkout around the working directory, as the settings' profiles are: a prompt is rendered by
    the code beside it, so a run from another directory still reads the prompts of the code that runs.
    """
    root = bundled_config_root() or find_repository_root(_PACKAGE_DIRECTORY)
    if root is None:
        raise ConfigurationError(
            f"{what} is read from the copy an installed build carries, or from the source checkout the "
            "code runs from, and this run has neither; reinstall the build",
            field=what,
        )
    return root


def _committed_prompts() -> Path:
    from debate_core.integrations.models.prompt_registry import DEFAULT_PROMPT_DIRECTORY

    directory = _committed_root(str(DEFAULT_PROMPT_DIRECTORY)) / DEFAULT_PROMPT_DIRECTORY
    if not directory.is_dir():
        raise ConfigurationError(
            f"no {DEFAULT_PROMPT_DIRECTORY}/ directory at {directory}; this build carries no prompts to "
            "cut a card with",
            field=str(DEFAULT_PROMPT_DIRECTORY),
        )
    return directory


def _committed_format_profiles() -> dict[str, ResolvedFormatProfile]:
    directory = _committed_root(str(FORMAT_PROFILES_DIRECTORY)) / FORMAT_PROFILES_DIRECTORY
    try:
        return load_format_profiles(directory)
    except FormatProfileError as error:
        raise ConfigurationError(str(error), field=str(FORMAT_PROFILES_DIRECTORY)) from error


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
        from debate_core.integrations.models.routing_policy import RoutingPolicy

        settings = settings_loader()
        RoutingPolicy.from_settings(settings)
        return settings

    return load


def _texts_under(directory: Path) -> list[str]:
    """Every JSON file's text under `directory`, in name order: the cassettes a scan reads."""
    if not directory.is_dir():
        return []
    return [path.read_text(encoding="utf-8") for path in sorted(directory.glob("*.json"))]


class SettingsNotConfigured(RuntimeError):
    """Raised when a service needs settings and the container was built without a loader."""

    def __init__(self) -> None:
        super().__init__(
            "this ServiceContainer was built without a settings loader; pass "
            "settings_loader=load_settings, as debate_cli.app.root_callback does"
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _build_named() -> str:
    """This build, as a lock holder names who wrote it: its tag, or a source checkout's commit."""
    info = current_build_info()
    if info.tag:
        return info.tag
    return f"source checkout {info.commit[:12]}" if info.commit else "source checkout"


def _ecs_task_metadata() -> str:
    """This ECS task's metadata address, without a trailing `/`, or `""` outside ECS (`v1-e40-t04`)."""
    return os.environ.get(_ECS_METADATA_VARIABLE, "").rstrip("/")


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

LANDSCAPE_REPORTS_DIRECTORY: Final = Path("reports") / "landscape"
"""Where `landscape report` writes each bundle in the data directory, by caselist and snapshot."""

FILES_DIRECTORY: Final = Path("files")
"""The files directory, in the data directory: recipes and drafts under `recipes/<topic>/`, built files
under `built/<topic>/` (`v1-e33-t03`). Derived, as every path of the local store is, so one environment
is one directory."""

SCAN_ACCEPTANCES_DIRECTORY: Final = "scan-acceptances"
"""Beside the classification cache: the scan hits the operator accepted, per caselist (`v1-e32-t05`)."""

MODEL_CASSETTES_DIRECTORY: Final = "model-cassettes"
"""Beside the classification cache: cassettes of the landscape model stage's calls on real cards
(`v1-e32-t07`). They hold scrubbed excerpts of real evidence, so they are derived corpus data: kept under
the data directory, never committed, and under its retention and removal."""

_PACKAGE_DIRECTORY: Final = Path(__file__).resolve().parent
"""This package's directory: inside the source checkout it was installed from, when it was."""

_ECS_METADATA_VARIABLE: Final = "ECS_CONTAINER_METADATA_URI_V4"
"""Set by ECS in every task's containers: how the run lock tells the cloud run from the Mac."""

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
        from debate_core.integrations.local import SqliteDatabase

        return self.singleton("database", lambda: SqliteDatabase.open(self.settings.storage.data_dir))

    def read_archive(self, source: Path) -> Iterator[ArchiveEntry]:
        """Read a caselist archive (a `.zip` or a directory) within this installation's size ceilings.

        The local archive reader, bound to `caselist.max_archive_bytes` and
        `caselist.max_unpacked_bytes`: what `caselist import`, `caselist import-openev` and the
        weekly pull all read an archive with.
        """
        from debate_core.integrations.local import archive_reader

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
        from debate_core.integrations.local import archive_reader

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
        from debate_core.integrations.local import archive_reader

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
        from debate_core.integrations.local import archive_reader

        return archive_reader.archive_digest(source)

    def openev_upstream_paths(self) -> dict[int, str]:
        """What this machine's OpenEv delivery record knows of each id's upstream path, as digests.

        `caselist reimport-openev-metadata` writes it onto release rows imported before they carried
        it (`v1-e30-t14`). The record is the pull's, in the data directory it keeps its state in.
        """
        return self.caselist_inbox().deliveries.upstream_paths()

    def evidence_object_path(self, key: ObjectKey) -> Path:
        """The file this machine's evidence store keeps the named object `key` at: a manifest."""
        from debate_core.integrations.local import FsEvidenceObjectStore

        return FsEvidenceObjectStore(self.settings.storage.data_dir).path_for(key)

    def caselist_card_stats(self) -> CaselistCardStatsService:
        """Build the card statistics over this machine's recorded disclosures (`v1-e31-t04`).

        Reads only: the local caselist repository for disclosures, and the fingerprint thresholds
        from `settings.fingerprints`.
        """
        from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository

        return self.singleton(
            "caselist_card_stats",
            lambda: CaselistCardStatsService(
                SqliteCaselistRepository(self.database), fingerprint_thresholds(self.settings.fingerprints)
            ),
        )

    def landscape_run(
        self, *, config_dir: Path, with_bucket: bool, restored_copy: Path | None = None
    ) -> LandscapeRunService:
        """Build one caselist's landscape report over this machine's stores (`v1-e32-t05`).

        `config_dir` holds `topics.yaml`, `taxonomies/` and `overrides/`, read and checked once here.
        The staleness check is given the sync run log (the PM's ruling of 2026-10-24), and the scan's
        acceptances are kept beside the classification cache. `with_bucket` is whether this run
        publishes: only then is this environment's bucket built, signed with the everyday profile.

        **A restored copy** (`v1-e40-t17`). With `restored_copy`, the caselist's cards are the copy's:
        its manifests, parsed store (the model stage's card texts too), suppression list, run log and raw
        sources, and the run refuses a copy whose newest parsed directory is not this build's parser
        version. Every piece of the landscape's own state stays in the data directory: the
        classification cache and the review queue, the plan-text and analytic-text caches, the scan
        acceptances, the model cassettes and usage log, and the bundle under `reports/landscape/`.

        **The aff seam.** Each affirmative round's aff comes from `v1-e32-t09`'s
        :class:`~debate_core.application.aff_assignment.AffAssignmentService`, which reads the
        affirmative files' plan texts from their cache under the data directory, parsing only what it
        lacks, through the same worker pool as `caselist parse`. `v1-e32-t09` merged first, so this
        task wired it (the PM's condition of 2026-10-24).

        **The analytic-text seam.** Each CP's and K's texts and each position's overview count come from
        `v1-e32-t11`'s :class:`~debate_core.application.analytic_texts.AnalyticTextService`, which reads
        every on-topic source's paragraphs through the same worker pool, caching derived fields under the
        data directory, and reads again only the texts the report quotes.

        **The review queue's order** (`v1-e32-t26`): the queue is ordered by the local proxy model kept
        under the data directory beside `v1-e32-t21`'s feature table, checked against the parsed store
        and suppression list the run reads, and in today's order when there is none that stands.
        """
        from debate_core.integrations.docx_parser import DebateDocxParser
        from debate_core.integrations.landscape.analytic_text_store import LocalAnalyticTextStore
        from debate_core.integrations.landscape.classification_store import (
            LANDSCAPE_DIRECTORY,
            LocalClassificationStore,
            LocalQueueOrderModelStore,
        )
        from debate_core.integrations.landscape.plan_text_store import LocalPlanTextStore
        from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
        from debate_core.integrations.local import FsEvidenceObjectStore
        from debate_core.integrations.local.parsed_store import LocalParsedStore
        from debate_core.integrations.local.suppression_list import local_suppression_list_file
        from debate_core.integrations.models.model_mode import ModelMode

        settings = self.settings
        data_dir = settings.storage.data_dir
        cards_dir = data_dir if restored_copy is None else restored_copy
        objects = FsEvidenceObjectStore(cards_dir)
        taxonomies = YamlTaxonomyRepository.load(config_dir)
        local = self._local_evidence(cards_dir)
        suppression = (
            self.local_suppression_list()
            if restored_copy is None
            else RecordedSuppressionList(local_suppression_list_file(restored_copy))
        )
        classifications = LocalClassificationStore(data_dir)
        parse = settings.parse
        runner = ProcessPoolParseRunner(
            workers=parse.worker_count(os.cpu_count()), timeout_seconds=parse.per_file_timeout_seconds
        )
        affs = AffAssignmentService(
            store=LocalParsedStore(cards_dir),
            local=local,
            suppression=suppression,
            taxonomies=taxonomies,
            classifications=classifications,
            plan_texts=PlanTextService(
                parser=DebateDocxParser(), runner=runner, store=LocalPlanTextStore(data_dir), local=local
            ),
        )
        texts = AnalyticTextService(
            parser=DebateDocxParser(), runner=runner, store=LocalAnalyticTextStore(data_dir), local=local
        )
        return LandscapeRunService(
            taxonomies=taxonomies,
            config_dir=config_dir,
            parsed_store=LocalParsedStore(cards_dir),
            local=local,
            suppression=suppression,
            classifications=classifications,
            objects=objects,
            run_log=SyncRunLog(cards_dir / SYNC_RUN_LOG_FILENAME),
            reports_dir=data_dir / LANDSCAPE_REPORTS_DIRECTORY,
            acceptances=ScanAcceptanceLog(data_dir / LANDSCAPE_DIRECTORY / SCAN_ACCEPTANCES_DIRECTORY),
            today=lambda: self.clock()().date(),
            bucket=self._evidence_bucket if with_bucket else None,
            aff_assignments=affs,
            analytic_texts=texts,
            model_stage=lambda mode, max_items: self.landscape_model_stage(
                ModelMode.REPLAY if mode is LandscapeModelMode.REPLAY else ModelMode.LIVE,
                max_items,
                parsed_dir=cards_dir,
            ),
            stale_after_days=settings.caselist.stale_after_days,
            backfile_caselists=settings.caselist.backfile_caselists,
            parser_version=None if restored_copy is None else DebateDocxParser().parser_version,
            queue_order=ReviewQueueOrdering(
                models=LocalQueueOrderModelStore(data_dir),
                parsed_store=LocalParsedStore(cards_dir),
                suppression=suppression,
            ),
        )

    def landscape_evaluation(self, *, config_dir: Path, record: bool) -> LandscapeModelEvaluationService:
        """The model stage measured against a coach's labels (`v1-e32-t07` ac4), over this machine's stores.

        It replays, or with `record` records, the same cassettes a landscape run replays, under the data
        directory, and scans every cassette of the prompt there after it has run. A breakdown
        (`v1-e32-t39`) also lists the scan's hits in the repair cassettes there, which hold the cards of
        each batch that was repaired.
        """
        from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
        from debate_core.integrations.local import FsEvidenceObjectStore
        from debate_core.integrations.local.parsed_store import LocalParsedStore
        from debate_core.integrations.models.model_mode import ModelMode

        mode = ModelMode.RECORD if record else ModelMode.REPLAY
        data_dir = self.settings.storage.data_dir
        cassettes = self._landscape_cassette_dir()
        return LandscapeModelEvaluationService(
            taxonomies=YamlTaxonomyRepository.load(config_dir),
            parsed_store=LocalParsedStore(data_dir),
            local=self._local_evidence(),
            suppression=self.local_suppression_list(),
            objects=FsEvidenceObjectStore(data_dir),
            stage=lambda max_items: self.landscape_model_stage(mode, max_items, cassette_dir=cassettes),
            cassette_texts=lambda: _texts_under(cassettes / CLASSIFY_POSITION_PROMPT_ID),
            repair_cassette_texts=lambda: _texts_under(cassettes / REPAIR_PROMPT_ID),
        )

    def landscape_model_stage(
        self,
        mode: ModelMode,
        max_items: int,
        *,
        cassette_dir: Path | None = None,
        parsed_dir: Path | None = None,
    ) -> ModelClassificationStage:
        """The landscape's model stage (`v1-e32-t07`): the prompt registry, a router for `mode`, the guard.

        The router is :func:`~debate_core.integrations.models.factory.build_model_router`'s: the fixture
        fake when `models.provider` is `fake`, and otherwise the record-and-replay router, over cassettes
        kept under `<data dir>/landscape/model-cassettes/` unless `cassette_dir` names others, with card
        texts from the parsed store under the data directory unless `parsed_dir` names a restored copy's
        (`v1-e40-t17`). Real cards'
        prompts are never committed (the data-use policy's model condition 6), so a replay of them reads
        what this machine recorded. Record and live wrap the Bedrock router, imported only then. The
        prompts are read from this checkout's `prompts/`; an installed build has none, and is refused.
        """
        from debate_core.integrations.local.parsed_store import LocalParsedStore
        from debate_core.integrations.models.factory import build_model_router
        from debate_core.integrations.models.model_mode import ModelMode
        from debate_core.integrations.models.prompt_registry import DEFAULT_PROMPT_DIRECTORY, PromptRegistry

        settings = self.settings
        root = find_repository_root()
        if root is None or not (root / DEFAULT_PROMPT_DIRECTORY).is_dir():
            raise ConfigurationError(
                "the landscape's model stage reads its prompt from prompts/ in a source checkout, and this "
                "run is not in one; run it from a checkout, or use --model-mode none",
                field="models.provider",
            )
        registry = PromptRegistry.load(root / DEFAULT_PROMPT_DIRECTORY)
        real_router = None
        if mode is not ModelMode.REPLAY and settings.models.provider is not ModelProvider.FAKE:
            # Imported here, not at module scope: only a record or live run needs the AWS SDK.
            from debate_core.integrations.bedrock import bedrock_router_factory

            real_router = bedrock_router_factory(registry)
        router = build_model_router(
            settings,
            mode=mode,
            real_router=real_router,
            repository_root=root,
            clock=_PortClock(self.clock()),
            usage_log=self.usage_log(),
            cassette_dir=cassette_dir or self._landscape_cassette_dir(),
        )
        return ModelClassificationStage(
            StructuredOutputGuard(router, registry),
            ParsedStoreCardTexts(LocalParsedStore(parsed_dir or settings.storage.data_dir)),
            max_items=max_items,
        )

    def landscape_cassettes(self) -> CassetteDirectory:
        """The landscape model cassettes on this machine, for `landscape cassettes` (`v1-e32-t34`).

        The directory :meth:`landscape_model_stage` records to and replays from by default, and
        :meth:`landscape_evaluation` scans: `<data dir>/landscape/model-cassettes/`, from `DEBATE_ENV`'s
        `storage.data_dir`. Unlike the model stage it needs no `prompts/`, so the checkout that ran the
        stage and an installed build read the same directory for the same environment.
        """
        from debate_core.integrations.models.record_replay import CassetteDirectory

        return CassetteDirectory(self._landscape_cassette_dir())

    def _landscape_cassette_dir(self) -> Path:
        from debate_core.integrations.landscape.classification_store import LANDSCAPE_DIRECTORY

        return self.settings.storage.data_dir / LANDSCAPE_DIRECTORY / MODEL_CASSETTES_DIRECTORY

    def usage_log(self) -> UsageLog:
        """This machine's model usage log, `<data dir>/usage/` (`v1-e05-t07`): what `usage` reads, and
        what every real model call a command makes is recorded in and budgeted against."""
        from debate_core.integrations.models.usage import UsageLog

        return UsageLog.for_data_dir(self.settings.storage.data_dir)

    @property
    def files_dir(self) -> Path:
        """Where `files build` and `files suggest` write by default: `<data dir>/files`."""
        return self.settings.storage.data_dir / FILES_DIRECTORY

    def file_quality(self) -> FileQualityService:
        """The built-file quality check (`v1-e33-t04`), which `files build` and `files check` both run.

        Offline: the parser `files build` writes with, this machine's blob store, and this
        environment's local copy of the suppression list. A build reaches no bucket (`v1-e33-t03`'s
        forbidden list), so the check it runs reads what the build read.
        """
        return self.singleton("file_quality", self._build_file_quality)

    def _build_file_quality(self) -> FileQualityService:
        from debate_core.integrations.local import FsSnapshotStore

        return FileQualityService(
            parser=self._docx_parser(),
            snapshots=FsSnapshotStore(self.settings.storage.data_dir),
            suppression=self.local_suppression_list(),
        )

    def file_build(self) -> FileBuildService:
        """Build one recipe into a file, its sidecar and its quality report (`v1-e33-t03`).

        Over this machine's parsed store, caselist records, blob store and local suppression list, with
        the lossless writer (`v1-e33-t02`) and :meth:`file_quality`, the one quality check this
        container wires. No bucket, no model, no network.
        """
        return self.singleton("file_build", self._build_file_build)

    def _build_file_build(self) -> FileBuildService:
        from debate_core.integrations.docx_file_writer.writer import DocxEvidenceFileWriter
        from debate_core.integrations.local import FsSnapshotStore
        from debate_core.integrations.local.parsed_store import LocalParsedStore
        from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository

        data_dir = self.settings.storage.data_dir
        parser = self._docx_parser()
        blobs = FsSnapshotStore(data_dir)
        return FileBuildService(
            parsed_store=LocalParsedStore(data_dir),
            caselists=SqliteCaselistRepository(self.database),
            suppression=self.local_suppression_list(),
            blobs=blobs,
            writer=DocxEvidenceFileWriter(snapshots=blobs, parser=parser),
            quality=self.file_quality(),
            parser_version=parser.parser_version,
            profile_version=parser.profile_version,
            files_dir=self.files_dir,
            clock=self.clock(),
        )

    def file_publish(self) -> FilePublishService:
        """Publish built files that pass their quality checks to this environment's bucket (`v1-e33-t05`).

        The gate runs :meth:`file_quality`, the check `files build` and `files check` run, over this
        machine's blob store; the recipes are looked for under :attr:`files_dir`. The bucket is
        :meth:`_evidence_bucket`, signed with the everyday evidence profile, which may write `files/`,
        and built only when a file is uploaded or looked up: a dry run builds no client. Raises
        :class:`EvidenceStoreNotConfigured` then, when this environment names no bucket.
        """
        return self.singleton("file_publish", self._build_file_publish)

    def _build_file_publish(self) -> FilePublishService:
        return FilePublishService(
            bucket=self._evidence_bucket, quality=self.file_quality(), files_dir=self.files_dir
        )

    def file_suggest(self, *, config_dir: Path) -> FileSuggestService:
        """Write a draft recipe from a landscape's most-read cards (`v1-e33-t03`).

        The landscape is :meth:`landscape_run` without a bucket, which the service runs dry; the
        resolver it pins with reads what :meth:`file_build` reads, so a draft resolves as it will build.
        """
        return self.singleton("file_suggest", lambda: self._build_file_suggest(config_dir))

    def _build_file_suggest(self, config_dir: Path) -> FileSuggestService:
        from debate_core.integrations.local.parsed_store import LocalParsedStore
        from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository

        data_dir = self.settings.storage.data_dir
        return FileSuggestService(
            landscape=self.landscape_run(config_dir=config_dir, with_bucket=False),
            parsed_store=LocalParsedStore(data_dir),
            caselists=SqliteCaselistRepository(self.database),
            suppression=self.local_suppression_list(),
            parser_version=self._docx_parser().parser_version,
            files_dir=self.files_dir,
        )

    def _docx_parser(self) -> DebateDocxParser:
        """One E31 parser for the file builder's services: the writer and the check read alike."""
        from debate_core.integrations.docx_parser import DebateDocxParser

        return self.singleton("docx_parser", DebateDocxParser)

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
        from debate_core.integrations.docx_parser import DebateDocxParser
        from debate_core.integrations.local.parsed_store import LocalParsedStore

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
            card_placer=self.caselist_card_stats().placer,
            failure_rate_threshold=parse.failure_rate_threshold,
            failure_rate_minimum_sources=parse.failure_rate_minimum_sources,
            # Bucket mode (`v1-e40-t04`): raw sources a restored copy lacks come from the bucket.
            fetch_missing=self.run_state().fetch_sources if self._in_bucket_mode else None,
        )

    def parsed_publisher(self) -> ParsedStorePublisher:
        """Build the copy of the parsed card store to this environment's bucket (`v1-e31-t06`).

        Raises :class:`EvidenceStoreNotConfigured` when this environment names no bucket.
        """
        return self.singleton("parsed_publisher", self._build_parsed_publisher)

    def _build_parsed_publisher(self) -> ParsedStorePublisher:
        from debate_core.integrations.local import FsEvidenceObjectStore

        local = FsEvidenceObjectStore(self.settings.storage.data_dir, subdirectory=PARSED_DIRECTORY)
        return ParsedStorePublisher(
            local=local,
            local_path_for=local.path_for,
            remote=self._evidence_bucket(),
            suppression=self.suppression_list(),
            evidence=self._local_evidence(),
        )

    def search_index_build(
        self, *, event_for_caselist: Callable[[str], Event | None]
    ) -> SearchIndexBuildService:
        """Build the student search pilot's index builder over this machine's store (`v1-e39-t02`).

        Offline, like `caselist parse` without `--publish`: the local parsed store, the local caselist
        records and this environment's local copy of the suppression list. `event_for_caselist` is the
        command's table, for the reason :meth:`caselist_sync` gives.
        """
        return self.singleton(
            "search_index_build", lambda: self._build_search_index_build(event_for_caselist)
        )

    def _build_search_index_build(
        self, event_for_caselist: Callable[[str], Event | None]
    ) -> SearchIndexBuildService:
        from debate_core.application.caselist.manifest import read_manifest_lines
        from debate_core.integrations.docx_parser import DebateDocxParser
        from debate_core.integrations.local.parsed_store import LocalParsedStore
        from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
        from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository

        return SearchIndexBuildService(
            parsed_store=LocalParsedStore(self.settings.storage.data_dir),
            caselists=SqliteCaselistRepository(self.database),
            suppression=self.local_suppression_list(),
            writer=SqliteSearchIndexWriter(),
            parser_version=DebateDocxParser().parser_version,
            event_for_caselist=event_for_caselist,
            release_manifest_lines=lambda key: read_manifest_lines(self.evidence_object_path(key)),
        )

    def search_index_publish(self) -> SearchIndexPublishService:
        """Build the publish of a built index to this environment's bucket (`v1-e39-t02`).

        Signed with the everyday evidence profile, which may write `reports/`. Raises
        :class:`EvidenceStoreNotConfigured` when this environment names no bucket. Its shrink guard's
        share is `caselist.search_index_minimum_share_percent`, for `tub index publish` and the weekly
        stage alike, which publishes through this same service (`v1-e39-t14`).
        """
        return self.singleton("search_index_publish", self._build_search_index_publish)

    def _build_search_index_publish(self) -> SearchIndexPublishService:
        from debate_core.integrations.docx_parser import DebateDocxParser

        return SearchIndexPublishService(
            bucket=self._evidence_bucket(),
            parser_version=DebateDocxParser().parser_version,
            minimum_share_percent=self.settings.caselist.search_index_minimum_share_percent,
        )

    def search_index_prune(self) -> SearchIndexPrune:
        """Build the prune of superseded search index versions in this environment's bucket (`v1-e39-t15`).

        Two credentials, as a removal has: the everyday profile reads `current.json`, which the
        takedown role may not read, and the takedown profile (`DEBATE_REMOVAL_PROFILE`, built only when
        the prune first lists) lists and deletes versions under `reports/tub/search/`, which the
        everyday role may not. Raises :class:`EvidenceStoreNotConfigured` when this environment names
        no bucket.
        """
        return self.singleton(
            "search_index_prune",
            lambda: SearchIndexPrune(
                pointer=self._evidence_bucket(),
                takedown=self.takedown_access,
                environment=self.settings.environment.value,
                clock=self.clock(),
            ),
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
        from debate_core.integrations.docx_parser import DebateDocxParser
        from debate_core.integrations.local.version_directories import LocalVersionDirectories

        parser_version = DebateDocxParser().parser_version
        if not bucket:
            return VersionDirectoryRetention(
                LocalVersionDirectories(self.settings.storage.data_dir), parser_version=parser_version
            )
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
            login_hint=self._s3_login_hint,
        )
        return VersionDirectoryRetention(place, parser_version=parser_version)

    def verify_manifest(self) -> VerifyManifest:
        """Build `debate-research verify` over this environment's local evidence store (`v1-e03-t06`).

        The verifier reads snapshot records from the SQLite file and their content from the blob
        store under `storage.data_dir`, through ``SnapshotService.load``: the same records and
        blobs every card on this machine was cut from. Nothing here reaches the network; a snapshot
        that is not in this data directory is a card the verifier reports as ``SNAPSHOT_MISSING``. A
        .docx's body is read in the committed format profiles (`v1-e06-t07`).
        """
        return self.singleton("verify_manifest", self._build_verify_manifest)

    def _build_verify_manifest(self) -> VerifyManifest:
        from debate_core.integrations.local import FsSnapshotStore, SqliteArticleRepository

        clock = _PortClock(self.clock())
        snapshots = SnapshotService(
            blobs=FsSnapshotStore(self.settings.storage.data_dir),
            clock=clock,
            # Verification only loads snapshots; it never mints an id. The port is required all the same.
            id_generator=_PortIdGenerator(),
        )
        articles = SqliteArticleRepository(self.database)
        return VerifyManifest(
            verifier=EvidenceVerifier(articles=articles, snapshots=snapshots, clock=clock),
            articles=articles,
            # A .docx's body is read in its cards' format profile (`v1-e06-t07`); loaded only for one.
            format_profiles=self.format_profiles,
        )

    def article_fetch(self) -> ArticleFetch:
        """Build `debate-research fetch` over the polite HTTP fetcher and this data directory (`v1-e04-t06`).

        ArticleService gets :class:`~debate_core.integrations.http_fetcher.HttpArticleFetcher` from
        `settings.http`, a content-type dispatcher over the HTML and PDF extractors with the limits in
        `settings.articles`, `settings.articles` itself, and `http.max_response_bytes` as the most
        pasted text it stores: no more than a fetch would read. Articles and snapshot records go to the
        SQLite file and the blobs to the store under `storage.data_dir`, the ones `verify` reads.

        The fetcher's transport is the network in every real run. A test that replays recorded
        responses registers its transport under `"article_fetch_transport"` before the command runs,
        and every other piece of this wiring stays as it is.
        """
        return self.singleton("article_fetch", self._build_article_fetch)

    def _build_article_fetch(self) -> ArticleFetch:
        from debate_cli import package_version
        from debate_core.integrations.html_extractor import TrafilaturaExtractor
        from debate_core.integrations.http_fetcher import HttpArticleFetcher
        from debate_core.integrations.local import FsSnapshotStore, SqliteArticleRepository
        from debate_core.integrations.pdf_extractor import PdfExtractor

        settings = self.settings
        limits = settings.articles
        clock = _PortClock(self.clock())
        ids = _PortIdGenerator()
        snapshots = SnapshotService(
            blobs=FsSnapshotStore(settings.storage.data_dir), clock=clock, id_generator=ids
        )
        fetcher = HttpArticleFetcher(
            settings.http,
            version=package_version(),
            clock=clock,
            # A test's replay transport, or None: the network. `Any`, because this module may not name
            # httpx, even for the type checker (the import contracts in the workspace root).
            transport=cast(Any, self._instances.get("article_fetch_transport")),
        )
        extractor = ContentTypeDispatcher(
            html=TrafilaturaExtractor(
                minimum_characters=limits.html_fallback_minimum_characters, max_bytes=limits.html_max_bytes
            ),
            pdf=PdfExtractor(
                max_bytes=limits.pdf_max_bytes,
                max_pages=limits.pdf_max_pages,
                max_stream_bytes=limits.pdf_max_stream_bytes,
            ),
        )
        service = ArticleService(
            articles=SqliteArticleRepository(self.database),
            snapshots=snapshots,
            fetcher=fetcher,
            extractor=extractor,
            clock=clock,
            id_generator=ids,
            settings=limits,
            max_user_text_bytes=settings.http.max_response_bytes,
        )
        return ArticleFetch(articles=service, snapshots=snapshots, connection=fetcher)

    def card_cutting(self) -> CardCutting:
        """What `debate-research cut` runs after the fetch: CardService and ExportService (`v1-e06-t06`).

        CardService gets :class:`~debate_core.application.card_selection.CardSelector` over the
        structured-output guard, the prompt registry and :meth:`card_model_router`; CitationService with
        :func:`~debate_core.integrations.crossref_doi.crossref_doi_client` over a
        :class:`~debate_core.integrations.crossref_doi.FileDoiCache` in `<data dir>/crossref/`; the
        evidence verifier; and the SQLite file and blob store under `storage.data_dir`, the ones `fetch`
        stores snapshots in and `verify` reads. ExportService renders with
        :func:`~debate_core.evidence.docx_renderer.render_cards_docx`.

        The prompts are read from the committed `prompts/`: an installed build's bundled copy
        (`scripts/stamp_build.py`), or that of the source checkout this code runs from. A run with
        neither is refused before anything is fetched, as is a format profile directory that does not
        load.

        Crossref's transport is the network in every real run. A test registers its own under
        `"crossref_transport"` before the command runs, as `fetch`'s tests do for the fetcher.
        """
        return self.singleton("card_cutting", self._build_card_cutting)

    def _build_card_cutting(self) -> CardCutting:
        from debate_cli import package_version
        from debate_core.evidence.docx_renderer import render_cards_docx
        from debate_core.integrations.crossref_doi import (
            CROSSREF_CACHE_DIRECTORY,
            FileDoiCache,
            crossref_doi_client,
        )
        from debate_core.integrations.local import (
            FsSnapshotStore,
            SqliteArticleRepository,
            SqliteCardRepository,
        )
        from debate_core.integrations.models.prompt_registry import PromptRegistry

        settings = self.settings
        profiles = self.format_profiles()
        registry = PromptRegistry.load(_committed_prompts())
        clock = _PortClock(self.clock())
        ids = _PortIdGenerator()
        snapshots = SnapshotService(
            blobs=FsSnapshotStore(settings.storage.data_dir), clock=clock, id_generator=ids
        )
        articles = SqliteArticleRepository(self.database)
        doi_client = crossref_doi_client(
            settings.http,
            settings.providers,
            version=package_version(),
            cache=FileDoiCache(settings.storage.data_dir / CROSSREF_CACHE_DIRECTORY),
            # A test's mock transport, or None: the network. `Any`, for the reason the fetcher's is.
            transport=cast(Any, self._instances.get("crossref_transport")),
        )
        cards = CardService(
            articles=articles,
            snapshots=snapshots,
            selector=CardSelector(StructuredOutputGuard(self._card_model_router(registry), registry)),
            citations=CitationService(
                articles=articles, snapshots=snapshots, edit_log=_NoCardEditsYet(), doi_metadata=doi_client
            ),
            verifier=EvidenceVerifier(articles=articles, snapshots=snapshots, clock=clock),
            cards=SqliteCardRepository(self.database),
            clock=clock,
            id_generator=ids,
        )
        export = ExportService(articles=articles, clock=clock, render_docx=render_cards_docx)
        return CardCutting(cards=cards, export=export, profiles=profiles, connection=doi_client)

    def _card_model_router(self, registry: PromptRegistry) -> ModelRouter:
        """The router `cut`'s `card.select` and `card.markup` calls go to, chosen as every model router is.

        :func:`~debate_core.integrations.models.factory.build_model_router` decides: the fixture fake
        when `models.provider` is `fake`, and otherwise the record-and-replay router in the mode
        `DEBATE_MODEL_MODE` names, replay when it names none, so a run nobody configured reaches no
        model. Its cassettes are kept in `<data dir>/cards/model-cassettes/`: they hold the numbered
        text of the articles cut, so they are this machine's data and never committed, as the
        landscape's are. Record and live wrap the Bedrock router, imported only then, behind the usage
        log and the budget (`v1-e05-t07`). A test registers its own router under `"card_model_router"`.
        """
        return self.singleton("card_model_router", lambda: self._build_card_model_router(registry))

    def _build_card_model_router(self, registry: PromptRegistry) -> ModelRouter:
        from debate_core.integrations.models.factory import build_model_router
        from debate_core.integrations.models.model_mode import ModelMode, resolve_model_mode

        settings = self.settings
        mode = resolve_model_mode(None)
        real_router = None
        if mode is not ModelMode.REPLAY and settings.models.provider is not ModelProvider.FAKE:
            # Imported here, not at module scope: only a record or live run needs the AWS SDK.
            from debate_core.integrations.bedrock import bedrock_router_factory

            real_router = bedrock_router_factory(registry)
        return build_model_router(
            settings,
            mode=mode,
            real_router=real_router,
            clock=_PortClock(self.clock()),
            usage_log=self.usage_log(),
            cassette_dir=settings.storage.data_dir / CARD_CASSETTES_DIRECTORY,
        )

    def format_profiles(self) -> dict[str, ResolvedFormatProfile]:
        """The card format profiles by name (`v1-e06-t03`), from the committed `config/format_profiles`.

        An installed build reads its bundled copy, and a source checkout the copy beside its code. A
        directory that is missing or does not load is a
        :class:`~debate_core.application.settings.ConfigurationError` naming the problem.
        """
        return self.singleton("format_profiles", _committed_format_profiles)

    def caselist_import(self) -> CaselistImportService:
        """Build the weekly-archive importer over this environment's local evidence store.

        No S3 and no bucket: an import writes to the machine it runs on, and publishing what it
        wrote is a separate, deliberate `debate-research caselist publish` (v1-e30-t05).
        """
        return self.singleton("caselist_import", self._build_caselist_import)

    def _build_caselist_import(self) -> CaselistImportService:
        from debate_core.integrations.local import FsSnapshotStore
        from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository

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
        from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository

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
        from debate_core.integrations.local.suppression_list import local_suppression_list_file

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
        return self._suppression_list_in(self.settings.storage.data_dir)

    def _suppression_list_in(self, data_dir: Path) -> RecordedSuppressionList:
        """:meth:`suppression_list` over `data_dir`'s copy: this environment's, or a restored one."""
        from debate_core.integrations.local.suppression_list import local_suppression_list_file

        bucket = self._evidence_bucket()
        return RecordedSuppressionList(
            local_suppression_list_file(data_dir),
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
        from debate_core.integrations.local import FsSnapshotStore
        from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository

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
        from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
        from debate_core.integrations.local.suppression_list import local_suppression_list_file
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
                login_hint=self._s3_login_hint,
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
            # A push leaves out the bytes `caselist publish` does not upload (v1-e30-t22), and the
            # manifests it withholds (v1-e30-t25).
            held_back=functools.partial(held_back_digests, self._local_evidence()),
            withheld_manifests=functools.partial(withheld_manifest_reason, self._local_evidence()),
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
        from debate_core.integrations.local.fs_version_store import FsEvidenceVersionStore
        from debate_core.integrations.local.suppression_list import local_removal_log_file
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
            # The landscape school views a removal left on this machine (v1-e32-t13).
            local_reports=FsEvidenceVersionStore(storage.data_dir),
            # A restored working copy holds no raw sources: what the bucket holds at the manifest's
            # digest is present, for the report stage, retention and `caselist status` alike (v1-e40-t13).
            bucket_mode=self._in_bucket_mode,
            versions=S3EvidenceVersionStore(
                bucket=str(storage.s3.bucket),
                profile=storage.s3.aws_profile,
                profile_setting=_EVERYDAY_PROFILE_SETTING,
                login_hint=self._s3_login_hint,
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
        from debate_core.integrations.local import BLOB_DIRECTORY
        from debate_core.integrations.local.fs_version_store import FsEvidenceVersionStore
        from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
        from debate_core.integrations.local.suppression_list import (
            local_removal_log_file,
            local_suppression_list_file,
        )
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
            # The data directory keyed as the bucket is, for reports/landscape/ (v1-e32-t13).
            local_reports=FsEvidenceVersionStore(data_dir),
            remote=bucket,
            # The everyday profile, which may list versions under the removable prefixes
            # (v1-e29-t06). Where that grant is not applied, the plan says they were not counted.
            remote_versions=S3EvidenceVersionStore(
                bucket=str(storage.s3.bucket),
                profile=storage.s3.aws_profile,
                profile_setting=_EVERYDAY_PROFILE_SETTING,
                login_hint=self._s3_login_hint,
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
            local_reports=FsEvidenceVersionStore(data_dir),
            inbox=self.caselist_inbox(),
            remote=bucket,
            suppression=suppression,
            local_suppression=local_suppression_list_file(data_dir),
            local_removal_log=local_removal_log_file(data_dir),
            takedown=self.takedown_access,
            clock=clock,
            environment=settings.environment.value,
            run_state=self.removal_run_state(),
            # A removal that reaches a snapshot clears its parse owed (`v1-e40-t08`); in bucket mode
            # the restored file, which the removal's save of the state files then saves.
            parse_owed=self.parse_owed(),
        )

    def parse_owed(self) -> ParseOwed:
        """The parses this machine's runs owe, in the data directory (`v1-e40-t08`).

        What `caselist status` and `caselist runs` read, and a removal clears from. The pull builds
        its own over the same file, with the bucket-mode save as it is written.
        """
        return ParseOwed(self.settings.storage.data_dir / PARSE_OWED_FILENAME)

    def removal_run_state(self) -> RunState | None:
        """The run's state a removal restores first and rewrites last, in bucket mode only (`v1-e40-t04`)."""
        return self.run_state() if self._in_bucket_mode else None

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

    def routing_file_finding(self) -> RoutingFileFinding:
        """Whether the routing file this run's settings name loads (`v1-e05-t09`).

        Asked of `doctor --routing-file`. The settings this container loads have their routing
        file validated already (:func:`validating_routing`), so a bad file is caught where loading
        them refuses it, and reported as found rather than raised. Not a service: nothing is built
        or kept.
        """
        from debate_core.integrations.models.routing_policy import RoutingFileFinding, check_routing_file

        try:
            settings = self.settings
        except RoutingConfigError as refused:
            return RoutingFileFinding.refused(refused)
        return check_routing_file(settings.models.routing_file)

    def evidence_profile_check(self) -> EvidenceProfileCheck:
        """Build the check of every evidence profile this environment is configured with (`v1-e34-t22`).

        The everyday profile, when the settings name one, the takedown profile, when
        `DEBATE_REMOVAL_PROFILE` is set, and the profile Bedrock calls are signed with,
        `models.aws_profile`, when the settings name one (`v1-e05-t08`). An environment with none,
        which is what `test` is, has nothing to check. Building the check asks nothing and reads no AWS
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
        if settings.models.aws_profile:
            configured.append(
                ConfiguredProfile(setting=MODEL_PROFILE_SETTING, name=settings.models.aws_profile)
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
        from debate_core.integrations.s3 import build_s3_client

        s3 = self.settings.storage.s3
        client = build_s3_client(
            region=s3.region,
            profile=profile,
            profile_setting=profile_setting,
            endpoint_url=s3.endpoint_url,
            ignore_configured_endpoints=self._ignores_configured_endpoints,
        )
        if self._in_bucket_mode:
            # Bucket mode (`v1-e40-t04`): every write this client sends asks the run lock first,
            # whichever adapter sends it, the takedown's included (ADR-0020 (4) 4).
            from debate_core.integrations.s3.fencing import fence_client

            fence_client(client, self.bucket_run_lock())
        return client

    def bucket_run_lock(self) -> BucketRunLock:
        """This command's lease on the bucket's run lock, `reports/sync/run-lock.json` (`v1-e40-t04`).

        One per command, on a client of its own that is never fenced: its writes are the lock's.
        Signed with the everyday profile, which a takedown also holds, because `EvidenceRemoval`
        may write nowhere but `manifests/_suppression/`. The holder is `cloud` inside an ECS task,
        which ECS marks with `ECS_CONTAINER_METADATA_URI_V4`, and `mac` anywhere else; the task is
        the last segment of that address. Raises :class:`EvidenceStoreNotConfigured` when this
        environment names no bucket.
        """
        return self.singleton("bucket_run_lock", self._build_bucket_run_lock)

    def _build_bucket_run_lock(self) -> BucketRunLock:
        from debate_core.integrations.s3 import build_s3_client
        from debate_core.integrations.s3.run_lock_object import S3LockObject

        settings = self.settings
        s3 = settings.storage.s3
        if not s3.bucket:
            raise EvidenceStoreNotConfigured(settings.environment)
        client = build_s3_client(
            region=s3.region,
            profile=s3.aws_profile,
            profile_setting=_EVERYDAY_PROFILE_SETTING,
            endpoint_url=s3.endpoint_url,
            ignore_configured_endpoints=self._ignores_configured_endpoints,
        )
        metadata = _ecs_task_metadata()
        return BucketRunLock(
            store=S3LockObject(
                bucket=str(s3.bucket),
                key=RUN_LOCK_KEY,
                client=client,
                profile=s3.aws_profile,
                profile_setting=_EVERYDAY_PROFILE_SETTING,
                login_hint=self._s3_login_hint,
            ),
            environment=settings.environment.value,
            clock=self.clock(),
            kind=HolderKind.CLOUD if metadata else HolderKind.MAC,
            task=metadata.rsplit("/", 1)[-1] if metadata else None,
        )

    def run_state(self) -> RunState:
        """This environment's run state in its bucket: the restore and the saves (`v1-e40-t04`).

        Over the bucket's everyday adapter, whose client the run lock fences in bucket mode, this
        machine's manifests and database, and the publisher's own withholding rule. Raises
        :class:`EvidenceStoreNotConfigured` when this environment names no bucket.
        """
        return self.singleton("run_state", self._build_run_state)

    def _build_run_state(self) -> RunState:
        return self._run_state_in(self.settings.storage.data_dir, self.suppression_list())

    def _run_state_in(self, data_dir: Path, suppression: SuppressionList) -> RunState:
        """:meth:`run_state` over `data_dir`: this environment's, or a copy's (`v1-e40-t06`)."""
        from debate_core.integrations.local.run_state_files import LocalRunStateFiles

        return RunState(
            bucket=self._evidence_bucket(),
            files=LocalRunStateFiles(data_dir),
            local=self._local_evidence(data_dir),
            staged=self._local_evidence,
            withheld=lambda evidence: functools.partial(withheld_manifest_reason, evidence),
            suppression=suppression,
            data_dir=data_dir,
            clock=self.clock(),
        )

    def run_state_seed(self) -> RunStateSeed:
        """`caselist seed-run-state` over this environment's bucket (`v1-e40-t04`)."""
        return self.singleton(
            "run_state_seed",
            lambda: RunStateSeed(
                lock=self.bucket_run_lock,
                state=self.run_state,
                bucket=self._evidence_bucket(),
                data_dir=self.settings.storage.data_dir,
            ),
        )

    def _home_moved_refusal(self) -> str | None:
        """What a lock held for good by the move of the run's home says to this environment (`v1-e40-t11`)."""
        moved = self.bucket_run_lock().home_moved()
        return str(moved) if moved is not None else None

    def run_home_move(self) -> RunHomeMove:
        """`caselist move-run-home`: dev's lock held for good when the run's home moves (`v1-e40-t11`)."""
        return self.singleton(
            "run_home_move",
            lambda: RunHomeMove(
                lock=self.bucket_run_lock,
                environment=self.settings.environment.value,
                build=_build_named(),
            ),
        )

    def run_state_restore(self) -> RunStateRestore:
        """`caselist restore-run-state`: a working copy restored into a directory of its own (`v1-e40-t06`).

        The run state, the suppression list and (`v1-e40-t10`) the raw sources it writes are built over
        the directory named, never over this environment's data directory, which it refuses.
        """
        return self.singleton("run_state_restore", self._build_run_state_restore)

    def _build_run_state_restore(self) -> RunStateRestore:
        from debate_core.integrations.docx_parser import DebateDocxParser

        def state_in(data_dir: Path) -> RunState:
            return self._run_state_in(data_dir, self._suppression_list_in(data_dir))

        def sources_in(data_dir: Path) -> RestoredSources:
            return RestoredSources(
                bucket=self._evidence_bucket(), local=self._local_evidence(data_dir), directory=data_dir
            )

        return RunStateRestore(
            state_in=state_in,
            suppression_in=self._suppression_list_in,
            sources_in=sources_in,
            data_dirs=self._data_dirs_a_restore_refuses(),
            parsed_version=DebateDocxParser().parser_version,
            environment=self.settings.environment.value,
            bucket=self.settings.storage.s3.bucket or "",
            build_tag=current_build_info().tag,
            clock=self.clock(),
        )

    def _data_dirs_a_restore_refuses(self) -> list[DataDirectory]:
        """This run's data directory, then dev's and prod's from their own profiles (`v1-e40-t24`).

        Dev's and prod's are read without this shell's overrides, which are the running environment's
        alone, so the running environment's appears twice when an override moves it: both are refused.
        One whose profile cannot be read is `None`, and the restore then refuses every directory.
        """
        data_dirs = [DataDirectory(self.settings.environment.value, self.settings.storage.data_dir)]
        for environment in (Environment.DEV, Environment.PROD):
            try:
                path = profile_data_dir(environment, bundled_config_root=bundled_config_root())
            except ConfigurationError:
                path = None
            data_dirs.append(DataDirectory(environment.value, path))
        return data_dirs

    def bucket_run(self) -> BucketRun:
        """What `caselist pull` does around its run for the bucket's run lock and state (`v1-e40-t04`)."""
        return self.singleton("bucket_run", self._build_bucket_run)

    def _build_bucket_run(self) -> BucketRun:
        from debate_core.integrations.docx_parser import DebateDocxParser

        bucket = bool(self.settings.storage.s3.bucket)
        return BucketRun(
            guard=self.bucket_write_guard(),
            lock=self.bucket_run_lock if bucket else None,
            state=self.run_state if bucket else None,
            parsed_version=DebateDocxParser().parser_version,
        )

    @property
    def _in_bucket_mode(self) -> bool:
        """`caselist.run_state = "bucket"` in an environment that names a bucket (`v1-e40-t04`)."""
        settings = self.settings
        return settings.caselist.run_state is RunStateMode.BUCKET and bool(settings.storage.s3.bucket)

    @property
    def _s3_login_hint(self) -> str | None:
        """What the everyday profile's S3 adapters name for a session that is not usable (`v1-e40-t28`).

        In the cloud run, its task role's cure,
        :data:`~debate_core.application.sync_runs.CLOUD_NO_SESSION_CURE`. The cloud run is told from an
        operator's hand run by what the code already knows: bucket mode (:attr:`_in_bucket_mode`), and
        an ECS task, which ECS marks with `ECS_CONTAINER_METADATA_URI_V4` in every container it starts,
        as the run lock tells its holder. Only the run task is both; the login task is not in bucket
        mode. Anything else, local mode or a bucket-mode command an operator runs on the Mac, gives
        `None`: the adapters' own `aws sso login`. The takedown profile's adapters are given none
        anywhere: `DEBATE_REMOVAL_PROFILE` is an SSO profile an operator signs in to.
        """
        return CLOUD_NO_SESSION_CURE if self._in_bucket_mode and _ecs_task_metadata() else None

    def bucket_write_guard(self) -> BucketWriteGuard:
        """What every command that writes to this environment's bucket enters first (`v1-e40-t04`).

        Bucket mode takes the lease; local mode refuses a bucket that holds a lock object (the PM's
        ruling 3(a)). An environment that names no bucket has nothing to guard.
        """
        return self.singleton(
            "bucket_write_guard",
            lambda: BucketWriteGuard(
                mode=self.settings.caselist.run_state,
                lock=self.bucket_run_lock if self.settings.storage.s3.bucket else None,
            ),
        )

    @property
    def _ignores_configured_endpoints(self) -> bool:
        """Whether botocore's own endpoint routes are ignored: in prod, always."""
        return self.settings.environment is Environment.PROD

    def _local_evidence(self, data_dir: Path | None = None) -> LocalEvidence:
        """This machine's evidence store, or (`v1-e40-t04`) the same view of a scratch directory."""
        from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore

        data_dir = self.settings.storage.data_dir if data_dir is None else data_dir
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
            login_hint=self._s3_login_hint,
            multipart_threshold_bytes=storage.s3.multipart_threshold_bytes,
        )

    def caselist_sync(self, *, event_for_caselist: Callable[[str], Event | None]) -> CaselistSyncService:
        """Build the weekly pull: the source, both importers, the publisher and the status check.

        `event_for_caselist` is the command's, not this container's: which event a caselist slug
        debates is a table `debate_cli.caselist_events` keeps for the commands, which pass it in here.

        The publisher and the status check are `None` when this environment names no bucket, which
        is what `test` is and what a half-configured installation is. The run then records its
        publish stage as skipped, with the reason, instead of failing: the archives are already on
        this machine and `caselist publish` completes them later.

        The parse stage (`v1-e34-t17`) is the pipeline `caselist parse` runs, built over the pull's
        own suppression list and, with a bucket, the parsed store's publisher. It is `None` when
        `caselist.parse_imported_sources` is off, and the run then records the stage as skipped
        with that setting's name. Landscape (`v1-e32-t05`) is `None` because it does not exist yet.

        The search index stage (`v1-e39-t09`) is `tub index build` and `tub index publish` over this
        environment's bucket, with the suppression list's two copies to reconcile first. It is wired
        in only where the environment names a bucket, because an index nothing can publish is not
        the weekly run's to build, and `caselist.refresh_search_index` is on; turned off, the run
        records the stage as skipped by that setting.

        Raises :class:`~debate_core.application.ports.caselist_source.CaselistApiDisabled` unless
        the operator has turned the API on, which is the data-use policy's E34 gate.
        """
        return self.singleton("caselist_sync", lambda: self._build_caselist_sync(event_for_caselist))

    def _build_caselist_sync(self, event_for_caselist: Callable[[str], Event | None]) -> CaselistSyncService:
        from debate_core.integrations.local import FsSnapshotStore
        from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository

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
        parse_stage = (
            PullParseStage(
                parse=self._build_caselist_parse(suppression),
                publisher=self.parsed_publisher() if settings.storage.s3.bucket else None,
            )
            if caselist.parse_imported_sources
            else None
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
            parse=parse_stage,
            # Every caselist the run follows is asked whether its store lacks this parser version's
            # directory, and parsed in full before the index stage if so (`v1-e40-t08`).
            full_parse_owed=parse_stage.full_parse_owed if parse_stage is not None else None,
            search_index=self._pull_search_index(event_for_caselist)
            if why_no_search_index_stage(
                bucket_named=bool(settings.storage.s3.bucket),
                refresh_search_index=caselist.refresh_search_index,
            )
            is None
            else None,
            search_index_turned_off=not caselist.refresh_search_index,
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
            # The cloud run's 70% warning on its ephemeral volume (`v1-e40-t03`); unset on the Mac.
            volume_warning_percent=settings.storage.volume_warning_percent,
            # Bucket mode (`v1-e40-t04`): each state file saved as it is written, and the run-state
            # bundle after a publish that confirmed everything.
            state_written=self.bucket_run().state_written(),
            after_publish=self.bucket_run().after_publish if self._in_bucket_mode else None,
            backfile_caselists=caselist.backfile_caselists,
            # A parse stage's unpublished version directory is still here for `caselist parse
            # --publish-only` in local mode; in bucket mode it goes with the run (`v1-e34-t31`).
            working_copy_outlives_the_run=not self._in_bucket_mode,
            # And in bucket mode the parsed store is the cloud run's: a parse stage that did not
            # publish it names the cloud cure, never a command run on the operator's Mac (`v1-e40-t18`).
            bucket_mode=self._in_bucket_mode,
        )

    def search_index_store_check(self) -> SearchIndexStoreCheck:
        """Build the check of every store the weekly run's search index stage would index (`v1-e34-t30`).

        The stores of `caselist.sync_caselists`, the caselists a `caselist pull` with no
        `--caselist` follows, against this machine's parsed store and the parser version this build
        runs. Whether the check applies is decided by the rule `caselist_sync` wires the stage by.
        Building it reads nothing.
        """
        return self.singleton("search_index_store_check", self._build_search_index_store_check)

    def _build_search_index_store_check(self) -> SearchIndexStoreCheck:
        from debate_core.integrations.docx_parser import DebateDocxParser
        from debate_core.integrations.local.parsed_store import LocalParsedStore

        settings = self.settings
        return SearchIndexStoreCheck(
            caselists=settings.caselist.sync_caselists,
            bucket_named=bool(settings.storage.s3.bucket),
            refresh_search_index=settings.caselist.refresh_search_index,
            parsed_store=LocalParsedStore(settings.storage.data_dir),
            parser_version=DebateDocxParser().parser_version,
        )

    def _pull_search_index(self, event_for_caselist: Callable[[str], Event | None]) -> SearchIndexRefresh:
        from debate_core.integrations.docx_parser import DebateDocxParser

        settings = self.settings
        return SearchIndexRefresh(
            builder=self.search_index_build(event_for_caselist=event_for_caselist),
            out=settings.storage.data_dir / SEARCH_INDEX_DIRECTORY,
            parser_version=DebateDocxParser().parser_version,
            publisher=self.search_index_publish(),
            bucket=self._evidence_bucket(),
            reconcile=self.suppression_list().reconcile,
            environment=settings.environment.value,
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
        """macOS Notification Centre on the operator's Mac; the alert topic in the cloud; else nothing.

        `caselist.notifier = "auto"` never notifies in the `test` environment, so no test run can
        put a banner on a developer's screen even with a profile that forgot to say `none`. `sns` is
        only ever chosen by name: the cloud run's and login's task definitions set it, with the
        topic (`v1-e40-t05`, ADR-0020 (6)).
        """
        settings = self.settings
        kind = settings.caselist.notifier
        if kind is SyncNotifierKind.NONE:
            return NullNotifier()
        if kind is SyncNotifierKind.SNS:
            from debate_core.integrations.sns import SnsNotifier

            # The settings refuse `sns` without a topic, so this is never None here.
            return SnsNotifier(
                cast(str, settings.caselist.alert_topic_arn), environment=settings.environment.value
            )
        if kind is SyncNotifierKind.AUTO and (
            settings.environment is Environment.TEST or sys.platform != "darwin"
        ):
            return NullNotifier()
        from debate_core.integrations.local.macos_notifier import MacOsNotifier

        return MacOsNotifier()

    def tub_account_administration(
        self, environment: str, user_pool_id: str, profile: str | None
    ) -> AccountAdministration:
        """The coach's `tub users` commands over the pilot's pool in `environment` (`v1-e39-t05`).

        Signed with `profile`, or `debate-<environment>-tub-accounts`: the `TubAccounts` permission
        set, which may manage accounts in its own environment's pool and append to the `tub-users`
        stream of its audit group, and nothing else (`infrastructure/modules/evidence_search`). The
        pilot reads no settings: its pool is named on the command line, and its region is the one
        ADR-0010 fixes.
        """
        return self.singleton(
            "tub_account_administration",
            lambda: self._build_tub_account_administration(environment, user_pool_id, profile),
        )

    def _build_tub_account_administration(
        self, environment: str, user_pool_id: str, profile: str | None
    ) -> AccountAdministration:
        from debate_core.integrations.cloudwatch_audit import (
            ACCOUNT_CHANGES_STREAM,
            CloudWatchAuditSink,
            build_logs_client,
        )
        from debate_core.integrations.cognito import (
            PILOT_REGION,
            CognitoAccountDirectory,
            build_cognito_admin_client,
        )

        accounts_profile = profile or f"debate-{environment}-tub-accounts"
        return AccountAdministration(
            directory=CognitoAccountDirectory(
                client=build_cognito_admin_client(profile=accounts_profile),
                user_pool_id=user_pool_id,
                profile=accounts_profile,
            ),
            audit=CloudWatchAuditSink(
                client=build_logs_client(profile=accounts_profile, region=PILOT_REGION),
                log_group=f"debate-{environment}-tub-audit",
                log_stream=ACCOUNT_CHANGES_STREAM,
                create_stream=False,
                profile=accounts_profile,
            ),
            clock=self.clock(),
        )

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
        return self.caselist_token_store_on(self.settings.caselist.token_backend)

    def caselist_token_store_on(
        self, backend: CaselistTokenBackend, *, aws_profile: str | None = None
    ) -> CaselistTokenStore:
        """The token store on `backend`, whatever `caselist.token_backend` says (`login --token-backend`).

        `aws_profile` signs the Secrets Manager backend's calls; unset, the SDK's own chain does,
        which in the cloud is the task role (ADR-0020 (5)). No other backend builds an AWS client.
        """
        from debate_core.integrations.opencaselist import CaselistTokenStore, default_secret_file

        settings = self.settings
        return CaselistTokenStore.for_settings(
            backend,
            account=settings.environment.value,
            secret_file=settings.caselist.secret_file or default_secret_file(settings.storage.data_dir),
            token_secret=lambda: self.caselist_secret(self.caselist_token_secret_id, aws_profile=aws_profile),
        )

    @property
    def caselist_token_secret_id(self) -> str:
        """`caselist.token_secret_id`, or the secret Terraform names `debate-<env>-caselist-token`."""
        settings = self.settings
        return settings.caselist.token_secret_id or f"debate-{settings.environment.value}-caselist-token"

    @property
    def caselist_password_secret_id(self) -> str:
        """`caselist.password_secret_id`, or `debate-<env>-caselist-tabroom-password` (ADR-0020 (2))."""
        settings = self.settings
        return (
            settings.caselist.password_secret_id
            or f"debate-{settings.environment.value}-caselist-tabroom-password"
        )

    def caselist_secret(self, secret_id: str, *, aws_profile: str | None = None) -> SecretText:
        """One of the two caselist secrets, by name, in `caselist.secrets_region`."""
        from debate_core.integrations import secrets_manager

        hint = f"run `aws sso login --profile {aws_profile}`" if aws_profile else None
        client = secrets_manager.build_secrets_manager_client(
            region=self.settings.caselist.secrets_region, profile=aws_profile
        )
        return secrets_manager.ManagedSecret(client, secret_id, login_hint=hint)

    def tabroom_password_secret(self, *, aws_profile: str | None = None) -> TabroomPasswordSecret:
        """The password secret, which `caselist auth set-password` writes and the login task reads."""
        from debate_core.application.caselist_login import TabroomPasswordSecret

        return TabroomPasswordSecret(
            self.caselist_secret(self.caselist_password_secret_id, aws_profile=aws_profile)
        )

    def scheduled_caselist_login(self) -> ScheduledLogin:
        """`caselist auth renew`, the login task's command: the password in, the token out (ADR-0020 (2)).

        Both secrets are read and written with the SDK's own credentials, the login task's role, and
        the token always goes to the Secrets Manager backend, whatever `caselist.token_backend` says.
        A failure goes to :meth:`sync_notifier`, which in the cloud is the alert topic (`v1-e40-t05`).
        """
        from debate_core.application.caselist_login import ScheduledLogin

        return ScheduledLogin(
            credentials=self.tabroom_password_secret(),
            session=self.opencaselist_client,
            tokens=lambda: self.caselist_token_store_on(CaselistTokenBackend.SECRETSMANAGER),
            notifier=self.sync_notifier(),
            environment=self.settings.environment.value,
        )

    def backfile_survey(self) -> BackfileSurvey:
        """`caselist backfile-survey`: what the API serves for earlier seasons, over the API client.

        Read-only (`v1-e34-t34`): listings and `HEAD` sizes, no download, no bucket, so no lock.
        """
        from debate_core.application.caselist.backfile_survey import BackfileSurvey

        return self.singleton("backfile_survey", lambda: BackfileSurvey(self.opencaselist_client()))

    def backfile_import(self, *, event_for_caselist: Callable[[str], Event | None]) -> BackfileImportService:
        """`caselist backfile-import`: one backfile caselist, imported, parsed and published (`v1-e34-t34`).

        Over the bucket's lock and state, and the very suppression list the weekly pull's importers
        read: both copies as one, and a held upload recorded in this machine's copy, which the
        everyday credential may write (the pull's rule, so that removal and holds reach a backfile
        exactly as they reach the current season). Everything comes from settings, so the same build
        runs it on the Mac and in the caselist image.
        """
        return self.singleton("backfile_import", lambda: self._build_backfile_import(event_for_caselist))

    def _build_backfile_import(
        self, event_for_caselist: Callable[[str], Event | None]
    ) -> BackfileImportService:
        from debate_core.application.caselist.backfile_import import BackfileImportService
        from debate_core.integrations.docx_parser import DebateDocxParser
        from debate_core.integrations.local import FsSnapshotStore
        from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository

        settings = self.settings
        # The E34 gate first: an installation that has not turned the API on refuses before any
        # bucket adapter is built, as the survey and the pull do.
        source = self.opencaselist_client()
        bucket = bool(settings.storage.s3.bucket)
        suppression: SuppressionList = self.local_suppression_list()
        if bucket:
            suppression = LocalFallbackSuppressionList(
                self.suppression_list(), local=self.local_suppression_list()
            )
        return BackfileImportService(
            caselist_settings=settings.caselist,
            bucket_mode=self._in_bucket_mode,
            source=source,
            importer=CaselistImportService(
                caselists=SqliteCaselistRepository(self.database),
                blobs=FsSnapshotStore(settings.storage.data_dir),
                suppression=suppression,
            ),
            local=self._local_evidence(),
            read_full_archive=self.read_full_archive,
            event_for_caselist=event_for_caselist,
            inbox=self._inbox_directory(),
            data_dir=settings.storage.data_dir,
            bucket=self._evidence_bucket if bucket else None,
            guard=self.bucket_write_guard(),
            run_state=self.run_state if bucket else None,
            seeded=(lambda: self.bucket_run_lock().bucket_is_seeded()) if bucket else None,
            home_moved=self._home_moved_refusal if bucket else None,
            publisher=self.caselist_publish if bucket else None,
            parse=lambda: self._build_caselist_parse(suppression),
            parsed_publisher=self.parsed_publisher if bucket else None,
            parsed_version=DebateDocxParser().parser_version,
            clock=self.clock(),
        )

    def openev_metadata_reimport_in_bucket(self) -> OpenEvMetadataReimportInBucket:
        """`caselist reimport-openev-metadata` in bucket mode, on the bucket's run state (`v1-e40-t34`).

        Over the command's lock and run state, `caselist publish`'s publisher, and an OpenEv importer
        that reads the suppression list's local and bucket copies as one. The importer and the delivery
        record are read only after the restore has replaced the database and the state files.
        """
        from debate_core.application.caselist.openev_metadata_reimport_in_bucket import (
            OpenEvMetadataReimportInBucket,
        )
        from debate_core.integrations.local import FsSnapshotStore
        from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository

        def importer() -> OpenEvImportService:
            return OpenEvImportService(
                caselists=SqliteCaselistRepository(self.database),
                blobs=FsSnapshotStore(self.settings.storage.data_dir),
                suppression=self.suppression_list(),
            )

        return OpenEvMetadataReimportInBucket(
            guard=self.bucket_write_guard(),
            lock=self.bucket_run_lock,
            run_state=self.run_state,
            bucket=self._evidence_bucket,
            importer=importer,
            publisher=self.caselist_publish,
            upstream_paths=self.openev_upstream_paths,
            manifest_path=self.evidence_object_path,
            clock=self.clock(),
        )

    def opencaselist_client(self) -> OpenCaselistClient:
        """The OpenCaselist API client, or the refusal this installation's settings call for.

        Raises :class:`~debate_core.application.ports.caselist_source.CaselistApiDisabled` unless
        `caselist.api_enabled` is set, before any prompt is shown or request built.
        """
        return self.singleton("opencaselist_client", self._build_opencaselist_client)

    def _build_opencaselist_client(self) -> OpenCaselistClient:
        from debate_cli import package_version
        from debate_core.integrations.opencaselist import OpenCaselistClient

        return OpenCaselistClient.from_settings(
            self.settings,
            token_store=self.caselist_token_store(),
            user_agent_version=package_version(),
            wall_clock=_PortClock(self.clock()),
        )

"""The composition root: the only place in the CLI where a service is built.

A command parses its arguments, asks the container for the service it needs, and renders what
comes back. It never constructs an adapter, never reads settings and never reaches for a global,
because the moment a command does any of those the CLI stops being replaceable by the API and the
workers, which wire the same services differently (architecture proposal §6, and
`docs/architecture/ports-and-adapters.md` for the injection pattern the services themselves use).

No service is wired yet: V1's services and their adapters arrive in E02–E08. What exists here is
the shape they slot into, and — since v1-e02-t05 — the settings they are built from.

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
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, cast

from debate_core.application.settings import Settings

__all__ = ["SERVICE_NAMES", "ServiceContainer", "Settings", "SettingsNotConfigured"]

SERVICE_NAMES: Final[tuple[str, ...]] = ()
"""Names of the services this container can build, for `debate-research doctor` to report."""


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

"""The container imports each integration inside the factory that builds it (v1-e01-t39).

Two things are held here, the PM's two conditions for that change of import timing (ruled on
2026-10-27, from v1-e01-t32's question 2):

* **Importing the container or the app loads no integration.** A fresh interpreter imports
  `debate_cli.container`, and another `debate_cli.app`, and lists the modules that are then loaded:
  none is a `debate_core.integrations` module, and none comes from a distribution one of
  `debate-core`'s extras adds (boto3, lxml, httpx and the rest, read from the installed metadata).
  So `debate-research --help` pays for none of them, and a change to one reaches only the
  commands whose factories import it, which is what `scripts/affected_tests.py` now reads.
* **An integration that fails to import still fails `ci`.** Until this task an integration that
  failed to import failed the container's own import, so every test of every command failed. Now
  it fails only the factory that imports it, so a test has to build every factory. The factories
  are found by reflection, every public method and property of
  :class:`~debate_cli.container.ServiceContainer`, never from a list kept here, and each is built
  under each settings variant below with fresh singletons. Between them those builds must import
  every integration the post-install check finds in the container
  (:func:`~debate_cli.installation.wired_integrations`), and with any one of those made to fail to
  import, a build that imports it must fail. That last check is the planted break: it is what
  shows this test is not passing through an integration it never reached.

What is kept by hand here is not a list of factories but what a factory is called with: one value,
or each of several, for each parameter name and annotation. A new factory whose parameter is not
in :data:`ARGUMENTS` fails this test, naming the parameter, rather than going unbuilt.

The test runs on every pull request (`scripts/affected_tests.py`'s always-run list), because any
change to any integration can break it.
"""

from __future__ import annotations

import builtins
import contextlib
import inspect
import itertools
import json
import subprocess
import sys
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any, Final

# boto3 is imported here, at the top, because a first import of it inside a test trips pytest-socket
# (urllib3 probes for IPv6 when it is imported), and building the AWS factories imports it.
import boto3  # noqa: F401
import botocore.loaders
import botocore.session
import pytest
from packaging.utils import canonicalize_name

from debate_cli.container import ServiceContainer, validating_routing
from debate_cli.installation import INTEGRATIONS_PACKAGE, optional_core_dependencies, wired_integrations
from debate_core.application.caselist.removal_service import TakedownNotConfigured
from debate_core.application.evidence_profiles import ConfiguredProfile
from debate_core.application.settings import (
    CaselistTokenBackend,
    ConfigurationError,
    Settings,
    load_settings,
)
from debate_core.domain.model_contracts import ModelProvider
from debate_core.integrations.models.model_mode import ModelMode

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[3]
LANDSCAPE_CONFIG: Final = REPOSITORY_ROOT / "config" / "landscape"

SETTINGS_REFUSALS: Final = (ConfigurationError, TakedownNotConfigured)
"""What a factory may raise instead of building: these settings do not allow it, and say so.

`TakedownNotConfigured` is the takedown access's own refusal when `DEBATE_REMOVAL_PROFILE` is unset
(the container's docstring, "The takedown credential")."""

CONTAINER_MECHANICS: Final = frozenset({"singleton", "override"})
"""The two public methods that are the container's own machinery: each takes a name and a service."""

EVERYDAY_PROFILE: Final = "planted-everyday"
TAKEDOWN_PROFILE: Final = "planted-takedown"
TUB_PROFILE: Final = "debate-test-tub-accounts"
"""The profile `tub users` derives for the `test` environment when `--profile` is not given."""


# --------------------------------------------------------------------------------------------
# Importing the container or the app loads no integration
# --------------------------------------------------------------------------------------------


def modules_loaded_by_importing(module: str) -> list[str]:
    """Every module a fresh interpreter has loaded once it has imported `module`."""
    probe = f"import json, sys\nimport {module}\nprint(json.dumps(sorted(sys.modules)))\n"
    completed = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True, cwd=REPOSITORY_ROOT
    )
    return json.loads(completed.stdout)


def integration_modules(loaded: list[str]) -> list[str]:
    """The `debate_core.integrations` modules in `loaded`, and those an extra of `debate-core` adds."""
    optional = {canonicalize_name(distribution) for distribution in optional_core_dependencies()}
    providers = metadata.packages_distributions()
    return [
        module
        for module in loaded
        if module == INTEGRATIONS_PACKAGE
        or module.startswith(f"{INTEGRATIONS_PACKAGE}.")
        or any(
            canonicalize_name(distribution) in optional
            for distribution in providers.get(module.split(".")[0], ())
        )
    ]


@pytest.mark.parametrize("module", ["debate_cli.container", "debate_cli.app"])
def test_importing_the_container_or_the_app_loads_no_integration(module: str) -> None:
    loaded = modules_loaded_by_importing(module)

    assert "debate_cli.container" in loaded
    assert integration_modules(loaded) == []


def test_the_integration_check_recognises_an_integration_and_an_extras_library() -> None:
    assert integration_modules(
        ["debate_core.integrations.s3", "boto3", "lxml.etree", "debate_core.application.settings", "json"]
    ) == ["debate_core.integrations.s3", "boto3", "lxml.etree"]


# --------------------------------------------------------------------------------------------
# Every factory builds, and between them they import every wired integration
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SettingsVariant:
    """One installation's settings, as overrides of the `test` profile, and what its run looks like."""

    name: str
    overrides: Mapping[str, Any]


VARIANTS: Final = (
    SettingsVariant("the test profile", {}),
    SettingsVariant(
        "the operator's Mac",
        {
            "storage": {"s3": {"bucket": "planted-evidence", "aws_profile": EVERYDAY_PROFILE}},
            "caselist": {"api_enabled": True, "notifier": "macos"},
            "models": {"provider": ModelProvider.BEDROCK.value},
            "allow_network": True,
            "removal_profile": TAKEDOWN_PROFILE,
        },
    ),
    SettingsVariant(
        "the cloud run",
        {
            "storage": {"s3": {"bucket": "planted-evidence"}},
            "caselist": {
                "api_enabled": True,
                "notifier": "sns",
                "alert_topic_arn": "arn:aws:sns:us-east-1:000000000000:planted-alerts",
                "run_state": "bucket",
            },
            "models": {"provider": ModelProvider.BEDROCK.value},
            "allow_network": True,
        },
    ),
)
"""The settings each factory is built under: between them, every branch that imports an integration."""


def arguments(tmp_path: Path) -> dict[str, tuple[object, ...]]:
    """The values a factory's parameters are built with, by `name: annotation`; each is tried in turn."""
    archive = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive, "w"):
        pass
    return {
        "source: Path": (archive,),
        "config_dir: Path": (LANDSCAPE_CONFIG,),
        "event_for_caselist: Callable[[str], Event | None]": (lambda slug: None,),
        "with_bucket: bool": (False, True),
        "bucket: bool": (False, True),
        "record: bool": (False, True),
        "mode: ModelMode": tuple(ModelMode),
        "max_items: int": (1,),
        "cassette_dir: Path | None": (None, tmp_path / "cassettes"),
        "blob_prefix: str | None": (None,),
        "key: ObjectKey": ("manifests/planted.json",),
        "profile: ConfiguredProfile": (ConfiguredProfile("storage.s3.aws_profile", EVERYDAY_PROFILE),),
        "secret_id: str": ("planted-secret",),
        "aws_profile: str | None": (None, EVERYDAY_PROFILE),
        "backend: CaselistTokenBackend": tuple(CaselistTokenBackend),
        "environment: str": ("test",),
        "user_pool_id: str": ("us-east-1_planted",),
        "profile: str | None": (None,),
    }


def factories() -> list[str]:
    """Every public method and property of the container, but its own machinery: found by reflection."""
    return sorted(
        name
        for name, member in vars(ServiceContainer).items()
        if not name.startswith("_")
        and name not in CONTAINER_MECHANICS
        and (isinstance(member, property) or inspect.isfunction(member))
    )


def calls_of(factory: str, values: Mapping[str, tuple[object, ...]]) -> list[dict[str, object]]:
    """Each set of arguments `factory` is called with: every combination of its parameters' values."""
    member = vars(ServiceContainer)[factory]
    if isinstance(member, property):
        return [{}]
    parameters = list(inspect.signature(member).parameters.values())[1:]
    choices = []
    for parameter in parameters:
        key = f"{parameter.name}: {parameter.annotation}"
        if key not in values:
            raise AssertionError(f"ServiceContainer.{factory} takes {key}; add the values to build it with")
        choices.append([(parameter.name, value) for value in values[key]])
    return [dict(combination) for combination in itertools.product(*choices)]


@dataclass
class Build:
    """One factory, called once under one variant: what it imported and how it ended."""

    variant: SettingsVariant
    factory: str
    call: dict[str, object]
    imported: set[str] = field(default_factory=set)
    failure: BaseException | None = None

    def __str__(self) -> str:
        shown = ", ".join(f"{name}={value!r}" for name, value in self.call.items())
        return f"{self.factory}({shown}) under {self.variant.name}"


def settings_for(variant: SettingsVariant, data_dir: Path) -> Settings:
    storage = {**variant.overrides.get("storage", {}), "data_dir": data_dir}
    return load_settings(environment="test", overrides={**variant.overrides, "storage": storage})


def new_container(settings: Settings) -> ServiceContainer:
    """A container with no services built yet, so each factory runs its own imports again.

    Its loader is wrapped in :func:`~debate_cli.container.validating_routing`, as the root callback
    wraps every run's, so the routing check's own import is built too.
    """
    return ServiceContainer(settings_loader=validating_routing(lambda: settings))


def build(container: ServiceContainer, factory: str, call: Mapping[str, object]) -> object:
    member = vars(ServiceContainer)[factory]
    if isinstance(member, property):
        return getattr(container, factory)
    return getattr(container, factory)(**call)


@contextlib.contextmanager
def recording_integration_imports() -> Iterator[set[str]]:
    """The integration modules each import statement run inside the block names, as the wiring check does.

    `from debate_core.integrations import secrets_manager` names `debate_core.integrations.secrets_manager`,
    as :func:`~debate_cli.installation.wired_integrations` reads it.
    """
    imported: set[str] = set()
    real_import = builtins.__import__

    def recording(
        name: str,
        globals: Mapping[str, object] | None = None,  # noqa: A002 - the signature of __import__
        locals: Mapping[str, object] | None = None,  # noqa: A002
        fromlist: tuple[str, ...] | None = (),
        level: int = 0,
    ) -> object:
        if level == 0 and (name == INTEGRATIONS_PACKAGE or name.startswith(f"{INTEGRATIONS_PACKAGE}.")):
            if name == INTEGRATIONS_PACKAGE and fromlist:
                imported.update(f"{name}.{item}" for item in fromlist)
            else:
                imported.add(name)
        return real_import(name, globals, locals, fromlist or (), level)

    builtins.__import__ = recording
    try:
        yield imported
    finally:
        builtins.__import__ = real_import


@contextlib.contextmanager
def failing_to_import(module: str) -> Iterator[None]:
    """Make every import statement that names `module` raise ImportError, as a broken integration would.

    `None` in `sys.modules` makes `import module` and `from module import x` fail even after it has
    been imported once. `from package import module` reads the package's attribute first, so that
    is hidden for the block too.
    """
    package_name, _, child = module.rpartition(".")
    package = sys.modules.get(package_name)
    absent = object()
    saved_module = sys.modules.get(module, absent)
    saved_attribute = getattr(package, child, absent) if package is not None else absent
    sys.modules[module] = None  # type: ignore[assignment]
    if saved_attribute is not absent:
        delattr(package, child)
    try:
        yield
    finally:
        if saved_module is absent:
            del sys.modules[module]
        else:
            sys.modules[module] = saved_module  # type: ignore[assignment]
        if saved_attribute is not absent:
            setattr(package, child, saved_attribute)


@pytest.fixture
def aws_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An AWS config and credentials for the profiles the variants name, so an AWS factory builds offline.

    The credentials are static and made up, here and for the default chain, so that nothing asks an
    instance metadata service or a login cache for any: pytest-socket refuses that as a network call.
    """
    profiles = (EVERYDAY_PROFILE, TAKEDOWN_PROFILE, TUB_PROFILE)
    config = tmp_path / "aws-config"
    config.write_text(
        "".join(f"[profile {name}]\nregion = us-east-1\n" for name in profiles), encoding="utf-8"
    )
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        "".join(
            f"[{name}]\naws_access_key_id = planted\naws_secret_access_key = planted\n" for name in profiles
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(credentials))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "planted")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "planted")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    for variable in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_SESSION_TOKEN", "DEBATE_REMOVAL_PROFILE"):
        monkeypatch.delenv(variable, raising=False)
    # Every boto3 session the adapters open would read botocore's service models from disk again,
    # which was most of this test's time; one loader, which caches what it has read, serves them all.
    shared = botocore.loaders.create_loader()
    monkeypatch.setattr(botocore.session, "create_loader", lambda *arguments, **keywords: shared)


def build_every_factory(tmp_path: Path) -> list[Build]:
    values = arguments(tmp_path)
    builds: list[Build] = []
    for number, variant in enumerate(VARIANTS):
        settings = settings_for(variant, tmp_path / f"data-{number}")
        for factory in factories():
            for call in calls_of(factory, values):
                done = Build(variant, factory, call)
                container = new_container(settings)
                with recording_integration_imports() as imported:
                    try:
                        build(container, factory, call)
                    except SETTINGS_REFUSALS:
                        pass  # refused by these settings, the way a run with them would be told
                    except Exception as error:  # noqa: BLE001 - every other failure is the finding
                        done.failure = error
                done.imported = imported
                builds.append(done)
    return builds


def test_every_factory_builds_and_between_them_they_import_every_wired_integration(
    tmp_path: Path, aws_config: None
) -> None:
    builds = build_every_factory(tmp_path)

    failed = [f"{done}: {type(done.failure).__name__}: {done.failure}" for done in builds if done.failure]
    assert failed == [], "\n".join(failed)
    imported = set().union(*(done.imported for done in builds))
    assert sorted(set(wired_integrations()) - imported) == [], "no factory build imports these"

    # The planted break: each wired integration in turn fails to import, and a build that imports it
    # must then fail with that ImportError. One build per integration is enough to show the test sees it.
    uncaught = []
    for module in wired_integrations():
        done = next(done for done in builds if module in done.imported)
        container = new_container(settings_for(done.variant, tmp_path / "data-blocked"))
        try:
            with failing_to_import(module):
                build(container, done.factory, done.call)
        except ImportError as error:
            if module not in str(error):
                uncaught.append(f"{module}: {done} raised {error!r}")
        else:
            uncaught.append(f"{module}: {done} built without it")
    assert uncaught == []


def test_a_parameter_with_no_values_to_build_with_fails_naming_it(tmp_path: Path) -> None:
    values = arguments(tmp_path)
    del values["config_dir: Path"]

    with pytest.raises(AssertionError, match=r"landscape_run takes config_dir: Path"):
        calls_of("landscape_run", values)


def test_the_factories_are_found_by_reflection(monkeypatch: pytest.MonkeyPatch) -> None:
    def planted_factory(self: ServiceContainer) -> object:
        return object()

    monkeypatch.setattr(ServiceContainer, "planted_factory", planted_factory, raising=False)

    assert "planted_factory" in factories()
    assert {"caselist_sync", "database", "landscape_run"} <= set(factories())
    assert not CONTAINER_MECHANICS & set(factories())

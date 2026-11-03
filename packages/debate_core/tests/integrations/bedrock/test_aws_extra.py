"""boto3 is the `aws` extra, and choosing Bedrock without it says which extra to install (ac4, as amended).

Amended by the PM, 2026-10-17: boto3 is already `debate-core[aws]`, which the CLI depends on, so the
adapter uses that extra rather than a second one for the same package. These tests read the
committed lockfile, which is what `uv sync` installs from, and stand in for a missing boto3 by
making its import fail; none installs or uninstalls anything.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from debate_core.application.settings import ConfigurationError, Settings, load_settings
from debate_core.integrations.bedrock import AWS_EXTRA, BedrockNotInstalledError, bedrock_model_router
from debate_core.integrations.models import RecordReplayModelRouter, build_model_router

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
AWS_SDK = ("boto3", "botocore")


def _locked_packages() -> dict[str, dict[str, Any]]:
    lock = tomllib.loads((REPOSITORY_ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {package["name"]: package for package in lock["package"]}


def _closure(packages: dict[str, dict[str, Any]], roots: list[str]) -> set[str]:
    """Every package installing `roots` brings in, by the lockfile's dependency lists."""
    seen: set[str] = set()
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        pending.extend(dependency["name"] for dependency in packages[name].get("dependencies", []))
    return seen


def test_debate_core_without_the_aws_extra_installs_no_aws_sdk() -> None:
    packages = _locked_packages()

    installed = _closure(packages, ["debate-core"])

    assert installed.isdisjoint(AWS_SDK), sorted(installed & set(AWS_SDK))
    assert "pydantic" in installed  # the walk did reach the base dependencies


def test_the_aws_extra_is_what_brings_boto3() -> None:
    packages = _locked_packages()
    extra = [dependency["name"] for dependency in packages["debate-core"]["optional-dependencies"]["aws"]]

    assert set(AWS_SDK) <= _closure(packages, extra)


def test_the_extra_the_error_names_is_the_one_that_exists() -> None:
    declared = tomllib.loads(
        (REPOSITORY_ROOT / "packages/debate_core/pyproject.toml").read_text(encoding="utf-8")
    )

    assert AWS_EXTRA == "debate-core[aws]"
    assert any(spec.startswith("boto3") for spec in declared["project"]["optional-dependencies"]["aws"])


@pytest.fixture
def without_the_aws_sdk(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make `import boto3` and `import botocore` fail, as they do where the extra is not installed."""
    for name in AWS_SDK:
        monkeypatch.setitem(sys.modules, name, None)
    yield


def bedrock_settings(tmp_path: Path) -> Settings:
    return load_settings(
        environment="test", overrides={"models": {"provider": "bedrock"}}, env_file=tmp_path / "no.env"
    )


@pytest.mark.parametrize("mode", ["record", "live"])
def test_selecting_bedrock_without_the_extra_is_a_configuration_error_naming_it(
    mode: str, tmp_path: Path, without_the_aws_sdk: None
) -> None:
    with pytest.raises(BedrockNotInstalledError) as raised:
        build_model_router(
            bedrock_settings(tmp_path), mode=mode, environ={}, real_router=bedrock_model_router
        )

    assert isinstance(raised.value, ConfigurationError)
    assert raised.value.field == "models.provider"
    assert "debate-core[aws]" in str(raised.value)


def test_replaying_bedrock_cassettes_needs_no_aws_sdk(tmp_path: Path, without_the_aws_sdk: None) -> None:
    """Replay never builds the real router, so a student without AWS can still run on cassettes."""
    router = build_model_router(
        bedrock_settings(tmp_path),
        mode="replay",
        environ={},
        real_router=bedrock_model_router,
        repository_root=REPOSITORY_ROOT,
    )

    assert isinstance(router, RecordReplayModelRouter)


def test_the_adapter_package_imports_with_no_aws_sdk_installed() -> None:
    """In a fresh interpreter without boto3, the package still loads, and says what to install."""
    script = (
        "import sys\n"
        "sys.modules['boto3'] = None\n"
        "sys.modules['botocore'] = None\n"
        "import debate_core.integrations.bedrock as bedrock\n"
        "try:\n"
        "    bedrock.require_aws_sdk()\n"
        "except bedrock.BedrockNotInstalledError as error:\n"
        "    print(error)\n"
    )
    environment = {key: value for key, value in os.environ.items() if not key.startswith("AWS_")}

    result = subprocess.run(  # noqa: S603 - this interpreter, a fixed script
        [sys.executable, "-c", script], capture_output=True, text=True, check=True, env=environment
    )

    assert "debate-core[aws]" in result.stdout

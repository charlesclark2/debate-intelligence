"""`debate-research store` against a real evidence bucket, as `validate-dev` runs it.

The read-only half of the command, pointed at an environment that has actually been applied. It
answers the question the unit suite cannot: that the bucket named in `config/profiles/<env>.toml`
exists, that this machine's SSO session can list the documented prefixes in it, and that a plan
against it comes back clean — which together are what "the evidence store works in dev" means
before a `dev` → `main` promotion (docs/process/branching-and-environments.md).

**Nothing here writes.** `store ls` reads and `store sync --dry-run` plans; neither issues a
`PutObject`, which is the property `packages/debate_core/tests/application/test_evidence_sync.py`
pins down at the wire level. Running this against prod is therefore safe and is the check an
operator repeats after a prod apply. Publishing evidence is a deliberate `--apply`, by a person,
under docs/guides/evidence-store-cli.md.

It runs only when it is told which environment to check, so a default `pytest` run collects it and
skips it:

    STORE_SMOKE_ENV=dev AWS_PROFILE= uv run pytest tests/smoke/test_store_cli.py -m dev

The default pytest options exclude `live` and disable sockets for the whole suite; the
`enable_socket` marker on each test below is what lets these, and only these, reach AWS. The
credentials come from the environment's own SSO profile, which the operator refreshes with
`aws sso login --profile debate-dev-evidence` first; an expired one fails these checks with that
same line rather than a traceback.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode

runner = CliRunner()

STORE_ENVIRONMENT = os.environ.get("STORE_SMOKE_ENV", "").strip()

#: What `store ls` is asked for when it is asked for one prefix. Present in both environments from
#: the first publish, and cheap to list even once the corpus is whole.
MANIFEST_PREFIX = "manifests/"


def _skip_unless_targeted(environment: str) -> None:
    if not STORE_ENVIRONMENT:
        pytest.skip("STORE_SMOKE_ENV is not set: no deployed evidence store to check.")
    if environment != STORE_ENVIRONMENT:
        pytest.skip(f"STORE_SMOKE_ENV is {STORE_ENVIRONMENT!r}, not {environment!r}.")


@pytest.fixture
def targeted_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Run the CLI against the environment named by `STORE_SMOKE_ENV`, and nothing else."""
    monkeypatch.setenv("DEBATE_ENV", STORE_ENVIRONMENT)
    yield STORE_ENVIRONMENT


def _envelope(result: Result) -> dict[str, Any]:
    """The one JSON object the run put on stdout, or a failure naming what it printed instead."""
    lines = result.stdout.splitlines()
    if len(lines) != 1:
        pytest.fail(f"expected one line of JSON on stdout; got {lines!r}\nstderr: {result.stderr}")
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def _require_success(result: Result, what: str) -> dict[str, Any]:
    """Report a failed check as a failure of the environment, with the reason the CLI gave."""
    envelope = _envelope(result)
    if result.exit_code != ExitCode.OK:
        error = envelope.get("error") or {}
        pytest.fail(
            f"{what} failed against {STORE_ENVIRONMENT}: "
            f"{error.get('code')}: {error.get('message')}\n{error.get('hint') or ''}"
        )
    return envelope


def _check_listing(environment: str) -> None:
    _skip_unless_targeted(environment)
    result = runner.invoke(create_app(), ["--json", "store", "ls", MANIFEST_PREFIX])
    data = _require_success(result, "`store ls`")["data"]

    assert data["environment"] == environment
    assert data["bucket"], "the environment resolved no bucket name"
    assert data["prefix"] == MANIFEST_PREFIX
    # An empty store is a legitimate answer before the backfill (v1-e30-t06) has run; what is
    # being checked is that the bucket answered at all, with a count and a byte total.
    assert data["count"] >= 0
    assert all(entry["key"].startswith(MANIFEST_PREFIX) for entry in data["objects"])


def _check_dry_run(environment: str) -> None:
    _skip_unless_targeted(environment)
    result = runner.invoke(create_app(), ["--json", "store", "sync", "--dry-run"])
    data = _require_success(result, "`store sync --dry-run`")["data"]

    assert data["environment"] == environment
    assert data["applied"] is False, "a dry run reported itself as applied"
    assert data["transferred"] == 0
    assert data["direction"] == "push"
    # Every action is always reported, so a consumer never has to tell "none" from "absent".
    assert set(data["counts"]) == {"new", "changed", "skipped", "would_delete", "mismatched"}
    assert data["counts"]["mismatched"] == 0, (
        f"content-addressed objects differ between this machine and the bucket: {data['mismatched']}"
    )


@pytest.mark.live
@pytest.mark.dev
@pytest.mark.enable_socket
def test_dev_store_lists_its_manifests(targeted_environment: str) -> None:
    _check_listing("dev")


@pytest.mark.live
@pytest.mark.dev
@pytest.mark.enable_socket
def test_dev_store_plans_a_sync_without_writing(targeted_environment: str) -> None:
    _check_dry_run("dev")


@pytest.mark.live
@pytest.mark.prod
@pytest.mark.enable_socket
def test_prod_store_lists_its_manifests(targeted_environment: str) -> None:
    _check_listing("prod")


@pytest.mark.live
@pytest.mark.prod
@pytest.mark.enable_socket
def test_prod_store_plans_a_sync_without_writing(targeted_environment: str) -> None:
    _check_dry_run("prod")

"""The recorded smoke tier: the build under test, run as a process, offline (v1-e01-t10).

These are the checks validate-dev runs against the pre-release it installed: `--version`, `doctor`,
`config show` (secrets redacted, environment selection), and `verify` on the fixture manifests of
v1-e03-t06. They run the binary through :func:`installed_cli` in tests/smoke/conftest.py, so the
same file passes against this checkout's console script on a laptop and in `ci`, and against the
installed pre-release in validate-dev, where the build must also report the commit and tag it was
installed for.

Expected values are written by hand. The tampered fixture card changes "had" to "has" in "Nobody in
the basin had planned for it.", and the data directory holding the snapshots is built into this
run's scratch directory by `build_fixture_data_dir`, the same builder the verify tests use; no
second fixture manifest exists for this tier.
"""

from __future__ import annotations

import json
import re
import secrets
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from tests.fixtures.verify.manifest_world import ALL_VERIFIED, TAMPERED, build_fixture_data_dir
from tests.smoke.installed_build import REPO_ROOT, CliRun, InstalledCli

DEV_PRERELEASE_TAG = re.compile(r"^v(?P<release>\d+\.\d+\.\d+)-dev\.(?P<build>\d+)$")


def data_of(run: CliRun) -> dict[str, Any]:
    assert run.exit_code == 0, run.output
    envelope = run.envelope()
    assert envelope["status"] == "ok", envelope
    data = envelope["data"]
    assert isinstance(data, dict)
    return data


# ------------------------------------------------------------------------------------------------
# --version: the build is the one that was asked for
# ------------------------------------------------------------------------------------------------


def test_the_build_reports_the_commit_tag_and_channel_it_was_installed_for(
    installed_cli: InstalledCli,
) -> None:
    """With DEBATE_ENV unset, so the environment is the build's own default and not the shell's."""
    build = installed_cli.build

    version = data_of(installed_cli.run("--version", "--json", env={"DEBATE_ENV": None}))

    assert version["commit"] == build.commit
    assert version["tag"] == build.tag
    assert version["channel"] == build.channel
    assert version["environment"] == "dev"
    if build.installed:
        assert build.tag is not None
        tag = DEV_PRERELEASE_TAG.fullmatch(build.tag)
        assert tag, f"{build.tag} is not a dev pre-release tag"
        assert version["version"] == f"{tag['release']}.dev{tag['build']}"
        assert version["environment_source"] == "build-channel:dev"


def test_the_human_version_line_names_the_channel(installed_cli: InstalledCli) -> None:
    run = installed_cli.run("--version")

    assert run.exit_code == 0, run.output
    assert f"{installed_cli.build.channel} channel" in run.stdout


# ------------------------------------------------------------------------------------------------
# doctor: the build runs on its own interpreter, with everything wired
# ------------------------------------------------------------------------------------------------


def test_doctor_reports_the_builds_own_interpreter_and_every_service(installed_cli: InstalledCli) -> None:
    version = data_of(installed_cli.run("--version", "--json"))["version"]

    report = data_of(installed_cli.run("--json", "doctor"))

    assert report["cli_version"] == report["core_version"] == version
    assert report["settings_configured"] is True
    assert "verify_manifest" in report["services"]
    # doctor exits 1 on a mismatch, so data_of would already have failed; this names the check.
    assert report["unicode_database_matches"] is True
    assert report["python_unicode_version"] == report["normalizer_unicode_version"]
    # The same for the wired integrations (v1-e01-t22): every one the build's composition root
    # imports was found and imported by the build itself. The S3 adapter is the one v0.1.0-dev.33
    # shipped without.
    assert report["integrations_import"] is True
    assert report["integrations_failed"] == {}
    assert "debate_core.integrations.s3" in report["integrations_wired"]
    assert "debate_core.integrations.opencaselist" in report["integrations_wired"]
    interpreter = Path(report["python_executable"])
    assert interpreter.resolve() == installed_cli.build.interpreter.resolve()
    if installed_cli.build.installed:
        assert not interpreter.resolve().is_relative_to(REPO_ROOT), "the build ran on the checkout's Python"


def test_doctor_renders_a_table_for_a_person(installed_cli: InstalledCli) -> None:
    run = installed_cli.run("doctor")

    assert run.exit_code == 0, run.output
    assert "debate-research doctor" in run.stdout
    assert "verify_manifest" in run.stdout


def test_doctor_checks_the_evidence_profiles_only_when_asked_and_fails_on_one_that_is_not_defined(
    installed_cli: InstalledCli,
) -> None:
    """`v1-e34-t22`. This harness gives the build an empty AWS config, which is what a machine
    with no AWS setup has, and `dev` names the everyday profile `debate-dev-evidence`. Plain
    `doctor` passes there, as every install and `validate-dev` need it to. With
    `--evidence-profiles` the same build fails on that profile, under the code a pull refused for
    the same reason records, naming the setting and no path. boto3 refuses the session before any
    request, so the network guard, which fails this check on any attempt, stays silent.

    The `dev` profile also names `debate-dev-bedrock` as `models.aws_profile` (`v1-e05-t08`),
    which this config does not define either. It is reported, with its own fix, and fails nothing:
    the failure names the evidence profile alone. An installed build reads that profile from its
    wheel and the checkout's script from the committed file (`v1-e01-t41`), so both report it."""
    plain = data_of(installed_cli.run("--json", "doctor"))
    assert "evidence_profiles" not in plain

    asked = installed_cli.run("--json", "doctor", "--evidence-profiles")

    assert asked.exit_code == 1, asked.output
    error = asked.envelope()["error"]
    assert isinstance(error, dict)
    assert error["code"] == "STORE_PROFILE_NOT_CONFIGURED"
    assert error["message"] == (
        "AWS profile 'debate-dev-evidence', named by storage.s3.aws_profile, is not defined in this "
        "machine's AWS config, so every command that uses it will refuse to start."
    )
    assert "storage.s3.aws_profile" in error["hint"] and "aws sso login" not in error["hint"]
    everyday = [
        {
            "setting": "storage.s3.aws_profile",
            "profile": "debate-dev-evidence",
            "defined": False,
            "session": "not_defined",
            "permission_set": None,
            "summary": "not defined in this machine's AWS config",
            "hint": error["hint"],
        }
    ]
    model = [
        {
            "setting": "models.aws_profile",
            "profile": "debate-dev-bedrock",
            "defined": False,
            "session": "not_defined",
            "permission_set": None,
            "summary": "not defined in this machine's AWS config",
            "hint": (
                "set models.aws_profile to a profile this machine's AWS config defines, or add the profile "
                "to it: docs/runbooks/bedrock-access.md lists the Bedrock profiles and how they are added. "
                "It is not an expired session, and logging in changes nothing"
            ),
        }
    ]
    assert error["details"]["evidence_profiles"] == everyday + model
    about_the_profile = f"{error['message']} {error['hint']}"
    assert str(installed_cli.home) not in about_the_profile and "/.aws" not in asked.stdout


def test_doctor_checks_the_search_index_stores_only_when_asked_and_fails_on_one_never_parsed(
    installed_cli: InstalledCli,
) -> None:
    """`v1-e34-t30`. `dev` names a bucket and keeps `caselist.refresh_search_index` on, so its weekly
    run has the search index stage, and nothing is parsed in this harness's data directory. Plain
    `doctor` passes and says nothing of it. With `--search-index` the build fails on every store the
    stage indexes, the build's own `caselist.sync_caselists` and then `openev`, naming the command
    that parses each and no path. With the setting off the check does not apply and passes.

    The caselists are read from the build under test, not written here (PM fix 2026-10-25): an
    installed pre-release carries `config/profiles/dev.toml`, which names the weekly run's caselists
    since `v1-e40-t06`, and this checkout's console script reads the same file (`v1-e01-t41`)."""
    plain = data_of(installed_cli.run("--json", "doctor"))
    assert "search_index" not in plain
    shown = data_of(installed_cli.run("--json", "config", "show"))
    caselists = list(shown["settings"]["caselist.sync_caselists"])
    stores = [*dict.fromkeys(caselists), "openev"]

    asked = installed_cli.run("--json", "doctor", "--search-index")

    assert asked.exit_code == 1, asked.output
    error = asked.envelope()["error"]
    assert isinstance(error, dict)
    assert error["code"] == "SEARCH_INDEX_STORE_NOT_READY"
    fixes = " and ".join(f"`debate-research caselist parse --caselist {store}`" for store in stores)
    assert error["hint"] == f"Run {fixes} before the next weekly run."
    found = error["details"]["search_index"]
    assert (found["applies"], found["caselists"], found["unparsed"]) == (True, caselists, stores)
    assert str(installed_cli.home) not in f"{error['message']} {error['hint']} {found}"

    turned_off = installed_cli.run(
        "--json", "doctor", "--search-index", env={"DEBATE_CASELIST__REFRESH_SEARCH_INDEX": "false"}
    )

    assert turned_off.exit_code == 0, turned_off.output
    data = turned_off.envelope()["data"]
    assert isinstance(data, dict)
    assert data["search_index"]["applies"] is False


# ------------------------------------------------------------------------------------------------
# config show: secrets never leave, and the environment decides the rest
# ------------------------------------------------------------------------------------------------

SECRET_SETTINGS = {
    "providers.semantic_scholar_api_key": "DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY",
    "providers.openalex_api_key": "DEBATE_PROVIDERS__OPENALEX_API_KEY",
    "providers.caselist_token": "DEBATE_PROVIDERS__CASELIST_TOKEN",
    "providers.contact_email": "DEBATE_PROVIDERS__CONTACT_EMAIL",
}


def test_config_show_redacts_every_secret_in_every_output_mode(installed_cli: InstalledCli) -> None:
    values = {setting: f"smoke-secret-{secrets.token_hex(12)}" for setting in SECRET_SETTINGS}
    environment = {variable: values[setting] for setting, variable in SECRET_SETTINGS.items()}

    as_json = installed_cli.run("--json", "config", "show", env=environment)
    as_table = installed_cli.run("--verbose", "config", "show", env=environment)

    report = data_of(as_json)
    for setting, variable in SECRET_SETTINGS.items():
        assert report["settings"][setting] == "***", setting
        assert report["sources"][setting] == f"env:{variable}", setting
    assert as_table.exit_code == 0, as_table.output
    for run in (as_json, as_table):
        for value in values.values():
            assert value not in run.output


def test_config_show_uses_the_scratch_data_directory_it_was_given(installed_cli: InstalledCli) -> None:
    """validate-dev never reads or writes a real data directory."""
    report = data_of(installed_cli.run("--json", "config", "show"))

    assert report["settings"]["storage.data_dir"] == str(installed_cli.data_dir)
    assert report["sources"]["storage.data_dir"] == "env:DEBATE_STORAGE__DATA_DIR"


def test_config_show_reads_the_api_gate_from_the_dev_profile_not_the_built_in_values(
    installed_cli: InstalledCli,
) -> None:
    """`v1-e01-t41`. An installed build reads the dev profile its wheel carries, and so must the
    checkout's script, run from a scratch directory, or a check can pass in `ci` on a premise the
    installed build breaks: validate-dev failed three runs on the gate the dev profile turns on. The
    value is the committed file's, which the wheel's copy is made from."""
    report = data_of(installed_cli.run("--json", "config", "show"))

    committed = tomllib.loads((REPO_ROOT / "config" / "profiles" / "dev.toml").read_text(encoding="utf-8"))
    source = report["sources"]["caselist.api_enabled"]
    assert report["settings"]["caselist.api_enabled"] is committed["caselist"]["api_enabled"]
    if installed_cli.build.installed:
        assert source.startswith("profile:") and "_bundled_config" in source, source
    else:
        assert source == f"profile:{REPO_ROOT / 'config' / 'profiles' / 'dev.toml'}"


def test_an_unset_debate_env_runs_the_build_as_dev(installed_cli: InstalledCli) -> None:
    report = data_of(installed_cli.run("--json", "config", "show", env={"DEBATE_ENV": None}))

    assert report["environment"] == "dev"
    if installed_cli.build.installed:
        assert report["sources"]["environment"] == "build-channel:dev"


def test_dev_and_prod_get_their_own_data_directory_routing_file_and_budget(
    installed_cli: InstalledCli,
) -> None:
    def settings_for(environment: str) -> dict[str, Any]:
        overrides: dict[str, str | None] = {"DEBATE_ENV": environment, "DEBATE_STORAGE__DATA_DIR": None}
        report = data_of(installed_cli.run("--json", "config", "show", env=overrides))
        assert report["environment"] == environment
        assert report["sources"]["environment"] == "env:DEBATE_ENV"
        settings: dict[str, Any] = report["settings"]
        return settings

    dev, prod = settings_for("dev"), settings_for("prod")

    assert dev["storage.data_dir"] == str(installed_cli.home / ".debate-research" / "dev")
    assert prod["storage.data_dir"] == str(installed_cli.home / ".debate-research" / "prod")
    assert Path(dev["models.routing_file"]).name == "model_routing.dev.yaml"
    assert Path(prod["models.routing_file"]).name == "model_routing.prod.yaml"
    # Dev's $2 a day is the capped sample's allowance; prod's $1.50 is the coach's $50 a month over
    # thirty days; both hold the month to that $50 (v1-e05-t15). Bundled and built in alike.
    assert (dev["models.budget_usd_daily"], prod["models.budget_usd_daily"]) == (2.0, 1.5)
    assert (dev["models.budget_usd_monthly"], prod["models.budget_usd_monthly"]) == (50.0, 50.0)
    # The profiles name each environment's Bedrock profile (v1-e05-t08), and both builds read them.
    assert (dev["models.aws_profile"], prod["models.aws_profile"]) == (
        "debate-dev-bedrock",
        "debate-prod-bedrock",
    )
    for routing in (dev["models.routing_file"], prod["models.routing_file"]):
        if installed_cli.build.installed:
            assert "_bundled_config" in routing, f"{routing} is not the configuration the build ships"
            assert not Path(routing).resolve().is_relative_to(REPO_ROOT)
        else:
            assert Path(routing).parent == REPO_ROOT / "config", f"{routing} is not this checkout's"


# ------------------------------------------------------------------------------------------------
# A model call is priced from the pricing file the build carries (v1-e05-t12)
# ------------------------------------------------------------------------------------------------

PRICED_CALL = """
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from debate_cli.build_info import settings_loader
from debate_core.domain.model_contracts import ModelPrompt, ModelResponse, ModelUsage, TaskClass
from debate_core.integrations.models import build_model_router


class Answer(BaseModel):
    ok: bool


class AnsweringRouter:
    def __init__(self, policy):
        self.policy = policy

    async def generate_structured(self, task_class, prompt, schema, params=None):
        return ModelResponse[schema](
            output=schema(ok=True),
            route=self.policy.resolve(task_class, params),
            usage=ModelUsage(input_tokens=1000, output_tokens=2000, latency_ms=5.0),
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.prompt_version,
            invoked_at=datetime.now(UTC),
        )


settings = settings_loader()()
router = build_model_router(
    settings,
    mode="live",
    environ={},
    real_router=lambda policy, *, aws_profile: AnsweringRouter(policy),
    cassette_dir=Path(sys.argv[1]),
)
prompt = ModelPrompt(prompt_id="smoke.priced-call", prompt_version="1.0.0", variables={})
asyncio.run(router.generate_structured(TaskClass.HIGH_VOLUME, prompt, Answer))
records = [
    json.loads(line)
    for day in sorted((settings.storage.data_dir / "usage").glob("*.jsonl"))
    for line in day.read_text(encoding="utf-8").splitlines()
]
print(json.dumps({"routing_file": str(settings.models.routing_file), "records": records}))
"""
"""One live-mode call through the router the build makes, with a stand-in where Bedrock would be."""


def test_a_model_call_is_priced_from_the_pricing_file_the_build_carries(installed_cli: InstalledCli) -> None:
    """`v1-e05-t12`. The build's own interpreter loads its settings as the CLI does and makes one
    high_volume call in live mode, under the dev profile's daily and monthly limits, through the
    router `build_model_router` wraps in the usage recorder and the budget guard. A stand-in answers
    in Bedrock's place with 1000 input and 2000 output tokens, so nothing leaves the machine.

    Without a pricing file beside the routing file the guard refuses the call as unpriced, which is
    what every installed build did before the stamp bundled one. An installed build reads the copy in
    its wheel, and the checkout's script the committed file; the copy is made from the committed
    file, so the expected cost is worked out from that file's price for dev's high_volume model."""
    build = installed_cli.build

    run = installed_cli.run_program([str(build.interpreter), "-c", PRICED_CALL, str(installed_cli.workdir)])

    assert run.exit_code == 0, run.output
    report = json.loads(run.stdout)
    routing = yaml.safe_load((REPO_ROOT / "config" / "model_routing.dev.yaml").read_text(encoding="utf-8"))
    model_id = routing["routes"]["high_volume"]["model_id"]
    pricing = yaml.safe_load((REPO_ROOT / "config" / "model_pricing.yaml").read_text(encoding="utf-8"))
    price = pricing["models"][model_id]
    [record] = report["records"]
    assert record["model_id"] == model_id
    assert (record["input_tokens"], record["output_tokens"]) == (1000, 2000)
    assert record["estimated_cost_usd"] == pytest.approx(
        (1000 * price["input_usd_per_1k_tokens"] + 2000 * price["output_usd_per_1k_tokens"]) / 1000
    )
    routing_file = Path(report["routing_file"])
    assert (routing_file.parent / "model_pricing.yaml").is_file()
    if build.installed:
        assert "_bundled_config" in routing_file.parts, (
            f"{routing_file} is not the configuration the build ships"
        )
        assert not routing_file.resolve().is_relative_to(REPO_ROOT)
    else:
        assert routing_file == REPO_ROOT / "config" / "model_routing.dev.yaml"


# ------------------------------------------------------------------------------------------------
# The endpoints a smoke check's stand-ins are reached through, which prod refuses (v1-e01-t21, ac3)
# ------------------------------------------------------------------------------------------------

STAND_IN_ENDPOINTS = {
    "storage.s3.endpoint_url": ("DEBATE_STORAGE__S3__ENDPOINT_URL", "http://127.0.0.1:9"),
    "caselist.api_base_url": ("DEBATE_CASELIST__API_BASE_URL", "https://127.0.0.1:9/v1"),
}


def test_config_show_reports_the_stand_in_endpoints_and_where_each_came_from(
    installed_cli: InstalledCli,
) -> None:
    unset = data_of(installed_cli.run("--json", "config", "show"))
    given = data_of(
        installed_cli.run(
            "--json",
            "config",
            "show",
            env={variable: value for variable, value in STAND_IN_ENDPOINTS.values()},
        )
    )

    assert (unset["settings"]["storage.s3.endpoint_url"], unset["sources"]["storage.s3.endpoint_url"]) == (
        None,
        "default",
    )
    assert unset["settings"]["caselist.api_base_url"] == "https://api.opencaselist.com/v1"
    for setting, (variable, value) in STAND_IN_ENDPOINTS.items():
        assert given["settings"][setting] == value, setting
        assert given["sources"][setting] == f"env:{variable}", setting


def test_prod_refuses_each_stand_in_endpoint_with_a_message_naming_the_setting(
    installed_cli: InstalledCli,
) -> None:
    """Whichever command it is: the settings are refused before anything runs, and nothing is reached."""
    for setting, (variable, value) in STAND_IN_ENDPOINTS.items():
        for command in (("config", "show"), ("caselist", "status")):
            run = installed_cli.run("--json", *command, env={"DEBATE_ENV": "prod", variable: value})

            assert run.exit_code == 1, run.output
            error = run.envelope()["error"]
            assert isinstance(error, dict)
            assert error["code"] == "CONFIGURATION_ERROR", error
            assert error["details"] == {"field": setting, "source": f"env:{variable}"}
            assert setting in error["message"] and variable in error["message"], error["message"]
            refusal = (
                "accepted only in the dev environment, never in prod"
                if setting == "storage.s3.endpoint_url"
                else "prod reaches OpenCaselist at https://api.opencaselist.com/v1 and nowhere else"
            )
            assert refusal in error["message"], error["message"]


# ------------------------------------------------------------------------------------------------
# verify: v1-e03-t06's fixture manifests against a data directory built for this run
# ------------------------------------------------------------------------------------------------


def verify(installed_cli: InstalledCli, manifest: Path, *, as_json: bool) -> CliRun:
    build_fixture_data_dir(installed_cli.data_dir)
    return installed_cli.run(*(["--json"] if as_json else []), "verify", str(manifest))


def test_verify_exits_zero_when_every_card_verifies(installed_cli: InstalledCli) -> None:
    run = verify(installed_cli, ALL_VERIFIED, as_json=True)

    report = data_of(run)
    assert [card["status"] for card in report["cards"]] == ["VERIFIED", "VERIFIED", "VERIFIED"]


def test_verify_reports_the_tampered_card_unverified_and_exits_one(installed_cli: InstalledCli) -> None:
    run = verify(installed_cli, TAMPERED, as_json=True)

    assert run.exit_code == 1, run.output
    envelope = run.envelope()
    assert envelope["status"] == "error"
    cards = envelope["error"]["details"]["cards"]  # type: ignore[index]
    assert [(card["status"], card["reason_codes"]) for card in cards] == [
        ("VERIFIED", []),
        ("VERIFIED", []),
        ("UNVERIFIED", ["TEXT_MISMATCH"]),
    ]


def test_verify_shows_a_person_the_tampered_row(installed_cli: InstalledCli) -> None:
    run = verify(installed_cli, TAMPERED, as_json=False)

    assert run.exit_code == 1, run.output
    rows = [line for line in run.stdout.splitlines() if line.startswith("│ 0CARD")]
    assert len(rows) == 3, run.stdout
    assert ["UNVERIFIED" in row for row in rows] == [False, False, True]
    assert "TEXT_MISMATCH" in rows[2]

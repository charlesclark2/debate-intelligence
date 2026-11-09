"""Tests for `scripts/stamp_build.py`: stamping a build and refusing unpublishable wheels (v1-e01-t09).

Wheels here are small zip files written by hand with the members and METADATA a real `uv build`
produces, so the checks are exercised without building anything. The stamp itself runs against a
copy of the files it edits, never the checkout the tests run in.

A stamped build carries `config/model_pricing.yaml` beside its routing files (v1-e05-t12), and the
router an installed build makes prices its calls from that copy. Those tests load the stamped
configuration as `debate_cli.build_info` hands it to `load_settings`, and put a stand-in where
Bedrock would be: no model is called. Their prices are a synthetic file's, written into the copied
checkout before the stamp, and every expected cost is worked out by hand beside it.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import zipfile
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from debate_core.application.budget import UnpricedModelError
from debate_core.application.federated_ranking import (
    FEDERATED_RANKING_CONFIG_PATH,
    load_federated_ranking_config,
)
from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.query_expansion import ARGUMENT_TAXONOMY_PATH, load_argument_taxonomy
from debate_core.application.settings import Settings, load_settings
from debate_core.domain.model_contracts import (
    EmbeddingResponse,
    ModelParams,
    ModelPrompt,
    ModelResponse,
    ModelUsage,
    RerankResponse,
    TaskClass,
)
from debate_core.integrations.discovery.feed_config import load_feed_directory
from debate_core.integrations.models import RoutingPolicy, build_model_router
from debate_core.integrations.models.prompt_registry import PromptRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import stamp_build as sb  # noqa: E402

COMMIT = "0123456789abcdef0123456789abcdef01234567"
VERSION = "0.1.0.dev3"


def info(**changes: str) -> dict[str, str]:
    values = {
        "version": VERSION,
        "tag": "v0.1.0-dev.3",
        "channel": "dev",
        "commit": COMMIT,
        "run_id": "4242",
        "built_at": "2026-09-27T12:00:00Z",
    }
    values.update(changes)
    return sb.build_info(**values)


# --------------------------------------------------------------------------------------------
# Build info
# --------------------------------------------------------------------------------------------


def test_build_info_carries_every_field() -> None:
    assert info() == {
        "version": "0.1.0.dev3",
        "tag": "v0.1.0-dev.3",
        "channel": "dev",
        "commit": COMMIT,
        "built_at": "2026-09-27T12:00:00Z",
        "run_id": "4242",
    }


def test_a_stable_build_info_names_its_plain_tag() -> None:
    assert info(version="0.1.0", tag="v0.1.0", channel="stable")["tag"] == "v0.1.0"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"version": "0.1.0-dev.3"}, "X.Y.Z or X.Y.Z.devN"),
        ({"channel": "local"}, "--channel"),
        ({"commit": "abc123"}, "40-character"),
        ({"tag": "v0.1.0-dev.4"}, "does not name version"),
    ],
)
def test_bad_build_info_is_refused(changes: dict[str, str], message: str) -> None:
    with pytest.raises(sb.StampError, match=message):
        info(**changes)


# --------------------------------------------------------------------------------------------
# Stamping a checkout
# --------------------------------------------------------------------------------------------


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """The files `stamp` reads and edits, copied from the real checkout."""
    root = tmp_path / "checkout"
    for relative in (sb.CORE_PYPROJECT, sb.CLI_PYPROJECT):
        (root / relative).parent.mkdir(parents=True)
        shutil.copyfile(REPO_ROOT / relative, root / relative)
    (root / sb.CLI_PACKAGE).mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "config", root / "config")
    shutil.copytree(REPO_ROOT / "prompts", root / "prompts")
    return root


def test_stamp_sets_both_versions_and_pins_debate_core(checkout: Path, tmp_path: Path) -> None:
    sb.stamp(checkout, info(), tmp_path / "dist")

    core = (checkout / sb.CORE_PYPROJECT).read_text(encoding="utf-8")
    cli = (checkout / sb.CLI_PYPROJECT).read_text(encoding="utf-8")
    assert 'version = "0.1.0.dev3"' in core
    assert 'version = "0.1.0.dev3"' in cli
    assert '"debate-core[aws,docx,extraction,feeds,http,opencaselist,tub]==0.1.0.dev3"' in cli


def test_stamp_writes_the_build_info_module_and_asset(checkout: Path, tmp_path: Path) -> None:
    sb.stamp(checkout, info(), tmp_path / "dist")

    module = (checkout / sb.BUILD_INFO_MODULE).read_text(encoding="utf-8")
    assert sb._stamped_build_info(module) == info()
    assert json.loads((tmp_path / "dist" / "build-info.json").read_text(encoding="utf-8")) == info()


def test_stamp_bundles_the_committed_profiles_and_routing_files(checkout: Path, tmp_path: Path) -> None:
    sb.stamp(checkout, info(), tmp_path / "dist")

    bundled = checkout / sb.BUNDLED_CONFIG / "config"
    assert sorted(
        path.relative_to(bundled).as_posix()
        for path in bundled.rglob("*")
        if path.is_file() and path.parent.name != "feeds"
    ) == [
        "argument_taxonomy.yaml",
        "daily_presets.yaml",
        "federated_ranking.yaml",
        "format_profiles/flow.yaml",
        "format_profiles/plain.yaml",
        "format_profiles/team-default.yaml",
        "model_pricing.yaml",
        "model_routing.dev.yaml",
        "model_routing.example.yaml",
        "model_routing.prod.yaml",
        "profiles/dev.toml",
        "profiles/prod.toml",
        "profiles/test.toml",
    ]
    # The E34 policy gate travels with the build.
    assert "api_enabled = true" in (bundled / "profiles" / "dev.toml").read_text(encoding="utf-8")


def test_stamp_bundles_the_taxonomy_and_ranking_table_search_reads_unchanged(
    checkout: Path, tmp_path: Path
) -> None:
    """An installed `search` expands with this taxonomy and ranks with this table (v1-e08-t09)."""
    sb.stamp(checkout, info(), tmp_path / "dist")

    for relative in (
        "config/argument_taxonomy.yaml",
        "config/federated_ranking.yaml",
        "config/daily_presets.yaml",
    ):
        bundled = checkout / sb.BUNDLED_CONFIG / relative
        assert bundled.read_bytes() == (REPO_ROOT / relative).read_bytes(), relative


def test_stamp_bundles_every_feed_list_but_no_readme(checkout: Path, tmp_path: Path) -> None:
    """The `rss` and `google_news` providers read every `config/feeds/*.yaml` (v1-e08-t09).

    The expected list is read from the committed directory, so a new topic's feed list is bundled
    without editing this test, as the prompts are.
    """
    sb.stamp(checkout, info(), tmp_path / "dist")

    committed = REPO_ROOT / "config" / "feeds"
    assert (committed / "README.md").is_file(), "the README this test expects to be left out has gone"
    expected = sorted(path.name for path in committed.glob("*.yaml"))
    assert {"health-insurance.yaml", "politics.yaml"} <= set(expected)

    bundled = checkout / sb.BUNDLED_CONFIG / "config" / "feeds"
    assert sorted(path.name for path in bundled.iterdir()) == expected
    for name in expected:
        assert (bundled / name).read_bytes() == (committed / name).read_bytes(), name


def test_the_bundled_search_configuration_loads_as_search_loads_it(checkout: Path, tmp_path: Path) -> None:
    """The container reads these three from an installed build's bundled root; each loads and checks."""
    sb.stamp(checkout, info(), tmp_path / "dist")
    root = checkout / sb.BUNDLED_CONFIG

    taxonomy = load_argument_taxonomy(root / ARGUMENT_TAXONOMY_PATH)
    assert taxonomy == load_argument_taxonomy(REPO_ROOT / ARGUMENT_TAXONOMY_PATH)
    assert "politics-da" in {argument.id for argument in taxonomy.arguments}
    ranking = load_federated_ranking_config(root / FEDERATED_RANKING_CONFIG_PATH)
    assert ranking == load_federated_ranking_config(REPO_ROOT / FEDERATED_RANKING_CONFIG_PATH)
    topics = load_feed_directory(root / "config" / "feeds")
    assert topics == load_feed_directory(REPO_ROOT / "config" / "feeds")
    assert len(topics) >= 2


@pytest.mark.parametrize(
    ("missing", "message"),
    [
        ("config/argument_taxonomy.yaml", "argument_taxonomy.yaml"),
        ("config/federated_ranking.yaml", "federated_ranking.yaml"),
        ("config/daily_presets.yaml", "daily_presets.yaml"),
        ("config/feeds", "feed lists"),
    ],
)
def test_stamp_refuses_a_checkout_without_what_search_reads(
    missing: str, message: str, checkout: Path, tmp_path: Path
) -> None:
    path = checkout / missing
    if path.is_dir():
        for feed_list in path.glob("*.yaml"):
            feed_list.unlink()
    else:
        path.unlink()

    with pytest.raises(sb.StampError, match=message):
        sb.stamp(checkout, info(), tmp_path / "dist")


def test_stamp_bundles_the_committed_prompts_and_their_lock_but_no_readme(
    checkout: Path, tmp_path: Path
) -> None:
    """`cut` loads its prompt registry from this copy in an installed build (v1-e06-t06).

    The expected list is read from the committed `prompts/` tree, every prompt file and the lock but
    no README, so a new prompt is bundled without editing this test (v1-e08-t04's CI failure).
    """
    sb.stamp(checkout, info(), tmp_path / "dist")

    committed = REPO_ROOT / "prompts"
    assert (committed / "README.md").is_file(), "the README this test expects to be left out has gone"
    expected = sorted(
        [
            path.relative_to(committed).as_posix()
            for path in committed.rglob("*.md")
            if path.is_file() and path.name != "README.md"
        ]
        + ["prompts.lock.json"]
    )
    assert {"card/select.md", "card/markup.md"} <= set(expected)

    bundled = checkout / sb.BUNDLED_CONFIG / "prompts"
    assert (
        sorted(path.relative_to(bundled).as_posix() for path in bundled.rglob("*") if path.is_file())
        == expected
    )
    for relative in expected:
        assert (bundled / relative).read_bytes() == (committed / relative).read_bytes(), relative


def test_the_bundled_prompts_load_as_the_checkouts_registry(checkout: Path, tmp_path: Path) -> None:
    sb.stamp(checkout, info(), tmp_path / "dist")

    bundled = PromptRegistry.load(checkout / sb.BUNDLED_CONFIG / "prompts").prompts
    committed = PromptRegistry.load(REPO_ROOT / "prompts").prompts
    assert [(prompt.label, prompt.body_sha256) for prompt in bundled] == [
        (prompt.label, prompt.body_sha256) for prompt in committed
    ]
    assert {"card.select@1.0.0", "card.markup@1.0.0"} <= {prompt.label for prompt in bundled}


def test_stamp_refuses_a_checkout_with_no_prompts(checkout: Path, tmp_path: Path) -> None:
    shutil.rmtree(checkout / "prompts")

    with pytest.raises(sb.StampError, match="no prompts"):
        sb.stamp(checkout, info(), tmp_path / "dist")


def test_stamp_refuses_a_pyproject_it_cannot_edit_unambiguously(checkout: Path, tmp_path: Path) -> None:
    path = checkout / sb.CLI_PYPROJECT
    original = path.read_text(encoding="utf-8")
    edited = original.replace('"debate-core[aws,docx,extraction,feeds,http,opencaselist,tub]"', '"typer"')
    assert edited != original, "the CLI's debate-core requirement changed; update this test's literal"
    path.write_text(edited)

    with pytest.raises(sb.StampError, match="unpinned debate-core"):
        sb.stamp(checkout, info(), tmp_path / "dist")


# --------------------------------------------------------------------------------------------
# Checking wheels
# --------------------------------------------------------------------------------------------


def write_wheel(
    dist: Path, distribution: str, version: str, members: dict[str, str], requires: list[str]
) -> Path:
    dist.mkdir(parents=True, exist_ok=True)
    wheel = dist / f"{distribution}-{version}-py3-none-any.whl"
    metadata = "\n".join(
        ["Metadata-Version: 2.4", f"Name: {distribution.replace('_', '-')}", f"Version: {version}"]
        + [f"Requires-Dist: {requirement}" for requirement in requires]
    )
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
        archive.writestr(f"{distribution}-{version}.dist-info/METADATA", metadata + "\n")
    return wheel


def cli_members(version: str = VERSION) -> dict[str, str]:
    members = {member: "" for member in sb.required_cli_members(REPO_ROOT)}
    members["debate_cli/_build_info.py"] = sb.render_build_info_module(info(version=version))
    members["debate_cli/app.py"] = ""
    return members


def good_dist(dist: Path) -> Path:
    write_wheel(dist, "debate_core", VERSION, {"debate_core/__init__.py": ""}, ["pydantic>=2.9"])
    write_wheel(
        dist, "debate_cli", VERSION, cli_members(), [f"debate-core[opencaselist]=={VERSION}", "typer>=0.15"]
    )
    return dist


def test_a_correct_pair_of_wheels_is_publishable(tmp_path: Path) -> None:
    assert sb.check_wheels(good_dist(tmp_path / "dist"), VERSION) == []


def test_an_extra_wheel_is_refused(tmp_path: Path) -> None:
    dist = good_dist(tmp_path / "dist")
    write_wheel(dist, "debate_api", VERSION, {}, [])

    assert any("expected exactly the wheels" in problem for problem in sb.check_wheels(dist, VERSION))


def test_an_unpinned_debate_core_is_refused(tmp_path: Path) -> None:
    dist = good_dist(tmp_path / "dist")
    write_wheel(dist, "debate_cli", VERSION, cli_members(), ["debate-core[opencaselist]", "typer>=0.15"])

    assert any("not pinned" in problem for problem in sb.check_wheels(dist, VERSION))


def test_a_wheel_without_bundled_profiles_is_refused(tmp_path: Path) -> None:
    dist = good_dist(tmp_path / "dist")
    members = cli_members()
    del members["debate_cli/_bundled_config/config/profiles/prod.toml"]
    write_wheel(dist, "debate_cli", VERSION, members, [f"debate-core=={VERSION}"])

    assert sb.check_wheels(dist, VERSION) == [
        f"debate_cli-{VERSION}-py3-none-any.whl: missing debate_cli/_bundled_config/config/profiles/prod.toml"
    ]


def test_a_wheel_without_the_bundled_pricing_file_is_refused(tmp_path: Path) -> None:
    dist = good_dist(tmp_path / "dist")
    members = cli_members()
    members.pop("debate_cli/_bundled_config/config/model_pricing.yaml", None)
    write_wheel(dist, "debate_cli", VERSION, members, [f"debate-core=={VERSION}"])

    assert sb.check_wheels(dist, VERSION) == [
        f"debate_cli-{VERSION}-py3-none-any.whl: missing debate_cli/_bundled_config/config/model_pricing.yaml"
    ]


@pytest.mark.parametrize(
    "member",
    [
        "debate_cli/_bundled_config/prompts/card/select.md",
        "debate_cli/_bundled_config/prompts/card/markup.md",
        "debate_cli/_bundled_config/config/format_profiles/team-default.yaml",
    ],
)
def test_a_wheel_without_cuts_prompts_or_its_default_format_profile_is_refused(
    member: str, tmp_path: Path
) -> None:
    dist = good_dist(tmp_path / "dist")
    members = cli_members()
    del members[member]
    write_wheel(dist, "debate_cli", VERSION, members, [f"debate-core=={VERSION}"])

    assert sb.check_wheels(dist, VERSION) == [f"debate_cli-{VERSION}-py3-none-any.whl: missing {member}"]


@pytest.mark.parametrize(
    "member",
    [
        "debate_cli/_bundled_config/config/argument_taxonomy.yaml",
        "debate_cli/_bundled_config/config/federated_ranking.yaml",
        "debate_cli/_bundled_config/config/daily_presets.yaml",
        "debate_cli/_bundled_config/config/feeds/health-insurance.yaml",
        "debate_cli/_bundled_config/config/feeds/politics.yaml",
        "debate_cli/_bundled_config/prompts/search/expand.md",
    ],
)
def test_a_wheel_without_what_search_reads_is_refused(member: str, tmp_path: Path) -> None:
    """The taxonomy, the ranking table, each committed feed list and `--expand-llm`'s prompt (v1-e08-t09)."""
    dist = good_dist(tmp_path / "dist")
    members = cli_members()
    del members[member]
    write_wheel(dist, "debate_cli", VERSION, members, [f"debate-core=={VERSION}"])

    assert sb.check_wheels(dist, VERSION) == [f"debate_cli-{VERSION}-py3-none-any.whl: missing {member}"]


def test_check_wheels_requires_a_feed_list_the_checkout_commits_after_the_wheel_was_built(
    tmp_path: Path,
) -> None:
    """The feed lists required are the checkout's own, so a new topic is required without a code edit."""
    repository = tmp_path / "checkout"
    shutil.copytree(REPO_ROOT / "config" / "feeds", repository / "config" / "feeds")
    dist = good_dist(tmp_path / "dist")
    assert sb.check_wheels(dist, VERSION, repository=repository) == []

    shutil.copyfile(
        repository / "config" / "feeds" / "politics.yaml", repository / "config" / "feeds" / "new-topic.yaml"
    )

    assert sb.check_wheels(dist, VERSION, repository=repository) == [
        f"debate_cli-{VERSION}-py3-none-any.whl: missing "
        "debate_cli/_bundled_config/config/feeds/new-topic.yaml"
    ]


def test_the_check_wheels_command_reads_the_feed_lists_of_the_checkout_it_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = tmp_path / "checkout"
    shutil.copytree(REPO_ROOT / "config" / "feeds", repository / "config" / "feeds")
    shutil.copyfile(
        repository / "config" / "feeds" / "politics.yaml", repository / "config" / "feeds" / "new-topic.yaml"
    )
    dist = good_dist(tmp_path / "dist")

    exit_code = sb.main(
        ["check-wheels", "--version", VERSION, "--dist", str(dist), "--repository", str(repository)]
    )

    assert exit_code == 1
    assert "missing debate_cli/_bundled_config/config/feeds/new-topic.yaml" in capsys.readouterr().err


def test_check_wheels_refuses_when_the_checkout_commits_no_feed_lists_to_compare(tmp_path: Path) -> None:
    """With nothing to compare with, it cannot say every feed list was bundled, so it refuses."""
    repository = tmp_path / "checkout"
    (repository / "config" / "feeds").mkdir(parents=True)

    problems = sb.check_wheels(good_dist(tmp_path / "dist"), VERSION, repository=repository)

    assert len(problems) == 1
    assert "no committed feed lists" in problems[0]


def test_a_wheel_of_what_the_stamp_bundled_passes_check_wheels(checkout: Path, tmp_path: Path) -> None:
    """The stamp and check-wheels agree: a wheel holding exactly the stamped package files passes.

    A stamp that left out a file check-wheels requires (one feed list, say) fails here, as it would
    fail the pre-release workflow.
    """
    sb.stamp(checkout, info(), tmp_path / "dist")
    package = checkout / sb.CLI_PACKAGE
    members = {
        f"debate_cli/{path.relative_to(package).as_posix()}": path.read_text(encoding="utf-8")
        for path in package.rglob("*")
        if path.is_file()
    }
    dist = tmp_path / "wheels"
    write_wheel(dist, "debate_core", VERSION, {"debate_core/__init__.py": ""}, ["pydantic>=2.9"])
    write_wheel(dist, "debate_cli", VERSION, members, [f"debate-core=={VERSION}"])

    assert sb.check_wheels(dist, VERSION, repository=checkout) == []


def test_a_version_mismatch_is_refused(tmp_path: Path) -> None:
    problems = sb.check_wheels(good_dist(tmp_path / "dist"), "0.1.0.dev4")

    assert any("METADATA says version 0.1.0.dev3, expected 0.1.0.dev4" in problem for problem in problems)


@pytest.mark.parametrize(
    "member",
    [
        "debate_cli/.env",
        "debate_cli/_bundled_config/.env.local",
        "debate_cli/secrets/anything.txt",
        "debate_cli/caselist_token",
        "debate_core/.debate-research/dev/evidence.json",
        "debate_core/store.sqlite3",
    ],
)
def test_secrets_and_local_data_are_refused(member: str, tmp_path: Path) -> None:
    dist = good_dist(tmp_path / "dist")
    members = cli_members()
    members[member] = "x"
    write_wheel(dist, "debate_cli", VERSION, members, [f"debate-core=={VERSION}"])

    assert any(member in problem for problem in sb.check_wheels(dist, VERSION))


@pytest.mark.parametrize(
    ("member", "reason"),
    [
        ("debate_core/tests/test_store.py", "inside a tests/ directory"),
        ("debate_core/fixtures/http/cassettes/feed.yaml", "inside a fixtures/ directory"),
        ("debate_cli/conftest.py", "a test module"),
        ("debate_core/evidence/test_spans.py", "a test module"),
        ("debate_core/evidence/spans_test.py", "a test module"),
        ("debate_core/round_one_aff.docx", "a debate file"),
        ("debate_core/integrations/docx_parser/samples/neg.docx", "a debate file"),
        ("debate_core/store.sqlite3-wal", "a database file"),
        ("debate_core/store.db-journal", "a database file"),
        ("debate_core/store.sqlite-shm", "a database file"),
    ],
)
def test_fixtures_test_modules_and_data_files_are_refused(member: str, reason: str, tmp_path: Path) -> None:
    """v1-e09-t06 ac1: no fixtures, test code or data files ship, as well as no secrets."""
    assert sb.forbidden_member(member) == reason

    dist = good_dist(tmp_path / "dist")
    write_wheel(dist, "debate_core", VERSION, {"debate_core/__init__.py": "", member: "x"}, ["pydantic>=2.9"])
    assert f"debate_core-{VERSION}-py3-none-any.whl: {member} is {reason}" in sb.check_wheels(dist, VERSION)


def test_ordinary_members_are_allowed() -> None:
    assert sb.forbidden_member("debate_cli/commands/config.py") is None
    assert sb.forbidden_member("debate_cli/_bundled_config/config/profiles/dev.toml") is None


@pytest.mark.parametrize(
    "member",
    [
        # The writer's own starting document, the one .docx a wheel carries.
        "debate_core/integrations/docx_file_writer/templates/base.docx",
        # Shared fakes and contract suites are code other packages' tests import, not fixtures.
        "debate_core/testing/fakes/caselist.py",
        "debate_core/testing/contracts/README.md",
        "debate_core/application/cassette_filing.py",
        "debate_core/integrations/local/migrations/0001_initial_schema.sql",
        "debate_core/retrieval/data/public_suffix_list.dat",
        "debate_core/evidence/contest_rules.py",
    ],
)
def test_package_resources_that_look_like_test_data_are_allowed(member: str) -> None:
    assert sb.forbidden_member(member) is None


# --------------------------------------------------------------------------------------------
# The pricing file a stamped build carries, and the router that prices from it (v1-e05-t12)
# --------------------------------------------------------------------------------------------

SYNTHETIC_PRICES = """\
version: 1
models:
  {model_id}:
    input_usd_per_1k_tokens: 0.003
    output_usd_per_1k_tokens: 0.007
    as_of: 2026-10-30
    source: https://pricing.example.test/bedrock
"""
"""Prices for dev's high_volume model that no committed file holds, so a cost names its file."""

INPUT_TOKENS, OUTPUT_TOKENS = 1000, 2000
SYNTHETIC_COST_USD = 0.017
"""1000 input tokens at $0.003 per 1K is $0.003; 2000 output tokens at $0.007 per 1K is $0.014."""


class Answer(BaseModel):
    ok: bool


class AnsweringRouter:
    """Stands where Bedrock would: answers every structured call, reporting the tokens it is told to."""

    def __init__(self, policy: RoutingPolicy) -> None:
        self.policy = policy
        self.calls = 0

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        self.calls += 1
        return ModelResponse[schema](
            output=schema.model_validate({"ok": True}),
            route=self.policy.resolve(task_class, params),
            usage=ModelUsage(input_tokens=INPUT_TOKENS, output_tokens=OUTPUT_TOKENS, latency_ms=5.0),
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.prompt_version,
            invoked_at=datetime.now(UTC),
        )

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        raise NotImplementedError("these tests make structured calls only")

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        raise NotImplementedError("these tests make structured calls only")


@pytest.fixture
def no_inherited_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No `DEBATE_*` variable from the shell, and the working directory a checkout: the real one."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(REPO_ROOT)
    yield


def stamped_with_synthetic_prices(checkout: Path, tmp_path: Path) -> Path:
    """Stamp `checkout` with synthetic prices for dev's high_volume model; return its bundled root."""
    route = RoutingPolicy.load(checkout / "config" / "model_routing.dev.yaml").resolve(TaskClass.HIGH_VOLUME)
    (checkout / "config" / "model_pricing.yaml").write_text(
        SYNTHETIC_PRICES.format(model_id=route.model_id), encoding="utf-8"
    )
    sb.stamp(checkout, info(), tmp_path / "dist")
    return checkout / sb.BUNDLED_CONFIG


def installed_dev_settings(bundled_root: Path, tmp_path: Path) -> Settings:
    """What an installed dev build loads (`debate_cli.build_info.settings_loader`), budgets and all."""
    return load_settings(
        overrides={"storage": {"data_dir": str(tmp_path / "data")}},
        env_file=tmp_path / "no.env",
        build_channel="dev",
        bundled_config_root=bundled_root,
    )


def live_router(settings: Settings, tmp_path: Path) -> tuple[ModelRouter, list[AnsweringRouter]]:
    """The router `settings` build in live mode, and the stand-in it was given for Bedrock."""
    stand_ins: list[AnsweringRouter] = []

    def real_router(policy: RoutingPolicy, *, aws_profile: str | None) -> ModelRouter:
        stand_ins.append(AnsweringRouter(policy))
        return stand_ins[-1]

    router = build_model_router(
        settings, mode="live", environ={}, real_router=real_router, cassette_dir=tmp_path / "cassettes"
    )
    return router, stand_ins


def one_high_volume_call(router: ModelRouter) -> None:
    prompt = ModelPrompt(prompt_id="stamp.priced-call", prompt_version="1.0.0", variables={})
    asyncio.run(router.generate_structured(TaskClass.HIGH_VOLUME, prompt, Answer))


def usage_records(settings: Settings) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for day in sorted((settings.storage.data_dir / "usage").glob("*.jsonl"))
        for line in day.read_text(encoding="utf-8").splitlines()
    ]


@pytest.mark.usefixtures("no_inherited_settings")
def test_a_stamped_build_s_router_prices_a_call_from_the_pricing_file_it_carries(
    checkout: Path, tmp_path: Path
) -> None:
    bundled_root = stamped_with_synthetic_prices(checkout, tmp_path)
    settings = installed_dev_settings(bundled_root, tmp_path)
    # The dev profile sets a daily and a monthly limit, so the call is priced before it is made too.
    assert settings.models.budget_usd_daily is not None and settings.models.budget_usd_monthly is not None
    assert settings.models.routing_file == bundled_root / "config" / "model_routing.dev.yaml"
    router, stand_ins = live_router(settings, tmp_path)

    one_high_volume_call(router)

    assert [stand_in.calls for stand_in in stand_ins] == [1]
    [record] = usage_records(settings)
    assert (record["input_tokens"], record["output_tokens"]) == (INPUT_TOKENS, OUTPUT_TOKENS)
    assert record["estimated_cost_usd"] == pytest.approx(SYNTHETIC_COST_USD)


@pytest.mark.usefixtures("no_inherited_settings")
def test_a_stamped_build_without_its_pricing_file_refuses_a_call_under_its_budget(
    checkout: Path, tmp_path: Path
) -> None:
    """Fail closed: a build whose pricing file is missing does not treat its calls as free."""
    bundled_root = stamped_with_synthetic_prices(checkout, tmp_path)
    missing = bundled_root / "config" / "model_pricing.yaml"
    missing.unlink(missing_ok=True)
    settings = installed_dev_settings(bundled_root, tmp_path)
    router, stand_ins = live_router(settings, tmp_path)

    with pytest.raises(UnpricedModelError, match="cannot be priced") as refused:
        one_high_volume_call(router)

    assert f"{missing} (not found)" in str(refused.value)
    assert [stand_in.calls for stand_in in stand_ins] == [0]
    assert usage_records(settings) == []

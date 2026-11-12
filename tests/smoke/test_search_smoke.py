"""`debate-research search` on the build under test, offline (v1-e08-t05, working agreement 5).

The recorded tier cannot reach a provider: the network guard refuses, and logs, every connection, and
a check fails on any attempt even when the command carried on. So the end-to-end check names a provider
the `dev` profile does not enable, or one it cannot configure on this machine (GovInfo, with no
api.data.gov key in the run's environment). The build then does everything a search does but call a
provider: it loads the dev profile's providers (since v1-e07-t13 OpenAlex, Crossref, the feeds over the
bundled `config/feeds/`, the Federal Register and GovInfo), expands the query with the bundled
`config/argument_taxonomy.yaml`, loads the bundled ranking table, fans out to nothing, stores the
search, and reports the provider it could not ask. A build whose
profile enables a provider it has no adapter for stops earlier, with a configuration error, which is
why the check reads the error code and not only the exit code.
"""

from __future__ import annotations

import json

from tests.smoke.installed_build import REPO_ROOT, InstalledCli

from debate_cli.exit_codes import ExitCode


def test_search_is_installed_with_its_options_and_exit_codes(installed_cli: InstalledCli) -> None:
    run = installed_cli.run("search", "--help", env={"COLUMNS": "200"})

    assert run.exit_code == 0, run.output
    for line in (
        "0  complete",
        "2  usage error",
        "3  no provider answered",
        "6  partial",
        "7  every provider answered, and nothing matched",
        "8  auto-cut short",
        "9  budget exceeded",
        "--argument",
        "--need",
        "--expand-llm",
        "--providers",
        "--auto-cut",
        "--card-format",
        "--concurrency",
        "--max-cost",
    ):
        assert line in run.stdout


def test_an_installed_build_carries_the_taxonomy_ranking_table_and_feed_lists_it_searches_with(
    installed_cli: InstalledCli,
) -> None:
    """Every feed list this checkout commits, beside the taxonomy, the table and the prompt (v1-e08-t09)."""
    feed_lists = sorted(
        f"config/feeds/{path.name}" for path in (REPO_ROOT / "config" / "feeds").glob("*.yaml")
    )
    assert "config/feeds/politics.yaml" in feed_lists
    names = [
        "config/argument_taxonomy.yaml",
        "config/federated_ranking.yaml",
        *feed_lists,
        "prompts/search/expand.md",
    ]
    probe = (
        "import json, sys\n"
        "from debate_cli.build_info import bundled_config_root\n"
        "root = bundled_config_root()\n"
        "names = sys.argv[1:]\n"
        "print(json.dumps(None if root is None else {name: (root / name).is_file() for name in names}))\n"
    )

    run = installed_cli.run_program([str(installed_cli.build.interpreter), "-c", probe, *names])

    assert run.exit_code == 0, run.output
    bundled = json.loads(run.stdout)
    if installed_cli.build.installed:
        assert bundled == dict.fromkeys(names, True)
    else:
        assert bundled is None, "the checkout's console script is not stamped: it reads the checkout's copy"


def test_search_runs_offline_and_names_the_provider_it_could_not_ask(installed_cli: InstalledCli) -> None:
    run = installed_cli.run(
        "--json",
        "search",
        "health insurance",
        "--argument",
        "politics-da",
        "--need",
        "link",
        "--providers",
        "semantic_scholar",
    )

    assert run.exit_code == ExitCode.DOMAIN_FAILURE, run.output
    error = run.envelope()["error"]
    assert isinstance(error, dict)
    assert (error["code"], error["exit_code"]) == ("NO_PROVIDER_ENABLED", 1)
    details = error["details"]
    assert isinstance(details, dict)
    assert details["results"] == []
    assert [(entry["provider"], entry["outcome"]) for entry in details["providers"]] == [
        ("semantic_scholar", "not configured")
    ]
    expansion = details["expansion"]
    assert (expansion["argument"], expansion["need"], expansion["model_requested"]) == (
        "politics-da",
        "link",
        False,
    )


def test_an_unknown_argument_exits_2_listing_the_arguments(installed_cli: InstalledCli) -> None:
    run = installed_cli.run(
        "search", "health insurance", "--argument", "nonsense-da", "--need", "link", env={"COLUMNS": "200"}
    )

    assert run.exit_code == ExitCode.USAGE_ERROR, run.output
    assert "politics-da" in run.stderr


def test_a_need_outside_the_arguments_family_exits_2_listing_its_needs(installed_cli: InstalledCli) -> None:
    """v1-e08-t08: a framework's needs are framework-good and answers; it has no uniqueness."""
    run = installed_cli.run(
        "search", "health insurance", "--argument", "util", "--need", "uniqueness", env={"COLUMNS": "200"}
    )

    assert run.exit_code == ExitCode.USAGE_ERROR, run.output
    assert "framework-good" in run.stderr
    assert "internal-link" not in run.stderr


def test_a_topic_alone_names_the_government_provider_it_could_not_ask(installed_cli: InstalledCli) -> None:
    """v1-e07-t07: `--topic` stands alone. Since v1-e07-t13 the dev profile enables both government
    providers, so the reason is GovInfo's missing key, not "not enabled in settings": the build's own
    profile enables it. The Federal Register takes no key, so asking it would leave the machine, and this
    offline tier does not. Since v1-e07-t23 the reason, named with --providers, carries its cure, and the
    message names GovInfo's state instead of "none of govinfo is enabled"."""
    run = installed_cli.run(
        "--json",
        "search",
        "health insurance",
        "--topic",
        "policy-2026-27-nhi",
        "--providers",
        "govinfo",
    )

    assert run.exit_code == ExitCode.DOMAIN_FAILURE, run.output
    error = run.envelope()["error"]
    assert isinstance(error, dict)
    assert (error["code"], error["exit_code"]) == ("NO_PROVIDER_ENABLED", 1)
    details = error["details"]
    assert isinstance(details, dict)
    govinfo = (
        "no api.data.gov key (DEBATE_PROVIDERS__API_DATA_GOV_KEY); "
        "get a free key at api.data.gov/signup to ask GovInfo"
    )
    assert [(entry["provider"], entry["outcome"], entry["reasons"]) for entry in details["providers"]] == [
        ("govinfo", "not configured", [govinfo]),
    ]
    assert error["message"] == f"no provider was asked:\n  govinfo: not configured: {govinfo}"
    assert "expansion" not in details or details["expansion"] is None


def test_an_unknown_topic_exits_2_listing_the_topics(installed_cli: InstalledCli) -> None:
    run = installed_cli.run(
        "search", "health insurance", "--topic", "policy-2025-26-nhi", env={"COLUMNS": "200"}
    )

    assert run.exit_code == ExitCode.USAGE_ERROR, run.output
    assert "policy-2026-27-nhi" in run.stderr

"""`debate-research search` on the build under test, offline (v1-e08-t05, working agreement 5).

The recorded tier cannot reach a provider: the network guard refuses, and logs, every connection, and
a check fails on any attempt even when the command carried on. So the end-to-end check names a provider
the `dev` profile does not enable. The build then does everything a search does but call a provider:
it loads the dev profile's providers (OpenAlex and the feeds, over the bundled `config/feeds/`),
expands the query with the bundled `config/argument_taxonomy.yaml`, loads the bundled ranking table,
fans out to nothing, stores the search, and reports the provider it could not ask. A build whose
profile enables a provider it has no adapter for stops earlier, with a configuration error, which is
why the check reads the error code and not only the exit code.
"""

from __future__ import annotations

import json

from tests.smoke.installed_build import InstalledCli

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
        "--argument",
        "--need",
        "--expand-llm",
        "--providers",
    ):
        assert line in run.stdout


def test_an_installed_build_carries_the_taxonomy_ranking_table_and_feed_lists_it_searches_with(
    installed_cli: InstalledCli,
) -> None:
    probe = (
        "import json\n"
        "from debate_cli.build_info import bundled_config_root\n"
        "root = bundled_config_root()\n"
        "names = ['config/argument_taxonomy.yaml', 'config/federated_ranking.yaml', "
        "'config/feeds/politics.yaml', 'prompts/search/expand.md']\n"
        "print(json.dumps(None if root is None else {name: (root / name).is_file() for name in names}))\n"
    )

    run = installed_cli.run_program([str(installed_cli.build.interpreter), "-c", probe])

    assert run.exit_code == 0, run.output
    bundled = json.loads(run.stdout)
    if installed_cli.build.installed:
        assert bundled == {
            "config/argument_taxonomy.yaml": True,
            "config/federated_ranking.yaml": True,
            "config/feeds/politics.yaml": True,
            "prompts/search/expand.md": True,
        }
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

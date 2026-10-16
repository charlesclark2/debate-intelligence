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

`plutil` and `launchctl` are macOS's. Every run of the installer here finds two stand-ins first on
its PATH, on every platform: a fake `launchctl` that keeps its state in a file, and a `plutil` over
`plistlib` that answers the verbs the installer uses as `plutil` does (`v1-e34-t24`). So the launchd
check and the reinstall, which reads the installed plist, run on Linux in CI as they do on a Mac.
Two tests stay macOS-only, because they are about the real `plutil`: the lint of the rendered
plist, and the comparison that holds the stand-in to the real one.

Nothing here loads, bootstraps or enables anything, nothing writes outside `tmp_path`, and nothing
asks the machine's own launchd anything: `HOME` is a temporary directory, the console script is a
fake that records how it was called, and `launchctl` is the fake. The one thing this suite must
never do is put a schedule on the machine it runs on.

## The profile check, and how it is proven off macOS (`v1-e34-t22`)

`install.sh --check-launchd` now also reports each configured evidence profile and fails on one
the AWS config does not define. It does that by what it already ran under launchd: the installed
wrapper's `--check`, which runs `debate-research --version` and then
`debate-research doctor --evidence-profiles`, and ends with that command's exit code. The installer
itself still only loads the one-off label, waits, prints the log and the exit code, and boots it
out.

So the part this task adds is the wrapper's `--check`, a POSIX shell script, and it is tested on
every platform, twice over: against the fake console script, to show which commands it runs, in
which order, and that the profile check's exit code is the one it ends with; and against this
checkout's real command, with an AWS config written for the test, to show a profile that is not
defined ending the check with `1` and naming its setting. The second needs no stub and reaches no
network, because boto3 refuses the session before any request. What `doctor` does with a profile
that *is* defined is `packages/debate_cli/tests/commands/test_doctor_evidence_profiles.py`.

The launchd half, the check's log, its failing exit code and the label booted out, was skipped off
macOS until `v1-e34-t24` gave it the `plutil` stand-in.

## A reinstall keeps what is installed (`v1-e34-t24`)

Over an installed agent the installer reads the installed plist: its `DEBATE_ENV` and its caselists
are kept unless an option says otherwise, a different `--env` is refused unless confirmed, and an
install that would move the agent's data directory is refused unless confirmed. Before writing
anything, a dry run included, it runs the build's `doctor --evidence-profiles` as the agent will
run it, and refuses a profile this machine's AWS config does not define.
"""

from __future__ import annotations

import json
import os
import platform
import plistlib
import re
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
    platform.system() != "Darwin", reason="about macOS's own plutil, which is not on this machine"
)


FAKE_LAUNCHCTL = '''#!@PYTHON@
"""A stand-in for launchctl: loads plists into a JSON file and runs a job the way launchd would."""
import json, os, plistlib, subprocess, sys
from pathlib import Path

state_file = Path(@STATE@)
state = json.loads(state_file.read_text()) if state_file.exists() else {}
with open(@CALLS@, "a") as calls:
    calls.write(" ".join(sys.argv[1:]) + "\\n")
command, target = sys.argv[1], sys.argv[-1]
label = target.rsplit("/", 1)[-1]

if command == "print":
    job = state.get(label)
    if job is None:
        print(f"Could not find service \\"{label}\\" in domain", file=sys.stderr)
        sys.exit(113)
    exit_code = job["last_exit_code"]
    print(f"{target} = {{")
    print(f"\\tstate = not running\\n\\truns = {job['runs']}\\n\\tlast exit code = {exit_code}\\n}}")
elif command == "bootstrap":
    plist = plistlib.loads(Path(target).read_bytes())
    state[plist["Label"]] = {
        "plist": target, "runs": 0, "last_exit_code": "(never exited)",
        "program": plist["ProgramArguments"], "environment": plist["EnvironmentVariables"],
        "cwd": plist["WorkingDirectory"],
        "stdout": plist["StandardOutPath"], "stderr": plist["StandardErrorPath"],
    }
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

PLUTIL_STAND_IN = '''#!@PYTHON@
"""A stand-in for macOS's plutil over plistlib: the verbs install.sh uses, answering as plutil does.

`-lint`; `-extract <keypath> raw`, which prints a string as it is, a boolean as true or false, an
array's length and a dictionary's keys, sorted, one to a line; `-replace` and `-insert` with
`-string`, `-bool` or `-array`; and `-remove`. A key path is keys and array indices joined by dots.
On macOS, `test_the_plutil_stand_in_answers_as_plutil_does` holds it to the real one.
"""
import plistlib, sys
from pathlib import Path

with open(@CALLS@, "a") as calls:
    calls.write(" ".join(sys.argv[1:]) + "\\n")
verb, *rest = sys.argv[1:]
named = rest[-1]
file = Path(named)


def refuse(message):
    print(f"{named}: {message}", file=sys.stderr)
    sys.exit(1)


try:
    document = plistlib.loads(file.read_bytes())
except Exception as error:
    refuse(f"the stand-in could not read it as a plist ({type(error).__name__})")
if verb == "-lint":
    print(f"{named}: OK")
    sys.exit(0)

keypath = rest[0]
*parents, last = keypath.split(".")
try:
    container = document
    for part in parents:
        container = container[int(part)] if isinstance(container, list) else container[part]
    if isinstance(container, list):
        last = int(last)
except (KeyError, IndexError, ValueError, TypeError):
    container = None

if verb == "-extract":
    if rest[1] != "raw":
        refuse(f"the stand-in answers -extract in raw only, not {rest[1]}")
    try:
        value = container[last]
    except (KeyError, IndexError, TypeError):
        refuse(f"Could not extract value, error: No value at that key path or invalid key path: {keypath}")
    if isinstance(value, bool):
        print("true" if value else "false")
    elif isinstance(value, dict):
        print("\\n".join(sorted(value)))
    elif isinstance(value, list):
        print(len(value))
    else:
        print(value)
    sys.exit(0)

if verb == "-remove":
    try:
        del container[last]
    except (KeyError, IndexError, TypeError):
        refuse(f"No value to remove at key path {keypath}")
elif verb in ("-replace", "-insert"):
    kind = rest[1]
    value = {"-string": lambda: rest[2], "-bool": lambda: rest[2].lower() in ("true", "yes", "1"),
             "-array": lambda: []}[kind]()
    if isinstance(container, list) and verb == "-insert":
        if last > len(container):
            refuse(f"Index {last} out of bounds in array at key path {keypath}")
        container.insert(last, value)
    elif isinstance(container, list):
        container[last] = value
    elif isinstance(container, dict):
        if verb == "-insert" and last in container:
            refuse(f"Value already exists at key path {keypath}")
        container[last] = value
    else:
        refuse(f"No value at key path {keypath}")
else:
    refuse(f"the stand-in does not know {verb}")
file.write_bytes(plistlib.dumps(document))
'''


def stand_ins(home: Path) -> Path:
    """The directory holding the fake `launchctl` and the `plutil` stand-in, beside the temporary
    HOME, written the first time a test asks for it. Every run of the installer here has it first
    on its PATH, so no test asks the machine's own launchd anything, even read-only."""
    directory = home.parent / "stand-ins"
    if not directory.exists():
        directory.mkdir()
        for name, template in (("launchctl", FAKE_LAUNCHCTL), ("plutil", PLUTIL_STAND_IN)):
            script = directory / name
            script.write_text(
                template.replace("@PYTHON@", sys.executable)
                .replace("@STATE@", repr(str(directory / "launchctl-state.json")))
                .replace("@CALLS@", repr(str(directory / f"{name}-calls.log"))),
                encoding="utf-8",
            )
            script.chmod(0o755)
    return directory


def plutil_calls(home: Path) -> list[str]:
    record = stand_ins(home) / "plutil-calls.log"
    return record.read_text(encoding="utf-8").splitlines() if record.exists() else []


def install(
    *arguments: str, home: Path, path_prefix: tuple[Path, ...] = ()
) -> subprocess.CompletedProcess[str]:
    """Run the installer with `HOME` pointed at a temporary directory, never the operator's, and
    the stand-ins for `launchctl` and `plutil` ahead of anything else on its PATH."""
    search_path = os.pathsep.join(
        [str(stand_ins(home)), *(str(entry) for entry in path_prefix), os.environ["PATH"]]
    )
    environment = dict(os.environ, HOME=str(home), PATH=search_path)
    return subprocess.run(
        [str(INSTALL_SCRIPT), *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
        cwd=REPOSITORY_ROOT,
    )


# `debate-research --json config show` as the real build prints it, cut down: one line holding
# `settings` and then `sources`, which names `storage.data_dir` again with the file it came from.
# An installer that read the second one would refuse every real build (it did, once).
CONFIG_SHOW = json.dumps({
    "status": "ok",
    "data": {
        "environment": "dev",
        "settings": {"storage.data_dir": "%s", "caselist.api_enabled": True},
        "sources": {"storage.data_dir": "profile:/bundled/config/profiles/dev.toml"},
    },
})  # fmt: skip


PROFILE_CHECK = "doctor --evidence-profiles"
"""What the wrapper's `--check` runs after `--version`, written out as the runbook gives it."""


def fake_console_script(directory: Path, *, data_directory: str | None = None) -> Path:
    """A `debate-research` that records each call beside itself and answers what is asked of it.

    `--json config show` reports a data directory the way the real build does: `data_directory`
    when given, otherwise `DEBATE_STORAGE__DATA_DIR` when that is set, as the settings loader
    reads it, otherwise the profile default `$HOME/.debate-research/$DEBATE_ENV`, so that the
    installer's check of the agent's data directory can be driven from a test.

    `doctor --evidence-profiles` prints one line and exits `0`, or with the number in the file
    `profile-check-exit` beside the script when a test has written one (:func:`profile_check_exits`).

    Each call's environment is kept beside it, numbered as the call is (:func:`environment_of_call`).
    """
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "debate-research"
    record = directory / "calls.log"
    profile_check_exit = directory / "profile-check-exit"
    reported = data_directory or "${DEBATE_STORAGE__DATA_DIR:-${HOME}/.debate-research/${DEBATE_ENV}}"
    script.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> '{record}'\n"
        f"env > '{directory}/environment-of-call-'\"$(wc -l < '{record}' | tr -d ' ')\"\n"
        'case "$*" in\n'
        "    '--json config show')\n"
        f"        printf '{CONFIG_SHOW}\\n' \"{reported}\" ;;\n"
        "    '--version') echo 'debate-research 0.0.0+fake' ;;\n"
        f"    '{PROFILE_CHECK}')\n"
        "        echo 'stand-in doctor: the evidence profiles were checked'\n"
        f"        if [ -f '{profile_check_exit}' ]; then\n"
        '            echo "stand-in doctor: debate-${DEBATE_ENV}-evidence'
        ' (storage.s3.aws_profile): not defined"\n'
        f"            exit \"$(cat '{profile_check_exit}')\"\n"
        "        fi ;;\n"
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def profile_check_exits(console_script: Path, exit_code: int) -> None:
    """Have the fake build's `doctor --evidence-profiles` end with `exit_code` from now on."""
    (console_script.parent / "profile-check-exit").write_text(f"{exit_code}\n", encoding="utf-8")


def calls_to(console_script: Path) -> list[str]:
    record = console_script.parent / "calls.log"
    return record.read_text(encoding="utf-8").splitlines() if record.exists() else []


def environment_of_call(console_script: Path, call: str) -> dict[str, str]:
    """The environment the fake build was run with the first time it was asked `call`."""
    number = calls_to(console_script).index(call) + 1
    lines = (console_script.parent / f"environment-of-call-{number}").read_text(encoding="utf-8")
    return dict(line.split("=", 1) for line in lines.splitlines() if "=" in line)


def installed_plist_bytes(home: Path) -> bytes:
    return (home / "Library" / "LaunchAgents" / f"{LABEL}.plist").read_bytes()


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
        "--env", "dev",
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
    assert list((home / "Library" / "LaunchAgents").iterdir()) == [], "a dry run installed an agent"
    assert not (home / ".local").exists(), "a dry run copied the wrapper"


@on_macos
def test_the_rendered_plist_is_one_launchctl_will_load(
    home: Path, tmp_path: Path, console_script: Path
) -> None:
    """The criterion the whole schedule rests on: `plutil -lint` is what `launchctl` runs too."""
    rendered = install(
        "--caselist",
        "testcl26",
        "--env",
        "dev",
        "--debate-research",
        str(console_script),
        "--dry-run",
        home=home,
    )
    assert rendered.returncode == 0, rendered.stderr

    written = tmp_path / "agent.plist"
    written.write_text(rendered.stdout, encoding="utf-8")
    linted = subprocess.run(["plutil", "-lint", str(written)], capture_output=True, text=True, check=False)

    assert linted.returncode == 0, linted.stdout + linted.stderr


@on_macos
def test_the_plutil_stand_in_answers_as_plutil_does(home: Path, tmp_path: Path, console_script: Path) -> None:
    """`v1-e34-t24`. The stand-in is what lets the launchd check and the reinstall run on Linux, so
    it is held to macOS's own `plutil` here: over a plist the installer rendered, every verb and
    kind of key path the installer uses, and each way they fail, answered alike, to the byte, and
    leaving the same document."""
    rendered = install(
        "--caselist", "testcl26", "--caselist", "othercl26", "--env", "dev",
        "--debate-research", str(console_script), "--dry-run", home=home,
    )  # fmt: skip
    assert rendered.returncode == 0, rendered.stderr
    steps = [
        ("-lint",),
        ("-extract", "Label", "raw", "-o", "-"),
        ("-extract", "ProgramArguments.0", "raw", "-o", "-"),
        ("-extract", "ProgramArguments.4", "raw", "-o", "-"),
        ("-extract", "ProgramArguments.5", "raw", "-o", "-"),
        ("-extract", "ProgramArguments", "raw", "-o", "-"),
        ("-extract", "EnvironmentVariables", "raw", "-o", "-"),
        ("-extract", "EnvironmentVariables.DEBATE_ENV", "raw", "-o", "-"),
        ("-extract", "EnvironmentVariables.NOT_SET", "raw", "-o", "-"),
        ("-extract", "StandardOutPath", "raw", "-o", "-"),
        ("-extract", "RunAtLoad", "raw", "-o", "-"),
        ("-replace", "Label", "-string", "renamed"),
        ("-remove", "ProgramArguments.1"),
        ("-insert", "ProgramArguments.1", "-string", "--check"),
        ("-insert", "ProgramArguments.9", "-string", "too-far"),
        ("-insert", "EnvironmentVariables.DEBATE_ENV", "-string", "prod"),
        ("-replace", "EnvironmentVariables.DEBATE_ENV", "-string", "prod"),
        ("-remove", "StartCalendarInterval"),
        ("-remove", "StartCalendarInterval"),
        ("-replace", "RunAtLoad", "-bool", "true"),
        ("-extract", "RunAtLoad", "raw", "-o", "-"),
        ("-lint",),
    ]
    answers: dict[str, tuple[list[tuple[object, ...]], object]] = {}
    for name, program in (("plutil", "/usr/bin/plutil"), ("stand-in", str(stand_ins(home) / "plutil"))):
        copy = tmp_path / f"answered-by-{name}.plist"
        copy.write_text(rendered.stdout, encoding="utf-8")
        said: list[tuple[object, ...]] = []
        for step in steps:
            ran = subprocess.run([program, *step, str(copy)], capture_output=True, text=True, check=False)
            said.append((
                step, ran.returncode,
                ran.stdout.replace(str(copy), "<plist>"), ran.stderr.replace(str(copy), "<plist>"),
            ))  # fmt: skip
        answers[name] = (said, plistlib.loads(copy.read_bytes()))

    for real, stand_in in zip(answers["plutil"][0], answers["stand-in"][0], strict=True):
        assert stand_in == real
    assert answers["stand-in"][1] == answers["plutil"][1]


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
    assert program_of(plist)[0] == str(
        home / ".local" / "share" / "debate-research" / "launchd" / "run-caselist-sync.sh"
    )


# --- The console script is pinned (ac2) ---------------------------------------------------------


def test_the_plist_pins_the_console_script_it_was_given(home: Path, console_script: Path) -> None:
    """ac2. `--debate-research` used to decide only whether to print a warning."""
    environment = environment_of(
        rendered_plist(
            install(
                "--caselist", "testcl26", "--debate-research", str(console_script), "--dry-run", home=home
            )
        )
    )

    assert environment["DEBATE_RESEARCH_BIN"] == str(console_script)
    assert environment["PATH"] == f"{console_script.parent}:{SYSTEM_PATH}"


def test_without_the_option_the_plist_pins_the_one_found_on_the_installers_path(
    home: Path, console_script: Path
) -> None:
    environment = environment_of(
        rendered_plist(
            install("--caselist", "testcl26", "--dry-run", home=home, path_prefix=(console_script.parent,))
        )
    )

    assert environment["DEBATE_RESEARCH_BIN"] == str(console_script)


def test_a_console_script_reached_through_a_symlink_is_pinned_as_found(
    home: Path, console_script: Path
) -> None:
    """`~/.local/bin/debate-research` is a link into uv's tool directory, and stays one: a
    reinstall replaces what it points at, so the link is the stable name."""
    bin_directory = home / ".local" / "bin"
    bin_directory.mkdir(parents=True)
    (bin_directory / "debate-research").symlink_to(console_script)

    environment = environment_of(
        rendered_plist(
            install("--caselist", "testcl26", "--dry-run", home=home, path_prefix=(bin_directory,))
        )
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


@pytest.mark.parametrize("exit_code", [0, 1, 3, 70])
def test_the_wrapper_hands_launchd_the_commands_exit_code_unchanged(
    home: Path, console_script: Path, exit_code: int
) -> None:
    """v1-e01-t20. 3 (the bucket did not answer) reaches launchd as 3, distinct from 1 and 70; the
    wrapper reads none of them, so it can never be the thing that turns one into another."""
    installed = install("--caselist", "testcl26", "--debate-research", str(console_script), home=home)
    assert installed.returncode == 0, installed.stderr
    plist = installed_plist(home)
    script = console_script.read_text(encoding="utf-8")
    console_script.write_text(script.replace("exit 0\n", f"exit {exit_code}\n"), encoding="utf-8")

    ran = subprocess.run(
        program_of(plist), env=environment_of(plist), capture_output=True, text=True, check=False
    )

    assert ran.returncode == exit_code, ran.stderr
    assert "--json caselist pull --caselist testcl26" in calls_to(console_script)


def test_no_exit_code_makes_launchd_run_the_agent_again(home: Path, console_script: Path) -> None:
    """The agent runs once a week by design. Without `KeepAlive` launchd records a non-zero exit as
    the last exit code and waits for the next calendar slot; a `KeepAlive` (or its
    `SuccessfulExit` and `Crashed` keys) would relaunch on an exit code, and a 3 that means "try
    later" would become a loop against the bucket and the site."""
    plist = rendered_plist(install("--caselist", "testcl26", "--debate-research", str(console_script),
                                   "--dry-run", home=home))  # fmt: skip

    assert "KeepAlive" not in plist
    assert "StartInterval" not in plist
    assert set(plist["StartCalendarInterval"]) == {"Weekday", "Hour", "Minute"}  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "where",
    ["given inside a working tree", "given inside a project .venv", "found on PATH inside a working tree",
     "a symlink into a working tree"],
)  # fmt: skip
def test_a_console_script_inside_a_checkout_or_a_venv_is_refused(
    home: Path, tmp_path: Path, where: str
) -> None:
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


def test_an_install_copies_the_wrapper_and_a_reinstall_replaces_the_copy(
    home: Path, console_script: Path
) -> None:
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
    "a File Provider folder": lambda home: home / "Library" / "CloudStorage" / "Dropbox",
    "a removable volume": lambda _home: Path("/Volumes/External Drive"),
}
PROTECTED_FOLDER_NAMES = {
    "Documents": "Documents",
    "Desktop": "Desktop",
    "Downloads": "Downloads",
    "iCloud Drive": "Library/Mobile Documents",
    "a File Provider folder": "Library/CloudStorage",
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
        console_script = fake_console_script(
            tmp_path / "reporting" / "bin", data_directory=str(protected / "data")
        )
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

    refused = install(
        "--caselist", "testcl26", "--debate-research", str(console_script), *arguments, home=home
    )

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
        "--caselist",
        "testcl26",
        "--debate-research",
        str(console_script),
        "--log-dir",
        str(home / "logs"),
        home=home,
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


def test_the_installer_asks_the_build_for_its_data_directory_and_checks_its_profile_as_the_agent_runs_it(
    home: Path, console_script: Path
) -> None:
    """The data directory comes from the profile bundled into the installed build, so the build is
    what is asked, with the agent's environment and nothing of this shell's. Then the build's own
    profile check, `v1-e34-t24`, the same way: what launchd will give the agent, and no more."""
    install(
        "--caselist",
        "testcl26",
        "--env",
        "dev",
        "--debate-research",
        str(console_script),
        "--dry-run",
        home=home,
    )

    assert calls_to(console_script) == ["--json config show", PROFILE_CHECK]
    for call in calls_to(console_script):
        environment = environment_of_call(console_script, call)
        environment.pop("PWD", None)
        environment.pop("SHLVL", None)
        environment.pop("_", None)
        assert environment == {
            "HOME": str(home),
            "PATH": f"{console_script.parent}:{SYSTEM_PATH}",
            "DEBATE_ENV": "dev",
        }, call


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


def run_wrapper(
    *arguments: str, console_script: Path, home: Path, **environment: str
) -> subprocess.CompletedProcess[str]:
    variables = {"HOME": str(home), "PATH": SYSTEM_PATH, "DEBATE_RESEARCH_BIN": str(console_script)}
    return subprocess.run(
        [str(WRAPPER_SCRIPT), *arguments],
        env={**variables, **environment},
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_wrapper_check_mode_prints_the_version_then_checks_the_profiles_and_never_pulls(
    home: Path, console_script: Path
) -> None:
    """ac5 of `v1-e34-t10`, and ac3 of `v1-e34-t22`. `--check` resolves DEBATE_RESEARCH_BIN, runs
    `--version` and then the profile check, in that order, and nothing else: it can spend nothing."""
    checked = run_wrapper("--check", console_script=console_script, home=home)

    assert checked.returncode == 0, checked.stderr
    assert str(console_script) in checked.stdout
    assert "debate-research 0.0.0+fake" in checked.stdout
    assert "stand-in doctor: the evidence profiles were checked" in checked.stdout
    assert calls_to(console_script) == ["--version", "doctor --evidence-profiles"]


@pytest.mark.parametrize("exit_code", [1, 2, 70])
def test_the_wrapper_check_mode_ends_with_the_profile_checks_exit_code(
    home: Path, console_script: Path, exit_code: int
) -> None:
    """A profile that is not defined ends `doctor --evidence-profiles` with `1`, and that is the
    number launchd records for the check and `install.sh --check-launchd` fails on. The wrapper
    reads none of them."""
    profile_check_exits(console_script, exit_code)

    checked = run_wrapper("--check", console_script=console_script, home=home)

    assert checked.returncode == exit_code
    assert "stand-in doctor: the evidence profiles were checked" in checked.stdout, "what it said is kept"
    assert calls_to(console_script) == ["--version", "doctor --evidence-profiles"]


def test_the_wrapper_check_mode_takes_no_other_arguments(home: Path, console_script: Path) -> None:
    """A `--check` that went on to read caselist arguments would be one step from a pull."""
    refused = run_wrapper("--check", "--caselist", "testcl26", console_script=console_script, home=home)

    assert refused.returncode == 2
    assert calls_to(console_script) == []


def test_the_wrapper_check_mode_fails_when_the_console_script_is_missing(home: Path, tmp_path: Path) -> None:
    checked = run_wrapper("--check", console_script=tmp_path / "gone" / "debate-research", home=home)

    assert checked.returncode == 127
    assert "DEBATE_RESEARCH_BIN" in checked.stderr


# --- The wrapper's check mode over the real command (v1-e34-t22 ac3, on every platform) ---------

EVERYDAY_PROFILE = "debate-dev-evidence"
MISSPELT_PROFILE = "debate-dev-evidence-typo"
AWS_CONFIG_NAME = "an-aws-config-written-for-this-test"


def this_checkouts_command(directory: Path) -> Path:
    """`debate-research` as this checkout's code, behind a script the wrapper can exec.

    The console script's own entry point, run by the interpreter the suite runs on. Nothing is
    stubbed: what the wrapper's `--check` gets back is what an installed build would give it.
    """
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "debate-research"
    script.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" -c "from debate_cli.app import main; main()" "$@"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def an_installation_whose_profile_setting_names(profile: str, directory: Path) -> dict[str, str]:
    """The environment of a dev installation: its profile directory, and an AWS config written
    here that defines the everyday profile and no other. Nothing of the machine's own AWS config
    is read, and a request, were one made, would go to a port nothing listens on."""
    directory.mkdir(parents=True, exist_ok=True)
    config = directory / AWS_CONFIG_NAME
    config.write_text(f"[profile {EVERYDAY_PROFILE}]\nregion = us-east-1\n", encoding="utf-8")
    profiles = directory / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{directory / "data"}"\n'
        f'[storage.s3]\nbucket = "debate-dev-evidence-not-a-bucket"\nregion = "us-east-1"\n'
        f'aws_profile = "{profile}"\n'
        '[caselist]\nnotifier = "none"\n'
        f'[models]\nrouting_file = "{directory / "routing.yaml"}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    return {
        "DEBATE_ENV": "dev",
        "DEBATE_PROFILE_DIR": str(profiles),
        "AWS_CONFIG_FILE": str(config),
        "AWS_SHARED_CREDENTIALS_FILE": str(directory / "no-credentials"),
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_ENDPOINT_URL": "http://127.0.0.1:9",
    }


def test_over_the_real_command_the_check_fails_on_a_profile_the_aws_config_lacks_and_names_its_setting(
    home: Path, tmp_path: Path
) -> None:
    """`v1-e34-t22` ac3, as `install.sh --check-launchd` runs it, with nothing standing in for the
    command: the wrapper's `--check` over this checkout's `debate-research`, in an installation
    whose `storage.s3.aws_profile` names a profile its AWS config does not define. Not skipped
    anywhere. boto3 refuses the session before any request, so no identity is stubbed and no
    network is reached."""
    command = this_checkouts_command(tmp_path / "bin")
    installation = an_installation_whose_profile_setting_names(MISSPELT_PROFILE, tmp_path / "installation")

    checked = run_wrapper("--check", console_script=command, home=home, **installation)

    said = " ".join((checked.stdout + checked.stderr).split())
    assert checked.returncode == 1, said
    assert "debate-dev-evidence-typo" in said
    assert "not defined in this" in said
    assert "storage.s3.aws_profile" in said
    assert "STORE_PROFILE_NOT_CONFIGURED" in said
    for forbidden in (str(tmp_path / "installation"), AWS_CONFIG_NAME, "/.aws", "aws sso login"):
        assert forbidden not in checked.stdout + checked.stderr


def test_over_the_real_command_the_check_passes_where_no_evidence_profile_is_configured(
    home: Path, tmp_path: Path
) -> None:
    """The other end of the same check: the `test` environment names no bucket and no profile, so
    there is nothing to ask about and the check ends with `0`."""
    command = this_checkouts_command(tmp_path / "bin")

    checked = run_wrapper(
        "--check",
        console_script=command,
        home=home,
        DEBATE_ENV="test",
        AWS_CONFIG_FILE=os.devnull,
        AWS_SHARED_CREDENTIALS_FILE=os.devnull,
        AWS_EC2_METADATA_DISABLED="true",
        AWS_ENDPOINT_URL="http://127.0.0.1:9",
    )

    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "none configured for this environment" in " ".join(checked.stdout.split())


# --- The installer's launchd check (ac5), against the fake launchctl and the plutil stand-in ----


@pytest.fixture
def fake_launchctl(home: Path) -> tuple[Path, Path, Path]:
    """The stand-ins' directory, the fake `launchctl`'s state file and its call log."""
    directory = stand_ins(home)
    return directory, directory / "launchctl-state.json", directory / "launchctl-calls.log"


def install_and_load(home: Path, console_script: Path, state: Path) -> None:
    """Install the agent into the temporary HOME and mark it loaded, with a week of runs behind it."""
    installed = install("--caselist", "testcl26", "--debate-research", str(console_script), home=home)
    assert installed.returncode == 0, installed.stderr
    state.write_text(json.dumps({LABEL: {"runs": 7, "last_exit_code": 0}}), encoding="utf-8")
    console_script.parent.joinpath("calls.log").unlink()


def check_launchd(
    home: Path, launchctl_directory: Path, **environment: str
) -> subprocess.CompletedProcess[str]:
    search_path = os.pathsep.join([str(launchctl_directory), os.environ["PATH"]])
    for tool in ("launchctl", "plutil"):
        assert shutil.which(tool, path=search_path) == str(launchctl_directory / tool), (
            f"the stand-in {tool} is not the one the installer would run"
        )
    return subprocess.run(
        [str(INSTALL_SCRIPT), "--check-launchd"],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, HOME=str(home), PATH=search_path, **environment),
        cwd=REPOSITORY_ROOT,
    )


def test_the_launchd_check_runs_the_installed_wrapper_under_its_own_label_and_never_pulls(
    home: Path, console_script: Path, fake_launchctl: tuple[Path, Path, Path]
) -> None:
    """ac5. Bootstrap a one-off label, kickstart it, print its log and exit code, boot it out."""
    launchctl_directory, state, calls = fake_launchctl
    install_and_load(home, console_script, state)

    checked = check_launchd(home, launchctl_directory)

    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "debate-research 0.0.0+fake" in checked.stdout, "the check's log was not printed"
    assert "stand-in doctor: the evidence profiles were checked" in checked.stdout
    assert "exit code 0" in checked.stdout
    assert f"{LABEL} runs: 7 before, 7 after" in checked.stdout
    assert calls_to(console_script) == ["--version", "doctor --evidence-profiles"], (
        "the check ran something other than --version and the profile check"
    )
    commands = calls.read_text(encoding="utf-8").splitlines()
    touched = {
        line.split()[0]
        for line in commands
        if line.endswith(f"/{LABEL}.check") or f"{LABEL}.check.plist" in line
    }
    assert {"bootstrap", "kickstart", "bootout"} <= touched
    assert [line for line in commands if line.endswith(f"/{LABEL}") and not line.startswith("print")] == [], (
        "the check touched the real agent"
    )
    assert LABEL + ".check" not in json.loads(state.read_text(encoding="utf-8")), (
        "the check label was left loaded"
    )
    check_plist = next(line.split()[-1] for line in commands if line.startswith("bootstrap"))
    assert not Path(check_plist).exists(), "the check's plist was left behind"


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


def test_the_launchd_check_fails_when_a_profile_is_not_defined_prints_what_was_said_and_boots_out(
    home: Path, console_script: Path, fake_launchctl: tuple[Path, Path, Path]
) -> None:
    """`v1-e34-t22` ac3. Under launchd the profile check ends with `1`: the installer prints the
    check's log, which is where the profile and its setting are named, reports the exit code,
    boots the one-off label out, and fails."""
    launchctl_directory, state, _calls = fake_launchctl
    install_and_load(home, console_script, state)
    profile_check_exits(console_script, 1)

    checked = check_launchd(home, launchctl_directory)

    assert checked.returncode == 1
    assert "stand-in doctor: the evidence profiles were checked" in checked.stdout
    assert f"{LABEL}.check exit code 1" in checked.stdout
    assert f"{LABEL} runs: 7 before, 7 after" in checked.stdout
    assert LABEL + ".check" not in json.loads(state.read_text(encoding="utf-8"))
    assert calls_to(console_script) == ["--version", "doctor --evidence-profiles"]


def test_the_launchd_check_says_a_build_without_the_profile_check_needs_replacing(
    home: Path, console_script: Path, fake_launchctl: tuple[Path, Path, Path]
) -> None:
    """A build installed before `v1-e34-t22` answers `doctor --evidence-profiles` with exit `2`,
    "no such option". The check fails, and says which build is too old rather than leave a usage
    error to be read as a verdict on the profile."""
    launchctl_directory, state, _calls = fake_launchctl
    install_and_load(home, console_script, state)
    profile_check_exits(console_script, 2)

    checked = check_launchd(home, launchctl_directory)

    assert checked.returncode == 1
    assert f"{LABEL}.check exit code 2" in checked.stdout
    assert "does not have the profile check" in checked.stderr
    assert "scripts/install_channel.sh" in checked.stderr


def test_the_launchd_check_fails_if_the_real_agent_ran_meanwhile(
    home: Path, console_script: Path, fake_launchctl: tuple[Path, Path, Path]
) -> None:
    launchctl_directory, state, _calls = fake_launchctl
    install_and_load(home, console_script, state)

    checked = check_launchd(home, launchctl_directory, FAKE_LAUNCHCTL_ALSO_RUNS=LABEL)

    assert checked.returncode == 1
    assert "7 before, 8 after" in checked.stdout + checked.stderr


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
    called = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    assert not any(line.startswith("bootstrap") for line in called)


# --- The AWS profile is the build's, and is checked before anything is written (v1-e34-t24) ------


def test_the_plist_names_no_aws_profile_because_nothing_the_agent_runs_reads_one(
    home: Path, console_script: Path
) -> None:
    """ac2. `--aws-profile` wrote `AWS_PROFILE` into the plist, and the run builds its session from
    `storage.s3.aws_profile`, which every dev and prod build sets, so the variable chose nothing.
    The option is gone and so is the variable: the profile is the build's setting, and the
    installer checks it rather than appearing to choose it."""
    environment = environment_of(
        rendered_plist(
            install(
                "--caselist",
                "testcl26",
                "--env",
                "dev",
                "--debate-research",
                str(console_script),
                "--dry-run",
                home=home,
            )  # fmt: skip
        )
    )

    assert set(environment) == {"DEBATE_ENV", "HOME", "DEBATE_RESEARCH_BIN", "PATH"}


def test_the_aws_profile_option_is_refused_and_says_where_the_profile_comes_from(
    home: Path, console_script: Path
) -> None:
    refused = install(
        "--caselist", "testcl26", "--aws-profile", "debate-dev-evidence",
        "--debate-research", str(console_script), "--dry-run", home=home,
    )  # fmt: skip
    helped = install("--help", home=home)

    assert refused.returncode == 2
    assert "--aws-profile" in refused.stderr and "storage.s3.aws_profile" in refused.stderr
    assert calls_to(console_script) == [], "the build was asked something before the option was refused"
    assert helped.returncode == 0
    assert "--aws-profile NAME" not in helped.stdout
    assert "AWS_PROFILE" not in TEMPLATE.read_text(encoding="utf-8")


@pytest.mark.parametrize("dry_run", [False, True], ids=["install", "dry run"])
def test_a_profile_the_aws_config_does_not_define_is_refused_naming_it_and_nothing_is_written(
    home: Path, console_script: Path, dry_run: bool
) -> None:
    """ac2. What the runbook's reinstall step 2 checks by hand, the installer checks too: the
    build's `doctor --evidence-profiles`, as the agent will run it. On a failure it shows what the
    build said, which names the profile and its setting, and installs nothing."""
    profile_check_exits(console_script, 1)

    refused = install(
        "--caselist", "testcl26", "--env", "dev", "--debate-research", str(console_script),
        *(["--dry-run"] if dry_run else []), home=home,
    )  # fmt: skip

    assert refused.returncode == 2
    assert refused.stdout == ""
    assert "debate-dev-evidence (storage.s3.aws_profile): not defined" in refused.stderr
    assert "nothing was installed" in refused.stderr
    assert list((home / "Library" / "LaunchAgents").iterdir()) == []
    assert not (home / ".local").exists()
    assert not (home / "Library" / "Logs").exists()


def test_a_build_without_the_profile_check_is_not_installed_and_is_said_to_be_too_old(
    home: Path, console_script: Path
) -> None:
    """Exit 2 from `doctor --evidence-profiles` is a build from before `v1-e34-t22` refusing the
    option, which says nothing about any profile."""
    profile_check_exits(console_script, 2)

    refused = install("--caselist", "testcl26", "--debate-research", str(console_script), home=home)

    assert refused.returncode == 2
    assert "does not have the profile check" in refused.stderr
    assert "scripts/install_channel.sh" in refused.stderr
    assert list((home / "Library" / "LaunchAgents").iterdir()) == []


@pytest.mark.parametrize("dry_run", [False, True], ids=["install", "dry run"])
def test_over_the_real_command_the_installer_refuses_a_profile_the_aws_config_lacks_naming_it(
    home: Path, tmp_path: Path, dry_run: bool
) -> None:
    """ac2 and ac3, with nothing standing in for the build: this checkout's `debate-research`, run
    by the installer as the agent will run it, in a HOME whose AWS config defines another profile.
    boto3 refuses the session before any request, so no network is reached, and the machine's own
    AWS config is not read: the installer gives the build the temporary HOME and nothing else.
    A refused install, its dry run included, leaves HOME as it found it."""
    (home / ".aws").mkdir()
    (home / ".aws" / "config").write_text("[profile someone-elses-profile]\nregion = us-east-1\n")
    command = this_checkouts_command(tmp_path / "bin")
    before = sorted(home.rglob("*"))

    refused = install(
        "--caselist", "testcl26", "--env", "dev", "--debate-research", str(command),
        *(["--dry-run"] if dry_run else []), home=home,
    )  # fmt: skip

    # The build's report is a table and a panel 80 columns wide, so its sentences wrap inside borders.
    said = " ".join(re.sub("[│┃╭╮╰╯─]", " ", refused.stdout + refused.stderr).split())
    assert refused.returncode == 2, said
    assert "debate-dev-evidence" in said
    assert "not defined in this" in said
    assert "storage.s3.aws_profile" in said
    assert "nothing was installed" in said
    assert sorted(home.rglob("*")) == before, "the refused install created something under HOME"
    assert str(home / ".aws") not in said and ".aws/config" not in said


# --- A reinstall keeps what is installed (v1-e34-t24 ac4) ----------------------------------------


def install_first(home: Path, console_script: Path, *arguments: str) -> None:
    installed = install(*arguments, "--debate-research", str(console_script), home=home)
    assert installed.returncode == 0, installed.stderr


def edit_installed_plist(home: Path, **environment: str) -> None:
    """Add to the installed plist's environment, as `PlistBuddy` would by hand."""
    plist_file = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    plist = plistlib.loads(plist_file.read_bytes())
    plist["EnvironmentVariables"].update(environment)
    plist_file.write_bytes(plistlib.dumps(plist))


def test_a_first_install_without_env_is_prod(home: Path, console_script: Path) -> None:
    """Unchanged: with nothing installed there is nothing to keep, and the schedule is prod's job."""
    install_first(home, console_script, "--caselist", "testcl26")

    assert environment_of(installed_plist(home))["DEBATE_ENV"] == "prod"


def test_a_reinstall_with_no_env_or_caselist_keeps_the_installed_ones_and_says_so(
    home: Path, console_script: Path
) -> None:
    """ac4. At the reinstall of 2026-10-14, a dev agent reinstalled with the runbook's example
    would have been switched to prod and an empty store, because `--env` defaulted to prod. Over
    an installed agent, an option left out now keeps what is installed, and the installer says
    what it kept."""
    install_first(home, console_script, "--caselist", "testcl26", "--caselist", "othercl26", "--env", "dev")

    again = install("--debate-research", str(console_script), home=home)

    assert again.returncode == 0, again.stderr
    plist = installed_plist(home)
    assert environment_of(plist)["DEBATE_ENV"] == "dev"
    assert program_of(plist)[1:] == ["--caselist", "testcl26", "--caselist", "othercl26"]
    said = " ".join(again.stdout.split())
    assert "Keeping the installed agent's environment, dev" in said
    assert "Keeping the installed agent's caselists: testcl26 othercl26" in said
    assert f"keeps its data in {home}/.debate-research/dev" in said
    assert environment_of_call(console_script, PROFILE_CHECK)["DEBATE_ENV"] == "dev", (
        "the profile checked was not the kept environment's"
    )


def test_a_dry_run_over_an_installed_agent_renders_what_is_installed_and_says_so_beside_the_plist(
    home: Path, console_script: Path
) -> None:
    install_first(home, console_script, "--caselist", "testcl26", "--env", "dev")

    rendered = install("--debate-research", str(console_script), "--dry-run", home=home)

    plist = rendered_plist(rendered)
    assert environment_of(plist)["DEBATE_ENV"] == "dev"
    assert program_of(plist)[1:] == ["--caselist", "testcl26"]
    assert "Keeping the installed agent's environment, dev" in rendered.stderr


@pytest.mark.parametrize("dry_run", [False, True], ids=["install", "dry run"])
def test_a_different_env_over_an_installed_agent_is_refused_and_changes_nothing(
    home: Path, console_script: Path, dry_run: bool
) -> None:
    """ac4. `--env prod` over a dev agent is a switch to another data directory and another
    bucket. Given without its confirmation, it is a mistake until shown otherwise."""
    install_first(home, console_script, "--caselist", "testcl26", "--env", "dev")
    before = installed_plist_bytes(home)
    asked_before = calls_to(console_script)

    refused = install(
        "--env", "prod", "--debate-research", str(console_script), *(["--dry-run"] if dry_run else []),
        home=home,
    )  # fmt: skip

    said = " ".join(refused.stderr.split())
    assert refused.returncode == 2, refused.stdout
    assert refused.stdout == ""
    assert "runs as dev" in said and "--env prod" in said
    assert "--confirm-env-change" in said
    assert "Nothing was installed" in said
    assert installed_plist_bytes(home) == before
    assert calls_to(console_script) == asked_before, "the build was asked something before the refusal"


def test_a_different_env_confirmed_switches_the_agent_keeps_its_caselists_and_says_so(
    home: Path, console_script: Path
) -> None:
    install_first(home, console_script, "--caselist", "testcl26", "--env", "dev")

    switched = install(
        "--env", "prod", "--confirm-env-change", "--debate-research", str(console_script), home=home
    )

    assert switched.returncode == 0, switched.stderr
    plist = installed_plist(home)
    assert environment_of(plist)["DEBATE_ENV"] == "prod"
    assert program_of(plist)[1:] == ["--caselist", "testcl26"]
    said = " ".join(switched.stdout.split())
    assert "from dev to prod" in said
    assert f"keeps its data in {home}/.debate-research/prod" in said


def test_the_installed_env_given_again_is_no_change(home: Path, console_script: Path) -> None:
    install_first(home, console_script, "--caselist", "testcl26", "--env", "dev")

    again = install("--env", "dev", "--debate-research", str(console_script), home=home)

    assert again.returncode == 0, again.stderr
    assert environment_of(installed_plist(home))["DEBATE_ENV"] == "dev"


def test_caselists_given_over_an_installed_agent_replace_them_and_it_says_so(
    home: Path, console_script: Path
) -> None:
    install_first(home, console_script, "--caselist", "testcl26", "--caselist", "othercl26", "--env", "dev")

    again = install("--caselist", "thirdcl26", "--debate-research", str(console_script), home=home)

    assert again.returncode == 0, again.stderr
    plist = installed_plist(home)
    assert program_of(plist)[1:] == ["--caselist", "thirdcl26"]
    assert environment_of(plist)["DEBATE_ENV"] == "dev"
    said = " ".join(again.stdout.split())
    assert "Replacing the installed agent's caselists testcl26 othercl26 with thirdcl26" in said


@pytest.mark.parametrize("dry_run", [False, True], ids=["install", "dry run"])
def test_a_reinstall_that_would_move_the_data_directory_is_refused_unless_confirmed(
    home: Path, tmp_path: Path, console_script: Path, dry_run: bool
) -> None:
    """The task's forbidden list: an agent's data directory never changes without an explicit
    option. A variable added to the installed plist by hand is not one this script writes, so a
    reinstall drops it; where that would move the data, the reinstall is refused, naming both
    directories and the variables it would drop."""
    install_first(home, console_script, "--caselist", "testcl26", "--env", "dev")
    elsewhere = tmp_path / "kept-elsewhere"
    edit_installed_plist(home, DEBATE_STORAGE__DATA_DIR=str(elsewhere))
    before = installed_plist_bytes(home)
    dry = ["--dry-run"] if dry_run else []

    refused = install("--debate-research", str(console_script), *dry, home=home)
    confirmed = install("--confirm-env-change", "--debate-research", str(console_script), *dry, home=home)

    said = " ".join(refused.stderr.split())
    assert refused.returncode == 2, refused.stdout
    assert str(elsewhere) in said and f"{home}/.debate-research/dev" in said
    assert "DEBATE_STORAGE__DATA_DIR" in said and "--confirm-env-change" in said
    assert confirmed.returncode == 0, confirmed.stderr
    if dry_run:
        assert installed_plist_bytes(home) == before
        assert "DEBATE_STORAGE__DATA_DIR" not in environment_of(rendered_plist(confirmed))
    else:
        assert "DEBATE_STORAGE__DATA_DIR" not in environment_of(installed_plist(home))


def test_a_variable_this_script_does_not_write_is_named_when_a_reinstall_drops_it(
    home: Path, console_script: Path
) -> None:
    """The parse stage's switch is added to the plist by hand, and a reinstall writes the plist
    afresh without it, as the runbook says. It moves no data, so the reinstall goes ahead, and
    now says what it dropped."""
    install_first(home, console_script, "--caselist", "testcl26", "--env", "dev")
    edit_installed_plist(home, DEBATE_CASELIST__PARSE_IMPORTED_SOURCES="false")

    again = install("--debate-research", str(console_script), home=home)

    assert again.returncode == 0, again.stderr
    assert "DEBATE_CASELIST__PARSE_IMPORTED_SOURCES" not in environment_of(installed_plist(home))
    said = " ".join(again.stdout.split())
    assert "Not carried over from the installed plist: DEBATE_CASELIST__PARSE_IMPORTED_SOURCES" in said


def test_an_agent_installed_with_aws_profile_keeps_its_environment_and_loses_the_variable(
    home: Path, console_script: Path
) -> None:
    """Every agent installed before `v1-e34-t24` has `AWS_PROFILE` in its plist. A reinstall
    keeps its environment, drops the variable, and says why it went."""
    install_first(home, console_script, "--caselist", "testcl26", "--env", "dev")
    edit_installed_plist(home, AWS_PROFILE="debate-dev-evidence")

    again = install("--debate-research", str(console_script), home=home)

    assert again.returncode == 0, again.stderr
    environment = environment_of(installed_plist(home))
    assert environment["DEBATE_ENV"] == "dev"
    assert "AWS_PROFILE" not in environment
    said = " ".join(again.stdout.split())
    assert "AWS_PROFILE" in said and "storage.s3.aws_profile" in said


def test_an_installed_agent_whose_arguments_this_script_did_not_write_needs_its_caselists_given(
    home: Path, console_script: Path
) -> None:
    install_first(home, console_script, "--caselist", "testcl26", "--env", "dev")
    plist_file = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    plist = plistlib.loads(plist_file.read_bytes())
    plist["ProgramArguments"].append("--full-archive")
    plist_file.write_bytes(plistlib.dumps(plist))

    refused = install("--debate-research", str(console_script), home=home)
    given = install("--caselist", "testcl26", "--debate-research", str(console_script), home=home)

    assert refused.returncode == 2
    assert "--full-archive" in refused.stderr and "--caselist" in refused.stderr
    assert given.returncode == 0, given.stderr
    assert program_of(installed_plist(home))[1:] == ["--caselist", "testcl26"]


# --- What the installer says to do next -----------------------------------------------------------


def test_after_a_first_install_the_next_steps_give_each_caselist_its_flag(
    home: Path, console_script: Path, fake_launchctl: tuple[Path, Path, Path]
) -> None:
    """The validation pull it prints has to be one the command accepts, `--caselist` per slug."""
    launchctl_directory, _state, _calls = fake_launchctl
    installed = install(
        "--caselist", "testcl26", "--caselist", "othercl26", "--debate-research", str(console_script),
        home=home, path_prefix=(launchctl_directory,),
    )  # fmt: skip

    assert installed.returncode == 0, installed.stderr
    assert "Nothing is scheduled yet" in installed.stdout
    assert "caselist pull --caselist testcl26 --caselist othercl26 --dry-run" in installed.stdout
    assert "caselist pull testcl26" not in installed.stdout


def test_a_reinstall_over_a_loaded_agent_suggests_a_reload_and_the_check_never_a_pull(
    home: Path, console_script: Path, fake_launchctl: tuple[Path, Path, Path]
) -> None:
    """A real pull on a reinstall would spend the day's downloads to prove nothing new."""
    launchctl_directory, state, calls = fake_launchctl
    state.write_text(json.dumps({LABEL: {"runs": 1, "last_exit_code": 0}}), encoding="utf-8")

    installed = install(
        "--caselist", "testcl26", "--debate-research", str(console_script),
        home=home, path_prefix=(launchctl_directory,),
    )  # fmt: skip

    assert installed.returncode == 0, installed.stderr
    assert "caselist pull" not in installed.stdout
    assert "Nothing is scheduled yet" not in installed.stdout
    assert f"launchctl bootout gui/$UID/{LABEL}" in installed.stdout
    assert f"launchctl bootstrap gui/$UID {home}/Library/LaunchAgents/{LABEL}.plist" in installed.stdout
    assert "--check-launchd" in installed.stdout
    called = calls.read_text(encoding="utf-8").splitlines()
    assert called and all(line.startswith("print ") for line in called), "the installer changed launchd"


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

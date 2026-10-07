"""`scripts/install_channel.sh`: what it installs, from where, on which Python, and when it refuses.

v1-e01-t09 ac2b: it never takes `debate-core` or `debate-cli` from an index.

Neither name is registered on PyPI, and the build this script installs is what a weekly launchd agent
runs unattended (v1-e34-t05). A squatter who registers either name must not be able to take over the
install. Third-party dependencies must still come from the index as normal.

These tests run the real script and the real `uv` against:

* a **release directory** holding synthetic `debate_core` / `debate_cli` wheels at a dev version,
  with `SHA256SUMS`, as `gh release download` would leave it;
* a **decoy index**, a PEP 503 directory served as `file://` and set as uv's *default* index (the
  stand-in for PyPI). It holds the one third-party dependency, `thirdparty-dep`, and squatted
  `debate-core` / `debate-cli` wheels: at the same dev version with a more specific wheel tag
  (`cpXY-none-any` for the running Python, which an installer prefers over `py3-none-any`), and at
  `99.0.0`.

Each synthetic `debate-research` prints which `debate_core` it imported, so the assertion is on
what actually runs rather than on what uv said it installed. A control test shows that the
`--find-links debate-cli==<version>` command this script used to run *does* take the decoy, so the
decoy index is live and the passing tests are not vacuous.

v1-e01-t14 adds three things, each tested here:

* **The interpreter comes from the wheel.** The synthetic `debate_core` wheel states the real
  `debate_core` pyproject's `requires-python` as its `Requires-Python`, and a `uv` shim first on
  `PATH` logs every call, so the tests see the specifier the script passed. Changing the wheel's
  bound changes the request; metadata the script cannot read makes it refuse before uv runs.
* **Rehearse, then replace.** Every check runs against an install in a temporary tool directory
  first, and a build that fails one leaves the previous install byte-for-byte as it was.
* **`--no-path-warning`** silences the PATH warning and nothing else.

v1-e01-t22 holds the real install to the rehearsal's resolution. The shim publishes a newer release
of the third-party dependency to the index the moment the rehearsal ends, and the real install must
still get the version the rehearsal checked. A control test shows that an unpinned second install
takes the newer one, so the publish is live.

Offline: every URL is `file://`, the uv cache is a temporary directory, and uv may not download a
Python (it needs one that debate_core's `requires-python` admits and that it can already find, as
CI's `uv python install` provides).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "install_channel.sh"

VERSION = "0.1.0.dev7"
TAG = "v0.1.0-dev.7"
NEXT_VERSION = "0.1.0.dev8"
NEXT_TAG = "v0.1.0-dev.8"

UV = shutil.which("uv")

# The one statement of the supported interpreter. The synthetic core wheel carries it, as the real
# wheel does, so these tests need no version of their own.
REQUIRES_PYTHON = tomllib.loads(
    (REPO_ROOT / "packages" / "debate_core" / "pyproject.toml").read_text("utf-8")
)["project"]["requires-python"]
# A bound no Python satisfies, so uv cannot find an interpreter and nothing is installed.
UNSATISFIABLE_BOUND = ">=9.1,<9.2"
# The tag an installer prefers over py3-none-any on the running Python.
RUNNING_PYTHON_TAG = f"cp{sys.version_info.major}{sys.version_info.minor}-none-any"

PATH_WARNING = "warning — `debate-research` on this PATH is"


def write_wheel(
    directory: Path,
    name: str,
    version: str,
    *,
    requires: tuple[str, ...] = (),
    files: dict[str, str],
    console_scripts: dict[str, str] | None = None,
    tag: str = "py3-none-any",
    metadata_extra: str = "",
    with_metadata: bool = True,
) -> Path:
    """A minimal, valid wheel: the members given, METADATA, WHEEL, entry points and a RECORD.

    `metadata_extra` is appended to METADATA as it stands, header lines or a blank line and a body.
    """
    directory.mkdir(parents=True, exist_ok=True)
    distribution = name.replace("-", "_")
    info = f"{distribution}-{version}.dist-info"
    members = dict(files)
    if with_metadata:
        members[f"{info}/METADATA"] = (
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
            + "".join(f"Requires-Dist: {requirement}\n" for requirement in requires)
            + metadata_extra
        )
    members[f"{info}/WHEEL"] = f"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: {tag}\n"
    if console_scripts:
        members[f"{info}/entry_points.txt"] = "[console_scripts]\n" + "".join(
            f"{command} = {target}\n" for command, target in console_scripts.items()
        )
    record = []
    for member, text in members.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(text.encode()).digest()).rstrip(b"=").decode()
        record.append(f"{member},sha256={digest},{len(text.encode())}")
    record.append(f"{info}/RECORD,,")
    members[f"{info}/RECORD"] = "\n".join(record) + "\n"
    path = directory / f"{distribution}-{version}-{tag}.whl"
    with zipfile.ZipFile(path, "w") as archive:
        for member, text in members.items():
            archive.writestr(member, text)
    return path


def core_files(origin: str) -> dict[str, str]:
    # Importing the third-party package proves it was installed, and from where the tests expect.
    return {"debate_core/__init__.py": f"import thirdparty_dep\n\nORIGIN = {origin!r}\n"}


def cli_files(origin: str, version: str, *, check_exit: int = 0, doctor_exit: int = 0) -> dict[str, str]:
    report = f'{{"version": "{version}", "channel": "dev", "cli": "{origin}", "core": debate_core.ORIGIN}}'
    return {
        "debate_cli/__init__.py": "",
        # `doctor` stands in for the real one (v1-e01-t14); anything else prints the version report.
        "debate_cli/app.py": (
            "import json\nimport sys\n\nimport debate_core\n\n\ndef main():\n"
            "    if 'doctor' in sys.argv[1:]:\n"
            f"        print('stand-in doctor, exiting {doctor_exit}')\n"
            f"        raise SystemExit({doctor_exit})\n"
            f"    print(json.dumps({report}))\n"
        ),
        # Stands in for the real post-install check (v1-e01-t17), which these wheels have nothing to
        # check with; its exit status is what install_channel.sh acts on.
        "debate_cli/installation.py": (
            f"print('stand-in installation check, exiting {check_exit}')\nraise SystemExit({check_exit})\n"
        ),
    }


def cli_wheel(
    directory: Path,
    origin: str,
    version: str,
    tag: str = "py3-none-any",
    *,
    core_version: str = VERSION,
    check_exit: int = 0,
    doctor_exit: int = 0,
) -> Path:
    return write_wheel(
        directory,
        "debate-cli",
        version,
        requires=(f"debate-core[opencaselist]=={core_version}",),
        files=cli_files(origin, version, check_exit=check_exit, doctor_exit=doctor_exit),
        console_scripts={"debate-research": "debate_cli.app:main"},
        tag=tag,
    )


@dataclass(frozen=True)
class Fixture:
    release: Path
    index_url: str
    tools: Path

    @property
    def installed(self) -> Path:
        return self.tools / "bin" / "debate-research"


def write_release(
    directory: Path,
    *,
    with_core: bool = True,
    check_exit: int = 0,
    doctor_exit: int = 0,
    version: str = VERSION,
    tag: str = TAG,
    core_metadata: str | None = f"Requires-Python: {REQUIRES_PYTHON}\n",
    core_bytes: bytes | None = None,
) -> Path:
    """The assets of a pre-release, as install_channel.sh finds them after `gh release download`.

    `core_metadata` is what the core wheel's METADATA says after its name, version and requirements
    (None: the wheel has no METADATA at all); `core_bytes` replaces the whole wheel file.
    """
    if with_core:
        core = write_wheel(
            directory,
            "debate-core",
            version,
            requires=("thirdparty-dep",),
            files=core_files("release"),
            metadata_extra=core_metadata or "",
            with_metadata=core_metadata is not None,
        )
        if core_bytes is not None:
            core.write_bytes(core_bytes)
    cli_wheel(
        directory, "release", version, core_version=version, check_exit=check_exit, doctor_exit=doctor_exit
    )
    (directory / "build-info.json").write_text(json.dumps({"version": version, "tag": tag}), encoding="utf-8")
    sums = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(directory.iterdir())
        if path.suffix in {".whl", ".json"}
    ]
    (directory / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return directory


def third_party_wheel(directory: Path, version: str) -> Path:
    """`thirdparty-dep` at `version`; the module says which version it is."""
    return write_wheel(
        directory, "thirdparty-dep", version, files={"thirdparty_dep/__init__.py": f"VERSION = {version!r}\n"}
    )


def write_decoy_index(root: Path, *, squat_versions: tuple[str, ...]) -> str:
    """A PEP 503 index holding the third-party dependency and squatted first-party wheels."""
    files = root / "files"
    third_party_wheel(files, "1.0")
    for version in squat_versions:
        for tag in ("py3-none-any", RUNNING_PYTHON_TAG):
            write_wheel(
                files,
                "debate-core",
                version,
                requires=("thirdparty-dep",),
                files=core_files(f"decoy {version} {tag}"),
                tag=tag,
                metadata_extra=f"Requires-Python: {REQUIRES_PYTHON}\n",
            )
            cli_wheel(files, f"decoy {version} {tag}", version, tag=tag)
    simple = root / "simple"
    for wheel in sorted(files.glob("*.whl")):
        add_to_index(simple, wheel)
    return simple.as_uri()


def add_to_index(simple: Path, wheel: Path) -> None:
    """List `wheel` on its project's page of the PEP 503 index at `simple`."""
    project = wheel.name.split("-", 1)[0].replace("_", "-")
    page = simple / project / "index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    existing = page.read_text(encoding="utf-8") if page.exists() else ""
    page.write_text(existing + f'<a href="{wheel.as_uri()}">{wheel.name}</a>\n', encoding="utf-8")


def uv_environment(fixture: Fixture, tmp_path: Path) -> dict[str, str]:
    """The process environment with the decoy as uv's default index and everything else disposable.

    `uv` on PATH is a shim that logs each call (see :func:`uv_calls`) and then runs the real uv.
    """
    environment = {
        name: value
        for name, value in os.environ.items()
        if name != "VIRTUAL_ENV"
        and not name.startswith(("UV_INDEX", "UV_EXTRA_INDEX", "UV_FIND_LINKS", "UV_DEFAULT_INDEX"))
        and name not in {"UV_PRERELEASE", "UV_OFFLINE", "UV_NO_INDEX", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL"}
    }
    environment.update(
        {
            "UV_DEFAULT_INDEX": fixture.index_url,
            "UV_CACHE_DIR": str(tmp_path / "uv-cache"),
            "UV_TOOL_DIR": str(fixture.tools / "environments"),
            "UV_TOOL_BIN_DIR": str(fixture.tools / "bin"),
            "UV_PYTHON_DOWNLOADS": "never",
            "UV_NO_CONFIG": "1",
            "PATH": f"{uv_shim(tmp_path)}{os.pathsep}{os.environ.get('PATH', '')}",
        }
    )
    return environment


def uv_shim(tmp_path: Path) -> Path:
    """A directory holding a `uv` that appends `UV_TOOL_DIR<TAB>arguments` to a log, then runs uv.

    Three settings in the script's environment change what happens around the real uv (v1-e01-t22):

    * `UV_SHIM_AFTER_REHEARSAL`: a shell script run once, at the first uv call made outside the
      rehearsal's tool directory after one made inside it, i.e. the moment the rehearsal ends and
      before anything that follows it. A test uses it to publish a newer release to the index.
    * `UV_SHIM_IGNORE_CONSTRAINTS`: drop `--constraints FILE` before running uv, as a uv that
      ignored the option would.
    * `UV_SHIM_FREEZE_EXTRA`: a line added to what `uv pip freeze` prints.
    """
    assert UV is not None
    directory = tmp_path / "uv-shim"
    directory.mkdir(exist_ok=True)
    shim = directory / "uv"
    seen = tmp_path / "uv-shim-rehearsal-seen"
    ran = tmp_path / "uv-shim-after-rehearsal-ran"
    shim.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\t%s\\n' \"${{UV_TOOL_DIR:-}}\" \"$*\" >> '{tmp_path / 'uv-calls.log'}'\n"
        'case "${UV_TOOL_DIR:-}" in\n'
        f"    *debate-research-rehearsal.*) : > '{seen}' ;;\n"
        "    *)\n"
        f"        if [ -n \"${{UV_SHIM_AFTER_REHEARSAL:-}}\" ] && [ -e '{seen}' ] && [ ! -e '{ran}' ]; then\n"
        f"            : > '{ran}'\n"
        '            sh "${UV_SHIM_AFTER_REHEARSAL}"\n'
        "        fi ;;\n"
        "esac\n"
        'if [ -n "${UV_SHIM_IGNORE_CONSTRAINTS:-}" ]; then\n'
        "    skip=\n"
        "    for argument do\n"
        "        shift\n"
        '        if [ -n "${skip}" ]; then skip=; continue; fi\n'
        '        if [ "${argument}" = --constraints ]; then skip=yes; continue; fi\n'
        '        set -- "$@" "${argument}"\n'
        "    done\n"
        "fi\n"
        'if [ -n "${UV_SHIM_FREEZE_EXTRA:-}" ] && [ "$1" = pip ] && [ "$2" = freeze ]; then\n'
        f"    '{UV}' \"$@\" || exit\n"
        "    printf '%s\\n' \"${UV_SHIM_FREEZE_EXTRA}\"\n"
        "    exit 0\n"
        "fi\n"
        f"exec '{UV}' \"$@\"\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return directory


def uv_calls(tmp_path: Path) -> list[tuple[str, str]]:
    """Every uv call the script made, as `(UV_TOOL_DIR, arguments)`."""
    log = tmp_path / "uv-calls.log"
    if not log.exists():
        return []
    return [tuple(line.split("\t", 1)) for line in log.read_text(encoding="utf-8").splitlines()]  # type: ignore[misc]


def tool_installs(tmp_path: Path) -> list[tuple[str, str]]:
    return [
        (tool_dir, arguments)
        for tool_dir, arguments in uv_calls(tmp_path)
        if arguments.startswith("tool install")
    ]


def install(
    fixture: Fixture, tmp_path: Path, *options: str, tag: str = TAG, **environment: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(SCRIPT), *options, "--dir", str(fixture.release), tag],
        capture_output=True,
        text=True,
        env=uv_environment(fixture, tmp_path) | environment,
        check=False,
    )


def run_installed(fixture: Fixture) -> dict[str, str]:
    output = subprocess.run([str(fixture.installed)], capture_output=True, text=True, check=True).stdout
    return json.loads(output.strip().splitlines()[-1])


def installed_third_party_version(tool_directory: Path) -> str:
    """The `thirdparty-dep` version the tool environment under `tool_directory` actually imports."""
    python = tool_directory / "debate-cli" / "bin" / "python"
    return subprocess.run(
        [str(python), "-c", "import thirdparty_dep; print(thirdparty_dep.VERSION)"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


pytestmark = pytest.mark.skipif(UV is None, reason="uv is not on PATH")


@pytest.fixture(params=["same-version squat", "higher-version squat"])
def fixture(request: pytest.FixtureRequest, tmp_path: Path) -> Fixture:
    squats = (VERSION,) if request.param == "same-version squat" else (VERSION, "99.0.0")
    return Fixture(
        release=write_release(tmp_path / "release"),
        index_url=write_decoy_index(tmp_path / "decoy-index", squat_versions=squats),
        tools=tmp_path / "tools",
    )


def test_install_channel_takes_both_first_party_wheels_from_the_release_and_never_the_decoy(
    fixture: Fixture, tmp_path: Path
) -> None:
    result = subprocess.run(
        ["sh", str(SCRIPT), "--dir", str(fixture.release), TAG],
        capture_output=True,
        text=True,
        env=uv_environment(fixture, tmp_path),
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert run_installed(fixture) == {
        "version": VERSION,
        "channel": "dev",
        "cli": "release",
        "core": "release",
    }


def test_without_the_release_core_wheel_the_install_fails_instead_of_using_the_index(
    tmp_path: Path,
) -> None:
    fixture = Fixture(
        release=write_release(tmp_path / "release", with_core=False),
        index_url=write_decoy_index(tmp_path / "decoy-index", squat_versions=(VERSION, "99.0.0")),
        tools=tmp_path / "tools",
    )

    result = subprocess.run(
        ["sh", str(SCRIPT), "--dir", str(fixture.release), TAG],
        capture_output=True,
        text=True,
        env=uv_environment(fixture, tmp_path),
        check=False,
    )

    assert result.returncode != 0
    assert f"has no debate_core wheel for version {VERSION}" in result.stderr
    assert not fixture.installed.exists()


def test_an_installed_build_whose_integration_check_fails_fails_the_install(tmp_path: Path) -> None:
    """`--version` passing is not enough: the build must pass `python -m debate_cli.installation`."""
    fixture = Fixture(
        release=write_release(tmp_path / "release", check_exit=1),
        index_url=write_decoy_index(tmp_path / "decoy-index", squat_versions=()),
        tools=tmp_path / "tools",
    )

    result = subprocess.run(
        ["sh", str(SCRIPT), "--dir", str(fixture.release), TAG],
        capture_output=True,
        text=True,
        env=uv_environment(fixture, tmp_path),
        check=False,
    )

    assert result.returncode != 0
    assert "stand-in installation check, exiting 1" in result.stdout
    assert f"the build installed from {TAG} is incomplete" in result.stderr
    assert "Installed debate-research" not in result.stdout


def test_control_the_old_find_links_install_is_taken_over_by_a_same_version_squat(tmp_path: Path) -> None:
    """Why the script changed: the command it used to run installs the squatter's debate_core."""
    assert UV is not None
    fixture = Fixture(
        release=write_release(tmp_path / "release"),
        index_url=write_decoy_index(tmp_path / "decoy-index", squat_versions=(VERSION,)),
        tools=tmp_path / "tools",
    )

    subprocess.run(
        [
            UV,
            "tool",
            "install",
            "--force",
            "--python",
            REQUIRES_PYTHON,
            "--find-links",
            str(fixture.release),
            f"debate-cli=={VERSION}",
        ],
        capture_output=True,
        text=True,
        env=uv_environment(fixture, tmp_path),
        check=True,
    )

    report = run_installed(fixture)
    assert report["core"].startswith("decoy"), report
    assert report["cli"].startswith("decoy"), report


# ------------------------------------------------------------------------------------------------
# v1-e01-t14 ac1: the interpreter comes from the debate_core wheel's Requires-Python
# ------------------------------------------------------------------------------------------------


def no_squats(tmp_path: Path, **release: Any) -> Fixture:
    return Fixture(
        release=write_release(tmp_path / "release", **release),
        index_url=write_decoy_index(tmp_path / "decoy-index", squat_versions=()),
        tools=tmp_path / "tools",
    )


def test_uv_is_asked_for_the_python_the_core_wheel_requires(tmp_path: Path) -> None:
    fixture = no_squats(tmp_path)

    result = install(fixture, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    installs = tool_installs(tmp_path)
    assert len(installs) == 2, installs
    for _tool_dir, arguments in installs:
        assert f"--python {REQUIRES_PYTHON} " in arguments, arguments


def test_changing_the_bound_in_the_wheel_changes_what_uv_is_asked_for(tmp_path: Path) -> None:
    fixture = no_squats(tmp_path, core_metadata=f"Requires-Python: {UNSATISFIABLE_BOUND}\n")

    result = install(fixture, tmp_path)

    assert result.returncode != 0
    installs = tool_installs(tmp_path)
    assert installs, "uv was never asked to install"
    assert all(f"--python {UNSATISFIABLE_BOUND} " in arguments for _tool_dir, arguments in installs), installs
    assert f"on a Python matching '{UNSATISFIABLE_BOUND}'" in result.stderr
    assert not fixture.installed.exists()


CORE_WHEEL = f"debate_core-{VERSION}-py3-none-any.whl"


@pytest.mark.parametrize(
    ("release", "refusal"),
    [
        pytest.param({"core_metadata": ""}, "states no Requires-Python", id="no Requires-Python line"),
        pytest.param(
            {"core_metadata": "Requires-Python: \n"}, "states no Requires-Python", id="empty Requires-Python"
        ),
        pytest.param(
            {"core_metadata": f"Summary: x\n\nRequires-Python: {REQUIRES_PYTHON}\n"},
            "states no Requires-Python",
            id="only in the description body",
        ),
        pytest.param(
            {"core_metadata": f"Requires-Python: {REQUIRES_PYTHON}\nRequires-Python: {REQUIRES_PYTHON}\n"},
            "more than once",
            id="stated twice",
        ),
        pytest.param(
            {"core_metadata": "Requires-Python: $(touch pwned)\n"},
            "is not a version specifier",
            id="not a specifier",
        ),
        pytest.param({"core_metadata": None}, "could not read", id="no METADATA in the wheel"),
        pytest.param({"core_bytes": b"not a zip archive"}, "could not read", id="not a zip archive"),
    ],
)
def test_metadata_that_cannot_be_read_makes_the_script_refuse_rather_than_guess(
    tmp_path: Path, release: dict[str, Any], refusal: str
) -> None:
    fixture = no_squats(tmp_path, **release)

    result = install(fixture, tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert refusal in result.stderr
    assert CORE_WHEEL in result.stderr, "the refusal must name the wheel"
    assert "refusing to guess" in result.stderr
    assert tool_installs(tmp_path) == [], "uv was asked to install anyway"
    assert not fixture.installed.exists()
    assert not (tmp_path / "pwned").exists()


def test_the_script_holds_no_interpreter_version_of_its_own() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "PYTHON_VERSION" not in text
    assert '--python "${REQUIRES_PYTHON}"' in text


# ------------------------------------------------------------------------------------------------
# v1-e01-t14 ac3 and ac5: rehearse in a temporary tool directory, then replace
# ------------------------------------------------------------------------------------------------


def snapshot(directory: Path) -> dict[str, tuple[object, ...]]:
    """Every entry under `directory`: kind, mode, mtime and content hash or link target."""
    entries: dict[str, tuple[object, ...]] = {}
    for path in sorted(directory.rglob("*")):
        info = path.lstat()
        relative = str(path.relative_to(directory))
        if path.is_symlink():
            entries[relative] = ("link", os.readlink(path), info.st_mode, info.st_mtime_ns)
        elif path.is_file():
            entries[relative] = (
                "file",
                hashlib.sha256(path.read_bytes()).hexdigest(),
                info.st_mode,
                info.st_mtime_ns,
            )
        else:
            entries[relative] = ("directory", info.st_mode)
    return entries


@pytest.mark.parametrize(
    ("failing", "message"),
    [
        pytest.param({"check_exit": 1}, "is incomplete", id="integration check"),
        pytest.param({"doctor_exit": 1}, "debate-research doctor failed", id="doctor"),
    ],
)
def test_a_build_failing_a_check_leaves_the_previous_install_byte_for_byte_untouched(
    tmp_path: Path, failing: dict[str, Any], message: str
) -> None:
    previous = no_squats(tmp_path)
    assert install(previous, tmp_path).returncode == 0
    # Running the build may write bytecode into its environment, so the snapshot is taken after.
    assert run_installed(previous)["version"] == VERSION
    before = snapshot(previous.tools)
    broken = Fixture(
        release=write_release(tmp_path / "next-release", version=NEXT_VERSION, tag=NEXT_TAG, **failing),
        index_url=previous.index_url,
        tools=previous.tools,
    )

    result = install(broken, tmp_path, tag=NEXT_TAG)

    assert result.returncode == 1, result.stdout + result.stderr
    assert message in result.stderr
    assert "failed a check in the rehearsal install" in result.stderr
    assert "the installed debate-research was not touched" in result.stderr
    assert snapshot(previous.tools) == before
    assert run_installed(previous)["version"] == VERSION
    # The one install uv was asked for went to a temporary directory, never to the real one.
    installs = tool_installs(tmp_path)[2:]
    assert len(installs) == 1, installs
    assert installs[0][0] != str(previous.tools / "environments")


def test_a_failing_doctor_fails_the_install_and_leaves_nothing_on_the_path(tmp_path: Path) -> None:
    fixture = no_squats(tmp_path, doctor_exit=1)

    result = install(fixture, tmp_path)

    assert result.returncode == 1
    assert "stand-in doctor, exiting 1" in result.stdout
    assert "Installed debate-research" not in result.stdout
    assert not fixture.installed.exists()
    assert not (fixture.tools / "environments" / "debate-cli").exists()


def test_every_check_runs_in_the_rehearsal_and_again_after_the_real_install(tmp_path: Path) -> None:
    fixture = no_squats(tmp_path)

    result = install(fixture, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    for check in (
        '"version": "0.1.0.dev7"',
        "stand-in installation check, exiting 0",
        "stand-in doctor, exiting 0",
    ):
        assert result.stdout.count(check) == 2, (check, result.stdout)
    assert result.stdout.index("The rehearsal passed") > result.stdout.index("stand-in doctor, exiting 0")


def test_the_rehearsal_goes_to_a_temporary_directory_even_when_the_caller_chose_one(tmp_path: Path) -> None:
    fixture = no_squats(tmp_path)

    result = install(fixture, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    (rehearsal, _), (real, _) = tool_installs(tmp_path)
    assert real == str(fixture.tools / "environments")
    assert rehearsal != real
    assert "debate-research-rehearsal." in rehearsal
    assert not Path(rehearsal).exists(), "the rehearsal directory was left behind"
    assert run_installed(fixture)["version"] == VERSION


# ------------------------------------------------------------------------------------------------
# v1-e01-t14 ac6: --no-path-warning silences the PATH warning and nothing else
# ------------------------------------------------------------------------------------------------


def script_messages(stderr: str) -> list[str]:
    return [line for line in stderr.splitlines() if line.startswith("install_channel:")]


def test_the_path_warning_is_shown_without_the_option_and_not_with_it(tmp_path: Path) -> None:
    fixture = no_squats(tmp_path)

    without = install(fixture, tmp_path)
    quiet = install(fixture, tmp_path, "--no-path-warning")

    assert without.returncode == quiet.returncode == 0, without.stderr + quiet.stderr
    assert PATH_WARNING in without.stderr
    assert PATH_WARNING not in quiet.stderr
    assert script_messages(quiet.stderr) == []
    assert f"Installed debate-research {VERSION} from {TAG}" in quiet.stdout


@pytest.mark.parametrize("environment", [{"CI": "true"}, {"GITHUB_ACTIONS": "true"}, {"TERM": "dumb"}])
def test_the_warning_is_never_guessed_away_from_the_environment(
    tmp_path: Path, environment: dict[str, str]
) -> None:
    result = install(no_squats(tmp_path), tmp_path, **environment)

    assert result.returncode == 0, result.stderr
    assert PATH_WARNING in result.stderr


@pytest.mark.parametrize(
    "failing",
    [
        pytest.param({"check_exit": 1}, id="integration check"),
        pytest.param({"doctor_exit": 1}, id="doctor"),
        pytest.param({"core_metadata": ""}, id="unreadable metadata"),
    ],
)
def test_the_option_leaves_every_failure_as_it_was(tmp_path: Path, failing: dict[str, Any]) -> None:
    loud = install(no_squats(tmp_path / "loud", **failing), tmp_path / "loud")
    quiet = install(no_squats(tmp_path / "quiet", **failing), tmp_path / "quiet", "--no-path-warning")

    assert loud.returncode == quiet.returncode == 1
    assert script_messages(quiet.stderr) == [
        line.replace(str(tmp_path / "loud"), str(tmp_path / "quiet")) for line in script_messages(loud.stderr)
    ]
    assert script_messages(quiet.stderr)


def test_the_workflows_that_install_into_scratch_directories_pass_the_option() -> None:
    # validate-dev's driver passes it in scripts/validate_dev.py (tests/scripts/test_validate_dev.py).
    runs = [
        line.strip()
        for workflow in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
        for line in workflow.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("sh scripts/install_channel.sh")
    ]

    assert runs, "no workflow runs scripts/install_channel.sh"
    assert all("--no-path-warning" in run for run in runs), runs


# ------------------------------------------------------------------------------------------------
# v1-e01-t22 ac1: the real install resolves exactly what the rehearsal resolved
# ------------------------------------------------------------------------------------------------

NEWER_THIRD_PARTY = "2.0"


def publish_newer_third_party_release(tmp_path: Path) -> Path:
    """A shell script that publishes `thirdparty-dep` 2.0 to the fixture's index when it runs.

    The wheel is built now, outside the index, and the script only moves it in and lists it, so
    publishing takes no Python and no time.
    """
    index = tmp_path / "decoy-index"
    staged = third_party_wheel(tmp_path / "unpublished", NEWER_THIRD_PARTY)
    published = index / "files" / staged.name
    page = index / "simple" / "thirdparty-dep" / "index.html"
    script = tmp_path / "publish-newer-release.sh"
    script.write_text(
        f"cp '{staged}' '{published}'\n"
        f"printf '%s\\n' '<a href=\"{published.as_uri()}\">{published.name}</a>' >> '{page}'\n",
        encoding="utf-8",
    )
    return script


def test_a_release_published_between_the_rehearsal_and_the_real_install_is_not_installed(
    tmp_path: Path,
) -> None:
    fixture = no_squats(tmp_path)
    publish = publish_newer_third_party_release(tmp_path)

    result = install(fixture, tmp_path, UV_SHIM_AFTER_REHEARSAL=str(publish))

    assert result.returncode == 0, result.stdout + result.stderr
    # The newer release really was on the index before the real install resolved.
    assert (tmp_path / "uv-shim-after-rehearsal-ran").exists()
    assert NEWER_THIRD_PARTY in (
        tmp_path / "decoy-index" / "simple" / "thirdparty-dep" / "index.html"
    ).read_text(encoding="utf-8")
    assert installed_third_party_version(fixture.tools / "environments") == "1.0"
    assert run_installed(fixture)["core"] == "release"


def test_control_an_unpinned_install_after_that_publish_takes_the_newer_release(tmp_path: Path) -> None:
    """Why the pins are needed: the same two installs without them resolve differently."""
    assert UV is not None
    fixture = no_squats(tmp_path)
    publish = publish_newer_third_party_release(tmp_path)
    command = [
        UV,
        "tool",
        "install",
        "--force",
        "--python",
        REQUIRES_PYTHON,
        f"debate-cli @ {(fixture.release / f'debate_cli-{VERSION}-py3-none-any.whl').as_uri()}",
        "--with",
        f"debate-core @ {(fixture.release / CORE_WHEEL).as_uri()}",
    ]
    environment = uv_environment(fixture, tmp_path)

    subprocess.run(command, capture_output=True, text=True, env=environment, check=True)
    first = installed_third_party_version(fixture.tools / "environments")
    subprocess.run(["sh", str(publish)], check=True)
    subprocess.run(command, capture_output=True, text=True, env=environment, check=True)
    second = installed_third_party_version(fixture.tools / "environments")

    assert (first, second) == ("1.0", NEWER_THIRD_PARTY)


def test_only_the_real_install_is_pinned_and_to_what_the_rehearsal_installed(tmp_path: Path) -> None:
    fixture = no_squats(tmp_path)

    result = install(fixture, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    (_, rehearsal), (_, real) = tool_installs(tmp_path)
    assert "--constraints" not in rehearsal
    assert "--constraints" in real
    # uv records the pins it was given in the tool's receipt; the first-party wheels are not among
    # them, because their verified file URLs already decide them.
    receipt = tomllib.loads(
        (fixture.tools / "environments" / "debate-cli" / "uv-receipt.toml").read_text("utf-8")
    )
    assert receipt["tool"]["constraints"] == [{"name": "thirdparty-dep", "specifier": "==1.0"}]
    assert "Pinning the real install to the 1 third-party distribution the rehearsal checked" in result.stdout


def test_a_uv_that_ignores_the_pins_is_caught_by_comparing_the_two_installs(tmp_path: Path) -> None:
    """A future uv that accepted `--constraints` and ignored it must not pass unnoticed."""
    fixture = no_squats(tmp_path)
    publish = publish_newer_third_party_release(tmp_path)

    result = install(fixture, tmp_path, UV_SHIM_AFTER_REHEARSAL=str(publish), UV_SHIM_IGNORE_CONSTRAINTS="1")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "the real install is not the build the rehearsal checked" in result.stderr
    assert "-thirdparty-dep==1.0" in result.stderr
    assert f"+thirdparty-dep=={NEWER_THIRD_PARTY}" in result.stderr
    assert "Installed debate-research" not in result.stdout


@pytest.mark.parametrize(
    "line",
    [
        pytest.param("someone-elses-package @ https://example.invalid/package.whl", id="a third-party URL"),
        pytest.param("-e file:///somewhere/else", id="an editable install"),
        pytest.param("debate-core==0.1.0.dev7", id="first-party from an index"),
    ],
)
def test_a_rehearsal_holding_something_that_cannot_be_pinned_is_refused_before_the_real_install(
    tmp_path: Path, line: str
) -> None:
    fixture = no_squats(tmp_path)

    result = install(fixture, tmp_path, UV_SHIM_FREEZE_EXTRA=line)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "cannot be pinned" in result.stderr
    assert line in result.stderr
    assert "the installed debate-research was not touched" in result.stderr
    assert len(tool_installs(tmp_path)) == 1, "the real install ran anyway"
    assert not fixture.installed.exists()

"""`scripts/install_channel.sh` never takes `debate-core` or `debate-cli` from an index (v1-e01-t09 ac2b).

Neither name is registered on PyPI, and the build this script installs is what a weekly launchd agent
runs unattended (v1-e34-t05). A squatter who registers either name must not be able to take over the
install. Third-party dependencies must still come from the index as normal.

These tests run the real script and the real `uv` against:

* a **release directory** holding synthetic `debate_core` / `debate_cli` wheels at a dev version,
  with `SHA256SUMS`, as `gh release download` would leave it;
* a **decoy index**, a PEP 503 directory served as `file://` and set as uv's *default* index (the
  stand-in for PyPI). It holds the one third-party dependency, `thirdparty-dep`, and squatted
  `debate-core` / `debate-cli` wheels: at the same dev version with a more specific wheel tag
  (`cp312-none-any`, which an installer prefers over `py3-none-any`), and at `99.0.0`.

Each synthetic `debate-research` prints which `debate_core` it imported, so the assertion is on
what actually runs rather than on what uv said it installed. A control test shows that the
`--find-links debate-cli==<version>` command this script used to run *does* take the decoy, so the
decoy index is live and the passing tests are not vacuous.

Offline: every URL is `file://`, the uv cache is a temporary directory, and uv may not download a
Python (it needs a 3.12 it can already find, as CI's `uv python install` provides).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "install_channel.sh"

VERSION = "0.1.0.dev7"
TAG = "v0.1.0-dev.7"

UV = shutil.which("uv")


def write_wheel(
    directory: Path,
    name: str,
    version: str,
    *,
    requires: tuple[str, ...] = (),
    files: dict[str, str],
    console_scripts: dict[str, str] | None = None,
    tag: str = "py3-none-any",
) -> Path:
    """A minimal, valid wheel: the members given, METADATA, WHEEL, entry points and a RECORD."""
    directory.mkdir(parents=True, exist_ok=True)
    distribution = name.replace("-", "_")
    info = f"{distribution}-{version}.dist-info"
    members = dict(files)
    members[f"{info}/METADATA"] = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n" + "".join(
        f"Requires-Dist: {requirement}\n" for requirement in requires
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


def cli_files(origin: str, version: str, *, check_exit: int = 0) -> dict[str, str]:
    report = f'{{"version": "{version}", "channel": "dev", "cli": "{origin}", "core": debate_core.ORIGIN}}'
    return {
        "debate_cli/__init__.py": "",
        "debate_cli/app.py": (
            f"import json\n\nimport debate_core\n\n\ndef main():\n    print(json.dumps({report}))\n"
        ),
        # Stands in for the real post-install check (v1-e01-t17), which these wheels have nothing to
        # check with; its exit status is what install_channel.sh acts on.
        "debate_cli/installation.py": (
            f"print('stand-in installation check, exiting {check_exit}')\nraise SystemExit({check_exit})\n"
        ),
    }


def cli_wheel(
    directory: Path, origin: str, version: str, tag: str = "py3-none-any", *, check_exit: int = 0
) -> Path:
    return write_wheel(
        directory,
        "debate-cli",
        version,
        requires=(f"debate-core[opencaselist]=={VERSION}",),
        files=cli_files(origin, version, check_exit=check_exit),
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


def write_release(directory: Path, *, with_core: bool = True, check_exit: int = 0) -> Path:
    """The assets of a pre-release, as install_channel.sh finds them after `gh release download`."""
    if with_core:
        write_wheel(
            directory, "debate-core", VERSION, requires=("thirdparty-dep",), files=core_files("release")
        )
    cli_wheel(directory, "release", VERSION, check_exit=check_exit)
    (directory / "build-info.json").write_text(json.dumps({"version": VERSION, "tag": TAG}), encoding="utf-8")
    sums = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(directory.iterdir())
        if path.suffix in {".whl", ".json"}
    ]
    (directory / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return directory


def write_decoy_index(root: Path, *, squat_versions: tuple[str, ...]) -> str:
    """A PEP 503 index holding the third-party dependency and squatted first-party wheels."""
    files = root / "files"
    write_wheel(files, "thirdparty-dep", "1.0", files={"thirdparty_dep/__init__.py": ""})
    for version in squat_versions:
        for tag in ("py3-none-any", "cp312-none-any"):
            write_wheel(
                files,
                "debate-core",
                version,
                requires=("thirdparty-dep",),
                files=core_files(f"decoy {version} {tag}"),
                tag=tag,
            )
            cli_wheel(files, f"decoy {version} {tag}", version, tag=tag)
    simple = root / "simple"
    for wheel in sorted(files.glob("*.whl")):
        project = wheel.name.split("-", 1)[0].replace("_", "-")
        page = simple / project / "index.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        existing = page.read_text(encoding="utf-8") if page.exists() else ""
        page.write_text(existing + f'<a href="{wheel.as_uri()}">{wheel.name}</a>\n', encoding="utf-8")
    return simple.as_uri()


def uv_environment(fixture: Fixture, tmp_path: Path) -> dict[str, str]:
    """The process environment with the decoy as uv's default index and everything else disposable."""
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
        }
    )
    return environment


def run_installed(fixture: Fixture) -> dict[str, str]:
    output = subprocess.run([str(fixture.installed)], capture_output=True, text=True, check=True).stdout
    return json.loads(output.strip().splitlines()[-1])


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
            "3.12",
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

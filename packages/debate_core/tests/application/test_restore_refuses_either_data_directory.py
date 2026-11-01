"""A restore refuses both environments' data directories, whichever environment it runs in (`v1-e40-t24`).

Before this task a restore in dev refused only dev's data directory, so
`--into ~/.debate-research/prod` was accepted while prod's was absent or empty, and the restored-copy
marker (`v1-e40-t21`) would then land in a live data directory. What is here:

* a restore in dev refuses prod's data directory, a directory inside it and one holding it, whether
  prod's is absent, empty or in use; a restore in prod refuses dev's the same way;
* the paths are compared real: a symbolic link to prod's data directory, a link on the way to it, `..`,
  `~`, a trailing slash and another letter case all resolve to it;
* a sibling beside the data directories, its name starting with theirs, is accepted, and restored into;
* an environment whose data directory cannot be resolved refuses every directory;
* each environment's data directory comes from its own profile, never from this shell's
  `DEBATE_STORAGE__DATA_DIR`.

The home folder is the test's own. Each environment's profile names its data directory the way the
committed ones do, from `~`. "apart" moves prod's out from beside dev's, so that a directory holding
prod's holds only prod's, which is the only way to tell that refusal from the one for dev's.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

import pytest

from debate_core.application.caselist.run_state import RestoreReport, RunState
from debate_core.application.caselist.run_state_restore import (
    RESTORED_COPY_MARKER,
    DataDirectory,
    RestoreTargetRefused,
    RunStateRestore,
    restore_target_refusal,
)
from debate_core.application.caselist.run_state_sources import RestoredSources
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.environment_data_dirs import profile_data_dir
from debate_core.application.settings import ConfigurationError, Environment

DEV, PROD = Environment.DEV, Environment.PROD
LAYOUTS: Final = {
    "beside each other": {DEV: "~/.debate-research/dev", PROD: "~/.debate-research/prod"},
    "apart": {DEV: "~/.debate-research/dev", PROD: "~/prod-store/data"},
}
"""Each environment's `storage.data_dir`, as its profile spells it."""

STATES: Final = ("absent", "empty", "in use")
"""The other environment's data directory: not made yet, made and empty, or holding a store."""


class Home:
    """A home folder with dev's and prod's profiles, and the data directories they name."""

    def __init__(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layout: str = "beside each other"
    ) -> None:
        self.root = tmp_path / "home"
        self.root.mkdir()
        monkeypatch.setenv("HOME", str(self.root))
        monkeypatch.delenv("DEBATE_STORAGE__DATA_DIR", raising=False)
        self.profiles = tmp_path / "profiles"
        self.profiles.mkdir()
        monkeypatch.setenv("DEBATE_PROFILE_DIR", str(self.profiles))
        for environment, spelled in LAYOUTS[layout].items():
            self.profile(environment, f'[storage]\ndata_dir = "{spelled}"\n')
        self.dirs = {environment: self.root / spelled[2:] for environment, spelled in LAYOUTS[layout].items()}

    def profile(self, environment: Environment, text: str) -> None:
        (self.profiles / f"{environment.value}.toml").write_text(text, encoding="utf-8")

    def make(self, environment: Environment, state: str) -> Path:
        """`environment`'s data directory, in `state`."""
        directory = self.dirs[environment]
        if state != "absent":
            directory.mkdir(parents=True)
        if state == "in use":
            (directory / "debate.sqlite3").write_bytes(b"a live database\n")
        return directory

    def data_dirs(self, running: Environment) -> list[DataDirectory]:
        """What the container hands a restore in `running`: its own, then dev's and prod's profiles'."""
        return [
            DataDirectory(running.value, profile_data_dir(running)),
            *(DataDirectory(environment.value, profile_data_dir(environment)) for environment in (DEV, PROD)),
        ]

    def refusal(self, target: Path, running: Environment) -> str | None:
        return restore_target_refusal(target, environment=running.value, data_dirs=self.data_dirs(running))


def other(running: Environment) -> Environment:
    return PROD if running is DEV else DEV


# ------------------------------------------------------------------------------------------------
# The other environment's data directory, inside it and holding it
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("layout", sorted(LAYOUTS))
@pytest.mark.parametrize("running", [DEV, PROD], ids=["a dev restore", "a prod restore"])
def test_a_restore_refuses_the_other_environments_data_directory_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, running: Environment, layout: str, state: str
) -> None:
    home = Home(tmp_path, monkeypatch, layout)
    home.make(running, "in use")
    target = home.make(other(running), state)

    refusal = home.refusal(target, running)

    assert refusal is not None
    assert f"is {other(running).value}'s data directory" in refusal, refusal
    assert f"a restore in {running.value} stays out of too" in refusal


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("layout", sorted(LAYOUTS))
@pytest.mark.parametrize("running", [DEV, PROD], ids=["a dev restore", "a prod restore"])
def test_a_restore_refuses_a_directory_inside_the_other_environments_data_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, running: Environment, layout: str, state: str
) -> None:
    home = Home(tmp_path, monkeypatch, layout)
    home.make(running, "in use")
    target = home.make(other(running), state) / "copies" / "this-week"

    refusal = home.refusal(target, running)

    assert refusal is not None
    assert f"is inside {other(running).value}'s data directory" in refusal, refusal


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("running", [DEV, PROD], ids=["a dev restore", "a prod restore"])
def test_a_restore_refuses_a_directory_holding_only_the_other_environments_data_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, running: Environment, state: str
) -> None:
    """Apart, so the directory holds the other environment's data directory and not the running one's."""
    home = Home(tmp_path, monkeypatch, "apart")
    home.make(running, "in use")
    target = home.make(other(running), state).parent

    refusal = home.refusal(target, running)

    assert refusal is not None
    assert f"holds {other(running).value}'s data directory" in refusal, refusal


@pytest.mark.parametrize("running", [DEV, PROD], ids=["a dev restore", "a prod restore"])
def test_a_directory_holding_both_data_directories_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, running: Environment
) -> None:
    home = Home(tmp_path, monkeypatch)
    home.make(DEV, "in use")
    home.make(PROD, "absent")

    for target in (home.root / ".debate-research", home.root):
        refusal = home.refusal(target, running)
        assert refusal is not None and "holds this environment's own data directory" in refusal, refusal


# ------------------------------------------------------------------------------------------------
# Compared real
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("state", STATES)
def test_a_symbolic_link_to_prods_data_directory_is_prods_data_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    """Absent, the link dangles, and is still followed to where prod's data directory will be."""
    home = Home(tmp_path, monkeypatch)
    home.make(DEV, "in use")
    link = tmp_path / "link-to-prod"
    link.symlink_to(home.make(PROD, state), target_is_directory=True)

    refusal = home.refusal(link, DEV)

    assert refusal is not None and "is prod's data directory" in refusal, refusal


@pytest.mark.parametrize("state", STATES)
def test_a_link_on_the_way_to_prods_data_directory_is_followed_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    """The target is not made yet; its nearest existing parent is a link, which resolves the rest."""
    home = Home(tmp_path, monkeypatch, "apart")
    home.make(DEV, "in use")
    prod = home.make(PROD, state)
    prod.parent.mkdir(parents=True, exist_ok=True)
    link = tmp_path / "link-to-the-prod-store"
    link.symlink_to(prod.parent, target_is_directory=True)

    for target, relation in (
        (link / prod.name, "is"),
        (link / prod.name / "copy", "is inside"),
        (link, "holds"),
    ):
        refusal = home.refusal(target, DEV)
        assert refusal is not None and f"{relation} prod's data directory" in refusal, (target, refusal)


@pytest.mark.parametrize(
    "spelled",
    [
        "~/.debate-research/prod",
        "~/.debate-research/prod/",
        "~/.debate-research/dev-journey-copy/../prod",
        "~/.debate-research/./prod/copies/..",
        "~/.debate-research/PROD",
        "~/.Debate-Research/Prod/copy",
    ],
)
def test_prods_data_directory_however_it_is_spelled_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spelled: str
) -> None:
    """`~`, `..`, `.`, a trailing slash and letter case, which the Mac's file system folds."""
    home = Home(tmp_path, monkeypatch)
    home.make(DEV, "in use")
    home.make(PROD, "absent")

    refusal = home.refusal(Path(spelled), DEV)

    assert refusal is not None and "prod's data directory" in refusal, refusal


# ------------------------------------------------------------------------------------------------
# A sibling is accepted
# ------------------------------------------------------------------------------------------------

SIBLINGS: Final = (
    "~/.debate-research/dev-journey-copy",
    "~/.debate-research/prod-landscape-copy",
    "~/.debate-research/devcopy",
    "~/.debate-research/prod2",
)
"""Each beside the data directories, its name starting with one's: a prefix is not a parent."""


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("sibling", SIBLINGS)
@pytest.mark.parametrize("running", [DEV, PROD], ids=["a dev restore", "a prod restore"])
def test_a_sibling_beside_the_data_directories_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, running: Environment, sibling: str, state: str
) -> None:
    home = Home(tmp_path, monkeypatch)
    home.make(running, "in use")
    home.make(other(running), state)

    assert home.refusal(Path(sibling), running) is None


# ------------------------------------------------------------------------------------------------
# Through the restore: a refused directory gets no marker, a sibling gets the copy
# ------------------------------------------------------------------------------------------------

RESTORED_AT: Final = datetime(2026, 11, 6, 14, 3, 9, tzinfo=UTC)


class StateStandIn:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    async def restore(self, caselists: Sequence[str], *, parsed_version: str | None) -> RestoreReport:
        (self.directory / "debate.sqlite3").write_bytes(b"a restored database\n")
        return RestoreReport(started_at=RESTORED_AT, finished_at=RESTORED_AT, state_files=())

    async def local_manifests(self) -> list[object]:
        return []


class SuppressionStandIn:
    async def reconcile(self) -> None:
        return None

    async def entries(self) -> list[object]:
        return []


def restore_in(home: Home, running: Environment, restored: list[Path]) -> RunStateRestore:
    def state_in(directory: Path) -> RunState:
        restored.append(directory)
        return cast("RunState", StateStandIn(directory))

    def sources_in(directory: Path) -> RestoredSources:  # pragma: no cover - no test asks for sources
        raise AssertionError("sources were not asked for")

    return RunStateRestore(
        state_in=state_in,
        suppression_in=lambda directory: cast("RecordedSuppressionList", SuppressionStandIn()),
        sources_in=sources_in,
        data_dirs=home.data_dirs(running),
        parsed_version="v1",
        environment=running.value,
        bucket="debate-dev-evidence-sample",
        build_tag=None,
        clock=lambda: RESTORED_AT,
    )


@pytest.mark.parametrize("state", ["absent", "empty"])
def test_a_dev_restore_into_prods_data_directory_leaves_no_marker_and_makes_no_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    """The case this task is for: prod's data directory absent or empty, the restore run in dev."""
    home = Home(tmp_path, monkeypatch)
    home.make(DEV, "in use")
    prod = home.make(PROD, state)
    restored: list[Path] = []

    with pytest.raises(RestoreTargetRefused, match="prod's data directory"):
        asyncio.run(restore_in(home, DEV, restored).restore(Path("~/.debate-research/prod"), ["samplecl26"]))

    assert restored == []
    assert list(home.root.rglob(RESTORED_COPY_MARKER)) == []
    assert prod.exists() == (state == "empty")
    assert not prod.exists() or list(prod.iterdir()) == []


def test_a_dev_restore_into_a_sibling_restores_the_copy_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = Home(tmp_path, monkeypatch)
    home.make(DEV, "in use")
    home.make(PROD, "absent")
    restored: list[Path] = []

    asyncio.run(restore_in(home, DEV, restored).restore(Path("~/.debate-research/dev-journey-copy"), ["x"]))

    copy = home.root / ".debate-research" / "dev-journey-copy"
    assert restored == [copy.resolve()]
    assert (copy / RESTORED_COPY_MARKER).is_file()
    assert not home.dirs[PROD].exists()


# ------------------------------------------------------------------------------------------------
# An environment whose data directory cannot be resolved
# ------------------------------------------------------------------------------------------------


def test_an_environment_whose_data_directory_is_not_known_refuses_every_directory(tmp_path: Path) -> None:
    data_dirs = [DataDirectory("dev", tmp_path / "dev"), DataDirectory("prod", None)]

    refusal = restore_target_refusal(tmp_path / "anywhere", environment="dev", data_dirs=data_dirs)

    assert refusal is not None
    assert "prod's data directory could not be resolved from its settings" in refusal
    assert "DEBATE_ENV=prod debate-research config show" in refusal
    assert str(tmp_path) not in refusal, "no path in the message"


# ------------------------------------------------------------------------------------------------
# Each environment's data directory, from its own profile
# ------------------------------------------------------------------------------------------------


def test_each_environments_data_directory_is_its_profiles_with_home_expanded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = Home(tmp_path, monkeypatch, "apart")

    assert profile_data_dir(DEV) == home.root / ".debate-research" / "dev"
    assert profile_data_dir(PROD) == home.root / "prod-store" / "data"


def test_this_shells_data_directory_override_is_not_another_environments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = Home(tmp_path, monkeypatch)
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(tmp_path / "a-dev-override"))

    assert profile_data_dir(PROD) == home.root / ".debate-research" / "prod"
    assert profile_data_dir(DEV) == home.root / ".debate-research" / "dev"


@pytest.mark.parametrize("profile", ["none", "no storage table", "no data_dir"])
def test_without_a_profile_value_the_built_in_profiles_data_directory_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    home = Home(tmp_path, monkeypatch, "apart")
    if profile == "none":
        (home.profiles / "prod.toml").unlink()
    else:
        home.profile(PROD, "[models]\n" if profile == "no storage table" else "[storage.s3]\nbucket = 'b'\n")

    assert profile_data_dir(PROD) == home.root / ".debate-research" / "prod"


@pytest.mark.parametrize(
    "text", ["[storage\ndata_dir = 'x'\n", "[storage]\ndata_dir = 5\n"], ids=["not TOML", "not a path"]
)
def test_a_profile_that_cannot_be_read_raises_a_configuration_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    home = Home(tmp_path, monkeypatch)
    home.profile(PROD, text)

    with pytest.raises(ConfigurationError):
        profile_data_dir(PROD)

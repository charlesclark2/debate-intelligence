"""Two synthetic OpenEv downloads of one camp release, for the OpenEv importer (`v1-e30-t04`).

Nothing here came from OpenEv. The camps are invented — `Quillfeather Debate Institute` (QDI),
`Tamarack Summer Forum` (TSF), `Brightwater Workshop` (BWW) and the deliberately unlisted
`Zephyr Scholars` — and so is every file title and every document body, a few hundred bytes of
filler this module writes. That is a rule, not a convenience: `docs/policies/caselist-data-use.md`
and the rulings merged with `v1-e31-t02` keep real camp files and real excerpts out of the
repository. The downloads are built into a temporary directory at test time and never committed.

The invented camps are in `camp_aliases.yaml` beside this file, which the tests and the smoke
check pass as `--camp-aliases`. The packaged table names real camps and none of these.

## The one file that is not new

`Tamarack/TSF-Borrowed Grove Aff.docx` holds **exactly the bytes** of the caselist fixture's
`grove-round-1-aff` (`tests/fixtures/caselist/build_synthetic_archives.py`), the file the synthetic
caselist discloses from its first week on. Imported after that caselist, it is ac2's case: a camp
file a team has already disclosed, stored once and linked from both a disclosure and a camp-file
record.

## The two downloads

`openev-2026-policy` is the first download of the 2026 Policy release: eleven camp files and two
pieces of macOS junk, laid out the ways a real download is — camp folders with lab folders below
them, camp prefixes on bare filenames, a folder and a prefix that disagree, a camp nobody listed,
a PDF, two files with identical bytes, and one file named the way the scheduled sync names what it
downloads (`openev-<id>-<file name>`).

`openev-2026-policy-addendum` is a later, partial download of the same release: one file exactly
as before, one revised under the same path, one new, one copy of an earlier file under a new name,
and the junk again. It is what the weekly sync will produce, and what must merge into the release
manifest rather than replace it.

## What they should produce

`expected_openev_import.json`, beside this file, **written by hand** from the tables below and not
by running the importer (`docs/process/working-agreements.md` §6). This module does not compute it
and nothing regenerates it.

Run it by hand to look at what it makes::

    uv run python -m tests.fixtures.openev.build_synthetic_openev /tmp/synthetic-openev
"""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES as CASELIST_DOCUMENT_BODIES,
)

# The caselist fixture's deterministic writers, reused so both fixtures build files one way.
from tests.fixtures.caselist.build_synthetic_archives import (
    _docx,  # pyright: ignore[reportPrivateUsage]
    _pdf,  # pyright: ignore[reportPrivateUsage]
)

__all__ = [
    "CAMP_ALIASES_PATH",
    "DOCUMENT_BODIES",
    "DOWNLOADS",
    "EXPECTED_PATH",
    "SYNTHETIC_EVENT",
    "SYNTHETIC_YEAR",
    "SyntheticDownload",
    "build_download_directories",
    "build_download_zips",
    "expected",
]

SYNTHETIC_YEAR = 2026
SYNTHETIC_EVENT = "POLICY"

#: The alias table naming the invented camps, passed as `--camp-aliases`.
CAMP_ALIASES_PATH = Path(__file__).parent / "camp_aliases.yaml"

#: The hand-written expectations the tests assert against.
EXPECTED_PATH = Path(__file__).parent / "expected_openev_import.json"

#: Same fixed timestamp as the caselist fixture, so two builds are byte-identical.
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _camp_docx(*paragraphs: str) -> bytes:
    """A small, valid `.docx` of invented filler. Deterministic: see the caselist fixture's `_docx`."""
    return _docx(paragraphs)


#: Every distinct body, by the short name the tables below use. Eleven OpenEv bodies of their own,
#: plus the one borrowed from the caselist fixture.
DOCUMENT_BODIES: dict[str, bytes] = {
    "orchard-kritik": _camp_docx("Brightwater Workshop.", "Orchard kritik: invented filler, no real card."),
    "tidewater-impact-turns": _camp_docx(
        "Brightwater Workshop.", "Tidewater impact turns, filed under QDI's prefix."
    ),
    "harbor-tariffs-aff": _camp_docx(
        "Quillfeather Debate Institute, Juniors Lab.", "Harbor tariffs affirmative."
    ),
    "harbor-tariffs-neg": _camp_docx(
        "Quillfeather Debate Institute, Juniors Lab.", "Harbor tariffs negative."
    ),
    "lighthouse-politics": _camp_docx(
        "Quillfeather Debate Institute, Seniors Lab.", "Lighthouse politics DA."
    ),
    "canal-counterplan": _camp_docx("Tamarack Summer Forum.", "Canal subsidies counterplan, first release."),
    "canal-counterplan-revised": _camp_docx(
        "Tamarack Summer Forum.", "Canal subsidies counterplan, revised in the addendum."
    ),
    "reservoir-topicality-pdf": _pdf("Tamarack reservoir topicality"),
    "glacier-case-neg": _camp_docx("Zephyr Scholars.", "Glacier case negative, from a camp nobody listed."),
    "spillway-advantage": _camp_docx("Tamarack Summer Forum.", "Spillway advantage, as the sync names it."),
    "estuary-solvency": _camp_docx(
        "Tamarack Summer Forum.", "Estuary solvency advocate, new in the addendum."
    ),
    # Byte-identical to a file the synthetic caselist discloses: ac2.
    "borrowed-grove-aff": CASELIST_DOCUMENT_BODIES["grove-round-1-aff"],
}


@dataclass(frozen=True, slots=True)
class SyntheticFile:
    """One member of a synthetic download: its path under the download root, and its body."""

    path: str
    body: str | None = None
    """An entry of :data:`DOCUMENT_BODIES`, or `None` for junk."""

    @property
    def content(self) -> bytes:
        if self.body is None:
            return b"\x00\x05\x16\x07 invented macOS metadata"
        return DOCUMENT_BODIES[self.body]


@dataclass(frozen=True, slots=True)
class SyntheticDownload:
    """One download: its name, which is also its wrapper directory, and its members."""

    name: str
    files: tuple[SyntheticFile, ...]


_JUNK = (
    SyntheticFile(path=".DS_Store"),
    SyntheticFile(path="__MACOSX/Tamarack/._TSF-Canal Subsidies Counterplan.docx"),
)

DOWNLOADS: tuple[SyntheticDownload, ...] = (
    SyntheticDownload(
        name="openev-2026-policy",
        files=(
            SyntheticFile("Brightwater Workshop - Orchard Kritik.docx", "orchard-kritik"),
            SyntheticFile("Brightwater/QDI-Tidewater Impact Turns.docx", "tidewater-impact-turns"),
            SyntheticFile("Quillfeather/Juniors Lab/QDI - Harbor Tariffs Aff.docx", "harbor-tariffs-aff"),
            SyntheticFile("Quillfeather/Juniors Lab/QDI - Harbor Tariffs Neg.docx", "harbor-tariffs-neg"),
            SyntheticFile("Quillfeather/Seniors Lab/Lighthouse Politics DA.docx", "lighthouse-politics"),
            SyntheticFile("Tamarack/TSF-Borrowed Grove Aff.docx", "borrowed-grove-aff"),
            SyntheticFile("Tamarack/TSF-Canal Subsidies Counterplan.docx", "canal-counterplan"),
            SyntheticFile("Tamarack/TSF-Canal Subsidies Counterplan_v2.docx", "canal-counterplan"),
            SyntheticFile("Tamarack/TSF-Reservoir Topicality.pdf", "reservoir-topicality-pdf"),
            SyntheticFile("Zephyr Scholars - Glacier Case Neg.docx", "glacier-case-neg"),
            SyntheticFile("openev-417-TSF-Spillway Advantage.docx", "spillway-advantage"),
            *_JUNK,
        ),
    ),
    SyntheticDownload(
        name="openev-2026-policy-addendum",
        files=(
            SyntheticFile("Quillfeather/Juniors Lab/QDI - Harbor Tariffs Aff.docx", "harbor-tariffs-aff"),
            SyntheticFile("Tamarack/TSF-Canal Subsidies Counterplan.docx", "canal-counterplan-revised"),
            SyntheticFile("Tamarack/TSF-Estuary Solvency Advocate.docx", "estuary-solvency"),
            SyntheticFile("Tamarack/TSF-Lighthouse Politics DA copy.docx", "lighthouse-politics"),
            _JUNK[0],
        ),
    ),
)


def build_download_zips(destination: Path) -> dict[str, Path]:
    """Write each download as `<name>.zip`, members under a `<name>/` wrapper, byte-identically."""
    built: dict[str, Path] = {}
    Path(destination).mkdir(parents=True, exist_ok=True)
    for download in DOWNLOADS:
        archive_path = Path(destination) / f"{download.name}.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member in sorted(download.files, key=lambda one: one.path):
                info = zipfile.ZipInfo(f"{download.name}/{member.path}", date_time=_ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, member.content)
        built[download.name] = archive_path
    return built


def build_download_directories(destination: Path) -> dict[str, Path]:
    """Write each download as an unpacked directory, which the importer reads the same way."""
    built: dict[str, Path] = {}
    for download in DOWNLOADS:
        root = Path(destination) / download.name
        for member in download.files:
            target = root / member.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(member.content)
        built[download.name] = root
    return built


def expected() -> dict[str, Any]:
    """The committed, hand-written expectations."""
    loaded: dict[str, Any] = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    return loaded


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    for name, path in build_download_zips(arguments.destination).items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    _main()

"""Three synthetic cumulative caselist archives, and the import summary they should produce.

Everything the archive importer (`v1-e30-t03`) is tested against is generated here. Nothing in
this module came from a real caselist: the schools are invented (`Maple Grove`, `Cedar Hollow`),
the team codes are invented (`QX`, `ZaLu`), the tournaments are invented, and every document is a
few hundred bytes this file writes from scratch. That is a rule, not a convenience —
`docs/policies/caselist-data-use.md` forbids a real school name, team code, filename or disclosure
path in any committed artefact, and the rulings merged with `v1-e31-t02` forbid real excerpts
outright. Verification against the real corpus is an operator run whose session report carries
counts and nothing else.

## What the three archives are

`testcl26-0901`, `testcl26-0908` and `testcl26-0915`: one fictional Lincoln-Douglas caselist,
three weekly archives, **cumulative** the way the real ones are. The 09-08 archive contains
everything the 09-01 archive contained and more; the 09-15 archive drops exactly one file. Each
archive is laid out the way OpenCaselist lays one out::

    testcl26-0915/<School>/<TeamCode>/<School>-<TeamCode>-<Side>-<Tournament>-<Round>.docx

## What is deliberately wrong with them

The filenames reproduce the ways real ones break, because a parser tested only against the
canonical pattern is a parser that drops files in week one (`v1-e30-t03` ac1):

* `Cedar Hollow-ZaLu-AFF-Harbor Classic.docx` — no round at all, side shouted.
* `Cedar Hollow-ZaLu-Negative-Harbor Classic-Octas.docx` — side spelled out, elimination round.
* `Northgate Prep-BeCo-Affirmative-Ridgeline Round Robin--Doubles.docx` — doubled hyphen, and a
  tournament whose own name contains the word "Round".
* `Northgate Prep-BeCo-Neg-02----Ridgeline Round Robin-Round 6.docx` — a numeric copy index right
  after the side, then four hyphens.
* `Riverbend Academy-MnPr-Pro-Seaside Cup-Finals.docx` — a Public Forum side in an LD caselist.
* `Riverbend Academy-MnPr-Aff-Seaside Cup-Quarters.pdf` — a PDF, stored unparsed.
* `Riverbend Academy-MnPr-Neg-Seaside Cup-Quarters.doc` — a legacy `.doc`, stored unparsed.
* `Maple Grove-QX-Aff-Grove City Invitational-Round 1 (1).docx` — a re-upload of a file the
  archive already holds.
* `notes about the harbor round.docx` — no structure at all: side UNKNOWN, with a warning.
* `Westfield-XY-Neg-Ridgeline Round Robin-Round 3.docx` — a filename prefix naming neither the
  school nor the team code its own directories name.
* `Maple Grove-QX-Neg-Bayview Open [2]-Semis.docx` — a bracketed copy number in the tournament.
* `Riverbend Academy-MnPr-Aff-Seaside Cup—Round 5.docx` — an em dash where a hyphen belongs.

and the junk every macOS-made archive carries: `__MACOSX/` AppleDouble entries, a `.DS_Store`, a
`~$` Word lock file, a symlink, and — in the zip form only, because a directory cannot hold one —
a `../escaped.docx` member that tries to write outside the staging root.

## Determinism

Two builds produce byte-identical archives: the document bodies are literals, and every zip entry
is written with a fixed timestamp and fixed compression. That is what lets
`expected_summary.json` state a distinct-SHA-256 count, and what makes ac3's "re-importing the
same snapshot produces identical manifest bytes" a property of the importer rather than of the
clock.

## The expected summary

:func:`expected_summary` states, as hand-written literals, what importing the three archives in
order must report. It does **not** run the importer — that is the point: the counts are worked out
from the table above by a person, and `packages/debate_core/tests/application/caselist/
test_import_service.py` fails when the importer disagrees with them. `expected_summary.json` is
the committed copy, and `test_build_synthetic_archives.py` fails when the two drift.

Run it by hand to look at what it makes::

    uv run python -m tests.fixtures.caselist.build_synthetic_archives /tmp/synthetic-caselist
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

__all__ = [
    "EXPECTED_SUMMARY_PATH",
    "SYNTHETIC_CASELIST",
    "SYNTHETIC_EVENT",
    "SYNTHETIC_SEASON",
    "SNAPSHOTS",
    "SyntheticMember",
    "SyntheticSnapshot",
    "build_snapshot_directories",
    "build_snapshot_zips",
    "expected_summary",
    "written_expected_summary",
]

SYNTHETIC_CASELIST = "testcl26"
"""The invented caselist slug. Shaped like a real one (`hsld26`) and belonging to no real season."""

SYNTHETIC_EVENT = "LD"
"""The event the fixture caselist debates, which decides that `Pro` is not one of its sides."""

SYNTHETIC_SEASON = "2026-27"

#: Where the committed expected summary lives, beside this file.
EXPECTED_SUMMARY_PATH = Path(__file__).parent / "expected_summary.json"

#: Fixed timestamp on every zip entry, so two builds are byte-identical. The earliest a zip can
#: record: DOS timestamps start in 1980 and `zipfile` refuses anything before.
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

#: Mode bits marking a zip entry as a symlink, the way macOS and Info-ZIP write one.
_SYMLINK_EXTERNAL_ATTRIBUTES = (stat.S_IFLNK | 0o777) << 16


# ------------------------------------------------------------------------------------------------
# Document bodies
# ------------------------------------------------------------------------------------------------


def _docx(paragraphs: tuple[str, ...]) -> bytes:
    """A minimal but genuinely valid `.docx`: a zip of the three parts Word insists on.

    Real enough that E31's parser can open it later, small enough to commit nothing — the archives
    are built into a temporary directory at test time, never checked in. The text is invented
    argument-shaped filler; it quotes no real evidence and no real card.
    """
    body = "".join(f"<w:p><w:r><w:t xml:space='preserve'>{text}</w:t></w:r></w:p>" for text in paragraphs)
    parts = {
        "[Content_Types].xml": (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
            "<Default Extension='rels' ContentType="
            "'application/vnd.openxmlformats-package.relationships+xml'/>"
            "<Override PartName='/word/document.xml' ContentType="
            "'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/>"
            "</Types>"
        ),
        "_rels/.rels": (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
            "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/"
            "relationships/officeDocument' Target='word/document.xml'/>"
            "</Relationships>"
        ),
        "word/document.xml": (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
            f"<w:body>{body}</w:body></w:document>"
        ),
    }
    return _deterministic_zip_bytes(parts)


def _pdf(title: str) -> bytes:
    """A minimal one-page PDF. Stored unparsed in V1; it exists to be a non-DOCX format."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n"
        b"%% " + title.encode("ascii") + b"\n"
        b"%%EOF\n"
    )


def _legacy_doc(title: str) -> bytes:
    """A legacy `.doc`: the OLE compound-file magic and filler.

    Not a readable Word 97 document and not meant to be. V1 stores `.doc` unparsed, so what the
    fixture needs from it is that it is distinct bytes with a `.doc` extension.
    """
    magic = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    return magic + b"\x00" * 24 + title.encode("ascii") + b"\x00" * 64


def _deterministic_zip_bytes(parts: dict[str, str]) -> bytes:
    """Zip `parts` into bytes that are identical on every machine and every run."""
    from io import BytesIO

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(parts):
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, parts[name])
    return buffer.getvalue()


#: Every distinct file body in the fixture, by the short name the tables below refer to it by.
#: Fourteen bodies, which is the distinct-SHA-256 count the importer has to arrive at.
DOCUMENT_BODIES: dict[str, bytes] = {
    "grove-round-1-aff": _docx(
        (
            "Grove City Invitational, Round 1, affirmative.",
            "Contention one: the fixture asserts nothing about the real world.",
        )
    ),
    "grove-round-2-neg-first": _docx(
        ("Grove City Invitational, Round 2, negative.", "As first disclosed on the first of September.")
    ),
    "grove-round-2-neg-revised": _docx(
        (
            "Grove City Invitational, Round 2, negative.",
            "Revised the following week: the same path, different bytes.",
        )
    ),
    "harbor-aff": _docx(("Harbor Classic, affirmative.", "This file's name states no round.")),
    "harbor-octas-neg": _docx(
        ("Harbor Classic, octafinals, negative.", "Taken down before the fifteenth of September.")
    ),
    "ridgeline-doubles-aff": _docx(
        ("Ridgeline Round Robin, doubles, affirmative.", "The tournament's own name contains 'Round'.")
    ),
    "ridgeline-round-6-neg": _docx(
        ("Ridgeline Round Robin, round six, negative.", "Filed under a numeric copy index.")
    ),
    "seaside-finals-pro": _docx(
        ("Seaside Cup, finals.", "Disclosed with a Public Forum side in a Lincoln-Douglas caselist.")
    ),
    "seaside-quarters-aff-pdf": _pdf("Seaside Cup quarters affirmative"),
    "seaside-quarters-neg-doc": _legacy_doc("Seaside Cup quarters negative"),
    "harbor-unstructured-notes": _docx(
        ("Notes about the harbor round.", "A filename with no structure the parser can anchor on.")
    ),
    "ridgeline-round-3-neg": _docx(
        ("Ridgeline Round Robin, round three, negative.", "Filed under a prefix its directories deny.")
    ),
    "bayview-semis-neg": _docx(
        ("Bayview Open, semifinals, negative.", "The tournament carries a bracketed copy number.")
    ),
    "seaside-round-5-aff": _docx(
        ("Seaside Cup, round five, affirmative.", "Separated from its round by an em dash.")
    ),
}


# ------------------------------------------------------------------------------------------------
# The archives
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SyntheticMember:
    """One member of a synthetic archive: where it sits, and what it is."""

    path: str
    """Its path relative to the archive root, e.g. `Maple Grove/QX/Maple Grove-QX-Aff-….docx`."""

    body: str | None = None
    """Which entry of :data:`DOCUMENT_BODIES` it holds, or `None` for junk with no body."""

    junk: str = ""
    """Why the importer must skip it, as a note to a reader. Empty for a real file."""

    symlink_target: str | None = None
    """For a symlink member, what it points at. Written as a real symlink in a directory."""

    zip_only: bool = False
    """True for a member a directory cannot hold: the `../` traversal entry."""

    @property
    def content(self) -> bytes:
        """The bytes this member holds."""
        if self.symlink_target is not None:
            return self.symlink_target.encode("utf-8")
        if self.body is None:
            return b"synthetic junk member\n"
        return DOCUMENT_BODIES[self.body]


@dataclass(frozen=True, slots=True)
class SyntheticSnapshot:
    """One weekly archive: its date, its directory name, and everything in it."""

    snapshot: date
    members: tuple[SyntheticMember, ...]

    @property
    def archive_name(self) -> str:
        """The archive's own name, e.g. `testcl26-0915` — slug and the date without its year."""
        return f"{SYNTHETIC_CASELIST}-{self.snapshot:%m%d}"

    def members_for(self, *, zip_form: bool) -> tuple[SyntheticMember, ...]:
        """The members a build of this form writes, sorted by path so a build is reproducible."""
        chosen = [member for member in self.members if zip_form or not member.zip_only]
        return tuple(sorted(chosen, key=lambda member: member.path))


# The junk every macOS-made archive carries, present in all three weeks because the archives are
# cumulative: what was in last week's zip is in this week's too.
_MACOS_AND_WORD_JUNK = (
    SyntheticMember(
        path="__MACOSX/Maple Grove/QX/._Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx",
        junk="AppleDouble metadata for a real member",
    ),
    SyntheticMember(path=".DS_Store", junk="Finder folder attributes"),
    SyntheticMember(
        path="Maple Grove/QX/~$ple Grove-QX-Aff-Grove City Invitational-Round 1.docx",
        junk="Word lock file for a document somebody had open",
    ),
)

#: Filed on the first of September, and still in every later archive.
_FIRST_WEEK_FILES = (
    SyntheticMember(
        path="Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx",
        body="grove-round-1-aff",
    ),
    SyntheticMember(
        path="Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-AFF-Harbor Classic.docx",
        body="harbor-aff",
    ),
    SyntheticMember(
        path="Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Negative-Harbor Classic-Octas.docx",
        body="harbor-octas-neg",
    ),
)

#: Added in the second week, and still there in the third.
_SECOND_WEEK_FILES = (
    SyntheticMember(
        path="Northgate Prep/BeCo/Northgate Prep-BeCo-Affirmative-Ridgeline Round Robin--Doubles.docx",
        body="ridgeline-doubles-aff",
    ),
    SyntheticMember(
        path="Northgate Prep/BeCo/Northgate Prep-BeCo-Neg-02----Ridgeline Round Robin-Round 6.docx",
        body="ridgeline-round-6-neg",
    ),
    SyntheticMember(
        path="Riverbend Academy/MnPr/Riverbend Academy-MnPr-Pro-Seaside Cup-Finals.docx",
        body="seaside-finals-pro",
    ),
    SyntheticMember(
        path="Riverbend Academy/MnPr/Riverbend Academy-MnPr-Aff-Seaside Cup-Quarters.pdf",
        body="seaside-quarters-aff-pdf",
    ),
    SyntheticMember(
        path="Riverbend Academy/MnPr/Riverbend Academy-MnPr-Neg-Seaside Cup-Quarters.doc",
        body="seaside-quarters-neg-doc",
    ),
    # A re-upload: the same bytes as the Round 1 affirmative, under a browser's "(1)" name.
    SyntheticMember(
        path="Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1 (1).docx",
        body="grove-round-1-aff",
    ),
    # The same bytes again, disclosed by a different team: one source document, two disclosures.
    SyntheticMember(
        path="Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Aff-Grove City Invitational-Round 3.docx",
        body="grove-round-1-aff",
    ),
    SyntheticMember(
        path="Cedar Hollow/ZaLu/notes about the harbor round.docx",
        body="harbor-unstructured-notes",
    ),
    SyntheticMember(
        path="Northgate Prep/BeCo/Westfield-XY-Neg-Ridgeline Round Robin-Round 3.docx",
        body="ridgeline-round-3-neg",
    ),
)

#: Added in the third week.
_THIRD_WEEK_FILES = (
    SyntheticMember(
        path="Maple Grove/QX/Maple Grove-QX-Neg-Bayview Open [2]-Semis.docx",
        body="bayview-semis-neg",
    ),
    SyntheticMember(
        path="Riverbend Academy/MnPr/Riverbend Academy-MnPr-Aff-Seaside Cup—Round 5.docx",
        body="seaside-round-5-aff",
    ),
)

#: The unsafe members, added in the third week so the first two stay a plain cumulative pair.
_UNSAFE_MEMBERS = (
    SyntheticMember(
        path="Cedar Hollow/ZaLu/latest-aff.docx",
        junk="symlink to a real member",
        symlink_target="Cedar Hollow-ZaLu-AFF-Harbor Classic.docx",
    ),
    SyntheticMember(
        path="../escaped.docx",
        body="harbor-aff",
        junk="zip-slip: a member naming a path outside the staging root",
        zip_only=True,
    ),
)

#: The Round 2 negative, as first disclosed and as revised a week later: one path, two bodies.
_ROUND_TWO_NEGATIVE_PATH = "Maple Grove/QX/Maple Grove-QX-Neg-Grove City Invitational-Round 2.docx"

SNAPSHOTS: tuple[SyntheticSnapshot, ...] = (
    SyntheticSnapshot(
        snapshot=date(2026, 9, 1),
        members=(
            *_FIRST_WEEK_FILES,
            SyntheticMember(path=_ROUND_TWO_NEGATIVE_PATH, body="grove-round-2-neg-first"),
            *_MACOS_AND_WORD_JUNK,
        ),
    ),
    SyntheticSnapshot(
        snapshot=date(2026, 9, 8),
        members=(
            *_FIRST_WEEK_FILES,
            # The same path as last week, holding different bytes.
            SyntheticMember(path=_ROUND_TWO_NEGATIVE_PATH, body="grove-round-2-neg-revised"),
            *_SECOND_WEEK_FILES,
            *_MACOS_AND_WORD_JUNK,
        ),
    ),
    SyntheticSnapshot(
        snapshot=date(2026, 9, 15),
        members=(
            # The Harbor Classic octafinals negative is gone: taken down between the two weeks.
            *(member for member in _FIRST_WEEK_FILES if member.body != "harbor-octas-neg"),
            SyntheticMember(path=_ROUND_TWO_NEGATIVE_PATH, body="grove-round-2-neg-revised"),
            *_SECOND_WEEK_FILES,
            *_THIRD_WEEK_FILES,
            *_UNSAFE_MEMBERS,
            *_MACOS_AND_WORD_JUNK,
        ),
    ),
)


# ------------------------------------------------------------------------------------------------
# Building
# ------------------------------------------------------------------------------------------------


def build_snapshot_directories(destination: Path) -> dict[date, Path]:
    """Write the three archives as unpacked directories under `destination`.

    Returns the directory of each snapshot, keyed by its date, which is what the importer is
    pointed at. The `../escaped.docx` member is left out: a directory cannot hold one, and
    writing it would put a file beside the staging root rather than inside it.
    """
    built: dict[date, Path] = {}
    for snapshot in SNAPSHOTS:
        root = Path(destination) / snapshot.archive_name
        for member in snapshot.members_for(zip_form=False):
            target = root / member.path
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.symlink_target is not None:
                target.unlink(missing_ok=True)
                os.symlink(member.symlink_target, target)
                continue
            target.write_bytes(member.content)
        built[snapshot.snapshot] = root
    return built


def build_snapshot_zips(destination: Path) -> dict[date, Path]:
    """Write the three archives as zips under `destination`, one top-level directory each.

    Returns each zip's path, keyed by its snapshot date. Members are written under the archive's
    own directory (`testcl26-0915/…`), which is how a downloaded weekly archive is shaped, and
    with a fixed timestamp so that two builds produce identical bytes. The `../escaped.docx`
    member is the exception and is written at the top level, because that is where a real
    zip-slip entry sits.
    """
    built: dict[date, Path] = {}
    Path(destination).mkdir(parents=True, exist_ok=True)
    for snapshot in SNAPSHOTS:
        archive_path = Path(destination) / f"{snapshot.archive_name}.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member in snapshot.members_for(zip_form=True):
                # The traversal member keeps its own name. Written under the archive directory it
                # would normalize back inside the staging root — `testcl26-0915/../escaped.docx`
                # is just `escaped.docx` — and would test nothing.
                name = (
                    member.path if member.path.startswith("../") else f"{snapshot.archive_name}/{member.path}"
                )
                info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (
                    _SYMLINK_EXTERNAL_ATTRIBUTES if member.symlink_target is not None else 0o644 << 16
                )
                archive.writestr(info, member.content)
        built[snapshot.snapshot] = archive_path
    return built


# ------------------------------------------------------------------------------------------------
# The expected summary
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExpectedSnapshot:
    """What importing one of the three archives must report.

    The classification counts are written out by hand from the tables above. They are the
    assertion, so deriving them from the importer would make the test agree with whatever the
    importer happened to do.
    """

    snapshot: date
    new: int
    unchanged: int
    changed: int
    duplicate: int
    removed: int
    suppressed: int = 0
    skipped_directory: int = 0
    skipped_zip: int = 0
    distinct_sha256_after: int = 0
    disclosures: int = 0
    warnings: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)


EXPECTED_SNAPSHOTS: tuple[ExpectedSnapshot, ...] = (
    ExpectedSnapshot(
        snapshot=date(2026, 9, 1),
        new=4,
        unchanged=0,
        changed=0,
        duplicate=0,
        removed=0,
        skipped_directory=3,
        skipped_zip=3,
        distinct_sha256_after=4,
        disclosures=4,
        warnings=1,
        notes=(
            "Four files, all new; nothing to compare against.",
            "One warning: the Harbor Classic affirmative states no round.",
        ),
    ),
    ExpectedSnapshot(
        snapshot=date(2026, 9, 8),
        new=7,
        unchanged=3,
        changed=1,
        duplicate=2,
        removed=0,
        skipped_directory=3,
        skipped_zip=3,
        distinct_sha256_after=12,
        disclosures=13,
        warnings=4,
        notes=(
            "Seven bodies appear for the first time; the Round 2 negative is revised in place.",
            "Two members repeat the Round 1 affirmative's bytes: a re-upload and another team's copy.",
            "Warnings, one member each: the Harbor Classic affirmative states no round; a Public "
            "Forum side in an LD caselist; a filename with no side token to anchor on; a filename "
            "prefix naming neither the school nor the team code its directories name.",
        ),
    ),
    ExpectedSnapshot(
        snapshot=date(2026, 9, 15),
        new=2,
        unchanged=12,
        changed=0,
        duplicate=0,
        removed=1,
        skipped_directory=4,
        skipped_zip=5,
        distinct_sha256_after=14,
        disclosures=14,
        warnings=4,
        notes=(
            "Two new bodies; everything else carried forward unchanged.",
            "The same four warnings as the second week: they belong to members still in the archive.",
            "The Harbor Classic octafinals negative is absent: one REMOVED.",
            "The directory build skips a symlink; the zip build skips that and a `../` member.",
        ),
    ),
)


def expected_summary() -> dict[str, object]:
    """The whole expected result of importing the three archives in order.

    `distinct_sha256` is computed from the bodies this module actually generates — it is a fact
    about the fixture, not about the importer — while every classification count is a literal.
    """
    distinct = {hashlib.sha256(body).hexdigest() for body in DOCUMENT_BODIES.values()}
    return {
        "caselist": SYNTHETIC_CASELIST,
        "event": SYNTHETIC_EVENT,
        "season": SYNTHETIC_SEASON,
        "description": (
            "Expected import summary for the three synthetic cumulative archives built by "
            "build_synthetic_archives.py. Schools, team codes, tournaments and document bodies "
            "are invented; no real caselist content appears here or in the archives."
        ),
        "snapshots": [
            {
                "snapshot": expected.snapshot.isoformat(),
                "archive": f"{SYNTHETIC_CASELIST}-{expected.snapshot:%m%d}",
                "classifications": {
                    "NEW": expected.new,
                    "UNCHANGED": expected.unchanged,
                    "CHANGED": expected.changed,
                    "DUPLICATE": expected.duplicate,
                    "REMOVED": expected.removed,
                    "SUPPRESSED": expected.suppressed,
                },
                "skipped": {
                    "directory": expected.skipped_directory,
                    "zip": expected.skipped_zip,
                },
                "disclosures": expected.disclosures,
                "warnings": expected.warnings,
                "distinct_sha256_after": expected.distinct_sha256_after,
                "notes": list(expected.notes),
            }
            for expected in EXPECTED_SNAPSHOTS
        ],
        "totals": {
            "distinct_sha256": len(distinct),
            "stored_blobs": len(distinct),
            "document_bodies": len(DOCUMENT_BODIES),
        },
    }


def written_expected_summary() -> dict[str, object]:
    """Read the committed `expected_summary.json`."""
    parsed = json.loads(EXPECTED_SUMMARY_PATH.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def write_expected_summary() -> Path:
    """Write `expected_summary.json` from :func:`expected_summary`. Run when the fixture changes."""
    EXPECTED_SUMMARY_PATH.write_text(
        json.dumps(expected_summary(), indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return EXPECTED_SUMMARY_PATH


def main() -> None:
    """Build the archives into a directory, for looking at what the tests run against."""
    parser = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    parser.add_argument("destination", type=Path, help="Directory to build the archives into.")
    parser.add_argument(
        "--write-expected-summary",
        action="store_true",
        help="Rewrite the committed expected_summary.json from the literals in this module.",
    )
    arguments = parser.parse_args()
    directories = build_snapshot_directories(arguments.destination)
    zips = build_snapshot_zips(arguments.destination)
    for snapshot in SNAPSHOTS:
        print(f"{snapshot.archive_name}: {directories[snapshot.snapshot]}  {zips[snapshot.snapshot]}")
    if arguments.write_expected_summary:
        print(f"wrote {write_expected_summary()}")


if __name__ == "__main__":
    main()

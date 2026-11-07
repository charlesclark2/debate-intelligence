"""The coach's labels file is guarded (`v1-e32-t58`): a changed file is refused, and every sitting keeps the
file it replaces.

On 2026-11-05 Microsoft Excel saved an older copy over the coach's labelled sample, and two sittings were
lost without any command noticing (`v1-e32-t55`'s report). So the file now has a **sidecar** beside it,
`<name>.sha256` (:func:`digest_path`): one line in the format `shasum -a 256` prints and checks, the file's
SHA-256 in lower-case hex, two spaces and the file's name (:func:`digest_line`). Only two things write it:

* the coach's sitting (`scripts/relabel_coach_sample.py`, :func:`write_sitting`), which first keeps a dated
  copy of the file it replaces (:func:`keep_dated_copy`, never over an existing copy), then writes the CSV
  through its `.incoming` file and `os.replace`, and only then the new sidecar. A sitting that stops between
  the two leaves a file its sidecar does not describe, which is refused, never a silent mismatch;
* the one-time step for a file no sitting has recorded (`scripts/record_coach_sample_digest.py`,
  :func:`record_first_digest`), run by the operator, which refuses to overwrite a sidecar and records only
  the digest the operator expects.

Every command that scores, replays or re-records against the labels reads the file through
:func:`read_labels_file`: the bytes are read once, their SHA-256 checked against the sidecar, and only those
bytes are decoded and read, so nothing can change between the check and the read. A refusal is a
:class:`LabelsFileRefused`, with its own error code, naming both digests shortened, the sidecar's path and the
command that writes it. Nothing here reads a row: digests, names and paths only.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from debate_core.application.errors import DomainError

__all__ = [
    "COPY_MARK",
    "DIGEST_SUFFIX",
    "RECORD_COMMAND",
    "SITTING_COMMAND",
    "LabelsDigestAlreadyRecorded",
    "LabelsDigestMissing",
    "LabelsDigestUnreadable",
    "LabelsFileChanged",
    "LabelsFileNotTheExpectedOne",
    "LabelsFileRefused",
    "SittingFiles",
    "check_labels",
    "digest_line",
    "digest_path",
    "keep_dated_copy",
    "labels_digest",
    "read_labels_file",
    "record_first_digest",
    "recorded_digest",
    "short_digest",
    "write_sitting",
]

DIGEST_SUFFIX: Final = ".sha256"
"""Added to the labels file's whole name for its sidecar: `coach-sample-labelled.csv.sha256`."""

COPY_MARK: Final = ".before-sitting-"
"""Between the labels file's stem and the sitting's date and time in a dated copy's name."""

SITTING_COMMAND: Final = "uv run python scripts/relabel_coach_sample.py"
"""The command that writes the labels file and its sidecar."""

RECORD_COMMAND: Final = "uv run python scripts/record_coach_sample_digest.py"
"""The one-time step that records the digest of a file no sitting has recorded."""

SHORT_DIGEST: Final = 12
"""Hex digits of a digest a refusal prints: enough to tell two files apart, short enough to read."""

_LINE: Final = re.compile(r"([0-9a-f]{64})  ([^\n]+)\n?")


def digest_path(sample: Path) -> Path:
    """The sidecar beside `sample`: its whole name with :data:`DIGEST_SUFFIX` added."""
    return sample.with_name(f"{sample.name}{DIGEST_SUFFIX}")


def labels_digest(data: bytes) -> str:
    """The SHA-256 of the labels file's bytes, lower-case hex."""
    return hashlib.sha256(data).hexdigest()


def short_digest(digest: str) -> str:
    """The first :data:`SHORT_DIGEST` hex digits of `digest`, as a refusal prints it."""
    return digest[:SHORT_DIGEST]


def digest_line(digest: str, sample: Path) -> str:
    """The sidecar's one line, as `shasum -a 256` prints it: the digest, two spaces, the file's name."""
    return f"{digest}  {sample.name}\n"


class LabelsFileRefused(DomainError):
    """A labels file no command may score, replay or re-record against: named by digest and path only."""

    def __init__(self, message: str, sample: Path, *, found: str, hint: str) -> None:
        self.labels_file = str(sample)
        """The labels file refused."""
        self.sidecar = str(digest_path(sample))
        """The sidecar that records the digest the file must have."""
        self.found = short_digest(found)
        """The file's SHA-256 now, shortened."""
        self.hint = hint
        super().__init__(message)


class LabelsFileChanged(LabelsFileRefused):
    """The labels file's SHA-256 is not the one its sidecar records: it was written outside a sitting, or a
    sitting stopped between the file and its sidecar."""

    def __init__(self, sample: Path, *, found: str, recorded: str) -> None:
        self.recorded = short_digest(recorded)
        """The SHA-256 the sidecar records, shortened."""
        super().__init__(
            f"the labels file {sample.name} has SHA-256 {short_digest(found)}…, but its sidecar "
            f"{digest_path(sample)} records {short_digest(recorded)}…: it changed after the last sitting "
            f"wrote it. Only a sitting writes the file and its sidecar ({SITTING_COMMAND}); nothing was read",
            sample,
            found=found,
            hint="Do not record the new digest, and do not open the file in a spreadsheet app. Keep the file "
            "as it is and tell the PM: the dated copies beside it hold the file each sitting replaced.",
        )


class LabelsDigestMissing(LabelsFileRefused):
    """The labels file has no sidecar: no sitting since `v1-e32-t58` wrote it, and no one recorded it."""

    def __init__(self, sample: Path, *, found: str) -> None:
        super().__init__(
            f"the labels file {sample.name} (SHA-256 {short_digest(found)}…) has no sidecar at "
            f"{digest_path(sample)}, so nothing says which file the last sitting wrote. A sitting writes it "
            f"({SITTING_COMMAND}); nothing was read",
            sample,
            found=found,
            hint="Once, for a file a sitting wrote before the sidecar existed: "
            f"{RECORD_COMMAND} --sample <the labels file> "
            "--expect <the SHA-256 that sitting's record gives>. It records the digest only if the file "
            "still has it, and never over a sidecar.",
        )


class LabelsDigestUnreadable(LabelsFileRefused):
    """The sidecar is there but is not one line of a SHA-256 and a name."""

    def __init__(self, sample: Path, *, found: str) -> None:
        super().__init__(
            f"the sidecar {digest_path(sample)} of the labels file {sample.name} (SHA-256 "
            f"{short_digest(found)}…) is not one line of a SHA-256 and a name. A sitting writes it "
            f"({SITTING_COMMAND}); nothing was read",
            sample,
            found=found,
            hint="Do not edit the sidecar or the file. Tell the PM; the dated copies beside the file hold "
            "the file each sitting replaced.",
        )


class LabelsDigestAlreadyRecorded(DomainError):
    """The one-time step found a sidecar already there, and never overwrites one."""

    def __init__(self, sample: Path) -> None:
        self.sidecar = str(digest_path(sample))
        """The sidecar already there."""
        self.hint = "Nothing to record: the sidecar is there. Run the scoring command; it checks the file."
        super().__init__(f"the labels file {sample.name} already has a sidecar at {digest_path(sample)}")


class LabelsFileNotTheExpectedOne(DomainError):
    """The one-time step found a file whose SHA-256 is not the one the operator expected."""

    def __init__(self, sample: Path, *, found: str, expected: str) -> None:
        self.labels_file = str(sample)
        """The labels file."""
        self.found = short_digest(found)
        """The file's SHA-256 now, shortened."""
        self.expected = short_digest(expected)
        """The SHA-256 the operator expected, shortened."""
        self.hint = "Nothing was recorded. Keep the file as it is and tell the PM."
        super().__init__(
            f"the labels file {sample.name} has SHA-256 {short_digest(found)}…, not the expected "
            f"{short_digest(expected)}…: it is not the file that sitting wrote"
        )


def recorded_digest(sample: Path, *, found: str) -> str:
    """The SHA-256 the sidecar of `sample` records.

    Raises :class:`LabelsDigestMissing` when there is no sidecar, and :class:`LabelsDigestUnreadable` when it
    is not one line of a lower-case SHA-256, two spaces and a name. `found` is the file's own digest, which
    the refusal names.
    """
    try:
        text = digest_path(sample).read_bytes().decode("ascii")
    except FileNotFoundError:
        raise LabelsDigestMissing(sample, found=found) from None
    except UnicodeDecodeError:
        raise LabelsDigestUnreadable(sample, found=found) from None
    line = _LINE.fullmatch(text)
    if line is None:
        raise LabelsDigestUnreadable(sample, found=found)
    return line.group(1)


def check_labels(sample: Path, data: bytes) -> str:
    """The SHA-256 of `data`, the bytes of the labels file `sample`, once it equals the sidecar's.

    Raises :class:`LabelsFileChanged` when it does not, and what :func:`recorded_digest` raises.
    """
    found = labels_digest(data)
    recorded = recorded_digest(sample, found=found)
    if found != recorded:
        raise LabelsFileChanged(sample, found=found, recorded=recorded)
    return found


def read_labels_file(sample: Path) -> str:
    """The labels file's text, read once and decoded only after its SHA-256 matched its sidecar.

    Every command that scores, replays or re-records against the coach's labels reads them through this.
    The text keeps its line endings, as `open(newline="")` would.
    """
    data = sample.read_bytes()
    check_labels(sample, data)
    return data.decode("utf-8")


def _replace(target: Path, data: bytes) -> None:
    """Write `data` to `.<name>.incoming` beside `target`, then move it into place with `os.replace`."""
    incoming = target.with_name(f".{target.name}.incoming")
    incoming.write_bytes(data)
    os.replace(incoming, target)


def keep_dated_copy(sample: Path, data: bytes, at: datetime) -> Path:
    """Keep `data`, the file a sitting is about to replace, beside `sample` under the sitting's date and time.

    The copy is `<stem>.before-sitting-YYYY-MM-DD-HHMM<suffix>`, and `-2`, `-3`, … after the time when a
    copy of that minute is already there: an existing copy is never overwritten (the file is opened for
    exclusive creation). Raises `OSError` when the copy read back is not `data`.
    """
    stamp = f"{sample.stem}{COPY_MARK}{at:%Y-%m-%d-%H%M}"
    number = 1
    while True:
        copy = sample.with_name(f"{stamp}{'' if number == 1 else f'-{number}'}{sample.suffix}")
        try:
            with copy.open("xb") as handle:
                handle.write(data)
        except FileExistsError:
            number += 1
            continue
        break
    if copy.read_bytes() != data:
        raise OSError(f"the copy at {copy} does not match the file it keeps")
    return copy


@dataclass(frozen=True, slots=True)
class SittingFiles:
    """What a sitting wrote: the dated copy of the file it replaced, and the new file's SHA-256."""

    copy: Path
    digest: str


def write_sitting(sample: Path, text: str, *, at: datetime) -> SittingFiles:
    """Write a sitting's labels: the dated copy of the file it replaces, then the CSV, then the sidecar.

    The copy keeps the bytes on disk at the moment of writing, the file the sitting replaces. The CSV goes
    through its `.incoming` file and `os.replace`, and the sidecar likewise after it, so a sitting that stops
    in between leaves a file its sidecar does not describe: a refusal, never a silent mismatch.
    """
    copy = keep_dated_copy(sample, sample.read_bytes(), at)
    data = text.encode("utf-8")
    _replace(sample, data)
    digest = labels_digest(data)
    _replace(digest_path(sample), digest_line(digest, sample).encode("ascii"))
    return SittingFiles(copy=copy, digest=digest)


def record_first_digest(sample: Path, *, expect: str) -> str:
    """The one-time step: record the SHA-256 of a labels file that has no sidecar, if it is `expect`.

    Raises :class:`LabelsFileNotTheExpectedOne` when the file's digest is not `expect`, and
    :class:`LabelsDigestAlreadyRecorded` when a sidecar is there: it is opened for exclusive creation, so one
    is never overwritten. Either way nothing is written.
    """
    found = labels_digest(sample.read_bytes())
    if found != expect:
        raise LabelsFileNotTheExpectedOne(sample, found=found, expected=expect)
    try:
        with digest_path(sample).open("x", encoding="ascii", newline="") as handle:
            handle.write(digest_line(found, sample))
    except FileExistsError:
        raise LabelsDigestAlreadyRecorded(sample) from None
    return found

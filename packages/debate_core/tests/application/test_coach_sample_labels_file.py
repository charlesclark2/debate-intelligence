"""The coach's labels file is guarded (`v1-e32-t58`): a changed file is refused, and every sitting keeps the
file it replaces.

Every label here is invented (`invented-da`, `made-up-cp`); none is from the coach's sample. The expected
names, lines and digests are written from the rule, with `hashlib` computing a digest of bytes the test
chose, never from the module under test.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

import pytest

import debate_core.application.coach_sample_labels_file as labels_file
from debate_core.application.coach_sample_labels_file import (
    LabelsDigestAlreadyRecorded,
    LabelsDigestMissing,
    LabelsDigestUnreadable,
    LabelsFileChanged,
    LabelsFileNotTheExpectedOne,
    check_labels,
    digest_line,
    digest_path,
    keep_dated_copy,
    read_labels_file,
    record_first_digest,
    write_sitting,
)
from debate_core.application.errors import error_code_of

INVENTED = b"sample_row,position\n1,invented-da\n2,made-up-cp\n"
RELABELLED = "sample_row,position\n1,invented-da\n2,at:invented-da\n"
RELABELLED_AGAIN = "sample_row,position\n1,none\n2,at:invented-da\n"
NAME = "coach-sample-labelled.csv"
SIDECAR = "coach-sample-labelled.csv.sha256"
AT = datetime(2026, 11, 7, 14, 30, 5)
FIRST_COPY = "coach-sample-labelled.before-sitting-2026-11-07-1430.csv"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def labels(tmp_path: Path, data: bytes = INVENTED, *, recorded: bytes | None = INVENTED) -> Path:
    """The labels file holding `data`, with a sidecar recording the digest of `recorded` (none for None)."""
    sample = tmp_path / NAME
    sample.write_bytes(data)
    if recorded is not None:
        (tmp_path / SIDECAR).write_text(f"{sha256(recorded)}  {NAME}\n", encoding="ascii")
    return sample


# ------------------------------------------------------------------------------------------------
# The sidecar
# ------------------------------------------------------------------------------------------------


def test_the_labels_sidecar_sits_beside_the_file_under_its_whole_name() -> None:
    assert digest_path(Path("/somewhere") / NAME) == Path("/somewhere") / SIDECAR


def test_the_labels_sidecar_line_is_shasums_digest_two_spaces_and_the_name() -> None:
    assert digest_line("ab" * 32, Path("/somewhere") / NAME) == f"{'ab' * 32}  {NAME}\n"


def test_a_labels_file_its_sidecar_records_is_read_with_its_line_endings(tmp_path: Path) -> None:
    data = b"sample_row,position\r\n1,invented-da\r\n"
    sample = labels(tmp_path, data, recorded=data)

    assert read_labels_file(sample) == "sample_row,position\r\n1,invented-da\r\n"
    assert check_labels(sample, data) == sha256(data)


# ------------------------------------------------------------------------------------------------
# A changed file, and a missing or unreadable sidecar, are refused
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "changed",
    [
        pytest.param(b"sample_row,position\n1,invented-da\n2,none\n", id="a label changed"),
        pytest.param(INVENTED.replace(b"\n", b"\r\n"), id="saved with CRLF line endings"),
        pytest.param(b"\xef\xbb\xbf" + INVENTED, id="saved with a byte order mark"),
        pytest.param(INVENTED[:-1], id="the last line ending dropped"),
    ],
)
def test_a_changed_labels_file_is_refused_naming_both_digests_the_sidecar_and_the_command(
    tmp_path: Path, changed: bytes
) -> None:
    sample = labels(tmp_path, changed, recorded=INVENTED)

    with pytest.raises(LabelsFileChanged) as refused:
        read_labels_file(sample)

    message = str(refused.value)
    assert sha256(changed)[:12] in message and sha256(INVENTED)[:12] in message
    assert sha256(changed) not in message and sha256(INVENTED) not in message
    assert str(tmp_path / SIDECAR) in message
    assert "uv run python scripts/relabel_coach_sample.py" in message
    assert error_code_of(refused.value) == "LABELS_FILE_CHANGED"
    assert (refused.value.found, refused.value.recorded) == (sha256(changed)[:12], sha256(INVENTED)[:12])
    assert refused.value.sidecar == str(tmp_path / SIDECAR)
    assert "spreadsheet" in refused.value.hint


def test_a_labels_file_with_no_sidecar_is_refused_with_the_one_time_step(tmp_path: Path) -> None:
    sample = labels(tmp_path, recorded=None)

    with pytest.raises(LabelsDigestMissing) as refused:
        read_labels_file(sample)

    message = str(refused.value)
    assert sha256(INVENTED)[:12] in message and sha256(INVENTED) not in message
    assert str(tmp_path / SIDECAR) in message
    assert "uv run python scripts/relabel_coach_sample.py" in message
    assert error_code_of(refused.value) == "LABELS_DIGEST_MISSING"
    assert "uv run python scripts/record_coach_sample_digest.py --sample" in refused.value.hint
    assert "--expect" in refused.value.hint


@pytest.mark.parametrize(
    "sidecar",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"not a digest\n", id="not a digest"),
        pytest.param(f"{sha256(INVENTED).upper()}  {NAME}\n".encode(), id="upper-case hex"),
        pytest.param(f"{sha256(INVENTED)} {NAME}\n".encode(), id="one space"),
        pytest.param(f"{sha256(INVENTED)}\n".encode(), id="no name"),
        pytest.param(f"{sha256(INVENTED)}  {NAME}\n{sha256(INVENTED)}  {NAME}\n".encode(), id="two lines"),
        pytest.param(f"{sha256(INVENTED)[:-1]}  {NAME}\n".encode(), id="63 hex digits"),
        pytest.param(b"\xff\xfe", id="not ascii"),
    ],
)
def test_an_unreadable_labels_sidecar_is_refused(tmp_path: Path, sidecar: bytes) -> None:
    sample = labels(tmp_path, recorded=None)
    (tmp_path / SIDECAR).write_bytes(sidecar)

    with pytest.raises(LabelsDigestUnreadable) as refused:
        read_labels_file(sample)

    assert error_code_of(refused.value) == "LABELS_DIGEST_UNREADABLE"
    assert str(tmp_path / SIDECAR) in str(refused.value)


def test_a_labels_sidecar_without_its_last_line_ending_is_read(tmp_path: Path) -> None:
    sample = labels(tmp_path, recorded=None)
    (tmp_path / SIDECAR).write_text(f"{sha256(INVENTED)}  {NAME}", encoding="ascii")

    assert read_labels_file(sample) == INVENTED.decode()


# ------------------------------------------------------------------------------------------------
# A sitting: the dated copy, then the labels, then the sidecar
# ------------------------------------------------------------------------------------------------


def _copies(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.glob("*.before-sitting-*"))


def test_a_sitting_writes_the_dated_copy_then_the_labels_file_then_its_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sample = labels(tmp_path)
    seen: list[tuple[str, list[str], bytes, str]] = []
    replace = os.replace

    def watched(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        seen.append(
            (Path(target).name, _copies(tmp_path), sample.read_bytes(), (tmp_path / SIDECAR).read_text("ascii"))
        )
        replace(source, target)

    monkeypatch.setattr(labels_file.os, "replace", watched)

    written = write_sitting(sample, RELABELLED, at=AT)

    old_line = f"{sha256(INVENTED)}  {NAME}\n"
    assert seen == [
        (NAME, [FIRST_COPY], INVENTED, old_line),
        (SIDECAR, [FIRST_COPY], RELABELLED.encode(), old_line),
    ]
    assert (tmp_path / FIRST_COPY).read_bytes() == INVENTED
    assert sample.read_bytes() == RELABELLED.encode()
    assert (tmp_path / SIDECAR).read_text("ascii") == f"{sha256(RELABELLED.encode())}  {NAME}\n"
    assert (written.copy, written.digest) == (tmp_path / FIRST_COPY, sha256(RELABELLED.encode()))
    assert read_labels_file(sample) == RELABELLED
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted([NAME, SIDECAR, FIRST_COPY])


def test_a_second_sitting_in_the_same_minute_never_overwrites_the_first_labels_copy(tmp_path: Path) -> None:
    sample = labels(tmp_path)

    write_sitting(sample, RELABELLED, at=AT)
    second = write_sitting(sample, RELABELLED_AGAIN, at=AT.replace(second=50))
    third = write_sitting(sample, INVENTED.decode(), at=AT.replace(second=59))

    assert _copies(tmp_path) == [
        "coach-sample-labelled.before-sitting-2026-11-07-1430-2.csv",
        "coach-sample-labelled.before-sitting-2026-11-07-1430-3.csv",
        FIRST_COPY,
    ]
    assert (tmp_path / FIRST_COPY).read_bytes() == INVENTED
    assert second.copy.read_bytes() == RELABELLED.encode()
    assert third.copy.read_bytes() == RELABELLED_AGAIN.encode()
    assert read_labels_file(sample) == INVENTED.decode()


def test_a_labels_copy_already_there_is_never_overwritten(tmp_path: Path) -> None:
    sample = labels(tmp_path)
    (tmp_path / FIRST_COPY).write_bytes(b"sample_row,position\n1,older-k\n")

    copy = keep_dated_copy(sample, INVENTED, AT)

    assert (tmp_path / FIRST_COPY).read_bytes() == b"sample_row,position\n1,older-k\n"
    assert copy == tmp_path / "coach-sample-labelled.before-sitting-2026-11-07-1430-2.csv"
    assert copy.read_bytes() == INVENTED


class SittingStopped(BaseException):
    """The power cut, or the Ctrl-C, between two of a sitting's writes."""


def test_a_sitting_stopped_before_the_sidecar_leaves_a_labels_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sample = labels(tmp_path)
    replace = os.replace

    def stops_at_the_sidecar(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        if Path(target).name == SIDECAR:
            raise SittingStopped
        replace(source, target)

    monkeypatch.setattr(labels_file.os, "replace", stops_at_the_sidecar)
    with pytest.raises(SittingStopped):
        write_sitting(sample, RELABELLED, at=AT)
    monkeypatch.undo()

    with pytest.raises(LabelsFileChanged) as refused:
        read_labels_file(sample)
    assert (refused.value.found, refused.value.recorded) == (
        sha256(RELABELLED.encode())[:12],
        sha256(INVENTED)[:12],
    )
    assert (tmp_path / FIRST_COPY).read_bytes() == INVENTED


def test_a_sitting_stopped_before_the_labels_file_leaves_it_as_its_sidecar_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sample = labels(tmp_path)

    def stops(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        raise SittingStopped

    monkeypatch.setattr(labels_file.os, "replace", stops)
    with pytest.raises(SittingStopped):
        write_sitting(sample, RELABELLED, at=AT)
    monkeypatch.undo()

    assert read_labels_file(sample) == INVENTED.decode()
    assert (tmp_path / FIRST_COPY).read_bytes() == INVENTED


# ------------------------------------------------------------------------------------------------
# The one-time step
# ------------------------------------------------------------------------------------------------


def test_the_one_time_step_records_the_labels_digest_it_expects(tmp_path: Path) -> None:
    sample = labels(tmp_path, recorded=None)

    assert record_first_digest(sample, expect=sha256(INVENTED)) == sha256(INVENTED)

    assert (tmp_path / SIDECAR).read_bytes() == f"{sha256(INVENTED)}  {NAME}\n".encode()
    assert read_labels_file(sample) == INVENTED.decode()


def test_the_one_time_step_refuses_an_existing_labels_sidecar(tmp_path: Path) -> None:
    other = b"sample_row,position\n1,older-k\n"
    sample = labels(tmp_path, recorded=other)
    before = (tmp_path / SIDECAR).read_bytes()

    with pytest.raises(LabelsDigestAlreadyRecorded) as refused:
        record_first_digest(sample, expect=sha256(INVENTED))

    assert (tmp_path / SIDECAR).read_bytes() == before
    assert error_code_of(refused.value) == "LABELS_DIGEST_ALREADY_RECORDED"
    assert str(tmp_path / SIDECAR) in str(refused.value)


def test_the_one_time_step_refuses_a_labels_file_that_is_not_the_expected_one(tmp_path: Path) -> None:
    sample = labels(tmp_path, recorded=None)
    expected = sha256(b"sample_row,position\n1,older-k\n")

    with pytest.raises(LabelsFileNotTheExpectedOne) as refused:
        record_first_digest(sample, expect=expected)

    assert not (tmp_path / SIDECAR).exists()
    message = str(refused.value)
    assert sha256(INVENTED)[:12] in message and expected[:12] in message
    assert error_code_of(refused.value) == "LABELS_FILE_NOT_THE_EXPECTED_ONE"

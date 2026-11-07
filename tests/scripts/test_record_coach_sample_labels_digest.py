"""`scripts/record_coach_sample_digest.py`, the one-time step that records a labels file's SHA-256
(`v1-e32-t58`): only the digest the operator expects, and never over a sidecar. Every label is invented."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import record_coach_sample_digest as script  # noqa: E402

INVENTED = b"sample_row,position\n1,invented-da\n2,made-up-cp\n"
NAME = "coach-sample-labelled.csv"
SIDECAR = "coach-sample-labelled.csv.sha256"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_the_one_time_step_records_the_labels_digest_it_was_told_to_expect(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / NAME).write_bytes(INVENTED)

    assert script.main(["--sample", str(tmp_path / NAME), "--expect", sha256(INVENTED).upper()]) == 0

    assert (tmp_path / SIDECAR).read_bytes() == f"{sha256(INVENTED)}  {NAME}\n".encode()
    assert capsys.readouterr().out == f"Recorded {sha256(INVENTED)} for {NAME} in {tmp_path / SIDECAR}.\n"


def test_the_one_time_step_refuses_to_overwrite_a_labels_sidecar(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / NAME).write_bytes(INVENTED)
    (tmp_path / SIDECAR).write_bytes(b"left by an earlier sitting\n")

    assert script.main(["--sample", str(tmp_path / NAME), "--expect", sha256(INVENTED)]) == 1

    assert (tmp_path / SIDECAR).read_bytes() == b"left by an earlier sitting\n"
    error = capsys.readouterr().err
    assert error.startswith("Refused: the labels file") and "already has a sidecar" in error


def test_the_one_time_step_refuses_a_labels_file_whose_digest_is_not_the_expected_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / NAME).write_bytes(INVENTED)
    expected = sha256(b"sample_row,position\n1,older-k\n")

    assert script.main(["--sample", str(tmp_path / NAME), "--expect", expected]) == 1

    assert not (tmp_path / SIDECAR).exists()
    error = capsys.readouterr().err
    assert sha256(INVENTED)[:12] in error and expected[:12] in error and "Nothing was recorded" in error


@pytest.mark.parametrize("expect", ["abcdef012345", "z" * 64, ""])
def test_the_one_time_step_takes_a_whole_sha256_for_the_labels_file(tmp_path: Path, expect: str) -> None:
    (tmp_path / NAME).write_bytes(INVENTED)

    with pytest.raises(SystemExit) as stopped:
        script.main(["--sample", str(tmp_path / NAME), "--expect", expect])

    assert stopped.value.code == 2
    assert not (tmp_path / SIDECAR).exists()

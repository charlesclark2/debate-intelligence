"""Keyed digests, and the guard that keeps a plain one out of anything committed.

The join-key problem this exists for: this repository is public, the OpenCaselist archives are
public, so a committed `sha256` of a corpus file can be reproduced by anyone with the same corpus
and read straight back to `<School>/<TeamCode>/<filename>`. Removing the file names does not help
if the digest beside them is a lookup key into the same public bytes.

Most of this runs anywhere. The last test needs the corpus and the key, and skips without them.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tests.evals.parser.corpus import load_path_map
from tests.evals.parser.digests import (
    MissingDigestKeyError,
    PlainDigestError,
    create_key,
    keyed_digest,
    load_key,
    refuse_plain_digest,
    require_key,
    text_digest,
)
from tests.evals.parser.labels_schema import (
    EVAL_FIXTURE_DIRECTORY,
    REPOSITORY_ROOT,
    load_manifest,
)

CONTENT = b"an invented debate file's bytes"


def _key(byte: str = "5e") -> bytes:
    return bytes.fromhex(byte * 32)


# --------------------------------------------------------------------------------------------
# The digests themselves
# --------------------------------------------------------------------------------------------


def test_a_keyed_digest_is_not_the_plain_hash() -> None:
    assert keyed_digest(CONTENT, _key()) != hashlib.sha256(CONTENT).hexdigest()


def test_a_keyed_digest_is_stable_for_the_same_key_and_content() -> None:
    assert keyed_digest(CONTENT, _key()) == keyed_digest(CONTENT, _key())
    assert text_digest("a paragraph", _key()) == text_digest("a paragraph", _key())


def test_a_different_key_gives_a_different_digest() -> None:
    """What makes the corpus unjoinable: without this key, nobody can reproduce these values."""
    assert keyed_digest(CONTENT, _key()) != keyed_digest(CONTENT, _key("11"))


def test_changed_content_still_changes_the_digest() -> None:
    """The fixture-changed validator rests on this: an HMAC moves when the content moves."""
    assert keyed_digest(CONTENT + b"!", _key()) != keyed_digest(CONTENT, _key())
    assert text_digest("Older plants fail first", _key()) != text_digest("Older plants fail first.", _key())


# --------------------------------------------------------------------------------------------
# The guard
# --------------------------------------------------------------------------------------------


def test_a_plain_digest_of_the_content_is_refused() -> None:
    with pytest.raises(PlainDigestError, match="refusing to write a plain SHA-256"):
        refuse_plain_digest(hashlib.sha256(CONTENT).hexdigest(), CONTENT)


def test_a_plain_digest_of_paragraph_text_is_refused_too() -> None:
    text = "Grid operators warn of shortfalls."
    with pytest.raises(PlainDigestError):
        refuse_plain_digest(hashlib.sha256(text.encode()).hexdigest(), text)


def test_a_keyed_digest_passes_the_guard() -> None:
    digest = keyed_digest(CONTENT, _key())
    assert refuse_plain_digest(digest, CONTENT) == digest


# --------------------------------------------------------------------------------------------
# Where the key may live
# --------------------------------------------------------------------------------------------


def test_the_key_is_never_read_from_inside_the_repository() -> None:
    with pytest.raises(PlainDigestError, match="outside the repository"):
        load_key(REPOSITORY_ROOT / "tests" / "evals" / "parser-eval.key")


def test_the_key_is_never_written_inside_the_repository() -> None:
    with pytest.raises(PlainDigestError, match="outside the repository"):
        create_key(REPOSITORY_ROOT / "build" / "parser-eval.key")


def test_an_existing_key_is_never_overwritten(tmp_path: Path) -> None:
    """Overwriting would orphan every committed digest at once."""
    location = tmp_path / "digest.key"
    create_key(location)
    original = location.read_text(encoding="utf-8")
    with pytest.raises(PlainDigestError, match="re-keying is deliberate"):
        create_key(location)
    assert location.read_text(encoding="utf-8") == original


def test_a_new_key_is_random_and_not_world_readable(tmp_path: Path) -> None:
    first = create_key(tmp_path / "one.key").read_text(encoding="utf-8").strip()
    second = create_key(tmp_path / "two.key")
    assert first != second.read_text(encoding="utf-8").strip()
    assert len(bytes.fromhex(first)) == 32
    assert second.stat().st_mode & 0o077 == 0


def test_no_key_is_a_clear_error_not_a_silent_plain_digest(tmp_path: Path) -> None:
    assert load_key(tmp_path / "absent.key") is None
    with pytest.raises(MissingDigestKeyError, match="no digest key"):
        require_key(tmp_path / "absent.key")


# --------------------------------------------------------------------------------------------
# What is actually committed
# --------------------------------------------------------------------------------------------


def test_nothing_committed_holds_a_plain_digest_of_a_corpus_file() -> None:
    """The check that matters: hash the corpus the way an outsider would, and look for the result.

    Needs the files and the key, so it runs on the operator's machine and skips everywhere else —
    which is the same place an outsider's version of this attack would have to run from, except
    that they have the public archives and we have the key.
    """
    path_map = load_path_map()
    key = load_key()
    if path_map is None or key is None:
        pytest.skip("no evaluation corpus on this machine")
    committed = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in sorted(EVAL_FIXTURE_DIRECTORY.rglob("*"))
        if path.is_file()
    )
    manifest = load_manifest()
    for entry in manifest.entries:
        content = path_map[entry.digest].read_bytes()
        plain = hashlib.sha256(content).hexdigest()
        assert plain not in committed, f"a plain digest of a corpus file is committed ({plain[:12]}…)"
        assert entry.digest == keyed_digest(content, key)


def test_the_committed_manifest_and_plan_agree_on_their_digests() -> None:
    manifest = json.loads((EVAL_FIXTURE_DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((EVAL_FIXTURE_DIRECTORY / "sampling-plan.json").read_text(encoding="utf-8"))
    assert {entry["digest"] for entry in manifest["entries"]} == {file["digest"] for file in plan["files"]}
    assert "sha256" not in json.dumps(manifest) and "sha256" not in json.dumps(plan)

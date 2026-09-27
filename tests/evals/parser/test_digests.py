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
import re
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


#: Phrasings that *claim* the digests are plain hashes. "never a plain SHA-256" and "HMAC-SHA256"
#: are the correct wording and do not match. Ordinary uses of `hashlib.sha256` in code do not either.
_PLAIN_DIGEST_CLAIMS = (
    re.compile(r"keyed by (a |an )?sha-?256", re.IGNORECASE),
    re.compile(r"\bby sha-?256[,;.]", re.IGNORECASE),
    re.compile(r"<sha256>"),
    re.compile(r"(?<!hmac-)(?<!hmac)sha-?256 of (its|the paragraph|the file)", re.IGNORECASE),
)

_DOCUMENTED = (
    "tests/fixtures/debate_files/eval/MANIFEST.md",
    "tests/fixtures/debate_files/eval/labels/README.md",
    "tests/evals/parser",
    "scripts/prelabel_docx.py",
    "scripts/select_eval_files.py",
    "scripts/plan_eval_sampling.py",
    "scripts/run_parser_eval.py",
)


def test_nothing_documents_the_digests_as_plain_hashes() -> None:
    """The lines a future reader follows must not contradict the code.

    Two lines of `MANIFEST.md` survived the re-key still saying files were listed "by SHA-256" and
    labels keyed by "the SHA-256 of its text". The code was keyed the whole time; the documentation
    was the part that would have talked someone into reintroducing the join key. This fails if that
    wording comes back anywhere it would be read as the rule.
    """
    offenders: list[str] = []
    for entry in _DOCUMENTED:
        path = REPOSITORY_ROOT / entry
        files = sorted(path.rglob("*.py")) if path.is_dir() else [path]
        for file in files:
            if file.name == "test_digests.py":
                continue  # this module quotes the wrong wording in order to forbid it
            for number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
                if any(pattern.search(line) for pattern in _PLAIN_DIGEST_CLAIMS):
                    offenders.append(f"{file.relative_to(REPOSITORY_ROOT)}:{number}: {line.strip()}")
    assert not offenders, "documentation claims plain-SHA-256 keying:\n  " + "\n  ".join(offenders)


def test_the_wording_guard_catches_the_lines_it_was_written_for() -> None:
    """Otherwise the guard above could pass by matching nothing at all.

    These two lines are verbatim what `MANIFEST.md` carried after the re-key, when the code was
    already keyed.
    """
    survived_the_rekey = (
        "| [`manifest.json`](manifest.json) | Each evaluation file by SHA-256, category, season, "
        "format and template family, and whether it is in the PR subset. |",
        "| [`labels/`](labels/) | One `<sha256>.jsonl` per file once it is labeled: each paragraph's "
        "unit and card, keyed by paragraph index and the SHA-256 of its text. |",
    )
    for line in survived_the_rekey:
        assert any(pattern.search(line) for pattern in _PLAIN_DIGEST_CLAIMS), line
    for correct in (
        "Each evaluation file by keyed digest, category, season, format and template family.",
        "Every digest here is an **HMAC-SHA256** under a key kept beside the path map.",
        "keyed by paragraph index and a keyed digest of its text",
        "never a plain SHA-256, which over a public corpus would join straight back to the file",
    ):
        assert not any(pattern.search(correct) for pattern in _PLAIN_DIGEST_CLAIMS), correct


def test_the_committed_manifest_and_plan_agree_on_their_digests() -> None:
    manifest = json.loads((EVAL_FIXTURE_DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((EVAL_FIXTURE_DIRECTORY / "sampling-plan.json").read_text(encoding="utf-8"))
    assert {entry["digest"] for entry in manifest["entries"]} == {file["digest"] for file in plan["files"]}
    assert "sha256" not in json.dumps(manifest) and "sha256" not in json.dumps(plan)

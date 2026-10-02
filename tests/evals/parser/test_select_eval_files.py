"""The selector's handling of rejected files, and what it prints.

A person who opens an evaluation file and finds it is not debate material at all rejects it. The
rejection is recorded by keyed digest, and from then on the selector must never choose that file
again, and replacing it must not disturb the rest of a selection someone has already looked at.

Everything here runs offline on invented candidates and invented `.docx` files.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest
from tests.evals.parser.digests import create_key
from tests.evals.parser.labels_schema import (
    REPOSITORY_ROOT,
    Category,
    DebateFormat,
    Manifest,
    RejectedFile,
    RejectionList,
    RejectionReason,
    TemplateFamily,
    coverage_shortfalls,
    rejection_conflicts,
    stratum_of,
)

sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

import select_eval_files as selector  # noqa: E402

_SEASONS = ("2024-25", "2025-26", "2026-27")


def _candidates() -> list[selector.Candidate]:
    """An invented corpus with several files in every stratum the selection draws on."""
    pool: list[selector.Candidate] = []

    def add(category: Category, season: str, debate_format: DebateFormat, family: TemplateFamily) -> None:
        n = len(pool)
        pool.append(
            selector.Candidate(
                path=Path(f"/nowhere/{n}.docx"),
                digest=hashlib.sha256(f"invented candidate {n}".encode()).hexdigest(),
                category=category,
                season=season,
                debate_format=debate_format,
                template_family=family,
                paragraphs=20 + (n * 37) % 400,
            )
        )

    team_families = (TemplateFamily.VERBATIM, TemplateFamily.OTHER_HEURISTIC, TemplateFamily.WIKI_CONVERTED)
    for season in _SEASONS:
        for debate_format in DebateFormat:
            for family in team_families:
                for _ in range(2):
                    add(Category.TEAM, season, debate_format, family)
    for family in TemplateFamily:
        for _ in range(7):
            add(Category.CASELIST, "2026-27", DebateFormat.LD, family)
        for _ in range(3):
            add(Category.CAMP, "2026-27", DebateFormat.POLICY, family)
    return pool


def _rejection(manifest: Manifest, digest: str) -> RejectedFile:
    entry = manifest.entry(digest)
    return RejectedFile(
        digest=digest,
        reason=RejectionReason.NOT_DEBATE_CONTENT,
        rejected_on="2026-10-02",
        category=entry.category,
        season=entry.season,
        debate_format=entry.debate_format,
        template_family=entry.template_family,
        pr_subset=entry.pr_subset,
    )


def _caselist_pr_subset_file(manifest: Manifest) -> str:
    """The case this was written for: a non-Verbatim caselist file in the PR subset."""
    return next(
        e.digest
        for e in manifest.entries
        if e.category is Category.CASELIST and e.pr_subset and not e.is_verbatim
    )


# --------------------------------------------------------------------------------------------
# Replacing a rejected file in a selection already proposed
# --------------------------------------------------------------------------------------------


def test_a_rejected_file_is_replaced_from_its_own_stratum_and_nothing_else_moves() -> None:
    candidates = _candidates()
    before, _ = selector.propose_selection(candidates)
    assert coverage_shortfalls(before) == []
    rejected = _caselist_pr_subset_file(before)

    after, replacements = selector.replace_rejected(before, candidates, {rejected})

    assert rejected not in {e.digest for e in after.entries}
    assert set(replacements) == {rejected}
    replacement = after.entry(replacements[rejected])
    assert replacement.digest not in {e.digest for e in before.entries}
    assert stratum_of(replacement) == stratum_of(before.entry(rejected))
    position = [e.digest for e in before.entries].index(rejected)
    assert after.entries[:position] == before.entries[:position]
    assert after.entries[position + 1 :] == before.entries[position + 1 :]
    assert after.entries[position] == replacement
    assert coverage_shortfalls(after) == []


def test_a_rejected_file_outside_the_pr_subset_is_replaced_the_same_way() -> None:
    candidates = _candidates()
    before, _ = selector.propose_selection(candidates)
    rejected = next(e.digest for e in before.entries if e.category is Category.TEAM and not e.pr_subset)

    after, replacements = selector.replace_rejected(before, candidates, {rejected})

    changed = [(old, new) for old, new in zip(before.entries, after.entries, strict=True) if old != new]
    assert len(changed) == 1
    old, new = changed[0]
    assert old.digest == rejected and new.digest == replacements[rejected]
    assert stratum_of(new) == stratum_of(old)


def test_the_pr_subset_replacement_is_the_shortest_eligible_file() -> None:
    """The PR subset takes the shortest files, so it stays cheap on every pull request."""
    candidates = _candidates()
    before, _ = selector.propose_selection(candidates)
    rejected = _caselist_pr_subset_file(before)
    stratum = stratum_of(before.entry(rejected))[:4]
    taken = {e.digest for e in before.entries}
    eligible = [c for c in candidates if c.stratum == stratum and c.digest not in taken]

    _, replacements = selector.replace_rejected(before, candidates, {rejected})

    shortest = min(eligible, key=lambda c: (c.paragraphs, c.digest))
    assert replacements[rejected] == shortest.digest


def test_replacing_is_deterministic() -> None:
    candidates = _candidates()
    before, _ = selector.propose_selection(candidates)
    rejected = {_caselist_pr_subset_file(before)}
    assert selector.replace_rejected(before, candidates, rejected) == selector.replace_rejected(
        before, list(reversed(candidates)), rejected
    )


def test_a_file_rejected_earlier_is_not_brought_back_by_a_later_rejection() -> None:
    candidates = _candidates()
    first, _ = selector.propose_selection(candidates)
    rejected_first = _caselist_pr_subset_file(first)
    second, replacements = selector.replace_rejected(first, candidates, {rejected_first})
    rejected_second = replacements[rejected_first]

    third, later = selector.replace_rejected(second, candidates, {rejected_first, rejected_second})

    chosen = {e.digest for e in third.entries}
    assert rejected_first not in chosen and rejected_second not in chosen
    assert set(later) == {rejected_second}


def test_a_stratum_with_nothing_left_is_an_error_not_a_file_from_another_stratum() -> None:
    candidates = _candidates()
    before, _ = selector.propose_selection(candidates)
    rejected = _caselist_pr_subset_file(before)
    stratum = stratum_of(before.entry(rejected))[:4]
    taken = {e.digest for e in before.entries}
    only_the_selection = [c for c in candidates if c.stratum != stratum or c.digest in taken]

    with pytest.raises(selector.NoReplacementError, match="no other candidate"):
        selector.replace_rejected(before, only_the_selection, {rejected})


def test_the_recorded_rejection_checks_out_against_the_new_manifest() -> None:
    candidates = _candidates()
    before, _ = selector.propose_selection(candidates)
    rejected = _caselist_pr_subset_file(before)
    after, replacements = selector.replace_rejected(before, candidates, {rejected})
    recorded = _rejection(before, rejected).model_copy(update={"replaced_by": replacements[rejected]})

    assert rejection_conflicts(after, RejectionList(rejections=(recorded,))) == []
    assert rejection_conflicts(before, RejectionList(rejections=(recorded,))) != []


# --------------------------------------------------------------------------------------------
# A fresh selection
# --------------------------------------------------------------------------------------------


def test_a_fresh_selection_never_chooses_a_rejected_file() -> None:
    candidates = _candidates()
    proposed, _ = selector.propose_selection(candidates)
    rejected = frozenset({_caselist_pr_subset_file(proposed), proposed.entries[0].digest})

    again, path_map = selector.propose_selection(candidates, rejected=rejected)

    assert rejected.isdisjoint(e.digest for e in again.entries)
    assert rejected.isdisjoint(path_map)
    assert coverage_shortfalls(again) == []


# --------------------------------------------------------------------------------------------
# Re-keying keeps the rejection list
# --------------------------------------------------------------------------------------------


def test_re_keying_re_keys_the_rejected_files_and_their_replacements(tmp_path: Path) -> None:
    files = {name: tmp_path / f"{name}.docx" for name in ("kept", "rejected", "replacement")}
    for name, path in files.items():
        path.write_bytes(f"invented bytes of the {name} file".encode())
    old_key, new_key = b"o" * 32, b"n" * 32
    old = {name: selector.keyed_digest(path.read_bytes(), old_key) for name, path in files.items()}
    new = {name: selector.keyed_digest(path.read_bytes(), new_key) for name, path in files.items()}
    old_path_map = tmp_path / "paths.json"
    old_path_map.write_text(json.dumps({old[name]: str(path) for name, path in files.items()}))
    manifest = tmp_path / "manifest.json"
    entry = {
        "category": "caselist",
        "season": "2026-27",
        "debate_format": "LD",
        "template_family": "wiki-converted",
        "pr_subset": True,
    }
    manifest.write_text(
        json.dumps({"entries": [{"digest": old["kept"], **entry}, {"digest": old["replacement"], **entry}]})
    )
    rejections = RejectionList(
        rejections=(
            RejectedFile.model_validate(
                {
                    "digest": old["rejected"],
                    "reason": "NOT_DEBATE_CONTENT",
                    "rejected_on": "2026-10-02",
                    "replaced_by": old["replacement"],
                    **entry,
                }
            ),
        )
    )

    rekeyed, _ = selector.rekey_manifest(manifest, old_path_map, new_key)
    rekeyed_rejections, rejected_paths = selector.rekey_rejections(rejections, old_path_map, new_key)

    assert {e.digest for e in rekeyed.entries} == {new["kept"], new["replacement"]}
    assert rejected_paths == {new["rejected"]: files["rejected"]}
    assert rekeyed_rejections.rejections[0].digest == new["rejected"]
    assert rekeyed_rejections.rejections[0].replaced_by == new["replacement"]
    assert rejection_conflicts(rekeyed, rekeyed_rejections) == []


def test_re_keying_refuses_a_rejected_file_it_cannot_find(tmp_path: Path) -> None:
    old_path_map = tmp_path / "paths.json"
    old_path_map.write_text("{}")
    rejections = RejectionList(
        rejections=(
            RejectedFile(
                digest="a" * 64,
                reason=RejectionReason.NOT_DEBATE_CONTENT,
                rejected_on="2026-10-02",
                category=Category.CASELIST,
                season="2026-27",
                debate_format=DebateFormat.LD,
                template_family=TemplateFamily.WIKI_CONVERTED,
                pr_subset=True,
            ),
        )
    )
    with pytest.raises(SystemExit, match="rejected file"):
        selector.rekey_rejections(rejections, old_path_map, b"n" * 32)


# --------------------------------------------------------------------------------------------
# The content hint
# --------------------------------------------------------------------------------------------


def _docx(path: Path, paragraphs: list[str]) -> Path:
    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return path


def test_a_file_with_a_citation_in_latin_script_raises_no_hint(tmp_path: Path) -> None:
    path = _docx(
        tmp_path / "card.docx",
        ["Invented tag about trade", "Invented Author 21, Professor, Invented Journal, 2021", "Body text."],
    )
    assert selector.content_hints(path) == selector.ContentHints(
        no_citation_like_paragraph=False, mostly_non_latin=False
    )


def test_a_file_with_no_citation_like_paragraph_is_hinted(tmp_path: Path) -> None:
    path = _docx(tmp_path / "prose.docx", ["An invented paragraph of prose.", "Another, with no date."])
    hints = selector.content_hints(path)
    assert hints.no_citation_like_paragraph and not hints.mostly_non_latin and hints.flagged


def test_a_file_mostly_in_a_non_latin_script_is_hinted(tmp_path: Path) -> None:
    path = _docx(tmp_path / "script.docx", ["Ουδέν εφεύρημα κειμένου", "Αλλο κείμενο 2021 Smith"])
    hints = selector.content_hints(path)
    assert hints.mostly_non_latin and not hints.no_citation_like_paragraph and hints.flagged


def test_the_selector_prints_counts_never_text_names_or_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The hint reads text to count it; none of what it reads may reach the terminal."""
    monkeypatch.setenv("DEBATE_PARSER_EVAL_KEY_FILE", str(create_key(tmp_path / "key" / "digest.key")))
    folder = tmp_path / "corpus" / "2025-2026" / "LD Debate" / "SECRETSCHOOL"
    folder.mkdir(parents=True)
    _docx(folder / "SECRETNAME one.docx", ["SECRETTEXT Ουδέν εφεύρημα κειμένου"] * 25)
    _docx(folder / "SECRETNAME two.docx", ["SECRETTEXT Invented prose with no date"] * 25)

    selector.main(
        [
            "--input",
            f"team={tmp_path / 'corpus'}",
            "--manifest",
            str(tmp_path / "out" / "manifest.json"),
            "--path-map",
            str(tmp_path / "out" / "paths.json"),
            "--rejections",
            str(tmp_path / "out" / "rejections.json"),
        ]
    )
    printed = capsys.readouterr()
    output = printed.out + printed.err
    assert "may not be debate material" in output
    for secret in ("SECRETTEXT", "SECRETNAME", "SECRETSCHOOL", "Ουδέν", str(tmp_path)):
        assert secret not in output

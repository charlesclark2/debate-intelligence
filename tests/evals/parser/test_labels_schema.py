"""The label schema, its validators, and the committed manifest.

Everything here runs in the PR `ci` check, where the real evaluation files never are: it needs
only the label files, the manifest and the invented file in `synthetic.py`.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from debate_core.domain.debate_files import CardCompleteness
from debate_core.domain.style_profile import StructuralUnit

from tests.evals.parser.labels_schema import (
    EVAL_FIXTURE_DIRECTORY,
    LABELS_DIRECTORY,
    CardLabel,
    Category,
    DebateFormat,
    FileLabelHeader,
    LabelStatus,
    Manifest,
    ManifestEntry,
    ParagraphLabel,
    ReviewerRole,
    SpanLabel,
    TemplateFamily,
    coverage_shortfalls,
    load_label_file,
    load_label_files,
    load_manifest,
    text_sha256,
    validate_against_texts,
    validate_label_file,
    write_label_file,
)
from tests.evals.parser.synthetic import build_synthetic_file

SHA = "a" * 64


def _with_paragraph(labels, index, **changes):  # type: ignore[no-untyped-def]
    paragraphs = list(labels.paragraphs)
    paragraphs[index] = paragraphs[index].model_copy(update=changes)
    return replace(labels, paragraphs=tuple(paragraphs))


# --------------------------------------------------------------------------------------------
# A well-formed label file
# --------------------------------------------------------------------------------------------


def test_the_hand_written_synthetic_labels_are_valid() -> None:
    assert validate_label_file(build_synthetic_file().labels) == []


def test_a_label_file_round_trips_through_jsonl(tmp_path: Path) -> None:
    labels = build_synthetic_file().labels
    path = write_label_file(labels, tmp_path)
    assert path.name == f"{labels.sha256}.jsonl"
    assert load_label_file(path) == labels
    first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert first["record"] == "file"


def test_a_label_file_holds_no_text(tmp_path: Path) -> None:
    """The labels travel with the repository; the paragraphs they describe must not."""
    path = write_label_file(build_synthetic_file().labels, tmp_path)
    written = path.read_text(encoding="utf-8")
    for text in ("Maple Grove Negative", "reserve margins", "Okonkwo", "Their turn is non-unique"):
        assert text not in written


def test_text_hash_is_sha256_of_the_utf8_text() -> None:
    # sha256("abc"), the FIPS 180-2 test vector.
    assert text_sha256("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


# --------------------------------------------------------------------------------------------
# What the structural validator catches
# --------------------------------------------------------------------------------------------


def test_paragraph_indices_must_be_complete_and_in_order() -> None:
    labels = build_synthetic_file().labels
    missing_one = replace(labels, paragraphs=labels.paragraphs[:-1])
    assert any("indices 0..10" in problem for problem in validate_label_file(missing_one))
    swapped = replace(labels, paragraphs=(labels.paragraphs[1], labels.paragraphs[0], *labels.paragraphs[2:]))
    assert validate_label_file(swapped)


def test_a_heading_or_analytic_is_never_inside_a_card() -> None:
    labels = _with_paragraph(build_synthetic_file().labels, 7, card=0)
    assert "paragraph 7: a ANALYTIC is never part of a card" in validate_label_file(labels)


def test_a_card_needs_a_cite() -> None:
    labels = _with_paragraph(build_synthetic_file().labels, 4, unit=StructuralUnit.EVIDENCE)
    assert "card 0 has no CITE paragraph" in validate_label_file(labels)


def test_completeness_must_agree_with_the_card_body() -> None:
    labels = build_synthetic_file().labels
    cite_only = replace(labels, cards=(CardLabel(card=0, completeness=CardCompleteness.CITE_ONLY), labels.cards[1]))
    assert "card 0 is CITE_ONLY but has EVIDENCE paragraphs" in validate_label_file(cite_only)
    no_body = _with_paragraph(labels, 10, unit=StructuralUnit.OTHER, card=None)
    assert "card 1 is FULL but has no EVIDENCE paragraph" in validate_label_file(no_body)


def test_every_card_has_exactly_one_record_and_some_paragraphs() -> None:
    labels = build_synthetic_file().labels
    no_record = replace(labels, cards=labels.cards[:1])
    assert "card 1 has paragraphs but no card record" in validate_label_file(no_record)
    orphan = replace(labels, cards=(*labels.cards, CardLabel(card=7, completeness=CardCompleteness.FULL)))
    assert "card 7 has a card record but no paragraphs" in validate_label_file(orphan)
    repeated = replace(labels, cards=(*labels.cards, labels.cards[0]))
    assert any("repeated" in problem for problem in validate_label_file(repeated))


def test_spans_must_fit_their_paragraph_and_not_overlap() -> None:
    labels = build_synthetic_file().labels
    too_long = replace(labels, spans=(SpanLabel(index=4, underline=((0, 999),)),))
    assert any("outside its" in problem for problem in validate_label_file(too_long))
    overlapping = replace(labels, spans=(SpanLabel(index=5, highlight=((0, 10), (5, 12))),))
    assert any("overlap" in problem for problem in validate_label_file(overlapping))
    unknown = replace(labels, spans=(SpanLabel(index=99),))
    assert any("not labeled" in problem for problem in validate_label_file(unknown))


def test_card_rules_are_skipped_for_pre_labels_only(tmp_path: Path) -> None:
    broken = _with_paragraph(build_synthetic_file(LabelStatus.PRELABELED).labels, 4, unit=StructuralUnit.EVIDENCE)
    assert validate_label_file(broken, check_cards=False) == []
    write_label_file(broken, tmp_path, check_cards=False)
    corrected = _with_paragraph(build_synthetic_file().labels, 4, unit=StructuralUnit.EVIDENCE)
    with pytest.raises(ValueError, match="only a PRELABELED file"):
        write_label_file(corrected, tmp_path, check_cards=False)


def test_labels_for_a_file_the_manifest_does_not_list_are_flagged() -> None:
    assert any("does not list" in problem for problem in validate_label_file(build_synthetic_file().labels, Manifest()))


# --------------------------------------------------------------------------------------------
# Review status: a pre-label cannot pass itself off as a person's work
# --------------------------------------------------------------------------------------------


def test_a_prelabel_names_no_reviewer() -> None:
    with pytest.raises(ValidationError, match="has not been corrected"):
        FileLabelHeader(
            sha256=SHA, paragraph_count=0, status=LabelStatus.PRELABELED, prelabel_parser_version="p",
            corrected_by=ReviewerRole.COACH,
        )  # fmt: skip


def test_a_corrected_file_says_who_corrected_it() -> None:
    with pytest.raises(ValidationError, match="which role corrected it"):
        FileLabelHeader(sha256=SHA, paragraph_count=0, status=LabelStatus.CORRECTED, prelabel_parser_version="p")


def test_only_the_coach_can_have_reviewed_a_file() -> None:
    with pytest.raises(ValidationError, match="reviewed_by the coach"):
        FileLabelHeader(
            sha256=SHA, paragraph_count=0, status=LabelStatus.COACH_REVIEWED, prelabel_parser_version="p",
            corrected_by=ReviewerRole.OPERATOR, reviewed_by=ReviewerRole.OPERATOR,
        )  # fmt: skip


# --------------------------------------------------------------------------------------------
# The validator that needs the file: fails when the file changes under its labels (ac4)
# --------------------------------------------------------------------------------------------

_TEXTS = [
    "Maple Grove Negative", "Grid Reliability", "AT: Reserve Margin Turn", "Moratoria collapse the reserve margin",
    "Okonkwo 26, Grid Analyst, Fictional Energy Review",
    "Grid operators warn that reserve margins fall below safe levels within two summers.", "",
    "Their turn is non-unique", "Older plants fail first", "Lindqvist 25, Professor, Invented University",
    "Moratoria shift load to older plants and raise outage risk.",
]  # fmt: skip


def test_the_unchanged_file_matches_its_labels() -> None:
    synthetic = build_synthetic_file()
    assert validate_against_texts(synthetic.labels, synthetic.sha256, _TEXTS) == []


def test_different_bytes_fail() -> None:
    labels = build_synthetic_file().labels
    assert "labels are for" in validate_against_texts(labels, "b" * 64, _TEXTS)[0]


def test_an_edited_paragraph_fails() -> None:
    synthetic = build_synthetic_file()
    edited = [*_TEXTS]
    edited[8] = "Older plants fail first."
    assert validate_against_texts(synthetic.labels, synthetic.sha256, edited) == [
        "paragraph 8: text changed under its label"
    ]


def test_a_paragraph_added_or_lost_fails() -> None:
    synthetic = build_synthetic_file()
    problems = validate_against_texts(synthetic.labels, synthetic.sha256, _TEXTS[:-1])
    assert "file has 10 paragraphs, labels have 11" in problems


# --------------------------------------------------------------------------------------------
# Coverage against ac1
# --------------------------------------------------------------------------------------------


def _entry(n: int, category: Category, **fields: object) -> ManifestEntry:
    values: dict[str, object] = {
        "sha256": f"{n:064x}",
        "category": category,
        "season": "2025-26",
        "debate_format": DebateFormat.LD,
        "template_family": TemplateFamily.VERBATIM,
    }
    values.update(fields)
    return ManifestEntry.model_validate(values)


def test_an_empty_manifest_falls_short_on_every_count() -> None:
    shortfalls = coverage_shortfalls(Manifest())
    assert "at least 30 files are labeled; the manifest has 0" in shortfalls
    assert any("wiki-converted caselist" in s for s in shortfalls)
    assert any("PR subset is 6 files" in s for s in shortfalls)


def test_a_manifest_meeting_ac1_has_no_shortfalls() -> None:
    entries: list[ManifestEntry] = []
    n = 0
    for season in ("2024-25", "2025-26", "2026-27"):
        for debate_format in DebateFormat:
            for family in (TemplateFamily.VERBATIM,) if season != "2024-25" else (TemplateFamily.OTHER_HEURISTIC,):
                entries.append(_entry(n, Category.TEAM, season=season, debate_format=debate_format, template_family=family))
                n += 1
    for _ in range(3):
        entries.append(_entry(n, Category.TEAM)); n += 1  # fmt: skip
    families = [TemplateFamily.OTHER_HEURISTIC] * 4 + [TemplateFamily.WIKI_CONVERTED] * 2 + [TemplateFamily.CARDMIRROR] * 6
    for family in families:
        entries.append(_entry(n, Category.CASELIST, template_family=family)); n += 1  # fmt: skip
    for _ in range(6):
        entries.append(_entry(n, Category.CAMP)); n += 1  # fmt: skip
    subset = {0, 1, 12, 13, 24, 25}
    manifest = Manifest(entries=tuple(e.model_copy(update={"pr_subset": i in subset}) for i, e in enumerate(entries)))
    assert coverage_shortfalls(manifest) == []

    without_wiki = Manifest(
        entries=tuple(
            e.model_copy(update={"template_family": TemplateFamily.CARDMIRROR})
            if e.template_family is TemplateFamily.WIKI_CONVERTED
            else e
            for e in manifest.entries
        )
    )
    assert coverage_shortfalls(without_wiki) == ["at least 2 wiki-converted caselist files; 0"]


def test_a_file_cannot_be_listed_twice() -> None:
    with pytest.raises(ValidationError, match="twice"):
        Manifest(entries=(_entry(1, Category.CAMP), _entry(1, Category.CAMP)))


# --------------------------------------------------------------------------------------------
# The committed manifest and labels
# --------------------------------------------------------------------------------------------


def test_the_committed_manifest_meets_ac1() -> None:
    assert coverage_shortfalls(load_manifest()) == []


def test_the_manifest_summary_table_matches_manifest_json() -> None:
    """MANIFEST.md is read by people; manifest.json by the tools. They must say the same thing."""
    rows = re.findall(
        r"^\| `([0-9a-f]{16})` \| (\w+) \| ([\d-]+) \| (\w+) \| ([\w-]+) \| (yes)? *\|$",
        (EVAL_FIXTURE_DIRECTORY / "MANIFEST.md").read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    table = {(sha, category, season, fmt, family, bool(subset)) for sha, category, season, fmt, family, subset in rows}
    manifest = {
        (e.sha256[:16], e.category.value, e.season, e.debate_format.value, e.template_family.value, e.pr_subset)
        for e in load_manifest().entries
    }
    assert table == manifest


def test_nothing_in_the_eval_directory_names_a_file() -> None:
    """No .docx, no path, no file name: the manifest is SHA-256 and metadata only."""
    for path in EVAL_FIXTURE_DIRECTORY.rglob("*"):
        assert path.suffix.lower() not in {".docx", ".doc", ".docm", ".pdf", ".csv"}, path.name
    raw = (EVAL_FIXTURE_DIRECTORY / "manifest.json").read_text(encoding="utf-8")
    assert ".docx" not in raw and "/" not in raw.replace("scripts/select_eval_files.py", "")
    for entry in json.loads(raw)["entries"]:
        assert set(entry) == {"sha256", "category", "season", "debate_format", "template_family", "pr_subset"}


def test_every_committed_label_file_is_valid_and_listed() -> None:
    manifest = load_manifest()
    for sha, labels in load_label_files(LABELS_DIRECTORY).items():
        check_cards = labels.header.status is not LabelStatus.PRELABELED
        assert validate_label_file(labels, manifest, check_cards=check_cards) == [], sha[:12]

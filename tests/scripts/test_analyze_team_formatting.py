"""Tests for `scripts/analyze_team_formatting.py`, the team card formatting survey.

They run on synthetic folders only, never on the operator's: the tree
`scripts/generate_team_format_fixtures.py` writes, and the style profile's own `verbatim-cut-card`
fixture placed in a season folder. Every expected count below was written by hand from those
files' descriptions, not by running the analysis.

The rule that matters most has its own tests: the analysis never reads document text. The same
tree built over other words must measure exactly the same, and those words must reach no output.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import shutil
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import analyze_team_formatting as analysis  # noqa: E402
import generate_team_format_fixtures as fixtures  # noqa: E402

from debate_core.evidence.style_profile_loader import load_style_profile  # noqa: E402

COMMITTED_TREE = REPO_ROOT / "tests" / "fixtures" / "debate_files" / "team_format"
STYLE_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "debate_files" / "style_profile" / "verbatim-cut-card.docx"
EXCLUDED = ("Opencaselist",)
RUN_ON = date(2026, 10, 26)
SENTINEL = "Zyxwvutsrq"


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    fixtures.write_tree(tmp_path / "debate", load_style_profile())
    return tmp_path / "debate"


def survey_of(*inputs: Path, exclude: tuple[str, ...] = EXCLUDED) -> analysis.TeamFormatSurvey:
    _, survey, _ = analysis.analyze(list(inputs), exclude, load_style_profile())
    return survey


def report_of(survey: analysis.TeamFormatSurvey) -> str:
    return analysis.render_report(survey, run_on=RUN_ON, excluded_folders=EXCLUDED)


# --------------------------------------------------------------------------------------------
# Which files are read
# --------------------------------------------------------------------------------------------


def test_files_are_chosen_by_rule_and_every_skip_is_counted(tree: Path) -> None:
    survey = survey_of(tree)

    assert survey.files_by_season_event == Counter(
        {("2024-25", "LD"): 1, ("2025-26", "PF"): 1, ("2026-27", "Policy"): 1}
    )
    assert survey.skipped == Counter(
        {
            "in an excluded folder": 1,
            "duplicate bytes": 1,
            "no season or event in the folder names": 1,
            "not a readable .docx": 1,
        }
    )


def test_without_the_exclusion_the_caselist_file_is_read(tree: Path) -> None:
    survey = survey_of(tree, exclude=())

    assert survey.files_by_season_event[("2026-27", "LD")] == 1
    assert "in an excluded folder" not in survey.skipped


def test_season_folders_given_one_by_one_are_read_the_same_way(tree: Path) -> None:
    together = survey_of(tree)
    one_by_one = survey_of(tree / "2024-2025", tree / "2025-2026", tree / "2026-2027")

    assert one_by_one.files_by_season_event == together.files_by_season_event
    assert one_by_one.underlined_sizes == together.underlined_sizes


def test_folders_above_the_input_are_never_read_for_season_or_event(tmp_path: Path) -> None:
    above = tmp_path / "2025-2026" / "LD Debate"
    fixtures.write_tree(above, load_style_profile())

    survey = survey_of(above / "2024-2025" / "LD")

    assert survey.files == 0
    assert survey.skipped["no season or event in the folder names"] == 1


def test_a_missing_input_folder_stops_the_run(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="input folder not found: absent"):
        survey_of(tmp_path / "absent")


# --------------------------------------------------------------------------------------------
# What is measured
# --------------------------------------------------------------------------------------------


def test_structural_units_their_outline_levels_and_style_ids(tree: Path) -> None:
    survey = survey_of(tree)

    assert survey.unit_paragraphs == Counter({"POCKET": 1, "BLOCK": 1, "TAG": 4, "UNDERTAG": 1, "ANALYTIC": 1})
    assert survey.unit_files == Counter({"POCKET": 1, "BLOCK": 1, "TAG": 3, "UNDERTAG": 1, "ANALYTIC": 1})
    assert survey.unit_outline_levels == Counter(
        {("POCKET", 0): 1, ("BLOCK", 2): 1, ("TAG", 3): 4, ("UNDERTAG", None): 1, ("ANALYTIC", 3): 1}
    )
    assert survey.unit_style_ids == Counter(
        {
            ("POCKET", "Heading1"): 1,
            ("BLOCK", "Heading3"): 1,
            ("TAG", "Heading4"): 4,
            ("UNDERTAG", "Undertag"): 1,
            ("ANALYTIC", "Analytic"): 1,
        }
    )
    assert survey.families == Counter({"verbatim": 3})


def test_the_cite_block(tree: Path) -> None:
    survey = survey_of(tree)

    assert survey.cite_paragraphs == 5
    assert survey.cite_paragraphs_led_by_short_cite == 4
    assert survey.short_cite_sizes == Counter({26: 5})
    assert survey.short_cite_bold_runs == 5
    assert survey.full_cite_sizes == Counter({16: 2, 20: 1, 22: 2})
    assert survey.full_cite_size_modes == Counter({16: 1, 20: 1, 22: 1})
    assert survey.full_cite_bold_runs == 0


def test_the_evidence(tree: Path) -> None:
    survey = survey_of(tree)

    assert survey.evidence_paragraphs == 6
    assert survey.condensed_evidence_paragraphs == 4
    assert survey.underlined_sizes == Counter({22: 7})
    assert survey.underlined_size_modes == Counter({22: 3})
    assert survey.not_underlined_sizes == Counter({16: 5, 12: 2, 22: 2})
    assert survey.not_underlined_size_modes == Counter({16: 1, 12: 1, 22: 1})
    assert survey.highlight_colors == Counter({"cyan": 3, "green": 1, "yellow": 2})
    assert survey.highlight_color_modes == Counter({"cyan": 1, "green": 1, "yellow": 1})
    assert survey.highlighted_not_underlined_runs == 0
    assert survey.bold_evidence_runs == 1


def test_the_style_profiles_own_card_fixture_measures_as_its_description_says(tmp_path: Path) -> None:
    season = tmp_path / "2025-2026" / "LD"
    season.mkdir(parents=True)
    shutil.copyfile(STYLE_FIXTURE, season / STYLE_FIXTURE.name)

    survey = survey_of(tmp_path / "2025-2026")

    assert survey.unit_paragraphs == Counter(
        {"POCKET": 1, "HAT": 1, "BLOCK": 1, "TAG": 1, "ANALYTIC": 1, "UNDERTAG": 1}
    )
    assert (survey.cite_paragraphs, survey.cite_paragraphs_led_by_short_cite) == (1, 1)
    assert survey.short_cite_sizes == Counter({26: 1})
    assert survey.full_cite_sizes == Counter({None: 1})
    assert (survey.evidence_paragraphs, survey.condensed_evidence_paragraphs) == (1, 1)
    assert survey.underlined_sizes == Counter({22: 1})
    assert survey.not_underlined_sizes == Counter({16: 2})
    assert survey.highlight_colors == Counter({"cyan": 1})


# --------------------------------------------------------------------------------------------
# It never reads text
# --------------------------------------------------------------------------------------------


def test_the_same_formatting_over_other_words_measures_exactly_the_same(tmp_path: Path) -> None:
    fixtures.write_tree(tmp_path / "original", load_style_profile())
    fixtures.write_tree(tmp_path / "other-words", load_style_profile(), variant=SENTINEL)

    original = survey_of(tmp_path / "original")
    other_words = survey_of(tmp_path / "other-words")

    assert other_words == original
    assert report_of(other_words) == report_of(original)


def test_text_elements_are_gone_before_anything_looks_at_the_body(tmp_path: Path) -> None:
    fixtures.write_tree(tmp_path, load_style_profile(), variant=SENTINEL)
    cyan = tmp_path / fixtures.cyan_convention().relative_path

    from zipfile import ZipFile

    with ZipFile(cyan) as archive:
        assert SENTINEL.encode() in archive.read("word/document.xml")
        body = analysis._parse_without_text(archive, "word/document.xml")

    assert body is not None
    assert not [element for element in body.iter() if element.tag in analysis.TEXT_ELEMENTS]
    assert SENTINEL not in "".join(body.itertext())


def test_no_words_paths_or_file_names_reach_the_report_or_the_manifest(tmp_path: Path) -> None:
    root = tmp_path / "debate"
    fixtures.write_tree(root, load_style_profile(), variant=SENTINEL)
    selection, survey, read = analysis.analyze([root], EXCLUDED, load_style_profile())
    written = report_of(survey) + analysis.render_manifest(
        analysis.manifest_rows(read, b"k" * 32), run_on=RUN_ON, excluded_folders=EXCLUDED
    )

    for forbidden in (SENTINEL, str(tmp_path), "debate/", "convention", "Practice Speech", "Public Forum", "~$"):
        assert forbidden not in written


# --------------------------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------------------------


def test_the_report_summary_names_what_most_files_do(tree: Path) -> None:
    report = report_of(survey_of(tree))

    assert report.splitlines()[0].startswith("<!-- docs-index: ")
    for line in (
        "- Evidence highlight colour: `cyan`, most common in 1 of 3 files with highlighting",
        "- Underlined evidence size: 22 half-points (11 pt), most common in 3 of 3 files with underlining",
        "- Not-underlined evidence size: 16 half-points (8 pt), most common in 1 of 3 files with text that is "
        "not underlined",
        "- Full cite size: 16 half-points (8 pt), most common in 1 of 3 files with cites",
        "- Evidence paragraphs holding text at or below the shrink maximum: 4 of 6",
        "- Cite paragraphs led by a short cite in the cite style: 4 of 5",
        "- Short cite runs that are bold: 5 of 5",
        "- Full cite runs that are bold: 0 of 5",
        "| Files analysed | 3 |",
        "| Run on | 2026-10-26 |",
        "| 2024-25 | LD | 1 |",
        "| duplicate bytes | 1 |",
        "| TAG | 4 | 3 | 3 (4) | `Heading4` (4) |",
        "| UNDERTAG | 1 | 1 | none (1) | `Undertag` (1) |",
        "| 16 half-points (8 pt) | 5 | 1 |",
        "| `cyan` | 3 | 1 |",
        "| 2024-25 | 1 | `cyan` | 22 half-points (11 pt) | 16 half-points (8 pt) | 16 half-points (8 pt) |",
        "| 2025-26 | 1 | `green` | 22 half-points (11 pt) | 12 half-points (6 pt) | 20 half-points (10 pt) |",
        "| 2026-27 | 1 | `yellow` | 22 half-points (11 pt) | 22 half-points (11 pt) | 22 half-points (11 pt) |",
    ):
        assert line in report, line


def test_an_unset_size_is_reported_as_not_set(tmp_path: Path) -> None:
    season = tmp_path / "2025-2026" / "LD"
    season.mkdir(parents=True)
    shutil.copyfile(STYLE_FIXTURE, season / STYLE_FIXTURE.name)

    report = report_of(survey_of(tmp_path / "2025-2026"))

    assert "- Full cite size: not set, most common in 1 of 1 files with cites" in report


def test_a_style_id_nobody_published_is_counted_but_never_named(tmp_path: Path) -> None:
    profile = load_style_profile()
    custom = fixtures.TeamFormatFixture(
        relative_path="2025-2026/LD/custom.docx",
        paragraphs=(fixtures.FormatParagraph((fixtures.FixtureRun("A tag"),), paragraph_style="JordanTag"),),
        extra_style_definitions=(("JordanTag", "paragraph", "Jordan Tag", "Heading4"),),
    )
    path = tmp_path / custom.relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(fixtures.build_docx(custom, profile))

    survey = survey_of(tmp_path / "2025-2026")

    assert survey.unit_style_ids == Counter({("TAG", "custom"): 1})
    assert survey.unit_outline_levels == Counter({("TAG", 3): 1})
    report = report_of(survey)
    assert "| TAG | 1 | 1 | 3 (1) | `custom` (1) |" in report
    assert "Jordan" not in report


@pytest.mark.parametrize(
    ("half_points", "label"), [(16, "16 half-points (8 pt)"), (21, "21 half-points (10.5 pt)"), (None, "not set")]
)
def test_sizes_are_labelled_in_half_points_and_points(half_points: int | None, label: str) -> None:
    assert analysis.size_label(half_points) == label


def test_ties_go_to_more_runs_then_to_the_smaller_size() -> None:
    assert analysis.most_common(Counter({22: 2, 16: 2, 20: 1})) == 16
    assert analysis.most_common(Counter({None: 3, 16: 3})) == 16
    assert analysis.most_common(Counter()) is None


# --------------------------------------------------------------------------------------------
# The manifest
# --------------------------------------------------------------------------------------------

_ROW = re.compile(r"^\| (?P<season>20\d\d-\d\d) \| (?P<event>LD|PF|Policy) \| `(?P<digest>[0-9a-f]{16})` \|$")


def test_the_manifest_lists_season_event_and_a_keyed_digest_prefix_only(tree: Path) -> None:
    key = b"a test key that is not the operator's".ljust(32, b".")
    _, _, read = analysis.analyze([tree], EXCLUDED, load_style_profile())

    manifest = analysis.render_manifest(analysis.manifest_rows(read, key), run_on=RUN_ON, excluded_folders=EXCLUDED)

    rows = [match.groupdict() for line in manifest.splitlines() if (match := _ROW.match(line))]
    table = [line for line in manifest.splitlines() if line.startswith("| ")]
    assert table[0] == "| Season | Event | Digest |"
    assert len(table) == 1 + len(rows)
    expected = []
    for relative in (
        "2024-2025/LD/cyan-convention.docx",
        "2025-2026/Public Forum/green-convention.docx",
        "2026-2027/Policy Debate/yellow-convention.docx",
    ):
        content = (tree / relative).read_bytes()
        keyed = hmac.new(key, content, hashlib.sha256).hexdigest()[:16]
        assert keyed != hashlib.sha256(content).hexdigest()[:16]
        expected.append(keyed)
    assert sorted(row["digest"] for row in rows) == sorted(expected)
    assert [row["digest"] for row in rows] == sorted(row["digest"] for row in rows)
    assert sorted((row["season"], row["event"]) for row in rows) == [
        ("2024-25", "LD"),
        ("2025-26", "PF"),
        ("2026-27", "Policy"),
    ]
    assert "Run on 2026-10-26: 3 files." in manifest


# --------------------------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------------------------


def test_the_command_line_writes_the_report_and_the_manifest(
    tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_file = tmp_path / "keys" / "digest.key"
    key_file.parent.mkdir()
    key_file.write_text("ab" * 32 + "\n", encoding="utf-8")
    monkeypatch.setenv("DEBATE_PARSER_EVAL_KEY_FILE", str(key_file))
    report, manifest = tmp_path / "out" / "survey.md", tmp_path / "out" / "MANIFEST.md"
    report.parent.mkdir()

    exit_code = analysis.main(
        [str(tree), "--exclude-dir", "Opencaselist", "--output", str(report), "--manifest", str(manifest),
         "--run-on", "2026-10-26"]
    )

    assert exit_code == 0
    assert "| Files analysed | 3 |" in report.read_text(encoding="utf-8")
    assert len([line for line in manifest.read_text(encoding="utf-8").splitlines() if _ROW.match(line)]) == 3


def test_a_manifest_without_the_digest_key_is_refused_before_anything_is_read(
    tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_PARSER_EVAL_KEY_FILE", str(tmp_path / "no-such.key"))
    manifest = tmp_path / "MANIFEST.md"

    with pytest.raises(Exception, match="no digest key"):
        analysis.main([str(tree), "--manifest", str(manifest)])

    assert not manifest.exists()


def test_the_report_goes_to_standard_output_without_an_output_path(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert analysis.main([str(tree), "--exclude-dir", "Opencaselist"]) == 0

    assert "| Files analysed | 3 |" in capsys.readouterr().out


def test_nothing_to_read_is_a_failure_not_an_empty_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "2025-2026" / "LD").mkdir(parents=True)
    output = tmp_path / "survey.md"

    assert analysis.main([str(tmp_path / "2025-2026"), "--output", str(output)]) == 2

    assert "no .docx files to analyse" in capsys.readouterr().err
    assert not output.exists()


# --------------------------------------------------------------------------------------------
# The committed synthetic tree
# --------------------------------------------------------------------------------------------


def test_the_committed_tree_is_what_the_generator_writes(tmp_path: Path) -> None:
    written = fixtures.write_tree(tmp_path, load_style_profile())

    committed = sorted(path.relative_to(COMMITTED_TREE) for path in COMMITTED_TREE.rglob("*.docx"))
    assert committed == sorted(path.relative_to(tmp_path) for path in written)
    for path in written:
        assert (COMMITTED_TREE / path.relative_to(tmp_path)).read_bytes() == path.read_bytes(), path.name

"""The bundle scan passes over the report's own fixed lines, and over nothing else (`v1-e32-t60`).

hspolicy26's dry run of 2026-11-06 found 76 hits, most of them a tournament's word in a line report.md
writes word for word: a table's header row, a note, the line saying round titles are not read. Those
lines are the template's, named once in :data:`~debate_core.arguments.landscape.render.FIXED_LINES`, and
a tournament found in one of them, whole and in its own file, is counted and passed over. A line with
anything from the caselist in it is a hit as before, however it begins.

Every tournament here is invented, chosen to collide with the template's own words: `Teams`, `Role`,
`Rank` and `Cite`. Every school, team code and path is invented too.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import re
from collections.abc import Callable, Iterable, Iterator
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Final, cast

import pytest
from pydantic import BaseModel

from debate_core.application.landscape_report import CIRCUIT_WIDE_FILES, LandscapeReportService
from debate_core.application.landscape_scan import (
    ExemptedLines,
    ScanKind,
    hits_digest,
    scan_bundle,
    scan_report,
)
from debate_core.arguments.landscape import render
from debate_core.arguments.landscape.render import FIXED_LINES, render_markdown
from debate_core.domain.caselist import Disclosure, Event, Side
from debate_core.testing.landscape_report import (
    read_synthetic_caselist,
    read_topic_change_caselist,
    synthetic_staleness,
)

REPO = Path(__file__).resolve().parents[4]
FIXTURE = REPO / "tests" / "fixtures" / "landscape" / "synthetic_caselist"
TOPIC_CHANGE = REPO / "tests" / "fixtures" / "landscape" / "topic_change_caselist"
SHA = "b" * 64
COLLIDING: Final = ("Teams", "Role", "Rank", "Cite")
"""Invented tournaments, each a word report.md's template writes."""

IMPACT_HEADER: Final = "| Rank | Teams | Tag | Cite | Scenario |"
CHAIN_HEADER: Final = "| Role | Teams | Tag | Cite |"
TEXT_HEADER: Final = "| Rank | Teams | Text |"
PLANK_HEADER: Final = "| Solves | Rank | Teams | Plank |"
TITLES_NOT_READ: Final = "The caselist's own round titles and cite entries are not read this season."
TEAMS_BULLET: Final = "* **Teams** are distinct teams, on any side."
LINK_CHAIN_LEAD: Final = "Link chain:"
NO_LABELLED_UNIQUENESS: Final = "| Uniqueness |  | no labelled card |  |"
TOP_CARDS_HEADER: Final = (
    "position_id,rank,fingerprint,teams_reading,tag,short_cite,source_object_key,element_index,"
    "source_snapshot,provenance_mode"
)
POSITIONS_HEADER: Final = (
    "position_id,label,kind,rounds,teams,aff_rounds,neg_rounds,first_seen_snapshot,is_new,share_of_teams"
)
"""The lines the build names, written here by hand from the template's text."""


def _disclosure(tournament: str, *, school: str = "Quillmere Academy", code: str = "QW") -> Disclosure:
    return Disclosure(
        source_sha256=SHA,
        caselist="synthetic26",
        snapshot=date(2026, 9, 15),
        event=Event.POLICY,
        school=school,
        team_code=code,
        side=Side.NEG,
        tournament=tournament,
        source_path=f"{school}/{code}/{school}-{code}-Neg-{tournament}-Round 2.docx",
    )


def _whole_word(word: str, line: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", line, re.IGNORECASE) is not None


# -- the fixed lines are passed over -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("file", "line", "tournament"),
    [
        ("report.md", IMPACT_HEADER, "Rank"),
        ("report.md", IMPACT_HEADER, "Teams"),
        ("report.md", IMPACT_HEADER, "Cite"),
        ("report.md", CHAIN_HEADER, "Role"),
        ("report.md", CHAIN_HEADER, "Cite"),
        ("report.md", TEXT_HEADER, "Rank"),
        ("report.md", PLANK_HEADER, "Teams"),
        ("report.md", TITLES_NOT_READ, "Cite"),
        ("report.md", TEAMS_BULLET, "Teams"),
        ("report.md", NO_LABELLED_UNIQUENESS, "Uniqueness"),
        ("report.md", LINK_CHAIN_LEAD, "Link Chain"),
        ("top_cards.csv", TOP_CARDS_HEADER, "Rank"),
        ("positions.csv", POSITIONS_HEADER, "Teams"),
    ],
)
def test_a_tournament_in_one_of_its_files_fixed_lines_is_counted_and_not_a_hit(
    file: str, line: str, tournament: str
) -> None:
    found = scan_bundle({file: f"{line}\n"}, [_disclosure(tournament)])
    assert found.hits == ()
    assert found.exempted == (ExemptedLines(file=file, term=tournament, lines=1),)


@pytest.mark.parametrize("tournament", COLLIDING)
def test_every_fixed_line_holding_a_colliding_tournament_is_passed_over(tournament: str) -> None:
    for file, lines in FIXED_LINES.items():
        holding = sorted(line for line in lines if _whole_word(tournament, line))
        found = scan_bundle({file: "\n".join(holding)}, [_disclosure(tournament)])
        assert found.hits == (), file
        assert found.exempted == ((ExemptedLines(file, tournament, len(holding)),) if holding else ())


def test_each_line_is_counted_once_per_tournament_and_the_counts_are_by_file_and_term() -> None:
    files = {
        "report.md": f"{IMPACT_HEADER}\n{CHAIN_HEADER}\n{IMPACT_HEADER}\nAt the Cite tournament, a tag.\n",
        "top_cards.csv": f"{TOP_CARDS_HEADER}\n",
    }
    found = scan_bundle(files, [_disclosure("Cite"), _disclosure("Rank", school="Brindle Valley", code="ZT")])
    assert found.exempted == (
        ExemptedLines("report.md", "Cite", 3),
        ExemptedLines("report.md", "Rank", 2),
        ExemptedLines("top_cards.csv", "Rank", 1),
    )
    assert [(hit.line_number, hit.term) for hit in found.hits] == [(4, "Cite")]


def test_what_was_passed_over_is_a_count_never_a_line() -> None:
    assert [one.name for one in dataclasses.fields(ExemptedLines)] == ["file", "term", "lines"]
    found = scan_bundle({"report.md": TITLES_NOT_READ}, [_disclosure("Cite")])
    assert "round titles" not in repr(found)


# -- every line with a value in it is a hit, as before -------------------------------------------------


@pytest.mark.parametrize(
    ("file", "line", "tournament"),
    [
        ("report.md", "| 1 | 3 | Rank and file workers strike | Okonkwo 26 | Dome |", "Rank"),
        ("report.md", "| Link | 2 | Spending crowds out | Cite Institute 26 |", "Cite"),
        (
            "report.md",
            "| Role Playing K (`role-playing-k`) | 3 | 2 | 0 | 3 | 50.0% | 2026-09-08 |  |",
            "Role",
        ),
        ("report.md", "| 1 | 2 | Teams of states should act. |", "Teams"),
        ("report.md", "* Rank 1: Dome collapse (scenario)", "Rank"),
        (
            "top_cards.csv",
            "spending-da,1,f00d,2,Teams of states act,Okonkwo 26,obj,0,2026-09-15,FILE_IMPORT",
            "Teams",
        ),
        ("top_cards.csv", "spending-da,1,f00d,2,States act,Cite 26,obj,0,2026-09-15,FILE_IMPORT", "Cite"),
        (
            "positions.csv",
            "# share_of_teams_over=teams disclosing on the position's side: aff 6, neg 6",
            "Teams",
        ),
    ],
)
def test_the_same_word_in_a_data_row_a_tag_or_a_cite_is_still_a_hit(
    file: str, line: str, tournament: str
) -> None:
    found = scan_bundle({file: line}, [_disclosure(tournament)])
    assert [(hit.file, hit.kind, hit.term, hit.line) for hit in found.hits] == [
        (file, ScanKind.TOURNAMENT, tournament, line)
    ]
    assert found.exempted == ()


def test_the_note_on_withheld_tags_carries_counts_and_is_still_a_hit() -> None:
    note = next(line for line in _golden_report().splitlines() if line.startswith("* **Tags left empty**"))
    for tournament in ("Rank", "Teams", "Cite"):
        found = scan_bundle({"report.md": note}, [_disclosure(tournament)])
        assert [hit.term for hit in found.hits] == [tournament]


def _upper(line: str) -> str:
    return line.upper()


def _lower(line: str) -> str:
    return line.lower()


def _doubled_space(line: str) -> str:
    return line.replace(" ", "  ", 1)


CHANGES: Final[dict[str, Callable[[str], str]]] = {
    "words": lambda line: f"{line} Okonkwo 26",
    "letter": lambda line: f"{line}x",
    "trailing-space": lambda line: f"{line} ",
    "leading-space": lambda line: f" {line}",
    "cell": lambda line: f"{line} |",
    "upper": _upper,
    "lower": _lower,
    "doubled-space": _doubled_space,
}


@pytest.mark.parametrize("line", [IMPACT_HEADER, CHAIN_HEADER, TITLES_NOT_READ, TEXT_HEADER])
@pytest.mark.parametrize("changed", list(CHANGES.values()), ids=list(CHANGES))
def test_a_fixed_line_with_anything_changed_is_a_hit(line: str, changed: Callable[[str], str]) -> None:
    text = changed(line)
    assert text != line
    tournament = "Cite" if line == TITLES_NOT_READ else "Teams"
    found = scan_bundle({"report.md": text}, [_disclosure(tournament)])
    assert [hit.term for hit in found.hits] == [tournament]
    assert found.exempted == ()


@pytest.mark.parametrize(
    "text",
    [f"{TOP_CARDS_HEADER},extra", f"{TOP_CARDS_HEADER} ", f" {TOP_CARDS_HEADER}", TOP_CARDS_HEADER.upper()],
    ids=["column", "trailing-space", "leading-space", "upper"],
)
def test_a_csv_header_row_with_anything_changed_is_a_hit(text: str) -> None:
    found = scan_bundle({"top_cards.csv": text}, [_disclosure("Rank")])
    assert [hit.term for hit in found.hits] == ["Rank"]
    assert found.exempted == ()


def test_a_fixed_line_is_passed_over_only_in_its_own_file() -> None:
    files = {"top_cards.csv": IMPACT_HEADER, "report.md": TOP_CARDS_HEADER, "schools.md": IMPACT_HEADER}
    found = scan_bundle(files, [_disclosure("Rank")])
    assert [hit.file for hit in found.hits] == ["report.md", "schools.md", "top_cards.csv"]
    assert found.exempted == ()


def test_only_a_tournament_is_passed_over_on_a_fixed_line() -> None:
    """A school or a team code is no tournament: on a fixed line it is a hit as it always was."""
    answers = "* A card under an `AT:` heading answers a position and never counts as reading it, and so does"
    bullet = next(line for line in FIXED_LINES["report.md"] if line.startswith(answers))
    found = scan_bundle(
        {"report.md": f"{bullet}\n{IMPACT_HEADER}"},
        [_disclosure("Lantern Classic", school="Teams", code="AT")],
    )
    assert [(hit.line_number, hit.kind) for hit in found.hits] == [
        (1, ScanKind.TEAM_CODE),
        (2, ScanKind.SCHOOL),
    ]


# -- the whole report ----------------------------------------------------------------------------------


def _golden_files() -> dict[str, str]:
    return dict(
        LandscapeReportService().bundle(read_synthetic_caselist(FIXTURE), synthetic_staleness()).files
    )


def _golden_report() -> str:
    return _golden_files()["report.md"]


def test_the_rendered_report_keeps_only_its_data_lines_as_hits() -> None:
    """Counted by hand in the golden report.md: `Cite` is in its 3 impact tables' header rows, its 6 link
    chains' header rows and the line on round titles, all fixed, and in the note on withheld tags, which
    carries counts. `Rank` is in top_cards.csv's and impact_cards.csv's header rows."""
    files = _golden_files()
    disclosures = (*read_synthetic_caselist(FIXTURE).disclosures, _disclosure("Cite"), _disclosure("Rank"))
    found = scan_bundle(
        files, disclosures, school_view_files=("schools.csv", "school_rounds.csv", "schools.md")
    )

    cite_hits = [hit for hit in found.hits if hit.term == "Cite"]
    assert [hit.line.startswith("* **Tags left empty**") for hit in cite_hits] == [True]
    assert ExemptedLines("report.md", "Cite", 10) in found.exempted
    assert ExemptedLines("top_cards.csv", "Rank", 1) in found.exempted
    assert ExemptedLines("impact_cards.csv", "Rank", 1) in found.exempted
    assert all(hit.line not in FIXED_LINES.get(hit.file, ()) for hit in found.hits)


def test_the_digest_of_the_remaining_hits_is_that_of_the_data_lines_alone() -> None:
    files = _golden_files()
    disclosures = [_disclosure(word) for word in COLLIDING]
    found = scan_bundle(files, disclosures)
    assert found.hits
    data_only = {
        name: "\n".join(line for line in text.splitlines() if line not in FIXED_LINES.get(name, ()))
        for name, text in files.items()
    }
    assert hits_digest(found.hits) == hits_digest(scan_bundle(data_only, disclosures).hits)
    moved = {
        name: f"{text}\n{IMPACT_HEADER}\n{CHAIN_HEADER}"
        for name, text in files.items()
        if name == "report.md"
    }
    assert hits_digest(scan_report({**files, **moved}, disclosures)) == hits_digest(found.hits)


# -- the template and the scan read the same lines -----------------------------------------------------


def _line_expressions(function: ast.FunctionDef) -> Iterator[ast.expr]:
    """What a report.md function writes as whole lines: list elements and `.append` arguments."""
    for node in ast.walk(function):
        if isinstance(node, ast.List):
            elements = node.elts
        elif (
            isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "append"
        ):
            elements = node.args
        else:
            continue
        for element in elements:
            yield from _branches(element)


def _branches(expression: ast.expr) -> Iterator[ast.expr]:
    if isinstance(expression, ast.IfExp):
        yield from _branches(expression.body)
        yield from _branches(expression.orelse)
    else:
        yield expression


def _report_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """render_markdown and every module function it reaches: what writes report.md."""
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    reached: dict[str, ast.FunctionDef] = {}
    waiting = ["render_markdown"]
    while waiting:
        name = waiting.pop()
        if name in reached:
            continue
        reached[name] = functions[name]
        waiting += [
            node.id
            for node in ast.walk(functions[name])
            if isinstance(node, ast.Name) and node.id in functions
        ]
    return reached


def _render_tree() -> ast.Module:
    return ast.parse(Path(inspect.getfile(render)).read_text(encoding="utf-8"))


def test_the_report_template_writes_no_line_word_for_word_that_the_scan_does_not_know() -> None:
    """A literal written as a whole line of report.md must be named in FIXED_LINES, never inline."""
    unknown: list[str] = []
    for name, function in _report_functions(_render_tree()).items():
        for expression in _line_expressions(function):
            value: object = None
            if isinstance(expression, ast.Constant):
                value = expression.value
                if isinstance(value, str) and re.search(r"\w", value):
                    unknown.append(f"{name}:{expression.lineno} writes {value[:40]!r} inline")
                    continue
            elif isinstance(expression, ast.Name):
                value = getattr(render, expression.id, None)
            elif isinstance(expression, ast.Attribute) and isinstance(expression.value, ast.Name):
                value = getattr(getattr(render, expression.value.id, None), expression.attr, None)
            if isinstance(value, str) and re.search(r"\w", value) and value not in FIXED_LINES["report.md"]:
                unknown.append(f"{name}:{expression.lineno} writes {value[:40]!r}, not in FIXED_LINES")
    assert unknown == []


def test_every_named_fixed_line_is_written_by_the_template() -> None:
    tree = _render_tree()
    named = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "_ReportLines")
    constants = {
        statement.target.id
        for statement in named.body
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
    }
    written = {
        node.attr
        for function in _report_functions(tree).values()
        for node in ast.walk(function)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "_ReportLines"
    }
    assert len(constants) > 40
    assert constants == written


def _values(found: object) -> Iterator[str]:
    """Every string a report or its trends holds, but an enum's: what the caselist put in it."""
    if isinstance(found, Enum):
        return
    if isinstance(found, str):
        yield found
    elif isinstance(found, BaseModel):
        for name in type(found).model_fields:
            yield from _values(getattr(found, name))
    elif dataclasses.is_dataclass(found) and not isinstance(found, type):
        for one in dataclasses.fields(found):
            yield from _values(getattr(found, one.name))
    elif isinstance(found, dict):
        for key, value in cast("dict[object, object]", found).items():
            yield from _values(key)
            yield from _values(value)
    elif isinstance(found, (tuple, list, set, frozenset)):
        for one in cast("Iterable[object]", found):
            yield from _values(one)


_ESCAPED: Final = re.compile(r"([\\`*_\[\]<>|])")


def _rendered_reports() -> Iterator[tuple[str, str, frozenset[str]]]:
    """report.md over the fixtures: this week, the first window, the topic change, and with no trends."""
    synthetic = read_synthetic_caselist(FIXTURE)
    weeks = [
        ("synthetic", synthetic),
        ("first window", dataclasses.replace(synthetic, through=date(2026, 9, 8))),
        ("topic change", read_topic_change_caselist(TOPIC_CHANGE)),
    ]
    for name, inputs in weeks:
        staleness = synthetic_staleness(caselist=inputs.caselist, newest_snapshot=inputs.through)
        bundle = LandscapeReportService().bundle(inputs, staleness)
        values = {
            form
            for value in (*_values(bundle.report), *_values(bundle.trends))
            if len(value) >= 4
            for form in (value, _ESCAPED.sub(r"\\\1", value))
        }
        yield name, render_markdown(bundle.report, bundle.trends), frozenset(values)
        yield f"{name}, no trends", render_markdown(bundle.report), frozenset(values)


def test_every_rendered_line_with_nothing_from_the_caselist_in_it_is_a_fixed_line() -> None:
    """A line with no digit and no value of the report's in it is the template's own: the scan must know it.

    The contents list is the exception: its line per part is built from which sections the week has, so it
    is not written word for word, and the scan reads it as before."""
    unknown: set[str] = set()
    for name, text, values in _rendered_reports():
        contents = False
        for line in text.splitlines():
            if line.startswith("#"):
                contents = line == "## Contents"
            if contents and line.startswith("* ["):
                continue
            if (
                not re.search(r"[A-Za-z]", line)
                or re.search(r"[0-9]", line)
                or any(v in line for v in values)
            ):
                continue
            if line not in FIXED_LINES["report.md"]:
                unknown.add(f"{name}: {line[:60]}")
    assert unknown == set()


def test_no_rendered_line_with_a_value_in_it_is_a_fixed_line() -> None:
    """No line holding a label, tag, cite, id or name of the report's is one the scan passes over.

    Digits prove nothing here: the template's own words hold some (`2AC`, `Scenario 1`, policy 1.13). That
    no count is written into a fixed line is the template test's: each is a literal, never formatted. A
    value the renderer's source writes itself proves nothing either: the fixture's `Midterms DA` is also
    the example the template's bullet on answers gives."""
    template = Path(inspect.getfile(render)).read_text(encoding="utf-8")
    checked = 0
    for _, text, values in _rendered_reports():
        from_the_caselist = [value for value in values if value not in template]
        for line in text.splitlines():
            if line in FIXED_LINES["report.md"]:
                checked += 1
                assert not [value for value in from_the_caselist if value in line], line
    assert checked > 100


def test_each_circuit_wide_csv_knows_its_first_line_and_its_header_row() -> None:
    files = _golden_files()
    assert set(FIXED_LINES) == set(CIRCUIT_WIDE_FILES)
    for name in CIRCUIT_WIDE_FILES:
        if name == "report.md":
            continue
        first, *rest = files[name].splitlines()
        header = next(line for line in rest if not line.startswith("#"))
        assert FIXED_LINES[name] == {first, header}, name
    assert TOP_CARDS_HEADER in FIXED_LINES["top_cards.csv"]
    assert POSITIONS_HEADER in FIXED_LINES["positions.csv"]

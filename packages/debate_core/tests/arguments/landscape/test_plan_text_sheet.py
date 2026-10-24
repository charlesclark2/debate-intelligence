"""The coach's plan-text sheet, clustered by the mechanism words that differ (`v1-e32-t09` ac2).

The PM's ruling of 2026-10-24: cluster by the mechanism words that tell plan texts apart. Every
expectation below was written by hand from the planted plan texts, never by running the code. Every
word, school and team here is invented.
"""

from __future__ import annotations

import io

from debate_core.arguments.landscape.plan_text_sheet import (
    PlanTextCluster,
    PlanTextSheet,
    PlanTextWords,
    cluster_plan_texts,
    render_plan_text_sheet,
    write_answers_csv,
)
from debate_core.arguments.landscape.source_headings import CaselistNames

FRAME = "the united states federal government should establish a sample payer system"
SAMPLE = "sample-plan-aff"
ROUTE = "route-plan-aff"
NAMES = CaselistNames({"Harbor Academy": ("HA",)})
NATIONAL = (
    "the",
    "united",
    "states",
    "federal",
    "government",
    "should",
    "establish",
    "a",
    "national",
    "program",
)


def item(sha: str, team: str, named: str | None, mechanism: str) -> PlanTextWords:
    return PlanTextWords(
        source_sha256=sha * 64,
        teams=frozenset({team}),
        named=named,
        words=tuple(f"{FRAME} {mechanism}".split()) if mechanism != "national program" else NATIONAL,
    )


ITEMS = [
    item("1", "team-one", SAMPLE, "financed by payroll levy"),
    item("2", "team-two", SAMPLE, "financed by harbor academy payroll levy"),
    item("3", "team-three", SAMPLE, "financed by new payroll levy"),
    item("7", "team-one", SAMPLE, "financed by payroll levy"),
    item("4", "team-four", ROUTE, "using voucher route"),
    item("5", "team-five", None, "using voucher route"),
    item("6", "team-six", None, "national program"),
]


def sheet(**options: object) -> PlanTextSheet:
    return cluster_plan_texts(ITEMS, NAMES, frame_share=0.8, **options)  # type: ignore[arg-type]


def test_plan_texts_cluster_by_the_words_that_tell_them_apart() -> None:
    found = sheet()
    assert found.clusters == (
        PlanTextCluster(
            label="C01",
            documents=4,
            teams=3,
            named=(SAMPLE,),
            shared_words=("financed", "levy", "payroll"),
            other_words=("new",),
        ),
        PlanTextCluster(
            label="C02",
            documents=2,
            teams=2,
            named=("none", ROUTE),
            shared_words=("route", "using", "voucher"),
            other_words=(),
        ),
    )
    assert (found.documents, found.teams) == (7, 6)
    assert found.frame_words == (
        "establish",
        "federal",
        "government",
        "payer",
        "sample",
        "should",
        "states",
        "system",
        "united",
    )
    assert (found.withheld_clusters, found.withheld_documents) == (1, 1)


def test_a_cluster_one_team_reads_is_counted_and_shown_only_below_the_minimum() -> None:
    found = sheet(minimum_teams=1)
    assert [(one.label, one.teams, one.shared_words) for one in found.clusters] == [
        ("C01", 3, ("financed", "levy", "payroll")),
        ("C02", 2, ("route", "using", "voucher")),
        ("C03", 1, ("national", "program")),
    ]
    assert found.withheld_clusters == 0


def test_a_one_word_edit_stays_apart_below_the_similarity() -> None:
    found = sheet(similarity=0.8)
    assert [(one.documents, one.teams, one.other_words) for one in found.clusters] == [(3, 2, ()), (2, 2, ())]
    assert (found.withheld_clusters, found.withheld_documents) == (2, 2)


def test_a_school_of_the_caselist_never_reaches_the_words() -> None:
    found = sheet(minimum_teams=1)
    words = {word for one in found.clusters for word in (*one.shared_words, *one.other_words)}
    assert not words & {"harbor", "academy", "ha"}


def test_the_frame_is_what_nearly_every_plan_text_shares() -> None:
    found = cluster_plan_texts(ITEMS, NAMES)
    assert "sample" in found.frame_words
    assert "financed" not in found.frame_words
    assert cluster_plan_texts(ITEMS, NAMES, frame_share=0.5).frame_words[:2] == ("establish", "federal")
    assert "financed" in cluster_plan_texts(ITEMS, NAMES, frame_share=0.5).frame_words


def test_no_plan_text_gives_an_empty_sheet() -> None:
    found = cluster_plan_texts([], NAMES)
    assert (found.clusters, found.documents, found.teams, found.withheld_clusters) == ((), 0, 0, 0)


EXPECTED_SHEET = "\n".join(
    [
        "# Plan texts on sample26, through 2026-10-20",
        "",
        "Taxonomy 1.0.0. 7 affirmative documents with a plan text, disclosed by 6 teams.",
        "",
        "Words in at least 80% of all plan texts are left out as the frame plans share: establish, "
        "federal, government, payer, sample, should, states, system, united. What is left of a plan "
        "text is its mechanism words, and plan texts are grouped by them. A cluster's documents all "
        "hold its first column of words; some hold the second.",
        "",
        "1 cluster (1 document) read by fewer than 2 teams is counted here and not shown: one team's "
        "plan text can point at the team.",
        "",
        "| Cluster | Teams | Documents | Aff its plan texts name | Words in every plan text "
        "| Words in some |",
        "|---|---|---|---|---|---|",
        "| C01 | 3 | 4 | sample-plan-aff | financed, levy, payroll | new |",
        "| C02 | 2 | 2 | none, route-plan-aff | route, using, voucher | |",
        "",
        "For each cluster that is a mechanism of its aff, write a short name in sentence case and the tag "
        "keywords that mark it in `plan-text-answers.csv` beside this sheet. Leave a row blank to keep it "
        "under its aff.",
        "",
    ]
)

EXPECTED_ANSWERS = """\
cluster,teams,documents,aff_named,words_in_every_plan_text,mechanism_name,tag_keywords\r
C01,3,4,sample-plan-aff,financed levy payroll,,\r
C02,2,2,none route-plan-aff,route using voucher,,\r
"""


def test_the_sheet_reads_as_written_by_hand() -> None:
    assert render_plan_text_sheet(
        sheet(), caselist="sample26", taxonomy_version="1.0.0", through="2026-10-20"
    ) == (EXPECTED_SHEET)


def test_the_answers_csv_has_a_blank_name_and_keywords_per_cluster() -> None:
    stream = io.StringIO(newline="")
    write_answers_csv(sheet(), stream)
    assert stream.getvalue() == EXPECTED_ANSWERS


def test_neither_file_names_a_team_or_a_withheld_word() -> None:
    rendered = render_plan_text_sheet(
        sheet(), caselist="sample26", taxonomy_version="1.0.0", through="2026-10-20"
    )
    stream = io.StringIO(newline="")
    write_answers_csv(sheet(), stream)
    for text in (rendered, stream.getvalue()):
        for word in ("team-one", "team-six", "national", "program", "harbor", "academy"):
            assert word not in text

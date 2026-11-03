"""The coach's plan-text sheet, clustered by the mechanism words that differ (`v1-e32-t09` ac2).

The PM's rulings of 2026-10-24: cluster by the mechanism words that tell plan texts apart (question
7), and show each cluster's commonest plan text verbatim, one-team clusters included, never beside a
school or team code (review ruling 1, under data-use policy 1.13). Every expectation below was
written by hand from the planted plan texts, never by running the code. Every word, school and team
here is invented.
"""

from __future__ import annotations

import io
import re

from debate_core.arguments.landscape.plan_text_sheet import (
    PlanTextCluster,
    PlanTextSheet,
    PlanTextWords,
    cluster_plan_texts,
    render_plan_text_sheet,
    write_answers_csv,
)
from debate_core.arguments.landscape.source_headings import CaselistNames

FRAME = "The United States federal government should establish a sample payer system"
SAMPLE = "sample-plan-aff"
ROUTE = "route-plan-aff"
NAMES = CaselistNames({"Harbor Academy": ("HA",)})

PAYROLL = f"{FRAME} financed by payroll levy."
PAYROLL_AT_A_SCHOOL = f"{FRAME} financed by Harbor Academy payroll levy."
NEW_PAYROLL = f"{FRAME} financed by new payroll levy."
VOUCHER = f"{FRAME} using voucher route."
VOUCHER_SPACED = f"{FRAME}  using\tvoucher route."
NATIONAL = "The United States federal government should establish a national program."


def item(sha: str, team: str, named: str | None, *texts: str) -> PlanTextWords:
    return PlanTextWords(
        source_sha256=sha * 64,
        teams=frozenset({team}),
        named=named,
        words=tuple(word for text in texts for word in re.findall(r"[0-9a-z]+", text.casefold())),
        texts=texts,
    )


ITEMS = [
    item("1", "team-one", SAMPLE, PAYROLL),
    item("2", "team-two", SAMPLE, PAYROLL_AT_A_SCHOOL),
    item("3", "team-three", SAMPLE, NEW_PAYROLL),
    item("7", "team-one", SAMPLE, PAYROLL),
    item("4", "team-four", ROUTE, VOUCHER),
    item("5", "team-five", None, VOUCHER_SPACED),
    item("6", "team-six", None, NATIONAL),
]


def sheet(items: list[PlanTextWords] = ITEMS, **options: object) -> PlanTextSheet:
    return cluster_plan_texts(items, NAMES, frame_share=0.8, **options)  # type: ignore[arg-type]


def render(found: PlanTextSheet) -> str:
    return render_plan_text_sheet(found, caselist="sample26", taxonomy_version="1.0.0", through="2026-10-20")


def test_plan_texts_cluster_by_the_words_that_tell_them_apart_one_team_clusters_included() -> None:
    found = sheet()
    assert found.clusters == (
        PlanTextCluster(
            label="C01",
            documents=4,
            teams=3,
            named=(SAMPLE,),
            shared_words=("financed", "levy", "payroll"),
            other_words=("new",),
            text=PAYROLL,
            text_documents=2,
        ),
        PlanTextCluster(
            label="C02",
            documents=2,
            teams=2,
            named=("none", ROUTE),
            shared_words=("route", "using", "voucher"),
            other_words=(),
            text=VOUCHER,
            text_documents=2,
        ),
        PlanTextCluster(
            label="C03",
            documents=1,
            teams=1,
            named=("none",),
            shared_words=("national", "program"),
            other_words=(),
            text=NATIONAL,
            text_documents=1,
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
    assert (found.withheld_clusters, found.withheld_documents, found.school_texts) == (0, 0, 1)


def test_a_minimum_of_two_teams_still_withholds_a_one_team_cluster() -> None:
    found = sheet(minimum_teams=2)
    assert [(one.label, one.teams, one.shared_words) for one in found.clusters] == [
        ("C01", 3, ("financed", "levy", "payroll")),
        ("C02", 2, ("route", "using", "voucher")),
    ]
    assert (found.withheld_clusters, found.withheld_documents) == (1, 1)
    assert (
        "1 cluster (1 document) read by fewer than 2 teams is counted here and not shown: one team's "
        "plan text can point at the team."
    ) in render(found)
    assert NATIONAL not in render(found)


def test_a_one_word_edit_stays_apart_below_the_similarity() -> None:
    found = sheet(similarity=0.8, minimum_teams=2)
    assert [(one.documents, one.teams, one.other_words) for one in found.clusters] == [(3, 2, ()), (2, 2, ())]
    assert (found.withheld_clusters, found.withheld_documents) == (2, 2)


def test_a_school_of_the_caselist_never_reaches_the_words_or_the_text() -> None:
    found = sheet()
    words = {word for one in found.clusters for word in (*one.shared_words, *one.other_words)}
    assert not words & {"harbor", "academy", "ha"}
    assert PAYROLL_AT_A_SCHOOL not in {one.text for one in found.clusters}
    assert "Harbor" not in render(found)


def test_a_cluster_whose_every_text_names_a_school_shows_no_text() -> None:
    found = sheet([item("2", "team-two", SAMPLE, PAYROLL_AT_A_SCHOOL)])
    (cluster,) = found.clusters
    assert (cluster.text, cluster.text_documents, found.school_texts) == (None, 0, 1)
    assert "No plan text of this cluster can be shown: each names a school of the caselist." in render(found)


def test_the_commonest_text_counts_texts_alike_but_for_their_spacing() -> None:
    (_, voucher, _) = sheet().clusters
    assert (voucher.text, voucher.text_documents) == (VOUCHER, 2)


def test_a_text_is_escaped_and_kept_on_one_line_in_the_sheet() -> None:
    awkward = f"{FRAME} under [Section 2] *and*\nits | rules."
    found = sheet([item("8", "team-one", SAMPLE, awkward), item("9", "team-two", SAMPLE, awkward)])
    assert (
        "> The United States federal government should establish a sample payer system under "
        "\\[Section 2\\] \\*and\\* its \\| rules."
    ) in render(found).splitlines()


def test_the_frame_is_what_nearly_every_plan_text_shares() -> None:
    found = cluster_plan_texts(ITEMS, NAMES)
    assert "sample" in found.frame_words
    assert "financed" not in found.frame_words
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
        "| Cluster | Teams | Documents | Aff its plan texts name | Words in every plan text "
        "| Words in some |",
        "|---|---|---|---|---|---|",
        "| C01 | 3 | 4 | sample-plan-aff | financed, levy, payroll | new |",
        "| C02 | 2 | 2 | none, route-plan-aff | route, using, voucher | |",
        "| C03 | 1 | 1 | none | national, program | |",
        "",
        "## The plan texts",
        "",
        "Each cluster's commonest plan text, word for word as its files hold it, and how many of the "
        "cluster's documents hold it exactly. No team or school is named beside a text, and a plan text "
        "that names a school of the caselist is not shown (1 document here).",
        "",
        "### C01: 3 teams, 4 documents",
        "",
        "> The United States federal government should establish a sample payer system financed by "
        "payroll levy.",
        "",
        "Held exactly by 2 of its 4 documents.",
        "",
        "### C02: 2 teams, 2 documents",
        "",
        "> The United States federal government should establish a sample payer system using voucher route.",
        "",
        "Held exactly by 2 of its 2 documents.",
        "",
        "### C03: 1 team, 1 document",
        "",
        "> The United States federal government should establish a national program.",
        "",
        "Held exactly by 1 of its 1 document.",
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
C03,1,1,none,national program,,\r
"""


def test_the_sheet_reads_as_written_by_hand() -> None:
    assert render(sheet()) == EXPECTED_SHEET


def test_the_answers_csv_has_a_blank_name_and_keywords_per_cluster() -> None:
    stream = io.StringIO(newline="")
    write_answers_csv(sheet(), stream)
    assert stream.getvalue() == EXPECTED_ANSWERS


def test_neither_file_names_a_team_or_a_school() -> None:
    rendered = render(sheet())
    stream = io.StringIO(newline="")
    write_answers_csv(sheet(), stream)
    for text in (rendered, stream.getvalue()):
        for word in ("team-one", "team-six", "harbor", "academy"):
            assert word not in text.casefold()

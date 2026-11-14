"""`scripts/import_golden_card.py`: the candidate lister, the shortlist and the excerpt.

Every file is invented and built under `tmp_path` (`tests/golden/synthetic_team_files.py`); no test
reads the operator's season folders. Every expected value below was written by hand from the
inputs, never by running the script (working agreement 6).
"""

from __future__ import annotations

import json
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import import_golden_card as golden  # noqa: E402
from tests.golden.synthetic_team_files import (  # noqa: E402
    FILLER,
    SyntheticCard,
    coach_attests,
    team_file,
    write_denylist,
)

from debate_core.integrations.docx_parser import DebateDocxParser  # noqa: E402

TEST_KEY = b"a test key that is not the operator's".ljust(32, b".")
OTHER_KEY = b"another key, also not the operator's".ljust(32, b".")
IMPORTED_ON = date(2026, 11, 13)

#: A word that appears only inside the invented cards, to prove the terminal never shows card text.
SENTINEL = "Zyxwvutsrq"

S = golden.SourceType
L = golden.LengthBand


# ------------------------------------------------------------------------------------------------
# Source type
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cite", "expected"),
    [
        ("Okonkwo 26 [Ada Okonkwo, NYT, https://www.nytimes.com/2026/01/02/us/grid.html]", S.NEWS),
        ("Lindqvist 25 [Lindqvist, https://apnews.com/article/x]", S.NEWS),
        ("Hale 24 [Hale, Wall Street Journal, 1-2-2024]", S.NEWS),
        ("Brennan 24 [Brennan, https://www.gao.gov/products/gao-24-1]", S.GOVERNMENT),
        ("Ruiz 23 [Ruiz, https://crsreports.congress.gov/product/pdf/R/R1]", S.GOVERNMENT),
        ("Ito 25 [Ito, https://www.mod.go.jp/en/x]", S.GOVERNMENT),
        ("Mbeki 22 [Mbeki, https://www.un.org/en/x]", S.GOVERNMENT),
        ("Park 24 [Park, Congressional Research Service, 4-1-2024]", S.GOVERNMENT),
        ("Varga 26 [Varga, Department of Energy Daily Briefing, 2026]", S.GOVERNMENT),
        ("Sato 25 [Sato, https://www.brookings.edu/articles/x]", S.THINK_TANK),
        ("Cole 23 [Cole, https://www.rand.org/pubs/x.html]", S.THINK_TANK),
        ("Diaz 24 [Diaz, fellow, Hudson Institute, 2024]", S.THINK_TANK),
        ("Nkemelu 25 [Nkemelu, https://doi.org/10.1000/xyz123]", S.JOURNAL),
        ("Abara 25 [Abara, Energy Policy 12(3), doi:10.1016/j.enpol.2025.1]", S.JOURNAL),
        ("Weiss 22 [Weiss, https://www.jstor.org/stable/123]", S.JOURNAL),
        ("Orr 21 [Orr, Harvard Law Review, Vol. 134]", S.JOURNAL),
        ("Kahn 26 [Kahn, https://medium.com/@kahn/grid]", S.UNKNOWN),
        ("Lowe 26 [Lowe, independent writer, 2026]", S.UNKNOWN),
    ],
)
def test_source_type_comes_from_the_link_then_the_words(cite: str, expected: golden.SourceType) -> None:
    assert golden.classify_source(cite) is expected


def test_a_known_host_outranks_the_words_of_the_cite() -> None:
    # The words say "Institute"; the host is a newspaper's.
    assert golden.classify_source("Quinn 25 [Quinn, Institute fellow, https://www.reuters.com/x]") is S.NEWS


@pytest.mark.parametrize(
    ("cite", "expected"),
    [
        ("A [A, https://www.reuters.com/a/b.]", "https://www.reuters.com/a/b"),
        ("A [A, www.cato.org/blog/x, accessed 2026]", "https://www.cato.org/blog/x"),
        ("A [A, Journal of X, 10.1000/abc.123]", "https://doi.org/10.1000/abc.123"),
        ("A [A, a book with no link, 2019]", None),
    ],
)
def test_the_source_link_is_the_first_link_or_the_doi(cite: str, expected: str | None) -> None:
    assert golden.source_link(cite) == expected


# ------------------------------------------------------------------------------------------------
# Cutter marks
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cite", "kept"),
    [
        ("Okonkwo 26 [Okonkwo, https://x.org/a] //MQ", "Okonkwo 26 [Okonkwo, https://x.org/a]"),
        ("Okonkwo 26 [Okonkwo, 2026]//mq", "Okonkwo 26 [Okonkwo, 2026]"),
        ("Okonkwo 26 [Okonkwo, 2026] \\\\AD", "Okonkwo 26 [Okonkwo, 2026]"),
        ("Okonkwo 26 [Okonkwo, 2026] // QZX MQ", "Okonkwo 26 [Okonkwo, 2026]"),
        ("Okonkwo 26 [Okonkwo, 2026] [QZX MQ]", "Okonkwo 26 [Okonkwo, 2026]"),
        ("Okonkwo 26 [Okonkwo, 2026] (MQ)", "Okonkwo 26 [Okonkwo, 2026]"),
        ("Okonkwo 26 [Okonkwo, 2026] -MQ", "Okonkwo 26 [Okonkwo, 2026]"),
        ("Okonkwo 26 [Okonkwo, https://x.org/a] MQ", "Okonkwo 26 [Okonkwo, https://x.org/a]"),
        ("Okonkwo 26 [Okonkwo, https://x.org/a MQ", "Okonkwo 26 [Okonkwo, https://x.org/a"),
    ],
)
def test_a_cutter_mark_at_the_end_of_a_cite_is_removed(cite: str, kept: str) -> None:
    assert golden.strip_cutter_mark(cite) == (kept, 1)


@pytest.mark.parametrize(
    "cite",
    [
        "Okonkwo 26 [Okonkwo, https://www.example.org/a/b]",
        "Okonkwo 26 [Okonkwo, accessed 10-2-24]",
        "Okonkwo 26 [Okonkwo, report] [PDF]",
        "Okonkwo 26 [Okonkwo, wire story] (AP)",
        "Okonkwo 26 [Okonkwo, https://x.org/a] PDF",
        "Okonkwo 26 [Okonkwo, Policy Analyst, Cato]",
        "Okonkwo 26 [Okonkwo, 2026] //2026",
    ],
)
def test_a_cite_that_ends_in_its_own_words_keeps_them(cite: str) -> None:
    assert golden.strip_cutter_mark(cite) == (cite, 0)


# ------------------------------------------------------------------------------------------------
# Length band and omission cut
# ------------------------------------------------------------------------------------------------


def test_length_band_is_short_for_one_paragraph_and_multi_for_more() -> None:
    assert [golden.length_band(count) for count in (1, 2, 5)] == [
        L.SHORT,
        L.MULTI_PARAGRAPH,
        L.MULTI_PARAGRAPH,
    ]


@pytest.mark.parametrize(
    ("body", "cut"),
    [
        ("words … words", True),
        ("words ... words", True),
        ("words [...] words", True),
        ("no cut here.", False),
    ],
)
def test_an_omission_cut_is_one_of_the_profiles_markers(body: str, cut: bool) -> None:
    markers = DebateDocxParser().profile.cite.wiki_ellipsis_markers

    assert golden.has_omission_cut(body, markers) is cut


# ------------------------------------------------------------------------------------------------
# Listing a tree of season folders
# ------------------------------------------------------------------------------------------------


def _card(
    tag: str, cite_rest: str, paragraphs: int = 1, *, cut: bool = False, link: str | None = None
) -> SyntheticCard:
    ending = " and then … after the cut." if cut else "."
    return SyntheticCard(
        tag=tag,
        short_cite="Okonkwo 26",
        cite_rest=cite_rest,
        link=link,
        body=[f"{SENTINEL} opens {FILLER} {{warrant}}{ending}"]
        + [f"More {FILLER} {{warrant}}."] * (paragraphs - 1),
    )


def _abbreviated() -> SyntheticCard:
    return SyntheticCard(
        tag="A disclosed card",
        short_cite="Okonkwo 26",
        cite_rest=" [Okonkwo, https://www.reuters.com/x]",
        body=["The first few words {warrant} … and the last few words."],
    )


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """Three events, plus every kind of folder and card the lister leaves out."""
    root = tmp_path / "debate"
    files = {
        ("2025-2026", "Policy Debate", "aff.docx"): [
            _card("Policy news", " [Okonkwo, {link}]", link="https://www.reuters.com/world/a"),
            _card("Policy think tank", " [Okonkwo, https://www.rand.org/pubs/a.html]", 2, cut=True),
            _card("No link", " [Okonkwo, a book, 2019]"),
            _abbreviated(),
            SyntheticCard(
                tag="Short",
                short_cite="Okonkwo 26",
                cite_rest=" [https://www.reuters.com/b]",
                body=["Too {warrant} short."],
            ),
            SyntheticCard(
                tag="Footnoted",
                short_cite="Okonkwo 26",
                cite_rest=" [https://www.reuters.com/c]",
                body=[f"Body {FILLER} {{warrant}}."],
                footnoted=True,
            ),
        ],
        ("2024-2025", "LD", "neg.docx"): [
            _card("LD government", " [Okonkwo, https://www.gao.gov/a]"),
            _card("LD journal", " [Okonkwo, https://doi.org/10.1000/a]", 3),
        ],
        ("2026-2027", "Public Forum", "pro.docx"): [_card("PF unknown", " [Okonkwo, https://medium.com/a]")],
        ("2026-2027", "Practice Speech", "speech.docx"): [
            _card("No event", " [Okonkwo, https://www.reuters.com/z]")
        ],
        ("2026-2027", "Opencaselist", "other.docx"): [
            _card("Another program", " [Okonkwo, https://www.reuters.com/y]")
        ],
    }
    for (season, folder, name), cards in files.items():
        (root / season / folder).mkdir(parents=True, exist_ok=True)
        (root / season / folder / name).write_bytes(team_file(cards, heading=f"{folder} block"))
    (root / "2024-2025" / "LD" / "neg_copy.docx").write_bytes(
        (root / "2024-2025" / "LD" / "neg.docx").read_bytes()
    )
    (root / "2024-2025" / "LD" / "~$neg.docx").write_bytes(b"lock")
    return root


def _seasons(root: Path) -> list[Path]:
    return [root / "2024-2025", root / "2025-2026", root / "2026-2027"]


def test_the_lister_classifies_every_whole_card_and_counts_the_rest(tree: Path) -> None:
    listing = golden.list_candidates(_seasons(tree), golden.DEFAULT_EXCLUDED_FOLDERS, TEST_KEY)

    assert listing.files_read == 3
    assert dict(listing.skipped_files) == {
        "in an excluded folder": 1,
        "duplicate bytes": 1,
        "no season or event in the folder names": 1,
    }
    assert listing.cards_read == 9
    assert dict(listing.left_out) == {
        golden.LEFT_OUT_NO_LINK: 1,
        golden.LEFT_OUT_NOT_WHOLE: 1,
        golden.LEFT_OUT_SHORT_BODY: 1,
        golden.LEFT_OUT_UNCOPYABLE: 1,
    }
    assert sorted(
        (c.tag, c.event, c.season, c.source_type, c.length_band, c.omission_cut) for c in listing.candidates
    ) == [
        ("LD government", "LD", "2024-25", S.GOVERNMENT, L.SHORT, False),
        ("LD journal", "LD", "2024-25", S.JOURNAL, L.MULTI_PARAGRAPH, False),
        ("PF unknown", "PF", "2026-27", S.UNKNOWN, L.SHORT, False),
        ("Policy news", "Policy", "2025-26", S.NEWS, L.SHORT, False),
        ("Policy think tank", "Policy", "2025-26", S.THINK_TANK, L.MULTI_PARAGRAPH, True),
    ]


def test_candidate_ids_are_stable_keyed_and_name_the_event(tree: Path) -> None:
    first = golden.list_candidates(_seasons(tree), golden.DEFAULT_EXCLUDED_FOLDERS, TEST_KEY)
    again = golden.list_candidates(_seasons(tree), golden.DEFAULT_EXCLUDED_FOLDERS, TEST_KEY)
    other = golden.list_candidates(_seasons(tree), golden.DEFAULT_EXCLUDED_FOLDERS, OTHER_KEY)

    ids = [c.candidate_id for c in first.candidates]
    assert ids == [c.candidate_id for c in again.candidates]
    assert set(ids).isdisjoint(c.candidate_id for c in other.candidates)
    assert sorted(i.rsplit("-", 1)[0] for i in ids) == ["ld", "ld", "pf", "policy", "policy"]
    assert all(len(i.rsplit("-", 1)[1]) == 10 for i in ids)


def test_list_prints_counts_and_writes_the_shortlist_outside_the_repo(
    tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key_file = tmp_path / "keys" / "digest.key"
    key_file.parent.mkdir()
    key_file.write_text("ab" * 32 + "\n", encoding="utf-8")
    monkeypatch.setenv("DEBATE_PARSER_EVAL_KEY_FILE", str(key_file))
    output = tmp_path / "shortlist"

    status = golden.main(["list", *map(str, _seasons(tree)), "--output", str(output), "--workers", "1"])

    printed = capsys.readouterr().out
    assert status == 0
    assert "candidates: 5" in printed
    assert "shortlist: 5" in printed
    for leak in (SENTINEL, "Policy news", "Okonkwo", "reuters", "aff.docx", "Policy Debate", str(tree)):
        assert leak not in printed
    shortlist = (output / golden.SHORTLIST_NAME).read_text(encoding="utf-8")
    assert all(f"### {c.candidate_id}" in shortlist for c in golden.read_shortlist(output))
    assert "Tag: Policy think tank" in shortlist


def test_list_refuses_to_write_the_shortlist_inside_the_repository(
    tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_file = tmp_path / "keys" / "digest.key"
    key_file.parent.mkdir()
    key_file.write_text("ab" * 32 + "\n", encoding="utf-8")
    monkeypatch.setenv("DEBATE_PARSER_EVAL_KEY_FILE", str(key_file))

    status = golden.main(
        ["list", *map(str, _seasons(tree)), "--output", str(REPO_ROOT / "shortlist"), "--workers", "1"]
    )

    assert status == 2
    assert not (REPO_ROOT / "shortlist").exists()


def test_the_shortlist_writer_itself_refuses_a_folder_inside_the_repository() -> None:
    with pytest.raises(SystemExit, match="outside the repository"):
        golden.write_shortlist(REPO_ROOT / "shortlist", [])

    assert not (REPO_ROOT / "shortlist").exists()


def test_list_without_the_digest_key_stops(
    tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_PARSER_EVAL_KEY_FILE", str(tmp_path / "no.key"))

    assert golden.main(["list", *map(str, _seasons(tree)), "--output", str(tmp_path / "out")]) == 2
    assert not (tmp_path / "out").exists()


# ------------------------------------------------------------------------------------------------
# The shortlist
# ------------------------------------------------------------------------------------------------


def _candidate(
    number: int, event: str, source: golden.SourceType, band: golden.LengthBand, cut: bool, path: str
) -> golden.Candidate:
    return golden.Candidate(
        candidate_id=f"{event.lower()}-{number:010d}",
        event=event,
        season="2025-26",
        source_type=source,
        length_band=band,
        omission_cut=cut,
        body_words=50,
        path=path,
        sha256="0" * 64,
        first_element_index=number,
        last_element_index=number + 2,
        tag="t",
        full_cite="c",
        opening_words="o",
    )


def test_the_shortlist_takes_a_third_per_event_round_every_source_type_and_length() -> None:
    shapes = [
        (event, source, band, cut, f"{event}-{source.value}-{n}.docx")
        for event in golden.EVENTS
        for source in golden.SourceType
        for band in golden.LengthBand
        for cut in (False, True)
        for n in range(3)
    ]
    pool = [_candidate(number, *shape) for number, shape in enumerate(shapes)]

    shortlist = golden.choose_shortlist(pool, 45)

    assert len(shortlist) == 45
    for event in golden.EVENTS:
        picks = [c for c in shortlist if c.event == event]
        assert len(picks) == 15
        # Ten buckets (five source types by two lengths), each visited before any is visited twice;
        # the first visit to a bucket takes a cut card, the second an uncut one.
        assert {(c.source_type, c.length_band) for c in picks[:10]} == {
            (s, b) for s in golden.SourceType for b in golden.LengthBand
        }
        assert [c.omission_cut for c in picks] == [True] * 10 + [False] * 5
        # Fifteen files per event, three per source type: no file is used twice.
        assert len({c.path for c in picks}) == 15
    assert shortlist == golden.choose_shortlist(list(reversed(pool)), 45)


def test_the_shortlist_alternates_cuts_and_prefers_a_new_file() -> None:
    # One bucket, a share of four. A cut card first (3), then an uncut one from a file not yet used
    # (2, not 1, which shares a.docx with 3), then a cut one (4), and only then the file reused (1).
    pool = [
        _candidate(1, "LD", S.NEWS, L.SHORT, False, "a.docx"),
        _candidate(2, "LD", S.NEWS, L.SHORT, False, "b.docx"),
        _candidate(3, "LD", S.NEWS, L.SHORT, True, "a.docx"),
        _candidate(4, "LD", S.NEWS, L.SHORT, True, "c.docx"),
    ]

    assert [c.candidate_id for c in golden.choose_shortlist(pool, 12)] == [
        "ld-0000000003",
        "ld-0000000002",
        "ld-0000000004",
        "ld-0000000001",
    ]


# ------------------------------------------------------------------------------------------------
# Importing
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def listed(tree: Path) -> list[golden.Candidate]:
    return golden.list_candidates(_seasons(tree), golden.DEFAULT_EXCLUDED_FOLDERS, TEST_KEY).candidates


def _by_tag(candidates: list[golden.Candidate], tag: str) -> golden.Candidate:
    (candidate,) = [c for c in candidates if c.tag == tag]
    return candidate


def test_import_numbers_cases_per_event_and_writes_the_index(
    listed: list[golden.Candidate], tmp_path: Path
) -> None:
    denylist = golden.load_denylist(write_denylist(tmp_path / "outside" / "denylist.txt"))
    fixtures = tmp_path / "golden_cards"
    picks = [_by_tag(listed, tag).candidate_id for tag in ("Policy think tank", "LD journal", "Policy news")]

    cases, refused = golden.import_candidates(
        listed, picks, denylist, fixtures, today=IMPORTED_ON, attest=coach_attests
    )

    assert refused == []
    assert [case.case_id for case in cases] == ["policy-001", "ld-001", "policy-002"]
    think_tank = json.loads((fixtures / "policy-001" / "case.json").read_text(encoding="utf-8"))
    assert think_tank == {
        "case_id": "policy-001",
        "candidate_id": picks[0],
        "event": "Policy",
        "season": "2025-26",
        "source_type": "think tank",
        "length_band": "multi-paragraph",
        "omission_cut": True,
        "coach_cut_and_reviewed_for_names": True,
        "research_need": "Policy think tank",
        "source_link": "https://www.rand.org/pubs/a.html",
        "parser_version": DebateDocxParser().parser_version,
        "imported_on": "2026-11-13",
    }
    index = (fixtures / "INDEX.md").read_text(encoding="utf-8")
    assert "| `ld-001` | LD | 2024-25 | journal | multi-paragraph | no | LD journal |" in index
    assert (
        "| `policy-001` | Policy | 2025-26 | think tank | multi-paragraph | yes | Policy think tank |"
        in index
    )
    assert index.endswith("\n3 cases.\n")


def test_import_refuses_an_unknown_id_a_repeat_and_a_changed_file(
    listed: list[golden.Candidate], tree: Path, tmp_path: Path
) -> None:
    denylist = golden.load_denylist(write_denylist(tmp_path / "outside" / "denylist.txt"))
    fixtures = tmp_path / "golden_cards"
    news, government = _by_tag(listed, "Policy news"), _by_tag(listed, "LD government")
    golden.import_candidates(
        listed, [news.candidate_id], denylist, fixtures, today=IMPORTED_ON, attest=coach_attests
    )
    (tree / "2024-2025" / "LD" / "neg.docx").write_bytes(
        team_file([_card("Edited", " [https://www.gao.gov/b]")])
    )

    cases, refused = golden.import_candidates(
        listed,
        ["policy-ffffffffff", news.candidate_id, government.candidate_id],
        denylist,
        fixtures,
        today=IMPORTED_ON,
        attest=coach_attests,
    )

    assert cases == []
    assert [(r.candidate_id, r.reason) for r in refused] == [
        ("policy-ffffffffff", golden.REFUSED_UNKNOWN_ID),
        (news.candidate_id, golden.REFUSED_ALREADY_IMPORTED),
        (government.candidate_id, golden.REFUSED_FILE_CHANGED),
    ]


def test_the_excerpt_rereads_as_the_card_and_keeps_only_what_the_card_needs(
    listed: list[golden.Candidate], tmp_path: Path
) -> None:
    denylist = golden.load_denylist(write_denylist(tmp_path / "outside" / "denylist.txt"))
    fixtures = tmp_path / "golden_cards"
    news = _by_tag(listed, "Policy news")

    golden.import_candidates(
        listed, [news.candidate_id], denylist, fixtures, today=IMPORTED_ON, attest=coach_attests
    )

    excerpt = (fixtures / "policy-001" / golden.EXCERPT_NAME).read_bytes()
    source_cards = golden._parse(DebateDocxParser(), Path(news.path).read_bytes())  # noqa: SLF001
    reread = golden._parse(DebateDocxParser(), excerpt)  # noqa: SLF001
    assert source_cards is not None and reread is not None
    (card,) = reread.cards
    (original,) = [c for c in source_cards.cards if c.tag == "Policy news"]
    assert card.tag == "Policy news"
    assert card.full_cite == original.full_cite
    assert card.evidence_text == original.evidence_text
    assert card.formatting_spans == original.formatting_spans
    with zipfile.ZipFile(Path(news.path)) as archive:
        assert "word/header1.xml" in archive.namelist()
    with zipfile.ZipFile(fixtures / "policy-001" / golden.EXCERPT_NAME) as archive:
        assert sorted(archive.namelist()) == [
            "[Content_Types].xml",
            "_rels/.rels",
            "docProps/core.xml",
            "word/_rels/document.xml.rels",
            "word/document.xml",
            "word/settings.xml",
            "word/styles.xml",
        ]
        relationships = archive.read("word/_rels/document.xml.rels").decode("utf-8")
        settings = archive.read("word/settings.xml").decode("utf-8")
        document = archive.read("word/document.xml").decode("utf-8")
    assert "https://www.reuters.com/world/a" in relationships
    assert "header" not in relationships and "comments" not in relationships
    assert "attachedTemplate" not in settings and "docVar" not in settings
    assert "headerReference" not in document


def test_import_takes_ids_space_or_comma_separated(
    listed: list[golden.Candidate], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shortlist_dir = tmp_path / "shortlist"
    golden.write_shortlist(shortlist_dir, listed)
    denylist = write_denylist(tmp_path / "outside" / "denylist.txt")
    news, journal, unknown = (
        _by_tag(listed, t).candidate_id for t in ("Policy news", "LD journal", "PF unknown")
    )

    status = golden.main(
        [
            "import",
            "--shortlist",
            str(shortlist_dir),
            "--denylist",
            str(denylist),
            "--fixtures",
            str(tmp_path / "golden_cards"),
            "--ids",
            f"{news},{journal}",
            unknown,
        ],
        today=IMPORTED_ON,
        attest=coach_attests,
    )

    printed = capsys.readouterr().out
    assert status == 0
    assert "imported 3, refused 0" in printed
    assert sorted(path.name for path in (tmp_path / "golden_cards").iterdir()) == [
        "INDEX.md",
        "ld-001",
        "pf-001",
        "policy-001",
    ]
    assert SENTINEL not in printed


# ------------------------------------------------------------------------------------------------
# The coach's attestation (PM ruling, 2026-11-14)
# ------------------------------------------------------------------------------------------------


def test_a_pick_the_coach_does_not_attest_is_refused_before_its_file_is_read(
    listed: list[golden.Candidate], tmp_path: Path
) -> None:
    denylist = golden.load_denylist(write_denylist(tmp_path / "outside" / "denylist.txt"))
    fixtures = tmp_path / "golden_cards"
    news, journal = _by_tag(listed, "Policy news"), _by_tag(listed, "LD journal")
    golden.import_candidates(
        listed, [news.candidate_id], denylist, fixtures, today=IMPORTED_ON, attest=coach_attests
    )
    asked: list[str] = []

    def only_the_news_card(candidate_id: str) -> bool:
        asked.append(candidate_id)
        return False

    Path(journal.path).unlink()
    cases, refused = golden.import_candidates(
        listed,
        ["policy-ffffffffff", news.candidate_id, journal.candidate_id],
        denylist,
        fixtures,
        today=IMPORTED_ON,
        attest=only_the_news_card,
    )

    assert cases == []
    assert [(r.candidate_id, r.reason) for r in refused] == [
        ("policy-ffffffffff", golden.REFUSED_UNKNOWN_ID),
        (news.candidate_id, golden.REFUSED_ALREADY_IMPORTED),
        (journal.candidate_id, golden.REFUSED_NOT_ATTESTED),
    ]
    assert asked == [journal.candidate_id]
    assert sorted(path.name for path in fixtures.iterdir()) == ["INDEX.md", "policy-001"]


class _Terminal:
    """A stand-in for the operator's terminal: what the coach types, and whether it is a terminal."""

    def __init__(self, typed: str, *, is_a_terminal: bool) -> None:
        self._lines = iter(typed.splitlines(keepends=True))
        self._is_a_terminal = is_a_terminal
        self.written = ""

    def isatty(self) -> bool:
        return self._is_a_terminal

    def readline(self) -> str:
        return next(self._lines, "")

    def write(self, text: str) -> int:
        self.written += text
        return len(text)

    def flush(self) -> None:
        return None


@pytest.mark.parametrize(
    ("typed", "attested"),
    [("yes\n", True), ("  YES \n", True), ("y\n", False), ("no\n", False), ("\n", False), ("", False)],
)
def test_only_yes_at_the_terminal_attests(typed: str, attested: bool) -> None:
    terminal = _Terminal(typed, is_a_terminal=True)

    answer = golden.terminal_attestation(terminal, terminal)("policy-0a1b2c3d4e")  # type: ignore[arg-type]

    assert answer is attested
    assert terminal.written == (
        "policy-0a1b2c3d4e: did the coach cut or re-cut this card, and review it for names? "
        "Type yes to import it: "
    )


def test_with_no_terminal_nothing_is_attested_and_nothing_is_asked() -> None:
    piped = _Terminal("yes\n", is_a_terminal=False)

    assert golden.terminal_attestation(piped, piped)("policy-0a1b2c3d4e") is False  # type: ignore[arg-type]
    assert piped.written == ""


def test_import_with_no_terminal_refuses_every_pick(
    listed: list[golden.Candidate],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shortlist_dir = tmp_path / "shortlist"
    golden.write_shortlist(shortlist_dir, listed)
    denylist = write_denylist(tmp_path / "outside" / "denylist.txt")
    news, journal = (_by_tag(listed, t).candidate_id for t in ("Policy news", "LD journal"))
    monkeypatch.setattr(sys, "stdin", _Terminal("yes\nyes\n", is_a_terminal=False))
    fixtures = tmp_path / "golden_cards"

    status = golden.main(
        [
            "import",
            "--shortlist",
            str(shortlist_dir),
            "--denylist",
            str(denylist),
            "--fixtures",
            str(fixtures),
            "--ids",
            news,
            journal,
        ],
        today=IMPORTED_ON,
    )

    printed = capsys.readouterr().out
    assert status == 1
    assert printed.splitlines() == [
        f"refused {news}: {golden.REFUSED_NOT_ATTESTED}",
        f"refused {journal}: {golden.REFUSED_NOT_ATTESTED}",
        "imported 0, refused 2",
    ]
    assert sorted(path.name for path in fixtures.iterdir()) == ["INDEX.md"]

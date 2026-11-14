#!/usr/bin/env python3
"""Find golden-card candidates in the team's season folders, and copy the coach's picks into the repo.

`v1-e09-t01-golden-card-fixtures` builds the corpus the E09 evaluations are measured on: 24 to 30
cards the coach cut or re-cut, about a third each Policy, LD and PF, from every kind of source,
short and long.
The coach picks them; this script does the two mechanical steps around that choice.

## `list`: a shortlist the coach picks from

It walks the season folders read-only, parses every `.docx` with the platform's own parser
(:class:`~debate_core.integrations.docx_parser.DebateDocxParser`, the reading every other tool
uses, so a card here is a card everywhere), and classifies each whole card. It writes a balanced
shortlist of about 45 to a folder **outside the repository**, and prints counts only.

    uv run python scripts/import_golden_card.py list \\
        ~/Documents/debate/2024-2025 ~/Documents/debate/2025-2026 ~/Documents/debate/2026-2027 \\
        --output ~/golden-card-shortlist

The folder gets `shortlist.md`, for the coach to read (each candidate's ID, tag, cite and the first
words of its body), and `candidates.json`, which `import` reads to find each pick again (its file's
path and SHA-256 and its paragraphs). Both name files and carry team text, so the script refuses a
folder inside the repository. The terminal gets counts by event, season, source type, length band
and omission cut, and nothing else: no tag, cite, card text, name, path or file name.

**Which files.** Every `.docx` below the inputs, chosen exactly as
`scripts/analyze_team_formatting.py` chooses them (its `select_files`): Word lock files, byte-identical
duplicates and files under a folder named by `--exclude-dir` are left out. The defaults exclude
`Opencaselist` and `Camp Files`, the folders that hold other programs' files inside a season folder.

**Event** comes from the folder names, by `scripts/select_eval_files.py`'s rule: the outermost folder
whose name says LD (`LD`, `Lincoln`), PF (`PF`, `PFD`, `Public Forum`) or Policy. **Season** is the
nearest folder named like `2025-2026`. What that cannot tell, and does not guess: a file in a folder
that names no event (`Practice Speech`, a season folder's own root) is skipped and counted; a file
filed under one event but written for another is read as the folder's event; a folder whose name
says two events is read as the first rule that matches, LD before PF before Policy.

**Source type** comes from the cite: its link's host first, then the words of the publication.

* *government*: a `.gov` or `.mil` host or a national government's own domain (`.gov.uk`,
  `.gc.ca`, `europa.eu`), an intergovernmental body's (`un.org`, `who.int`, `imf.org`,
  `worldbank.org`, `oecd.org`, `nato.int`), or words such as `Congressional Research Service`,
  `Department of`, `Government Accountability Office`, `Ministry of`;
* *journal*: a DOI, a publisher's or index's host (`jstor.org`, `sciencedirect.com`,
  `springer.com`, `wiley.com`, `tandfonline.com`, `sagepub.com`, `academic.oup.com`, …), or words
  such as `Journal of`, `Law Review`, `Quarterly`, `Vol.`;
* *think tank*: a research institute's host (`brookings.edu`, `rand.org`, `csis.org`, `cfr.org`,
  `heritage.org`, `cato.org`, …) or words such as `Institute`, `Foundation`, `Center for`;
* *news*: a news organisation's host (`nytimes.com`, `reuters.com`, `apnews.com`, …) or its name;
* *unknown* otherwise. A host the tables do not know and a cite whose words say nothing are not
  guessed at: a university page, a blog, a company's site and a cite with no publication are unknown.

**Length band**: *short* when the body is one paragraph, *multi-paragraph* when it is more.
**Omission cut**: the body holds one of the style profile's ellipsis markers (`…`, `...`, `[…]`,
`[...]`, `***`). It cannot tell an ellipsis the cutter typed from one the author printed.

**Which cards** are candidates: whole cards (`FULL`, never a disclosure's first and last words),
with a tag and a cite, a body of at least :data:`MINIMUM_BODY_WORDS` words, a link or a DOI in the
cite (the source has to be fetched again), and nothing the lossless copier refuses (a table, a
picture, a text box, a footnote). Every card left out is counted by its first failing reason.

**The shortlist** takes about a third per event and, within an event, goes round every pairing of
source type and length band in turn, alternating cards with and without an omission cut, one card
per file until no other file is left. Candidates are taken in the order of their IDs, which are
keyed digests (below) and say nothing about who wrote a card or what it says.

**Candidate IDs** are stable: the event and the first ten hex digits of an HMAC-SHA256, under the
parser evaluation's digest key (`tests/evals/parser/digests.py`), of the file's bytes and the card's
first paragraph. The same file gives the same IDs on every run, and an ID joins to nothing without
the key, so one can be pasted into a command, a report or a case's `case.json`.

## `import`: the picked cards, scrubbed, into `tests/fixtures/golden_cards/`

    uv run python scripts/import_golden_card.py import --shortlist ~/golden-card-shortlist \\
        --ids policy-0a1b2c3d4e ld-...

For each ID it first asks the coach, in the terminal and by ID only, whether the coach cut or re-cut
the card and reviewed it for names (the product owner's ruling of 2026-11-14: debaters' own cuts are
not picked, and this attestation is the control in place of a roster denylist). Only `yes` imports
it; any other answer, or no terminal to ask in, refuses the pick, and `case.json` records the
attestation as `coach_cut_and_reviewed_for_names`. Then it re-reads the file (refusing one whose
bytes changed since the listing), finds the card again, and writes `<case_id>/team-card.docx` and
`<case_id>/case.json` under the fixtures folder, case ids numbered per event (`policy-001`,
`ld-001`, `pf-001`), then rewrites `INDEX.md`. The corpus's terms are in its `README.md`.

The excerpt is the source package cut down to the card's own paragraphs: the source's style table,
numbering, theme and settings are kept, so the card looks as it was cut, and every other part
is left behind (headers and footers, comments, `people.xml`, custom XML, footnotes, media, the
extended properties, the settings part's template link and document variables). Then it is scrubbed:

* **cutter marks**: initials or a school code trailing the cite (`//JS`, `\\\\AD`, `[QZX JS]`,
  `(JS)`, `] -JS`, or two to four capitals after the cite's closing link or bracket), removed, unless
  they are a file type, a wire, a country or an agency (`[PDF]`, `(AP)`, :data:`NOT_CUTTER_MARKS`);
* **document metadata, comments and tracked-change authors**, by
  `scripts/scrub_docx_fixture.py`'s `scrub_package`: `docProps` author, `lastModifiedBy`, title and
  the rest blanked, comment markup removed, every `w:author` written `Redacted`;
* **an optional denylist**, only when `--denylist` names one, by the same scrub, and verified by
  it: a name left anywhere deletes the output.

The first two run on every import, denylist or not. With a denylist, a card whose body holds a
listed entry is refused, because replacing it would change the evidence the case exists to hold.
The excerpt is parsed again and must read as one card with the
source card's body text and formatting spans exactly; otherwise it is refused. What it prints per
case is counts of what was removed, never the removed text. A refusal names the ID and a reason
code, never the card.

`case.json` records the event, season, source type, length band, omission cut, the cite's link (the
source to record at the next step) and the research need: the card's tag, which says what the card
is for, written through the denylist when one is given. The coach may rewrite it when labelling.

## The denylist: optional, off by default

The product owner's ruling of 2026-11-14 replaced the roster denylist with the coach's attestation,
so `import` and `check` run without one, and none is read unless `--denylist` names it. A denylist
named that way is a plain text file outside the repository, one entry per line (names, school and
team codes, initials). Blank lines are ignored. Matching ignores case and spacing, and an entry of
four characters or fewer matches only as a whole word. **A named denylist that is missing, empty or
inside the repository is an error**: asking for a check and getting none would pass everything.

## `check`: no fixture carries metadata

    uv run python scripts/import_golden_card.py check

Reads every file under the fixtures folder: each `.docx` must carry no author or `lastModifiedBy`,
no company or manager, no comments or people part, and no tracked-change author but `Redacted`.
With `--denylist`, no file may hold a listed entry either. It prints counts, whether a denylist was
used, and the case paths that fail, never what matched.

Owned by `v1-e09-t01-golden-card-fixtures`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from typing import Any, Final, TextIO
from urllib.parse import urlsplit
from xml.sax.saxutils import quoteattr

from lxml import etree

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import scrub_docx_fixture as scrub  # noqa: E402
from analyze_team_formatting import select_files  # noqa: E402
from tests.evals.parser.digests import MissingDigestKeyError, keyed_digest, require_key  # noqa: E402

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin  # noqa: E402
from debate_core.domain.debate_files import (  # noqa: E402
    CardCompleteness,
    ParsedCard,
    ParsedDocument,
)
from debate_core.domain.style_profile import StructuralUnit  # noqa: E402
from debate_core.integrations.docx_file_writer.base_template import load_base_template  # noqa: E402
from debate_core.integrations.docx_file_writer.package_writer import write_package  # noqa: E402
from debate_core.integrations.docx_file_writer.run_copier import (  # noqa: E402
    HyperlinkTargets,
    UnsupportedCard,
    copy_card,
    open_source,
)
from debate_core.integrations.docx_parser import (  # noqa: E402
    DebateDocxParser,
    open_debate_docx,
)
from debate_core.integrations.docx_parser.package import hardened_xml_parser  # noqa: E402
from debate_core.integrations.docx_parser.parser import body_paragraphs  # noqa: E402

__all__ = [
    "DEFAULT_EXCLUDED_FOLDERS",
    "DEFAULT_SHORTLIST_SIZE",
    "FIXTURES_DIR",
    "MINIMUM_BODY_WORDS",
    "NO_DENYLIST",
    "Candidate",
    "CheckReport",
    "DenylistError",
    "ImportRefused",
    "ImportedCase",
    "LengthBand",
    "Listing",
    "SourceType",
    "build_excerpt",
    "check_fixtures",
    "choose_shortlist",
    "classify_source",
    "count_lines",
    "has_omission_cut",
    "import_candidates",
    "length_band",
    "list_candidates",
    "load_denylist",
    "main",
    "metadata_problems",
    "read_shortlist",
    "render_index",
    "source_link",
    "strip_cutter_mark",
    "write_index",
    "write_shortlist",
]

FIXTURES_DIR: Final = REPO_ROOT / "tests" / "fixtures" / "golden_cards"
DEFAULT_EXCLUDED_FOLDERS: Final = ("Opencaselist", "Camp Files")
DEFAULT_SHORTLIST_SIZE: Final = 45

#: The shortest body a candidate may have. A golden case is measured on its warrants; a body of a
#: sentence or two has too little to select from to say anything about a selection.
MINIMUM_BODY_WORDS: Final = 20

#: How many words of a body the shortlist shows, so the coach can recognise the card.
OPENING_WORDS: Final = 15

#: Hex digits of the keyed digest in a candidate ID.
CANDIDATE_DIGEST_LENGTH: Final = 10

EXCERPT_NAME: Final = "team-card.docx"
CASE_NAME: Final = "case.json"
INDEX_NAME: Final = "INDEX.md"
SHORTLIST_NAME: Final = "shortlist.md"
CANDIDATES_NAME: Final = "candidates.json"

EVENTS: Final = ("Policy", "LD", "PF")
_EVENT_SLUGS: Final = {"Policy": "policy", "LD": "ld", "PF": "pf"}

W_NS: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
RELS_NS: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS: Final = "http://schemas.openxmlformats.org/package/2006/content-types"
CORE_NS: Final = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS: Final = "http://purl.org/dc/elements/1.1/"
EXTENDED_NS: Final = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

_OFFICE_DOCUMENT_REL: Final = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
)
_CORE_PROPERTIES_REL: Final = (
    "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
)
_HYPERLINK_REL_SUFFIX: Final = "/hyperlink"

#: The document part's relationships an excerpt keeps, by the last segment of their type: what the
#: card's look depends on, and nothing that can carry anything else.
_KEPT_DOCUMENT_RELATIONSHIPS: Final = frozenset(
    {"styles", "stylesWithEffects", "settings", "numbering", "theme"}
)

#: Settings a source's `settings.xml` carries that an excerpt drops: the template link (a path that
#: routinely holds a user name) and the document variables and mail merge an add-in fills in.
_DROPPED_SETTINGS: Final = frozenset({"attachedTemplate", "docVars", "mailMerge"})

#: A section's links to headers and footers, which the excerpt does not keep.
_DROPPED_SECTION_REFERENCES: Final = frozenset({"headerReference", "footerReference"})

#: What a denylisted entry becomes in a tag or cite: plainly a removal, not a pseudonym.
REDACTED: Final = scrub.REDACTED_AUTHOR


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


# --------------------------------------------------------------------------------------------
# Classifying a card
# --------------------------------------------------------------------------------------------


class SourceType(StrEnum):
    NEWS = "news"
    THINK_TANK = "think tank"
    GOVERNMENT = "government"
    JOURNAL = "journal"
    UNKNOWN = "unknown"


class LengthBand(StrEnum):
    SHORT = "short"
    MULTI_PARAGRAPH = "multi-paragraph"


#: Hosts by registered domain. A host matches its entry or any subdomain of it.
_HOSTS: Final[Mapping[SourceType, frozenset[str]]] = {
    SourceType.GOVERNMENT: frozenset(
        """
            europa.eu un.org who.int imf.org worldbank.org oecd.org nato.int wto.org iaea.org
            ipcc.ch federalreserve.gov congress.gov
            """.split()  # noqa: SIM905 - a word list, kept readable
    ),
    SourceType.JOURNAL: frozenset(
        """
            doi.org jstor.org sciencedirect.com springer.com link.springer.com wiley.com
            tandfonline.com sagepub.com academic.oup.com cambridge.org muse.jhu.edu nature.com
            science.org pnas.org thelancet.com nejm.org bmj.com ncbi.nlm.nih.gov
            pubmed.ncbi.nlm.nih.gov ssrn.com papers.ssrn.com arxiv.org mdpi.com frontiersin.org
            plos.org journals.plos.org heinonline.org elsevier.com ieee.org ieeexplore.ieee.org
            annualreviews.org degruyter.com emerald.com cell.com
            """.split()  # noqa: SIM905 - a word list, kept readable
    ),
    SourceType.THINK_TANK: frozenset(
        """
            brookings.edu rand.org csis.org cfr.org heritage.org cato.org aei.org
            carnegieendowment.org urban.org newamerica.org cnas.org atlanticcouncil.org hoover.org
            piie.com stimson.org chathamhouse.org wilsoncenter.org belfercenter.org
            americanprogress.org thirdway.org manhattan-institute.org niskanencenter.org epi.org
            cbpp.org taxfoundation.org brookings.org csbaonline.org iiss.org rusi.org sipri.org
            crisisgroup.org wri.org rff.org itif.org bipartisanpolicy.org pewresearch.org
            mercatus.org lawfaremedia.org warontherocks.com fpri.org hudson.org migrationpolicy.org
            cgdev.org energypolicy.columbia.edu csis-website-prod.s3.amazonaws.com
            """.split()  # noqa: SIM905 - a word list, kept readable
    ),
    SourceType.NEWS: frozenset(
        """
            nytimes.com washingtonpost.com wsj.com reuters.com apnews.com bloomberg.com ft.com
            economist.com theguardian.com bbc.com bbc.co.uk cnn.com npr.org politico.com politico.eu
            axios.com thehill.com foreignpolicy.com foreignaffairs.com vox.com theatlantic.com
            forbes.com cnbc.com usatoday.com latimes.com nbcnews.com cbsnews.com abcnews.go.com
            foxnews.com aljazeera.com time.com newsweek.com businessinsider.com nikkei.com
            asia.nikkei.com scmp.com theverge.com wired.com propublica.org defensenews.com
            breakingdefense.com thediplomat.com nationalinterest.org newyorker.com nymag.com
            slate.com salon.com huffpost.com marketwatch.com barrons.com fortune.com yahoo.com
            news.yahoo.com japantimes.co.jp telegraph.co.uk independent.co.uk dw.com france24.com
            theconversation.com eenews.net statnews.com insidehighered.com chronicle.com edweek.org
            semafor.com newrepublic.com nationalreview.com reason.com
            """.split()  # noqa: SIM905 - a word list, kept readable
    ),
}

#: Government hosts by suffix: a country's government domain, or a US one.
_GOVERNMENT_SUFFIXES: Final = (
    ".gov",
    ".mil",
    ".gov.uk",
    ".gc.ca",
    ".gov.au",
    ".govt.nz",
    ".gov.in",
    ".go.jp",
    ".int",
)

#: Words in a cite that name a kind of publisher, checked in this order when the host says nothing.
#: News organisations' names come first because a newspaper may be called a *Journal*; government
#: before think tank because an agency's *Office* or *Center* is still an agency; the words a
#: newspaper's title is made of (*Times*, *News*, *Daily*) last, because an agency's briefing or an
#: institute's newsletter uses them too.
_CITE_WORDS: Final[tuple[tuple[SourceType, re.Pattern[str]], ...]] = (
    (
        SourceType.NEWS,
        re.compile(
            r"\b(New York Times|NYT|Washington Post|Wall Street Journal|WSJ|Reuters|Associated Press|"
            r"Bloomberg|Financial Times|The Economist|Guardian|BBC|CNN|NPR|Politico|Axios|The Hill|"
            r"Foreign Policy|Foreign Affairs|Vox|The Atlantic|Forbes|CNBC|USA Today|Los Angeles Times|"
            r"NBC News|CBS News|ABC News|Fox News|Al Jazeera|Newsweek|Business Insider|ProPublica|"
            r"Defense News|Breaking Defense|The Diplomat|National Interest|New Yorker|"
            r"The Conversation)\b"
        ),
    ),
    (
        SourceType.GOVERNMENT,
        re.compile(
            r"\b(Congressional Research Service|CRS|Government Accountability Office|GAO|"
            r"Congressional Budget Office|CBO|Department of|Dept\.? of|Ministry of|Secretary of|"
            r"Federal Reserve|Office of the|Bureau of|Agency|Senate|House of Representatives|"
            r"Committee on|White House|Parliament|Supreme Court|Inspector General|"
            r"Environmental Protection Agency|EPA|Pentagon|Commission)\b"
        ),
    ),
    (
        SourceType.THINK_TANK,
        re.compile(
            r"\b(Brookings|RAND|CSIS|Council on Foreign Relations|Heritage Foundation|Cato|"
            r"American Enterprise Institute|Carnegie|Atlantic Council|Hoover|Chatham House|"
            r"Wilson Center|Belfer|Center for American Progress|Institute|Foundation|"
            r"Center for|Centre for|Council|Think Tank)\b"
        ),
    ),
    (
        SourceType.JOURNAL,
        re.compile(
            r"(\bJournal\b|\bLaw Review\b|\bL\. ?Rev\.|\bReview of\b|\bQuarterly\b|\bAnnals of\b|"
            r"\bProceedings of\b|\bVol\.|\bVolume \d|\bIssue \d|\bpp\. ?\d|\bdoi\b)",
            re.IGNORECASE,
        ),
    ),
    (SourceType.NEWS, re.compile(r"\b(Times|Tribune|Herald|Gazette|Chronicle|News|Daily|Magazine|Weekly)\b")),
)

_URL: Final = re.compile(r"(?:https?://|www\.)[^\s\]\)>\"'”’]+", re.IGNORECASE)
_DOI: Final = re.compile(r"\b10\.\d{4,9}/[^\s\]\)>\"'”’]+")


def source_link(full_cite: str) -> str | None:
    """The cite's first link, or its DOI as a `https://doi.org/` link, or None."""
    match = _URL.search(full_cite)
    if match:
        link = match.group(0).rstrip(".,;:")
        return link if link.lower().startswith("http") else f"https://{link}"
    doi = _DOI.search(full_cite)
    return f"https://doi.org/{doi.group(0).rstrip('.,;:')}" if doi else None


def _host(link: str) -> str:
    return (urlsplit(link).hostname or "").lower().removeprefix("www.")


def _host_type(host: str) -> SourceType | None:
    if not host:
        return None
    for source_type, hosts in _HOSTS.items():
        if any(host == known or host.endswith(f".{known}") for known in hosts):
            return source_type
    if host.endswith(_GOVERNMENT_SUFFIXES):
        return SourceType.GOVERNMENT
    return None


def classify_source(full_cite: str) -> SourceType:
    """News, think tank, government or journal, from the cite's link and then its words."""
    link = source_link(full_cite)
    if link is not None:
        by_host = _host_type(_host(link))
        if by_host is not None:
            return by_host
    if _DOI.search(full_cite):
        return SourceType.JOURNAL
    for source_type, words in _CITE_WORDS:
        if words.search(full_cite):
            return source_type
    return SourceType.UNKNOWN


def has_omission_cut(evidence_text: str, markers: Sequence[str]) -> bool:
    """Whether the body holds one of the profile's ellipsis markers."""
    return any(marker in evidence_text for marker in markers)


def length_band(body_paragraphs: int) -> LengthBand:
    return LengthBand.SHORT if body_paragraphs <= 1 else LengthBand.MULTI_PARAGRAPH


#: A cutter's mark at the end of a cite: initials or a school code behind `//` or `\\`, in a bracket
#: or parentheses of capitals, or behind a dash after the cite's closing bracket. The `//` form may
#: not follow a colon, so a link's `https://` is never read as one, and takes no dot or digit, so a
#: host or a date never is either.
_CUTTER_MARKS: Final = (
    re.compile(r"\s*(?<!:)(?://|\\\\)\s*[A-Za-z]{1,5}(?:[\s/-]+[A-Za-z]{1,5}){0,2}\s*$"),
    re.compile(r"\s*\[\s*[A-Z]{1,5}(?:[\s/-][A-Z]{1,5}){0,2}\s*\]\s*$"),
    re.compile(r"\s*\(\s*[A-Z]{1,5}(?:[\s/-][A-Z]{1,5}){0,2}\s*\)\s*$"),
    re.compile(r"(?<=[\])])\s*[-–—]{1,2}\s*[A-Z]{1,5}(?:[\s/][A-Z]{1,5})?\s*$"),
)
#: Two to four capitals after a link or a bracket that closes the cite: `https://example.org/a JS`,
#: `[..., 2026] JS`.
_MARK_AFTER_A_LINK: Final = re.compile(r"(?<=\S)\s+[A-Z]{2,4}\s*$")

#: Capitals a cite ends with that are not anybody's initials: a file type, a country, a wire, an
#: agency or a publisher's own abbreviation.
NOT_CUTTER_MARKS: Final = frozenset(
    """
        PDF HTML DOI URL AP UPI AFP UN US USA EU UK NATO GAO CRS CBO EPA DOD DOE OECD IMF WHO CSIS
        RAND AEI CFR NBER NYT WSJ BBC CNN NPR CNBC FT ABC CBS NBC
        """.split()  # noqa: SIM905 - a word list, kept readable
)


def _is_a_mark(text: str) -> bool:
    words = re.findall(r"[A-Za-z]+", text)
    return bool(words) and not all(word.upper() in NOT_CUTTER_MARKS for word in words)


def strip_cutter_mark(cite: str) -> tuple[str, int]:
    """`cite` without a cutter's mark at its end, and how many marks were removed (0 or 1)."""
    for pattern in _CUTTER_MARKS:
        match = pattern.search(cite)
        if match and match.start() > 0 and _is_a_mark(match.group(0)):
            return cite[: match.start()], 1
    match = _MARK_AFTER_A_LINK.search(cite)
    if match and _is_a_mark(match.group(0)):
        before = cite[: match.start()].split()
        if before and (before[-1].endswith(("]", ")")) or _URL.fullmatch(before[-1].rstrip(".,;:"))):
            return cite[: match.start()], 1
    return cite, 0


# --------------------------------------------------------------------------------------------
# The denylist
# --------------------------------------------------------------------------------------------


class DenylistError(RuntimeError):
    """A denylist named with `--denylist` is missing, empty, inside the repository, or unreadable."""


#: What `import` and `check` use unless `--denylist` names a file (product owner's ruling,
#: 2026-11-14): no entries, so nothing is replaced, refused or reported for a name. The metadata,
#: comment and tracked-change scrub and the cutter-mark rule do not depend on it.
NO_DENYLIST: Final = scrub.ReplacementList(replacements=())


def _inside_repository(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    return True


def load_denylist(path: Path) -> scrub.ReplacementList:
    """Read the roster denylist: one entry per line, each replaced by `Redacted`.

    Never returns an empty list. A missing file, a file with no entries and a file inside the
    repository are errors, because a scrub against nothing passes everything.
    """
    if _inside_repository(path):
        raise DenylistError("the denylist names real students; it must live outside the repository")
    if not path.is_file():
        raise DenylistError(f"no denylist at {path}; create it first (one name or code per line)")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise DenylistError(f"the denylist at {path} cannot be read: {type(error).__name__}") from error
    entries = list(dict.fromkeys(" ".join(line.split()) for line in lines if line.strip()))
    if not entries:
        raise DenylistError(
            f"the denylist at {path} lists nothing; a scrub against nothing passes everything"
        )
    replacements = tuple(scrub.Replacement(find=entry, replace=REDACTED) for entry in entries)
    for replacement in replacements:
        if replacement.pattern.search(REDACTED):
            raise DenylistError(
                f"a denylist entry matches the word {REDACTED!r} itself; the scrub would never converge"
            )
    return scrub.ReplacementList(replacements=replacements, source_path=path)


# --------------------------------------------------------------------------------------------
# Listing candidates
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """One card the coach may pick. Holds team text and a path: it is written only outside the repo."""

    candidate_id: str
    event: str
    season: str
    source_type: SourceType
    length_band: LengthBand
    omission_cut: bool
    body_words: int
    path: str
    sha256: str
    first_element_index: int
    last_element_index: int
    tag: str
    full_cite: str
    opening_words: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self) | {"source_type": self.source_type.value, "length_band": self.length_band.value}

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Candidate:
        return cls(
            **{
                **data,
                "source_type": SourceType(data["source_type"]),
                "length_band": LengthBand(data["length_band"]),
            }
        )


@dataclass
class Listing:
    """What a walk of the season folders found. The counts are what reaches the terminal."""

    candidates: list[Candidate] = field(default_factory=list)
    files_read: int = 0
    skipped_files: Counter[str] = field(default_factory=Counter)
    cards_read: int = 0
    left_out: Counter[str] = field(default_factory=Counter)


LEFT_OUT_NOT_WHOLE: Final = "not a whole card (a disclosure's first and last words, or a cite alone)"
LEFT_OUT_NO_TAG: Final = "no tag"
LEFT_OUT_NO_CITE: Final = "no cite"
LEFT_OUT_SHORT_BODY: Final = f"a body under {MINIMUM_BODY_WORDS} words"
LEFT_OUT_NO_LINK: Final = "no link or DOI in the cite"
LEFT_OUT_UNCOPYABLE: Final = "holds a table, picture, text box or footnote the copier refuses"
SKIPPED_UNPARSABLE: Final = "the parser refuses the file"

#: The day the parser is told a team file was seen. A team file has no snapshot; nothing here reads it.
_UNDATED: Final = date(2000, 1, 1)


def _source_document(content: bytes, sha256: str) -> SourceDocument:
    # A team file is neither a caselist disclosure nor a camp release; the origin only feeds the
    # provenance of the parsed cards, which nothing here keeps, so it is read as a camp file's.
    return SourceDocument(
        sha256=sha256,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.OPENEV,
        caselist=None,
        first_seen_snapshot=_UNDATED,
        last_seen_snapshot=_UNDATED,
    )


def _parse(parser: DebateDocxParser, content: bytes) -> ParsedDocument | None:
    sha256 = hashlib.sha256(content).hexdigest()
    parsed = parser.parse(content, _source_document(content, sha256), source_path="team-file.docx")
    return parsed if isinstance(parsed, ParsedDocument) else None


def _units(document: ParsedDocument) -> Callable[[int], StructuralUnit]:
    by_index = {section.element_index: section.unit for section in document.sections}
    return lambda index: by_index.get(index, StructuralUnit.OTHER)


def _body_paragraph_count(document: ParsedDocument, card: ParsedCard) -> int:
    first, last = card.provenance.first_element_index, card.provenance.last_element_index
    return sum(
        1
        for section in document.sections
        if first <= section.element_index <= last
        and section.unit is StructuralUnit.EVIDENCE
        and section.text.strip()
    )


def _left_out_because(card: ParsedCard) -> str | None:
    if card.completeness is not CardCompleteness.FULL:
        return LEFT_OUT_NOT_WHOLE
    if card.tag is None:
        return LEFT_OUT_NO_TAG
    if not card.full_cite.strip():
        return LEFT_OUT_NO_CITE
    if len(card.evidence_text.split()) < MINIMUM_BODY_WORDS:
        return LEFT_OUT_SHORT_BODY
    if source_link(card.full_cite) is None:
        return LEFT_OUT_NO_LINK
    return None


def candidate_id(event: str, content: bytes, first_element_index: int, key: bytes) -> str:
    digest = keyed_digest(content + f"\0{first_element_index}".encode(), key)
    return f"{_EVENT_SLUGS[event]}-{digest[:CANDIDATE_DIGEST_LENGTH]}"


@dataclass(frozen=True)
class _FileToRead:
    path: Path
    season: str
    event: str
    content: bytes


@dataclass
class _FileRead:
    candidates: list[Candidate] = field(default_factory=list)
    cards_read: int = 0
    left_out: Counter[str] = field(default_factory=Counter)
    parsed: bool = True


_WORKER_PARSER: DebateDocxParser | None = None


def _read_one_file(item: _FileToRead, key: bytes) -> _FileRead:
    global _WORKER_PARSER  # noqa: PLW0603 - one parser per worker process
    if _WORKER_PARSER is None:
        _WORKER_PARSER = DebateDocxParser()
    parser = _WORKER_PARSER
    document = _parse(parser, item.content)
    result = _FileRead()
    if document is None:
        result.parsed = False
        return result
    markers = parser.profile.cite.wiki_ellipsis_markers
    units = _units(document)
    base_style_ids = load_base_template().style_ids
    opened = None
    sha256 = hashlib.sha256(item.content).hexdigest()
    for card in document.cards:
        result.cards_read += 1
        reason = _left_out_because(card)
        if reason is None:
            if opened is None:
                opened = open_source(item.content)
            copied = copy_card(
                opened,
                first_element_index=card.provenance.first_element_index,
                last_element_index=card.provenance.last_element_index,
                units=units,
                profile=parser.profile,
                base_style_ids=base_style_ids,
                hyperlinks=HyperlinkTargets(),
            )
            if isinstance(copied, UnsupportedCard):
                reason = LEFT_OUT_UNCOPYABLE
        if reason is not None:
            result.left_out[reason] += 1
            continue
        assert card.tag is not None
        words = card.evidence_text.split()
        result.candidates.append(
            Candidate(
                candidate_id=candidate_id(item.event, item.content, card.provenance.first_element_index, key),
                event=item.event,
                season=item.season,
                source_type=classify_source(card.full_cite),
                length_band=length_band(_body_paragraph_count(document, card)),
                omission_cut=has_omission_cut(card.evidence_text, markers),
                body_words=len(words),
                path=str(item.path),
                sha256=sha256,
                first_element_index=card.provenance.first_element_index,
                last_element_index=card.provenance.last_element_index,
                tag=card.tag,
                full_cite=card.full_cite,
                opening_words=" ".join(words[:OPENING_WORDS]),
            )
        )
    return result


def list_candidates(
    inputs: Sequence[Path], exclude_dirs: Iterable[str], key: bytes, *, workers: int = 1
) -> Listing:
    """Every candidate card below `inputs`, with counts of everything left out."""
    selection = select_files(inputs, exclude_dirs)
    listing = Listing(files_read=len(selection.files), skipped_files=Counter(selection.skipped))
    items = [_FileToRead(f.path, f.season, f.event, f.content) for f in selection.files]
    if workers <= 1:
        reads = [_read_one_file(item, key) for item in items]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            reads = list(pool.map(_read_one_file, items, [key] * len(items)))
    for read in reads:
        if not read.parsed:
            listing.skipped_files[SKIPPED_UNPARSABLE] += 1
            listing.files_read -= 1
            continue
        listing.cards_read += read.cards_read
        listing.left_out.update(read.left_out)
        listing.candidates.extend(read.candidates)
    listing.candidates.sort(key=lambda candidate: candidate.candidate_id)
    return listing


# --------------------------------------------------------------------------------------------
# The shortlist
# --------------------------------------------------------------------------------------------


def _event_shares(size: int) -> dict[str, int]:
    share, extra = divmod(size, len(EVENTS))
    return {event: share + (1 if position < extra else 0) for position, event in enumerate(EVENTS)}


_Bucket = tuple[SourceType, LengthBand]


def _pick_for_event(pool: Sequence[Candidate], share: int) -> list[Candidate]:
    """Round the event's source-type and length-band buckets, cuts alternating, new files first."""
    buckets: dict[_Bucket, list[Candidate]] = {
        (source_type, band): [c for c in pool if c.source_type is source_type and c.length_band is band]
        for source_type in SourceType
        for band in LengthBand
    }
    last_cut: dict[_Bucket, bool] = {}
    files_used: set[str] = set()
    picked: list[Candidate] = []
    for new_file_only in (True, False):
        progress = True
        while len(picked) < share and progress:
            progress = False
            for bucket, waiting in buckets.items():
                if len(picked) >= share:
                    break
                options = [c for c in waiting if not new_file_only or c.path not in files_used]
                if not options:
                    continue
                wanted_cut = not last_cut.get(bucket, False)
                pick = next((c for c in options if c.omission_cut is wanted_cut), options[0])
                waiting.remove(pick)
                last_cut[bucket] = pick.omission_cut
                files_used.add(pick.path)
                picked.append(pick)
                progress = True
    return picked


def choose_shortlist(candidates: Sequence[Candidate], size: int = DEFAULT_SHORTLIST_SIZE) -> list[Candidate]:
    """About a third per event, round every source type and length band, cuts alternating.

    Deterministic: the same candidates give the same shortlist, taken in candidate-ID order.
    """
    chosen: list[Candidate] = []
    for event, share in _event_shares(size).items():
        pool = sorted((c for c in candidates if c.event == event), key=lambda c: c.candidate_id)
        chosen.extend(_pick_for_event(pool, share))
    return chosen


def write_shortlist(directory: Path, shortlist: Sequence[Candidate]) -> None:
    """Write `shortlist.md` and `candidates.json` to `directory`, which must be outside the repo."""
    if _inside_repository(directory):
        raise SystemExit("the shortlist names files and carries team text; write it outside the repository")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / CANDIDATES_NAME).write_text(
        json.dumps([candidate.to_json() for candidate in shortlist], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (directory / SHORTLIST_NAME).write_text(_render_shortlist(shortlist), encoding="utf-8")


def _render_shortlist(shortlist: Sequence[Candidate]) -> str:
    lines = [
        "# Golden card shortlist",
        "",
        "Local to this machine: never commit, paste or send this file. It names the team's files.",
        "",
        "Pick 24 to 30 by ID, about a third per event, with every source type, short and",
        "multi-paragraph cards, and some cards with an omission cut. Pick only cards the coach cut",
        "or re-cut (never a debater's own cut, another program's card, the caselist's or a camp",
        "file's), whose source is still free to read with no paywall or login. Read each pick for",
        "names before importing it. Then run the import with the picked IDs: it asks about each one",
        "by ID, and only `yes` imports the card.",
        "",
    ]
    for event in EVENTS:
        picks = [c for c in shortlist if c.event == event]
        lines += [f"## {event} ({len(picks)})", ""]
        for c in picks:
            lines += [
                f"### {c.candidate_id}",
                "",
                f"- {c.season}, {c.source_type.value}, {c.length_band.value}, "
                f"{'omission cut' if c.omission_cut else 'no omission cut'}, {c.body_words} words",
                f"- Tag: {c.tag}",
                f"- Cite: {c.full_cite}",
                f"- Opens: {c.opening_words} ...",
                "",
            ]
    return "\n".join(lines)


def read_shortlist(directory: Path) -> list[Candidate]:
    data = json.loads((directory / CANDIDATES_NAME).read_text(encoding="utf-8"))
    return [Candidate.from_json(item) for item in data]


def _table(title: str, counts: Mapping[str, int]) -> list[str]:
    lines = [title]
    lines += [f"  {name}: {count}" for name, count in sorted(counts.items())] or ["  none"]
    return lines


def count_lines(listing: Listing, shortlist: Sequence[Candidate]) -> list[str]:
    """What `list` prints: counts only, safe to send to the PM."""

    def by(cards: Sequence[Candidate], key: Callable[[Candidate], str]) -> Counter[str]:
        return Counter(key(card) for card in cards)

    lines = [
        f"files read: {listing.files_read}",
        *_table("files skipped:", listing.skipped_files),
        f"cards read: {listing.cards_read}",
        *_table("cards left out, by first reason:", listing.left_out),
        f"candidates: {len(listing.candidates)}",
    ]
    for title, cards in (("candidates", listing.candidates), ("shortlist", shortlist)):
        lines += _table(f"{title} by event:", by(cards, lambda c: c.event))
        lines += _table(f"{title} by season:", by(cards, lambda c: c.season))
        lines += _table(f"{title} by source type:", by(cards, lambda c: c.source_type.value))
        lines += _table(f"{title} by length band:", by(cards, lambda c: c.length_band.value))
        lines += _table(
            f"{title} by omission cut:",
            by(cards, lambda c: "omission cut" if c.omission_cut else "no omission cut"),
        )
        lines += _table(
            f"{title} by event and source type:", by(cards, lambda c: f"{c.event}, {c.source_type.value}")
        )
    lines.append(f"shortlist: {len(shortlist)}")
    return lines


# --------------------------------------------------------------------------------------------
# The excerpt
# --------------------------------------------------------------------------------------------


def _parse_xml(data: bytes) -> etree._Element:
    return etree.fromstring(data, parser=hardened_xml_parser())


def _serialize(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _strip_trailing_text(paragraph: etree._Element, keep: int) -> None:
    """Cut a paragraph's text to its first `keep` characters, over however many runs it spans."""
    offset = 0
    for node in paragraph.iter(_w("t")):
        text = node.text or ""
        if offset >= keep:
            node.text = None
        elif offset + len(text) > keep:
            node.text = text[: keep - offset]
        offset += len(text)


def _paragraph_text(paragraph: etree._Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(_w("t")))


def _part_for_target(target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    parts: list[str] = ["word"]
    for segment in target.split("/"):
        if segment == "..":
            if parts:
                parts.pop()
        elif segment and segment != ".":
            parts.append(segment)
    return "/".join(parts)


def _references(paragraphs: Iterable[etree._Element]) -> set[str]:
    referenced: set[str] = set()
    for paragraph in paragraphs:
        for element in paragraph.iter():
            for name, value in element.attrib.items():
                if str(name).startswith(f"{{{R_NS}}}"):
                    referenced.add(str(value))
    return referenced


@dataclass(frozen=True)
class _Excerpt:
    content: bytes
    cutter_marks_removed: int
    parts_left_behind: int


def build_excerpt(content: bytes, card: ParsedCard, units: Callable[[int], StructuralUnit]) -> _Excerpt:
    """The source package cut down to `card`'s paragraphs, its cite's cutter mark removed.

    Not yet scrubbed: :func:`import_candidates` scrubs it. Keeps the source's own styles, numbering,
    theme and settings, so the card looks as the team cut it, and nothing else.
    """
    package = open_debate_docx(content)
    paragraphs = body_paragraphs(package.body)
    first, last = card.provenance.first_element_index, card.provenance.last_element_index
    kept = [paragraphs[index].element for index in range(first, last + 1)]
    copies = [etree.fromstring(etree.tostring(paragraph)) for paragraph in kept]

    cutter_marks = 0
    cite_positions = [
        position
        for position, index in enumerate(range(first, last + 1))
        if units(index) is StructuralUnit.CITE
    ]
    if cite_positions:
        cite = copies[cite_positions[-1]]
        stripped, cutter_marks = strip_cutter_mark(_paragraph_text(cite))
        if cutter_marks:
            _strip_trailing_text(cite, len(stripped))

    with zipfile.ZipFile(BytesIO(content)) as archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        parts = {name: archive.read(name) for name in names}

    source_root = package.body.getparent()
    assert source_root is not None
    # The source's own root, namespaces and all, with nothing in its body but the card.
    document = etree.fromstring(etree.tostring(source_root), parser=hardened_xml_parser())
    body = document.find(_w("body"))
    assert body is not None
    for child in list(body):
        body.remove(child)
    for copied in copies:
        body.append(copied)
    section = package.body.find(_w("sectPr"))
    if section is not None:
        section = etree.fromstring(etree.tostring(section))
        for child in list(section):
            if etree.QName(child).localname in _DROPPED_SECTION_REFERENCES:
                section.remove(child)
        body.append(section)

    document_part = package.document_part
    rels_name = f"{document_part.rpartition('/')[0]}/_rels/{document_part.rpartition('/')[2]}.rels"
    referenced = _references(copies)
    kept_parts: dict[str, bytes] = {}
    rels_root = (
        _parse_xml(parts[rels_name]) if rels_name in parts else etree.Element(f"{{{RELS_NS}}}Relationships")
    )
    for relationship in list(rels_root):
        relationship_type = relationship.get("Type") or ""
        target = relationship.get("Target") or ""
        kind = relationship_type.rsplit("/", 1)[-1]
        if relationship.get("TargetMode") == "External":
            if relationship_type.endswith(_HYPERLINK_REL_SUFFIX) and relationship.get("Id") in referenced:
                continue
        elif kind in _KEPT_DOCUMENT_RELATIONSHIPS and _part_for_target(target) in parts:
            kept_parts[_part_for_target(target)] = parts[_part_for_target(target)]
            continue
        rels_root.remove(relationship)

    for name in list(kept_parts):
        if name.endswith("settings.xml"):
            settings = _parse_xml(kept_parts[name])
            for child in list(settings):
                if isinstance(child.tag, str) and etree.QName(child).localname in _DROPPED_SETTINGS:
                    settings.remove(child)
            kept_parts[name] = _serialize(settings)

    core = parts.get("docProps/core.xml")
    package_relationships = [(_OFFICE_DOCUMENT_REL, document_part)]
    if core is not None:
        package_relationships.append((_CORE_PROPERTIES_REL, "docProps/core.xml"))
    package_rels = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{RELS_NS}">'
        + "".join(
            f'<Relationship Id="rId{number}" Type={quoteattr(kind)} Target={quoteattr(target)}/>'
            for number, (kind, target) in enumerate(package_relationships, start=1)
        )
        + "</Relationships>"
    ).encode()

    written: dict[str, bytes] = {
        document_part: _serialize(document),
        rels_name: _serialize(rels_root),
        "_rels/.rels": package_rels,
        **kept_parts,
    }
    if core is not None:
        written["docProps/core.xml"] = core

    content_types = _parse_xml(parts["[Content_Types].xml"])
    for override in list(content_types.findall(f"{{{CONTENT_TYPES_NS}}}Override")):
        if (override.get("PartName") or "").lstrip("/") not in written:
            content_types.remove(override)
    ordered = [("[Content_Types].xml", _serialize(content_types))] + sorted(written.items())
    return _Excerpt(
        content=write_package(ordered),
        cutter_marks_removed=cutter_marks,
        parts_left_behind=len(
            [name for name in parts if name not in written and name != "[Content_Types].xml"]
        ),
    )


# --------------------------------------------------------------------------------------------
# Importing the coach's picks
# --------------------------------------------------------------------------------------------


class ImportRefused(Exception):
    """One pick could not be imported. The reason is a code and a sentence, never the card's text."""

    def __init__(self, candidate_id: str, reason: str) -> None:
        super().__init__(f"{candidate_id}: {reason}")
        self.candidate_id = candidate_id
        self.reason = reason


REFUSED_UNKNOWN_ID: Final = "not in the shortlist"
REFUSED_FILE_GONE: Final = "the file is no longer where the listing found it"
REFUSED_FILE_CHANGED: Final = "the file changed since the listing; list again"
REFUSED_CARD_GONE: Final = "the parser no longer reads the card there"
REFUSED_DENYLIST_IN_BODY: Final = "a denylist entry appears in the card's body; pick another card"
REFUSED_SCRUB_FAILED: Final = "the scrub could not remove every denylist entry"
REFUSED_REREAD_DIFFERS: Final = "the excerpt does not re-read as the card (body or spans differ)"
REFUSED_ALREADY_IMPORTED: Final = "already imported"
REFUSED_NOT_ATTESTED: Final = (
    "the coach did not confirm cutting or re-cutting this card and reviewing it for names "
    "(answer yes at the question, in a terminal)"
)

ATTESTATION_QUESTION: Final = (
    "{candidate_id}: did the coach cut or re-cut this card, and review it for names? Type yes to import it: "
)


def terminal_attestation(stdin: TextIO, stdout: TextIO) -> Callable[[str], bool]:
    """Ask the coach about each pick, by ID only. Only `yes` attests; no terminal attests nothing."""

    def ask(candidate_id: str) -> bool:
        if not stdin.isatty():
            return False
        stdout.write(ATTESTATION_QUESTION.format(candidate_id=candidate_id))
        stdout.flush()
        return stdin.readline().strip().lower() == "yes"

    return ask


@dataclass(frozen=True)
class ImportedCase:
    """What one import removed, in counts. Safe to print and to send."""

    case_id: str
    candidate_id: str
    parts_left_behind: int
    properties_blanked: int
    tracked_change_authors_redacted: int
    identity_attributes_dropped: int
    comment_markup_removed: int
    cutter_marks_removed: int
    denylist_replacements: int

    def summary(self) -> str:
        return (
            f"{self.case_id} ({self.candidate_id}): parts left behind {self.parts_left_behind}, "
            f"properties blanked {self.properties_blanked}, tracked-change authors redacted "
            f"{self.tracked_change_authors_redacted}, identity attributes dropped "
            f"{self.identity_attributes_dropped}, comment markup removed {self.comment_markup_removed}, "
            f"cutter marks removed {self.cutter_marks_removed}, "
            f"denylist replacements {self.denylist_replacements}"
        )


def _existing_cases(fixtures_dir: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(fixtures_dir.glob(f"*/{CASE_NAME}"))
    ]


def _next_case_id(event: str, taken: set[str]) -> str:
    number = 1
    while f"{_EVENT_SLUGS[event]}-{number:03d}" in taken:
        number += 1
    return f"{_EVENT_SLUGS[event]}-{number:03d}"


def _spans(card: ParsedCard) -> list[tuple[str, int, int, str | None]]:
    return [
        (span.emphasis.value, span.start_offset, span.end_offset, span.highlight_color)
        for span in card.formatting_spans
    ]


def _import_one(
    candidate: Candidate,
    denylist: scrub.ReplacementList,
    parser: DebateDocxParser,
    case_id: str,
    fixtures_dir: Path,
    today: date,
) -> ImportedCase:
    path = Path(candidate.path)
    if not path.is_file():
        raise ImportRefused(candidate.candidate_id, REFUSED_FILE_GONE)
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != candidate.sha256:
        raise ImportRefused(candidate.candidate_id, REFUSED_FILE_CHANGED)
    document = _parse(parser, content)
    card = None
    if document is not None:
        card = next(
            (
                c
                for c in document.cards
                if c.provenance.first_element_index == candidate.first_element_index
                and c.provenance.last_element_index == candidate.last_element_index
            ),
            None,
        )
    if document is None or card is None or card.tag is None:
        raise ImportRefused(candidate.candidate_id, REFUSED_CARD_GONE)
    if denylist.survivors(card.evidence_text):
        raise ImportRefused(candidate.candidate_id, REFUSED_DENYLIST_IN_BODY)

    excerpt = build_excerpt(content, card, _units(document))
    with tempfile.TemporaryDirectory() as scratch:
        unscrubbed = Path(scratch) / "unscrubbed.docx"
        scrubbed = Path(scratch) / "scrubbed.docx"
        unscrubbed.write_bytes(excerpt.content)
        try:
            result = scrub.scrub_package(unscrubbed, scrubbed, denylist)
        except scrub.ScrubError as error:
            raise ImportRefused(candidate.candidate_id, REFUSED_SCRUB_FAILED) from error
        with zipfile.ZipFile(scrubbed) as archive:
            scrubbed_parts = [(info.filename, archive.read(info.filename)) for info in archive.infolist()]
    final = write_package(scrubbed_parts)

    reread = _parse(parser, final)
    if reread is None or len(reread.cards) != 1:
        raise ImportRefused(candidate.candidate_id, REFUSED_REREAD_DIFFERS)
    (only,) = reread.cards
    if only.evidence_text != card.evidence_text or _spans(only) != _spans(card):
        raise ImportRefused(candidate.candidate_id, REFUSED_REREAD_DIFFERS)

    case_dir = fixtures_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=False)
    (case_dir / EXCERPT_NAME).write_bytes(final)
    link = source_link(card.full_cite)
    case = {
        "case_id": case_id,
        "candidate_id": candidate.candidate_id,
        "event": candidate.event,
        "season": candidate.season,
        "source_type": candidate.source_type.value,
        "length_band": candidate.length_band.value,
        "omission_cut": candidate.omission_cut,
        "coach_cut_and_reviewed_for_names": True,
        "research_need": denylist.apply(card.tag),
        "source_link": denylist.apply(link) if link else None,
        "parser_version": parser.parser_version,
        "imported_on": today.isoformat(),
    }
    (case_dir / CASE_NAME).write_text(json.dumps(case, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return ImportedCase(
        case_id=case_id,
        candidate_id=candidate.candidate_id,
        parts_left_behind=excerpt.parts_left_behind + len(result.dropped_parts),
        properties_blanked=len(result.blanked_properties),
        tracked_change_authors_redacted=result.redacted_author_attributes,
        identity_attributes_dropped=result.dropped_identity_attributes,
        comment_markup_removed=result.removed_comment_elements,
        cutter_marks_removed=excerpt.cutter_marks_removed,
        denylist_replacements=result.replaced_occurrences,
    )


def import_candidates(
    shortlist: Sequence[Candidate],
    ids: Sequence[str],
    denylist: scrub.ReplacementList,
    fixtures_dir: Path,
    *,
    today: date,
    attest: Callable[[str], bool],
) -> tuple[list[ImportedCase], list[ImportRefused]]:
    """Import each picked ID the coach attests; return what was imported and what was refused.

    `attest` is asked about each known, not yet imported ID before its file is read: the coach
    confirms cutting or re-cutting the card and reviewing it for names (the product owner's
    ruling, 2026-11-14). A pick without it is refused. `denylist` is :data:`NO_DENYLIST` unless
    the operator named one.
    """
    by_id = {candidate.candidate_id: candidate for candidate in shortlist}
    existing = _existing_cases(fixtures_dir)
    taken = {case["case_id"] for case in existing}
    imported_ids = {case["candidate_id"] for case in existing}
    parser = DebateDocxParser()
    imported: list[ImportedCase] = []
    refused: list[ImportRefused] = []
    for pick in dict.fromkeys(ids):
        candidate = by_id.get(pick)
        try:
            if candidate is None:
                raise ImportRefused(pick, REFUSED_UNKNOWN_ID)
            if pick in imported_ids:
                raise ImportRefused(pick, REFUSED_ALREADY_IMPORTED)
            if not attest(pick):
                raise ImportRefused(pick, REFUSED_NOT_ATTESTED)
            case_id = _next_case_id(candidate.event, taken)
            imported.append(_import_one(candidate, denylist, parser, case_id, fixtures_dir, today))
            taken.add(case_id)
            imported_ids.add(pick)
        except ImportRefused as refusal:
            refused.append(refusal)
    write_index(fixtures_dir)
    return imported, refused


# --------------------------------------------------------------------------------------------
# INDEX.md
# --------------------------------------------------------------------------------------------

_INDEX_HEADER: Final = """# Golden card corpus

The cases E09's tests and evaluations are measured on (`v1-e09-t01-golden-card-fixtures`). Each
folder holds one card the coach cut or re-cut and reviewed for names: `team-card.docx`, the card's
own paragraphs copied out of the team file and scrubbed (document metadata, comments,
tracked-change authors and cutter marks), and `case.json`, what the table below says about it.
Later steps add the source snapshot's digests and the card's offsets to `case.json` (the snapshot
itself stays outside the repository), `expected.json` and the expected render. What the corpus
keeps, and what it never does, is in `README.md`.

Written by `scripts/import_golden_card.py`, which rewrites this file after every import; do not
edit it by hand. The research need is the card's tag, which says what the card is for.

| Case | Event | Season | Source type | Length | Omission cut | Research need |
|---|---|---|---|---|---|---|
"""


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def render_index(fixtures_dir: Path) -> str:
    rows = [
        f"| `{case['case_id']}` | {case['event']} | {case['season']} | {case['source_type']} | "
        f"{case['length_band']} | {'yes' if case['omission_cut'] else 'no'} | "
        f"{_cell(case['research_need'])} |"
        for case in sorted(_existing_cases(fixtures_dir), key=lambda case: case["case_id"])
    ]
    return _INDEX_HEADER + "".join(f"{row}\n" for row in rows) + f"\n{len(rows)} cases.\n"


def write_index(fixtures_dir: Path) -> None:
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    (fixtures_dir / INDEX_NAME).write_text(render_index(fixtures_dir), encoding="utf-8")


# --------------------------------------------------------------------------------------------
# Checking the fixtures
# --------------------------------------------------------------------------------------------


def metadata_problems(package: bytes) -> list[str]:
    """What in `package` still names a person: never the value, only where it is."""
    problems: list[str] = []
    with zipfile.ZipFile(BytesIO(package)) as archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        for name in names:
            if name in scrub.DROPPED_PARTS or name.startswith(scrub.DROPPED_PART_PREFIXES):
                problems.append(f"{name} is present")
        if "docProps/core.xml" in names:
            core = _parse_xml(archive.read("docProps/core.xml"))
            for namespace, tag in ((DC_NS, "creator"), (CORE_NS, "lastModifiedBy")):
                for element in core.iter(f"{{{namespace}}}{tag}"):
                    if (element.text or "").strip():
                        problems.append(f"docProps/core.xml {tag} is set")
        if "docProps/app.xml" in names:
            app = _parse_xml(archive.read("docProps/app.xml"))
            for tag in ("Company", "Manager"):
                for element in app.iter(f"{{{EXTENDED_NS}}}{tag}"):
                    if (element.text or "").strip():
                        problems.append(f"docProps/app.xml {tag} is set")
        for name in names:
            if not name.endswith((".xml", ".rels")):
                continue
            root = _parse_xml(archive.read(name))
            for element in root.iter():
                if not isinstance(element.tag, str):
                    continue
                for attribute, value in element.attrib.items():
                    local = etree.QName(attribute).localname
                    if local in scrub.AUTHOR_ATTRIBUTE_NAMES and value != scrub.REDACTED_AUTHOR:
                        problems.append(f"{name} carries an author name")
                    elif local == "initials":
                        problems.append(f"{name} carries initials")
    return sorted(set(problems))


@dataclass
class CheckReport:
    """What `check` found. Paths are relative to the fixtures folder; no matched text is kept."""

    docx_checked: int = 0
    text_files_checked: int = 0
    metadata_problems: list[tuple[str, str]] = field(default_factory=list)
    denylist_hits: list[tuple[str, int]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.metadata_problems and not self.denylist_hits


_TAGS: Final = re.compile(r"<[^>]*>")


def _denylist_hits_in_package(package: bytes, denylist: scrub.ReplacementList) -> int:
    """Denylist entries found in any part: its name, its bytes as text, and its text without tags."""
    found: set[tuple[str, str]] = set()
    with zipfile.ZipFile(BytesIO(package)) as archive:
        for info in archive.infolist():
            raw = archive.read(info.filename).decode("utf-8", errors="ignore")
            readable = " ".join(_TAGS.sub(" ", raw).split())
            for text in (info.filename, raw, readable):
                found.update((info.filename, entry) for entry in denylist.survivors(text))
    return len(found)


def check_fixtures(fixtures_dir: Path, denylist: scrub.ReplacementList) -> CheckReport:
    report = CheckReport()
    for path in sorted(p for p in fixtures_dir.rglob("*") if p.is_file()):
        relative = path.relative_to(fixtures_dir).as_posix()
        hits = len(denylist.survivors(relative))
        if path.suffix == ".docx":
            report.docx_checked += 1
            content = path.read_bytes()
            report.metadata_problems += [(relative, problem) for problem in metadata_problems(content)]
            hits += _denylist_hits_in_package(content, denylist)
        else:
            report.text_files_checked += 1
            text = path.read_bytes().decode("utf-8", errors="ignore")
            hits += len(denylist.survivors(text))
        if hits:
            report.denylist_hits.append((relative, hits))
    return report


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="import_golden_card.py", description=(__doc__ or "").split("\n\n")[0]
    )
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", help="write a balanced shortlist outside the repo; print counts")
    listing.add_argument("inputs", nargs="+", type=Path, help="season folders to read")
    listing.add_argument(
        "--output", type=Path, required=True, help="folder outside the repo for the shortlist"
    )
    listing.add_argument("--exclude-dir", action="append", default=None, help="folder name to leave out")
    listing.add_argument("--size", type=int, default=DEFAULT_SHORTLIST_SIZE, help="shortlist size")
    listing.add_argument("--workers", type=int, default=os.cpu_count() or 1, help="parsing processes")

    importing = commands.add_parser("import", help="copy picked cards into the fixtures, scrubbed")
    importing.add_argument("--shortlist", type=Path, required=True, help="the folder `list` wrote")
    importing.add_argument("--ids", nargs="+", required=True, help="candidate IDs, space- or comma-separated")
    importing.add_argument("--denylist", type=Path, default=None, help="an optional denylist; off by default")
    importing.add_argument("--fixtures", type=Path, default=FIXTURES_DIR, help=argparse.SUPPRESS)

    checking = commands.add_parser("check", help="no fixture carries metadata (or a denylist entry)")
    checking.add_argument("--denylist", type=Path, default=None, help="an optional denylist; off by default")
    checking.add_argument("--fixtures", type=Path, default=FIXTURES_DIR, help=argparse.SUPPRESS)

    indexing = commands.add_parser("index", help="rewrite INDEX.md from the cases")
    indexing.add_argument("--fixtures", type=Path, default=FIXTURES_DIR, help=argparse.SUPPRESS)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    today: date | None = None,
    attest: Callable[[str], bool] | None = None,
) -> int:
    arguments = _build_parser().parse_args(argv)
    if arguments.command == "list":
        if _inside_repository(arguments.output):
            print(
                "the shortlist names files and carries team text; write it outside the repository",
                file=sys.stderr,
            )
            return 2
        excluded = (
            arguments.exclude_dir if arguments.exclude_dir is not None else list(DEFAULT_EXCLUDED_FOLDERS)
        )
        try:
            key = require_key()
        except MissingDigestKeyError as error:
            print(f"import_golden_card: {error}", file=sys.stderr)
            return 2
        listing = list_candidates(arguments.inputs, excluded, key, workers=arguments.workers)
        shortlist = choose_shortlist(listing.candidates, arguments.size)
        write_shortlist(arguments.output, shortlist)
        for line in count_lines(listing, shortlist):
            print(line)
        return 0
    if arguments.command == "index":
        write_index(arguments.fixtures)
        print(f"{INDEX_NAME}: {len(_existing_cases(arguments.fixtures))} cases")
        return 0
    try:
        denylist = NO_DENYLIST if arguments.denylist is None else load_denylist(arguments.denylist)
    except DenylistError as error:
        print(f"import_golden_card: {error}", file=sys.stderr)
        return 2
    if arguments.command == "import":
        ids = [part for value in arguments.ids for part in value.replace(",", " ").split()]
        imported, refused = import_candidates(
            read_shortlist(arguments.shortlist),
            ids,
            denylist,
            arguments.fixtures,
            today=today or date.today(),
            attest=attest or terminal_attestation(sys.stdin, sys.stdout),
        )
        for case in imported:
            print(case.summary())
        for refusal in refused:
            print(f"refused {refusal.candidate_id}: {refusal.reason}")
        print(f"imported {len(imported)}, refused {len(refused)}")
        return 0 if not refused else 1
    report = check_fixtures(arguments.fixtures, denylist)
    print(f"docx checked: {report.docx_checked}, other files checked: {report.text_files_checked}")
    for relative, problem in report.metadata_problems:
        print(f"metadata: {relative}: {problem}")
    for relative, hits in report.denylist_hits:
        print(f"denylist: {relative}: {hits} entr{'y' if hits == 1 else 'ies'} found")
    print(
        "denylist: off" if arguments.denylist is None else f"denylist: {len(denylist.replacements)} entries"
    )
    print("clean" if report.clean else "NOT CLEAN")
    return 0 if report.clean else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

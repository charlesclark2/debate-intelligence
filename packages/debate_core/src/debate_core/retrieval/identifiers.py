"""DOI, arXiv and PMID detection in URLs and text (v1-e04-t01 ac4).

ArticleService (v1-e04-t05) dedupes by DOI as well as by canonical URL (architecture §9), and
CitationService (E06) looks metadata up by identifier. `detect_identifiers` finds the identifiers a
URL or a passage of text states, normalizes them, and resolves nothing: a DOI is never looked up,
and nothing is fetched.

**DOI** (`10.NNNN/suffix`). Found anywhere, in a doi.org or dx.doi.org URL, a publisher's path or
query (`?id=10.1371%2Fjournal.pone.0230000`) or running text. A percent-encoded DOI is decoded,
`%2F` slash included. Normalized to lower case, as DOIs are case-insensitive and
`ArticleIdentifiers` stores them. A DOI ends at whitespace, a quote, `<`, `>`, or a URL's `?`,
`#` or `&`. Running-text punctuation is then trimmed from its end: `.,;:!?'"*`, and a closing
`)`, `]` or `}` only when the DOI does not open one itself, so `10.1016/S0140-6736(20)30183-5).`
keeps its own parenthesis and loses the sentence's. Publisher viewer suffixes (`/full`,
`/abstract`, `/epdf`, `/pdf`, `/fulltext`, `.pdf`) are trimmed too. Two known limits: a DOI with a
raw `<`, `>` or `&` (some old SICI DOIs) is cut short, and a DOI written with no punctuation or
space before the next word cannot be told from one that continues.

**arXiv**. New style `YYMM.NNNN` or `YYMM.NNNNN`, old style `archive/YYMMNNN`, in an arxiv.org URL
(`/abs/`, `/pdf/`, `/html/`, `/format/`, any arxiv.org host) or after an `arXiv:` label in any case.
A bare `2101.01234` in text is not taken, as nothing marks it as arXiv. The version suffix is
dropped (`2101.01234v3` → `2101.01234`), and so is an old-style subject class, which is not part
of the identifier (`math.GT/0309136` → `math/0309136`). An arXiv DOI (`10.48550/arXiv.2101.01234`)
yields its arXiv id as well.

**PMID**. In a PubMed URL (`pubmed.ncbi.nlm.nih.gov/N`, `ncbi.nlm.nih.gov/pubmed/N`), a Europe PMC
`MED` URL, or after a `PMID` label (`PMID: N`, `PMID N`, `pmid:N`). A PMCID (`PMC7092803`) is a
different identifier and is not taken. Normalized to digits with no leading zeros.

Each kind is returned in order of first appearance, once each. Which of several is the article's
own is the caller's decision: `as_article_identifiers` takes the first of each, which is right
for the article's URL and its own metadata and not for a reference list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote

from debate_core.domain.article import ArticleIdentifiers

__all__ = ["ScholarlyIdentifiers", "detect_identifiers"]


@dataclass(frozen=True, slots=True)
class ScholarlyIdentifiers:
    """The identifiers found in one URL or text, normalized, each kind in order of appearance."""

    dois: tuple[str, ...] = ()
    arxiv_ids: tuple[str, ...] = ()
    pmids: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.dois or self.arxiv_ids or self.pmids)

    def as_article_identifiers(self) -> ArticleIdentifiers:
        """The first identifier of each kind, as the domain model stores them."""
        return ArticleIdentifiers(
            doi=self.dois[0] if self.dois else None,
            arxiv_id=self.arxiv_ids[0] if self.arxiv_ids else None,
            pmid=self.pmids[0] if self.pmids else None,
        )


# ---------------------------------------------------------------------------------------------
# DOI
# ---------------------------------------------------------------------------------------------

_DOI = re.compile(r"(?<![0-9.])10\.\d{4,9}(?:/|%2[Ff])[^\s\"<>?#&]+")
_DOI_SHAPE = re.compile(r"10\.\d{4,9}/\S+")
_TRAILING_PUNCTUATION = frozenset(".,;:!?'\"*")
_CLOSING_TO_OPENING = {")": "(", "]": "[", "}": "{"}
_VIEWER_SUFFIXES = ("/full", "/abstract", "/epdf", "/pdf", "/fulltext", ".pdf")
_ARXIV_DOI_PREFIX = "10.48550/arxiv."


def _trim_doi(candidate: str) -> str:
    while candidate:
        last = candidate[-1]
        opening = _CLOSING_TO_OPENING.get(last)
        if last in _TRAILING_PUNCTUATION or (
            opening is not None and candidate.count(opening) < candidate.count(last)
        ):
            candidate = candidate[:-1]
            continue
        lowered = candidate.lower()
        suffix = next((suffix for suffix in _VIEWER_SUFFIXES if lowered.endswith(suffix)), None)
        if suffix is None:
            return candidate
        candidate = candidate[: -len(suffix)]
    return candidate


def _dois(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for match in _DOI.finditer(text):
        doi = _trim_doi(unquote(match.group())).lower()
        if _DOI_SHAPE.fullmatch(doi):
            found.append((match.start(), doi))
    return found


# ---------------------------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------------------------

_MONTH = r"(?:0[1-9]|1[0-2])"
_ARXIV_NEW = rf"(?P<new>\d\d{_MONTH}\.\d{{4,5}})"
_ARXIV_OLD = rf"(?P<archive>[a-z]+(?:-[a-z]+)?)(?:\.[a-z]{{2}})?/(?P<number>\d\d{_MONTH}\d{{3}})"
_ARXIV = re.compile(
    rf"(?:arxiv\.org/(?:abs|pdf|html|format)/|arxiv:\s*)(?:{_ARXIV_NEW}|{_ARXIV_OLD})(?:v\d+)?(?!\d)",
    re.IGNORECASE,
)
_ARXIV_ID_IN_DOI = re.compile(rf"{_ARXIV_NEW}(?:v\d+)?")


def _arxiv_ids(text: str, dois: list[tuple[int, str]]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for match in _ARXIV.finditer(text):
        if match["new"]:
            found.append((match.start(), match["new"]))
        else:
            found.append((match.start(), f"{match['archive'].lower()}/{match['number']}"))
    for position, doi in dois:
        in_doi = _ARXIV_ID_IN_DOI.fullmatch(doi.removeprefix(_ARXIV_DOI_PREFIX))
        if doi.startswith(_ARXIV_DOI_PREFIX) and in_doi:
            found.append((position, in_doi["new"]))
    return found


# ---------------------------------------------------------------------------------------------
# PMID
# ---------------------------------------------------------------------------------------------

_PMID = re.compile(
    r"(?:pubmed\.ncbi\.nlm\.nih\.gov/|ncbi\.nlm\.nih\.gov/pubmed/|europepmc\.org/(?:abstract|article)/med/"
    r"|pmid\s*:?\s*)(?P<pmid>\d{1,9})(?!\d)",
    re.IGNORECASE,
)


def _pmids(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for match in _PMID.finditer(text):
        pmid = int(match["pmid"])
        if pmid > 0:
            found.append((match.start(), str(pmid)))
    return found


def _in_order_once(found: list[tuple[int, str]]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for _, value in sorted(found)))


def detect_identifiers(text: str) -> ScholarlyIdentifiers:
    """Every DOI, arXiv id and PMID that a URL or passage of text states, normalized."""
    dois = _dois(text)
    return ScholarlyIdentifiers(
        dois=_in_order_once(dois),
        arxiv_ids=_in_order_once(_arxiv_ids(text, dois)),
        pmids=_in_order_once(_pmids(text)),
    )

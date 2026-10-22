"""Federated deduplication: one entry per source, whichever providers found it (v1-e08-t02).

The normalize stage of a federated search (:class:`DedupeStage`) collapses the `candidates` every
provider returned into `merged_candidates`, one :class:`MergedCandidate` per distinct source. It
fetches nothing and resolves nothing: every decision is made from what the providers already said.

## Matching

Records are grouped with a union-find, by four rules tried in order of confidence. Each rule links a
record to every earlier record it matches, and :attr:`MergedCandidate.matched_on` says which rules
joined a group.

1. **DOI** — the same DOI, as :class:`~debate_core.domain.article.ArticleIdentifiers` normalizes it
   (bare, lower case, whatever spelling the provider used).
2. **Canonical URL** — the same :func:`~debate_core.retrieval.canonicalize_url` of the provider's
   canonical URL, or of its URL when it gave none: tracking parameters, AMP variants, link wrappers,
   host case, default ports and fragments make no difference. The canonical URL is an identity key
   here and never a fetch target. A site's front page (path `/`, no query) is not a key: a feed that
   links every item to its home page names the site, not the story.
3. **Provider ids** — the same arXiv id (version suffix and `arXiv:` prefix ignored, and read from an
   arXiv DOI), PMID (leading zeros ignored), OpenAlex work id (as a URL or bare, any case) or
   Semantic Scholar paper id (any case).
4. **Title** — normalized titles that agree (:func:`titles_agree`), gated by the first author's surname
   (:func:`surname_key`) and the publication date. Both records must name a first author and a date:
   a title alone never merges two records. For two scholarly records the year must agree. Otherwise
   (news, government, think tank, other, or one scholarly and one not) the UTC day must agree and both
   URLs must be on the same site (registrable domain), because the same headline on two outlets is two
   sources: a card cites the outlet it was read at, and each outlet's page is reached, and may be
   paywalled, on its own.

**Identifiers that disagree win over every rule.** Two groups are never joined while they hold
different values of one identifier: DOI, arXiv id, PMID, OpenAlex id or Semantic Scholar id. A shared
URL, a shared provider id or matching titles do not overrule two different DOIs. A missing identifier
is not a different one.

**A preprint and its published version stay apart** whenever the records tell them apart. They are
different versions: text, pagination and peer-review status differ, and a card cites the version it
was read from, so merging them would let one version's metadata (its venue, its date, its
peer-reviewed status for ranking) stand for the other. For the identifier rule, a record with an arXiv
id and no DOI carries its arXiv DOI (`10.48550/arxiv.<id>`), which every arXiv paper has. So an arXiv
preprint never joins a record carrying a journal DOI, even when that record lists the preprint's arXiv
id as a cross-link, as Semantic Scholar's published records do. Preprint servers that mint their own
DOIs (bioRxiv, medRxiv, SSRN) differ from the journal by DOI already. When one record has no
identifier at all the versions cannot be told apart, and the title rule may join them.

Identifiers are never read out of URLs: a news story's URL can carry the DOI of the study it reports,
and that would merge the story with the study.

## Titles

:func:`title_tokens` absorbs the ways providers write one title: case, accents, HTML entities and JATS
markup (`<i>`, `<sub>`), punctuation, `&` for "and", hyphens and apostrophes inside words
(`Co-operation`, `China's`), abbreviations' full stops (`U.S.`), and British spellings, which a fixed
table rewrites to American ones. Two titles agree when their tokens are the same words in the same
order, at least :data:`MIN_TITLE_TOKENS` of them, or when one title is the other's main title with its
subtitle dropped (the part before `: `, ` - `, ` – `, ` — ` or ` | `), which is how one provider
shortens what another keeps whole. Two titles that both have subtitles must agree in full.

There is no similarity threshold. A token-set ratio scores any title 1.0 against a longer title that
contains all its words ("The case for a carbon tax" against "... in Canada"), and a character ratio
passes a one-word difference in a long title or a near-spelling of another word ("immigration" and
"emigration" score 0.857). Every difference the labelled pairs show between two providers' copies of
one title is one of the normalizations above, so the rule is equality after them.

## Merging

:func:`merge_group` builds a group's :class:`MergedCandidate` from its members by
:data:`FIELD_PRECEDENCE`, one row per merged field naming the providers in the order they are
trusted for it. A field takes the value of the first member, in that order, that has one; members
from a provider outside the table come after every provider in it; between two members from one
provider the earlier wins. Empty values (`None`, no authors, a blank snippet, source type `other`)
give way to the next member. `canonical_url` is not in the table: it is the canonical form of the
merged `url`, from the same provider.

Every field with a value names the provider it came from in `field_sources`, and the model refuses
to be built otherwise: a value with no source, a source for a field with no value, a source that is
not one of the members' providers, or a value the named provider did not supply.

## Where MergedCandidate lives

In the application layer, beside the stage that makes it, because it lives only in memory. A search
stores its raw per-provider results (`ProviderStatus`, v1-e08-t01) and its ranking (`SearchResult`),
and merged candidates are a pure function of the first: replaying the stored results through this
stage gives them back. Storing them too would keep a second copy that could disagree with the rules
that made it. If a later task persists them, the model moves to `debate_core.domain.discovery`, as
`ProviderStatus` did.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Self
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from debate_core.application.federated_search_types import SearchState
from debate_core.application.settings import SearchProviderName
from debate_core.domain import DomainModel, NonEmptyText
from debate_core.domain.article import ArticleIdentifiers
from debate_core.domain.base import HttpUrlStr, UtcDatetime
from debate_core.domain.discovery import CandidateResult
from debate_core.domain.enums import SourceType
from debate_core.retrieval import InvalidUrlError, canonicalize_url, detect_identifiers, registrable_domain

__all__ = [
    "FIELD_PRECEDENCE",
    "MERGED_FIELDS",
    "MIN_TITLE_TOKENS",
    "DedupeStage",
    "MatchRule",
    "MergedCandidate",
    "american_spelling",
    "candidate_canonical_url",
    "merge_candidates",
    "merge_group",
    "plain_text",
    "surname_key",
    "title_tokens",
    "titles_agree",
]

MIN_TITLE_TOKENS: Final = 3
"""The fewest words a title may have and still join two records: "Introduction", "Editorial" and
"Reply to critics" name a kind of piece, not one piece."""


class MatchRule(StrEnum):
    """Why records were taken for one source, in the order the rules are tried."""

    DOI = "doi"
    CANONICAL_URL = "canonical_url"
    PROVIDER_ID = "provider_id"
    TITLE = "title"
    """Normalized titles agree, and so do the first author's surname and the publication date."""


MERGED_FIELDS: Final = (
    "title",
    "url",
    "canonical_url",
    "identifiers.doi",
    "identifiers.arxiv_id",
    "identifiers.pmid",
    "identifiers.openalex_id",
    "identifiers.semantic_scholar_id",
    "source_type",
    "authors",
    "publication",
    "published_at",
    "snippet",
    "open_access_url",
)
"""Every field a :class:`MergedCandidate` takes from its members, as `field_sources` names them."""


def candidate_canonical_url(candidate: CandidateResult) -> str | None:
    """The canonical form of the provider's canonical URL, or of its URL; None if it has none."""
    try:
        return canonicalize_url(candidate.canonical_url or candidate.url)
    except InvalidUrlError:
        return None


def _member_value(candidate: CandidateResult, field: str) -> object:
    """What one provider's record says for one merged field, as it said it."""
    if field == "canonical_url":
        return candidate_canonical_url(candidate)
    if field.startswith("identifiers."):
        return getattr(candidate.identifiers, field.removeprefix("identifiers."))
    return getattr(candidate, field)


def _is_empty(value: object) -> bool:
    return value is None or value == () or (isinstance(value, str) and not value.strip())


class MergedCandidate(DomainModel):
    """One source as every provider that found it describes it, with each field's provider named.

    The values are the members' own, chosen field by field by :data:`FIELD_PRECEDENCE`; nothing is
    composed or rewritten except `canonical_url`, the canonical form of the chosen `url`. `members`
    keeps every contributing record as its provider returned it.
    """

    title: NonEmptyText = Field(description="Title, from the provider `field_sources` names.")
    url: HttpUrlStr = Field(description="URL as that provider gave it.")
    canonical_url: HttpUrlStr | None = Field(
        default=None, description="Canonical form of `url`; None when it has none."
    )
    identifiers: ArticleIdentifiers = Field(
        default_factory=ArticleIdentifiers, description="Each identifier from the provider trusted for it."
    )
    source_type: SourceType = Field(default=SourceType.OTHER, description="Descriptive category.")
    authors: tuple[NonEmptyText, ...] = Field(default=(), description="Authors, from one provider.")
    publication: NonEmptyText | None = Field(default=None, description="Journal, outlet or issuing body.")
    published_at: UtcDatetime | None = Field(default=None, description="Publication timestamp, in UTC.")
    snippet: str | None = Field(
        default=None, description="Abstract or snippet: discovery context only, never quoted on a card."
    )
    open_access_url: HttpUrlStr | None = Field(default=None, description="Open-access copy, if any.")
    providers: tuple[NonEmptyText, ...] = Field(
        description="Every provider that returned this source, each once, in the order of `members`."
    )
    members: tuple[CandidateResult, ...] = Field(
        min_length=1, description="Every contributing record, as its provider returned it, in input order."
    )
    matched_on: tuple[MatchRule, ...] = Field(
        default=(), description="The rules that joined the members, in rule order; empty for one record."
    )
    field_sources: dict[str, NonEmptyText] = Field(
        description="For each field in MERGED_FIELDS with a value, the provider that supplied it."
    )

    def value_of(self, field: str) -> object:
        """This candidate's value for one of :data:`MERGED_FIELDS`."""
        if field.startswith("identifiers."):
            return getattr(self.identifiers, field.removeprefix("identifiers."))
        return getattr(self, field)

    @model_validator(mode="after")
    def _check_providers_are_the_members(self) -> Self:
        expected = tuple(dict.fromkeys(member.provider for member in self.members))
        if self.providers != expected:
            raise ValueError(
                f"providers must be the members' providers in order, {expected}, not {self.providers}"
            )
        return self

    @model_validator(mode="after")
    def _check_every_value_names_the_provider_that_supplied_it(self) -> Self:
        unknown = sorted(set(self.field_sources) - set(MERGED_FIELDS))
        if unknown:
            raise ValueError(f"field_sources names fields a MergedCandidate does not have: {unknown}")
        for field in MERGED_FIELDS:
            value = self.value_of(field)
            source = self.field_sources.get(field)
            if source is None:
                if not _is_empty(value):
                    raise ValueError(f"{field} has a value but no source provider in field_sources")
                continue
            if _is_empty(value):
                raise ValueError(f"{field} has no value but field_sources names {source!r} as its source")
            if source not in self.providers:
                raise ValueError(f"{field}'s source {source!r} is not one of the providers {self.providers}")
            if not any(
                member.provider == source and _member_value(member, field) == value for member in self.members
            ):
                raise ValueError(f"{field}'s value was not supplied by its named source {source!r}")
        return self


# ---------------------------------------------------------------------------------------------
# Field precedence
# ---------------------------------------------------------------------------------------------

_CROSSREF = SearchProviderName.CROSSREF.value
_OPENALEX = SearchProviderName.OPENALEX.value
_SEMANTIC_SCHOLAR = SearchProviderName.SEMANTIC_SCHOLAR.value
_RSS = SearchProviderName.RSS.value
_GDELT = SearchProviderName.GDELT.value

_PUBLISHER_DEPOSIT_FIRST = (_CROSSREF, _OPENALEX, _SEMANTIC_SCHOLAR, _RSS, _GDELT)
_INDEXES_FIRST = (_OPENALEX, _SEMANTIC_SCHOLAR, _CROSSREF, _RSS, _GDELT)

FIELD_PRECEDENCE: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        # Crossref holds what the publisher deposited when it registered the DOI; OpenAlex and
        # Semantic Scholar rebuild it from crawls. For news, the publisher's own feed (rss) before
        # GDELT's crawl record.
        "title": _PUBLISHER_DEPOSIT_FIRST,
        "authors": _PUBLISHER_DEPOSIT_FIRST,
        "publication": _PUBLISHER_DEPOSIT_FIRST,
        "source_type": _PUBLISHER_DEPOSIT_FIRST,
        "identifiers.doi": _PUBLISHER_DEPOSIT_FIRST,
        # Crossref's date is the earliest the publisher deposited (online before print); a publisher
        # feed dates its own story; GDELT's date is when GDELT saw the story, so it comes last.
        "published_at": (_CROSSREF, _RSS, _OPENALEX, _SEMANTIC_SCHOLAR, _GDELT),
        # The publisher's own link: a feed item's link is the publisher's page, Crossref's is the DOI
        # resolver, which leads to it. OpenAlex's landing page next; Semantic Scholar's is its own
        # index page; GDELT's is whatever URL it crawled, AMP and tracking included.
        "url": (_RSS, _CROSSREF, _OPENALEX, _SEMANTIC_SCHOLAR, _GDELT),
        # Abstracts and open-access copies are what the indexes add: OpenAlex rebuilds the abstract
        # and finds the best open location, Semantic Scholar has abstracts and open-access PDFs, and
        # Crossref has an abstract only when the publisher deposited one.
        "snippet": _INDEXES_FIRST,
        "open_access_url": _INDEXES_FIRST,
        "identifiers.pmid": _INDEXES_FIRST,
        # Each index first for its own id; Semantic Scholar is the one that lists arXiv ids.
        "identifiers.openalex_id": _INDEXES_FIRST,
        "identifiers.semantic_scholar_id": (_SEMANTIC_SCHOLAR, _OPENALEX, _CROSSREF, _RSS, _GDELT),
        "identifiers.arxiv_id": (_SEMANTIC_SCHOLAR, _OPENALEX, _CROSSREF, _RSS, _GDELT),
    }
)
"""For each merged field, the configured providers in the order their value is taken."""


def _precedence_value(candidate: CandidateResult, field: str) -> object | None:
    """The member's value for `field`, or None when it has none worth taking."""
    value = _member_value(candidate, field)
    if _is_empty(value) or value is SourceType.OTHER:
        return None
    return value


def _in_precedence(members: Sequence[CandidateResult], field: str) -> list[CandidateResult]:
    order = FIELD_PRECEDENCE[field]
    ranked = sorted(
        range(len(members)),
        key=lambda index: (
            order.index(members[index].provider) if members[index].provider in order else len(order),
            index,
        ),
    )
    return [members[index] for index in ranked]


def merge_group(members: Sequence[CandidateResult], matched_on: Sequence[MatchRule] = ()) -> MergedCandidate:
    """One :class:`MergedCandidate` from records already taken for one source, by field precedence."""
    if not members:
        raise ValueError("a merged candidate needs at least one record")
    sources: dict[str, str] = {}

    def chosen(field: str) -> CandidateResult | None:
        """The member whose value `field` takes, recorded as its source; None if no member has one."""
        for member in _in_precedence(members, field):
            if _precedence_value(member, field) is not None:
                sources[field] = member.provider
                return member
        return None

    # Every record has a title and a URL, so these two always find a member.
    title_from = chosen("title") or members[0]
    url_from = chosen("url") or members[0]
    canonical_url = candidate_canonical_url(url_from)
    if canonical_url is not None:
        sources["canonical_url"] = url_from.provider
    doi_from = chosen("identifiers.doi")
    arxiv_from = chosen("identifiers.arxiv_id")
    pmid_from = chosen("identifiers.pmid")
    openalex_from = chosen("identifiers.openalex_id")
    semantic_scholar_from = chosen("identifiers.semantic_scholar_id")
    source_type_from = chosen("source_type")
    if source_type_from is None:
        sources["source_type"] = _in_precedence(members, "source_type")[0].provider
    authors_from = chosen("authors")
    publication_from = chosen("publication")
    published_at_from = chosen("published_at")
    snippet_from = chosen("snippet")
    open_access_from = chosen("open_access_url")
    return MergedCandidate(
        title=title_from.title,
        url=url_from.url,
        canonical_url=canonical_url,
        identifiers=ArticleIdentifiers(
            doi=doi_from.identifiers.doi if doi_from else None,
            arxiv_id=arxiv_from.identifiers.arxiv_id if arxiv_from else None,
            pmid=pmid_from.identifiers.pmid if pmid_from else None,
            openalex_id=openalex_from.identifiers.openalex_id if openalex_from else None,
            semantic_scholar_id=semantic_scholar_from.identifiers.semantic_scholar_id
            if semantic_scholar_from
            else None,
        ),
        source_type=source_type_from.source_type if source_type_from else SourceType.OTHER,
        authors=authors_from.authors if authors_from else (),
        publication=publication_from.publication if publication_from else None,
        published_at=published_at_from.published_at if published_at_from else None,
        snippet=snippet_from.snippet if snippet_from else None,
        open_access_url=open_access_from.open_access_url if open_access_from else None,
        providers=tuple(dict.fromkeys(member.provider for member in members)),
        members=tuple(members),
        matched_on=tuple(rule for rule in MatchRule if rule in matched_on),
        field_sources=sources,
    )


# ---------------------------------------------------------------------------------------------
# Identity keys
# ---------------------------------------------------------------------------------------------

_ARXIV_DOI_PREFIX = "10.48550/arxiv."
_ARXIV_LABEL = re.compile(r"^\s*arxiv:\s*", re.IGNORECASE)


def _arxiv_key(identifiers: ArticleIdentifiers) -> str | None:
    """The arXiv id with no version or label, from `arxiv_id` or else from an arXiv DOI."""
    if identifiers.arxiv_id is not None:
        bare = _ARXIV_LABEL.sub("", identifiers.arxiv_id)
        found = detect_identifiers(f"arXiv:{bare}").arxiv_ids
        return found[0] if found else bare.strip().casefold()
    if identifiers.doi is not None and identifiers.doi.startswith(_ARXIV_DOI_PREFIX):
        found = detect_identifiers(identifiers.doi).arxiv_ids
        return found[0] if found else None
    return None


def _identity(candidate: CandidateResult) -> dict[str, str]:
    """The identifiers that must not disagree within a group, by kind, normalized."""
    ids = candidate.identifiers
    identity: dict[str, str] = {}
    arxiv = _arxiv_key(ids)
    if ids.doi is not None:
        identity["doi"] = ids.doi
    elif arxiv is not None:
        identity["doi"] = f"{_ARXIV_DOI_PREFIX}{arxiv}".casefold()
    if arxiv is not None:
        identity["arxiv"] = arxiv
    if ids.pmid is not None:
        identity["pmid"] = str(int(ids.pmid))
    if ids.openalex_id is not None:
        identity["openalex"] = ids.openalex_id.rstrip("/").rsplit("/", 1)[-1].upper()
    if ids.semantic_scholar_id is not None:
        identity["semantic_scholar"] = ids.semantic_scholar_id.strip().casefold()
    return identity


def _url_key(candidate: CandidateResult) -> str | None:
    canonical = candidate_canonical_url(candidate)
    if canonical is None:
        return None
    parts = urlsplit(canonical)
    if parts.path in ("", "/") and not parts.query:
        return None
    return canonical


def _provider_id_keys(identity: Mapping[str, str]) -> list[tuple[str, str]]:
    return [
        (kind, identity[kind])
        for kind in ("arxiv", "pmid", "openalex", "semantic_scholar")
        if kind in identity
    ]


def _site(candidate: CandidateResult) -> str | None:
    host = urlsplit(candidate_canonical_url(candidate) or candidate.url).hostname
    return registrable_domain(host) if host else None


# ---------------------------------------------------------------------------------------------
# Titles and authors
# ---------------------------------------------------------------------------------------------

_MARKUP = re.compile(r"</?[a-zA-Z][a-zA-Z0-9:-]*(?:\s[^<>]*)?/?>")
_JOINED_INSIDE_WORDS = re.compile(r"[-‐‑'‘’.]")
_WORD = re.compile(r"[^\W_]+")
_SUBTITLE_SEPARATOR = re.compile(r":\s+|\s+[-–—|]\s+")

_AMERICAN_WORDS: Final = MappingProxyType(
    {
        "programme": "program",
        "programmes": "programs",
        "ageing": "aging",
        "grey": "gray",
        "aluminium": "aluminum",
        "sceptic": "skeptic",
        "sceptical": "skeptical",
        "scepticism": "skepticism",
        "paediatric": "pediatric",
        "paediatrics": "pediatrics",
        "anaemia": "anemia",
        "haemorrhage": "hemorrhage",
        "oestrogen": "estrogen",
        "foetal": "fetal",
        "foetus": "fetus",
        "orthopaedic": "orthopedic",
        "manoeuvre": "maneuver",
        "mould": "mold",
        "plough": "plow",
    }
)
"""British spellings no suffix rule covers, and their American forms."""

_AMERICAN_SUFFIXES: Final = (
    ("isational", "izational"),
    ("isations", "izations"),
    ("isation", "ization"),
    ("ourable", "orable"),
    ("elling", "eling"),
    ("ising", "izing"),
    ("ysing", "yzing"),
    ("elled", "eled"),
    ("eller", "eler"),
    ("ised", "ized"),
    ("ises", "izes"),
    ("ysed", "yzed"),
    ("ogue", "og"),
    ("ence", "ense"),
    ("ours", "ors"),
    ("ise", "ize"),
    ("yse", "yze"),
    ("our", "or"),
    ("tre", "ter"),
)
"""British endings and their American forms, longest first. Only words of six letters or more are
rewritten, so four, hour, your, tour, rise and fence stay as they are. Both titles go through the same
rewrite, so a rewrite that produces a word that does not exist (detour to "detor") does no harm; what
the table must never do is turn two different words into one, which is why "-oured" and "-ouring" are
not in it (poured and pored, pouring and poring)."""

_MIN_REWRITTEN_LENGTH: Final = 6


def american_spelling(word: str) -> str:
    """The American spelling of one normalized word, by the tables above; other words unchanged."""
    if word in _AMERICAN_WORDS:
        return _AMERICAN_WORDS[word]
    if len(word) < _MIN_REWRITTEN_LENGTH:
        return word
    for british, american in _AMERICAN_SUFFIXES:
        if word.endswith(british):
            return word[: -len(british)] + american
    return word


def plain_text(text: str) -> str:
    """Entities decoded, markup removed, accents dropped and case folded."""
    decoded = _MARKUP.sub("", html.unescape(text))
    decomposed = unicodedata.normalize("NFKD", decoded)
    return "".join(character for character in decomposed if not unicodedata.combining(character)).casefold()


def _words(plain: str) -> tuple[str, ...]:
    return tuple(_WORD.findall(_JOINED_INSIDE_WORDS.sub("", plain.replace("&", " and "))))


def title_tokens(title: str) -> tuple[str, ...]:
    """A title's words after every normalization two providers' copies of one title can differ by."""
    return tuple(american_spelling(word) for word in _words(plain_text(title)))


def _title_forms(title: str) -> tuple[tuple[str, ...], tuple[str, ...] | None]:
    """The whole title's tokens, and its main title's when it has a subtitle."""
    plain_markup_free = _MARKUP.sub("", html.unescape(title))
    parts = _SUBTITLE_SEPARATOR.split(plain_markup_free, maxsplit=1)
    whole = title_tokens(plain_markup_free)
    return whole, (title_tokens(parts[0]) if len(parts) == 2 else None)


def _forms_agree(
    left: tuple[tuple[str, ...], tuple[str, ...] | None],
    right: tuple[tuple[str, ...], tuple[str, ...] | None],
) -> bool:
    (left_whole, left_main), (right_whole, right_main) = left, right
    if left_whole == right_whole:
        return len(left_whole) >= MIN_TITLE_TOKENS
    if left_main is not None and right_main is None:
        return left_main == right_whole and len(right_whole) >= MIN_TITLE_TOKENS
    if right_main is not None and left_main is None:
        return right_main == left_whole and len(left_whole) >= MIN_TITLE_TOKENS
    return False


def titles_agree(left: str, right: str) -> bool:
    """Whether two titles are one title as two providers wrote it (see the module docstring)."""
    return _forms_agree(_title_forms(left), _title_forms(right))


_NAME_SUFFIXES: Final = frozenset({"jr", "sr", "ii", "iii", "iv"})
_INITIALS = re.compile(r"^[A-Z]{1,3}$")


def surname_key(name: str) -> str | None:
    """The last word of an author's surname, normalized; None when the name has none.

    "Rivera, Ana", "Ana Rivera", "A. Rivera", "Rivera AM" (PubMed's form) and "RIVERA, ANA" all give
    "rivera". A hyphenated surname gives its last part ("Hanna-Attisha" gives "attisha"), and so does
    one with a particle ("van Beethoven" gives "beethoven"), whichever order the name is written in.
    A name written given-name-first cannot be split into given names and surnames reliably, so
    "Ana María Rivera Gómez" gives "gomez" while "Ana Rivera" gives "rivera".
    """
    if "," in name:
        words = name.split(",", 1)[0].split()
    else:
        words = name.split()
        initials_dropped = [word for word in words if not _INITIALS.match(word.replace(".", ""))]
        words = initials_dropped or words
    keys = [
        "".join(_WORD.findall(_JOINED_INSIDE_WORDS.sub("", piece)))
        for word in words
        for piece in plain_text(word).replace("-", " ").split()
    ]
    keys = [key for key in keys if len(key) > 1 and key not in _NAME_SUFFIXES]
    return keys[-1] if keys else None


def _first_author_surname(candidate: CandidateResult) -> str | None:
    return surname_key(candidate.authors[0]) if candidate.authors else None


# ---------------------------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------------------------


class _Groups:
    """Union-find over record positions that refuses to join groups whose identifiers disagree."""

    def __init__(self, identities: Sequence[dict[str, str]]) -> None:
        self._parent = list(range(len(identities)))
        self._identity = [dict(identity) for identity in identities]
        self._rules: list[set[MatchRule]] = [set() for _ in identities]

    def root(self, index: int) -> int:
        while self._parent[index] != index:
            self._parent[index] = self._parent[self._parent[index]]
            index = self._parent[index]
        return index

    def join(self, left: int, right: int, rule: MatchRule) -> None:
        left_root, right_root = self.root(left), self.root(right)
        if left_root == right_root:
            return
        left_identity, right_identity = self._identity[left_root], self._identity[right_root]
        if any(right_identity.get(kind, value) != value for kind, value in left_identity.items()):
            return
        keep, drop = min(left_root, right_root), max(left_root, right_root)
        self._parent[drop] = keep
        self._identity[keep] = {**left_identity, **right_identity}
        self._rules[keep] |= self._rules[drop] | {rule}

    def members(self) -> list[tuple[list[int], set[MatchRule]]]:
        """Each group's positions in input order, with its rules; groups in order of their first position."""
        by_root: dict[int, list[int]] = defaultdict(list)
        for index in range(len(self._parent)):
            by_root[self.root(index)].append(index)
        return [(positions, self._rules[root]) for root, positions in sorted(by_root.items())]


def _join_on_keys(groups: _Groups, keys: Sequence[Sequence[object]], rule: MatchRule) -> None:
    """Link each record to every earlier record sharing one of its keys under `rule`."""
    holders: dict[object, list[int]] = defaultdict(list)
    for index, record_keys in enumerate(keys):
        for key in record_keys:
            for earlier in holders[key]:
                groups.join(earlier, index, rule)
            holders[key].append(index)


def _dates_and_sites_agree(left: CandidateResult, right: CandidateResult) -> bool:
    if left.published_at is None or right.published_at is None:
        return False
    if left.source_type is SourceType.SCHOLARLY and right.source_type is SourceType.SCHOLARLY:
        return left.published_at.year == right.published_at.year
    site = _site(left)
    return left.published_at.date() == right.published_at.date() and site is not None and site == _site(right)


def _join_on_titles(groups: _Groups, candidates: Sequence[CandidateResult]) -> None:
    """Link records whose titles and dates agree, within blocks of one first-author surname.

    The block is the author gate; `_dates_and_sites_agree` is the date gate. Each gate is applied in
    one place only, so neither hides a fault in the other.
    """
    blocks: dict[str, list[int]] = defaultdict(list)
    for index, candidate in enumerate(candidates):
        surname = _first_author_surname(candidate)
        if surname is not None:
            blocks[surname].append(index)
    forms = {index: _title_forms(candidates[index].title) for block in blocks.values() for index in block}
    for block in blocks.values():
        for position, left in enumerate(block):
            for right in block[position + 1 :]:
                if (
                    groups.root(left) != groups.root(right)
                    and _forms_agree(forms[left], forms[right])
                    and _dates_and_sites_agree(candidates[left], candidates[right])
                ):
                    groups.join(left, right, MatchRule.TITLE)


def merge_candidates(candidates: Sequence[CandidateResult]) -> tuple[MergedCandidate, ...]:
    """Every provider's records collapsed into one :class:`MergedCandidate` per distinct source.

    In the order each source's first record appears; each candidate's members in input order.
    """
    identities = [_identity(candidate) for candidate in candidates]
    groups = _Groups(identities)
    _join_on_keys(
        groups, [[c.identifiers.doi] if c.identifiers.doi else [] for c in candidates], MatchRule.DOI
    )
    url_keys = [_url_key(candidate) for candidate in candidates]
    _join_on_keys(groups, [[key] if key else [] for key in url_keys], MatchRule.CANONICAL_URL)
    _join_on_keys(groups, [_provider_id_keys(identity) for identity in identities], MatchRule.PROVIDER_ID)
    _join_on_titles(groups, candidates)
    return tuple(
        merge_group([candidates[index] for index in positions], tuple(rules))
        for positions, rules in groups.members()
    )


class DedupeStage:
    """The normalize stage: `candidates` collapsed into `merged_candidates`, nothing else changed."""

    async def run(self, state: SearchState) -> SearchState:
        return state.evolve(merged_candidates=merge_candidates(state.candidates))

    def __repr__(self) -> str:
        return "DedupeStage()"

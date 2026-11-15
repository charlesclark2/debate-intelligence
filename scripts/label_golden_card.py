#!/usr/bin/env python3
"""Label every golden case from the coach's own card, and render what each case should look like.

`v1-e09-t01-golden-card-fixtures`, nodes `label-offsets` and `expected-renders`. Run by the
operator, after `import_golden_card.py record`, over the local snapshot folder (outside the
repository: the PM's ruling of 2026-11-14, Q2 B):

    uv run scripts/label_golden_card.py --snapshots ~/.debate-intelligence/golden-snapshots
    uv run scripts/label_golden_card.py --snapshots ~/.debate-intelligence/golden-snapshots --render-expected
    uv run scripts/label_golden_card.py --render-expected --check

It prints counts and case IDs, never text.

## Labelling: `expected.json`, offsets only

The coach cut or re-cut every card in the corpus, so the card's own underlining and highlighting
are the coach-authored labels (ac3). For each case with a recorded snapshot, the snapshot copy is
read back and checked (`golden_snapshots.load_recorded_snapshot`) and the team card is read from
`team-card.docx` by the platform's parser. Then:

* **segments.** The card's body is normalized and split at its omission markers, and each stretch
  is found in the snapshot's text, in order, in the comparison form `golden_snapshots` defines (a
  whitespace gap is one space; nothing else is loosened). A stretch the snapshot does not hold
  whole is split at the longest run of whole words it does hold, at least
  :data:`MINIMUM_UNMARKED_WORDS` words, and the rest is looked for after it: a cut the cutter made
  without a marker. Each found stretch is a segment, `[start, end)` of the snapshot's text. A
  stretch that cannot be found leaves the case unlabelled, with the stretch's number and how much
  of it was found;
* **spans.** Each underline (Verbatim's underline and its `Emphasis`, which is underlined) and each
  highlight of the card is carried through the normalizer's offset map onto the characters of the
  snapshot the alignment matched, one span per segment it touches, trimmed of whitespace, merged
  where one style's spans meet. A highlight outside the underlining is cut back to the underlining,
  as the platform's markup requires (a highlight is emphasis within underlined text), and the
  characters cut back are counted. Purposes are `null`: a Verbatim card's runs say how a stretch is
  marked, never what argumentative work it does (`SpanPurpose`);
* an omission marker with nothing of the snapshot between its two sides (one inside a word) leaves
  the case unlabelled: the platform's extractor would join the two segments into one, which no
  longer reads as the card. Whether the segments reproduce the card is `check --snapshots`'s to
  say, by the comparison the alignment matched in, and the render builds them into the platform's
  `ExtractedEvidence` and `CardMarkup`, which refuse anything a card could not hold.

`expected.json` holds the format, the case ID, the team's tag, its cite (short and full, as the
excerpt holds them), the research need, the segments and the spans: offsets into the recorded
snapshot and the team's own words, never evidence text (the spec's forbidden list).

## Rendering: `expected.docx`

`--render-expected` renders each labelled case's card with the renderer (`render_cards_docx`) in the
`team-default` format profile, with no model call: the card is built from `expected.json` and the
snapshot copy by `place_evidence_on_card`, given the team's cite as its cite text, and checked by the
platform's `EvidenceVerifier` against the copy, whose verdict is what the render shows. Nothing
here sets a card VERIFIED. Every id and time in it comes from the case, so a case renders to the
same bytes every time. `--check` renders without writing and fails on any case whose committed
`expected.docx` differs or is missing.

Owned by `v1-e09-t01-golden-card-fixtures`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections.abc import Coroutine, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import golden_snapshots as snapshots  # noqa: E402
import import_golden_card as golden  # noqa: E402

from debate_core.application.evidence_verifier import EvidenceVerifier  # noqa: E402
from debate_core.application.snapshot_service import SnapshotService  # noqa: E402
from debate_core.domain import (  # noqa: E402
    AccessStatus,
    Card,
    Citation,
    ProvenanceMode,
    SourceSnapshot,
    SpanStyle,
)
from debate_core.domain.debate_files import ParsedCard  # noqa: E402
from debate_core.domain.style_profile import RunEmphasis  # noqa: E402
from debate_core.evidence.card_mapping import place_evidence_on_card  # noqa: E402
from debate_core.evidence.card_rendering import CardToRender, CiteText, RenderRefused  # noqa: E402
from debate_core.evidence.docx_renderer import render_cards_docx  # noqa: E402
from debate_core.evidence.extractor import EvidenceExtractor  # noqa: E402
from debate_core.evidence.format_profile import ResolvedFormatProfile, load_format_profile  # noqa: E402
from debate_core.evidence.manifest import MANIFEST_VERSION, CardManifest, SnapshotReference  # noqa: E402
from debate_core.evidence.markup import CardMarkup, EvidenceMarkupSpan, InvalidMarkup  # noqa: E402
from debate_core.evidence.normalization import NORMALIZER_VERSION, NormalizedText, normalize  # noqa: E402
from debate_core.evidence.selection import EvidenceSelection, InvalidSelection  # noqa: E402
from debate_core.evidence.snapshot_text import SnapshotText  # noqa: E402
from debate_core.integrations.docx_parser import DebateDocxParser  # noqa: E402
from debate_core.testing.fakes.persistence import (  # noqa: E402
    InMemoryArticleRepository,
    InMemorySnapshotStore,
)

__all__ = [
    "EXPECTED_RENDER_NAME",
    "MINIMUM_UNMARKED_WORDS",
    "RENDER_PROFILE",
    "CaseLabel",
    "LabelProblem",
    "LabelRefused",
    "golden_id",
    "label_case",
    "main",
    "render_case",
]

EXPECTED_RENDER_NAME: Final = golden.EXPECTED_RENDER_NAME
RENDER_PROFILE: Final = "team-default"
FORMAT_PROFILES_DIR: Final = REPO_ROOT / "config" / "format_profiles"

#: The fewest whole words a stretch split at a cut the cutter did not mark may have. Shorter runs of
#: words recur in any long page, so a match that short says nothing about where the card's text is.
MINIMUM_UNMARKED_WORDS: Final = 4

#: How the card's runs are read as span styles: Verbatim's `Emphasis` is underlined text the
#: debater leans on, so it is underlining; nothing else (bold, shrunk text, cite styling) is a span.
_SPAN_STYLE_OF: Final = {
    RunEmphasis.UNDERLINE: SpanStyle.UNDERLINE,
    RunEmphasis.EMPHASIS: SpanStyle.UNDERLINE,
    RunEmphasis.HIGHLIGHT: SpanStyle.HIGHLIGHT,
}

_GAP_CHARACTERS: Final = " \n"


def _run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    return asyncio.run(coroutine)


class LabelProblem(StrEnum):
    NO_SNAPSHOT_RECORD = "no snapshot record in case.json"
    SNAPSHOT = "the snapshot copy does not verify"
    TEAM_CARD_UNREADABLE = "the team card does not read as one card"
    NOT_FOUND = "a stretch of the card is not in the snapshot"
    NOTHING_OMITTED = "an omission marker leaves nothing of the snapshot out"
    MARKUP_REFUSED = "the platform refuses the card's segments or spans"


class LabelRefused(Exception):
    """One case could not be labelled; `detail` holds counts and positions only, never text."""

    def __init__(self, problem: LabelProblem, detail: str = "") -> None:
        super().__init__(f"{problem.value}{f' ({detail})' if detail else ''}")
        self.problem = problem
        self.detail = detail


@dataclass(frozen=True)
class CaseLabel:
    """What labelling found for one case, as counts. Safe to print."""

    case_id: str
    segments: int
    unmarked_cuts: int
    underlines: int
    highlights: int
    highlight_characters_cut_back: int

    def summary(self) -> str:
        return (
            f"{self.case_id}: {self.segments} segments ({self.unmarked_cuts} unmarked cuts), "
            f"{self.underlines} underlines, {self.highlights} highlights, "
            f"{self.highlight_characters_cut_back} highlighted characters outside the underlining"
        )


# --------------------------------------------------------------------------------------------
# Aligning the card to the snapshot
# --------------------------------------------------------------------------------------------


def _comparison_view(text: str, offset: int = 0) -> tuple[str, list[int]]:
    """`text` in comparison form, and the position in `text` (plus `offset`) of each of its characters.

    The same string :func:`golden_snapshots.comparison_form` gives; a gap's one space stands at the
    gap's first character.
    """
    characters: list[str] = []
    positions: list[int] = []
    in_gap = False
    for position, character in enumerate(text):
        if character in _GAP_CHARACTERS:
            if characters and not in_gap:
                characters.append(" ")
                positions.append(position + offset)
            in_gap = True
        else:
            characters.append(character)
            positions.append(position + offset)
            in_gap = False
    if characters and characters[-1] == " ":
        characters.pop()
        positions.pop()
    return "".join(characters), positions


def _team_stretches(normalized: str, markers: Sequence[str]) -> list[tuple[str, list[int]]]:
    """The normalized card split at its omission markers: each stretch's view and positions."""
    ordered = sorted({marker for marker in markers if marker}, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(marker) for marker in ordered)) if ordered else None
    bounds: list[tuple[int, int]] = []
    start = 0
    for match in pattern.finditer(normalized) if pattern else ():
        bounds.append((start, match.start()))
        start = match.end()
    bounds.append((start, len(normalized)))
    views = [_comparison_view(normalized[a:b], a) for a, b in bounds]
    return [(view, positions) for view, positions in views if view]


def _word_ends(view: str) -> list[int]:
    """Where each whole-word prefix of `view` ends: before each space, and at the end."""
    return [index for index, character in enumerate(view) if character == " "] + [len(view)]


@dataclass
class _Alignment:
    segments: list[tuple[int, int]] = field(default_factory=list)
    to_snapshot: dict[int, int] = field(default_factory=dict)
    unmarked_cuts: int = 0


def _align(snapshot_text: str, stretches: Sequence[tuple[str, list[int]]]) -> _Alignment:
    page, page_positions = _comparison_view(snapshot_text)
    alignment = _Alignment()
    cursor = 0
    for number, (view, positions) in enumerate(stretches, start=1):
        remaining, remaining_positions = view, positions
        after_unmarked_cut = False
        matched = 0
        while remaining:
            # Both sides of a cut the cutter did not mark need the minimum: a short tail found
            # anywhere after the head is no evidence of where the rest of the card is. (A tail that
            # short has no usable prefix either, so it is refused below.)
            too_short = after_unmarked_cut and len(_word_ends(remaining)) < MINIMUM_UNMARKED_WORDS
            found = -1 if too_short else page.find(remaining, cursor)
            if found >= 0:
                taken = len(remaining)
            else:
                ends = _word_ends(remaining)
                usable = ends[MINIMUM_UNMARKED_WORDS - 1 : -1]
                low, high, best = 0, len(usable) - 1, -1
                while low <= high:
                    middle = (low + high) // 2
                    if page.find(remaining[: usable[middle]], cursor) >= 0:
                        best, low = middle, middle + 1
                    else:
                        high = middle - 1
                if best < 0:
                    raise LabelRefused(
                        LabelProblem.NOT_FOUND,
                        f"stretch {number} of {len(stretches)}, {matched} of {len(view)} characters found",
                    )
                taken = usable[best]
                found = page.find(remaining[:taken], cursor)
                alignment.unmarked_cuts += 1
                after_unmarked_cut = True
            for index in range(taken):
                alignment.to_snapshot[remaining_positions[index]] = page_positions[found + index]
            start, end = page_positions[found], page_positions[found + taken - 1] + 1
            if alignment.segments and start <= alignment.segments[-1][1]:
                # A marker with nothing of the snapshot between its two sides (inside a word): the
                # extractor would join the two into one segment, which no longer reads as the card.
                raise LabelRefused(LabelProblem.NOTHING_OMITTED, f"after stretch {number - 1}")
            alignment.segments.append((start, end))
            cursor = found + taken
            matched += taken
            rest, rest_positions = remaining[taken:], remaining_positions[taken:]
            skipped = len(rest) - len(rest.lstrip(" "))
            remaining, remaining_positions = rest[skipped:], rest_positions[skipped:]
    return alignment


# --------------------------------------------------------------------------------------------
# The spans
# --------------------------------------------------------------------------------------------


def _trim(snapshot_text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and snapshot_text[start] in _GAP_CHARACTERS:
        start += 1
    while end > start and snapshot_text[end - 1] in _GAP_CHARACTERS:
        end -= 1
    return (start, end) if start < end else None


def _merge(ranges: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _spans(
    card: ParsedCard, normalized: NormalizedText, alignment: _Alignment, snapshot_text: str
) -> tuple[dict[SpanStyle, list[tuple[int, int]]], int]:
    by_style: dict[SpanStyle, list[tuple[int, int]]] = {style: [] for style in SpanStyle}
    for span in card.formatting_spans:
        style = _SPAN_STYLE_OF.get(span.emphasis)
        if style is None:
            continue
        start, end = normalized.to_normalized_range(span.start_offset, span.end_offset)
        mapped = [alignment.to_snapshot[i] for i in range(start, end) if i in alignment.to_snapshot]
        for segment_start, segment_end in alignment.segments:
            inside = [p for p in mapped if segment_start <= p < segment_end]
            if inside:
                trimmed = _trim(snapshot_text, min(inside), max(inside) + 1)
                if trimmed is not None:
                    by_style[style].append(trimmed)
    merged = {style: _merge(ranges) for style, ranges in by_style.items()}
    underlined = merged[SpanStyle.UNDERLINE]
    kept: list[tuple[int, int]] = []
    cut_back = 0
    for start, end in merged[SpanStyle.HIGHLIGHT]:
        pieces = [(max(start, a), min(end, b)) for a, b in underlined if max(start, a) < min(end, b)]
        cut_back += (end - start) - sum(b - a for a, b in pieces)
        kept += [piece for piece in (_trim(snapshot_text, a, b) for a, b in pieces) if piece is not None]
    merged[SpanStyle.HIGHLIGHT] = _merge(kept)
    return merged, cut_back


# --------------------------------------------------------------------------------------------
# The snapshot record a card is built on
# --------------------------------------------------------------------------------------------

_CROCKFORD: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def golden_id(kind: str, case_id: str) -> str:
    """A ULID-shaped id for one of a case's records, the same on every run: from its kind and case."""
    number = (
        int.from_bytes(hashlib.sha256(f"golden-card:{kind}:{case_id}".encode()).digest()[:16], "big") >> 3
    )
    characters = []
    for _ in range(25):
        characters.append(_CROCKFORD[number & 31])
        number >>= 5
    return "0" + "".join(reversed(characters))


def _moment(record: snapshots.SnapshotRecord) -> datetime:
    return datetime.fromisoformat(record.fetched_on).replace(tzinfo=UTC)


def _source_snapshot(case_id: str, record: snapshots.SnapshotRecord) -> SourceSnapshot:
    """The snapshot record a case's copy stands for, rebuilt from `case.json`'s digests."""
    moment = _moment(record)
    return SourceSnapshot(
        snapshot_id=golden_id("snapshot", case_id),
        owner_id=None,
        organization_id=None,
        article_id=golden_id("article", case_id),
        canonical_url=record.canonical_url,
        retrieved_at=moment,
        access_status=AccessStatus(record.access_status),
        provenance_mode=ProvenanceMode(record.provenance_mode),
        raw_blob_key=record.raw_sha256,
        normalized_blob_key=record.normalized_document_sha256,
        sha256=record.raw_sha256,
        normalized_text_hash=record.normalized_text_sha256,
        extractor_version=record.extractor_version,
        normalizer_version=record.normalizer_version,
        content_type=record.content_type,
        byte_size=record.raw_byte_size,
        created_at=moment,
        updated_at=moment,
    )


def _markup(
    snapshot: SourceSnapshot,
    text: SnapshotText,
    segments: Sequence[Sequence[int]],
    spans: Sequence[EvidenceMarkupSpan],
) -> CardMarkup:
    try:
        evidence = EvidenceExtractor().extract(
            snapshot, text, EvidenceSelection.of_offsets(*((start, end) for start, end in segments))
        )
        return CardMarkup(evidence, tuple(spans))
    except (InvalidSelection, InvalidMarkup) as refused:
        raise LabelRefused(LabelProblem.MARKUP_REFUSED, type(refused).__name__) from refused


# --------------------------------------------------------------------------------------------
# Labelling one case
# --------------------------------------------------------------------------------------------


def _record_of(case: dict[str, Any]) -> snapshots.SnapshotRecord:
    if not isinstance(case.get("snapshot"), dict):
        raise LabelRefused(LabelProblem.NO_SNAPSHOT_RECORD)
    try:
        return snapshots.SnapshotRecord.from_json(case["snapshot"])
    except KeyError as missing:
        raise LabelRefused(LabelProblem.NO_SNAPSHOT_RECORD) from missing


def _verified_text(case_id: str, record: snapshots.SnapshotRecord, snapshot_folder: Path) -> SnapshotText:
    try:
        return snapshots.load_recorded_snapshot(snapshot_folder / case_id, record)
    except snapshots.SnapshotProblem as problem:
        raise LabelRefused(LabelProblem.SNAPSHOT, problem.code.value) from problem


def label_case(
    case_dir: Path, snapshot_folder: Path, parser: DebateDocxParser
) -> tuple[dict[str, Any], CaseLabel]:
    """`expected.json` for one case, and its counts; raise :class:`LabelRefused`."""
    case = json.loads((case_dir / golden.CASE_NAME).read_text(encoding="utf-8"))
    case_id = case["case_id"]
    record = _record_of(case)
    text = _verified_text(case_id, record, snapshot_folder)
    card = golden.team_card(case_dir, parser)
    if card is None or card.tag is None:
        raise LabelRefused(LabelProblem.TEAM_CARD_UNREADABLE)
    markers = parser.profile.cite.wiki_ellipsis_markers
    normalized = normalize(card.evidence_text, NORMALIZER_VERSION)
    alignment = _align(text.text, _team_stretches(normalized.text, markers))
    spans, cut_back = _spans(card, normalized, alignment, text.text)
    markup_spans = [
        EvidenceMarkupSpan(start, end, style) for style in SpanStyle for start, end in spans[style]
    ]
    segments = [[start, end] for start, end in alignment.segments]
    expected = {
        "format": snapshots.EXPECTED_FORMAT,
        "case_id": case_id,
        "tag": card.tag,
        "cite": {"short_cite": card.short_cite, "full_cite": card.full_cite},
        "research_need": case["research_need"],
        "segments": segments,
        "spans": [
            {"start": span.start, "end": span.end, "style": span.style.value, "purpose": None}
            for span in sorted(markup_spans, key=lambda span: (span.start, span.style.value))
        ],
    }
    return expected, CaseLabel(
        case_id=case_id,
        segments=len(segments),
        unmarked_cuts=alignment.unmarked_cuts,
        underlines=len(spans[SpanStyle.UNDERLINE]),
        highlights=len(spans[SpanStyle.HIGHLIGHT]),
        highlight_characters_cut_back=cut_back,
    )


# --------------------------------------------------------------------------------------------
# Rendering one case
# --------------------------------------------------------------------------------------------


class _FixedClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


class _NoIds:
    def new_id(self) -> str:
        raise AssertionError("verifying a golden card mints no id")


def _cite_text(expected: dict[str, Any]) -> CiteText:
    cite = expected["cite"]
    short = cite.get("short_cite") or cite["full_cite"].split("[", 1)[0].strip() or expected["case_id"]
    full = cite["full_cite"] if cite["full_cite"].startswith(short) else f"{short} {cite['full_cite']}"
    return CiteText(short_cite=short, full_cite=full)


def render_case(case_dir: Path, snapshot_folder: Path, profile: ResolvedFormatProfile) -> bytes:
    """`expected.docx` for one labelled case: its card, verified against the copy, rendered."""
    case = json.loads((case_dir / golden.CASE_NAME).read_text(encoding="utf-8"))
    expected = json.loads((case_dir / golden.EXPECTED_NAME).read_text(encoding="utf-8"))
    case_id = case["case_id"]
    record = _record_of(case)
    text = _verified_text(case_id, record, snapshot_folder)
    snapshot = _source_snapshot(case_id, record)
    spans = [
        EvidenceMarkupSpan(span["start"], span["end"], SpanStyle(span["style"])) for span in expected["spans"]
    ]
    markup = _markup(snapshot, text, expected["segments"], spans)
    moment = _moment(record)
    blank = Card(
        card_id=golden_id("card", case_id),
        owner_id=golden_id("owner", case_id),
        article_id=snapshot.article_id,
        tag=expected["tag"],
        citation=Citation(),
        provenance_mode=ProvenanceMode.PASTED,
        format_profile=RENDER_PROFILE,
        created_at=moment,
        updated_at=moment,
    )
    placed = place_evidence_on_card(blank, markup)
    # A span's id is minted at random; numbered from the case instead, a case renders the same bytes.
    card = placed.model_copy(
        update={
            "spans": tuple(
                span.model_copy(update={"span_id": golden_id(f"span-{number}", case_id)})
                for number, span in enumerate(placed.spans, start=1)
            )
        }
    )

    articles = InMemoryArticleRepository()
    blobs = InMemorySnapshotStore()
    _run(articles.save_snapshot(snapshot))
    _run(blobs.put((snapshot_folder / case_id / snapshots.RAW_NAME).read_bytes()))
    _run(blobs.put((snapshot_folder / case_id / snapshots.NORMALIZED_NAME).read_bytes()))
    clock = _FixedClock(moment)
    verifier = EvidenceVerifier(
        articles=articles,
        snapshots=SnapshotService(blobs=blobs, clock=clock, id_generator=_NoIds()),
        clock=clock,
    )
    card, result = _run(verifier.verify_and_record(card))
    reasons = tuple(dict.fromkeys(reason.code.value for reason in result.reasons))
    manifest = CardManifest(
        manifest_version=MANIFEST_VERSION,
        generated_at=moment,
        cards=(card,),
        snapshots=(SnapshotReference.of(snapshot),),
    )
    return render_cards_docx(manifest, [CardToRender(card, _cite_text(expected), reasons)], profile)


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------


def _cases(fixtures_dir: Path) -> list[Path]:
    return sorted(path.parent for path in fixtures_dir.glob(f"*/{golden.CASE_NAME}"))


def _label_all(fixtures_dir: Path, snapshot_folder: Path) -> int:
    parser = DebateDocxParser()
    labelled = refused = 0
    for case_dir in _cases(fixtures_dir):
        try:
            expected, counts = label_case(case_dir, snapshot_folder, parser)
        except LabelRefused as refusal:
            refused += 1
            print(f"{case_dir.name}: NOT LABELLED: {refusal}")
            continue
        (case_dir / golden.EXPECTED_NAME).write_text(
            json.dumps(expected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        labelled += 1
        print(counts.summary())
    print(f"labelled {labelled}, not labelled {refused}")
    return 0 if labelled and not refused else 1


def _render_all(fixtures_dir: Path, snapshot_folder: Path, *, check: bool) -> int:
    profile = load_format_profile(RENDER_PROFILE, FORMAT_PROFILES_DIR)
    rendered = differ = failed = 0
    for case_dir in _cases(fixtures_dir):
        target = case_dir / EXPECTED_RENDER_NAME
        if not (case_dir / golden.EXPECTED_NAME).is_file():
            failed += 1
            print(f"{case_dir.name}: not rendered: no expected.json")
            continue
        try:
            content = render_case(case_dir, snapshot_folder, profile)
        except (LabelRefused, RenderRefused) as refusal:
            failed += 1
            print(f"{case_dir.name}: not rendered: {refusal}")
            continue
        rendered += 1
        if check:
            if not target.is_file() or target.read_bytes() != content:
                differ += 1
                print(f"{case_dir.name}: expected.docx {'is missing' if not target.is_file() else 'differs'}")
        else:
            target.write_bytes(content)
    verb = "rendered and compared" if check else "rendered"
    print(f"{verb} {rendered}, differ {differ}, not rendered {failed}")
    return 0 if rendered and not differ and not failed else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="label_golden_card.py", description=(__doc__ or "").split("\n\n")[0]
    )
    parser.add_argument(
        "--snapshots",
        type=Path,
        default=snapshots.DEFAULT_SNAPSHOT_FOLDER,
        help="the local snapshot folder `import_golden_card.py record` wrote",
    )
    parser.add_argument("--render-expected", action="store_true", help="render expected.docx, not label")
    parser.add_argument("--check", action="store_true", help="with --render-expected: compare, write nothing")
    parser.add_argument("--fixtures", type=Path, default=golden.FIXTURES_DIR, help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    folder = arguments.snapshots.expanduser()
    if arguments.check and not arguments.render_expected:
        parser.error("--check goes with --render-expected")
    if arguments.render_expected:
        return _render_all(arguments.fixtures, folder, check=arguments.check)
    return _label_all(arguments.fixtures, folder)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

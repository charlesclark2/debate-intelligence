"""A local text classifier for the cards headings cannot place, compared before it is wired (`v1-e32-t21`).

Headings and tags place about half of a caselist's cards (`v1-e32-t02`). This module asks whether a
light model, trained on this machine from the cards they do place, could place the rest. Nothing here
is wired into the matcher, the review queue or the report: it trains, scores and counts.

## The model

Word and short-phrase weights: TF-IDF over the word 1- and 2-grams of a card's headings and of its
tag, kept apart (a heading's words are `h:` tokens, the tag's `t:`), with scikit-learn's logistic
regression over them. No pretrained model, no download and no model provider: everything it knows is
fitted here, from the rows it is given.

## What it reads (:class:`FeatureRow`)

A card as the matcher reads it (:func:`~debate_core.arguments.landscape.matcher.read_items`): its
headings normalized with the disclosing teams' own names and the caselist's schools taken out, and
its tag as words with the same names and every team code of the caselist taken out (:func:`card_tag`).
Never a cite, a file path, a team or the card's text: the disclosing teams are kept only as keyed
digests (:func:`team_token`), to count. A token is a feature only when the training cards of at least
`minimum_teams` distinct teams carry it (:data:`DEFAULT_MINIMUM_FEATURE_TEAMS`), so a word only one
team writes, such as a debater's name, never is.

## The labels

The deterministic placements at or above the review threshold, made by ALIAS, INHERITED, OVERRIDE or
TAG_KEYWORD. A card the coach ruled names no position, one placed below the threshold, and an unplaced
one are never labels.

## The comparison (:func:`compare`)

1. **A held-out tenth, by document.** The documents are ordered by a seeded digest of their sha256
   and the first tenth is held out, so no file has cards on both sides of the split. The model is
   trained on the labelled cards of the rest.
2. **Held-out precision and recall** by position kind and by position, precision by confidence band,
   and :attr:`HeldOutMeasure.confidence_at_target`: the lowest confidence on a fixed grid above which
   held-out precision is at least 90%, there and at every higher grid point with enough cards.
3. **What it would place**: the unplaced cards, and the other cards no label covers, it would place at
   that confidence, by kind.
4. **A coach sample** (:func:`coach_sample`): unplaced cards for the coach to label from their tag and
   headings, stratified by one model's confidence and by predicted kind, one card per document, and
   each compared model's score on the coach's labels (:func:`score_sample`).

Deterministic for a seed: the split, the fitted weights, the predictions and the sample are the same
on every run, whatever order the rows arrive in. Pure: rows in, values out. The caller reads the store
and writes the files, under the data directory.

Every value that holds a heading, a tag or a team withholds it from its `repr`.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any, Final, TextIO, cast

from sklearn.feature_extraction.text import TfidfVectorizer  # pyright: ignore[reportMissingTypeStubs]
from sklearn.linear_model import LogisticRegression  # pyright: ignore[reportMissingTypeStubs]

from debate_core.arguments.landscape.matcher import PositionMatcher, read_items, tag_words
from debate_core.arguments.landscape.review_queue import DEFAULT_REVIEW_THRESHOLD, needs_review
from debate_core.arguments.landscape.seeding import SeedSource
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import ClassificationMethod, ClassificationResult, ItemKind

__all__ = [
    "BELOW_THRESHOLD",
    "CONFIDENCE_BANDS",
    "CONFIDENCE_GRID",
    "DECIDED_NO_POSITION",
    "DEFAULT_MINIMUM_FEATURE_TEAMS",
    "DEFAULT_MINIMUM_SUPPORT",
    "DEFAULT_SEED",
    "HELD_OUT_SHARE",
    "LABEL_METHODS",
    "NO_POSITION_LABEL",
    "SAMPLE_COLUMNS",
    "SAMPLE_SCHEMA",
    "SAMPLE_STRATA",
    "TARGET_PRECISION",
    "UNPLACED",
    "WITHHELD_HEADING",
    "Band",
    "CoachSample",
    "Comparison",
    "FeatureRow",
    "HeldOutMeasure",
    "LocalClassifier",
    "Prediction",
    "SampleItem",
    "SampleScore",
    "StratumScore",
    "Tally",
    "WouldPlace",
    "card_tag",
    "coach_sample",
    "code_words",
    "compare",
    "feature_rows",
    "feature_tokens",
    "heading_teams",
    "held_out_documents",
    "measure_held_out",
    "read_sample",
    "read_sample_labels",
    "row_from_json",
    "row_to_json",
    "sample_lines",
    "score_sample",
    "team_token",
    "team_vocabulary",
    "write_sample_csv",
]

DEFAULT_SEED: Final = 21
"""The seed of the split, the sample and the regression's solver, unless a run names another."""

DEFAULT_MINIMUM_FEATURE_TEAMS: Final = 3
"""A token fewer training teams carry is no feature. Three, not two: a debater who changes partners is
two teams."""

HELD_OUT_SHARE: Final = 0.1
TARGET_PRECISION: Final = 0.9
DEFAULT_MINIMUM_SUPPORT: Final = 50
"""A grid point with fewer held-out cards above it says too little to fail the target on."""

CONFIDENCE_BANDS: Final = (0.0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
"""The lower edges of the bands precision is shown in; each runs to the next edge, the last to 1."""

CONFIDENCE_GRID: Final = (*(step / 20 for step in range(20)), 0.975, 0.99)
"""The confidences a threshold is chosen from: 0, 0.05 ... 0.95, then 0.975 and 0.99."""

LABEL_METHODS: Final = frozenset(
    {
        ClassificationMethod.ALIAS,
        ClassificationMethod.INHERITED,
        ClassificationMethod.OVERRIDE,
        ClassificationMethod.TAG_KEYWORD,
    }
)

UNPLACED: Final = "UNPLACED"
"""A card nothing placed, as `v1-e32-t02`'s counts name it."""

DECIDED_NO_POSITION: Final = "OVERRIDE_NO_POSITION"
"""A card every heading over which the coach ruled names no position, as `v1-e32-t02`'s counts name it."""

BELOW_THRESHOLD: Final = "BELOW_THRESHOLD"
"""A card placed under a position less surely than the review threshold: its tag alone placed it."""

NO_POSITION_LABEL: Final = "none"
"""What the coach writes for a sampled card that belongs to no position."""

_UNSURE_LABEL: Final = "unsure"

WITHHELD_HEADING: Final = "[a heading one team used]"
"""What the sample shows for a heading fewer than two teams use, which the review queue leaves out too."""

_MINIMUM_SHOWN_HEADING_TEAMS: Final = 2

SAMPLE_COLUMNS: Final = ("sample_row", "tag", "headings", "position", "note")

SAMPLE_STRATA: Final = (
    ("at-or-above-threshold", 30),
    ("just-below-threshold", 20),
    ("far-below-threshold", 10),
)
"""How the 60 sampled cards divide by the stratifying model's confidence: at or above its threshold (what
wiring it would place), then the cards below it split at their median confidence."""

SAMPLE_SCHEMA: Final = "local-classifier-sample-1"
_FALLBACK_THRESHOLD: Final = 0.9
"""Where the sample's top stratum starts when no confidence reaches the target precision."""

_PREDICTION_BATCH: Final = 20_000
_MAX_ITERATIONS: Final = 1_000


# ------------------------------------------------------------------------------------------------
# What it reads
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FeatureRow:
    """One card as the classifier reads it, and what the deterministic stage made of it."""

    item_id: str
    source_sha256: str
    teams: tuple[str, ...] = field(repr=False)
    """The teams that disclosed the card's document, as keyed digests (:func:`team_token`): only counted."""
    headings: tuple[str, ...] = field(repr=False)
    """The non-empty normalized headings over the card, outermost first, names taken out."""
    placing: tuple[bool, ...]
    """For each heading, whether it places a card on its own: an alias, or an override naming a position."""
    tag: str | None = field(repr=False)
    """The tag as words, the teams' own names and the caselist's schools taken out."""
    placement: str
    """The placing method; else :data:`UNPLACED`, :data:`DECIDED_NO_POSITION` or :data:`BELOW_THRESHOLD`."""
    label: str | None
    """The position the deterministic stage placed it under, when that is a label (:data:`LABEL_METHODS`)."""


def card_tag(
    tag: str | None,
    own_names: Sequence[str],
    caselist: CaselistNames,
    codes: Collection[str] = frozenset(),
) -> str | None:
    """`tag` as words, without the disclosing teams' own names, any school of the caselist, or any word
    of `codes`, the caselist's team codes as :func:`code_words` gives them.

    A tag is free text, so a team code standing alone in it is taken out too, which a heading keeps
    (`v1-e32-t01`): a code that is also an ordinary word costs a tag one word.
    """
    if tag is None:
        return None
    words = tag_words(tag)
    for name in own_names:
        phrase = tag_words(name)
        if phrase:
            words = " ".join(re.sub(rf"(?<!\S){re.escape(phrase)}(?!\S)", " ", words).split())
    words = caselist.without_schools(words)
    return " ".join(word for word in words.split() if word not in codes) or None


def team_token(identity: str, salt: bytes) -> str:
    """A team's identity as a digest keyed by `salt`, equal for equal identities under one salt.

    The builder of a feature table draws the salt and keeps it nowhere, so the table can count a word's
    teams and cannot name one: an unkeyed digest of a school and code could be found by trying the
    caselist's schools.
    """
    return hashlib.blake2b(identity.encode(), key=salt, digest_size=12).hexdigest()


def code_words(names: Mapping[str, Sequence[str]]) -> frozenset[str]:
    """Every word of every team code of a caselist's schools (`school -> codes`), as a tag's words are."""
    return frozenset(word for codes in names.values() for code in codes for word in tag_words(code).split())


def _placement(result: ClassificationResult, review_threshold: float) -> str:
    if result.method is None:
        return UNPLACED
    if result.position_id is None:
        return DECIDED_NO_POSITION
    if needs_review(result, review_threshold):
        return BELOW_THRESHOLD
    return result.method.value


def feature_rows(
    source: SeedSource,
    caselist: CaselistNames,
    matcher: PositionMatcher,
    *,
    team_salt: bytes,
    codes: Collection[str] = frozenset(),
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> tuple[FeatureRow, ...]:
    """Every card of `source` as the classifier reads it, placed by `matcher`, in file order.

    `codes` are the caselist's team codes as :func:`code_words` gives them, taken out of each tag; the
    teams are written as :func:`team_token` keys them under `team_salt`.
    """
    own = [name for team in source.teams for name in team.names if name.strip()]
    teams = tuple(sorted({team_token(team.identity, team_salt) for team in source.teams if team.identity}))
    rows: list[FeatureRow] = []
    for item in read_items(source, caselist):
        if item.kind is not ItemKind.CARD:
            continue
        result = matcher.place(item)
        placement = _placement(result, review_threshold)
        headings = tuple(heading.text for heading in item.headings)
        rows.append(
            FeatureRow(
                item_id=item.item_id,
                source_sha256=source.sha256,
                teams=teams,
                headings=headings,
                placing=tuple(matcher.placing_index([text]) is not None for text in headings),
                tag=card_tag(item.tag, own, caselist, codes),
                placement=placement,
                label=result.position_id if placement in LABEL_METHODS else None,
            )
        )
    return tuple(rows)


def row_to_json(row: FeatureRow) -> str:
    """One row as a compact JSON line, for the feature table under the data directory."""
    return json.dumps(
        {
            "item_id": row.item_id,
            "source_sha256": row.source_sha256,
            "teams": list(row.teams),
            "headings": list(row.headings),
            "placing": list(row.placing),
            "tag": row.tag,
            "placement": row.placement,
            "label": row.label,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def row_from_json(line: str) -> FeatureRow:
    data = cast(dict[str, Any], json.loads(line))
    return FeatureRow(
        item_id=str(data["item_id"]),
        source_sha256=str(data["source_sha256"]),
        teams=tuple(str(one) for one in data["teams"]),
        headings=tuple(str(one) for one in data["headings"]),
        placing=tuple(bool(one) for one in data["placing"]),
        tag=None if data["tag"] is None else str(data["tag"]),
        placement=str(data["placement"]),
        label=None if data["label"] is None else str(data["label"]),
    )


def feature_tokens(row: FeatureRow, *, without_placing_headings: bool = False) -> tuple[str, ...]:
    """The row's word 1- and 2-grams: each heading's as `h:` tokens, the tag's as `t:` tokens.

    A phrase never runs from one heading into the next, or from a heading into the tag. With
    `without_placing_headings`, a heading that places a card on its own is left out, as no heading over
    an unplaced card does.
    """
    found: list[str] = []
    for text, places in zip(row.headings, row.placing, strict=True):
        if not (without_placing_headings and places):
            found += _grams("h", text.split())
    if row.tag:
        found += _grams("t", row.tag.split())
    return tuple(found)


def _grams(prefix: str, words: Sequence[str]) -> list[str]:
    return [f"{prefix}:{word}" for word in words] + [f"{prefix}:{one} {two}" for one, two in pairwise(words)]


def team_vocabulary(
    documents: Iterable[tuple[Sequence[str], Sequence[str]]], minimum_teams: int
) -> tuple[str, ...]:
    """The tokens of `(tokens, teams)` documents that at least `minimum_teams` distinct teams carry, sorted.

    A document no known team disclosed counts for no team.
    """
    teams_of: dict[str, set[str]] = defaultdict(set)
    for tokens, teams in documents:
        if teams:
            for token in set(tokens):
                teams_of[token].update(teams)
    return tuple(sorted(token for token, teams in teams_of.items() if len(teams) >= minimum_teams))


# ------------------------------------------------------------------------------------------------
# The model
# ------------------------------------------------------------------------------------------------


def _as_given(tokens: Sequence[str]) -> Sequence[str]:
    """The vectorizer's analyzer: the tokens are already made by :func:`feature_tokens`."""
    return tokens


@dataclass(frozen=True, slots=True)
class Prediction:
    position_id: str
    confidence: float
    """The model's probability for that position: the largest it gives."""


class LocalClassifier:
    """TF-IDF over word 1- and 2-grams with a logistic regression, fitted on labelled rows."""

    def __init__(
        self,
        vectorizer: Any,
        model: Any,
        *,
        vocabulary: tuple[str, ...],
        without_placing_headings: bool,
        trained_cards: int,
    ) -> None:
        self._vectorizer = vectorizer
        self._model = model
        self.vocabulary = vocabulary
        self.without_placing_headings = without_placing_headings
        self.trained_cards = trained_cards
        """Labelled cards with at least one feature, before identical ones were folded together."""

    def __repr__(self) -> str:
        return f"LocalClassifier(<{len(self.vocabulary)} features withheld>, classes={len(self.classes)})"

    @property
    def classes(self) -> tuple[str, ...]:
        return tuple(str(one) for one in cast(Iterable[object], self._model.classes_))

    @classmethod
    def train(
        cls,
        rows: Iterable[FeatureRow],
        *,
        seed: int = DEFAULT_SEED,
        minimum_teams: int = DEFAULT_MINIMUM_FEATURE_TEAMS,
        without_placing_headings: bool = False,
    ) -> LocalClassifier:
        """Fit on the labelled rows of `rows`. Identical (tokens, label) cards are fitted once, weighted.

        Raises `ValueError` when fewer than two positions have a labelled card with a feature.
        """
        labelled = [
            (feature_tokens(row, without_placing_headings=without_placing_headings), row)
            for row in rows
            if row.label is not None
        ]
        vocabulary = team_vocabulary(((tokens, row.teams) for tokens, row in labelled), minimum_teams)
        known = frozenset(vocabulary)
        folded: Counter[tuple[tuple[str, ...], str]] = Counter()
        for tokens, row in labelled:
            kept = tuple(sorted(token for token in tokens if token in known))
            if kept and row.label is not None:
                folded[(kept, row.label)] += 1
        if len({label for _, label in folded}) < 2:
            raise ValueError("the classifier needs labelled cards with features under two positions at least")
        keys = sorted(folded)
        # The stubs type `analyzer` as a name only; a callable is the documented way to pass tokens in.
        options: dict[str, Any] = {"analyzer": _as_given, "vocabulary": vocabulary, "lowercase": False}
        vectorizer: Any = TfidfVectorizer(sublinear_tf=True, **options)
        matrix = vectorizer.fit_transform([tokens for tokens, _ in keys])
        model: Any = LogisticRegression(max_iter=_MAX_ITERATIONS, random_state=seed)
        model.fit(matrix, [label for _, label in keys], sample_weight=[folded[key] for key in keys])
        return cls(
            vectorizer,
            model,
            vocabulary=vocabulary,
            without_placing_headings=without_placing_headings,
            trained_cards=sum(folded.values()),
        )

    def predict(self, rows: Sequence[FeatureRow]) -> tuple[Prediction | None, ...]:
        """Each row's likeliest position and its probability; None for a row with no feature."""
        classes = self.classes
        found: list[Prediction | None] = []
        for start in range(0, len(rows), _PREDICTION_BATCH):
            batch = rows[start : start + _PREDICTION_BATCH]
            matrix: Any = self._vectorizer.transform(
                [feature_tokens(row, without_placing_headings=self.without_placing_headings) for row in batch]
            )
            features = [int(count) for count in matrix.getnnz(axis=1)]
            probabilities: Any = self._model.predict_proba(matrix)
            best = [int(index) for index in probabilities.argmax(axis=1)]
            for number, index in enumerate(best):
                found.append(
                    Prediction(classes[index], float(probabilities[number, index]))
                    if features[number]
                    else None
                )
        return tuple(found)


# ------------------------------------------------------------------------------------------------
# The held-out measure
# ------------------------------------------------------------------------------------------------


def _digest(seed: int, key: str) -> str:
    return hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()


def held_out_documents(documents: Iterable[str], seed: int = DEFAULT_SEED) -> frozenset[str]:
    """A tenth of `documents` (rounded, at least one of two or more): the first by a seeded digest."""
    ordered = sorted(set(documents), key=lambda sha: (_digest(seed, sha), sha))
    count = round(len(ordered) * HELD_OUT_SHARE)
    if len(ordered) >= 2:
        count = max(count, 1)
    return frozenset(ordered[:count])


@dataclass(frozen=True, slots=True)
class Tally:
    """Held-out cards of one position or kind, the predictions of it, and the right ones among them."""

    name: str
    held_out: int
    """Held-out cards labelled with it."""
    predicted: int
    """Held-out cards predicted as it."""
    correct: int
    """Of those predicted, the ones whose position is the label's."""
    right_kind: int = 0
    """Of those predicted, the ones whose label is a position of the same kind (kinds only)."""

    @property
    def precision(self) -> float | None:
        return self.correct / self.predicted if self.predicted else None

    @property
    def recall(self) -> float | None:
        return self.correct / self.held_out if self.held_out else None


@dataclass(frozen=True, slots=True)
class Band:
    """Held-out predictions with a confidence from `low` (included) to `high` (excluded, or 1 included)."""

    low: float
    high: float
    cards: int
    correct: int

    @property
    def precision(self) -> float | None:
        return self.correct / self.cards if self.cards else None


@dataclass(frozen=True, slots=True)
class HeldOutMeasure:
    cards: int
    """Labelled held-out cards."""
    predicted: int
    """Of those, the ones with a feature, so a prediction."""
    correct: int
    by_kind: tuple[Tally, ...]
    by_position: tuple[Tally, ...]
    bands: tuple[Band, ...]
    at_or_above: tuple[Band, ...]
    """For each grid confidence, the predictions at or above it (`high` is 1)."""
    confidence_at_target: float | None
    """The lowest grid confidence from which held-out precision stays at the target; None if none does."""
    seen_in_training: int = 0
    """Predicted held-out cards whose features a training card has exactly."""
    seen_in_training_correct: int = 0
    unseen_at_or_above: tuple[Band, ...] = ()
    """:attr:`at_or_above` over the predicted cards no training card has the features of."""


def _kind(taxonomy: Taxonomy, position_id: str) -> str:
    return taxonomy.resolve(position_id).kind.value


def _at_or_above(made: Sequence[tuple[str, Prediction]]) -> tuple[Band, ...]:
    return tuple(
        Band(
            low,
            1.0,
            sum(prediction.confidence >= low for _, prediction in made),
            sum(
                prediction.confidence >= low and label == prediction.position_id for label, prediction in made
            ),
        )
        for low in CONFIDENCE_GRID
    )


def measure_held_out(
    taxonomy: Taxonomy,
    labels: Sequence[str],
    predictions: Sequence[Prediction | None],
    *,
    seen: Sequence[bool] | None = None,
    minimum_support: int = DEFAULT_MINIMUM_SUPPORT,
) -> HeldOutMeasure:
    """Precision and recall of `predictions` against `labels`, by kind, position and confidence.

    With `seen`, which held-out cards have a training card's features exactly, it also counts those
    and gives the precision of the others at each grid confidence.
    """
    if len(labels) != len(predictions) or (seen is not None and len(seen) != len(labels)):
        raise ValueError("one prediction, and one seen flag when given, per label")
    flags = list(seen) if seen is not None else [False] * len(labels)
    made = [
        (label, prediction, flag)
        for label, prediction, flag in zip(labels, predictions, flags, strict=True)
        if prediction is not None
    ]
    pairs = [(label, prediction) for label, prediction, _ in made]

    def tallies(name_of: Callable[[str], str], kinds: bool) -> tuple[Tally, ...]:
        held: Counter[str] = Counter(name_of(label) for label in labels)
        predicted: Counter[str] = Counter(name_of(prediction.position_id) for _, prediction in pairs)
        correct: Counter[str] = Counter(
            name_of(prediction.position_id) for label, prediction in pairs if label == prediction.position_id
        )
        right_kind: Counter[str] = Counter(
            name_of(prediction.position_id)
            for label, prediction in pairs
            if kinds and _kind(taxonomy, label) == _kind(taxonomy, prediction.position_id)
        )
        return tuple(
            Tally(name, held[name], predicted[name], correct[name], right_kind[name])
            for name in sorted(set(held) | set(predicted))
        )

    bands: list[Band] = []
    for number, low in enumerate(CONFIDENCE_BANDS):
        high = CONFIDENCE_BANDS[number + 1] if number + 1 < len(CONFIDENCE_BANDS) else 1.0
        inside = [
            (label, prediction)
            for label, prediction in pairs
            if low <= prediction.confidence and (prediction.confidence < high or high == 1.0)
        ]
        bands.append(Band(low, high, len(inside), sum(label == p.position_id for label, p in inside)))
    above = _at_or_above(pairs)
    return HeldOutMeasure(
        cards=len(labels),
        predicted=len(pairs),
        correct=sum(label == prediction.position_id for label, prediction in pairs),
        by_kind=tallies(lambda position_id: _kind(taxonomy, position_id), True),
        by_position=tallies(lambda position_id: position_id, False),
        bands=tuple(bands),
        at_or_above=above,
        confidence_at_target=_confidence_at_target(above, minimum_support),
        seen_in_training=sum(flag for _, _, flag in made),
        seen_in_training_correct=sum(flag and label == p.position_id for label, p, flag in made),
        unseen_at_or_above=_at_or_above([(label, p) for label, p, flag in made if not flag])
        if seen is not None
        else (),
    )


def _confidence_at_target(above: Sequence[Band], minimum_support: int) -> float | None:
    """The lowest grid point that meets the target, where every higher point with enough cards does too.

    A point with fewer than `minimum_support` cards above it is passed over, neither chosen nor failing.
    """
    found: float | None = None
    for band in reversed(above):
        if band.cards < minimum_support:
            continue
        if band.precision is None or band.precision < TARGET_PRECISION:
            break
        found = band.low
    return found


# ------------------------------------------------------------------------------------------------
# The comparison
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WouldPlace:
    """Cards of one standing no label covers, and how many the model would place at the threshold."""

    placement: str
    cards: int
    without_features: int
    """Cards with no feature the model knows: it places none of them."""
    at_threshold: int
    by_kind: tuple[tuple[str, int], ...]
    """At the threshold, by the predicted position's kind."""
    seen_in_training: int = 0
    """Cards whose features a labelled training card has exactly."""
    at_threshold_seen: int = 0
    """Of those at the threshold, the ones a training card has the features of."""


@dataclass(frozen=True, slots=True)
class Comparison:
    """One model's comparison: the split, what it was trained on, how it did, and what it would place."""

    without_placing_headings: bool
    seed: int
    documents: int
    held_out_documents: int
    trained_cards: int
    classes: int
    features: int
    held_out: HeldOutMeasure
    threshold: float | None
    """:attr:`HeldOutMeasure.confidence_at_target`, the confidence a wired stage would place from."""
    would_place: tuple[WouldPlace, ...]
    classifier: LocalClassifier = field(repr=False, compare=False)
    predictions: Mapping[str, Prediction | None] = field(repr=False, compare=False)
    """Every unlabelled card's prediction, by item id: what the sample is drawn from."""


def compare(
    taxonomy: Taxonomy,
    rows: Sequence[FeatureRow],
    *,
    seed: int = DEFAULT_SEED,
    minimum_teams: int = DEFAULT_MINIMUM_FEATURE_TEAMS,
    without_placing_headings: bool = False,
    minimum_support: int = DEFAULT_MINIMUM_SUPPORT,
) -> Comparison:
    """Split `rows` by document, train on nine tenths, measure on the tenth, and count what it would place."""
    ordered = sorted(rows, key=lambda row: row.item_id)
    held = held_out_documents((row.source_sha256 for row in ordered), seed)
    training = [row for row in ordered if row.source_sha256 not in held]
    classifier = LocalClassifier.train(
        training, seed=seed, minimum_teams=minimum_teams, without_placing_headings=without_placing_headings
    )
    known = frozenset(classifier.vocabulary)

    def features_of(row: FeatureRow) -> tuple[str, ...]:
        tokens = feature_tokens(row, without_placing_headings=without_placing_headings)
        return tuple(sorted(token for token in tokens if token in known))

    trained = {features_of(row) for row in training if row.label is not None}
    tested = [row for row in ordered if row.source_sha256 in held and row.label is not None]
    measure = measure_held_out(
        taxonomy,
        [row.label or "" for row in tested],
        classifier.predict(tested),
        seen=[features_of(row) in trained for row in tested],
        minimum_support=minimum_support,
    )
    unlabelled = [row for row in ordered if row.label is None]
    guesses = classifier.predict(unlabelled)
    threshold = measure.confidence_at_target
    standings: list[WouldPlace] = []
    for placement in (UNPLACED, DECIDED_NO_POSITION, BELOW_THRESHOLD):
        these = [
            (features_of(row) in trained, prediction)
            for row, prediction in zip(unlabelled, guesses, strict=True)
            if row.placement == placement
        ]
        placed = [
            (seen, prediction)
            for seen, prediction in these
            if prediction is not None and threshold is not None and prediction.confidence >= threshold
        ]
        kinds = Counter(_kind(taxonomy, prediction.position_id) for _, prediction in placed)
        standings.append(
            WouldPlace(
                placement=placement,
                cards=len(these),
                without_features=sum(prediction is None for _, prediction in these),
                at_threshold=len(placed),
                by_kind=tuple(sorted(kinds.items())),
                seen_in_training=sum(seen for seen, _ in these),
                at_threshold_seen=sum(seen for seen, _ in placed),
            )
        )
    return Comparison(
        without_placing_headings=without_placing_headings,
        seed=seed,
        documents=len({row.source_sha256 for row in ordered}),
        held_out_documents=len(held),
        trained_cards=classifier.trained_cards,
        classes=len(classifier.classes),
        features=len(classifier.vocabulary),
        held_out=measure,
        threshold=threshold,
        would_place=tuple(standings),
        classifier=classifier,
        predictions={row.item_id: prediction for row, prediction in zip(unlabelled, guesses, strict=True)},
    )


# ------------------------------------------------------------------------------------------------
# The coach sample
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SampleItem:
    """One sampled card: its row number in the coach's file, where it is, and what each model predicted."""

    sample_row: int
    item_id: str
    source_sha256: str
    stratum: str
    predictions: Mapping[str, Prediction | None]
    """Each compared model's prediction, by the model's name."""
    row: FeatureRow | None = field(default=None, repr=False, compare=False)
    """The card's row, for the coach's file; None once read back, since the sample keeps no text."""


@dataclass(frozen=True, slots=True)
class CoachSample:
    """The sampled cards, and what they were drawn from: each stratum's unplaced cards and each threshold."""

    stratified_by: str
    """The model whose confidence the strata are cut on."""
    thresholds: Mapping[str, float | None]
    """Each model's confidence at the target held-out precision."""
    populations: Mapping[str, int]
    """The unplaced cards the stratifying model predicts in each stratum, sampled or not."""
    items: tuple[SampleItem, ...]


def _strata_of(confidences: Sequence[float], threshold: float) -> Callable[[float], str]:
    """At or above the threshold; below it, the upper half by confidence (median included), then the rest."""
    below = sorted(one for one in confidences if one < threshold)
    median = below[len(below) // 2] if below else 0.0

    def stratum(confidence: float) -> str:
        if confidence >= threshold:
            return SAMPLE_STRATA[0][0]
        return SAMPLE_STRATA[1][0] if confidence >= median else SAMPLE_STRATA[2][0]

    return stratum


def coach_sample(
    taxonomy: Taxonomy,
    rows: Sequence[FeatureRow],
    comparisons: Mapping[str, Comparison],
    *,
    stratified_by: str,
    seed: int = DEFAULT_SEED,
) -> CoachSample:
    """Up to 60 unplaced cards for the coach to label, at most one per document, in a seeded order.

    The strata (:data:`SAMPLE_STRATA`) are cut on the `stratified_by` model's confidence: at or above
    its threshold (0.9 when none reaches the target), then the cards below it split at their median.
    Each stratum takes its share, one short of cards passing what it lacks to the next, and what the
    last cannot take goes back to the first that still has cards. Inside a
    stratum the predicted kinds take turns, largest first, and each kind's cards come in seeded-digest
    order. Only unplaced cards that model predicts are drawn.
    """
    model = comparisons[stratified_by]
    threshold = model.threshold if model.threshold is not None else _FALLBACK_THRESHOLD
    candidates = sorted(
        (row for row in rows if row.placement == UNPLACED and model.predictions.get(row.item_id) is not None),
        key=lambda row: (_digest(seed, row.item_id), row.item_id),
    )
    predicted = {row.item_id: cast(Prediction, model.predictions[row.item_id]) for row in candidates}
    stratum_of = _strata_of([one.confidence for one in predicted.values()], threshold)
    by_stratum: dict[str, dict[str, list[FeatureRow]]] = {
        name: defaultdict(list) for name, _ in SAMPLE_STRATA
    }
    for row in candidates:
        prediction = predicted[row.item_id]
        by_stratum[stratum_of(prediction.confidence)][_kind(taxonomy, prediction.position_id)].append(row)
    used: set[str] = set()
    chosen: list[tuple[str, FeatureRow]] = []
    carried = 0
    for name, share in SAMPLE_STRATA:
        taken = _take(by_stratum[name], share + carried, used)
        chosen += [(name, row) for row in taken]
        carried = share + carried - len(taken)
    for name, _ in SAMPLE_STRATA:
        if not carried:
            break
        left = {
            kind: [row for row in rows if row.source_sha256 not in used]
            for kind, rows in by_stratum[name].items()
        }
        taken = _take(left, carried, used)
        chosen += [(name, row) for row in taken]
        carried -= len(taken)
    ordered = sorted(chosen, key=lambda pair: (_digest(seed + 1, pair[1].item_id), pair[1].item_id))
    return CoachSample(
        stratified_by=stratified_by,
        thresholds={name: one.threshold for name, one in comparisons.items()},
        populations={name: sum(len(rows) for rows in by_stratum[name].values()) for name, _ in SAMPLE_STRATA},
        items=tuple(
            SampleItem(
                sample_row=number,
                item_id=row.item_id,
                source_sha256=row.source_sha256,
                stratum=name,
                predictions={
                    model_name: one.predictions.get(row.item_id) for model_name, one in comparisons.items()
                },
                row=row,
            )
            for number, (name, row) in enumerate(ordered, start=1)
        ),
    )


def _take(kinds: Mapping[str, list[FeatureRow]], wanted: int, used: set[str]) -> list[FeatureRow]:
    queues = {kind: list(rows) for kind, rows in kinds.items()}
    turn = sorted(queues, key=lambda kind: (-len(queues[kind]), kind))
    taken: list[FeatureRow] = []
    while len(taken) < wanted and any(queues.values()):
        for kind in turn:
            queue = queues[kind]
            while queue and queue[0].source_sha256 in used:
                queue.pop(0)
            if queue and len(taken) < wanted:
                row = queue.pop(0)
                used.add(row.source_sha256)
                taken.append(row)
    return taken


def heading_teams(rows: Iterable[FeatureRow]) -> dict[str, int]:
    """How many distinct teams' cards sit under each normalized heading."""
    teams: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for heading in row.headings:
            teams[heading].update(row.teams)
    return {heading: len(found) for heading, found in teams.items()}


def write_sample_csv(stream: TextIO, sample: CoachSample, teams_by_heading: Mapping[str, int]) -> None:
    """The coach's file: each card's row number, tag and headings, and empty `position` and `note`.

    The headings are the normalized ones the model read, outermost first; one fewer than two teams use
    is shown as :data:`WITHHELD_HEADING`. Nothing else: no prediction, confidence, stratum, path, school
    or team code.
    """
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(SAMPLE_COLUMNS)
    for item in sample.items:
        if item.row is None:
            raise ValueError("a sample read back holds no text to write")
        shown = [
            heading if teams_by_heading.get(heading, 0) >= _MINIMUM_SHOWN_HEADING_TEAMS else WITHHELD_HEADING
            for heading in item.row.headings
        ]
        writer.writerow((item.sample_row, item.row.tag or "", " > ".join(shown), "", ""))


def _prediction_json(prediction: Prediction | None) -> dict[str, object] | None:
    if prediction is None:
        return None
    return {"position_id": prediction.position_id, "confidence": prediction.confidence}


def _prediction_from(data: object) -> Prediction | None:
    if not isinstance(data, dict):
        return None
    found = cast(dict[str, Any], data)
    return Prediction(str(found["position_id"]), float(found["confidence"]))


def sample_lines(sample: CoachSample) -> list[str]:
    """What the sample keeps beside the coach's file, as JSON lines: a header, then each card's row number,
    item id and predictions. No heading, tag or team."""
    header = {
        "schema": SAMPLE_SCHEMA,
        "stratified_by": sample.stratified_by,
        "thresholds": dict(sample.thresholds),
        "populations": dict(sample.populations),
    }
    lines = [json.dumps(header, sort_keys=True, separators=(",", ":"))]
    lines += [
        json.dumps(
            {
                "sample_row": item.sample_row,
                "item_id": item.item_id,
                "source_sha256": item.source_sha256,
                "stratum": item.stratum,
                "predictions": {name: _prediction_json(one) for name, one in item.predictions.items()},
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        for item in sample.items
    ]
    return [line + "\n" for line in lines]


def read_sample(lines: Iterable[str]) -> CoachSample:
    """A sample :func:`sample_lines` wrote, its cards without rows. Raises `ValueError` on another schema."""
    read = iter(line for line in lines if line.strip())
    header = cast(dict[str, Any], json.loads(next(read, "{}")))
    if header.get("schema") != SAMPLE_SCHEMA:
        raise ValueError(f"not a {SAMPLE_SCHEMA} sample")
    items: list[SampleItem] = []
    for line in read:
        data = cast(dict[str, Any], json.loads(line))
        predictions = cast(dict[str, object], data["predictions"])
        items.append(
            SampleItem(
                sample_row=int(data["sample_row"]),
                item_id=str(data["item_id"]),
                source_sha256=str(data["source_sha256"]),
                stratum=str(data["stratum"]),
                predictions={str(name): _prediction_from(one) for name, one in predictions.items()},
            )
        )
    thresholds = cast(dict[str, object], header["thresholds"])
    populations = cast(dict[str, object], header["populations"])
    return CoachSample(
        stratified_by=str(header["stratified_by"]),
        thresholds={
            str(name): None if one is None else float(cast(float, one)) for name, one in thresholds.items()
        },
        populations={str(name): int(cast(int, one)) for name, one in populations.items()},
        items=tuple(items),
    )


def read_sample_labels(stream: TextIO, taxonomy: Taxonomy) -> dict[int, str]:
    """The coach's labels by row: a position id, or :data:`NO_POSITION_LABEL`. Blank and `unsure` are skipped.

    A label naming no active position of `taxonomy` is refused with its row number, never its text.
    """
    reader = csv.DictReader(stream)
    if reader.fieldnames is None or not {"sample_row", "position"} <= set(reader.fieldnames):
        raise ValueError("the labelled sample needs its sample_row and position columns")
    active = {position.id for position in taxonomy.active_positions}
    labels: dict[int, str] = {}
    for line in reader:
        label = (line.get("position") or "").strip()
        if not label or label.casefold() == _UNSURE_LABEL:
            continue
        row = int(line["sample_row"])
        if label.casefold() == NO_POSITION_LABEL:
            labels[row] = NO_POSITION_LABEL
        elif label in active:
            labels[row] = label
        else:
            raise ValueError(f"row {row} of the labelled sample names no active position of the taxonomy")
    return labels


@dataclass(frozen=True, slots=True)
class StratumScore:
    name: str
    labelled: int
    correct: int
    population: int | None = None
    """The unplaced cards of the stratum, sampled or not (strata only)."""

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.labelled if self.labelled else None


@dataclass(frozen=True, slots=True)
class SampleScore:
    """One model's accuracy on the coach's labels: in the sample, by stratum and kind, and weighted."""

    model: str
    labelled: int
    correct: int
    no_position: int
    """Labelled cards the coach said belong to no position: every one is a wrong placement."""
    by_stratum: tuple[StratumScore, ...]
    by_predicted_kind: tuple[StratumScore, ...]
    threshold: float | None
    at_threshold: StratumScore
    """The labelled cards it predicts at or above its own threshold, and the right ones among them."""
    weighted_accuracy: float | None
    """Accuracy over every unplaced card it predicts, each stratum weighted by its population."""
    weighted_precision_at_threshold: float | None
    """Precision over the unplaced cards it would place at its threshold, weighted the same way."""

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.labelled if self.labelled else None


def _weighted(
    sample: CoachSample, scored: Sequence[tuple[SampleItem, bool, bool]]
) -> tuple[float | None, float | None]:
    """`(accuracy, precision of the chosen)` over the population, from `(item, right, chosen)` triples."""
    labelled = Counter(item.stratum for item, _, _ in scored)
    weight = {name: sample.populations.get(name, 0) / count for name, count in labelled.items()}
    right = sum(weight[item.stratum] for item, correct, _ in scored if correct)
    total = sum(weight[item.stratum] for item, _, _ in scored)
    chosen_right = sum(weight[item.stratum] for item, correct, chosen in scored if correct and chosen)
    chosen = sum(weight[item.stratum] for item, _, chosen in scored if chosen)
    return (right / total if total else None, chosen_right / chosen if chosen else None)


def score_sample(
    taxonomy: Taxonomy, sample: CoachSample, labels: Mapping[int, str]
) -> tuple[SampleScore, ...]:
    """Each model's score on the coach's labels, in the order the sample names the models."""
    labelled_items = [item for item in sample.items if item.sample_row in labels]
    names = list(dict.fromkeys(name for item in sample.items for name in item.predictions))
    scores: list[SampleScore] = []
    for model in names:
        threshold = sample.thresholds.get(model)
        scored: list[tuple[SampleItem, bool, bool]] = []
        kinds: dict[str, list[bool]] = defaultdict(list)
        for item in labelled_items:
            prediction = item.predictions.get(model)
            right = prediction is not None and prediction.position_id == labels[item.sample_row]
            chosen = prediction is not None and threshold is not None and prediction.confidence >= threshold
            scored.append((item, right, chosen))
            kinds[_kind(taxonomy, prediction.position_id) if prediction else "no prediction"].append(right)
        strata = {
            name: [right for item, right, _ in scored if item.stratum == name] for name, _ in SAMPLE_STRATA
        }
        weighted_accuracy, weighted_precision = _weighted(sample, scored)
        chosen = [right for _, right, picked in scored if picked]
        scores.append(
            SampleScore(
                model=model,
                labelled=len(scored),
                correct=sum(right for _, right, _ in scored),
                no_position=sum(labels[item.sample_row] == NO_POSITION_LABEL for item in labelled_items),
                by_stratum=tuple(
                    StratumScore(name, len(found), sum(found), sample.populations.get(name, 0))
                    for name, found in strata.items()
                ),
                by_predicted_kind=tuple(
                    StratumScore(kind, len(found), sum(found)) for kind, found in sorted(kinds.items())
                ),
                threshold=threshold,
                at_threshold=StratumScore("at-threshold", len(chosen), sum(chosen)),
                weighted_accuracy=weighted_accuracy,
                weighted_precision_at_threshold=weighted_precision,
            )
        )
    return tuple(scores)

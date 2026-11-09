"""`config/daily_presets.yaml`, read and checked against what the presets name (v1-e08-t07).

:func:`load_daily_presets` reads the file into :class:`~debate_core.domain.daily_preset.DailyPresets`,
which checks its shape. :func:`check_daily_presets` then checks every preset against the rest of the
committed configuration, so a mistake is found when the file is loaded and not halfway through a
digest:

* each pair's argument is a taxonomy argument id (not an alias), and its need an id of that
  argument's family;
* the topic, when there is one, is a topic a search may name (the taxonomy's presets and the feed
  lists' `search_topics`);
* each provider is one this build has a name for, and a government provider only on a topic whose
  feed list enables it, because a search on any other topic never asks it (v1-e07-t07);
* each feed topic is a file in `config/feeds/`; the feed and Google News providers need at least one,
  and feed topics need one of them to read them.

Every preset in the file is checked, not only the one asked for, so adding a preset that does not
load fails every `daily` run until it is fixed, and the test over the committed file fails first.
A preset is added by adding it to the file; nothing here names one.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import yaml
from pydantic import ValidationError

from debate_core.application.settings import TOPIC_ENABLED_PROVIDERS, SearchProviderName
from debate_core.domain.argument_taxonomy import ArgumentTaxonomy
from debate_core.domain.daily_preset import DailyPreset, DailyPresets

__all__ = [
    "DAILY_PRESETS_PATH",
    "DailyPresetError",
    "PresetReferences",
    "check_daily_presets",
    "load_daily_presets",
]

DAILY_PRESETS_PATH: Final = Path("config") / "daily_presets.yaml"
"""Where the presets are committed, relative to the repository root or an installed build's copy."""

FEED_PROVIDERS: Final = frozenset({SearchProviderName.RSS.value, SearchProviderName.GOOGLE_NEWS.value})
"""The providers that read a preset's feed topics."""


class DailyPresetError(ValueError):
    """The presets file could not be read, or a preset in it names something that does not exist."""


@dataclass(frozen=True)
class PresetReferences:
    """What a preset may name, from the rest of the committed configuration."""

    taxonomy: ArgumentTaxonomy
    search_topics: Collection[str]
    """Every topic `search --topic` takes: the taxonomy's presets and the feed lists' `search_topics`."""
    feed_topics: Collection[str]
    """Every `config/feeds/` topic, by file name."""
    government_providers: Mapping[str, frozenset[str]] = field(default_factory=dict[str, frozenset[str]])
    """For each search topic, the government providers its feed lists enable."""


def load_daily_presets(path: Path) -> DailyPresets:
    """Read and check the shape of `path`; :class:`DailyPresetError` names the file and the problem."""
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise DailyPresetError(f"{path}: cannot be read: {error}") from error
    try:
        return DailyPresets.model_validate(document)
    except ValidationError as error:
        raise DailyPresetError(f"{path}: {error}") from error


def check_daily_presets(presets: DailyPresets, references: PresetReferences, *, source: str) -> DailyPresets:
    """`presets`, once every preset's names are found in `references`; otherwise the first problem."""
    for preset in presets.presets:
        problem = _problem(preset, references)
        if problem is not None:
            raise DailyPresetError(f"{source}: preset {preset.name!r}: {problem}")
    return presets


def _problem(preset: DailyPreset, references: PresetReferences) -> str | None:
    return (
        _pair_problem(preset, references.taxonomy)
        or _topic_problem(preset, references)
        or _provider_problem(preset, references)
        or _feed_problem(preset, references)
    )


def _pair_problem(preset: DailyPreset, taxonomy: ArgumentTaxonomy) -> str | None:
    for pair in preset.pairs:
        argument = taxonomy.find_argument(pair.argument)
        if argument is None or argument.id != pair.argument:
            known = f"; did you mean {argument.id!r}" if argument is not None else ""
            return f"the taxonomy has no argument with the id {pair.argument!r}{known}"
        needs = [need.id for need in taxonomy.family_of(argument).needs]
        if pair.need not in needs:
            return f"{pair.argument} has no need with the id {pair.need!r}; its needs are {', '.join(needs)}"
    return None


def _topic_problem(preset: DailyPreset, references: PresetReferences) -> str | None:
    if preset.topic is not None and preset.topic not in references.search_topics:
        return f"no search topic {preset.topic!r}; the topics are {', '.join(references.search_topics)}"
    return None


def _provider_problem(preset: DailyPreset, references: PresetReferences) -> str | None:
    known = [name.value for name in SearchProviderName]
    government = {name.value for name in TOPIC_ENABLED_PROVIDERS}
    for name in preset.providers:
        if name not in known:
            return f"no provider named {name!r}; the providers are {', '.join(known)}"
        if name in government:
            enabled = references.government_providers.get(preset.topic or "", frozenset())
            if name not in enabled:
                topic = preset.topic or "no topic"
                return f"{name} is asked only on a topic whose feed list enables it, and {topic} does not"
    return None


def _feed_problem(preset: DailyPreset, references: PresetReferences) -> str | None:
    for topic in preset.feed_topics:
        if topic not in references.feed_topics:
            known = ", ".join(references.feed_topics)
            return f"no feed topic {topic!r} in config/feeds/; the topics are {known}"
    reads_feeds = FEED_PROVIDERS.intersection(preset.providers)
    if reads_feeds and not preset.feed_topics:
        return f"{', '.join(sorted(reads_feeds))} reads feed topics, and the preset names none"
    if preset.feed_topics and not reads_feeds:
        return "feed_topics are read only by rss or google_news, and the preset asks neither"
    return None

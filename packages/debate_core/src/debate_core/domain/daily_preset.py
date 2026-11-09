"""A daily digest's preset: what `debate-research daily <preset>` searches for (v1-e08-t07).

`config/daily_presets.yaml` holds the presets. Each one names:

* `topic`: the debate topic it is for, as `search --topic` takes it (`policy-2026-27-nhi`), or none.
  The topic decides which government providers may be asked and fills the expansion's `{topic}`;
* `queries`: what the debater would type into `search`;
* `pairs`: the argument/need pairs each query is expanded for, which are also the digest's groups;
* `providers`: the discovery providers asked, by settings name;
* `feed_topics`: the feed lists in `config/feeds/` the feed and Google News providers read for this
  preset's run, and no others, so a politics digest never reads the health-insurance feeds (the PM's
  amendment of 2026-10-22).

This module is the file's shape alone. Whether an argument, a need, a topic, a provider or a feed
topic exists is the application's to check against the taxonomy, the settings' provider names and
the feed lists (:mod:`debate_core.application.daily_preset_config`), so a third preset added to the
file needs no code.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Final, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from debate_core.domain.argument_taxonomy import Slug
from debate_core.domain.base import DomainModel, NonEmptyText

__all__ = ["DAILY_PRESETS_SCHEMA_VERSION", "DailyPair", "DailyPreset", "DailyPresets"]

DAILY_PRESETS_SCHEMA_VERSION: Final = 1
"""The version of `config/daily_presets.yaml`'s shape."""

PresetName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
"""A preset's name, as `daily` takes it and as its digest files and seen-set are named: `politics`."""


class DailyPair(DomainModel):
    """One argument and need a preset's queries are expanded for: one group of the digest."""

    argument: Slug = Field(description="The taxonomy's argument id: `politics-da`. Not an alias.")
    need: Slug = Field(description="The need's id in that argument's family: `uniqueness`. Not an alias.")


def _duplicates(values: Sequence[object]) -> list[str]:
    seen: set[object] = set()
    repeated: list[str] = []
    for value in values:
        if value in seen:
            repeated.append(str(value))
        seen.add(value)
    return repeated


class DailyPreset(DomainModel):
    """One preset: the searches a daily digest runs, and where it looks."""

    name: PresetName = Field(description="What `daily` is given: `politics`, `nhi`.")
    label: NonEmptyText = Field(description="The preset as a heading says it: `Politics`.")
    description: NonEmptyText = Field(description="What the digest is for, for the coach reading the file.")
    topic: Slug | None = Field(
        default=None,
        description="The debate topic, as `search --topic` takes it (`policy-2026-27-nhi`), or none.",
    )
    queries: tuple[NonEmptyText, ...] = Field(
        min_length=1, description="What each search is for, as a debater would type it."
    )
    pairs: tuple[DailyPair, ...] = Field(
        min_length=1, description="The argument/need pairs each query is expanded for, in digest order."
    )
    providers: tuple[NonEmptyText, ...] = Field(
        min_length=1, description="The discovery providers asked, by settings name: `rss`, `openalex`."
    )
    feed_topics: tuple[PresetName, ...] = Field(
        default=(),
        description="The `config/feeds/` topics the feed and Google News providers read for this preset.",
    )
    max_results: int = Field(
        default=20, ge=1, le=200, description="The most results each of the preset's searches ranks."
    )

    @model_validator(mode="after")
    def _check_nothing_twice(self) -> Self:
        for field_name, values in (
            ("queries", self.queries),
            ("pairs", [(pair.argument, pair.need) for pair in self.pairs]),
            ("providers", self.providers),
            ("feed_topics", self.feed_topics),
        ):
            repeated = _duplicates(values)
            if repeated:
                raise ValueError(f"{field_name} lists {repeated[0]} twice")
        return self


class DailyPresets(DomainModel):
    """`config/daily_presets.yaml`: every preset `daily` knows, by name."""

    schema_version: Literal[1] = Field(description="The file's shape; 1.")
    presets: tuple[DailyPreset, ...] = Field(min_length=1, description="The presets, in listing order.")

    @model_validator(mode="after")
    def _check_names_are_unique(self) -> Self:
        repeated = _duplicates([preset.name for preset in self.presets])
        if repeated:
            raise ValueError(f"two presets are named {repeated[0]!r}")
        return self

    @property
    def names(self) -> tuple[str, ...]:
        """Every preset's name, in listing order: what an unknown name is answered with."""
        return tuple(preset.name for preset in self.presets)

    def find(self, name: str) -> DailyPreset | None:
        """The preset named exactly `name`, or None."""
        return next((preset for preset in self.presets if preset.name == name), None)

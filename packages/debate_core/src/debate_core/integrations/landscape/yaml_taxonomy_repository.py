"""`config/landscape/` read and checked as one configuration (`v1-e32-t01-position-taxonomy`).

The directory holds the coach's files::

    config/landscape/topics.yaml                       the topic map: topics and caselist ranges
    config/landscape/taxonomies/<topic id>.yaml        one topic's positions
    config/landscape/taxonomies/generic.yaml           format-level positions, merged in by event
    config/landscape/overrides/<topic id>.yaml         the coach's decisions on that topic's headings

:meth:`YamlTaxonomyRepository.load` reads every file at once and checks each on its own (the
models in :mod:`debate_core.domain.landscape`) and against the others:

* a taxonomy file's `topic_id` is its file's stem;
* every topic `topics.yaml` gives a `taxonomy_version` has a file, of that version and that event,
  and every file other than generic.yaml belongs to such a topic;
* each topic's positions, with generic.yaml's for its event, pass the taxonomy rules as one list,
  so an alias the two files both claim is refused here;
* an overrides file's `topic_id` is its file's stem, the topic has a taxonomy, and every decision
  names a position that taxonomy counts under (`v1-e32-t02`);
* a mapping that gives one key twice is an error rather than YAML's silent "last one wins", which
  would drop a coach's first list of aliases without a word.

Every failure is a :class:`~debate_core.application.ports.taxonomy_repository.TaxonomyConfigError`
naming the file. A `.yml` file is refused rather than skipped, since a skipped file is a position
list nobody counts against.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import ValidationError

from debate_core.application.ports.taxonomy_repository import (
    NoTaxonomyForTopic,
    ResolvedTopic,
    TaxonomyConfigError,
)
from debate_core.domain.landscape import GENERIC_TOPIC_ID, Taxonomy, TopicMap
from debate_core.domain.landscape_classification import OverrideRules

__all__ = [
    "GENERIC_FILE",
    "OVERRIDE_DIRECTORY",
    "TAXONOMY_DIRECTORY",
    "TOPICS_FILE",
    "YamlTaxonomyRepository",
    "load_override_file",
    "load_taxonomy_file",
    "load_topic_map",
    "render_override_file",
]

TOPICS_FILE: Final = "topics.yaml"
TAXONOMY_DIRECTORY: Final = "taxonomies"
OVERRIDE_DIRECTORY: Final = "overrides"
GENERIC_FILE: Final = f"{GENERIC_TOPIC_ID}.yaml"


class _UniqueKeyLoader(yaml.SafeLoader):
    """YAML's safe loader, except that a mapping giving one key twice is an error."""


def _construct_unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    seen: set[object] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node)  # pyright: ignore[reportUnknownMemberType]
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"the key {key!r} is given twice", key_node.start_mark
            )
        seen.add(key)
    return loader.construct_mapping(node)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def _read(path: Path) -> object:
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)  # noqa: S506
    except (OSError, UnicodeDecodeError) as error:
        raise TaxonomyConfigError(str(path), f"cannot be read: {error}") from error
    except yaml.YAMLError as error:
        raise TaxonomyConfigError(str(path), f"is not valid YAML: {error}") from error


def load_topic_map(path: Path) -> TopicMap:
    """Read and check `topics.yaml` alone, for a caller that needs no taxonomy (the seeding script)."""
    try:
        return TopicMap.model_validate(_read(path))
    except ValidationError as error:
        raise TaxonomyConfigError(str(path), str(error)) from error


def load_taxonomy_file(path: Path) -> Taxonomy:
    """Read and check one taxonomy file on its own; its `topic_id` must be the file's stem."""
    try:
        taxonomy = Taxonomy.model_validate(_read(path))
    except ValidationError as error:
        raise TaxonomyConfigError(str(path), str(error)) from error
    if taxonomy.topic_id != path.stem:
        raise TaxonomyConfigError(
            str(path), f"its topic_id is {taxonomy.topic_id}, but the file is named for {path.stem}"
        )
    return taxonomy


def load_override_file(path: Path) -> OverrideRules:
    """Read and check one overrides file on its own; its `topic_id` must be the file's stem."""
    try:
        rules = OverrideRules.model_validate(_read(path))
    except ValidationError as error:
        raise TaxonomyConfigError(str(path), str(error)) from error
    if rules.topic_id != path.stem:
        raise TaxonomyConfigError(
            str(path), f"its topic_id is {rules.topic_id}, but the file is named for {path.stem}"
        )
    return rules


_OVERRIDE_HEADER: Final = """\
# The coach's decisions from the landscape review queue: each heading, as the normalizer writes it,
# and the position it names, or null for a heading that names no position. Written by
# scripts/classify_landscape_positions.py apply-decisions; docs/guides/landscape-taxonomy.md says how.
# The matcher reads these before the taxonomy's aliases. No team, school or person is named here.
"""


def render_override_file(rules: OverrideRules) -> str:
    """The YAML an overrides file holds for `rules`, header comment first; what `load_override_file` reads."""
    document = rules.model_dump(mode="json")
    return _OVERRIDE_HEADER + yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)


class YamlTaxonomyRepository:
    """The topic map, every topic's merged taxonomy and its overrides, read from one `config/landscape/`."""

    def __init__(
        self,
        topic_map: TopicMap,
        taxonomies: Mapping[str, Taxonomy],
        overrides: Mapping[str, OverrideRules] | None = None,
    ) -> None:
        self._topic_map = topic_map
        self._taxonomies = dict(taxonomies)
        self._overrides = dict(overrides or {})

    @classmethod
    def load(cls, directory: Path) -> YamlTaxonomyRepository:
        """Read and check every file under `directory`; the error names the first bad file."""
        topic_map = load_topic_map(directory / TOPICS_FILE)
        taxonomy_directory = directory / TAXONOMY_DIRECTORY
        paths = sorted(taxonomy_directory.iterdir()) if taxonomy_directory.is_dir() else []
        for path in paths:
            if path.suffix == ".yml":
                raise TaxonomyConfigError(
                    str(path), "a taxonomy file ends in .yaml; this one would be skipped"
                )
        files = {path.stem: (path, load_taxonomy_file(path)) for path in paths if path.suffix == ".yaml"}
        generic = files.pop(GENERIC_TOPIC_ID, None)
        versioned = {topic.id: topic for topic in topic_map.topics if topic.taxonomy_version is not None}
        for stem, (path, _) in files.items():
            if stem not in versioned:
                raise TaxonomyConfigError(
                    str(path),
                    f"no topic in {TOPICS_FILE} gives {stem} a taxonomy_version, so nothing reads it",
                )
        merged: dict[str, Taxonomy] = {}
        for topic in versioned.values():
            if topic.id not in files:
                raise TaxonomyConfigError(
                    str(directory / TOPICS_FILE),
                    f"{topic.id} names taxonomy_version {topic.taxonomy_version}, "
                    f"but {TAXONOMY_DIRECTORY}/{topic.id}.yaml does not exist",
                )
            path, own = files[topic.id]
            if own.taxonomy_version != topic.taxonomy_version:
                raise TaxonomyConfigError(
                    str(path),
                    f"is version {own.taxonomy_version}, but {TOPICS_FILE} names {topic.taxonomy_version}; "
                    "a version bump changes both",
                )
            if own.event is not topic.event:
                raise TaxonomyConfigError(
                    str(path), f"is for {own.event}, but {TOPICS_FILE} puts {topic.id} in {topic.event.value}"
                )
            try:
                merged[topic.id] = own.with_generic(generic[1]) if generic is not None else own
            except ValidationError as error:
                raise TaxonomyConfigError(str(path), f"with {GENERIC_FILE} merged in: {error}") from error
        return cls(topic_map, merged, _load_overrides(directory / OVERRIDE_DIRECTORY, merged))

    def topic_map(self) -> TopicMap:
        return self._topic_map

    def taxonomy(self, topic_id: str) -> Taxonomy:
        try:
            return self._taxonomies[topic_id]
        except KeyError:
            raise NoTaxonomyForTopic(topic_id) from None

    def overrides(self, topic_id: str) -> OverrideRules:
        if topic_id not in self._taxonomies:
            raise NoTaxonomyForTopic(topic_id)
        return self._overrides.get(topic_id, OverrideRules(topic_id=topic_id))

    def resolve(self, caselist: str, snapshot: date) -> ResolvedTopic | None:
        found = self._topic_map.resolve(caselist, snapshot)
        if found is None:
            return None
        return ResolvedTopic(
            topic=self._topic_map.topic(found.topic_id), taxonomy=self._taxonomies.get(found.topic_id)
        )


def _load_overrides(directory: Path, taxonomies: Mapping[str, Taxonomy]) -> dict[str, OverrideRules]:
    """Every overrides file, each checked against its topic's merged taxonomy."""
    paths = sorted(directory.iterdir()) if directory.is_dir() else []
    found: dict[str, OverrideRules] = {}
    for path in paths:
        if path.suffix != ".yaml":
            raise TaxonomyConfigError(str(path), "an overrides file ends in .yaml; this one would be skipped")
        rules = load_override_file(path)
        taxonomy = taxonomies.get(rules.topic_id)
        if taxonomy is None:
            raise TaxonomyConfigError(
                str(path), f"no topic in {TOPICS_FILE} gives {rules.topic_id} a taxonomy, so nothing reads it"
            )
        try:
            rules.check_against(taxonomy)
        except ValueError as error:
            raise TaxonomyConfigError(str(path), str(error)) from error
        found[rules.topic_id] = rules
    return found

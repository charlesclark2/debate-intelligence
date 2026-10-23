"""`config/landscape/` read and checked as one configuration (`v1-e32-t01-position-taxonomy`).

The directory holds the coach's files::

    config/landscape/topics.yaml                       the topic map: topics and caselist ranges
    config/landscape/taxonomies/<topic id>.yaml        one topic's positions
    config/landscape/taxonomies/generic.yaml           format-level positions, merged in by event

:meth:`YamlTaxonomyRepository.load` reads every file at once and checks each on its own (the
models in :mod:`debate_core.domain.landscape`) and against the others:

* a taxonomy file's `topic_id` is its file's stem;
* every topic `topics.yaml` gives a `taxonomy_version` has a file, of that version and that event,
  and every file other than generic.yaml belongs to such a topic;
* each topic's positions, with generic.yaml's for its event, pass the taxonomy rules as one list,
  so an alias the two files both claim is refused here;
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

__all__ = [
    "GENERIC_FILE",
    "TAXONOMY_DIRECTORY",
    "TOPICS_FILE",
    "YamlTaxonomyRepository",
    "load_taxonomy_file",
    "load_topic_map",
]

TOPICS_FILE: Final = "topics.yaml"
TAXONOMY_DIRECTORY: Final = "taxonomies"
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


class YamlTaxonomyRepository:
    """The topic map and every topic's merged taxonomy, read from one `config/landscape/` directory."""

    def __init__(self, topic_map: TopicMap, taxonomies: Mapping[str, Taxonomy]) -> None:
        self._topic_map = topic_map
        self._taxonomies = dict(taxonomies)

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
        return cls(topic_map, merged)

    def topic_map(self) -> TopicMap:
        return self._topic_map

    def taxonomy(self, topic_id: str) -> Taxonomy:
        try:
            return self._taxonomies[topic_id]
        except KeyError:
            raise NoTaxonomyForTopic(topic_id) from None

    def resolve(self, caselist: str, snapshot: date) -> ResolvedTopic | None:
        found = self._topic_map.resolve(caselist, snapshot)
        if found is None:
            return None
        return ResolvedTopic(
            topic=self._topic_map.topic(found.topic_id), taxonomy=self._taxonomies.get(found.topic_id)
        )

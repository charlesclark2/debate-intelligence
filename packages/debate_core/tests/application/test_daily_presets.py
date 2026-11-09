"""`config/daily_presets.yaml`: every preset validates on load, and a new one needs no code (v1-e08-t07).

The committed file is loaded and checked against the committed taxonomy and feed lists, as the
container does. An invented third preset, written into a copy of the file, loads with no code change.
Each refusal below is one mistake a coach editing the file could make, with the words it is refused in.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import pytest
import yaml

from debate_core.application.daily_preset_config import (
    DAILY_PRESETS_PATH,
    DailyPresetError,
    PresetReferences,
    check_daily_presets,
    load_daily_presets,
)
from debate_core.application.query_expansion import ARGUMENT_TAXONOMY_PATH, load_argument_taxonomy
from debate_core.domain.daily_preset import DailyPair, DailyPresets
from debate_core.integrations.discovery.feed_config import (
    load_feed_directory,
    search_topic_ids,
    topic_providers,
)

REPOSITORY: Final = Path(__file__).resolve().parents[4]
TAXONOMY: Final = load_argument_taxonomy(REPOSITORY / ARGUMENT_TAXONOMY_PATH)
FEED_LISTS: Final = load_feed_directory(REPOSITORY / "config" / "feeds")


def committed_references() -> PresetReferences:
    """What the container checks the presets against: the committed taxonomy and feed lists."""
    return PresetReferences(
        taxonomy=TAXONOMY,
        search_topics=tuple(
            dict.fromkeys((*(topic.id for topic in TAXONOMY.topics), *search_topic_ids(FEED_LISTS)))
        ),
        feed_topics=tuple(config.topic for config in FEED_LISTS),
        government_providers=topic_providers(FEED_LISTS),
    )


def committed_document() -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load((REPOSITORY / DAILY_PRESETS_PATH).read_text(encoding="utf-8"))
    return document


def loaded(document: dict[str, Any], tmp_path: Path) -> DailyPresets:
    path = tmp_path / "daily_presets.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return check_daily_presets(load_daily_presets(path), committed_references(), source=str(path))


def test_the_committed_presets_validate_against_the_committed_taxonomy_and_feed_lists() -> None:
    presets = check_daily_presets(
        load_daily_presets(REPOSITORY / DAILY_PRESETS_PATH), committed_references(), source="committed"
    )

    assert presets.names == ("politics", "nhi")
    politics = presets.find("politics")
    assert politics is not None
    assert politics.topic is None
    assert politics.feed_topics == ("politics",)
    assert politics.providers == ("rss",)
    assert politics.pairs == (
        DailyPair(argument="politics-da", need="uniqueness"),
        DailyPair(argument="midterms-da", need="uniqueness"),
    )
    nhi = presets.find("nhi")
    assert nhi is not None
    assert (nhi.topic, nhi.feed_topics) == ("policy-2026-27-nhi", ("health-insurance",))


def test_an_invented_third_preset_loads_with_no_code_change(tmp_path: Path) -> None:
    document = committed_document()
    document["presets"].append(
        {
            "name": "ld-de-extinction",
            "label": "LD de-extinction",
            "description": "An invented preset the coach might add for the LD topic.",
            "topic": "ld-2026-nov-dec-de-extinction",
            "queries": ["de-extinction"],
            "pairs": [{"argument": "economy-da", "need": "impact"}],
            "providers": ["openalex"],
            "max_results": 5,
        }
    )

    presets = loaded(document, tmp_path)

    assert presets.names == ("politics", "nhi", "ld-de-extinction")
    invented = presets.find("ld-de-extinction")
    assert invented is not None
    assert (invented.topic, invented.queries, invented.max_results) == (
        "ld-2026-nov-dec-de-extinction",
        ("de-extinction",),
        5,
    )


def preset(**changes: Any) -> dict[str, Any]:
    """A preset that loads, with `changes` applied: a value of None removes the key."""
    entry: dict[str, Any] = {
        "name": "invented",
        "label": "Invented",
        "description": "A preset for a refusal test.",
        "queries": ["bill"],
        "pairs": [{"argument": "politics-da", "need": "uniqueness"}],
        "providers": ["rss"],
        "feed_topics": ["politics"],
    }
    entry.update(changes)
    return {key: value for key, value in entry.items() if value is not None}


def test_the_refusal_test_preset_itself_loads(tmp_path: Path) -> None:
    assert loaded({"schema_version": 1, "presets": [preset()]}, tmp_path).names == ("invented",)


@pytest.mark.parametrize(
    ("changes", "words"),
    [
        ({"pairs": [{"argument": "nonsense-da", "need": "link"}]}, "no argument with the id 'nonsense-da'"),
        ({"pairs": [{"argument": "ptx", "need": "link"}]}, "did you mean 'politics-da'"),
        ({"pairs": [{"argument": "politics-da", "need": "uq"}]}, "politics-da has no need with the id 'uq'"),
        (
            {"pairs": [{"argument": "util", "need": "uniqueness"}]},
            "util has no need with the id 'uniqueness'",
        ),
        ({"topic": "policy-2031-nonsense"}, "no search topic 'policy-2031-nonsense'"),
        ({"providers": ["rss", "altavista"]}, "no provider named 'altavista'"),
        ({"providers": ["rss", "govinfo"]}, "govinfo is asked only on a topic whose feed list enables it"),
        ({"feed_topics": ["space"]}, "no feed topic 'space' in config/feeds/"),
        ({"feed_topics": None}, "rss reads feed topics, and the preset names none"),
        ({"providers": ["openalex"]}, "feed_topics are read only by rss or google_news"),
    ],
)
def test_a_preset_naming_what_does_not_exist_fails_the_load_naming_it(
    changes: dict[str, Any], words: str, tmp_path: Path
) -> None:
    document = {"schema_version": 1, "presets": [preset(), preset(name="broken", **changes)]}

    with pytest.raises(DailyPresetError, match="preset 'broken'") as refused:
        loaded(document, tmp_path)

    assert words in str(refused.value)


@pytest.mark.parametrize(
    ("document", "words"),
    [
        ({"schema_version": 1, "presets": [preset(), preset()]}, "two presets are named 'invented'"),
        ({"schema_version": 1, "presets": [preset(queries=["bill", "bill"])]}, "queries lists bill twice"),
        ({"schema_version": 1, "presets": [preset(goggle_news=True)]}, "goggle_news"),
        ({"schema_version": 1, "presets": [preset(name="Politics")]}, "name"),
        ({"schema_version": 1, "presets": [preset(queries=[])]}, "queries"),
        ({"schema_version": 2, "presets": [preset()]}, "schema_version"),
        ({"schema_version": 1, "presets": []}, "presets"),
    ],
)
def test_a_file_of_the_wrong_shape_fails_the_load_naming_the_file(
    document: dict[str, Any], words: str, tmp_path: Path
) -> None:
    with pytest.raises(DailyPresetError, match="daily_presets.yaml") as refused:
        loaded(document, tmp_path)

    assert words in str(refused.value)


def test_a_file_that_is_not_yaml_fails_the_load_naming_the_file(tmp_path: Path) -> None:
    path = tmp_path / "daily_presets.yaml"
    path.write_text("presets: [unclosed\n", encoding="utf-8")

    with pytest.raises(DailyPresetError, match="daily_presets.yaml: cannot be read"):
        load_daily_presets(path)

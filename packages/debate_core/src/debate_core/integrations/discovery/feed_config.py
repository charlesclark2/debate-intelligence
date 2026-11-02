"""The coach's per-topic feed lists, `config/feeds/<topic>.yaml`, read and checked (v1-e07-t05).

One file per topic names the publisher RSS and Atom feeds the
:class:`~debate_core.integrations.discovery.feeds.FeedProvider` reads for it, and whether the
:class:`~debate_core.integrations.discovery.google_news_rss.GoogleNewsRssProvider` may search Google
News for it. The lists are the coach's: the files in the repository are a starter set, and every feed
in them says whether the coach has reviewed it yet (:class:`FeedReview`). A feed URL is never
"verified" by being listed here; the operator's feed check
(:mod:`~debate_core.integrations.discovery.feed_check`) is what shows that one answers.

A file is checked when it is read, and a mistake fails the load with the file and the field named:
an unknown key (a misspelled `goggle_news:`), a feed URL that is not absolute http(s), the same feed
listed twice, or a `topic:` that is not the file's own name. :func:`load_feed_directory` reads every
`*.yaml` in a directory, so a topic is added by adding a file.

A file can also name the debate topics it applies to (`search_topics`, the ids `search --topic` takes)
and the government providers a search on one of them asks (`government_providers`): the Federal
Register and GovInfo run only for a search whose topic lists them, never for every search
(v1-e07-t07; :data:`~debate_core.application.settings.TOPIC_ENABLED_PROVIDERS`).
:func:`topic_providers` and :func:`search_topic_ids` read them for the search.

Google News is off unless a topic turns it on (`google_news.enabled: true`), because the publisher URL
of a Google News item can rarely be resolved without asking Google, which this platform does not do
(PM ruling 2026-10-22); see :mod:`~debate_core.integrations.discovery.google_news_rss`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Final, Self
from urllib.parse import urlsplit

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, model_validator

from debate_core.application.settings import TOPIC_ENABLED_PROVIDERS, SearchProviderName

__all__ = [
    "FeedConfig",
    "FeedConfigError",
    "FeedReview",
    "FeedSource",
    "GoogleNewsConfig",
    "feeds_of",
    "load_feed_config",
    "load_feed_directory",
    "search_topic_ids",
    "topic_providers",
]

TOPIC_NAME: Final = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
"""A topic's name, which is also its file's stem: lowercase words joined by hyphens."""


class FeedConfigError(ValueError):
    """A feed list could not be read or failed its checks; the message names the file."""


class FeedReview(StrEnum):
    """Whether the coach has looked at a listed feed and kept it."""

    AWAITING_COACH_REVIEW = "awaiting_coach_review"
    """Listed as a starting point; the coach has not yet decided to keep it."""

    COACH_REVIEWED = "coach_reviewed"
    """The coach has reviewed the feed and kept it on the topic."""


def _feed_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc or any(c.isspace() for c in value):
        raise ValueError(f"a feed URL must be an absolute http(s) URL with no spaces, got {value!r}")
    return value


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class FeedSource(_ConfigModel):
    """One publisher feed on a topic."""

    url: Annotated[str, AfterValidator(_feed_url)] = Field(description="The RSS or Atom feed's URL.")
    publisher: str = Field(
        min_length=1, description="The outlet's name, as a candidate's `publication` reports it."
    )
    review: FeedReview = Field(description="Whether the coach has reviewed this feed yet.")


class GoogleNewsConfig(_ConfigModel):
    """Whether, and in which edition, Google News is searched for this topic."""

    enabled: bool = Field(default=False, description="Search Google News for this topic. Off by default.")
    language: str = Field(default="en-US", min_length=2, description="Google News `hl`: interface language.")
    country: str = Field(default="US", min_length=2, description="Google News `gl`: the edition's country.")
    edition: str = Field(default="US:en", min_length=4, description="Google News `ceid`: country:language.")


class FeedConfig(_ConfigModel):
    """One topic's feed list: `config/feeds/<topic>.yaml`."""

    topic: str = Field(pattern=TOPIC_NAME.pattern, description="The topic's name; the file's stem.")
    description: str = Field(min_length=1, description="What the topic is, for the coach reading the file.")
    feeds: tuple[FeedSource, ...] = Field(default=(), description="The publisher feeds read for this topic.")
    google_news: GoogleNewsConfig = Field(
        default_factory=GoogleNewsConfig, description="Google News search for this topic; off by default."
    )
    search_topics: tuple[Annotated[str, Field(pattern=TOPIC_NAME.pattern)], ...] = Field(
        default=(),
        description=(
            "The debate topics this file applies to, as a search names them with --topic "
            "(`policy-2026-27-nhi`); v1-e07-t07."
        ),
    )
    government_providers: tuple[SearchProviderName, ...] = Field(
        default=(),
        description="The government providers a search on one of `search_topics` asks (v1-e07-t07).",
    )

    @model_validator(mode="after")
    def _check_the_government_providers(self) -> Self:
        others = [name.value for name in self.government_providers if name not in TOPIC_ENABLED_PROVIDERS]
        if others:
            allowed = ", ".join(sorted(name.value for name in TOPIC_ENABLED_PROVIDERS))
            raise ValueError(
                f"government_providers lists {', '.join(others)}; only government providers are enabled "
                f"per topic ({allowed}), every other one by providers.enabled alone"
            )
        if len(set(self.government_providers)) != len(self.government_providers):
            raise ValueError("government_providers lists a provider twice")
        if self.government_providers and not self.search_topics:
            raise ValueError("government_providers is set but there are no search_topics for them to run on")
        if len(set(self.search_topics)) != len(self.search_topics):
            raise ValueError("search_topics lists a topic twice")
        return self

    @model_validator(mode="after")
    def _check_no_feed_twice(self) -> Self:
        seen: set[str] = set()
        for feed in self.feeds:
            if feed.url in seen:
                raise ValueError(f"the feed {feed.url!r} is listed twice")
            seen.add(feed.url)
        return self


def load_feed_config(path: Path) -> FeedConfig:
    """Read and check one topic file; :class:`FeedConfigError` names the file and what is wrong."""
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise FeedConfigError(f"{path}: cannot be read: {error}") from error
    try:
        config = FeedConfig.model_validate(document)
    except ValidationError as error:
        raise FeedConfigError(f"{path}: {error}") from error
    if config.topic != path.stem:
        raise FeedConfigError(f"{path}: topic {config.topic!r} does not match the file name {path.stem!r}")
    return config


def load_feed_directory(directory: Path) -> tuple[FeedConfig, ...]:
    """Every topic file in `directory` (`*.yaml`), checked, in file-name order."""
    if not directory.is_dir():
        raise FeedConfigError(f"{directory}: no such feed directory")
    return tuple(load_feed_config(path) for path in sorted(directory.glob("*.yaml")))


def feeds_of(topics: Sequence[FeedConfig]) -> tuple[FeedSource, ...]:
    """Every feed on `topics`, each URL once, in topic and then listing order."""
    seen: dict[str, FeedSource] = {}
    for topic in topics:
        for feed in topic.feeds:
            seen.setdefault(feed.url, feed)
    return tuple(seen.values())


def topic_providers(topics: Sequence[FeedConfig]) -> dict[str, frozenset[str]]:
    """Each debate topic the files name, with the government providers a search on it asks.

    Joined across files: two files naming one topic give it the providers of both. A topic a file names
    with no government providers is there with none.
    """
    enabled: dict[str, set[str]] = {}
    for config in topics:
        for topic in config.search_topics:
            enabled.setdefault(topic, set()).update(name.value for name in config.government_providers)
    return {topic: frozenset(names) for topic, names in enabled.items()}


def search_topic_ids(topics: Sequence[FeedConfig]) -> tuple[str, ...]:
    """Every debate topic the files name, each once, in file and then listing order."""
    return tuple(dict.fromkeys(topic for config in topics for topic in config.search_topics))

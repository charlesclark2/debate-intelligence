"""How many feed items a daily digest's queries keep, query by query, as counts (v1-e08-t25).

Run with the installed build's Python, from the home folder, on this script in a checkout
(docs/guides/daily-digests.md, "Counting a template before adding it"):

    "$(uv tool dir)/debate-cli/bin/python" -I <checkout>/scripts/count_digest_feed_matches.py politics \
        --candidate "midterms-da/uniqueness={query} polls"

It rebuilds the preset's searches with the build's own code: the preset from the bundled
`config/daily_presets.yaml`, each query expanded for each pair by the bundled taxonomy
(`expand_with_templates`), and the preset's feed lists from the bundled `config/feeds/`. It reads each
of the preset's feeds once, through the build's own `FeedFetcher` and `feed_client` (the User-Agent,
redirects and size limit a digest uses), into an in-memory cache, so no conditional headers go out and
nothing is written: not the feed cache in `<data dir>/feeds/`, not the seen-set, not the SQLite file.

Two windows, both ending at the run: the 24 hours before it, and the 72 hours before it. For each it
prints:

* per feed: the entries it lists (each link once across the feeds, as the provider counts them), how
  many have no date, and how many fall in each window;
* per filled query, by its template id, its pair and the preset query it was filled with:
  `every_word`, the items today's rule keeps (every word of the filled template in the title or
  summary); `own_words`, the items kept if only the preset query's own words were required; and
  `own_plus_one`, kept if the query's own words and at least one of the template's other words were;
* per digest template `daily` asks (`digest/...`, `config/daily_templates.yaml`, v1-e08-t25), for
  the queries it is asked for, the items the every-word rule keeps: the build's own file, or this
  checkout's when the build predates it (the first line says which). A pair with no digest
  templates is counted as `daily` asks it, by the taxonomy's templates (the PM's ruling C);
* per `--candidate PAIR=TEMPLATE` (`candidate/...`, any number), a template not yet in the file,
  counted for every preset query of the pair, under the every-word rule;
* per pair and for the whole digest, the distinct items any of its queries keeps under each rule.

The counts are before the search's `max_results` cut (20 for each search). A feed that fails is
named by its publisher and the kind of failure (`HTTP 404`, `timed out`). Nothing else is printed:
never a title, a summary, a link or any other text of a feed item.

`--offline` reads one made-up feed for every feed URL instead of the network, to check the script.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import yaml

from debate_cli import package_version
from debate_cli.build_info import bundled_config_root, settings_loader
from debate_core.application.daily_preset_config import DAILY_PRESETS_PATH, load_daily_presets
from debate_core.application.errors import ProviderError
from debate_core.application.federated_search_types import ExpansionRequest, SearchRequest
from debate_core.application.query_expansion import (
    ARGUMENT_TAXONOMY_PATH,
    expand_with_templates,
    load_argument_taxonomy,
)
from debate_core.application.settings import HttpSettings, find_repository_root
from debate_core.domain import SearchFilters
from debate_core.domain.daily_preset import DailyPair, DailyPreset
from debate_core.integrations.discovery.feed_cache import InMemoryFeedCache
from debate_core.integrations.discovery.feed_config import FeedSource, feeds_of, load_feed_directory
from debate_core.integrations.discovery.feed_parsing import FeedEntry
from debate_core.integrations.discovery.feeds import (
    CONCURRENT_FETCHES,
    MAX_FEED_BYTES,
    PROVIDER_NAME,
    FeedFetcher,
    feed_client,
    in_window,
    matches_terms,
    query_terms,
)

FEEDS_DIRECTORY = Path("config") / "feeds"

WINDOWS: tuple[tuple[str, timedelta], ...] = (("24h", timedelta(hours=24)), ("72h", timedelta(hours=72)))
"""The two windows, each ending at the run."""

DAILY_TEMPLATES = Path("config") / "daily_templates.yaml"
"""The digest templates `daily` asks (v1-e08-t25), read as plain YAML so a build that predates them runs."""


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Row:
    """One filled query: what it is, and the terms each rule requires of an item."""

    kind: str
    """`taxonomy` for the taxonomy's templates (what `search` asks), `digest` for what `daily` asks,
    `candidate` for a template given with `--candidate`."""
    pair: str
    preset_query: str
    template_id: str
    template: str
    every_word: tuple[str, ...]
    own_words: tuple[str, ...]
    template_words: tuple[str, ...]


def own_plus_one(entry: FeedEntry, row: Row) -> bool:
    """The query's own words, and at least one of the template's other words."""
    if not matches_terms(entry, row.own_words):
        return False
    return not row.template_words or any(matches_terms(entry, (word,)) for word in row.template_words)


RULES: tuple[tuple[str, Callable[[FeedEntry, Row], bool]], ...] = (
    ("every_word", lambda entry, row: matches_terms(entry, row.every_word)),
    ("own_words", lambda entry, row: matches_terms(entry, row.own_words)),
    ("own_plus_one", own_plus_one),
)


def pair_name(pair: DailyPair) -> str:
    return f"{pair.argument}/{pair.need}"


def config_root(offline: bool) -> Path:
    root = bundled_config_root()
    if root is not None:
        return root
    if offline:
        checkout = find_repository_root(Path(__file__).resolve().parent)
        if checkout is not None:
            return checkout
    sys.exit("STOP: this Python is not an installed build (no bundled config); run it with the tool's Python")


def digest_groups(root: Path) -> tuple[str, dict[str, list[dict[str, object]]]]:
    """Where the digest templates came from (`build`, `checkout` or `none`), and each pair's templates."""
    checkout = find_repository_root(Path(__file__).resolve().parent)
    for base in (root, checkout):
        if base is not None and (base / DAILY_TEMPLATES).is_file():
            where = "checkout" if base == checkout else "build"
            document = yaml.safe_load((base / DAILY_TEMPLATES).read_text(encoding="utf-8")) or {}
            groups = {
                f"{g['argument']}/{g['need']}": list(g["templates"]) for g in document.get("groups") or []
            }
            return where, groups
    return "none", {}


def template_row(kind: str, pair: str, preset_query: str, template_id: str, template: str) -> Row:
    own = query_terms(preset_query)
    terms = query_terms(template.replace("{query}", preset_query))
    return Row(
        kind, pair, preset_query, template_id, template, terms, own, tuple(t for t in terms if t not in own)
    )


def the_rows(
    root: Path,
    preset: DailyPreset,
    digest: dict[str, list[dict[str, object]]],
    candidates: list[tuple[str, str]],
) -> list[Row]:
    """The preset's filled queries: the taxonomy's, then the digest templates', then the candidates'."""
    taxonomy = load_argument_taxonomy(root / ARGUMENT_TAXONOMY_PATH)
    rows: list[Row] = []
    for pair in preset.pairs:
        for preset_query in preset.queries:
            own = query_terms(preset_query)
            request = SearchRequest(
                query=preset_query,
                filters=SearchFilters(max_results=preset.max_results),
                providers=preset.providers,
                expansion=ExpansionRequest(argument=pair.argument, need=pair.need, topic_id=preset.topic),
                topic_id=preset.topic,
            )
            expansion = expand_with_templates(taxonomy, request, now=datetime.now(UTC))
            for expanded in expansion.queries:
                terms = query_terms(expanded.query)
                rows.append(
                    Row(
                        kind="taxonomy",
                        pair=pair_name(pair),
                        preset_query=preset_query,
                        template_id=expanded.template_id or "model",
                        template=expanded.template or "",
                        every_word=terms,
                        own_words=own,
                        template_words=tuple(dict.fromkeys(term for term in terms if term not in own)),
                    )
                )
            name = pair_name(pair)
            if name not in digest:
                taxonomys = [
                    r for r in rows if (r.kind, r.pair, r.preset_query) == ("taxonomy", name, preset_query)
                ]
                rows.extend(replace(row, kind="digest") for row in taxonomys)
            for number, entry in enumerate(digest.get(name, []), start=1):
                queries = entry.get("queries")
                if isinstance(queries, list) and preset_query not in queries:
                    continue
                rows.append(
                    template_row("digest", name, preset_query, f"digest/{name}/{number}", str(entry["text"]))
                )
            mine = [template for wanted, template in candidates if wanted == name]
            for number, template in enumerate(mine, start=1):
                rows.append(
                    template_row("candidate", name, preset_query, f"candidate/{name}/{number}", template)
                )
    return rows


def the_feeds(root: Path, preset: DailyPreset) -> tuple[FeedSource, ...]:
    lists = [
        config for config in load_feed_directory(root / FEEDS_DIRECTORY) if config.topic in preset.feed_topics
    ]
    return feeds_of(lists)


def offline_feed(request: httpx.Request) -> httpx.Response:
    """One made-up RSS feed: three items about a bill, the Senate and the midterms, at known ages."""
    del request
    now = datetime.now(UTC)
    items = [
        ("Senate vote count on the bill", now - timedelta(hours=2)),
        ("Senate Republicans and the midterms polls", now - timedelta(hours=30)),
        ("An undated item on the bill", None),
        ("A bill from last month", now - timedelta(days=30)),
    ]
    body = "".join(
        f"<item><title>{title}</title><link>https://example.test/{number}</link>"
        + (f"<pubDate>{when.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>" if when else "")
        + "</item>"
        for number, (title, when) in enumerate(items)
    )
    xml = f'<?xml version="1.0"?><rss version="2.0"><channel><title>Made up</title>{body}</channel></rss>'
    return httpx.Response(200, content=xml.encode(), headers={"content-type": "application/rss+xml"})


def failure_kind(error: ProviderError) -> str:
    """`HTTP 404`, `timed out`, `unreadable feed`: the reason up to its first colon, never a body."""
    reason = str(error).removeprefix(f"{error.provider}: ")
    return reason.split(":", 1)[0].strip()[:40]


async def read_feeds(
    feeds: Sequence[FeedSource], http: HttpSettings, transport: httpx.AsyncBaseTransport | None
) -> list[tuple[FeedSource, tuple[FeedEntry, ...] | str]]:
    """Each feed read once: its entries, or the kind of its failure."""
    client = feed_client(http, version=package_version(), transport=transport)
    fetcher = FeedFetcher(
        client,
        cache=InMemoryFeedCache(),
        clock=SystemClock(),
        provider=PROVIDER_NAME,
        max_bytes=min(http.max_response_bytes, MAX_FEED_BYTES),
    )
    gate = asyncio.Semaphore(CONCURRENT_FETCHES)

    async def one(feed: FeedSource) -> tuple[FeedSource, tuple[FeedEntry, ...] | str]:
        async with gate:
            try:
                return feed, (await fetcher.fetch(feed.url)).entries
            except ProviderError as error:
                return feed, failure_kind(error)

    try:
        return list(await asyncio.gather(*(one(feed) for feed in feeds)))
    finally:
        await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Count what a daily digest's queries keep of its feeds.")
    parser.add_argument("preset", nargs="?", default="politics")
    parser.add_argument("--offline", action="store_true", help="read a made-up feed, not the network")
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        metavar="PAIR=TEMPLATE",
        help='a template to count, e.g. "midterms-da/uniqueness={query} polls"; repeat for more',
    )
    arguments = parser.parse_args()
    root = config_root(arguments.offline)
    preset = load_daily_presets(root / DAILY_PRESETS_PATH).find(arguments.preset)
    if preset is None:
        sys.exit(f"STOP: this build has no daily preset {arguments.preset!r}")
    candidates = [tuple(text.split("=", 1)) for text in arguments.candidate if "=" in text]
    if len(candidates) != len(arguments.candidate):
        sys.exit("STOP: a --candidate is PAIR=TEMPLATE, for example midterms-da/uniqueness={query} polls")
    where, digest = digest_groups(root)
    rows = the_rows(root, preset, digest, [(pair, template) for pair, template in candidates])
    feeds = the_feeds(root, preset)
    http = HttpSettings() if arguments.offline else settings_loader()().http
    transport = httpx.MockTransport(offline_feed) if arguments.offline else None
    now = datetime.now(UTC)
    read = asyncio.run(read_feeds(feeds, http, transport))

    failed = [(feed, outcome) for feed, outcome in read if isinstance(outcome, str)]
    print(
        f"build {package_version()} preset {preset.name} feeds {len(feeds)} read {len(read) - len(failed)} "
        f"failed {len(failed)} run {now.strftime('%Y-%m-%dT%H:%MZ')}"
        + (" OFFLINE" if arguments.offline else "")
    )
    print(f"digest templates from the {where}" if where != "none" else "digest templates: none found")
    listed: list[tuple[int, FeedEntry]] = []
    links: set[str] = set()
    for index, (_, outcome) in enumerate(read):
        if isinstance(outcome, str):
            continue
        for entry in outcome:
            if entry.link not in links:
                links.add(entry.link)
                listed.append((index, entry))

    print("\nfeed | listed | undated | " + " | ".join(f"in_{name}" for name, _ in WINDOWS))
    for index, (feed, outcome) in enumerate(read):
        if isinstance(outcome, str):
            print(f"{feed.publisher} | failed: {outcome}")
            continue
        own = [entry for at, entry in listed if at == index]
        in_windows = [sum(1 for entry in own if inside(entry, now, span)) for _, span in WINDOWS]
        undated = sum(1 for entry in own if entry.published_at is None)
        print(
            f"{feed.publisher} | {len(own)} | {undated} | " + " | ".join(str(count) for count in in_windows)
        )
    totals = [sum(1 for _, entry in listed if inside(entry, now, span)) for _, span in WINDOWS]
    undated_total = sum(1 for _, entry in listed if entry.published_at is None)
    print(f"all feeds | {len(listed)} | {undated_total} | " + " | ".join(str(count) for count in totals))

    for name, span in WINDOWS:
        in_span = [entry for _, entry in listed if inside(entry, now, span)]
        print(f"\nwindow {name}: {len(in_span)} items")
        print("kind | pair | preset_query | template_id | template | every_word | own_words | own_plus_one")
        kept: dict[tuple[str, str, str], set[int]] = {}
        for row in rows:
            counts: list[str] = []
            for rule, keeps in RULES:
                hits = {position for position, entry in enumerate(in_span) if keeps(entry, row)}
                kept.setdefault((row.kind, row.pair, rule), set()).update(hits)
                kept.setdefault((row.kind, "whole digest", rule), set()).update(hits)
                counts.append(str(len(hits)) if row.kind == "taxonomy" or rule == "every_word" else "-")
            print(
                f"{row.kind} | {row.pair} | {row.preset_query} | {row.template_id} | {row.template} | "
                + " | ".join(counts)
            )
        print("distinct items kept, any query of the group:")
        groups = dict.fromkeys((row.kind, row.pair) for row in rows)
        for kind, group in [*groups, *dict.fromkeys((kind, "whole digest") for kind, _ in groups)]:
            counts = [
                str(len(kept.get((kind, group, rule), set())))
                if kind == "taxonomy" or rule == "every_word"
                else "-"
                for rule, _ in RULES
            ]
            print(f"{kind} | {group} | " + " | ".join(counts))


def inside(entry: FeedEntry, now: datetime, span: timedelta) -> bool:
    return in_window(entry.published_at, SearchFilters(since=now - span, until=now))


if __name__ == "__main__":
    main()

# Topic feed lists

One YAML file per topic names the publisher RSS and Atom feeds the `rss` discovery provider reads
for that topic, and whether Google News may be searched for it. The lists are the coach's. The files
committed here are a small starter set: every feed in them says `review: awaiting_coach_review`.

The LD and PF topics change on 2026-11-01, so they are left for the coach to add.

## The file

The file name is the topic's name, lowercase words joined by hyphens, and `topic:` repeats it.

```yaml
topic: health-insurance
description: >-
  What the topic is, for the person reading this file.
feeds:
  - url: https://publisher.example.org/feed.xml
    publisher: The outlet's name, as results report it
    review: awaiting_coach_review
google_news:
  enabled: false
  language: en-US
  country: US
  edition: US:en
```

* `feeds` lists each feed's absolute `http` or `https` URL, the publisher's name, and `review`:
  `awaiting_coach_review` until the coach has looked at the feed and kept it, then `coach_reviewed`.
  A feed listed on two topics is read once.
* `google_news` is optional and off unless `enabled: true`. When it is on, the topic's searches
  also ask Google News's RSS search, in the edition `language`, `country` and `edition` name
  (Google's `hl`, `gl` and `ceid`). Most Google News items cannot be traced to the publisher's own
  URL without asking Google, which the platform does not do, so they are dropped and few results
  come back.

Every file is checked when it is read. A misspelled key, a URL that is not absolute http(s), a feed
listed twice or a `topic:` that does not match the file name stops the load with the file and the
problem named. `packages/debate_core/tests/integrations/discovery/test_feed_config.py` loads every
file here on every pull request.

## Checking that the feeds answer

A URL listed here has not been shown to work by being listed. The operator's feed check fetches each
configured feed once and prints, per feed, the status, the number of entries and how many of them
carried a date. It prints nothing from an entry. Run it from the repository root, on a machine with
network access:

```bash
uv run python -m debate_core.integrations.discovery.feed_check --feeds-dir config/feeds
```

It exits with status 1 when any feed failed. A feed that answers `HTTP 200` with dated entries is
ready for the coach's review; one that fails or carries no dates is worth replacing.

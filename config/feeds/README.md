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
search_topics: [policy-2026-27-nhi]
government_providers: [federal_register, govinfo]
```

* `feeds` lists each feed's absolute `http` or `https` URL, the publisher's name, and `review`:
  `awaiting_coach_review` until the coach has looked at the feed and kept it, then `coach_reviewed`.
  A feed listed on two topics is read once.
* `google_news` is optional and off unless `enabled: true`. When it is on, the topic's searches
  also ask Google News's RSS search, in the edition `language`, `country` and `edition` name
  (Google's `hl`, `gl` and `ceid`). Most Google News items cannot be traced to the publisher's own
  URL without asking Google, which the platform does not do, so they are dropped and few results
  come back.

* `search_topics` and `government_providers` are optional, and go together. `search_topics` names
  the debate topics the file applies to, as `search --topic` takes them (`policy-2026-27-nhi`, the
  ids in `config/argument_taxonomy.yaml` and `config/landscape/topics.yaml`).
  `government_providers` names the government sources a search on one of those topics also asks:
  `federal_register` (the Federal Register's rules, proposed rules and notices) and `govinfo`
  (GovInfo's bills, committee reports, hearings and committee prints). They run only for such a
  search, and only when `providers.enabled` lists them too; a search with no `--topic` never asks
  them. Today only `health-insurance.yaml` lists them, for the NHI Policy topic. The data-center PF
  topic's file waits for the coach's November-December resolution.

Every file is checked when it is read. A misspelled key, a URL that is not absolute http(s), a feed
listed twice, a provider in `government_providers` that is not a government one or a `topic:` that
does not match the file name stops the load with the file and the problem named. `packages/debate_core/tests/integrations/discovery/test_feed_config.py` loads every
file here on every pull request.

## Checking that the feeds answer

A URL listed here has not been shown to work by being listed. The operator's feed check fetches each
configured feed once and prints, per feed, the status, the number of entries, how many of them
carried a date and the newest of those dates. It prints nothing from an entry. Run it from the
repository root, on a machine with network access:

```bash
uv run python -m debate_core.integrations.discovery.feed_check --feeds-dir config/feeds
```

It exits with status 1 when any feed failed. A feed that answers `HTTP 200` with dated entries is
ready for the coach's review; one that fails or carries no dates is worth replacing.

A feed that answers but cannot be parsed gets a second line, `why:`, in counts and statuses only:
the content type and encoding the server declared, the body's size, what comes before its first
markup and what kind of markup that is (an XML declaration, an HTML page), the XML parser's error
with its line and column, how many control characters XML forbids and how many bare `&` the body
holds, whether it is UTF-8, and whether it would parse with leading whitespace removed. That tells a
publisher serving broken XML or a web page from a parser refusing a valid feed.

To check a feed before it is added, give its URL instead; `--url` may be repeated, and the rows say
`candidate` for the topic and the URL's host for the publisher:

```bash
uv run python -m debate_core.integrations.discovery.feed_check --url https://publisher.example.org/feed.xml
```

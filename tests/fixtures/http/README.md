# HTTP cassettes (`v1-e04-t06-fetch-command`)

Recorded responses for `debate-research fetch` and for later end-to-end tests (E06, E08). The
integration tests hand them to the real `HttpArticleFetcher` through `ReplayTransport`
([`cassettes.py`](cassettes.py)), so every gate of the fetcher, both extractors, the access
classifier and `ArticleService` run as they do for a student. Nothing is sent anywhere: a request no
cassette recorded is answered with a transport failure and fails the test that made it.

## Nothing here was recorded from a real site

Every page is **synthetic** (the PM's amendment of 2026-10-25). A real article is someone else's text,
so the corpus reuses the invented samples that `v1-e04-t03` ([`../access/`](../access/README.md)) and
`v1-e04-t04` ([`../extraction/`](../extraction/README.md)) wrote by hand, each served at an invented
address under an `example` domain as the response it imitates. No source or recording date exists to
record, so the table says how each cassette was made instead. How the pipeline behaves on real pages
is measured in place by `v1-e04-t07` and never committed.

| Cassette | Kind | Served as | Made from | Expected |
|---|---|---|---|---|
| `news-article.json` | news | 200, `text/html`, fetched with `?utm_source=newsletter` | t04's newspaper story (The Daily Meridian is invented), whose relative `rel=canonical` names its own path | ACCESSIBLE |
| `think-tank-report.json` | think-tank | 200, `text/html` | t04's policy report (the Harwell Institute is invented) | ACCESSIBLE |
| `government-press-release.json` | government | 200, `text/html`, at `www.fosw.example.gov` | t04's federal press release; the Federal Office of Synthetic Wildlife imitates no real agency, and no real .gov page was fetched | ACCESSIBLE |
| `open-access-pdf.json` | open-access PDF | 200, `application/pdf`, at a URL carrying the test-prefix DOI `10.5555/jscs.2026.0012` | t04's three-page journal article, written by `build_pdf_fixtures.py` with no PDF library | ACCESSIBLE, DOI detected |
| `paywalled.json` | paywalled | 200, `text/html` | t03's hard-paywall teaser (The Harbor Review is invented): one paragraph, `isAccessibleForFree` "False" | PAYWALLED |
| `robots-disallowed.json` | robots-disallowed | robots.txt only: `Disallow: /archive/` | an invented site; the page is never requested, so no response for it exists | ROBOTS_DISALLOWED |
| `not-found.json` | 404 | 404, `text/html` | t03's 404 page, which carries the site's metering script | NOT_FOUND |
| `bot-challenge.json` | blocked | 403, `text/html` | t03's bot-challenge interstitial | BLOCKED |

Every cassette also answers its origin's `/robots.txt`, which the fetcher reads before the page. All
but `robots-disallowed.json` allow every agent.

## The format

One JSON file per fixture URL: `kind`, `url`, `made_from`, and `interactions`, each a request
(`method` and `url`, nothing else) and its response (`status_code`, `headers`, and either `body_file`,
a sample's path relative to `tests/fixtures/`, or a short inline `body_text` for a robots.txt). Bodies
are referenced rather than copied, so a cassette serves exactly the bytes that t03's and t04's
hand-written expectations were written from.

## Scrub rules

`build_cassettes.py` writes every response's headers through `scrub_headers`, and
`../test_cassette_hygiene.py` checks every committed cassette against the same rules, written out
again so that a builder that stopped scrubbing is caught:

* **No credentials or session state:** `Cookie`, `Set-Cookie`, `Set-Cookie2`, `Authorization`,
  `Proxy-Authorization`, `WWW-Authenticate`, `X-Api-Key`, `X-Amz-Security-Token`.
* **No per-visit tracking:** `CF-Ray`, `NEL`, `Report-To`, `Server-Timing`, `X-Request-Id`,
  `X-Trace-Id`, `X-Amz-Cf-Id`, `traceparent`.
* **No request headers at all.** A request is its method and URL, so nothing the fetcher sent (its
  User-Agent included) is kept.
* **No full paywalled article.** A paywalled cassette serves a teaser: fewer than 200 visible words.
  t03's sample is one paragraph and a subscribe box, so there is no body to truncate.
* **Invented hosts only.** Every host has an `example` label, and every body is one of t03's or t04's
  synthetic samples.

## Rebuilding

The hygiene test fails when a committed cassette differs from what the builder writes. After changing
`build_cassettes.py`, rewrite them:

```bash
uv run python tests/fixtures/http/build_cassettes.py
```

## Expected outcomes are written by hand

[`expected_fetches.json`](expected_fetches.json) says, for each cassette, the status, exit code,
canonical URL, title, identifiers, paragraph count, marker and the start of the reason that
`debate-research fetch` must print. It was written from the samples and from t03's and t04's own
hand-written expectations (working agreement 6), never saved from a run. The paragraph counts are the
lengths of t04's `*.expected.json` paragraph lists; the reasons are t03's classifier tables.

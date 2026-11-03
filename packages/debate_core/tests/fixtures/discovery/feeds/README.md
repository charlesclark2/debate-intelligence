# Feed fixtures

Feeds and recordings for the feed providers
(`packages/debate_core/src/debate_core/integrations/discovery/feeds.py` and `google_news_rss.py`),
used by the `test_feed*.py` files in `packages/debate_core/tests/integrations/discovery/` and their
bindings of the shared search provider contract kit.

Nothing here was captured from a live feed. Every feed was written by hand, so the outlets, stories
and people are invented and every host is an `example` domain. Every expected mapping
(`*.expected.json`) and every count a test asserts was worked out by hand from these bodies.

* `publisher_rss.xml` is an RSS 2.0 politics feed from "The Example Courier" with twelve items:
  * dates in `+0000`, `-0000` (UTC, RFC 5322), `EDT`, `+0545`, `+05:30` and `BST`. The standard
    library cannot place `BST`, so that item has no date;
  * one item with no date and one with no link (skipped);
  * the first item listed a second time, with the same link;
  * one item outside the October 2026 window, one that does not mention health insurance, and one
    that says only "reinsurance";
  * a `content:encoded` full text and an `<author>` that is an email address with a name.
* `publisher_atom.xml` is an Atom 1.0 feed from "Example Health Ledger" with five entries:
  * `html`, `text` and `xhtml` summaries, and an `html` title;
  * a `self` link beside the `alternate` one;
  * one entry dated only by `<updated>`, one with no date and one dated with no offset;
  * a `<content>` full text.
* `entity_expansion.xml` is the "billion laughs" attack: ten nested entities that would expand to
  10⁹ copies of "lol". `external_entity.xml` declares an entity read from `file:///etc/passwd`.
  The parser must refuse both without expanding or reading anything.
* `google_news_search.xml` is a Google News RSS search answer, in Google's shape, with five items:
  * two whose article ids are the pre-2024 format, which carries the publisher URL;
  * one in the current opaque format, which cannot be resolved without asking Google;
  * one outside the window;
  * one whose embedded URL is Google's own.

  Every `<source url>` is the outlet's home page, never the article. The article ids were built by
  hand from URLs chosen for the test (protobuf field 4 holding the URL, base64url-encoded), so the
  publisher URLs the tests expect are the URLs that went in.

The recordings, in the contract kit's format:

* `feeds_search.json` is a `health insurance` search between 2026-10-01 and 2026-10-21 over both
  publisher feeds. The RSS feed answers with an `ETag` and the Atom feed with a `Last-Modified`.
  `feeds_search.expected.json` is the eight candidates it must map to, newest first.
* `feeds_not_modified.json` is the same search asked again: both feeds answer `304 Not Modified`
  with no body, and the results must be the same eight, from the cache, with nothing parsed.
* `feeds_rate_limited.json` is the same search with the RSS feed answering `429` with
  `Retry-After: 600`. The answer is partial, with the Atom feed's three candidates
  (`feeds_rate_limited.expected.json`).
* `google_news_search.json` is the same search on Google News. `google_news_search.expected.json`
  is the two items whose publisher URL can be resolved and that fall in the window.

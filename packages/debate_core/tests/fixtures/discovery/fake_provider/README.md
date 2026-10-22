# Fake discovery provider fixtures

Recordings for the `FakeProvider` in
`packages/debate_core/tests/integrations/discovery/test_fake_provider.py`, which proves the shared
search provider contract kit (`debate_core.testing.contracts.search_provider`) passes a correct
adapter and fails a broken one.

Every body here is invented: the provider, its API, the papers and the people do not exist. The
contact email in the recorded URLs, `coach@example.org`, is the sentinel the tests configure.

* `search.json` records one `GET` search. `search_by_post.json` is the same search sent as a `POST`,
  for the non-idempotent resending rule.
* `search.body.json` is the provider's answer: three items for a request that asked for two.
* `search.expected.json` is what that answer must map to, written by hand from the body (working
  agreement 6). Two results, because the adapter keeps to `max_results`. The DOI is bare and
  lowercase, and the first item's `-05:00` timestamp is in UTC.

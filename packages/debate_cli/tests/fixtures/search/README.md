# `search` command fixtures

Recorded answers for `packages/debate_cli/tests/test_search_command.py`. Every body is invented:
the journals, the outlet, the people and the papers do not exist (the PM's ruling that fixtures are
synthetic). The DOIs use the `10.5555` test prefix.

* `openalex_works.body.json` is an OpenAlex `/works` answer of three works dated after
  2026-09-14. The test transport serves it for every `/works` request, whatever the query, and
  keeps each request so a test can read which queries were asked.
* `openalex_empty.body.json` is the same endpoint answering with no works.
* `courier_politics.xml` is one publisher RSS feed of five items:
  * "Midterm elections tighten…" and "Policy Center: turnout…" match `midterm elections` inside
    the window `--since 2026-09-14`;
  * "Policy Center: turnout…" links the same URL as the second OpenAlex work, so the two are one
    source found by two providers;
  * "Health insurance fight costs the president political capital" matches the politics DA's
    first link template for `health insurance`;
  * "the summer primaries" is dated 2026-08-01, before the window;
  * "Weekend weather" matches nothing.

* `openalex_auto_cut.body.json` (v1-e08-t06) is an OpenAlex answer of six works whose landing pages are
  the HTTP cassettes' pages (`tests/fixtures/http/cassettes/`), so `search --auto-cut` can fetch and
  cut them offline. The titles, venues and authors are invented and say nothing of the pages. By the
  cassettes and the citation fixtures: the news article, the think-tank report and the open-access PDF
  (the one work with a DOI, which Crossref's recorded answer resolves) cut VERIFIED cards; the
  government press release names no author, so its card is UNVERIFIED; the Harbor Review page is
  PAYWALLED and the Closed Stacks page ROBOTS_DISALLOWED.

Two sentinels are in text a search must never print: `ABSTRACTSENTINEL` in the first work's
abstract and `SNIPPETSENTINEL` in the first item's description.

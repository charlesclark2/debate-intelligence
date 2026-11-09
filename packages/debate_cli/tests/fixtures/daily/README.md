# Recorded feeds for `debate-research daily`'s tests

Synthetic RSS feeds, written by hand, that the tests' transport serves for the feed URLs of the test's
own feed lists (`test_daily_command.py`'s `FEED_LISTS`). No item is a real article; every URL is under
an `example` domain. Every description starts with `SNIPPETSENTINEL`, a word no digest may print.

The committed `politics` preset asks `bill` and `Senate`, each expanded for politics DA uniqueness
(`{query} vote count Senate`, `{query} likely to pass Congress`, `{query} will not pass`) and midterms
DA uniqueness (`{query} midterms polling`, `{query} election forecast`). The feed provider keeps an
item when every word of a query is in its title or description, inside the window.

| File | Items | What each search keeps |
|---|---|---|
| `courier_2026-09-17.xml` | A Senate vote count (17 Sep), B farm bill likely to pass (17 Sep, with a `utm_source`), C Senate election forecast (17 Sep), E an old Senate vote count on a bill (10 Sep), F weekend weather | politics x bill: B. politics x Senate: A (E is outside the window). midterms x Senate: C. Nothing else. |
| `courier_2026-09-18.xml` | G spending bill will not pass (18 Sep), H Senate midterms polling (17 Sep, first listed a day late), then A, B, C and F again | with `--window 2d` on 18 Sep: politics x bill: B and G. politics x Senate: A. midterms x Senate: C and H. |
| `ledger_2026-09-17.xml` | a weekend weather item | nothing |
| `courier_auto_cut.xml` | B, A and C's titles at three of the HTTP cassettes' pages: the Daily Meridian news article and the Harwell Institute report, whose cards verify, and the Harbor Review page, which is paywalled | as the first file |
| `health_wire_2026-09-17.xml` | subsidies at the center of the federal spending debate in Congress, states lead on health insurance policy | the `nhi` preset's spending DA and federalism DA uniqueness searches |

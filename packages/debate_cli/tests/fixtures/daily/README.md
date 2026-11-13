# Recorded feeds for `debate-research daily`'s tests

Synthetic RSS feeds, written by hand, that the tests' transport serves for the feed URLs of the test's
own feed lists (`test_daily_command.py`'s `FEED_LISTS`). No item is a real article; every URL is under
an `example` domain. Every description starts with `SNIPPETSENTINEL`, a word no digest may print.

The committed `politics` preset asks `bill` and `Senate`, and `daily` asks the committed digest
templates for them (`config/daily_templates.yaml`, v1-e08-t25): `bill Congress` for politics DA x
bill; `Senate Congress` and `Senate Republicans` for politics DA x Senate; `Senate election` for
midterms DA x Senate; midterms DA x bill is not searched. The feed provider keeps an item when every
word of a query is in its title or description, inside the window. The `nhi` preset's pairs have no
digest templates, so each of its searches asks the taxonomy's uniqueness templates, as before.

| File | Items | What each search keeps |
|---|---|---|
| `courier_2026-09-17.xml` | A Senate vote count (17 Sep, 14:00), B farm bill likely to pass Congress (17 Sep, 09:30, with a `utm_source`), I Senate Republicans block the stopgap (17 Sep, 11:00), C Senate election forecast (17 Sep, 16:45), E an old Senate vote count on a bill (10 Sep), F weekend weather | politics x bill: B. politics x Senate: I. midterms x Senate: C. A matches only the taxonomy's `Senate vote count Senate`, which `daily` does not ask. |
| `courier_2026-09-18.xml` | G spending bill heads back to Congress (18 Sep, 11:00), H Senate election polling (17 Sep, 23:15, first listed a day late), then A, B, I, C and F again | with `--window 2d` on 18 Sep: politics x bill: B and G. politics x Senate: I. midterms x Senate: C and H. |
| `ledger_2026-09-17.xml` | a weekend weather item | nothing |
| `courier_auto_cut.xml` | B, I and C's titles at three of the HTTP cassettes' pages: the Daily Meridian news article and the Harwell Institute report, whose cards verify, and the Harbor Review page, which is paywalled | as the first file |
| `health_wire_2026-09-17.xml` | subsidies at the center of the federal spending debate in Congress, states lead on health insurance policy | the `nhi` preset's spending DA and federalism DA uniqueness searches |

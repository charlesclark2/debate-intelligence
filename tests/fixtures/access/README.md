# Access-status fixtures (`v1-e04-t03-access-status`)

Saved pages for the access classifier, and the status each must get.

Every sample here is **synthetic**. The pages imitate the shapes the classifier meets (an open
article, a metered paywall, a hard paywall, a bot challenge, a 404 page, a teaser cut short by a
script, a registration wall), but the publications, people and text are invented for these tests.
No real page was saved or fetched. Vendor script hosts and challenge signatures appear because they
are what the markers match; the identifiers in them (`EXAMPLEAID`, `EXAMPLERAY`) are placeholders.

| Sample | What it is | Expected |
|---|---|---|
| `open-article.html` | A news story with NewsArticle JSON-LD declaring 280 words, `article:content_tier` free, a newsletter sign-up that says "subscribe" | ACCESSIBLE |
| `metered-paywall.html` | A full story served with Piano's Tinypass metering script | PAYWALLED, `piano-tinypass-script` |
| `hard-paywall.html` | A one-paragraph teaser, JSON-LD `isAccessibleForFree: "False"` and a "subscribe to continue reading" box | PAYWALLED, by the HTML extractor's refusal |
| `challenge-page.html` | A Cloudflare-style "Just a moment..." interstitial, served as a 403; once more with `cf-mitigated: challenge` | BLOCKED |
| `not-found.html` | A 404 page carrying the site-wide metering script and a "subscribe to keep reading" line | NOT_FOUND: a missing page is not a paywall |
| `truncated-teaser.html` | Two paragraphs of a story whose JSON-LD (in an `@graph`) declares 1450 words; the rest is loaded by a script | PAYWALLED, by the truncation heuristic |
| `registration-wall.html` | Two paragraphs and "Create a free account to continue reading" | PAYWALLED, `register-to-continue-reading-text` |

## Expected output is written by hand

`expected_statuses.json` is written by hand from the samples (working agreement 6), never saved
from a classifier run, and was committed failing before the classifier was built. Each entry names
the sample file, the response it is served as (status code and headers), whether the HTML extractor
runs on it (it does on a 200, as ArticleService will; an error page is classified from its status
and markers), the status, the marker that must be recorded (`null` for none), and the declared
article length that must be recorded (`null` for none).

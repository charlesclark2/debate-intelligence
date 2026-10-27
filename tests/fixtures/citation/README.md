# Citation fixtures (`v1-e06-t01-citation-service`)

Pages, Crossref answers and the cites each must produce, for the page metadata harvester
(`debate_core.retrieval.citation_harvest`), the Crossref DOI client
(`debate_core.integrations.crossref_doi`) and `CitationService`.

## Nothing here was recorded

Every page and every Crossref answer is **synthetic** (the PM's E04 amendment of 2026-10-25, and
the ruling for this task). The pages reuse the invented samples t04 wrote by hand, served at the
addresses t06's cassettes give them; the one page added here is written the same way. Crossref
answers are written by hand under the `10.5555` test prefix, the one Crossref's own documentation
uses for examples, as t06's PDF cassette is. Nothing was fetched from a real site or from Crossref, and no test makes a
live call: respx serves the answers.

| Case | Kind | Page | Made from | Crossref |
|---|---|---|---|---|
| `news-article` | news | `../extraction/news-article.html`, unchanged | t04's newspaper story (The Daily Meridian is invented), at t06's address with `?utm_source=newsletter` | none: no DOI |
| `think-tank-report` | think tank | `../extraction/think-tank-report.html`, unchanged | t04's policy report (the Harwell Institute is invented), whose author bios give the credentials | none |
| `government-press-release` | government | `../extraction/gov-press-release.html`, unchanged | t04's federal press release; the Federal Office of Synthetic Wildlife imitates no real agency. It names no author and has no JSON-LD or `og:title`, so its title is the `<title>` element's, a heuristic | none |
| `journal-article-landing` | journal | `journal-article-landing.html`, added here | a landing page for t04's invented journal article (`build_pdf_fixtures.py`): `citation_*` meta tags, the test-prefix DOI `10.5555/jscs.2026.0012`, a `citation_author_institution` that must not become a credential | `crossref/works-10.5555-jscs.2026.0012.json` |
| `open-access-pdf` | journal PDF | `../extraction/journal-article.pdf`, unchanged | t04's PDF at t06's address, which carries the DOI; a PDF has no markup to read | the same answer |
| `user-supplied` | pasted text | none: the text is in the case file | a USER_SUPPLIED snapshot of invented text, with a meta tag and a byline typed into it that must not be read | none |
| `organization-report` | government, issued by an organization | `organization-report.html`, added by `v1-e06-t02` | t04's press release unchanged but for one JSON-LD `Report` block in its head naming the invented agency as a `GovernmentOrganization` author: the case of an organization standing in as the author | none |

`crossref/works-10.5555-jscs.2026.0012.json` is a Crossref `/works/{doi}` answer for that invented
article: the authors' full names (the page gives initials), one affiliation, and dates to the day
except `published-print`, which gives a month only. Its `DOI` is upper-case, as Crossref sometimes
sends one, so the client's lower-casing is exercised.

## Expected cites are written by hand

Each `<case>.expected.json` names its inputs (page, content type, the URL it was retrieved from, its
provenance mode, the article ArticleService would have stored) and the cite: every field's value,
source and verified flag, the short and full cite lines, and which fields are unverified or missing.
They were written from the pages and the Crossref answer (working agreement 6), before
`CitationService` was written, and never saved from a run. `v1-e06-t02` changed them by hand for its cite
rules: every accessed date, and the open-access PDF's and the pasted text's URLs, have the source
`retrieval` (verified for the five publisher-retrieved cases), and `organization-report` was added. Every case is retrieved at
`2026-10-26T15:00:00Z`, which is its accessed date.

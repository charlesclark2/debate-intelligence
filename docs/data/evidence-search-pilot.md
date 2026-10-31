<!-- docs-index: The student search pilot's evidence: early sessions, the promotion checklist, the beta and the go or no-go -->
# Student search pilot: what happened

The record of the student search pilot (E39, v1.7): who used it in which environment, as counts,
what the promotion to prod did, the coach's beta and the student pilot, and the decision for the
whole team. It never holds a name, a username, a quotation with an identity, or card text
(data-use policy, E39 gate items 8 and 9). `v1-e39-t10` laid out the tables below; the operator,
the coach and the PM fill them in. The PM started it on 2026-10-22 so that the early evidence is not
lost.

## Early evidence, before the beta

| Date | Environment | What happened | Recorded by |
|---|---|---|---|
| 2026-10-22 | dev | The coach gave **2** debaters dev accounts. Both signed in and searched on their own school Chromebooks, on the school's network, without help. This is the first sign that the school's web filter lets the pilot's hosts through, for dev's hostnames only. Their dev accounts are not carried to prod. | PM, from the coach's report |
| 2026-10-22 | dev | The weekly agent run `20261022T052044Z` published index `767b9c7c056b80cb`: 52,059 documents, 839,438,336 SQLite bytes, 314,054,035 gzip bytes. | PM |

## The card-only rule (`v1-e39-t12`)

The dev index's documents before and after the first index built with the card-only rule (CITE_ONLY,
or no cite and fewer than 25 words: [the rule](search-index.md#only-real-cards)), published by hand
as [the scheduled sync runbook](../runbooks/caselist-scheduled-sync.md#the-first-index-with-the-card-only-rule-v1-e39-t12-once)
says. The expected row is from the counts over the 2026-10-22 index; the measured rows are the
operator's (`v1-e39-t12` ac3).

| | Index | Date | hsld26 | hspf26 | hspolicy26 | openev | All |
|---|---|---|---:|---:|---:|---:|---:|
| Counted, before the rule | `767b9c7c056b80cb` | 2026-10-22 | 13,225 | 11,393 | 21,595 | 5,846 | 52,059 |
| Expected after it | | | 12,714 | 11,000 | 20,961 | 5,759 | 50,434 |
| Before, measured | `767b9c7c056b80cb` | 2026-10-22 | 13,225 | 11,393 | 21,595 | 5,846 | 52,059 |
| After, measured | `f29b81c276dd67c5` | 2026-10-22 | 12,714 | 11,000 | 20,961 | 5,759 | 50,434 |
| Left out as no card, measured | | | 511 | 393 | 634 | 87 | 1,625 |
| of which cite only | | | 366 | 297 | 558 | 70 | 1,291 |
| of which no cite, under 25 words | | | 145 | 96 | 76 | 17 | 334 |

Shares kept: 96.1%, 96.6%, 97.1% and 98.5%. The stores had not grown since the counts, so the
measured rows equal the expected row. Block 1 printed `OK: every store keeps 90% or more`; block 2,
a plain publish with no `--allow-shrink`, passed the shrink guard, and `current.json` names
`f29b81c276dd67c5`. Recorded by the PM from the operator's run of 2026-10-22.

## The promotion to prod

Each item of [the runbook's promotion list](../runbooks/evidence-search.md#promoting-the-pilot-to-prod),
ticked yes or no with its date, before the coach's beta (`v1-e39-t10` ac7).

| Item | Done | Date | Notes |
|---|---|---|---|
| 1. `dev` promoted to `main` | | | |
| 2. Prod's `owner.auto.tfvars` checked | | | |
| 3. Step 11 in full, nothing destroyed | | | |
| 4. `v1-e29-t08`'s prod plan | | | |
| 5. Prod's suppression list exists | | | |
| 6. Prod's parsed store current | | | |
| 7. Prod's first index published | | | |
| 8. `v1-e39-t07`'s prod removal exercise | | | |
| 9. Superseded parsed directories retired in prod | | | |
| 10. The request to school IT | | | |
| 11. The beta's prod accounts created | | | |
| 12. The Lambda bandwidth-quota request sent | | | |

## Dev's checks before the promotion

`validate-dev`'s `cloud` job and the operator's signed-in journey on dev
([the runbook](../runbooks/evidence-search.md#the-signed-in-journey-on-dev)), each with its date and
the commit dev ran. Yes or no, and the step that failed if one did.

| Check | Date | Dev's deployed commit | Passed | Notes |
|---|---|---|---|---|
| The dev cloud checks by hand (`3 passed`) | | | | |
| The journey (J6): every step `PASS` | | | | |
| The removed card gone five minutes after `DONE` (J8) | | | | |
| The seed out of dev's index (J9), shrink allowed for `testcl26` alone | | | | |

## Measured from the app log

The CloudWatch Logs Insights queries of
[the runbook](../runbooks/evidence-search.md#measuring-the-pilot-from-the-app-log-v1-e39-t10), over the
time range in the row (`v1-e39-t10` ac5). Times in milliseconds or seconds as the query gives them;
bytes as logged.

| Environment | Time range | Searches | Query p50 (ms) | Query p95 (ms) | Cold-start index loads | Index load (s), median and max | Init Duration (ms), median and max | Index loaded: SQLite bytes, gzip bytes | Peak `/tmp` across a replacement (bytes) |
|---|---|---:|---:|---:|---:|---|---|---|---:|
| dev | | | | | | | | | |
| prod, the beta | | | | | | | | | |
| prod, the pilot | | | | | | | | | |

A replacement is a load line whose directory total is above its own SQLite bytes; with none in the
range, the peak column says *no replacement* rather than a number.

## The coach's beta

[The checklist](../runbooks/evidence-search.md#the-coachs-beta-v1-e39-t10), on prod, once every item of
the promotion above is ticked (`v1-e39-t10` ac2, ac6). One column per tester, numbered in the order
they started, never named; each cell yes, no, or the count asked for. The coach keeps the screenshots.

**Each tester's first sign-in**

| | Tester 1 | Tester 2 | Tester 3 | Tester 4 | Tester 5 |
|---|---|---|---|---|---|
| Date | | | | | |
| Device (Chromebook, phone, other) | | | | | |
| Factors managed login offered (authenticator, email, both) | | | | | |
| Factor chosen | | | | | |
| The pilot's authenticator page appeared afterwards | | | | | |
| Reached the search page signed in, without help | | | | | |

**On a school Chromebook, on the school's network**

| Check | Yes / no | Date | Notes (no names) |
|---|---|---|---|
| 5. Sign in | | | |
| 6. Search by words, filtered by event, caselist and side | | | |
| 7. The result count shown | | | |
| 8. Open a card; its provenance line on the card page | | | |
| 9. *Back to results* returns to the same results | | | |
| 10. *Open on openCaselist* opens the team's page in a new tab | | | |
| 11. *Search by passage* finds the card a pasted sentence came from | | | |
| 12. *Copy card* into Google Docs, formatting kept | | | |
| 13. No provenance line in the pasted card | | | |
| 14. *Download .docx* and a cart open in Google Docs | | | |

**Once, with Word**

| Check | Yes / no | Date | Notes |
|---|---|---|---|
| 15. *Copy card* into Word, formatting kept | | | |
| 16. A downloaded card opens in Word with Verbatim | | | |

**Found in the beta**: each problem as one line, what it was and what was done (fixed in which deploy,
or accepted by the coach), with no tester named.

## The student pilot, and the decision

Three to five debaters, prod accounts, at least a week (`v1-e39-t10` ac3), after the PM's go on the
beta. Tallies are counts over the pilot's dates, counted from the audit log group's `searched`,
`card-viewed`, `card-copied` and `cards-downloaded` records; only the counts are copied here (data-use
policy, E39 gate items 4, 8 and 9). Themes are what debaters said, summarised by the coach, never
quoted with an identity.

| | Count |
|---|---:|
| Pilot dates (first, last) | |
| Debaters with an account | |
| Debaters who signed in at least once | |
| Days with at least one search | |
| Searches | |
| Card pages viewed | |
| Cards copied | |
| Files downloaded (cards in them) | |
| Sign-ins that needed the coach's help | |
| Sessions refused with *Search is not available right now* | |

| Theme | How many debaters raised it | What it means for the whole team |
|---|---:|---|
| | | |

**The decision**: go or no-go for the whole team, the date, who decided (the coach, with the PM), and
the reasons in a sentence each.

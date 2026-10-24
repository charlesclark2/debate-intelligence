# Session report: v1-e32-t10-impact-cards-per-position

| | |
|---|---|
| Task | `v1-e32-t10-impact-cards-per-position` — Impact cards per DA and advantage in the landscape report |
| Spec | [`plan_specs/v1/e32-argument-landscape/t10-impact-cards-per-position.yaml`](../../plan_specs/v1/e32-argument-landscape/t10-impact-cards-per-position.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t10-impact-cards-per-position` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Status: counts taken; the build waits for the PM's ruling.** The spec and the PM's brief say to
count first and to build nothing until the PM rules. This session counted, read-only, on hspolicy26
through 2026-10-20, and the question block is [below](#questions-for-the-pm). No code, fixture or
golden file has changed. The Goal stays `InProgress`: ac2 and ac3 come after the ruling.

**What the counts say:**
* **DAs:** under the proposed rule, 296 of 662 DA documents (44.7%) hold at least one labelled impact
  card. 176 of them have an `impact` heading on the card's path, and 172 have a tag that opens with
  an impact word.
* **Advantages:** 411 of 1,164 documents (35.3%) hold one, almost all of them through the tag (397).
  Only 29 have an `impact` heading, which is the coach's "1AC impacts are unlabelled". What a 1AC
  does is open the tag with the impact itself ("extinction…", "existential…").
* **No labelled impact:** 366 DA documents (55.3%) and 753 advantage documents (64.7%).

**Look first at question 3, the card or the cluster.** If a cluster counts once any copy of it is
labelled, coverage nearly doubles. It also brings widely read link and solvency cards into the top
three, so I recommend the card-level rule the spec describes.

## The counts on the real store

**How they were taken.** Read-only, counts only, hspolicy26 through 2026-10-20, taxonomy 1.1.0 and
the coach's 45 decisions, as `landscape report` stands on `dev`. Before each run, no `DEBATE_*`
variable was set and no `caselist pull` was running.

* **The script** was a scratchpad script, not committed. It read the store as t05's run service
  does, and classified through the run's read-only view of t02's cache.
* **It wrote nothing to the store.** The classification cache and the plan-text cache had the same
  SHA-256 after both runs as before. Nothing under `landscape/review/` changed, and no report
  directory was created.
* **Runtime:** 38.6 s and 41.6 s, at load average 4.5 and 2.3.
* **Coverage matches t05's wired run to the card:** 63,494 of 126,681 cards counted.
* **The cache missed every lookup** (107,187). It holds taxonomy 1.0.0 entries, and every landscape
  run since 1.1.0 has been a read-only dry run, so nothing has rewritten it. Classification ran
  deterministically in memory instead. The first real run rewrites the cache; this is expected, not
  a defect.

**What a document is.** A parsed file holding at least one card that the report counts for the
position: placed under it, READS, at or above the review threshold, and in a round on the position's
own side. This is t03's rule (the PM's rulings). 20,119 DA and advantage cards were placed only in
rounds on the other side, and none of them counts here. No counted card was in a round on no
readable side.

**The comparison with t03's measure.** t03's measure was `impact` or `impacts` in a heading, or
anywhere in the tag. On today's taxonomy it finds 333 of 662 DA documents (50.3%) and 235 of 1,164
advantage documents (20.2%). t03 had 284 of 562 and 229 of 1,129 under 1.0.0. The difference is
1.1.0's three new DAs and the coach's decisions.

### Impact headings, by documents (cards)

A heading is normalized as the matcher reads it (t01's normalizer, with the caselist's schools taken
out). It matches when it holds the label as whole words.

| Heading label | DA documents (cards) | Advantage documents (cards) |
|---|---|---|
| `impact` | 186 (779) | 31 (80) |
| `impacts` | 1 (2) | 0 |
| `impact overview` | 10 (17) | 0 |
| `turns case` | 21 (47) | 0 |
| `t c`, `tc` (T/C) | 17 (40), 10 (19) | 0 |
| `i l`, `il`, `internal link` | 21 (50), 12 (28), 8 (20) | 1 (2), 0, 1 (7) |
| `i l and impact`, `impact calc`, `magnitude`, `escalation`, `outweighs` | 0 | 0, apart from `outweighs` 1 (1) |
| `extinction`, `war`, `nuclear war`, `terminal`, `timeframe` | 1, 10, 1, 2, 2 | 5, 8, 0, 0, 0 |
| `overview`, `ov` (t11's, not an impact) | 42 (175), 19 (64) | 5 (5), 1 (1) |
| answers inside an impact heading: `no impact`, `impact defense`, `impact turn(s)` | 7 (12), 3 (8), 8 (22) | 0, 2 (2), 0 |

### Tags that open with an impact word, by documents (cards)

The tag's words are compared after a leading enumerator: a number, a letter `a` to `h`, or `first`
to `fifth`.

| Tag opens with | DA documents (cards) | Advantage documents (cards) |
|---|---|---|
| `extinction` | 76 (88) | 244 (335) |
| `existential` | 1 (1) | 110 (111) |
| `the impact`, `our impact`, `impact`, `impacts` | 16, 16, 14, 1 | 35, 1, 6, 0 |
| `nuclear war`, `nuke war`, `goes nuclear` | 5, 1, 2 | 14, 11, 0 |
| `turns case` | 29 (33) | 0 |
| `timeframe`, `magnitude`, `probability` | 29, 9, 0 | 2, 0, 4 (5) |
| `outweighs` | 9 (9) | 0 |
| `escalation` | 0 | 4 (4) |
| not proposed: `independently` | 19 (20) | 269 (297) |
| not proposed: `nuclear` alone, `war` alone, `otherwise extinction` | 16, 3, 1 | 19, 3, 15 |
| not proposed: `no impact` (defense) | 32 (36) | 11 (11) |

### The proposed rule, per kind

A card is an impact card when either of these holds:
* **A heading on its path** holds `impact` or `impacts`, but not `no impact`, `impact defense` or
  `impact turn(s)`; or it holds `turns case`.
* **Its tag**, after an enumerator, opens with one of the proposed words: `impact`, `impacts`, `the
  impact`, `our impact`, `extinction`, `existential`, `nuclear war`, `nuke war`, `goes nuclear`,
  `escalation`, `turns case`, `outweighs`, `magnitude`, `timeframe` or `probability`.

| Rule | DA documents with one | Advantage documents with one | DA / advantage documents with none |
|---|---|---|---|
| Narrow: headings `impact(s)`; tags opening `impact(s)`, `the impact`, `our impact` | 214 of 662 (32.3%) | 73 of 1,164 (6.3%) | 448 (67.7%) / 1,091 (93.7%) |
| **Proposed**, card by card | **296 (44.7%)**: 187 by heading, 172 by tag, 63 both | **411 (35.3%)**: 29 by heading, 397 by tag, 15 both | **366 (55.3%) / 753 (64.7%)** |
| Proposed, a cluster counted once any copy is labelled | 484 (73.1%) | 806 (69.2%) | 178 / 358 |

Under the proposed rule, 959 of 9,401 counted DA cards and 598 of 21,157 counted advantage cards are
impact cards.

### Per position, proposed rule, card by card

| DA | Documents | Heading `impact(s)` | Heading `turns case` | Tag word | Any | None | Impact clusters |
|---|---|---|---|---|---|---|---|
| Midterms DA | 418 | 104 | 12 | 90 | 177 | 241 | 164 |
| Economy DA | 89 | 18 | 1 | 22 | 36 | 53 | 40 |
| Pharma DA | 74 | 18 | 1 | 11 | 27 | 47 | 48 |
| Democracy DA | 62 | 0 | 0 | 2 | 2 | 60 | 2 |
| Stocks DA | 53 | 8 | 2 | 14 | 16 | 37 | 14 |
| Debt DA | 49 | 0 | 0 | 0 | 0 | 49 | 0 |
| Rates DA | 44 | 13 | 0 | 19 | 25 | 19 | 30 |
| Federalism DA | 44 | 0 | 0 | 1 | 1 | 43 | 1 |
| AI DA | 28 | 0 | 0 | 0 | 0 | 28 | 0 |
| IRS DA | 28 | 16 | 2 | 5 | 18 | 10 | 20 |
| HHS DA | 20 | 6 | 0 | 1 | 7 | 13 | 10 |
| Capital flight DA | 19 | 5 | 3 | 10 | 12 | 7 | 15 |
| Unions DA | 19 | 1 | 0 | 0 | 1 | 18 | 6 |
| Court clog DA | 17 | 6 | 0 | 7 | 11 | 6 | 24 |
| Medical devices DA | 13 | 7 | 0 | 3 | 9 | 4 | 6 |
| Taxes DA | 11 | 5 | 0 | 0 | 5 | 6 | 6 |
| Permitting reform DA | 10 | 4 | 0 | 0 | 4 | 6 | 16 |
| Innovation DA | 9 | 0 | 0 | 0 | 0 | 9 | 0 |
| Politics DA | 6 | 0 | 0 | 1 | 1 | 5 | 2 |
| Doctors DA | 3 | 0 | 0 | 0 | 0 | 3 | 0 |
| **Distinct documents** | **662** | **176** | **21** | **172** | **296** | **366** | |

| Advantage | Documents | Heading `impact(s)` | Heading `turns case` | Tag word | Any | None | Impact clusters |
|---|---|---|---|---|---|---|---|
| Costs | 394 | 2 | 0 | 42 | 43 | 351 | 12 |
| Disease | 241 | 0 | 0 | 21 | 21 | 220 | 10 |
| Economy | 225 | 4 | 0 | 14 | 18 | 207 | 19 |
| Inequality | 220 | 3 | 0 | 97 | 99 | 121 | 10 |
| Coverage | 217 | 3 | 0 | 43 | 44 | 173 | 32 |
| Growth | 184 | 2 | 0 | 14 | 16 | 168 | 14 |
| Access | 109 | 0 | 0 | 74 | 74 | 35 | 5 |
| Budgets | 103 | 2 | 0 | 56 | 56 | 47 | 8 |
| Stagnation | 93 | 7 | 0 | 27 | 31 | 62 | 19 |
| Bioterror | 86 | 1 | 0 | 13 | 14 | 72 | 12 |
| Innovation | 71 | 0 | 0 | 8 | 8 | 63 | 8 |
| Pandemics | 51 | 1 | 0 | 0 | 1 | 50 | 1 |
| Data | 42 | 1 | 0 | 13 | 13 | 29 | 12 |
| Sustainability | 29 | 0 | 0 | 7 | 7 | 22 | 3 |
| Pharma | 15 | 3 | 0 | 4 | 6 | 9 | 9 |
| Biotech | 12 | 0 | 0 | 0 | 0 | 12 | 0 |
| **Distinct documents** | **1,164** | **29** | **0** | **397** | **411** | **753** | |

31 of the 36 DAs and advantages have at least one impact card. Debt, AI, Innovation and Doctors DA
and the Biotech advantage have none.

### What the top three would show

I read these in my own terminal and quote none of them. Ranked by distinct teams, then cluster id:
* **Tag-opening cards:** of 50 sampled at random (seeded), every one is an impact or
  impact-comparison claim. One of them answers impact defense.
* **Cards placed by heading alone:** of 40 sampled, about half are impact claims. The rest are
  rebuttals filed inside an "Impact" block ("err neg", "doesn't assume the plan").
* **The top three per position, card by card:** about four in five rows read as impact claims. The
  misses come from the heading signal.
* **The top three, cluster-wide:** worse at the top. One team's label carries a widely read card
  into the list: two of the Economy advantage's top three become admin-cost and monopsony cards read
  by 30 or more teams. Cluster-wide changes the top three of 21 of the 31 positions.

**Headings are only read, never shown.** Some raw headings still carry a school name that the source
heading normalizer does not take out. A report never shows a heading, only the tag and the short
cite as parsed, so this changes nothing in what a report says. I kept every such word out of this
report and out of the question block.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| impact-cards | In progress | Counts done and sent to the PM (ac1). The rule, its fixture cases, the hand-written golden files and the section wait for the ruling |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any rule, per DA and advantage, of documents with a labelled impact card, sent to the PM with the proposed impact-heading list | PASS, pending the PM's receipt | [The counts on the real store](#the-counts-on-the-real-store): scratchpad script, read-only, 38.6 s and 41.6 s, cache checksums unchanged. The question block below goes to the PM |
| ac2: after the ruling, on the synthetic fixture, report.md shows up to N impact cards under each DA and advantage, and impact_cards.csv lists them, byte for byte against hand-written golden files; ANSWERS and other-side cards are never impact cards; tests shown failing first | NOT RUN | Waits for the ruling |
| ac3: the report states, per kind, how many documents carry no labelled impact | NOT RUN | Waits for the ruling. The real-store numbers under each proposed rule are above |
| impact-cards: `uv run pytest packages/debate_core/tests/application/test_landscape_report.py` | NOT RUN | No code has changed yet |

## Files changed

* This report. Nothing else.

## Deviations from the spec

None so far.

## Decisions and assumptions

1. **A document** is a parsed file holding at least one card that the report counts for the
   position: READS, at or above the threshold, in a round on its own side. It is the same file the
   report counts, so the "no labelled impact" line has the same denominator as the positions.
2. **A label is matched as whole words** of the normalized heading or of the tag's words, so
   `impactful` and `impacted` do not match `impact`.
3. **The tag rule skips one leading enumerator** (`1`, `b`, `third`), because numbered impact
   modules ("2 timeframe…") are common in blocks.

## Operator follow-ups

1. **Relay the question block** below to the PM, and paste the ruling back into this session.

## Follow-up work

* **The source heading normalizer leaves some schools in headings** (v1-e32-t02's
  `CaselistNames`, or a new E32 task). Nothing shows a heading today, but the review queue and the
  candidates sheet do show headings to the coach. I have not measured how often this happens.

## Questions for the PM

```text
v1-e32-t10 questions (session, 2026-10-24): counts first, nothing built

Read-only, hspolicy26 through 2026-10-20, taxonomy 1.1.0 with the coach's 45
decisions; counts only. A document is a file with a card the report counts
for the position (READS, at or above the threshold, round on its own side;
20,119 other-side DA/advantage cards excluded). 662 DA documents, 1,164
advantage documents. t03's measure ("impact" in a heading or anywhere in the
tag) now finds 333 of 662 DA and 235 of 1,164 advantage documents.

Impact headings (documents, DA / advantage):
  impact 186 / 31, impacts 1 / 0, impact overview 10 / 0,
  turns case 21 / 0, T/C ("t c", "tc") 17 and 10 / 0,
  i/l ("i l", "il", "internal link") 21, 12, 8 / 1, 0, 1,
  "i l and impact", impact calc, magnitude, escalation 0 / 0,
  overview 42 / 5 (t11's, not an impact),
  inside an impact heading: "no impact" 7, "impact defense" 3,
  "impact turn(s)" 8 / 0, 2, 0.

Tags opening with an impact word (documents, DA / advantage; after a
leading enumerator such as "1", "b", "third"):
  extinction 76 / 244, existential 1 / 110, the impact 16 / 35,
  our impact 16 / 1, impact(s) 15 / 6, nuclear war 5 / 14, nuke war 1 / 11,
  goes nuclear 2 / 0, turns case 29 / 0, timeframe 29 / 2, magnitude 9 / 0,
  outweighs 9 / 0, probability 0 / 4, escalation 0 / 4.
  Not proposed: independently 19 / 269 (mostly add-ons and links),
  "no impact" 32 / 11 (defense), nuclear alone 16 / 19.

Under the proposed rule, card by card:
  DA: 296 of 662 documents (44.7%) hold an impact card, 187 by heading and
    172 by tag; 366 (55.3%) hold none.
  Advantage: 411 of 1,164 (35.3%), 29 by heading and 397 by tag; 753 (64.7%)
    hold none.
  Narrow rule (headings impact(s); tags opening impact(s), the/our impact):
    DA 214 (32.3%), advantage 73 (6.3%).
  Per position: Midterms 177 of 418, Economy DA 36 of 89, Pharma DA 27 of 74.
    The Debt, AI, Innovation and Doctors DAs and the Biotech advantage have
    none. The Inequality advantage has 99 of 220, Costs 43 of 394. The full
    table is in the session report.

1. Heading list. A card is an impact card when a heading on its path holds
   "impact" or "impacts" (whole words), but not "no impact", "impact
   defense" or "impact turn(s)"; or holds "turns case".
   (a) As proposed.
   (b) Also T/C ("t c", "tc") and i/l.
   (c) Only "impact" and "impacts", no exclusions.
   Recommendation: (a). T/C is ambiguous as an abbreviation; i/l alone is a
   link, not an impact; the exclusions are defense or answers filed under an
   impact heading. "i l and impact" never occurs.

2. Tag words. A card is an impact card when its tag, after one leading
   enumerator, opens with: impact, impacts, the impact, our impact,
   extinction, existential, nuclear war, nuke war, goes nuclear, escalation,
   turns case, outweighs, magnitude, timeframe, probability.
   (a) As proposed.
   (b) Only impact, impacts, the impact and our impact.
   Recommendation: (a). It is what makes advantages countable at all (6.3%
   becomes 35.3%): a 1AC opens the tag with the impact itself. Of 50 such
   cards sampled at random, all 50 are impact or impact-comparison claims.

3. Card or cluster. Is a cluster an impact card when one of its copies is
   labelled, so that every team reading any copy under the position counts?
   (a) Card by card: only the labelled copies count, and their teams rank
       the cluster.
   (b) Cluster-wide: DA 484 documents (73.1%), advantage 806 (69.2%); the top
       three changes for 21 of 31 positions.
   Recommendation: (a), as the spec words it. Cluster-wide lets one team's
   label carry widely read link and solvency cards into the top three (two
   of the Economy advantage's top three, read by 30 or more teams each).
   Card by card, about four in five top-three rows read as impact claims;
   the misses are rebuttals inside an "Impact" block, from the heading
   signal.

4. The "no labelled impact" line (ac3) uses the same rule and denominator:
   DA 366 of 662, advantage 753 of 1,164 today, per kind, in report.md's
   impact section and in impact_cards.csv's header block. Agree?
   Recommendation: yes. With the rule ruled, the line says exactly what the
   section could not see, and t07's model stage is what closes it.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

# Session report: v1-e39-t12-card-only-results

| | |
|---|---|
| Task | `v1-e39-t12-card-only-results` — Only real cards come back: entries with no cite or a few words of text, counted before any rule |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t12-card-only-results.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t12-card-only-results.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t12-card-only-results` |
| Session status | IN PROGRESS: counts sent to the PM, waiting for a ruling <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Counts first, no rule yet. Over the dev index `767b9c7c056b80cb` (52,059 documents, built
2026-10-22), 334 documents (0.6%) have no cite and fewer than 25 words of text, the shape the spec
guessed at. **The coach's example is probably not that shape.** The four documents whose tag carries
the coach's sentence include two CITE_ONLY documents: a tag, something parsed as a cite, and no text.
A "no cite" rule cannot catch them, because every CITE_ONLY document has a cite. Three candidate
rules are with the PM (below). None of them takes any caselist near the shrink guard's 10%; only
"no cite, any length" would, and it is not proposed. Nothing in the code has changed.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| `card-only` | In progress | Counts taken and sent; the rule waits for the PM's ruling |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: tallies by cite, word band and tag, per caselist, counts only, sent to the PM before any rule | PASS | [The counts](#the-counts), sent 2026-10-22 as a relay prompt; no code changed before it |
| ac2: the ruled rule leaves excluded documents out of the build, red first, excluded count in the build summary and the run record | NOT RUN | Waiting for the PM's ruling |
| ac3: the dev index's document count before and after, in `docs/data/evidence-search-pilot.md` (operator) | NOT RUN | After the merge, an operator step |
| Node `card-only`: `uv run pytest packages/debate_core/tests/application -k search_index` | NOT RUN | Waiting for the PM's ruling |

## The counts

Read-only, on the operator's Mac, by this session (working agreement 2): the newest directory under
`~/.debate-research/dev/tub-index/`, `767b9c7c056b80cb`, parser `2026.10.20-docx-6`, latest snapshot
2026-10-20, 52,059 documents, opened `mode=ro`. The tally took 2.8 s wall-clock; the follow-up
counts below took 2.8 to 6.8 s each. Each script printed caselist slugs and numbers, never a field's
text; the scripts stayed in the session's scratch directory.

How a document was counted, from its `documents` row (the representative's card):

* **Cite present:** `cite` holds something besides whitespace. The column is `NOT NULL`, and "no
  cite" is the parser's empty `full_cite`.
* **Tag present:** `tag` is not null and not blank.
* **Words:** `len(text.split())` over `text`, the representative's evidence text. A CITE_ONLY card's
  text is empty, so it is 0 words.

### Every document, by word band

| Caselist | 0 | 1–9 | 10–24 | 25–49 | 50–99 | 100+ | All |
|---|---:|---:|---:|---:|---:|---:|---:|
| hsld26 | 366 | 103 | 161 | 252 | 604 | 11,739 | 13,225 |
| hspf26 | 297 | 62 | 92 | 295 | 740 | 9,907 | 11,393 |
| hspolicy26 | 558 | 79 | 107 | 304 | 1,049 | 19,498 | 21,595 |
| openev | 70 | 15 | 21 | 41 | 242 | 5,457 | 5,846 |
| All | 1,291 | 259 | 381 | 892 | 2,635 | 46,601 | 52,059 |

### Cite present or absent

| Caselist | Cite | 0 | 1–9 | 10–24 | 25–49 | 50–99 | 100+ | All |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| hsld26 | yes | 366 | 41 | 78 | 148 | 404 | 10,705 | 11,742 |
| hsld26 | no | 0 | 62 | 83 | 104 | 200 | 1,034 | 1,483 |
| hspf26 | yes | 297 | 16 | 42 | 127 | 452 | 7,731 | 8,665 |
| hspf26 | no | 0 | 46 | 50 | 168 | 288 | 2,176 | 2,728 |
| hspolicy26 | yes | 558 | 42 | 68 | 227 | 843 | 18,210 | 19,948 |
| hspolicy26 | no | 0 | 37 | 39 | 77 | 206 | 1,288 | 1,647 |
| openev | yes | 70 | 5 | 14 | 36 | 215 | 5,150 | 5,490 |
| openev | no | 0 | 10 | 7 | 5 | 27 | 307 | 356 |
| All | yes | 1,291 | 104 | 202 | 538 | 1,914 | 41,796 | 45,845 |
| All | no | 0 | 155 | 179 | 354 | 721 | 4,805 | 6,214 |

### Tag present or absent

| Caselist | Tag | 0 | 1–9 | 10–24 | 25–49 | 50–99 | 100+ | All |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| hsld26 | yes | 201 | 99 | 148 | 231 | 574 | 11,451 | 12,704 |
| hsld26 | no | 165 | 4 | 13 | 21 | 30 | 288 | 521 |
| hspf26 | yes | 188 | 57 | 88 | 277 | 684 | 9,284 | 10,578 |
| hspf26 | no | 109 | 5 | 4 | 18 | 56 | 623 | 815 |
| hspolicy26 | yes | 417 | 75 | 104 | 293 | 1,020 | 19,307 | 21,216 |
| hspolicy26 | no | 141 | 4 | 3 | 11 | 29 | 191 | 379 |
| openev | yes | 57 | 15 | 21 | 41 | 240 | 5,417 | 5,791 |
| openev | no | 13 | 0 | 0 | 0 | 2 | 40 | 55 |
| All | yes | 863 | 246 | 361 | 842 | 2,518 | 45,459 | 50,289 |
| All | no | 428 | 13 | 20 | 50 | 117 | 1,142 | 1,770 |

### No cite and fewer than 25 words: the spec's example shape

| Caselist | 1–9 | 10–24 | Together | Share of the caselist |
|---|---:|---:|---:|---:|
| hsld26 | 62 | 83 | 145 | 1.1% |
| hspf26 | 46 | 50 | 96 | 0.8% |
| hspolicy26 | 37 | 39 | 76 | 0.4% |
| openev | 10 | 7 | 17 | 0.3% |
| All | 155 | 179 | 334 | 0.6% |

There are none at 0 words: a document with no cite always has text.

### What the counts say about shape

* **Every document with no cite has a tag** (6,214 of 6,214), and every CITE_ONLY document has a cite
  (1,291 of 1,291). So a CITE_ONLY document can never meet a "no cite" rule.
* **Completeness:** 50,768 FULL, 0 ABBREVIATED, 1,291 CITE_ONLY. The 0-word band is exactly the
  CITE_ONLY documents. No occurrence in the index is ABBREVIATED either (332,321 FULL, 3,343
  CITE_ONLY occurrence rows).
* **Cite present but the parser read no short cite:** 15,023 documents, 13,261 of them with 100+
  words. Most are real cards, so an unreadable short cite on its own does not mark a non-card.

### The coach's example

Counted read-only by matching the public resolution's wording, "negate" with "outer space
colonization is a moral imperative", in each document's tag and text, whitespace and case folded.
Counts only. Four documents, all hsld26, and the sentence is in the **tag** of each, never the text:

| Completeness | Text words | Cite words | Short cite readable | Year in cite | URL in cite | Documents |
|---|---|---|---|---|---|---:|
| CITE_ONLY | 0 | 1–9 | no | no | no | 1 |
| CITE_ONLY | 0 | 10–24 | yes | no | no | 1 |
| FULL | 100+ | 0 (no cite) | no | no | no | 1 |
| FULL | 25–49 | 25–49 | yes | no | no | 1 |

The coach saw a card whose whole content was that one line. The likeliest of the four is the first
CITE_ONLY document: the sentence as a tag, a short line under it that the parser took for a cite (no
short cite, no year, no URL), and no text. None of the four has no cite and fewer than 25 words.

### CITE_ONLY documents by what their cite looks like

| Caselist | CITE_ONLY | No readable short cite | …and no year and no URL in the cite |
|---|---:|---:|---:|
| hsld26 | 366 | 241 | 117 |
| hspf26 | 297 | 78 | 14 |
| hspolicy26 | 558 | 325 | 84 |
| openev | 70 | 39 | 25 |
| All | 1,291 | 683 | 240 |

"Year" is a four-digit 19xx or 20xx standing alone in the cite; "URL" is `http` anywhere in it.

### Candidate rules, per caselist (documents excluded, and share of the caselist)

| Caselist | Documents | A: no cite, under 25 words | B: A, or CITE_ONLY whose cite has no readable short cite, no year and no URL | C: A, or any CITE_ONLY | No cite at any length (not proposed) |
|---|---:|---:|---:|---:|---:|
| hsld26 | 13,225 | 145 (1.1%) | 262 (2.0%) | 511 (3.9%) | 1,483 (11.2%) |
| hspf26 | 11,393 | 96 (0.8%) | 110 (1.0%) | 393 (3.4%) | 2,728 (23.9%) |
| hspolicy26 | 21,595 | 76 (0.4%) | 160 (0.7%) | 634 (2.9%) | 1,647 (7.6%) |
| openev | 5,846 | 17 (0.3%) | 42 (0.7%) | 87 (1.5%) | 356 (6.1%) |
| All | 52,059 | 334 (0.6%) | 574 (1.1%) | 1,625 (3.1%) | 6,214 (11.9%) |

Against the shrink guard's 10%, measured against the current index: A, B and C stay under it in
every caselist. Only "no cite at any length" passes it, in hsld26 and hspf26, and it would also drop
4,805 documents of 100 words or more, most of them likely real evidence whose cite the parser
missed.

**Judged on the representative.** Every count above is of the representative's card, the only one
the index stores. A CITE_ONLY representative means every member of its cluster is CITE_ONLY, since
completeness is the first key of the representative order. A representative with no cite says
nothing about its siblings: of rule A's 334 documents, 193 have one occurrence and 141 have several
(17 in one file, 124 across files; hsld26 62, hspf26 35, hspolicy26 42, openev 2). Whether a sibling
has a cite is not in the index; the occurrence table carries no cite.

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

<!-- Choices the spec left open, with the reasoning. -->

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

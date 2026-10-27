<!-- docs-index: Where the labelled parser evaluation's missed cites, tags and highlights go: the docx-6 re-measure beside 2026-10-20's baseline, and tallies before any rule -->
# Parser evaluation gaps: the re-measure and the tallies (October 2026)

Task [`v1-e31-t31-labelled-evaluation-gaps`](../../plan_specs/v1/e31-debate-file-parsing/t31-labelled-evaluation-gaps.yaml).
This document holds two things, both measured before any parser rule changed:

* the 2026-10-20 baseline's tiers re-measured on parser `2026.10.20-docx-6` (ac1);
* where the labelled rows the parser misses go (ac2): for every labelled row whose gold unit is
  `CITE` or `TAG`, or that carries a labelled highlight, and that the parser read otherwise.

Counts only. Nothing here holds card text, a school, a team code, a file name or a person's name.
A file is named, where it must be, by the first 16 hex digits of its keyed digest, as
[`MANIFEST.md`](../../tests/fixtures/debate_files/eval/MANIFEST.md) names it. The baseline it is
compared with is [`parser-eval-2026-10.md`](parser-eval-2026-10.md).

## Re-measured on docx-6 (2026-10-27)

`uv run python scripts/run_parser_eval.py --tier both`, without `--write-baseline`, over the 30
labelled files on the operator's Mac, read-only: 2.9 s. The gate passed for both tiers against the
committed `docx-5` baseline.

**Every figure in the 2026-10-20 report is unchanged.** The whole report rendered from this run was
compared with `parser-eval-2026-10.md` line by line. The only lines that differ are the parser
version, the gate's status, and the gate's note: "no baseline" then, "baseline recorded for docx-5"
now. `docx-6` (`v1-e31-t24`) changed no reading of a labelled row.

### Targets, full tier (1,851 labelled rows of 5,763)

| Group | Metric | Target | 2026-10-20, `docx-5` | 2026-10-27, `docx-6` |
|---|---|---|---|---|
| template:verbatim | TAG F1 | 0.97 | 0.950 | 0.950 |
| template:verbatim | CITE F1 | 0.97 | 0.751 | 0.751 |
| template:verbatim | EVIDENCE F1 | 0.97 | 0.934 | 0.934 |
| template:verbatim | POCKET F1 | 0.95 | 1.000 | 1.000 |
| template:verbatim | HAT F1 | 0.95 | 1.000 | 1.000 |
| template:verbatim | BLOCK F1 | 0.95 | 0.985 | 0.985 |
| template:verbatim | ANALYTIC F1 | 0.85 | 0.872 | 0.872 |
| template:verbatim | span F1 | 0.99 | 0.971 | 0.971 |
| template:non-verbatim | TAG F1 | 0.90 | 0.908 | 0.908 |
| template:non-verbatim | CITE F1 | 0.90 | 0.796 | 0.796 |
| template:non-verbatim | EVIDENCE F1 | 0.90 | 0.908 | 0.908 |

### Precision and recall, full tier, overall

| Unit | Support | Precision, `docx-5` | Precision, `docx-6` | Recall, `docx-5` | Recall, `docx-6` |
|---|---|---|---|---|---|
| TAG | 173 | 0.952 | 0.952 | 0.919 | 0.919 |
| CITE | 215 | 0.985 | 0.985 | 0.623 | 0.623 |
| EVIDENCE | 1054 | 0.971 | 0.971 | 0.882 | 0.882 |
| ANALYTIC | 81 | 0.845 | 0.845 | 0.741 | 0.741 |

Highlight F1, overall: 0.973 then and now. Format PF: 0.759 then and now.

### Targets, PR subset (410 labelled rows, the whole of six files)

| Group | Metric | Target | 2026-10-20, `docx-5` | 2026-10-27, `docx-6` |
|---|---|---|---|---|
| template:verbatim | TAG F1 | 0.97 | 0.952 | 0.952 |
| template:verbatim | CITE F1 | 0.97 | 0.762 | 0.762 |
| template:verbatim | EVIDENCE F1 | 0.97 | 0.895 | 0.895 |
| template:verbatim | span F1 | 0.99 | 0.808 | 0.808 |
| template:non-verbatim | TAG F1 | 0.90 | 0.850 | 0.850 |
| template:non-verbatim | CITE F1 | 0.90 | 0.882 | 0.882 |
| template:non-verbatim | EVIDENCE F1 | 0.90 | 0.978 | 0.978 |

PR subset, overall: CITE precision 0.969, recall 0.705; TAG precision 0.949, recall 0.861, then
and now.

## Where the misses go (full tier, `docx-6`)

`uv run python scripts/tally_missed_units.py --tier full`, 3.0 s, read-only. Its module is
[`tests/evals/parser/missed_units.py`](../../tests/evals/parser/missed_units.py). "Above" and
"below" mean the nearest paragraph that says something, stepping over blank lines and page
furniture as the parser's assembly does. A rule is named by its family, the part of its id before
the first colon.

**"By caselist":** the evaluation's caselist files are all from one caselist, `hsld26` (LD), so a
breakdown by caselist is the breakdown by source below (team, caselist, camp).

### Cites: 81 of 215 labelled rows missed

**What students see is a card with no source.** 135 labelled cards lie wholly inside a labelled
block. Of them:

| Cards | As read |
|---|---|
| Every cite row read as a cite | 72 |
| Some of the cite read, some not | 32 |
| **No cite row read at all** | **31** |

Of the 81 missed rows, 31 belong to a card none of whose cite was read, 34 to a card whose cite was
read in part, and 16 to no card the labels can judge (a card that runs past its labelled block).

**What they were read as, and by which rule**

| Read as | Rule | Rows |
|---|---|---|
| OTHER | `heuristic-unclassified-paragraph` | 61 |
| OTHER | `verbatim-alias-id` (a style the profile maps to nothing) | 3 |
| EVIDENCE | `heuristic-marked-up-body-text` | 11 |
| EVIDENCE | `heuristic-prose-paragraph` | 2 |
| TAG | `heuristic-direct-formatted-heading-tag` | 2 |
| TAG | `verbatim-style-id` (the tag style) | 2 |

**By source, template family and format**

| | Read as OTHER | Read as EVIDENCE | Read as TAG | All |
|---|---|---|---|---|
| source: team | 29 | 9 | 0 | 38 |
| source: camp | 28 | 4 | 3 | 35 |
| source: caselist (`hsld26`) | 7 | 0 | 1 | 8 |
| family: verbatim | 39 | 6 | 1 | 46 |
| family: cardmirror | 13 | 0 | 2 | 15 |
| family: other-heuristic | 9 | 6 | 1 | 16 |
| family: wiki-converted | 3 | 1 | 0 | 4 |
| format: Policy | 28 | 4 | 3 | 35 |
| format: PF | 22 | 6 | 0 | 28 |
| format: LD | 14 | 3 | 1 | 18 |

**Where they stand.** The line above, labelled and as read:

| Above: labelled, read as | Rows |
|---|---|
| CITE, CITE: **a later line of a cite whose first line was read** | 36 |
| TAG, TAG: **the line under a tag** | 28 |
| CITE, OTHER: a third or later line of a cite | 10 |
| TAG, ANALYTIC: the line under a tag the assembly demoted | 4 |
| other | 3 |

Below, 54 have a body read as body, 10 another cite line read as nothing and 9 a body read as
nothing.

**What they look like**

| | Rows |
|---|---|
| Hold a link | 59 |
| Hold a year | 63 |
| Name and year at the head (the classifier's 40 characters) | 12 |
| Name and year further in | 21 |
| No name and year | 48 |
| Neither underlined nor highlighted | 70 |
| Underlined, not highlighted | 7 |
| Highlighted | 4 |
| Up to 100 characters / 101 to 400 / over 400 | 17 / 53 / 11 |
| Bold as Word shows it | 6 |

### Tags: 14 of 173 labelled rows missed

| Read as | Rule | Rows | Where |
|---|---|---|---|
| EVIDENCE | `heuristic-marked-up-body-text` | 5 | wiki-converted 4, cardmirror 1 |
| EVIDENCE | `heuristic-prose-paragraph` | 3 | wiki-converted 3 |
| ANALYTIC | `assembly-tag-without-cite-or-evidence` | 4 | cardmirror 2, other-heuristic 1, verbatim 1 |
| CITE | `verbatim-cite-run-style` | 1 | verbatim, PF |
| HAT | `verbatim-style-id` | 1 | other-heuristic, PF |

By source: caselist 9 (all LD; the 7 wiki-converted rows are in this source's wiki-converted
files), camp 3, team 2. By format: LD 9, Policy 3, PF 2.

**4 of the 14 are caused by a missed cite.** Each of the 4 analytics is a tag whose cite below it was
read as a second tag, so the assembly found nothing under the tag and demoted it. Every one of the
14 is bold as Word shows it; 6 are underlined; none holds a link.

### Highlight: nothing missed, 707 characters added, all in one file

Over the 336 sampled span rows, **the parser missed no labelled highlight character.** Every error
is an added highlight, and all of them are in one coach-reviewed team file, `a888a5db95488218`
(PF, Verbatim, in the PR subset):

| Run's highlight colour | Characters the labels call unhighlighted |
|---|---|
| cyan (a reading colour) | 449 |
| green (a reading colour) | 71 |
| white (the profile: not a reading colour) | 187 |

177 of the white characters are in body paragraphs and 10 in a cite. The runs carry a plain
`w:highlight`, outside any tracked change, and nothing in their properties hides them. The
labelling guide says "Highlight is any highlight colour", so the cyan and green characters are a
question for the coach, not for a rule. White is invisible on the page, and the guide does not say
how to label it.

This one file is the whole of format PF's highlight F1 of 0.759, team's 0.901 and the PR subset's
Verbatim 0.695.

## Candidate shapes, and what each would score

A shape is what a rule could take, as the parser sees the file. Each is counted over **every
labelled row whatever its gold unit**, so a shape's `CITE` rows are what it could add to recall and
its other rows are what it would cost in precision. The scores beside them are the harness's own
`score_file`, with the shape's paragraphs read as cites. A tag the assembly demoted only for want of
a cite is given back when a cite under it is read. Card boundaries stay as the parser drew them, so
these are unit and span scores only.

| Shape | Labelled CITE | Labelled other |
|---|---|---|
| Second line of a cite, read as nothing (directly under a line read as a cite, directly over a body), no guard | 23 | EVIDENCE 3, UNDERTAG 1 |
| **(1) The same, holding a link or a year** | **23** | **0** |
| (1′) Every line between a cite and a body read as nothing, holding a link or a year | 33 | EVIDENCE 1 |
| **(2) Line under a tag, read as nothing, over a body, holding a link or a year** | **19** | **0** |
| (3) Line under a tag, read as body, no longer than 400 characters, over a body, with a link, not highlighted | 2 | 0 |
| **(4) Line read as a second tag under a tag, name and year at its head, over a body** | **4** | **0** |

By family: (1) verbatim 22, other-heuristic 1; (2) other-heuristic 8, cardmirror 4, verbatim 4,
wiki-converted 3; (3) other-heuristic 2; (4) cardmirror 2, other-heuristic 1, verbatim 1.

### What-if scores, full tier, overall

| | CITE P | CITE R | CITE F1 | TAG P | TAG R | TAG F1 | ANALYTIC F1 | Cards with no cite read |
|---|---|---|---|---|---|---|---|---|
| As read | 0.985 | 0.623 | 0.763 | 0.952 | 0.919 | 0.935 | 0.789 | 31 |
| (1) | 0.987 | 0.730 | 0.840 | 0.952 | 0.919 | 0.935 | 0.789 | 31 |
| (1), no guard | 0.963 | 0.730 | 0.831 | 0.952 | 0.919 | 0.935 | 0.789 | 31 |
| (1′) | 0.982 | 0.777 | 0.868 | 0.952 | 0.919 | 0.935 | 0.789 | 31 |
| (2) | 0.987 | 0.712 | 0.827 | 0.952 | 0.919 | 0.935 | 0.789 | 13 |
| (3) | 0.986 | 0.633 | 0.771 | 0.952 | 0.919 | 0.935 | 0.789 | 29 |
| (4) | 0.986 | 0.642 | 0.778 | 0.976 | 0.942 | 0.959 | 0.811 | 28 |
| **(1) + (2) + (3) + (4)** | **0.989** | **0.847** | **0.912** | **0.976** | **0.942** | **0.959** | **0.811** | **8** |
| (1′) + (2) + (3) + (4) | 0.985 | 0.893 | 0.937 | 0.976 | 0.942 | 0.959 | 0.811 | 8 |

With all four, cards whose cite is read in full go from
72 to 116, and those read in part from 32 to 11 (with (1′), 125 and 2). EVIDENCE F1 is 0.925 with
(3), 0.924 without; no other unit moves.

**Against the targets**, with (1) + (2) + (3) + (4):

| Group | Metric | Target | As read | With the four |
|---|---|---|---|---|
| template:verbatim | CITE F1 (precision) | 0.97 | 0.751 (0.979) | 0.895 (0.985) |
| template:verbatim | TAG F1 (precision) | 0.97 | 0.950 (0.946) | 0.977 (0.973) |
| template:non-verbatim | CITE F1 (precision) | 0.90 | 0.796 (1.000) | 0.956 (1.000) |
| template:non-verbatim | TAG F1 (precision) | 0.90 | 0.908 (0.964) | 0.924 (0.982) |

With (1′) in place of (1), Verbatim CITE F1 is 0.929, but its precision falls from 0.9794 to
0.9787.

**PR subset** (the gate's tier), with the four: CITE precision 0.969 to 0.973, recall 0.705 to 0.818;
TAG precision 0.949 to 0.974, recall 0.861 to 0.884; non-Verbatim CITE F1 0.882 to 1.000, TAG F1
0.850 to 0.900; Verbatim CITE F1 0.762 to 0.791. No unit's F1 falls. Cards with no cite read: 8
of 38 to 4. With (1′) the subset's figures are the same.

**White highlight not read as highlight:** highlight F1 overall 0.973 to 0.980, Verbatim span F1
0.971 to 0.974, PR subset Verbatim highlight F1 0.695 to 0.756. No unit score moves.

**Left after the four:** 33 cite rows. 11 are a later cite line read as nothing that the guard or
the body test turns away, 10 are third or later lines (taken by (1′) alone), 11 are read as body
(7 of them under a tag), and 1 is another shape. 10 tag rows: the 8 read as body (7 wiki-converted,
1 CardMirror), the 1 read as a hat and the 1 read as a cite. (4) gives all 4 demoted tags back.

## Context: the dev index's documents with no cite

The PM's note gives the dev index of 2026-10-22 (`767b9c7c056b80cb`, parser `docx-6`, 52,059
documents): 6,214 documents have no cite, and 4,805 of them have 100 or more words. Each document is
counted here by the template family of its representative's source file, as
`scripts/survey_docx_styles.py` classifies it. The count is read-only, over the index opened
`mode=ro` and the 2,679 source files on the operator's Mac, and took 10 s. Both totals reproduce.

| Family | No cite | Of them 100+ words | Source files |
|---|---|---|---|
| other-heuristic | 3,105 | 2,375 | 1,165 |
| cardmirror | 2,505 | 1,941 | 1,302 |
| verbatim | 510 | 422 | 178 |
| wiki-converted | 94 | 67 | 34 |
| All | 6,214 | 4,805 | 2,679 |

| Caselist | other-heuristic | cardmirror | verbatim | wiki-converted |
|---|---|---|---|---|
| hsld26 | 426 (283) | 805 (575) | 201 (148) | 51 (28) |
| hspf26 | 2,365 (1,867) | 220 (182) | 108 (96) | 35 (31) |
| hspolicy26 | 252 (184) | 1,277 (1,001) | 110 (95) | 8 (8) |
| openev | 62 (41) | 203 (183) | 91 (83) | 0 (0) |

In brackets: of them, 100 or more words. The labelled evaluation's cite gap is mostly in Verbatim
files' second cite lines (shape (1)), but the index's cards with no cite come mostly from
other-heuristic and CardMirror files, where the labelled cites missed sit under a tag (shape (2)).
How many index documents each shape would give a cite is not counted here: that needs a re-parse
of the store.

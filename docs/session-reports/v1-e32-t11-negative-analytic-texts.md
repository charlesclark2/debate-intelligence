# Session report: v1-e32-t11-negative-analytic-texts

| | |
|---|---|
| Task | `v1-e32-t11-negative-analytic-texts` — Counterplan texts, kritik alternatives and overviews in the landscape report |
| Spec | [`plan_specs/v1/e32-argument-landscape/t11-negative-analytic-texts.yaml`](../../plan_specs/v1/e32-argument-landscape/t11-negative-analytic-texts.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t11-negative-analytic-texts` |
| Session status | PARTIAL: built and tested; the operator's first cache fill and the dry run are next <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Built, after the PM's rulings of 2026-10-24.** The landscape report now quotes each CP's texts and
each K's alternatives and roles of the ballot, and counts each position's overviews, on synthetic
sources against hand-written golden files.

* **CP texts:** by label, and as the first `should` analytic of a block whose nearest placed heading is
  a CP the team reads, past the actor guard (ruling 1). The guard's actors are config:
  `config/landscape/analytic_texts/policy-2026-27-nhi.yaml`.
* **The top 3 texts per CP and K**, with their team counts, then "and N more texts, read by M teams"
  (ruling 4). Texts are grouped by their normalized words. A text naming a school of the caselist is
  withheld and counted.
* **Overviews are counted only** (ruling 3): per position, the teams with one on each side, and no
  overview text in the cache or the report.
* **Every label found is counted** by where it went. So the report states how many it could not place,
  and a kind that shows almost nothing (roles of the ballot) says so (ruling 2).
* **The cache** holds derived fields only, beside t09's, keyed as ruled (ruling 5). The texts to quote
  are read again in memory and checked against their digests.
* **Tests were shown failing first**, and 21 targeted mutants on the withholding rule, the placement
  rule and the guard were all caught, after one new test ([below](#mutants)).

**What is left:**
* **The first fill of the new cache** is the operator's (about 2 minutes over 8 workers;
  [the block](#operator-follow-ups)).
* **Then the dry run on hspolicy26**, without `--publish`, with its runtime and the scan's hits by
  section. I run it once the cache is warm.
* **The Goal stays InProgress** until both are recorded. Every criterion is otherwise met.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| negative-texts | In progress: built and tested; the dry run on hspolicy26 waits on the operator's first cache fill | The counts (2026-10-24), the PM's rulings (2026-10-24), then the reader, the cache, the config, the report's sections and golden, the service, the run's seam and wiring, the operator script and the guide |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any rule, per kind, of documents with a CP-text, alternative, role-of-the-ballot or overview label and the paragraph under it, sent to the PM with the proposed labels | PASS | [The counts](#the-counts-hspolicy26-through-2026-10-20), [the proposed labels](#the-proposed-labels), [the questions](#questions-for-the-pm), sent 2026-10-24 and ruled on the same day. Nothing was built before the ruling |
| ac2: after the ruling, on synthetic sources, the report shows each CP's and K's distinct texts with their team counts and each position's most common overview (ruling 3: overview counts, no text), matching hand-written golden files; a text never beside a school or team code; tests shown failing first | PASS | `tests/fixtures/landscape/golden/report.md`'s two new sections, hand-written from the hand-written `synthetic_caselist/analytic_texts.json`, matched on the renderer's first run (`test_rendering_the_fixture_matches_the_golden_file[report.md]`). The red runs: [below](#checks-shown-failing-for-their-reason). Never beside a school or team code: `test_texts_a_text_is_never_beside_a_school_or_team_code`, the golden's scan test, and the run's test that the texts are in report.md and no other file (Deviations 1 for the overview clause) |
| negative-texts node: `uv run pytest packages/debate_core/tests/application/test_landscape_report.py` | PASS | `.venv/bin/python -m pytest packages/debate_core/tests/application/test_landscape_report.py -q -p no:randomly` under `perl -e 'alarm 100'` → 65 passed (52 before this task) |
| PM ruling 1: how many of the 163 the guard keeps, and one test of a `should` analytic it refuses | PASS in part | The refused test: `test_the_actor_guard_refuses_a_should_analytic_naming_no_actor_and_counts_it` (and the twelve-word and whole-word cases). With the committed actor list, measured in memory on the counts' 163: **158 kept, 5 refused**, all 5 theory analytics ("our counter interpretation is that we should ...", "logical policy maker is a neg argument"). The count from the built reader on the real store comes from the operator's fill ([pending](#operator-follow-ups)) |
| PM: the dry run on hspolicy26 without `--publish`, with counts, its runtime and the scan's hits by section | NOT RUN | Waits on the operator's first cache fill: a dry run writes no cache, so on a cold cache it would parse every source and keep nothing |

## The counts (hspolicy26, through 2026-10-20)

**How they were read.** Every pass was read-only:
* before each one, no `DEBATE_*` variable was set and no `caselist pull` was running (both checked
  by the script, which stops otherwise);
* each ran under `perl -e 'alarm 115'` on the interpreter, and each parent killed its own pool at
  100 s;
* the load average was 4 to 13 on 11 cores, from other sessions, so the pools ran 6 workers.

The scripts are scratch files outside the repository. They printed counts only.

* **The sources:** t02's reader (`read_seed_sources`), parser version `2026.10.20-docx-6`, through
  2026-10-20. `LandscapeStalenessCheck.newest_snapshot` gives that date as the newest weekly snapshot.
  * 3,825 sources are on the topic, all DOCX;
  * **negative:** 2,070 documents with a live negative disclosure, by 392 teams;
  * **affirmative:** 1,770 documents, by 552 teams.
* **The raw re-read** is t09's pattern: each blob parsed in memory by the code's parser (the store's
  version) under a placeholder path. All 3,825 parsed: 0 refused, 0 missing.
  * The workers returned candidate paragraphs in memory.
  * The parent normalized each with the team's own names and the caselist's schools taken out, and
    placed it.
  * The scratch files hold only units, element indexes, word counts, digests, placement ids and the
    normalized form of short labels. No paragraph text.
* **A candidate label** is a non-evidence paragraph of at most 8 words holding a label word (`text`,
  `alt`, `alternative`, `rob`, `role`, `ballot`, `overview`, `ov`, ...). It can also be a paragraph
  opening with an inline label (`Text:`, `CP:`, `Alt:`, `ROB:`, `Overview:`) or with a sentence label
  (`The alternative is`, `The role of the ballot is`).
* **Placed** means the label's nearest placed heading by t02's matcher. That is the label's own
  `section_path`, cut as `heading_path` cuts a card's, each heading normalized as the matcher reads
  it, with the coach's overrides. It is the rule the report counts cards by:
  * **under no heading:** every heading over it normalizes to nothing (`1NC`, `OFF`), or there is
    none;
  * **under headings that place nothing:** headings are there, and none is an alias or an override.
  * Neither is ever guessed.
* **Teams** are the disclosing teams' opaque identities, on the side named. A document's side is its
  disclosures' side.
* **The paragraph under it:** for a label on its own, the next written paragraph; for an inline or
  sentence label, the paragraph itself. "Kept" means inside a card the store holds.

### What each kind's labels look like

The labels the raw sources show, with their documents and teams, are under
[the proposed labels](#the-proposed-labels). The tables below use the proposed list.

### CP texts

| Count | Paragraphs | Documents | Teams |
|---|---|---|---|
| Negative documents with a CP-text label | 76 | **68** | **37** |
| `Text:` opening a paragraph with `should` | | 54 | 28 |
| `CP:` opening a paragraph with `should` | | 7 | 3 |
| `CP Text:` with `should` | | 3 | 2 |
| `Counterplan:` with `should` | | 2 | 2 |
| `Text` on its own | | 2 | 2 |
| Affirmative documents with one (quoted CP texts) | | 2 | 2 |
| **The label's unit:** analytic (inline) / other (inline) / analytic / block | 70 / 4 / 1 / 1 | | |
| **What holds the text:** an analytic with `should`, not kept / other, not kept / a stored tag / a block | 70 / 4 / 1 / 1 | | |
| **Placed:** on a CP, READS | 10 | **10** | **7** |
| Placed on a DA, READS | 2 | 2 | 1 |
| Under headings that place nothing | 39 | 34 | 20 |
| Under no heading | 25 | 22 | 14 |

**For comparison, the CP text by its place, with no label.** The rule is the first paragraph with
`should` in a block whose nearest placed heading is a CP, READS. It finds 210 paragraphs:
* 163 analytics, not kept;
* 45 stored tags;
* 2 other.

| Count | Documents | Teams |
|---|---|---|
| Analytic, not kept (the CP text the store drops) | **133** | **56** |
| Of those, also holding a CP-text label placed on a CP | 7 | |
| Documents with a placed CP-text label and no such paragraph | 3 | |

Read again in memory (below), all 163 have at most 12 words before `should`. 146 open with "The
fifty" (68), "The United" (58) or "The 50" (20), and 7 more with an inline "Text: The". That is the
shape of a CP text. t03 counted 322 CP documents in the store, by their placed cards.

### K alternatives

| Count | Paragraphs | Documents | Teams |
|---|---|---|---|
| Negative documents with an alternative label | 555 | **452** | **185** |
| `The alternative is ...` | | 307 | 143 |
| `The alt is ...` | | 56 | 33 |
| `Our alternative is ...` | | 37 | 24 |
| `Alt` on its own | | 52 | 37 |
| `Alternative` on its own | | 15 | 9 |
| `Alt: <name>` as a heading (left out, below) | | 19 | 11 |
| `Alt:` / `The alt:` / `Alternative:` opening a tag or analytic | | 17 | 10 |
| Affirmative documents with one | | 67 | 46 |
| **The label's unit:** tag (sentence) / block / block (`Alt: <name>`) / tag (inline) / analytic / hat / other | 411 / 84 / 22 / 15 / 14 / 7 / 2 | | |
| **What holds the text:** a **stored card tag** / a block / an analytic, not kept / a hat / nothing / other | **480** / 47 / 15 / 5 / 5 / 3 | | |
| **Placed:** on a K, READS | 95 | **72** | **33** |
| Placed on an advantage | 1 | 1 | 1 |
| Under no heading | 237 | 212 | 107 |
| Under headings that place nothing | 222 | 188 | 104 |

**The store already holds most alternatives:** 480 of the 555 paragraphs are stored card tags.
t03's report called the alt's own text an analytic. For the "Alt" block that is sometimes true, but
the commonest form is a card's tag, "The alternative is ...", that the store keeps.

### Roles of the ballot

| Count | Paragraphs | Documents | Teams |
|---|---|---|---|
| Negative documents with a role-of-the-ballot label | 38 | **30** | **24** |
| `The role of the ballot is ...` | | 15 | 13 |
| `Role of the ballot` on its own | | 9 | 7 |
| `The role of the judge is ...` | | 4 | 3 |
| `Role of judge`, `ROJ`, `Role of the judge`, `ROB`, inline `Role of the ballot:`, `The role of the ballot should` | | 3, 2, 2, 1, 1, 1 | |
| Affirmative documents with one (K affs) | | 19 | 15 |
| **The label's unit:** block / analytic / tag / hat | 13 / 14 / 8 / 3 | | |
| **What holds the text:** an analytic, not kept / a stored tag / a block | 18 / 12 / 8 | | |
| **Placed:** on a K, READS | 1 | **1** | **1** |
| Under headings that place nothing | 28 | 23 | 20 |
| Under no heading | 9 | 9 | 9 |

### Overviews (both sides)

| Count | Negative | Affirmative |
|---|---|---|
| Documents / teams with an overview label | **335 / 94** | **159 / 52** |
| `O/V` | 120 / 45 | |
| `Overview` | 110 / 47 | |
| `OV` | 24 / 18 | |
| `OVW` | 5 / 2 | |
| Compound: `Impact overview`, `Link O/V`, `Midterms DA overview`, `Overview – Cap K` | 191 / 60 | |
| **The label's unit:** block / other / hat / pocket / tag | 624 / 11 / 4 / 1 / 1 | |
| **What is directly under it** (neg paragraphs): another heading / a stored tag / an analytic / evidence / other or nothing | 305 / 257 / 63 / 11 / 5 | |
| **Until the next heading:** nothing / cards only / analytics | 314 / 246 / 81 | 386 / 27 / 54 |
| Analytic words under it: median, 90th percentile, longest | 32, 97, 278 | 71, 141, 294 |

**Placement** (paragraphs, documents, teams):

| Nearest placed heading | Negative | Affirmative |
|---|---|---|
| A DA, READS | 210, 136, 50 | 20, 20, 15 |
| A CP, READS | 81, 70, 36 | 1, 1, 1 |
| A K, READS | 25, 16, 11 | 4, 4, 4 |
| A T, READS | 18, 16, 12 | 1, 1, 1 |
| An advantage, READS | 15, 9, 7 | **196, 63, 19** |
| A DA, ANSWERS | 1, 1, 1 | |
| Headings that place nothing | 237, 157, 67 | 187, 88, 30 |
| No heading | 54, 42, 25 | 58, 38, 17 |

**Compound labels** (both sides, 669 paragraphs) beyond the overview word:
* 189 are a part of the position: impact, link, uniqueness, solvency, alt;
* **127 name an alias themselves** (`midterms da overview`), and 30 of those have nothing placed
  above them. The matcher does not place a label by its own words, so those 30 are left out;
* 353 are other words.

**The most common overview.** This is the first paragraph under the label, over 8 words, grouped by
its normalized words, under a placed position (READS):

| | Negative | Affirmative |
|---|---|---|
| Positions with an overview | 16 (7 DAs, 4 CPs, 2 Ts, 2 advantages, 1 K) | 6 (3 advantages, 3 DAs) |
| Teams | 39 | 7 |
| Positions whose most common overview is read by 1 team | **13** | **6** |
| ... by 2 teams | 2 | 0 |
| ... by 3 or more | 1 (midterms-da: 20 teams, 26 distinct, the top one 3 teams) | 0 |

**What aff overviews would add:** 3 advantages (costs, disease, inequality) and 3 DAs read in
affirmative files. That is 7 teams, and every most common overview is one team's.

### Distinct texts per position (for the cut-off)

These are grouped by normalized words, as t09 grouped plan texts, under a placed position, READS. A
team counts once per text.

| Kind and rule | Positions | Team-position pairs | Distinct texts | Read by one team | Pairs on the top 1 / 3 / 5 texts |
|---|---|---|---|---|---|
| CP texts by label | 3 | 6 | 8 | 8 | 3 / 6 / 6 |
| **CP texts by place** (the comparison rule) | 8 | 75 | 64 | 53 | 28 / **42** / 50 |
| K alternatives by label | 5 | 33 | 47 | 40 | 9 / **13** / 17 |
| Roles of the ballot | 1 | 1 | 1 | 1 | 1 / 1 / 1 |

Per position (teams, distinct texts, teams on the top texts):

| Position | Teams | Distinct | Top texts |
|---|---|---|---|
| states-cp (by place) | 40 | 33 | 9, 3, 3, 3, 2 |
| advantage-cp (by place) | 14 | 5 | 12, 1, 1, 1, 1 |
| public-option-cp (by place) | 8 | 10 | 2, 1, 1, 1, 1 |
| nhs-cp, vouchers-cp, smokers-pic, delay-cp, taxes-pic (by place) | 4, 4, 3, 1, 1 | 5, 4, 3, 3, 1 | all one team each |
| cap-k | 28 | 41 | 4, 4, 4, 2, 2 |
| racial-capitalism-k, security-k, disability-k, biopolitics-k | 2, 1, 1, 1 | 2, 1, 1, 2 | 2, then one team each |

### Quoting at report time

The report's cost of quoting was measured with t09's `words` pattern:
* re-read, in memory, every source holding a text placed on a position;
* find each text by its paragraph's element index;
* check it against the digest the counts kept;
* then count the texts naming a school (t09's `CaselistNames.without_schools`) and what t05's
  `scan_report` would find if every one of them were quoted.

| Count | |
|---|---|
| Sources re-read | 270 |
| Texts: CP by label 9, CP by place 163, K alternative 81, role of the ballot 2, overview 94 neg + 16 aff | 365 |
| Paragraphs that read differently from their digest; sources unread | 0; 0 |
| **Texts naming a school of the caselist** (withheld, counted) | **1** (a K alternative) |
| **Scan hits if every text were quoted** | **2**: a team code in one CP text, the ordinary word `all` that t09's sheet also met; and a school's name, in the K alternative the school rule withholds |

So a report quoting under these rules should raise **1** scan hit, in the CP texts section, for the
operator to read at the publish. The dry run after the build will give the real number.

### Runtimes

| Pass | What it read | Wall-clock |
|---|---|---|
| Raw pass, sample (1 shard of 40) | 96 sources | 33.9 s |
| **Raw pass** (labels), 5 shards of 765, 6 workers | all 3,825 on-topic sources | 66.7, 58.0, 63.2, 70.8 and 58.0 s; 976.7 s of worker time (0.23 to 0.29 s a source); the reader 26.6 to 33.3 s of each |
| **Shape pass**, 4 shards of 517 or 518, 6 workers | the 2,070 negative sources | 45.7, 49.2, 56.0 and 48.3 s; 478 s of worker time (0.21 to 0.26 s a source) |
| Forms, tables, refinements | the reader and the derived files | 27.1, 28.3 and 27.8 s |
| **Quoting** | 270 sources re-read for 365 texts, 6 workers | **14.9 s** of re-reading (wall 50.7 s with the reader's 35.6 s); a second run at a higher load 52.8 s (wall 93.1 s) |

**What a report run would cost, from these:**
* **The first run on a machine** fills the new cache from every on-topic source: about 980 s of worker
  time, so about 2 minutes over 8 workers plus the reader. That first run is an operator block. With
  overviews on the negative side only, it is the 2,070 negative sources: about 480 s, a minute over 8
  workers.
* **A weekly run** parses only new sources: a few hundred at most, well under a minute.
* **Quoting** re-reads only the sources whose texts the report shows: 15 to 55 s over 6 workers for
  all 270. With a cut-off, fewer.

**One incident, handled before any count was kept.** The first sample's scratch file held the
normalized form of every candidate, and an inline or sentence label's form is its whole paragraph.
I deleted that file. From then on, a form is kept only for a label of at most 8 words with no
`should`, and an inline or sentence label keeps only its opening words (`text`, `the alternative is`).
Every count above comes from the corrected passes.

## The proposed labels

Labels are listed as t01's normalizer writes them, with the negative documents and teams that show
each. "Inline" means the label opens a paragraph that holds the text. "Sentence" means the paragraph
is the text, opening with those words.

**CP text**

| Label | Neg documents / teams | Proposed |
|---|---|---|
| inline `Text:` with `should` | 54 / 28 | yes |
| inline `CP:` with `should` | 7 / 3 | yes |
| inline `CP Text:`, `Counterplan Text:`, `Counterplan:` with `should` | 3 / 2, 0, 2 / 2 | yes |
| `Text`, `CP Text`, `Counterplan Text`, `Texts` on their own | 2 / 2 | yes |
| **The first `should` analytic of a block under a placed CP heading, no label** | **133 / 56** | question 1 |
| Left out: `Text condensed, none omitted`, `Text shrunk ...` | 489 docs (both sides) | card-cutting notes, not labels |
| Left out: `Full text` | 217 docs, almost all affirmative | an affirmative hat |
| Left out: `Plan text` in a negative file | 3 teams | a quoted plan, not a CP |
| Left out: `The counterplan is ...` | 28 docs | tags, claims about the CP |
| Left out: `CP: <name>` without `should` | 469 docs (both sides) | a heading naming the CP, not its text |

**K alternative**

| Label | Neg documents / teams | Proposed |
|---|---|---|
| sentence `The alternative is`, `The alt is`, `Our alternative is` (and `should`, `will`) | 307 / 143, 56 / 33, 37 / 24 | yes |
| `Alt`, `Alternative`, `The alt`, `The alternative`, `Alt text`, `Alts` on their own | 52 / 37, 15 / 9, and 1 | yes |
| inline `Alt:`, `Alternative:`, `The alt:` in a tag or analytic | 17 / 10 | yes |
| Left out: `Alt: <name>` as a heading | 19 / 11 | a heading that names the alt in a few words, not its text (question 2) |
| Left out: `Alt causes`, `Alt fails`, `Perm do the alt`, `Alt cause to ...` | mostly affirmative | answers to an alt |
| Left out: `Alt overview` | | counted as an overview |

**Role of the ballot**

| Label | Neg documents / teams | Proposed |
|---|---|---|
| sentence `The role of the ballot is` / `should`, `The role of the judge is` | 15 / 13, 1, 4 / 3 | yes |
| `Role of the ballot`, `ROB`, `Role of the judge`, `ROJ`, `Role of judge`, and inline `ROB:`, `Role of the ballot:` | 9 / 7, 1, 2, 2, 3, 1 | yes |
| Left out: `Ballot` on its own | 28 docs (16 teams, both sides) | also heads ballot-PIK and presumption blocks; cannot be told apart |
| Left out: `Ballot PIK`, `Ballot PIC` | 33 and 14 docs | a K's name, not its role of the ballot |

**Overview**

| Label | Neg documents / teams | Proposed |
|---|---|---|
| `O/V`, `Overview`, `OV`, `OVW` on their own | 120 / 45, 110 / 47, 24 / 18, 5 / 2 | yes |
| compound with a part or a position (`Impact overview`, `Link O/V`, `UQ O/V`, `Midterms DA overview`, `Overview – Cap K`) | 191 / 60 | yes |
| Left out: `O/W`, `Extinction O/W` | | "outweighs", not an overview |

## The PM's rulings, applied

The PM ruled on the counts on 2026-10-24:
* (1) (b), with an actor guard;
* (2) the labels as proposed;
* (3) (c), counts only;
* (4) the top 3;
* (5) the key as proposed.

The rulings are a PM-ruling comment above the spec's `acceptanceCriteria`.

### What was built

| Where | What |
|---|---|
| `domain/landscape_texts.py` (new) | What is kept of one text (`AnalyticTextReading`: kind, form, label and paragraph, unit, kept, digest, placement, position and role; never words; an overview has no digest) and what the report shows (`LandscapeTexts`: per CP and K its top texts and the rest as a count, per kind the coverage, per position the overview teams) |
| `arguments/landscape/analytic_texts.py` (new) | The pure reader: the ruled label lists, inline and sentence labels, the CP text by its place with the actor guard, placement by the nearest placed heading through t02's matcher (the label's own path, cut as a card's, with the team's names and the caselist's schools taken out), the rules digest, reading back against a digest, the school rule, and the ranking with its cut-off |
| `application/ports/analytic_text_store.py`, `integrations/landscape/analytic_text_store.py` (new) | The cache, `<data_dir>/landscape/analytic_texts/<caselist>.jsonl`, beside t09's, keyed by (source digest, parser version, rules digest). Derived fields only |
| `application/analytic_texts.py` (new) | `AnalyticTextService`: `read` parses only what the cache lacks through t09's blob jobs (now one shared function, `plan_texts.blob_jobs`) and a placeholder path; `quote` reads again in memory only the sources holding a CP text, alternative or role of the ballot placed under its kind; `report_inputs` is the run's seam, and a dry run writes no cache |
| `application/landscape_report.py`, `domain/landscape_report.py` | The report's `texts`: a text counts for the teams of the rounds disclosing its file, as a card's read does (never in a round on the other side); every label is counted by where it went |
| `arguments/landscape/render.py` | report.md's two sections, "Counterplan texts, alternatives and roles of the ballot" and "Overviews", before "New this week". Texts are in report.md only |
| `application/landscape_run.py`, `debate_cli/container.py` | The `AnalyticTextsFromReading` seam beside t09's, wired over the same worker pool |
| `integrations/landscape/yaml_taxonomy_repository.py`, `application/ports/taxonomy_repository.py` | `analytic_texts/<topic id>.yaml` loaded and checked with the taxonomies; `cp_text_actors(topic)` |
| `config/landscape/analytic_texts/policy-2026-27-nhi.yaml` (new) | The actor phrases (ruling 1) |
| `scripts/read_landscape_texts.py` (new) | Fills the cache and prints counts only; `--quote` counts the texts read again |
| `docs/guides/landscape-taxonomy.md` | "CP texts, alternatives, roles of the ballot and overviews": the labels, what is left out, and how to edit the actors |

### The actor guard (ruling 1)

The rule:
* at most 12 words before the text's first `should`;
* among them one of the config's actor phrases, as whole words.

The committed list is `fifty states`, `50 states`, `states`, `state`, `territories`, `governors`,
`united states`, `usfg`, `federal government`, `congress`, `supreme court`, `federal judiciary`,
`courts`, `executive branch`, `president`, `department of health and human services`, `hhs`,
`centers for medicare and medicaid services` and `cms`.

Measured in memory on the counts' 163 paragraphs (read-only, 41.4 s for the pass):
* **158 kept and 5 refused**;
* the phrases that matched: `fifty states` 68, `united states` 64, `50 states` 22, `state` 2, `usfg` 1,
  `states` 1;
* the 5 refused are theory analytics, not CP texts: "our counter interpretation is that we" (twice),
  "logic is neg debate", and "logical policy maker is a neg argument debate" (twice). Each is fewer
  than 12 words, with no actor.

The reader's own count on the real store comes from the operator's fill: its "CP texts by place in
negative files" line. It should be a little under 158. A paragraph that opens with an inline `Text:`
label counts as that label, not as a text by its place, and the counts found 7 such paragraphs among
the 163.

### Checks shown failing for their reason

Each check was run red before its code, against a skeleton that found nothing, or by taking out the
line it checks:

| Suite | Red |
|---|---|
| `arguments/landscape/test_analytic_texts.py` (the reader) | 50 failed, 21 passed. The 21 are the nothing-found cases, the guard's True cases and the rules digest, which a find-nothing skeleton passes by construction |
| The same, for an inline label being no part of its text (found while writing the fixture) | 8 failed, 64 passed |
| `integrations/landscape/test_analytic_text_store.py` | 3 failed, 4 passed (the protocol, the key, the no-text fields, an empty cache) |
| `integrations/landscape/test_analytic_text_files.py` | 9 failed, 2 passed. A first attempt failed at import and was redone against a skeleton (agreement 8) |
| `tests/config`, the directory test without its new line | 1 failed, 55 passed |
| `application/test_landscape_report.py` and the golden | 12 failed (the golden report.md among them), 85 passed. One expectation of mine was wrong (7 labels through the first snapshot; it is 5) and was corrected before the code |
| `application/test_analytic_texts.py` (the service) | 14 failed, 2 passed (the two writes-nothing guards) |
| `application/test_landscape_run.py` (the seam) | 3 failed, 31 passed |
| `debate_cli/tests/test_landscape_command.py` (the wiring) | Written after the wiring; it fails with the wiring line removed, and passed after the line was restored byte for byte |
| `tests/scripts/test_read_landscape_texts.py` | 4 failed against a stub |

The golden `report.md` matched on the renderer's first run. Every count in it was worked out by hand
from the fixture's table, in its README's "Analytic texts".

### Mutants

There were 21 targeted mutants. Each:
* was applied to one file, after a check that its replacement occurs exactly once;
* ran the four covering suites (185 tests) in a fresh process, with bytecode writing off and
  `__pycache__` cleared;
* was restored from a copy and compared byte for byte.

No Hypothesis is used, so there is no example database to isolate (agreement 8). Every run took
1.5 to 4.8 s.

| Rule | Mutant | Failed |
|---|---|---|
| Withholding | `names_a_school` never true | 7 |
| Withholding | `names_a_school` on the raw text, not its words | 6 |
| Withholding | a text naming a school still shown | 3 |
| Withholding | withheld texts not counted | 4 |
| Withholding | the report given no schools | 4 |
| Withholding | the seam gives the report no schools | 1 |
| Placement | the team's own names left in a heading | 2 |
| Placement | an open tag read as a heading | 1 |
| Placement | the outermost heading wins | 1 |
| Placement | headings that place nothing read as no heading | 2 |
| Placement | an answer counted as a read in the report | 3 |
| Placement | a round on the other side counted | 2 |
| Placement | a text under another kind of position counted | 3 |
| Placement | a text by its place under any position | 1 |
| Placement | a text by its place under an answer | 1 |
| Guard | no twelve-word limit | 1 |
| Guard | no actor needed | 10 |
| Guard | an actor matched inside words | 1 |
| Guard | the words before the last `should` | **survived**, then 1 |
| Guard | not applied by the reader | 8 |
| Guard | refusals not counted | 5 |

**The one survivor** read the words before the last `should`. No test had two `should`s. The new case,
a CP text whose second `should` comes after 12 words, catches it: 1 failed.

### Before the report (working agreement 10)

* **The affected set** (`uv run scripts/affected_tests.py`) is **180 test files**.
  * I ran them once with `-n auto -m "not slow and not live"` under a 115 s limit on the interpreter,
    and the limit stopped it (exit 142). A second attempt, to capture the output, stopped the same way.
    Other sessions had the load average at 7 to 14.
  * The alarm left two xdist workers and their smoke-test stand-in servers running, orphaned. They were
    my worktree's interpreter with their parent gone; I found and stopped them.
  * So, by agreement 10 and the PM's ruling of 2026-10-19, the whole affected set is left to the pull
    request's `ci` check.
* **Within the limit, the test directories of what changed and the always-run list:**

  | Run | Result |
  |---|---|
  | `arguments/landscape`, `integrations/landscape`, the application's landscape, analytic-text, plan-text, assignment and classification tests, `tests/config`, the four landscape scripts' tests | 964 passed |
  | The domain's landscape tests, `tests/architecture`, `tests/specs`, `tests/smoke/test_landscape_smoke.py` | 415 passed |
  | All of `packages/debate_cli/tests`, the pinned integration lists among them | 907 passed in 37.4 s |
  | `tests/fixtures/caselist/test_build_synthetic_archives.py`, `tests/smoke/test_caselist_cards.py` | 19 passed |

* **The cheap checks:**
  * `ruff format --check .`: 1259 files already formatted;
  * `ruff check .`: all checks passed;
  * `pyright` (the project's configuration): 0 errors;
  * `lint-imports`: 16 kept, 0 broken;
  * `check_thin_handlers.py`: 50 handlers within 25 statements;
  * `docs_index.py --check-descriptions`: OK;
  * `check_command_blocks.py --base origin/dev`: OK;
  * `check_links.py`: OK;
  * `pre-commit run check-merge-conflict --all-files`: passed;
  * `validate_specs.py`: OK, 437 files.
* **No shared test ground changed:** no `pyproject.toml`, `uv.lock`, conftest or pytest plugin. So no
  whole-selection hand-off.

## Files changed

* **`debate_core.domain`:** `landscape_texts.py` (new); `landscape_report.py` (the report's `texts`).
* **`debate_core.arguments.landscape`:** `analytic_texts.py` (new); `render.py` (the two sections).
* **`debate_core.application`:**
  * `analytic_texts.py` and `ports/analytic_text_store.py` (new);
  * `landscape_report.py` (the aggregation), `landscape_run.py` (the seam);
  * `plan_texts.py` (`blob_jobs`, shared, behaviour unchanged: t09's tests pass);
  * `ports/taxonomy_repository.py` (`cp_text_actors`).
* **`debate_core.integrations.landscape`:** `analytic_text_store.py` (new); `yaml_taxonomy_repository.py`.
* **`debate_core.testing.landscape_report`:** reads the fixture's `analytic_texts.json`.
* **`debate_cli`:** `container.py` (the wiring); `tests/test_landscape_command.py`,
  `tests/test_installation.py` and `tests/commands/test_doctor.py` (the pinned integration lists gain
  `landscape.analytic_text_store`).
* **`config/landscape/analytic_texts/policy-2026-27-nhi.yaml`** (new).
* **Tests:**
  * `packages/debate_core/tests`: `arguments/landscape/test_analytic_texts.py`,
    `application/test_analytic_texts.py`, `integrations/landscape/test_analytic_text_store.py` and
    `test_analytic_text_files.py` (new); `application/test_landscape_report.py` and
    `test_landscape_run.py`;
  * `tests/config/test_landscape_taxonomies.py`; `tests/scripts/test_read_landscape_texts.py` (new).
* **`tests/fixtures/landscape`:** `synthetic_caselist/analytic_texts.json` (new, by hand), its README,
  and `golden/report.md` (two sections, by hand).
* **`scripts/read_landscape_texts.py`** (new).
* **`docs/guides/landscape-taxonomy.md`:** a section on the texts.
* **The spec:** the PM's rulings as a comment above `acceptanceCriteria`.

## Deviations from the spec

1. **ac2 still says "each position's most common overview".** Ruling 3 replaced it with counts only:
   per position, on each side, the teams with an overview, and no text. The code follows the ruling,
   and ac2 is reported against it. Question 1 asks to amend ac2's wording.
2. **Files outside `constraints.packages`**, each needed by a ruling or by the wiring:
   * `debate_core.integrations` (the cache adapter and the actor file's loading);
   * `debate_core.testing` (the fixture's loader);
   * `debate_cli` (the composition root and its pinned lists);
   * `config/landscape` (ruling 1's actor list);
   * `tests/config`;
   * `tests/scripts` and `scripts` (the operator's fill);
   * `docs/guides`.

   t09's PM amended its own list the same way. Question 2 asks to amend this one.

## Decisions and assumptions

From the counts (2026-10-24):

1. **Both sides were counted for every kind,** and the tables lead with the negative side. An
   affirmative CP text or alternative is one the aff answers. For overviews the coach said "each
   position's", so both sides are shown.
2. **Placement is the label's own path,** the headings over the label itself. A label that is itself
   a heading (an `Overview` block) is placed by the headings over it, not by its own words.
3. **The shape pass read negative sources only.** A CP text in an affirmative file is an answer's
   quote, and the comparison rule asks for READS.
4. **The most common overview was measured as the first paragraph under the label,** over 8 words,
   of any unit. Ruling 3 made overviews counts only, so the build keeps no overview text or digest.

From the build:

5. **An inline label is no part of its text.** `Text: The fifty states should ...` and the same text
   with no label are one text, and the report quotes it without its label.
6. **A text counts as a card's read does:** for the teams of the rounds disclosing its file. A round on
   the other side of the position does not count, and a round on no readable side does. A text under an
   answer heading, under another kind of position, or in a round on the other side is counted as
   "placed elsewhere". **An overview counts on both sides**, READS, as ruling 3 asks; under an answer
   heading it is "placed under an answer".
7. **A text read again differently** keeps its teams in the count, from its reading, and is not quoted.
   Another copy of the same words shows instead. One with no copy read again is not shown and is
   counted as "could not be read again". A blob is content-addressed, so this should not happen.
8. **The guard reads the words before the first `should`.** A CP text opens with its actor, and its
   second `should` may come late. t09's plan-text rule reads the last, for preambles such as "care
   should be a right, so ...". The counts' 163 were measured this way.
9. **The cache's key leaves out the team names and the caselist's schools** used to place a heading.
   A school seen for the first time in a later week is not taken out of a heading cached before it,
   until the next parser, rules, taxonomy or overrides change reads every file again. Keying on the
   caselist's schools would read every file again every week the caselist gains a school.
10. **A CP no card counts still shows its texts.** The texts section is not limited to the positions
    table, so a CP whose texts are placed but whose cards are below the threshold is shown.
11. **The first fill has its own script,** not `landscape report`. A report run also rewrites the
    classification cache and the coach's review queue, which t09 avoided for the same reason.

## Operator follow-ups

1. **Fill the analytic-text cache for hspolicy26** (expected runtime about 2 to 4 minutes over the
   default workers, longer if other sessions load the machine). It reads every on-topic file of the
   newest snapshot through the parser and writes only `~/.debate-research/dev/landscape/analytic_texts/hspolicy26.jsonl`,
   with digests, indexes and ids and no text. It prints counts only, and refuses to start if a
   `DEBATE_*` variable is set or a `caselist pull` is running. First, from the task worktree:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t11-negative-analytic-texts
```

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run python scripts/read_landscape_texts.py --caselist hspolicy26; fi
```

   **Success looks like:**
   * `Read hspolicy26 2026.10.20-docx-6 through 2026-10-20: 3825 sources on policy-2026-27-nhi, 2070
     negative, 1770 affirmative.`;
   * an `Analytic texts:` line with `3825 sources`, `0 cached` and a parsed count above zero, `0
     unread` and `cache written`;
   * each kind's found and placed counts, all above zero, and the `CP texts by place in negative
     files:` line;
   * the `Runtime` line.

   Paste every line back. A `STOP:` line means nothing ran.
2. **Then I run the dry run** of `debate-research landscape report --caselist hspolicy26 --dry-run`,
   without `--publish`, on the warm cache. I record its runtime, its counts and the scan's hits by
   section, and finish this report.
3. **The first publish with these sections** is the PM's to coordinate, after the review.

## Follow-up work

* **Overviews quoted**, should the coach and Charlie ever list them in the data-use policy. The reader
  would keep a digest for them again, and the report would show them as it shows texts.
* **The CLI's JSON** does not include the texts' counts yet. The run's result carries them
  (`LandscapeRunResult.analytic_texts`), for t05's command to print if the PM wants them.
* **Labels that name their own position** (`Midterms DA overview`, 127 of 669 compound overview
  labels in the counts) are placed only by the headings over them. A rule reading a label's own words
  as a heading would place 30 more, but it is a placement change, and the matcher's to make.

## Questions for the PM

Two, both about the spec. Paste-ready:

```text
v1-e32-t11 questions (session, 2026-10-24, after the build). The build follows
your rulings 1-5; the dry run waits on the operator's first cache fill.

1. ac2 still says "each position's most common overview". Your ruling 3 (the
   coach's decision) made overviews counts only: per position, on each side,
   the teams with one, and no text. Amend ac2's wording to that?
   Recommendation: yes, so the criterion says what was built.

2. Files outside constraints.packages, each needed by a ruling or the wiring:
   debate_core.integrations (the cache adapter, the actor file's loading),
   debate_core.testing (the fixture's loader), debate_cli (the composition
   root and its two pinned integration lists), config/landscape (ruling 1's
   actors), tests/config, tests/scripts and scripts (the operator's fill), and
   docs/guides. Amend the list with a PM-ruling comment?
   Recommendation: yes, as for t09.
```

### The questions of 2026-10-24 on the counts, answered

The PM ruled the same day: (1) (b) with an actor guard; (2) yes; (3) (c), counts only, the coach's
decision; (4) yes, top 3; (5) yes, that key. Kept as asked:

```text
v1-e32-t11 questions (session, 2026-10-24). Counts only, nothing built.
hspolicy26 through 2026-10-20: 3,825 on-topic sources re-read in memory
(t09's pattern); 2,070 negative documents (392 teams), 1,770 affirmative (552).
"Placed" = the label's nearest placed heading by t02's matcher.

1. CP texts. Labels are rare: a "Text:"-style label is in 68 negative
   documents (37 teams), and only 10 (7 teams) sit under a placed CP. The CP
   text is usually the first "should" paragraph of the CP's own block, unlabelled:
   133 documents (56 teams) under a placed CP heading, 8 CPs, 64 distinct texts.
   Read back in memory, all 163 such paragraphs have at most 12 words before
   "should" and 146 open "The fifty / The United / The 50".
   (a) Labels only: 10 documents, 3 CPs, 8 texts, each read by one team.
   (b) Labels, plus the first "should" analytic of a block whose nearest placed
       heading is a CP (READS): 136 documents, 8 CPs.
   Recommendation: (b). The CP is named by the heading, as every card is, so the
   position is never guessed. Only which paragraph holds the text is read from
   its place, and on the negative side under the CP's own READS block that is
   the text. Without it the CP section would show almost nothing.

2. The labels for alternatives, roles of the ballot and overviews, as listed in
   the report (alternatives: "The alternative is / The alt is / Our alternative
   is", "Alt", "Alternative", inline "Alt:"; ROB: "Role of the ballot", "ROB",
   "Role of the judge", "ROJ" and their sentences; overviews: "O/V", "Overview",
   "OV", "OVW" and compounds such as "Impact overview"). Left out: "Ballot" on
   its own (also heads ballot-PIK and presumption blocks), "Alt causes / Alt
   fails / Perm do the alt" (answers), "O/W" (outweighs), and "Alt: <name>" as a
   heading (19 documents, 11 teams; it names the alt rather than giving its text).
   Placed: alternatives 72 documents (33 teams, 5 Ks); ROB 1 document.
   Approve the list?
   Recommendation: yes. Roles of the ballot then show almost nothing this
   season (1 placed document); the report says so rather than dropping the kind.

3. Overviews. Data-use policy 1.13 lists plan texts, counterplan texts, kritik
   alternatives and roles of the ballot as quotable, and not overviews. And the
   most common overview is one team's in 13 of 16 negative positions (2 read by
   two teams, 1 by three) and in all 6 affirmative ones, so "most common" is
   mostly a tie broken arbitrarily.
   (a) Quote a position's most common overview only when two or more teams read
       it (3 positions today), and count overviews per position otherwise.
   (b) Quote every position's most common overview, a one-team one included
       (16 negative positions, 6 affirmative), ties broken by the most teams and
       then a fixed order.
   (c) Counts only: the number of teams with an overview per position, no text.
   Recommendation: (a), if you and Charlie read 1.13 as covering overviews
   (they are a team's own analytic text); otherwise (c) until the policy says.
   Either way both sides are counted; aff overviews add 3 advantages and 7 teams.

4. The cut-off per CP and per K: the top 3 distinct texts with their team counts,
   then "and N more texts, read by M teams". Today's counts: CP texts by place,
   75 team-position pairs, the top 3 per CP cover 42 (top 5: 50); alternatives,
   33 pairs, the top 3 per K cover 13 (top 5: 17); 53 of 64 CP texts and 40 of
   47 alternatives are read by one team.
   Recommendation: top 3. It shows 31 texts for today's 8 CPs and 5 Ks (some
   have fewer than 3), and the rest stay counted.

5. The cache's key. The cache keeps no text, so it cannot keep the headings a
   text sits under either, and a text's position has to be cached with it. Then
   the key is (source digest, parser version, digest of the labels and rules,
   taxonomy positions and the coach's overrides), as t02's cache keys on the
   taxonomy version and the overrides. A taxonomy or overrides edit re-reads every
   on-topic source once: measured about 980 s of worker time, about 2 minutes
   over 8 workers.
   Recommendation: yes, with that key. The alternative, re-placing at report
   time, means re-reading every source with a candidate each week: 1,994
   documents today (1,007 with a label, 1,553 negative ones with a first
   "should" analytic in a block), about 500 s of worker time, and growing.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

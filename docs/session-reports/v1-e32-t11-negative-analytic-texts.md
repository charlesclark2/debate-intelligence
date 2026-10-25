# Session report: v1-e32-t11-negative-analytic-texts

| | |
|---|---|
| Task | `v1-e32-t11-negative-analytic-texts` — Counterplan texts, kritik alternatives and overviews in the landscape report |
| Spec | [`plan_specs/v1/e32-argument-landscape/t11-negative-analytic-texts.yaml`](../../plan_specs/v1/e32-argument-landscape/t11-negative-analytic-texts.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t11-negative-analytic-texts` |
| Session status | PARTIAL: stopped for the PM's ruling after the counts <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**The counts are done (ac1), and nothing is built.** As the PM's context asks, the session stops here
for a ruling ([the questions](#questions-for-the-pm)). ac2 waits on that ruling, so the Goal stays
**InProgress**.

The counts cover hspolicy26 through 2026-10-20, its newest snapshot. They were read-only, under t09's
guards, and printed counts only. Every one of the 3,825 on-topic sources was re-read from its blob
with t09's pattern (the parser in memory, a placeholder path). Each label was placed by t02's matcher
from the headings over it.

What the store shows, kind by kind:
* **CP texts are almost never labelled.** A `Text:`-style label is in 68 negative documents (37
  teams), and only 10 of them (7 teams) sit under a heading the matcher places on a CP.
  * The CP text is usually the first `should` paragraph of the CP's own block, with no label. That is
    133 documents (56 teams) under a placed CP heading.
  * All 163 such paragraphs have at most 12 words before `should`, and 146 open with "The fifty",
    "The United" or "The 50".
  * Question 1 is whether that position rule may name a CP text.
* **K alternatives are mostly card tags the store already holds:** "The alternative is ...", "The
  alt is ...". The labels are in 452 negative documents (185 teams). 72 of them (33 teams) sit under
  a heading placed on a K. The rest are under `1NC`/`OFF`-style headings that place nothing, as the
  report already counts their cards.
* **Roles of the ballot are rare:** 30 negative documents, and 1 under a placed K.
* **Overviews are labelled in 335 negative documents (94 teams) and 159 affirmative ones (52).**
  * The most common overview of a position is read by one team in 13 of 16 negative positions, and
    in all 6 affirmative ones.
  * Data-use policy 1.13 lists plan texts, CP texts, alternatives and roles of the ballot, but not
    overviews (question 3).
* **Quoting at report time is cheap:** 270 sources re-read for 365 texts in 14.9 s over 6 workers.
  * Every paragraph matched its digest.
  * 1 text names a school and would be withheld.
  * t05's scan would hit twice: the ordinary word `all` in one CP text, and the school in the text
    that is withheld.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| negative-texts | In progress: the counts (ac1) done and sent; stopped for the PM's ruling before any building | Scratch count scripts only, outside the repository. No code, test, fixture or config changed |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any rule, per kind, of documents with a CP-text, alternative, role-of-the-ballot or overview label and the paragraph under it, sent to the PM with the proposed labels | PASS | [The counts](#the-counts-hspolicy26-through-2026-10-20), [the proposed labels](#the-proposed-labels), [the questions](#questions-for-the-pm), sent 2026-10-24. Nothing was built |
| ac2: after the ruling, on synthetic sources, the report shows each CP's and K's distinct texts with their team counts and each position's most common overview, matching hand-written golden files; a text never beside a school or team code; tests shown failing first | NOT RUN | Waits on the PM's ruling (the PM's context: build nothing before it) |
| negative-texts node: `uv run pytest packages/debate_core/tests/application/test_landscape_report.py` | NOT RUN as a criterion | Nothing changed yet. Baseline only: `.venv/bin/python -m pytest packages/debate_core/tests/application/test_landscape_report.py -q -p no:randomly` under `perl -e 'alarm 100'` → 52 passed in 5.97 s |

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

## Files changed

* **`docs/session-reports/v1-e32-t11-negative-analytic-texts.md`:** this report.

No code, test, fixture, config or spec changed. The count scripts are scratch files in the
session's scratchpad, outside the repository.

## Deviations from the spec

None so far.

## Decisions and assumptions

1. **Both sides were counted for every kind,** and the tables lead with the negative side. An
   affirmative CP text or alternative is one the aff answers. For overviews the coach said "each
   position's", so both sides are shown.
2. **Placement is the label's own path,** the headings over the label itself. A label that is itself
   a heading (an `Overview` block) is placed by the headings over it, not by its own words.
3. **The shape pass read negative sources only.** A CP text in an affirmative file is an answer's
   quote, and the comparison rule asks for READS.
4. **The most common overview is the first paragraph under the label,** over 8 words, of any unit.
   The overview's analytics alone would miss the 257 overviews written as tags.

## Operator follow-ups

None yet. After the ruling, the first report run with these sections fills the new cache from
every on-topic source. That is about 2 minutes over 8 workers, so it is an operator block, and the
PM coordinates the first publish.

## Follow-up work

None yet.

## Questions for the PM

Paste-ready for the PM:

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

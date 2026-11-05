# Session report: v1-e32-t06-ld-de-extinction-taxonomy

| | |
|---|---|
| Task | `v1-e32-t06-ld-de-extinction-taxonomy` — LD de-extinction position taxonomy |
| Spec | [`plan_specs/v1/e32-argument-landscape/t06-ld-de-extinction-taxonomy.yaml`](../../plan_specs/v1/e32-argument-landscape/t06-ld-de-extinction-taxonomy.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t06-ld-de-extinction-taxonomy` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The LD de-extinction topic is in `topics.yaml` with the coach's resolution, copied from the spec, and a
taxonomy file, `ld-2026-nov-dec-de-extinction.yaml` 1.0.0, seeded from hsld26's 2026-11-03 snapshot and
approved by the coach on 2026-11-05: 15 positions, plus 2 LD format-level positions in `generic.yaml`
(1.2.0). Because the coach's word (PM amendment of 2026-11-01) makes the topic follow the tournament, the
topic map gained **tournament entries**, built to the PM's ruling of 2026-11-05: a disclosure resolves by
a matching entry, then its snapshot's range, then to no topic. Florida Blue Key's 292 of the snapshot's
902 disclosures are on de-extinction; every earlier snapshot resolves as before, which a config test
pins. Seeding, the report and its trends read each disclosure's topic; a report on an entry-only week
says it reads 292 of 902, and the week after calls it a partial base. A dry run on the newest snapshot
resolves the new topic at 1.0.0. `argument_taxonomy.yaml` 1.5.0 adds the topic's search preset and six
LD arguments, both approved by the coach. Every acceptance criterion passes; the Goal is `Succeeded`.

The PM should look first at the loader change in `debate_core.domain.landscape` (Deviation 1), the one
JSON key added to `landscape report --json` (Deviation 2), the dry run's exit on 7 unaccepted scan hits
(a publish's matter), and **Q2's counts**: the ruling asks for them on the 2026-11-10 and 2026-11-17
snapshots "while the task is open", and neither snapshot exists yet (Operator follow-ups).

## Counts taken before any rule (2026-11-05)

Counts only, read-only over v1-e40-t17's restored copy of hsld26 (restored 2026-11-05, 19 manifests,
7,030 sources fetched of 7,030 named, 0 suppressed, parsed store `2026.10.27-docx-7` restored with
7,141 objects, so the parse had nothing to do). The copy is the state of the operator's hand run
`20261105T034547Z` (2026-11-05 03:45 to 05:12 UTC, `completed`), which imported **hsld26
2026-11-03**: the snapshot this report means by "the 2026-11-03 snapshot (the run of 2026-11-04)".
The scheduled run of 2026-11-04 failed to launch on an AWS-side error. The script is a session
scratch file, not committed; each run took 2 to 7 s.

* **What a stored disclosure carries to decide by.** Its snapshot date (a weekly Tuesday), the
  tournament as the filename spells it, and a round label. 9,700 live hsld26 disclosures in 18
  snapshots: 9,700 with tournament text, 9,700 with a round (9,494 read as a known round). No stored
  field holds a tournament date or a round date (`caselist_disclosures`, `caselist_sources`,
  `caselist_snapshots`, the manifests), so a per-tournament rule can only match the tournament text,
  with the snapshot.
* **Florida Blue Key in the 2026-11-03 snapshot** (902 live disclosures, 810 sources). The tournament
  text, lower-cased with everything but letters and digits removed, holding `bluekey` or `fbk`
  (12 spellings): **292 disclosures, 257 sources, 27 schools**. The four spellings two or more schools
  wrote for the tournament itself: 243 disclosures, 214 sources. The round robin's spelling: 11
  disclosures, 9 sources, 2 schools. No disclosure in any earlier snapshot holds `bluekey` or `fbk`.
* **Topic words as a check on the rule**, by source, in cards' tags and headings (`de-extinct` against
  `space col`/`coloniz`): Florida Blue Key's 257 sources: 184 de-extinction only, 4 both, 2 space only,
  66 neither, 1 not parsed. The snapshot's other 554 sources: 2 de-extinction only, 490 space only,
  55 neither, 7 not parsed.
* **Disclosures in snapshots from 2026-11-10 naming a tournament from before 2026-11-06: NOT RUN.** No
  such snapshot exists on 2026-11-05. The nearest measure is a ceiling, not the count: in the 2026-11-03
  snapshot, 246 of 902 disclosures name a tournament spelling first seen two or more snapshots earlier,
  which counts real late disclosures and spellings that recur (two tournaments, one word) alike.
* **Disclosures naming no tournament:** 0 in the 2026-11-03 snapshot (the path parser gives every
  disclosure some tournament text).

## The proposal (2026-11-05, for the PM's ruling, kept as written)

Sent through the operator after the counts above. Kept as written, with one change: Q2's option (ii)
named four tournaments that share their host schools' names; this report names no school, so they are
left out here, shown as "[four tournament names]".

> v1-e32-t06 (LD de-extinction taxonomy): the counts the 2026-11-01 amendment asks for, and the rule's
> form for your ruling. Nothing is built yet.
>
> WHICH RUN. The hand run 20261105T034547Z (completed 2026-11-05 05:12 UTC) imported hsld26 snapshot
> 2026-11-03. Its state was restored through v1-e40-t17's copy (7,030 of 7,030 sources, parsed store
> 2026.10.27-docx-7). The copy has now been deleted.
>
> COUNTS (counts only; each read took seconds)
> 1. What a stored disclosure carries to decide by: the snapshot date (a weekly Tuesday), the tournament
>    as the filename spells it, and a round label. All 9,700 live hsld26 disclosures carry tournament
>    text and a round. No stored field holds a tournament date or a round date. So a per-tournament rule
>    can only match tournament text, together with the snapshot.
> 2. Florida Blue Key in the 2026-11-03 snapshot (902 disclosures, 810 sources): tournament text that,
>    lower-cased with only letters and digits kept, holds "bluekey" or "fbk" (12 spellings) gives 292
>    disclosures, 257 sources, 27 schools. 11 of those disclosures are the Florida Blue Key Round Robin.
>    No earlier snapshot holds either spelling.
>    Check by topic words in tags and headings: FBK's 257 sources split 188 de-extinction, 6 space, 66
>    neither. The other 554 sources split 490 space, 2 de-extinction, 55 neither. So the tournament
>    separates the two topics cleanly.
> 3. Disclosures in snapshots from 2026-11-10 naming a tournament from before 2026-11-06: NOT RUN,
>    because no such snapshot exists yet. The only ceiling I have: in 2026-11-03, 246 of 902 disclosures
>    name a spelling first seen two or more snapshots earlier. That mixes real late disclosures with
>    recurring spellings, so it is a ceiling, not the count.
> 4. Disclosures naming no tournament: 0 (the path parser always yields some tournament text).
> 257 sources from 27 schools is enough to seed from.
>
> PROPOSED RULE FORM (recommended)
> topics.yaml keeps every snapshot range as it is. A topic may add tournament entries, each with:
> caselist, a public name, spellings (lower-case letters and digits, matched as a part of the
> disclosure's tournament text after the same reduction), and the snapshot window the entry applies in.
> A disclosure resolves to:
>   (a) the topic of a tournament entry whose spelling it holds and whose window covers its snapshot;
>       otherwise
>   (b) the topic whose range covers its snapshot; otherwise
>   (c) no topic, as today.
>
>     - id: ld-2026-nov-dec-de-extinction
>       event: LD
>       resolution: "Resolved: De-extinction is unethical"   (copied from the spec)
>       taxonomy_version: 1.0.0
>       caselists:
>         - {caselist: hsld26, from: 2026-11-06, to: 2026-12-31}
>       tournaments:
>         - caselist: hsld26
>           name: Florida Blue Key Speech and Debate Tournament
>           spellings: [bluekey, fbk]
>           from: 2026-11-03
>           to: 2026-11-03
>     ld-2026-sep-oct-space-colonization: unchanged (hsld26 2026-09-01 to 2026-10-31, no taxonomy).
>
> What this does:
> - Every snapshot up to 2026-10-27 resolves exactly as today; a test pins it.
> - In 2026-11-03, the 292 FBK disclosures resolve to de-extinction. The other 610 resolve to no topic,
>   as the whole snapshot does today; space colonization has no taxonomy, so nothing counts them either
>   way.
> - From 2026-11-10, every disclosure is de-extinction by range unless a tournament entry says otherwise.
> - A disclosure naming no tournament resolves by its snapshot's range (rule b): no topic in 2026-11-03,
>   de-extinction from 2026-11-10.
> - The snapshot-level answer that a report, staleness and week-over-week use: a snapshot is on the
>   topic of its range. With no range, it is on the topic of the one tournament entry covering it, so the
>   landscape report on 2026-11-03 resolves de-extinction (ac4 can pass on today's newest snapshot). Two
>   entries of different topics covering one snapshot are refused at load, as overlapping ranges are now.
> - The loader refuses: a spelling in two topics' entries for one caselist with overlapping windows; an
>   entry window reaching back over a snapshot already covered by another topic's range (so earlier
>   snapshots cannot move); a spelling that is not lower-case letters and digits.
> - Code (this task's, as the amendment says): the domain model and resolution in
>   debate_core.domain.landscape; the per-disclosure filter in landscape_seeding.read_seed_sources (it
>   decides what seeding and the report count); landscape_run's snapshot topics. No topic wording or
>   slug in Python.
>
> QUESTIONS
> Q1. The form above: per-tournament entries beside the date ranges, with rules (a) to (c). Recommended:
>     yes. It is the smallest change that matches the coach's word: no earlier snapshot moves, and space
>     colonization keeps its range untouched.
> Q2. Late disclosures from pre-2026-11-06 tournaments in 2026-11-10 and later. Options:
>    (i) Count them each week and add space colonization tournament entries only when the count is
>        material. Recommended: the count cannot be taken until 2026-11-10 exists, and the ceiling above
>        overstates it.
>    (ii) Pre-list the 2026-11-03 snapshot's other tournaments under space colonization with window
>        2026-11-10 to 2026-12-31: about 18 public names ([four tournament names], NSD season opener, and
>        others). Risk: a spelling a November tournament shares is moved off de-extinction.
>    (iii) Decide by topic words in the file. Rejected for now: it is a content rule, and about a quarter
>        of files hold neither topic's words.
> Q3. Florida Blue Key Round Robin (11 disclosures, 9 sources; 5 hold de-extinction words, 0 space). The
>     coach named "the Florida Blue Key Speech and Debate Tournament". The spelling "bluekey" catches the
>     round robin too. Recommended: include it, since its files are on de-extinction. Say if the coach
>     wants it out; then the spellings become exact rather than "holds".
> Q4. Matching "holds a spelling" (catches 49 extra disclosures under 8 one-school spellings) versus
>     exact spellings. Recommended: "holds", as the counts above show it adds only de-extinction files.
>
> FYI, I'll proceed this way unless told otherwise:
> - After the ruling: one more restore, seeding from that copy's 2026-11-03 FBK disclosures, curation
>   with the coach, then the NHI-style preset in argument_taxonomy.yaml with the topic's own LD arguments
>   marked awaiting coach review. The generic LD framing is untouched.
> - ac4 (coach review, and the dry run resolving the new topic) needs the coach and a further operator
>   run.

## The PM's ruling (2026-11-05)

Quoted as given, the second wording the operator relayed (the first differed only in Q4's check and had
no paragraph asking for these two sections).

> Q1: YES, the form as proposed: per-tournament entries beside the date ranges, resolving by (a) a
> covering tournament entry, then (b) the covering range, then (c) no topic. Conditions:
> - Configuration lists only the two public spellings, bluekey and fbk. Never a spelling only one school
>   uses, and never one carrying a school or team code.
> - The snapshot-level answer for 2026-11-03 (on the one covering entry's topic) is accepted. The
>   landscape report on that snapshot must say it reads only the tournament entry's disclosures, with the
>   counts (292 of 902), so nobody reads it as the whole week.
> - Week-over-week from 2026-11-03 to 2026-11-10 labels 2026-11-03 a partial base (tournament entry only)
>   instead of comparing it as a whole week.
> - The loader refusals as proposed. One test pins every snapshot up to 2026-10-27 resolving exactly as
>   today; another pins 2026-11-03's per-disclosure split.
>
> Q2: (i). Count, do not pre-list. Once the 2026-11-10 snapshot exists (and again on 2026-11-17), count
> in counts only: hsld26 disclosures whose tournament spelling was first seen in a snapshot on or before
> 2026-11-03, FBK spellings excluded, with their share of the snapshot and the topic-word split as the
> check. Record these in this report while the task is open. If such disclosures exceed 5% of a
> snapshot's hsld26 disclosures, or the topic-word check shows space files landing in de-extinction
> counts, propose space colonization entries then. (ii) is rejected: it guesses ahead and risks moving a
> November tournament that shares a spelling. (iii) stays rejected.
>
> Q3: INCLUDE the Florida Blue Key Round Robin (its files read as de-extinction, none as space).
>
> Q4: HOLDS, after one check. Of FBK's 257 sources, 2 carry space words only. Say, in counts only,
> whether either of them, or any of the 66 with neither topic's words, is caught only through a held
> one-school spelling rather than one of the four shared spellings or the round robin's. If either
> space-only source comes only through a held spelling, use exact matching and say so. Otherwise use
> holds.
>
> Also: write your proposal (as sent) and this ruling into the report as dated sections, as v1-e32-t46
> did, so the review checks the build against them.
>
> Your FYI plan is accepted. The next restore is an operator block deleted after use (policy 1.18). It
> may meet RUN_LOCK_HELD while the operator's restore for v1-e31-t32 is in use; the block says to wait
> and run it again. Curation with the coach shows heading text in the operator's terminal only. Counts
> by kind go in the report, never heading text, schools or team codes.

### How the build follows it

* Q1 (`e3c9102`, `c46d4ea`, `13f6fd7`, `6520a52`): `TournamentEntry` and `TopicMap.resolve_disclosure`
  in `debate_core.domain.landscape`; `read_seed_sources` filters per disclosure; a report on a snapshot
  only an entry covers says "Part of a week" with N of M, and the week after names it a partial base.
  `topics.yaml` lists `bluekey` and `fbk` only. `tests/config/test_landscape_topic_map.py` holds both pins.
  The refusal of an entry reaching back was made precise: an entry may not overlap the range of a topic
  that began before its own topic (by its first range or entry on the caselist). An older topic's entry
  may reach forward into a newer topic's range, which keeps Q2's remedy open (Decisions).
* Q2: counts on 2026-11-10 and 2026-11-17 are owed while the task is open (Operator follow-ups).
* Q3: `bluekey` is held by the round robin's spelling, so it is included with no entry of its own.
* Q4: the check is below, under the seeding's counts.

## Seeding and the Q4 check (2026-11-05)

Read-only over the second restored copy (restored 2026-11-05: 19 manifests, 7,030 of 7,030 sources,
0 suppressed, parsed store `2026.10.27-docx-7` with 7,141 objects), from this worktree with the guards
checked first (no `DEBATE_` variable set, no `caselist pull` running).

**Q4, in counts only** (scratch script, 2.6 s). Florida Blue Key's 2026-11-03 disclosures: 292, from 257
sources. One-school spellings that hold `bluekey` or `fbk`: 7, with 38 disclosures. By source:

| Reached through | de-extinction words only | both | space words only | neither | not parsed |
|---|---|---|---|---|---|
| a shared spelling (the tournament's four, or the round robin's) | 162 | 4 | 2 | 52 | 1 |
| a one-school spelling only | 22 | 0 | 0 | 14 | 0 |

Neither space-only source comes only through a held spelling, so matching stays **holds**, as ruled.
Of the 66 with neither topic's words, 14 come only through a held one-school spelling.

**Seeding** (`scripts/seed_landscape_taxonomy.py candidates --topic ld-2026-nov-dec-de-extinction
--data-dir <copy>`, 2.7 s): 7,030 source entries, 6,889 parsed; **256 sources on the topic** (the 257
above less the one not parsed), 2,593 cards; 595 headings counted, 251 distinct, 192 used by fewer than
two teams left out; **59 candidate rows**. The CSV is on the operator's Mac under
`~/Documents/debate/landscape-seed/`, never committed.

**Drafted** (by kind, from the 59 candidates): the topic file has 14 positions (9 contentions, five
affirmative and four negative; 1 CP, 1 T, 2 Ks, 1 criterion) with 21 aliases; generic.yaml gains 4 LD
positions (2 criteria, 2 theory) with 5 aliases. So 26 of the 59 candidates are aliases. The other 33
are 23 structure labels (overview, framing, contention, offense, the speech and advantage numbers and
the like), 2 that name a tournament or a round, and 8 whose meaning would be a guess; the review sheet
lists them as unplaced for the coach.

## ac4's first dry run (2026-11-05): refused for the parser version

Over the second copy, from this worktree (`uv run debate-research --json landscape report --caselist
hsld26 --restored-copy <copy> --config-dir <worktree>/config/landscape --model-mode none --publish
--dry-run`): `exit 2`, `PARSED_VERSION_NOT_IN_STORE`. The copy's parsed store is the cloud image's
`2026.10.27-docx-7`; this branch, started from dev, parses with `2026.11.03-docx-9`, and a report reads
only its own version. Nothing was written. The copy was then deleted (`removed`; the marker search listed
2 restored copies left on the Mac, neither this task's). The seeding counts above stand: they were read
from the run's own `docx-7` store. The next dry run parses a fresh copy with this worktree's code first.

## ac4's dry run (2026-11-05): the new topic resolves

A third copy, restored 2026-11-05 (7,030 of 7,030 sources, 0 suppressed), parsed with this worktree's
code (`uv run debate-research caselist parse` with `DEBATE_STORAGE__DATA_DIR` naming the copy): dry run
`parser_version 2026.11.03-docx-9`, 7,030 to parse; the parse attempted 7,030, parsed 6,889, 105,944
cards, failure rate 0.0004, threshold not exceeded, 767.2 s. Then, from the worktree:

    uv run debate-research --json landscape report --caselist hsld26 --restored-copy <copy> --config-dir <worktree>/config/landscape --model-mode none --publish --dry-run

| Field | Value |
|---|---|
| exit, code | 1, `SCAN_HITS_NOT_ACCEPTED` |
| snapshot, topic, taxonomy | 2026-11-03, `ld-2026-nov-dec-de-extinction`, 1.0.0 |
| parsed version, stale | `2026.11.03-docx-9`, False |
| sources, cards, cards counted, positions | 256, 2,593, 267, 17 |
| rounds, teams | 291, 51 |
| would ask the model, model calls | 0, 0 |
| scan hits, not yet accepted | 7, 7 |
| planned uploads | 7, each `UPLOAD` |
| `tournament_entry_snapshots` | 2026-11-03, Florida Blue Key Speech and Debate Tournament, 292 on the topic of 902 |

The newest snapshot resolves the new topic at 1.0.0, and the report counts the entry's week as the PM
ruled: 292 of 902. The exit is the scan's: the dry run found 7 lines in the bundle no earlier publish
accepted, the refusal a publish would also meet. Publishing is not this task's, so they were not read
(their lines can name a school, and are for a terminal only); whoever publishes the first LD report reads
them first, as the runbook's step 3 says (Follow-up work). 267 of 2,593 cards counted is the deterministic
first pass on a 1.0.0 taxonomy of two-team headings; the report shows the rest as unclassified. The copy
was deleted after the run (`removed`; the 2 restored copies the search still lists are other tasks').

## The coach's review (2026-11-05)

In one sitting, through the guided script of Decision 8, which saved the decisions to a JSON file on the
operator's Mac. Counts only:

| | Count |
|---|---|
| Positions drafted (14 in the topic file, 4 in generic.yaml) | 18 |
| Kept as drafted | 15 |
| Kept with the coach's description (`trade`) | 1 |
| Renamed, merged | 0, 0 |
| Dropped (generic.yaml's two LD theory positions) | 2 |
| Added, from an unplaced candidate | 1 (an aff) |
| Candidate headings: aliases before the review, after | 26, 25 of 59 |
| Unplaced candidates left out | 34 |
| Proposed search arguments approved, changed, dropped | 6, 0, 0 |
| Topic preset | approved |
| Taxonomy approved once the changes are made | yes |

The added aff's label is in sentence case, "Jurassic park aff": the coach's "Jurassic Park aff" fails the
personal-data check, which reads a capital after a label's first word as a person's name (the guide's
rule, sentence case). His description keeps its capitals. Still 1.0.0: nothing of this topic has been
released, as t01 kept its first version through its coach's changes.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| seed-and-curate | Done | Files counted, seeding run, taxonomy and topics.yaml written, the coach's review applied, t01's config tests pass |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `topics.yaml` maps hsld26 for the coach's de-extinction range to a new taxonomy file, and keeps space colonization's range with no taxonomy | PASS | `topics.yaml`: `ld-2026-nov-dec-de-extinction`, `taxonomy_version: 1.0.0`, hsld26 2026-11-06 to 2026-12-31 plus the Florida Blue Key entry for 2026-11-03 (the 2026-11-01 amendment supersedes the first range); space colonization unchanged at 2026-09-01 to 2026-10-31, no `taxonomy_version`. `pytest tests/config/test_landscape_topic_map.py` → 29 passed (every snapshot to 2026-10-27 as before; 2026-11-03's split; 2026-11-10 onward by range) |
| ac2: at least 12 active positions seeded from hsld26 headings, each with id, label, kind, side and an alias; passes t01's loader and config tests | PASS | 15 positions after the coach's review, none retired, each with 1 to 3 aliases, all from the candidates CSV (two or more teams). `uv run pytest tests/config/test_landscape_taxonomies.py` → 58 passed |
| ac3: the report records the disclosed hsld26 files on the new topic, the candidate count, and the coach's kept, merged and dropped, as counts | PASS | 292 disclosures, 257 sources, 256 parsed and read; 59 candidate rows (Seeding section); the coach kept 16, merged 0, dropped 2, added 1 (The coach's review) |
| ac4: the coach has reviewed the seeded file, and a `landscape report --caselist hsld26` dry run on the newest snapshot resolves the new topic | PASS | The coach reviewed and approved it on 2026-11-05. Dry run over a restored copy (before his review): snapshot 2026-11-03, topic `ld-2026-nov-dec-de-extinction`, taxonomy 1.0.0, 256 sources, 17 positions, entry week 292 of 902; exit 1 `SCAN_HITS_NOT_ACCEPTED` (7 hits, a publish's matter). His changes moved aliases and positions, not the topic map, so the topic resolves as it did |
| Node: taxonomy config tests pass | PASS | `uv run pytest tests/config/test_landscape_taxonomies.py` → 58 passed in 1.80 s |

### Checks run before this report

* The affected set: `uv run scripts/affected_tests.py` chose **346 of 698 test files** from 30 changed
  files. A selection that size runs well past two minutes on this Mac, so under working agreement 10 it
  is left to the pull request's `ci` check, which runs the same selection. Run instead, within the
  limit: the always-run list and every test directory or file of what changed (33 paths:
  `tests/architecture`, `tests/specs`, the CLI wiring tests, `packages/debate_core/tests/domain`,
  `.../arguments/landscape`, `.../integrations/landscape`, every `test_landscape_*.py` in
  `.../application`, `test_query_expansion.py`, `test_aff_assignment.py`,
  `test_position_classification.py`, `test_analytic_texts.py`, `tests/config`, the CLI's
  `test_landscape_command.py`, and the scripts' tests for the six scripts changed) →
  **3,737 passed in 42.9 s**; `tests/smoke/test_landscape_smoke.py` and `test_search_smoke.py` → 13 passed.
  After the coach's review was applied, the same paths with the two smoke files: **3,750 passed in 36.5 s**.
* `ruff format --check .` → 1,953 files already formatted; `ruff check .` → all passed;
  `pyright` over `packages/debate_core`, `packages/debate_cli`, the six scripts and `tests/config` →
  0 errors; `lint-imports` → 20 kept, 0 broken; `scripts/check_thin_handlers.py` → 72 handlers within 25
  statements; `docs_index.py --check-descriptions`, `check_links.py` and
  `check_command_blocks.py --base origin/dev` → OK; `scripts/validate_specs.py` → OK, 619 files.

### Mutants

Eight, on the new rules, each run against the four test files that cover them
(`test_landscape_tournament_entries.py`, `test_landscape_topic_map.py`, `test_landscape_seeding.py`,
`test_landscape_trends.py`), the file restored from HEAD after each. No Hypothesis property is involved.

| Mutant | Result |
|---|---|
| Entries ignored when a disclosure resolves | Caught: 14 failed |
| Exact spelling instead of "holds" | Caught: 10 failed |
| No refusal of an entry reaching into an older topic's range | Caught: 1 failed |
| No refusal of two topics' entries covering one snapshot | Caught: 1 failed |
| A snapshot no range covers does not fall back to its entry | Caught: 3 failed |
| Seeding resolves each disclosure by its snapshot alone | Caught: 1 failed |
| Trends drop the partial windows | Caught: 2 failed |
| No "Part of a week" notice | Caught: 1 failed |

The first and fifth were written first as deleted `if` blocks, which left an empty loop body and failed
at import (4 errors each): not catches. They were rewritten as `if False:` and run again; the counts
above are those runs.

## Files changed

* **`debate_core.domain.landscape`**: `TournamentEntry`, `Topic.tournaments`, `tournament_key`,
  `TopicMap.resolve_disclosure`, the snapshot-level fallback flagged `tournament_entries_only`, the two
  refusals, and `TournamentEntrySnapshot`.
* **`debate_core.domain.landscape_trends`**, **`debate_core.application.landscape_trends`**,
  **`debate_core.application.landscape_report`**, **`debate_core.arguments.landscape.render`**: the
  partial windows, the "Part of a week" notice and the partial base.
* **`debate_core.application.landscape_seeding`**: each disclosure's topic from the whole map, and the
  entry-only snapshots with their counts; **`landscape_run`**, **`aff_assignment`**,
  **`landscape_model_evaluation`** and six scripts pass the topic map; `landscape_run` gives an entry-only
  snapshot its topic's first later range.
* **`debate_cli.commands.landscape`**: `tournament_entry_snapshots` in `--json`.
* **`config/landscape/`**: `topics.yaml` (the topic and its entry), `taxonomies/ld-2026-nov-dec-de-extinction.yaml`
  (new), `taxonomies/generic.yaml` (two LD positions, 1.2.0).
* **`config/argument_taxonomy.yaml`**: 1.5.0, the preset and six arguments, coach-reviewed; its reviewed
  copy is now `packages/debate_core/tests/fixtures/argument_taxonomy/coach_reviewed_1_5_0.yaml` (1.4.0's
  removed, as its header says to do when the coach reviews a change).
* **Tests**: `test_landscape_tournament_entries.py` (new), `tests/config/test_landscape_topic_map.py`
  (new), additions to the seeding, trends, query-expansion and CLI landscape tests, `SHORT_WORDS` in
  `tests/config/test_landscape_taxonomies.py`.
* **`docs/guides/landscape-taxonomy.md`**: tournament entries.

## Deviations from the spec

1. **Packages outside `constraints.packages`.** The rule lives in `debate_core.domain.landscape` and
   `debate_core.domain.landscape_trends`, where the topic map and the trends model are; the spec's list
   has no `debate_core.domain`. The proposal named the domain module and the ruling accepted the form;
   the amendment makes the loader change this task's.
2. **One `--json` key in `debate_cli`** (`tournament_entry_snapshots`), not in the proposal: without it a
   dry run cannot show the 292 of 902 the report states, and the PM's condition could only be checked in
   unit tests. No test pinned the landscape JSON's key set. Drop it if unwanted; nothing else reads it.
3. **The proposal is in this report with four tournament names left out**: they are also their host
   schools' names, and this report names no school.
4. **ac4's dry run ran from this worktree's code, over a copy parsed with its parser** (`docx-9`): the
   installed build cannot read tournament entries, and the cloud image's `docx-7` store is refused by a
   report from this branch. Seeding read the run's own `docx-7` store, as the brief asked.

## Decisions and assumptions

1. **The reach-back refusal, made precise.** An entry may not overlap the range of a topic that began
   before its own topic (by its first range or entry on the caselist). An older topic's entry may reach
   forward into a newer topic's range, so Q2's remedy, space colonization entries for late disclosures,
   stays possible without a code change.
2. **A report on an entry-only snapshot** takes its topic's first range after that snapshot as the topic's
   dates (2026-11-06 to 2026-12-31), so its "Short history" line reads as for any first week.
3. **`psychoanalysis-k` is in the topic file**, not added to generic.yaml's Policy position: changing that
   position's events would edit a Policy position that released reports counted.
4. **`de` and `nc` join `SHORT_WORDS`**: `de` because the normalizer splits de-extinction, `nc` the
   negative constructive (1NC's NC). Both are debate or topic words, not initials.
5. **The proposed arguments** are written as DAs (affirmative contentions, a cost of de-extinction) and
   advantages (negative contentions, a good of it), the families whose needs fit; each takes its landscape
   position's id.
6. **I ran the seeding and the Q4 and topic-word counts myself**, read-only over the restored copy in
   seconds, as t01 ran its seeding; the restores, parses and the dry run went to the operator.
7. **One `git fetch origin dev`**, to compare this spec with dev's before the report.
8. **The coach's review is a one-off guided script**, not a committed tool. The operator found the review
   sheet plus four file listings hard to work through in one sitting. The script walks the sheet's
   content one question per screen (the 18 positions; the unplaced headings, the 25 that look like file
   structure on one screen, left out unless picked; the six proposed arguments; the preset; approval) and
   writes the decisions as JSON. It lives beside the review sheet because it shows real headings, and
   because a permanent, tested guided review is a scope change (Follow-up work). Tested here with scripted
   keypresses: an all-Enter run, a stop and resume, and rename, merge, drop, join and new answers.
9. **`aliases: []` written out** on three of the six arguments: the reviewed-copy test compares each
   entry's dump, which carries the empty list, with the YAML. No search changes.

## Operator follow-ups

1. **Q2's counts on 2026-11-10 and 2026-11-17** (the PM's ruling). Neither snapshot exists until the weekly
   runs of 2026-11-11 and 2026-11-18. For each: restore a copy (the runbook's step 1 with
   `CASELIST=hsld26`); the session counts the disclosures whose tournament spelling was first seen on or
   before 2026-11-03, FBK spellings excluded, with their share and the topic-word split; then delete the
   copy (step 5). Above 5% of the snapshot, or space files counted under de-extinction, the session
   proposes space colonization entries. The ruling asks for them in this report while the task is open,
   so the PM decides whether the pull request waits for them or they move to a follow-up.

## Follow-up work

* **The first LD report's publish** reads the 7 scan hits the dry run found before publishing, as the
  runbook's step 3 says, then writes the release lock for `ld-2026-nov-dec-de-extinction` 1.0.0
  (`scripts/release_landscape_taxonomy.py`). For E32's publishing tasks.
* **A stale comment in `config/argument_taxonomy.yaml`** above the generic LD framing still says the
  de-extinction resolution is not committed. Left as v1-e08-t04 wrote it, as the brief asked; a one-line
  edit when the coach reviews the framing.
* **A permanent guided review for a seeded taxonomy**: `seed_landscape_taxonomy.py review --interactive`
  (or an apply step that reads the decisions file into the YAML), so a new topic's curation is one
  command for the coach rather than a sheet plus file listings. This task's one-off script is the
  prototype (Decision 8). For E32, or wherever the next topic's seeding lands.
* **The coach reviews taxonomy updates in the tub application** (the operator's request, 2026-11-05):
  after a new LD or PF topic starts, the coach would periodically review the seeded positions and the
  headings no position claims inside the tub app rather than the command line, with the decisions
  written back as the guided script writes them. Out of this task's scope; for the PM to place.
* **The late-disclosure count could be a report line**, so the weekly report shows Q2's check without a
  session (E32).
* **`landscape-copy-*` restores and a newer dev parser**: the runbook's report steps assume the installed
  build's parser matches the restored store; a branch ahead of the run image needs its own parse
  (Deviation 4). Worth a line in `landscape-report-from-the-cloud-run.md` (E40).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-05

**Notes:**

Built to the ruling point by point, counted before it was built, and the coach's review made workable
for the coach instead of being forced through a sheet.

1. **ac1 to ac4 pass.** The topic and its Florida Blue Key entry are in `topics.yaml` with space
   colonization untouched; 29 topic-map tests pin every snapshot to 2026-10-27 as before and 2026-11-03's
   split; 15 positions seeded from headings two or more teams used, the loader and config tests passing;
   the counts recorded; the coach's review applied and the dry run resolving the new topic at 1.0.0, the
   entry's week reported as 292 of 902.
2. **The ruling, checked:** only `bluekey` and `fbk` in configuration; the "Part of a week" notice and
   the partial base; the loader's refusals, the reach-back one made precise so that Q2's remedy stays a
   configuration change (Decision 1, accepted); Q3 by the held spelling; Q4's check done and recorded
   (neither space-only source comes only through a one-school spelling, so holds stands). Eight mutants
   caught, the two that first failed at import rewritten and run again rather than counted.
3. **Deviations accepted.** (1) The rule in `debate_core.domain.landscape` and `landscape_trends`, where
   the topic map and trends model live; the PM adds `debate_core.domain` to the spec's packages in the
   next batch. (2) `tournament_entry_snapshots` in `--json`: it is how the 292 of 902 is checked outside
   a unit test. (3) The four tournament names that are also schools' names left out of the quoted
   proposal. (4) ac4's dry run from this worktree over a copy parsed with `docx-9`: the installed build
   cannot read tournament entries; seeding read the run's own `docx-7` store, as asked.
4. **`generic.yaml` 1.2.0 adds LD-only positions**, so the NHI topic keeps 1.5.0 and no Policy count
   moves, as its changelog says. `v1-e32-t49` runs beside this task: once this merges, that session
   replays the kept 1.2.0 cassettes once more and confirms 23 of 33 before its re-record. The PM tells it.
5. **Decision 7, one `git fetch origin dev`:** a network call belongs to the operator, apart from
   `scripts/task sync`. Harmless here; not again.
6. **The 7 scan hits are a publish's matter**, as the report says: whoever publishes the first LD report
   reads them in the terminal first.
7. **The operator's decisions, ruled by the PM:**
   - **Q2's counts move to a follow-up the PM files** (E32, p2, not before the run of 2026-11-11): the
     late-disclosure count on 2026-11-10 and 2026-11-17 with the ruling's 5% trigger, and the report line
     that would make the check weekly without a session. This task's Goal stays `Succeeded`.
   - **A permanent guided review** (`seed_landscape_taxonomy.py review --interactive` and an apply step
     reading the decisions file into the YAML), this task's script as its prototype: filed (E32, p3).
   - **The coach reviewing taxonomy updates in the tub app**: filed (E39, p3, proposal first, after the
     guided review), writing the same decisions file, which the operator's apply step reads, so the app
     never writes configuration itself.
   - The stale comment in `config/argument_taxonomy.yaml` and the runbook line on a branch whose parser is
     ahead of the run image: the PM makes both edits in the next batch.
8. **Closing checks:** the changed directories and the always-run list (3,750 passed after the review),
   the two smoke files, ruff, pyright, lint-imports, thin handlers, the docs index, links, command blocks
   and the specs are clean; the 346-file affected set is the pull request's `ci` (agreement 10).
9. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.

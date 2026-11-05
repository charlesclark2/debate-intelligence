# Session report: v1-e32-t06-ld-de-extinction-taxonomy

| | |
|---|---|
| Task | `v1-e32-t06-ld-de-extinction-taxonomy` — LD de-extinction position taxonomy |
| Spec | [`plan_specs/v1/e32-argument-landscape/t06-ld-de-extinction-taxonomy.yaml`](../../plan_specs/v1/e32-argument-landscape/t06-ld-de-extinction-taxonomy.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t06-ld-de-extinction-taxonomy` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

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

## Summary

<!-- 3-6 sentences: what was built, how it fits the epic, anything the PM should look at first. -->

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

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

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

# Session report: v1-e32-t17-kritikal-affirmatives

| | |
|---|---|
| Task | `v1-e32-t17-kritikal-affirmatives` — Kritikal affirmatives identified, not left among the rounds with no identified aff |
| Spec | [`plan_specs/v1/e32-argument-landscape/t17-kritikal-affirmatives.yaml`](../../plan_specs/v1/e32-argument-landscape/t17-kritikal-affirmatives.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t17-kritikal-affirmatives` |
| Session status | IN PROGRESS: the counts are sent; nothing is built until the PM rules <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**The counts are done (ac1). Nothing is built yet:** the build waits on the PM's ruling on the
[questions](#questions-for-the-pm).

**K affs are a small share of the rounds with no identified aff.** On hspolicy26 through 2026-10-20,
under taxonomy 1.2.0, the report has 709 affirmative rounds with no identified aff. They disclose 565
files, by 203 teams. 555 of those files hold no `should` plan text.
* **25 of the 555 files have a K-aff marker:** 28 rounds, 21 teams.
  * The markers are a role of the ballot, an advocacy-statement label, `The 1AC is`, or a method
    label.
  * Carrying the identification to the same teams' other unidentified rounds would raise that to at
    most 55 rounds.
* **1 of the 25 has its marker placed under a K by its alias.** 2 have any heading placed under a K.
* **The K families are scattered.** Only 4 of the 25 files name a family in a heading. 18 files
  (15 teams) name one in a card tag, across 15 families. The largest is cap, with 5 teams.

**Most of the 555 files are not K affs:**
* 256 files (304 rounds, 93 teams) carry an advantage heading. These are policy affs whose plan text
  is not under a label;
* 224 files (312 rounds, 124 teams) have no heading that places anything;
* 75 files (78 rounds, 22 teams) place only negative positions, mostly read or answered in
  affirmative answer files.

**The recommendation is option (a):** one generic K-aff position per topic, of the existing `aff`
kind. No new position kind is needed. It still adds a position, so the taxonomy goes from 1.2.0 to
1.3.0 under t08's lock, and that costs an operator refill of three caches
([question 1](#questions-for-the-pm)).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| kritikal-affs | In progress | The counts are taken and sent (2026-10-25). Waiting for the PM's ruling before any rule, fixture or test |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any rule, over affirmative rounds with no identified aff, of files with K-aff markers and no plan text, by marker and team, sent to the PM with the options | PASS (sent, awaiting ruling) | [The counts](#the-counts-hspolicy26-through-2026-10-20-taxonomy-120) and [the questions](#questions-for-the-pm). Read-only: all 17 files under `landscape/` and `reports/` were checksummed before and after, and none changed. Nothing was built |
| ac2: after the ruling, the synthetic fixture's report shows kritikal affirmatives as their own group and the rounds still unidentified, matching a hand-written golden file; tests shown failing first; a taxonomy change passes the released-ids check | NOT RUN | Waits on the ruling |
| kritikal-affs node: `uv run pytest packages/debate_core/tests/application/test_landscape_report.py` | NOT RUN | Waits on the ruling |

## The counts (hspolicy26, through 2026-10-20, taxonomy 1.2.0)

### How they were read

**Guards.** Before every pass:
* no `DEBATE_*` variable was set and no `caselist pull` was running. Each command checked both and
  would have stopped otherwise;
* the load average was 4.4 to 6.8 on 11 cores, from other sessions.

**Time limits.** Each pass ran as `perl -e 'setpgrp(0,0); alarm 115; exec @ARGV' .venv/bin/python ...`.
* The limit sat on the interpreter, in its own process group.
* Inside, a 100 s `SIGALRM` raised in the parent. That closes the pool's generator, whose `finally`
  stops every worker.
* After every pass, `pgrep` found no worker or script process left. No pass reached either limit.

**The local store only.** The scripts built the services by hand over `~/.debate-research/dev`, as
`scripts/read_landscape_texts.py` does, so the container and the dev profile's bucket mode were never
involved. No bucket was built and nothing was published.

**Nothing was written.** The 17 files under `~/.debate-research/dev/landscape/` and `reports/` had
the same SHA-256 before the first pass and after the last.

**Counts only.** The scripts are scratch files outside the repository, and they printed counts only.
* Their scratch JSON holds source digests, t03's round ids, team keys, verdicts, position ids,
  placements, family ids and the normalized forms of short labels.
* A team key is a salted digest of the team, and the salt was never written.
* No paragraph, tag or cite text is in them. A grep of the files for `should`, `united states` and
  `school` found none.

**Reused, not rebuilt** (the PM's context):
* **The rounds and their affs** are t09's and t03's own.
  * Pass 1 ran `LandscapeRunService` as a dry run for snapshot 2026-10-20, with t09's
    `AffAssignmentService` and t11's texts left off, so it parsed nothing.
  * It captured the inputs handed to `LandscapeReportService` and called t03's `count()` on them.
  * A round has no identified aff when no aff position's reads include it. That is t03's rule:
    neither a `PLAN_TEXT` or `TEAM_CARRY` assignment nor a `PLACED_CARD`.
  * **The dry run gave 709 unidentified rounds of 2,192, the report's figure. Recomputed from the
    captured reads, it is 709 again.**
* **No plan text** is t09's verdict `NONE`, from the run's own plan-text reading, which came from
  the cache with no parse.
* **Roles of the ballot** are t11's `ROLE_OF_THE_BALLOT` readings from the analytic-text cache. All
  3,825 entries are current under this parser and these rules.
* **Placement** is t11's `heading_placement`: the nearest placed heading by t02's matcher, with the
  team's own names and the caselist's schools taken out. No second placement was written.
* **Card placements under a K** are t02's classifications from the same dry run.
* **The new labels** (advocacy, `The 1AC is`, method, K-aff headings) were read the way t11 reads its
  labels:
  * each source was parsed in memory from the blob store under a placeholder path (`blob_jobs`);
  * its paragraphs were read with `section_paragraphs_of`;
  * a label is a non-evidence paragraph of at most 8 words, normalized by t01's normalizer, or a
    sentence or inline opening.

**The families** are a word count, not a placement: whole-word phrases in a file's normalized headings
and in its card tags. They are listed under [the families](#the-k-families).

**The control.** The same reader read the 1,205 files of the identified affirmative rounds, to show
how specific each marker is.

### The files of the unidentified rounds

| | Files | Unidentified rounds | Teams |
|---|---|---|---|
| **All files of the 709 rounds** | **565** | **709** | **203** |
| t09 verdict `NONE`: no `should` plan text | **555** | 692 | 199 |
| `CONFLICTING` (two affs named) | 7 | 9 | 4 |
| `UNNAMED` (a plan text naming no aff) | 2 | 8 | 2 |
| `NAMES` (in a round whose other file conflicts) | 1 | 1 | 1 |
| Parsed again with no failure | 565 | | |

The 555 no-plan files, by what their headings place (t11's placement over each file's distinct
section paths):

| What the headings place | Files | Unidentified rounds | Teams |
|---|---|---|---|
| An advantage, READS | 256 | 304 | 93 |
| Nothing: no heading places anything | 224 | 312 | 124 |
| Negative positions only (DA, CP, K, T, theory), read or answered, and no advantage | 75 | 78 | 22 |

* 5 of the 555 files are also disclosed in a negative round.
* 90 no-plan files have a heading placed under a K, READS. 55 of them also have an advantage heading
  and 65 a DA or CP heading, so they are mostly aff answer files. Only 12 files (10 teams) hold K
  headings and no advantage, DA, CP or aff heading.

### K-aff markers

Over the 565 files, then the 555 with no plan text. A file counts once per marker:

| Marker | Files | Unidentified rounds | Teams | Of those, files with no plan text |
|---|---|---|---|---|
| Role of the ballot (t11's reader) | 15 | 16 | 11 | 15 |
| Advocacy-statement label | 2 | 4 | 2 | 2 |
| `The 1AC is` | 5 | 7 | 5 | 5 |
| Method label (`Method`, `Our method is`) | 5 | 5 | 5 | 5 |
| K-aff heading (`K aff`, `Kritikal aff`, `Critical aff`, `Performance aff`, `Method aff`) | **0** | 0 | 0 | 0 |
| **Any marker** | **25** | **28** | **21** | **25** |

* **Overlap:** 13 files hold a role of the ballot only, 5 a method label only and 5 `The 1AC is`
  only. The 2 advocacy files also hold a role of the ballot.
* **The forms found:**
  * role of the ballot: 12 sentences (`The role of the ballot is ...`), 3 inline, 2 labels;
  * advocacy: the label `Advocacy statement` twice. No `Advocacy` on its own, no `Our advocacy is`
    sentence and no inline `Advocacy:` in these files;
  * `The 1AC is`: 5 sentences;
  * method: `Our method is` in 4 paragraphs, `Method` alone in 2.
* **Left out: `Methods`.** It is in 11 paragraphs of the unidentified files, 8 of them under an
  advantage heading. In the control, all 8 files with the label have a plan text naming an aff.
  It is a policy aff's label, not a K aff's. With it, the method row would be 16 files and 15 teams.
* **Advocacy statements are counted, never shown** (data-use policy 1.13). No advocacy text was
  read into a scratch file or printed.

**Where the markers sit.** By t11's placement, in paragraphs:

| Marker | Headings place nothing | No heading | Placed under an advantage | Placed under a K |
|---|---|---|---|---|
| Role of the ballot (17) | 13 | 4 | 0 | 0 |
| Advocacy statement (2) | 2 | 0 | 0 | 0 |
| `The 1AC is` (5) | 3 | 1 | 1 | 0 |
| Method (6) | 3 | 2 | 0 | **1** (`Our method is`) |

**What else the 25 files hold:**
* 2 carry an advantage heading, READS, and none a DA or CP heading;
* 1 is also disclosed in a negative round, and every one has cards in the store;
* 1 holds a t11 K alternative reading.

**The control.** Of the 1,205 files of the identified rounds, 5 hold a K-aff marker under the
proposed list ([question 2](#questions-for-the-pm)), by 5 teams:
* a role of the ballot 3, an advocacy label 1, `The 1AC is` 1, a method label 0;
* 2 of the 5 have a plan text naming an aff.

The counting pass took any short label holding the word, so it also found two that the proposed list
does not match: a theory interpretation heading holding `advocacy`, and a method label naming its
method. They are left out of the 5. In the unidentified files every label found is on the list, so the
25 stand.

So a marker without a plan text is rare in a file whose round already has an aff (3 files). In the
unidentified rounds it holds in 25.

### Placed under a K by its alias

Of the 25 marker files with no plan text:

| | Files | Teams |
|---|---|---|
| The marker itself placed under a K (t11's placement) | **1** | 1 |
| Any heading of the file placed under a K, READS | 2 | 2 (cap-k, racial-capitalism-k, buddhism-k between them) |
| A card t02 placed under a K by `ALIAS` | 2 | 2 |

All 14 K positions of taxonomy 1.2.0 are on the negative side, and their aliases are `<name> k`
headings (`cap k`, `set col k`). A K aff's 1AC does not head itself that way, so the matcher seldom
places one.

### The K families

Whole-word phrases in the 25 files' normalized headings and card tags:

| Family | Files naming it in a heading | In a tag | Teams (heading or tag) |
|---|---|---|---|
| cap (capitalism, marxism) | 1 | 4 | 5 |
| biopolitics (biopower, necropolitics) | 0 | 4 | 4 |
| colonialism (coloniality, decolonial) | 1 | 6 | 3 |
| disability (ableism, crip, debility) | 0 | 3 | 3 |
| feminism | 1 | 3 | 3 |
| settler colonialism (set col) | 1 | 3 | 2 |
| antiblackness | 0 | 2 | 2 |
| pessimism | 0 | 2 | 2 |
| neoliberalism | 0 | 2 | 2 |
| afropessimism | 0 | 1 | 1 |
| racial capitalism, buddhism, nietzsche, ontology, deleuze | 1, 1, 1, 1, 0 | 0, 0, 1, 1, 1 | 1 each |

* **18 of the 25 files (15 teams) name a family somewhere. Only 4 name one in a heading.**
* A tag that names a family is weak evidence of which K an aff reads: an aff answer file names
  capitalism in tags as well.
* Over all 555 no-plan files, 118 name a family in a heading, but 90 of those headings are K
  headings in answer files ([above](#the-files-of-the-unidentified-rounds)).

### The teams behind each

* **Any marker:** 21 teams.
* **By marker:** role of the ballot 11, `The 1AC is` 5, method 5, advocacy statement 2.
* **Carry:** the 21 teams have 55 unidentified affirmative rounds in all. 28 of them hold a marker
  file.
* **Per family,** in the families table.
* No school or team code is in this report, the scratch files, or anything printed.

### Runtimes

| Pass | What it read | Wall-clock |
|---|---|---|
| Pass 1: the dry run, its inputs and the caches | the run (no parse) | 52.9 s for the dry run, 55.5 s in all |
| Pass 2 sample (1 shard of 20) | 29 files | 33.7 s (29.6 s reading the seed sources) |
| Pass 2, unidentified files, 2 shards, 7 workers | 565 files | 55.7 s and 56.0 s, each about 28 s of seed reading and 28 s of parsing |
| Pass 2, control, 4 shards, 7 workers | 1,205 files | 65.3, 63.8, 66.4 and 61.5 s |
| Tables | the scratch JSON | under 1 s |

**One rerun.** The first full pass 2 checked a file's negative disclosure against lower-case side
values, but `Side` is upper-case. So it found 0 negative files. I fixed the check and ran both
unidentified shards again. Every count above comes from those reruns and the control that followed.

## The options

**(a) One generic K-aff position per topic.** For example, `kritikal-aff`, labelled "Kritikal
affirmative": kind `aff`, side `aff`, no aliases.
* It is identified by the markers in a file with no plan text, as a new assignment method beside
  `PLAN_TEXT` and `TEAM_CARRY`.
* The report shows it as its own group in the Affirmative part.
* **Today it would take 28 rounds (21 teams).** That is 55 rounds if the identification carries to a
  team's other unidentified rounds as `TEAM_CARRY` does, with t09's guard.

**(b) K-aff positions named by the K they read,** as t09's mechanisms are.
* **They need new ids.** The 14 Ks are released with side `neg`, and t08's lock refuses a released id
  whose side changes. So these would be new `aff`-kind positions, such as `cap-kritikal-aff`.
* **The headings cannot name them:**
  * 1 marker is placed under a K;
  * 2 files have a heading placed under a K;
  * 4 files name a family in a heading.
* Naming them from tag words would be a second placement, which the PM's context rules out. Without
  it, almost every K aff falls back to an unnamed one.
* Spread by tag words, 15 families share 15 teams, and the largest, cap, has 5.

**Position kinds.** Neither option needs a new kind.
* A K aff is an affirmative case, and the `aff` kind already carries what the report needs:
  * t03's `_assignments` refuses an assignment to a position that is not an aff;
  * t15's advantages-by-aff section keys on aff positions.
* A new `PositionKind` would change the enum, the lock's recorded kinds and every kind switch in the
  report, for no count it would change.

**Either option is a taxonomy bump**, from 1.2.0 to 1.3.0. 1.2.0 is released, and the lock refuses a
position added at a released version. The bump changes the keys of three caches, so the first run
after it reads everything again. That is an operator block:
* t02's classifications;
* t09's plan texts, whose vocabulary digest covers the taxonomy (204 s on 2026-10-23);
* t11's analytic texts, whose rules digest covers it (551 s on 2026-10-24 under load).

## Files changed

Only this report, after the counts.

## Deviations from the spec

None so far.

## Decisions and assumptions

1. **"No plan text" is t09's `NONE` verdict.** The 10 files with `CONFLICTING`, `UNNAMED` or
   `NAMES` have a `should` plan text and are left out of the marker counts. None of them holds a
   marker in any case.
2. **`Methods` is not a method label** ([above](#k-aff-markers)). A rule after the ruling would leave
   it out, as t11 left out `Ballot` on its own.
3. **K-aff headings were looked for by their own words,** in pocket, hat and block headings: `k`,
   `kritik`, `kritikal`, `kritical`, `critical`, `performance` or `method` before `aff`,
   `affirmative` or `1ac`. None was found in either the unidentified or the control files. The 1AC
   heading itself normalizes to nothing.
4. **The family list was mine,** chosen to count only. It takes the 14 Ks of 1.2.0 by their own words
   (`cap`, `set col`, `antiblackness` and so on) and adds families the K-aff literature uses
   (`afropessimism`, `feminism`, `neoliberalism`, `deleuze`, `baudrillard`, `nietzsche`, `pessimism`,
   `trans`, `anthropocentrism`). It is not a proposal for the taxonomy.
5. **A team** is t03's (school, team code), compared without case, and only ever a salted key here.

## Operator follow-ups

None yet. After the ruling, a taxonomy bump makes the first run read the three caches again
([the options](#the-options)). That is an operator block, written with the build.

## Follow-up work

* **The 256 no-plan files that carry advantage headings** (304 rounds, 93 teams) are policy affs
  whose plan text is not under a label t09 reads. That is about 43% of the unidentified rounds, far
  more than K affs. Identifying an aff by its advantages, or from the plan text that sits without a
  label, belongs to t09's plan-text rule or a new task, not t17. Question 4 asks.

## Questions for the PM

Four, paste-ready:

```text
v1-e32-t17 counts (session, 2026-10-25). Read-only, local store only,
nothing written (17 files checksummed before and after), counts only.
hspolicy26 through 2026-10-20, taxonomy 1.2.0. Rounds and affs are the
dry run's own (t03 count over t09's assignments): 709 of 2,192 affirmative
rounds have no identified aff; they disclose 565 files by 203 teams, and
555 of those files have no `should` plan text (t09 verdict NONE).

K-aff markers in those 555 files (t11's ROB reader; the new labels read
as t11 reads labels; placement is t11's heading_placement):
  role of the ballot          15 files, 16 rounds, 11 teams
  advocacy statement label     2 files,  4 rounds,  2 teams (both also ROB)
  "The 1AC is"                 5 files,  7 rounds,  5 teams
  method label                 5 files,  5 rounds,  5 teams
  K-aff headings               0
  any marker                  25 files, 28 rounds, 21 teams
Control: 5 of the 1,205 files of identified rounds hold a marker on the
list in question 2 (2 with a plan text naming an aff).
Placed under a K by its alias: the marker itself 1 file; any heading of
the file 2; a card t02 placed under a K by ALIAS 2.
Families: 4 of the 25 name a K family in a heading; 18 (15 teams) in a
tag, across 15 families, the largest cap with 5 teams.
The rest of the 555: 256 files (304 rounds, 93 teams) carry advantage
headings, so they are policy affs with an unlabelled plan; 224 (312
rounds) place nothing; 75 (78 rounds) place only neg positions.

1. Option (a) or (b)?
   (a) one generic K-aff position per topic (say `kritikal-aff`, kind
       aff, side aff, no aliases), identified by a marker in a file with
       no plan text, as a new assignment method beside PLAN_TEXT and
       TEAM_CARRY, shown as its own group in the Affirmative part
       (t15's advantages-by-aff section as the model for where it sits);
   (b) K-aff positions named by the K they read: new aff-kind ids (the
       released Ks are side neg and the lock refuses a side change),
       named from headings, which name a K in 2 of 25 files; naming from
       tag words would be a second placement.
   Neither needs a new position kind: `aff` fits, and t03 refuses an
   assignment to a non-aff. Either is a taxonomy bump 1.2.0 -> 1.3.0
   under t08's lock (1.2.0 is released), which re-keys three caches:
   the first run after it re-reads classifications, plan texts (204 s)
   and analytic texts (551 s under load) - one operator block.
   Recommendation: (a). The headings cannot name the K, and (b) would
   split 21 teams over 15 families, most of them one team's.

2. The markers that identify a K aff, in a file with no plan text:
   t11's role-of-the-ballot labels; `Advocacy`, `Advocacy statement`,
   `Our advocacy (statement) is`, inline `Advocacy:`; `The 1AC is`;
   `Method` on its own, `Our method is`, inline `Method:`. Left out:
   `Methods` (11 paragraphs, 8 under an advantage; in the control all
   8 files with it name an aff by plan text). Approve the list?
   Recommendation: yes. `Methods` belongs to policy affs.

3. Carry: should a K-aff identification carry to the same team's other
   unidentified rounds, as TEAM_CARRY does (never into a round whose
   own plan text names an aff)? Without carry 28 rounds; with it at
   most 55, the 21 teams' unidentified rounds in all.
   Recommendation: yes, through t09's carry rule and guard, so a K aff
   and a policy aff are carried alike; the method table counts K-aff
   rounds by own marker and by carry.

4. Out of scope, for a decision: 256 of the 555 no-plan files (304
   rounds, 93 teams) carry advantage headings, so they are policy affs
   whose plan text sits under no label t09 reads. That is about 43% of
   the 709, far more than K affs. A follow-up task (t09's plan-text
   rule, or an aff identified by its advantages)?
   Recommendation: yes, a follow-up task; t17 stays on K affs.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

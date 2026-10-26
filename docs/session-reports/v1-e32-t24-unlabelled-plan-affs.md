# Session report: v1-e32-t24-unlabelled-plan-affs

| | |
|---|---|
| Task | `v1-e32-t24-unlabelled-plan-affs` — Policy affs whose plan text has no label, identified by the plan or the advantages |
| Spec | [`plan_specs/v1/e32-argument-landscape/t24-unlabelled-plan-affs.yaml`](../../plan_specs/v1/e32-argument-landscape/t24-unlabelled-plan-affs.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t24-unlabelled-plan-affs` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**The counts are taken and ready to send** ([the relay block](#questions-for-the-pm)). Nothing is built.
The session stops here for the PM's ruling, as the PM's context asked.

* **Most of these plan texts sit under one label that t09 does not read: `Thus the plan`.** Of t17's
  256 files (254 under taxonomy 1.3.0):
  * 180 hold a plan text under `Thus the plan` or `Thus plan`, or inline as `Thus the plan:`;
  * 52 more hold one under a bare `Thus` or `Therefore`.
  * In every case the plan text has t09's own shape: `should`, with a federal actor before it.
* **The advantages point to an aff no better than chance.**
  * Every advantage is read under 1 to 5 top-level affs, and single payer reads the most of all 16.
  * A rule that picks an advantage's majority aff names single payer for all 301 open rounds that
    read an advantage. In a control that leaves out each round's own team, it is right for 871 of
    935 plan-text rounds. That is the base rate: 871 of those 935 rounds are single payer anyway.
  * At the mechanism level the same rule is wrong in 204 of 720 control rounds.
* **The proposed rule** is a new method beside t09's and t17's. It reads a plan text under `Thus the
  plan`, `Thus plan`, inline `Thus the plan:` or a bare `Thus`, using t09's own shape and vocabulary.
  It applies only to rounds every existing method leaves open, and it has a carry.
  * Simulated over the counts, it identifies **327 rounds by their own plan text and 23 by carry (91
    teams)**.
  * That takes the rounds with no identified aff **from 669 to 319 of 2,192**.
  * All 17 rounds that t17's advantage guard refused get a policy aff.
  * No assignment moves, and no taxonomy bump is needed.
* **t17's method sentence** is in 3 no-plan files of the open rounds, 1 file of a K-aff round
  (already a K aff by another marker), and 0 of the 1,205 control files.
* **For the PM to rule:** the label list, the method names, and what happens to 9 K-aff rounds and 13
  `TEAM_CARRY` rounds whose own `Thus the plan` names a different aff. Under "never move" they stay as
  they are. Also the method sentence.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| unlabelled-plan-affs | In progress | The counts are taken (2026-10-26, below). The rule waits for the PM's ruling |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before building, read-only: where the 256 files' plan texts sit, and which affs their advantages point to, sent to the PM with a proposed rule | PASS once relayed | [The counts](#the-counts-hspolicy26-through-2026-10-20-taxonomy-130). The [relay block](#questions-for-the-pm) holds the proposed rule and the questions. Nothing was built |
| ac2: after the ruling, on synthetic fixtures, the rule identifies an unlabelled plan's aff, refuses a round whose own plan text names another, and the method table counts the new method's rounds; tests shown failing first | NOT RUN | Waits for the ruling |
| ac3: the operator's dry run on hspolicy26 before and after: rounds with no identified aff, by method | NOT RUN | After the build. The "before" is on record: the method table in [the base](#the-base) |
| unlabelled-plan-affs node: `uv run pytest packages/debate_core/tests/arguments/landscape` | NOT RUN | No code has changed yet |

## The counts (hspolicy26, through 2026-10-20, taxonomy 1.3.0)

### How they were read

These are t17's passes, rerun under 1.3.0 with t17's scratch scripts adapted.

**Guards.**
* Before every pass, no `DEBATE_*` variable was set and no `caselist pull` was running.
* The load average was 6.5 to 11.8.
* Each pass ran as `perl -e 'setpgrp(0,0); alarm 115; exec @ARGV' .venv/bin/python -I ...`, with a
  100 s `SIGALRM` inside, as in t17. No pass reached either limit.
* `pgrep` found no script or worker left after any pass.

**The local store only.**
* The scripts built the services by hand over `~/.debate-research/dev`. The container and bucket mode
  were not involved, and nothing was published.
* **Nothing was written:** the 19 files under `~/.debate-research/dev/landscape/` and `reports/` had
  the same SHA-256 before the first pass and after the last.

**Counts only.**
* The scripts and their scratch JSON are in the session's scratchpad, outside the repository.
* The JSON holds:
  * source digests and t03's round ids;
  * salted team keys (the salt was never written);
  * verdicts, position ids and categories;
  * label forms made only of listed words (`thus the plan`, `therefore`). Any other form is recorded
    as "other short label".
* No paragraph, tag or cite text is in them. A grep for `should`, `united states` and `school` found
  only the position id `should-t`.

**What each pass read:**

| Pass | What it read | Wall-clock |
|---|---|---|
| Rounds | `LandscapeRunService` as a dry run, t11's texts off, t09's `AffAssignmentService` on its warm cache, with the report's inputs captured and t03's `count()` called on them | 73.3 s (dry run 64.6 s) |
| Plan texts, sample (1 of 20) | 27 files | 29.9 s |
| Plan texts, open rounds, 2 shards, 7 workers | 534 files | 61.5 s, 62.0 s |
| Plan texts, control, 4 shards, 7 workers | 1,205 files | 83.2, 76.9, 83.8, 84.0 s |
| Plan texts, K-aff rounds | 31 files | 34.5 s |
| Tables | the scratch JSON | under 1 s each |

**How the plan-text pass read each file:**
* Each file was parsed in memory from the blob store under a placeholder path (t09's `blob_jobs`).
* Its paragraphs came from t11's `section_paragraphs_of`, and t11's `heading_placement` placed them.
* For each paragraph holding `should`, the pass kept:
  * its unit, and its word-count bucket;
  * the actor class before `should`;
  * whether t09's shape holds (`_shaped`: a federal actor before `should`, not the fifty states);
  * what comes before it: a t09 label, a short label of at most 6 words, a longer heading, or other
    text;
  * an inline label before a colon;
  * its placement;
  * the affs t09's vocabulary names in it, by t09's `named` and resolutional rules.

### The base

The dry run reproduces t17's table after the coach's families exactly:

| Method | Aff rounds |
|---|---|
| `PLAN_TEXT` | 1,172 |
| `TEAM_CARRY` | 254 |
| `PLACED_CARD` | 57 |
| `KRITIKAL_AFF_MARKER` | 31 |
| `KRITIKAL_AFF_CARRY` | 9 |
| Not identified | **669 of 2,192**, 190 teams |
| Of those, refused by t17's advantage guard | 17 |

* **The 669 rounds disclose 534 files.** By t09's verdict: `NONE` 524, `CONFLICTING` 7, `UNNAMED` 2,
  `NAMES` 1. In 652 of the rounds, every file is `NONE`.
* **t17's 256 files under 1.3.0** (no-plan files with a heading placed under an advantage, READS) are
  **254 files, 302 rounds and 93 teams**. The other 2 are files of K-aff rounds now, the 2 marker files
  that t17's counts said carry an advantage heading.
* **301 open rounds (94 teams) read an advantage** by t15's rule, a card placed under it READS on the
  round's own side. 300 of them are rounds of the 254 files.

### Where the plan texts sit

Each file is counted once, under the first category in this order that it meets. The first three are
labels t09 does not read, over a paragraph with t09's shape that is not card text. A file's rounds can
fall under two categories through two files, so the rounds column does not sum.

| Where the plan text sits | t17's 256 (254): files | rounds | teams | All 524 no-plan files: files | rounds | teams |
|---|---|---|---|---|---|---|
| Under a label naming the plan that t09 does not read: `Thus the plan`, `Thus plan`, inline `Thus the plan:` | **180** | 211 | 65 | **260** | 303 | 82 |
| Under a transition label alone: `Thus`, `Therefore` | **52** | 67 | 17 | 68 | 86 | 22 |
| A federal `should` analytic of at most 80 words, under no label | 11 | 12 | 9 | 50 | 63 | 25 |
| A federal `should` sentence as a heading | 0 | | | 3 | 3 | 2 |
| A federal `should` sentence only as a card tag | 1 | 1 | 1 | 7 | 7 | 2 |
| A federal `should` sentence only inside card text | 9 | 10 | 6 | 58 | 90 | 31 |
| A `should` analytic of another federal actor (Congress, an agency, the President, a court) | 0 | | | 0 | | |
| No `should` sentence a plan could be | 1 | 1 | 1 | 78 | 100 | 45 |

**The labels, by form,** over the 524 no-plan files. Each form is in one paragraph per file.

| Label t09 does not read | Files |
|---|---|
| `Thus the plan` | 172 |
| `Thus` | 53 |
| `Thus plan` | 51 |
| `Thus the plan:` inline | 37 |
| `Therefore` | 15 |
| `Hence`, `So` | 0 |

* t09 reads `The plan`. The normalizer keeps `thus`, so `Thus the plan` misses
  `PLAN_TEXT_LABELS`.
* **The reader matches t09's.** No open `NONE` file has a t09 label over a shaped paragraph. In the
  control's `NAMES` files, the same reading of t09's own labels names t09's aff in 929 of 931
  paragraphs, the same top-level aff in 1, and another in 1.
* **No other actor is missed.** A `should` with Congress or an agency as its actor adds nothing to any
  count. t09's federal-actor shape holds for these plans.

**What those labels name** (`Thus the plan`, `Thus plan`, inline, `Thus`, `Therefore`), by t09's
vocabulary and resolutional rule:

| | t17's 256 (254) | All 524 |
|---|---|---|
| Names one aff | **199** | 289 |
| A plan text naming none | 33 | 39 |
| No such label | 22 | 196 |
| Of "names one", only the resolutional aff (`nhi-aff`) | 1 | 2 |

### The control: the same labels in files whose round already has an aff

* **The control is t17's: the 1,205 files of the rounds identified by `PLAN_TEXT`, `TEAM_CARRY` or
  `PLACED_CARD`.** These labels appear almost only where t09 reads no plan text: in 1 `NAMES` file,
  naming the same aff.
* **The test is the 254 `TEAM_CARRY` rounds,** whose aff came from the team's other rounds. 142 hold
  one of these labels in their own files. What the label's plan text names, against the carried aff:

| Label | The carried aff | The same top-level aff, another level | Another top-level aff | Names none |
|---|---|---|---|---|
| `Thus the plan`, `Thus plan`, inline (paragraphs) | 61 | 31 | 11 | 1 |
| `Thus` (paragraphs) | 5 | 22 | 0 | 13 |
| `Therefore` (paragraphs) | 0 | 3 | 3 | 0 |
| **By round** | **64** | **51** | **13** | **14** |

So where these labels name an aff, they agree with the team's carried aff at the top level in 115 of
128 rounds. `Therefore` is the weak one: it disagrees in 3 of its 6 paragraphs.

### What a rule would identify

This is a simulation over the counts. Each variant:
* runs after every existing method and moves no assignment;
* reads only files whose t09 verdict is `NONE`;
* takes a round whose files name two affs as conflicting, and assigns it nothing;
* carries by t09's rule: a team whose identified affs, existing and new, narrow to one carries it
  into its open rounds that hold no plan text of their own.

| Rule | Own plan text | Carried | Teams | Left conflicting | Carries refused (own plan text names none) | Unidentified after |
|---|---|---|---|---|---|---|
| Plan labels only (`Thus the plan`, `Thus plan`, inline) | 284 | 18 | 79 | 9 | 12 | 367 |
| **Plan labels and `Thus` (proposed)** | **327** | **23** | **91** | 9 | 14 | **319 of 2,192** |
| Plan labels, `Thus` and `Therefore` | 339 | 21 | 97 | 9 | 32 | 309 |
| As the last row, and federal `should` analytics of at most 80 words under no label | 385 | 14 | 115 | 9 | 36 | 270 |
| As the last row, and Congress or an agency as actor | 385 | 14 | 115 | 9 | 36 | 270 |

**The proposed rule's 350 rounds:**

| By top-level aff | Rounds |
|---|---|
| `single-payer-aff` | 324 |
| `nhi-aff` (11 of them by the resolutional rule) | 11 |
| `eco-nhi-aff` | 8 |
| `incarceration-aff` | 4 |
| `tiered-nhi-aff` | 3 |

* **By mechanism:** `single-payer-aff` itself 259, `global-budgets-aff` 29, `single-public-authority-aff`
  27, `prescription-drug-coverage-aff` 4.
* **All 17 rounds** that t17's advantage guard refused are among them.
* **Of the 301 open rounds that read an advantage, 231 are among them.** 70 stay open (26 teams):
  * 35 hold a plan text that names no aff;
  * 34 hold no plan text these labels mark;
  * 1 is conflicting.
* **Why `Therefore` is left out:** it adds 12 rounds of its own but blocks 18 carries, and it
  disagrees in 3 of its 6 control paragraphs.
* **Why the unlabelled analytics are left out:** they add 46 rounds, but the `TEAM_CARRY` control's
  "another top-level aff" goes from 13 to 21.

### Rounds that already have an aff and hold one of these plan texts

The PM's rules for the build keep these as they are. These are their sizes:

| Method | Rounds | Of those, the label names a policy aff |
|---|---|---|
| `KRITIKAL_AFF_CARRY` | 9 | **7** |
| `KRITIKAL_AFF_MARKER` | 31 | 2 |
| `TEAM_CARRY` | 254 | 13 name another top-level aff than the carried one ([the control](#the-control-the-same-labels-in-files-whose-round-already-has-an-aff)) |

t17's K-aff carry reads t09's `NONE`, so it could carry into a round whose plan text sits under `Thus
the plan`. 7 of its 9 carried rounds are such rounds.

### Which affs the advantages point to (t15's advantages by aff)

**t15's mapping is built from the 1,466 assigned rounds:** each advantage, under the top-level affs and
mechanisms whose assigned rounds read it. Teams are counted.

| Advantage | Top-level affs reading it | Teams | Single payer's teams |
|---|---|---|---|
| `costs-advantage` | 3 | 109 | 102 |
| `disease-advantage` | 2 | 86 | 85 |
| `economy-advantage` | 3 | 80 | 74 |
| `inequality-advantage` | 5 | 69 | 64 |
| `coverage-advantage` | 4 | 63 | 59 |
| `growth-advantage` | 3 | 41 | 39 |
| `access-advantage` | 1 | 32 | 32 |
| `bioterror-advantage` | 2 | 20 | 19 |
| `pandemics-advantage` | 2 | 20 | 17 |
| `budgets-advantage` | 3 | 19 | 17 |
| `stagnation-advantage` | 2 | 16 | 15 |
| `innovation-advantage` | 4 | 12 | 8 |
| `data-advantage` | 1 | 9 | 9 |
| `sustainability-advantage` | 1 | 8 | 8 |
| `pharma-advantage` | 1 | 7 | 7 |
| `biotech-advantage` | 2 | 6 | 5 |

**At the mechanism level,** each advantage is read under 3 to 9 affs. No advantage has a `parent` in
the taxonomy, so the advantages can point only through these reads.

**The 301 open rounds that read an advantage** read 1 advantage (100 rounds), 2 (163), 3 (33) or 4 (5).

| Rule over the round's advantages | One aff | Several | None |
|---|---|---|---|
| Any aff reading one of them (top level) | 9 rounds (4 teams) | 292 | 0 |
| Same, the K aff left out | 14 | 287 | 0 |
| An aff reading every one of them (top level) | 51 | 250 | 0 |
| Only affs with at least half an advantage's teams (top level) | **301, all `single-payer-aff`** | 0 | 0 |
| Only affs with at least half an advantage's teams (mechanism) | 194 | 0 | 107 |

**The control leaves out each round's own team,** then asks this of the 935 `PLAN_TEXT` rounds that
read an advantage:

| Rule | Right | Wrong | Several or none |
|---|---|---|---|
| Any aff reading one of them (top level) | 29 | 0 | 906 several |
| At least half an advantage's teams (top level) | **871** | **64** | 0 |
| At least two thirds (top level) | 866 | 64 | 5 none |
| At least half (mechanism) | 516 | **204** | 212 none, 3 several |

The majority rule's 871 equals the base rate: 871 of the 935 rounds are single payer. It never names
anything else, so it adds nothing an unconditional "single payer" would not. At the mechanism level it
is wrong in 28% of the rounds it names.

### t17's method sentence

The sentence is `The`, `Our` or `My` with `method` or `methodology`, then `is`, `will` or `should`.
t17's counting regex was read outside headings.

| Files | Hold it | Notes |
|---|---|---|
| The 524 no-plan files of the open rounds | **3** (3 rounds, 3 teams) | 2 in a tag, 1 in an unstyled paragraph. Placed: 1 under a K, 1 where the headings place nothing, 1 with no heading. None holds a K-aff marker, an advantage heading or read, or one of the plan labels above |
| The 31 files of the K-aff rounds | 1 | A `KRITIKAL_AFF_MARKER` round, already a K aff by another marker |
| The control (1,205) | **0** | |

Widening t17's sentence to this form would add at most 3 rounds by their own marker, before any carry.
Their teams' other open rounds were not counted.

## Files changed

* This report. Nothing else: no code, config or spec has changed.

## Deviations from the spec

None so far.

## Decisions and assumptions

1. **The 256 are re-counted under 1.3.0:** 254 files. The other 2 are now files of K-aff rounds, as
   t17 recorded.
2. **"Where the plan sits" uses t09's own shape:** `should` with a federal actor before it, never the
   fifty states. That is what a widened reader would keep. The other-actor row shows nothing is lost
   by it.
3. **A label is a paragraph of at most 6 words** before the plan text, as t09's `_LONGEST_LABEL_WORDS`.
   An inline label is at most 5 words before a colon.
4. **The simulation reads t09's carry rule as it is.** A carry needs a team whose identified affs
   narrow to one, and it never goes into a round whose own plan text exists and names none. A team
   that already holds a K aff and a policy aff disagrees, and carries nothing.

## Operator follow-ups

None yet. After the build, ac3 needs one operator block. It re-reads the plan-text cache under a new
rule version (about 205 to 305 s, as t17's refills), then runs the dry run for the method table.

## Follow-up work

None yet.

## Questions for the PM

Paste-ready:

```text
v1-e32-t24 counts (session, 2026-10-26). Read-only, local store only, nothing
written (19 files checksummed before and after), counts only. hspolicy26
through 2026-10-20, taxonomy 1.3.0. The dry run reproduces t17's table:
669 of 2,192 aff rounds unidentified (190 teams), 17 refused by the
advantage guard. t17's 256 no-plan files with an advantage heading are 254
under 1.3.0 (302 rounds, 93 teams); the other 2 are K-aff rounds' files now.

Where their plan texts sit (each file once, first category that holds):
  under `Thus the plan` / `Thus plan` / inline `Thus the plan:`   180 files (211 rounds, 65 teams)
  under a bare `Thus` or `Therefore`                                52 files (67 rounds, 17 teams)
  a federal should analytic under no label                         11
  only inside card text 9; only as a tag 1; none 1; another actor (Congress, an agency) 0
Every one has t09's shape (should, a federal actor before it). t09 reads
`The plan`, but the normalizer keeps `thus`. Over all 524 no-plan files:
Thus the plan 172, Thus 53, Thus plan 51, inline 37, Therefore 15.
What they name: 199 of the 254 one aff, 33 none, 22 hold no such label.

Control (the 254 TEAM_CARRY rounds, aff from the team): 142 hold such a
label; it names the carried aff 64, the same top-level aff at another level
51, another top-level aff 13, none 14. Therefore: 3 of its 6 disagree.

Advantages (t15's advantages by aff): every advantage is read under 1-5
top-level affs, single payer the most of all 16. The majority-aff rule
names single payer for all 301 open rounds reading an advantage; with each
round's own team left out it is right in 871 of 935 PLAN_TEXT rounds, which
is the base rate (871 of 935 are single payer). By mechanism it is wrong in
204 of 720. Advantages do not identify an aff here.

1. The rule. A new method beside PLAN_TEXT, TEAM_CARRY, KRITIKAL_AFF_MARKER
   and KRITIKAL_AFF_CARRY: in a file t09 reads as NONE, a plan text under
   `Thus the plan`, `Thus plan`, inline `Thus the plan:` or a bare `Thus`,
   with t09's shape and vocabulary (resolutional rule included). Only into
   rounds every existing method leaves open, every file NONE; two affs
   named is conflicting, nothing assigned. A carry by t09's rule and guard.
   No advantage rule. No new ids, so no taxonomy bump; the plan-text rule
   version moves, so ac3 starts with one operator re-read (about 205-305 s).
   Simulated: 327 rounds by own plan text, 23 by carry, 91 teams; 669 ->
   319 unidentified; all 17 advantage-guard refusals get a policy aff.
   (With Therefore: 339 + 21 -> 309, but it blocks 18 carries and disagrees
   3 of 6. Adding federal should analytics under no label: -> 270, but the
   control's disagreements go from 13 to 21.)
   Recommendation: as written, Therefore and unlabelled analytics left out.

2. Names: TRANSITION_PLAN_TEXT for the round's own plan text and
   TRANSITION_PLAN_CARRY for the carry, two rows in the method table, as
   t17's two?
   Recommendation: yes; the carry kept apart so TEAM_CARRY's 254 do not
   change.

3. Rounds that keep their aff under "never move": 7 of t17's 9
   KRITIKAL_AFF_CARRY rounds and 2 of its 31 KRITIKAL_AFF_MARKER rounds hold
   a `Thus the plan` text naming a policy aff; 13 TEAM_CARRY rounds hold one
   naming another top-level aff. Options:
   (a) leave all of them, and count them in the method table as a control
       row (as t17's control);
   (b) let the new reading refuse t17's K-aff carry where the round's own
       file holds such a plan text (moves 7 rounds; changes t17's method).
   Recommendation: (a). The rules say t17's methods stay; the row puts the
   7 on record for a later ruling.

4. t17's method sentence (The|Our|My + method|methodology + is|will|should):
   3 no-plan files of the open rounds (3 rounds, 3 teams; 2 in tags, none
   with a plan label, a K marker or an advantage), 1 file of a K-aff round
   already a K aff, 0 of the 1,205 control files.
   Recommendation: widen it. It is specific (0 in the control) but small (at
   most 3 rounds before carry). It is a marker-list change in t17's reader,
   so it needs your ruling under "t17's K-aff methods stay".
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

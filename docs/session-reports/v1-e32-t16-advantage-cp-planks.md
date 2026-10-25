# Session report: v1-e32-t16-advantage-cp-planks

| | |
|---|---|
| Task | `v1-e32-t16-advantage-cp-planks` — An advantage counterplan's planks, and the advantage each one solves |
| Spec | [`plan_specs/v1/e32-argument-landscape/t16-advantage-cp-planks.yaml`](../../plan_specs/v1/e32-argument-landscape/t16-advantage-cp-planks.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t16-advantage-cp-planks` |
| Session status | IN PROGRESS: counts taken and sent to the PM with the proposed plank rule; nothing built, waiting for the ruling <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Counts only so far (ac1); nothing is built.** They were taken read-only on hspolicy26 through
2026-10-20 under taxonomy 1.2.0, using t11's reader and placement. They change the picture the spec
starts from:

* **An advantage CP's planks are a list, not further `should` analytics.** Under `advantage-cp`,
  14 teams have a CP text by its place. 12 of them write it as a short stem ending in a colon
  (`... should:`), followed by one paragraph per plank with no `should` and no actor. Word's list
  numbering is not in the paragraph text, so nothing marks them as planks except their place.
  Only 1 block holds two `should` analytics.
* **So t11 drops every plank, not only plank 2 onward.** The 12-team "text" it quotes for
  `advantage-cp` is the shared stem.
* **The proposed rule finds 152 planks under `advantage-cp`** (14 teams), 297 under `states-cp`
  (28 teams) and 13 under three other CPs (one team each).
* **Most planks name no advantage.** Under `advantage-cp`, 24 of 152 name one in their own words,
  each with a one-word alias. None has a heading or card of its own that names one. 128 name none.
* **The planks are almost all different.** 92 of `advantage-cp`'s 103 distinct planks are one
  team's, so a top 3 per CP would show 6 of its 114 team-plank pairs. Cut-off question below.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| advantage-cp-planks | In progress | The counts (2026-10-25), sent to the PM. The build waits for the ruling |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any rule, of advantage-CP blocks with several `should` analytics, plank labels or numbered planks, and of planks naming an advantage by heading, card or own words, or none, sent to the PM with the proposed plank rule | PASS (sent 2026-10-25, ruling pending) | [The counts](#the-counts-hspolicy26-through-2026-10-20), [the proposed rule](#the-proposed-plank-rule), [the questions](#questions-for-the-pm). Nothing was built before them |
| ac2: after the ruling, on synthetic sources, report.md shows each multi-plank CP's planks with team counts and what each solves or "not named", matching hand-written golden files; never beside a school or team code; a plank naming a school withheld and counted; tests shown failing first | NOT RUN | Waits for the ruling |
| ac3: the operator's refill of the analytic-text cache and a dry run without `--publish` on hspolicy26, with the scan's hits by section (operator) | NOT RUN | After the build |
| advantage-cp-planks node: `uv run pytest packages/debate_core/tests/application/test_landscape_report.py` | NOT RUN | After the build |

## The counts (hspolicy26, through 2026-10-20)

### How they were read

* **Guards.** Every run was read-only and started from a check, made by the script itself:
  * no `DEBATE_*` variable set;
  * no `caselist pull` running.
* **Time limits.** Each run had `perl -e 'alarm 115'` on the interpreter. Its parent also set its
  own 100 s alarm, which unwinds through the pool runner's `finally` and stops the workers.
* **Orphans.** After every run, a check for my worktree's spawn workers found none.
  * Six workers from the `dev-preview` worktree, with their parent alive, were someone else's run.
* **The guard fired once:** see [Decisions 4](#decisions-and-assumptions).
* **Load.** The load average was 4 to 12 on 11 cores, so the pools ran 7 workers.
* **Output.** The script is a scratch file outside the repository.
  * It printed counts only.
  * Its scratch files hold digests, element indexes, word counts, flags, position ids and taxonomy
    aliases. They hold no paragraph text and no names.
* **The sources:** t02's reader (`read_seed_sources`), as t11 read them. That is 3,825 on-topic
  sources, of which **2,070 are negative**.
  * Each source was parsed in memory by the code's parser, under a placeholder path, through t09's
    `blob_jobs`.
  * All 2,070 parsed: 0 failed.
* **t11's reader and placement, reused:**
  * `section_paragraphs_of`;
  * `heading_placement`, the label's own `section_path` cut as a card's, normalized with the team's
    names and the caselist's schools taken out;
  * `passes_actor_guard`;
  * `read_analytic_texts`, for a cross-check.

  There is no second placement.
* **Terms:**
  * **A CP text by its place** is t11's: a `should` analytic the store does not keep, of at most 120
    words, whose nearest placed heading is a CP the team reads.
  * **A block** runs from one pocket, hat or block heading to the next.
  * **Teams** are the negative disclosing teams' opaque identities.
* **Naming an advantage** uses t02's alias table, whole phrase only:
  * **A heading** names one when it normalizes to an alias of an advantage, or to `solves <alias>`
    (also `cp solves`, `<alias> solvency`).
  * **A card** names one when its tag holds `solves <alias>` as whole words, or is an alias.
  * **A plank's own words** name one when they hold an alias as a whole phrase.
  * "Advantage" means a position of kind `advantage`, on the aff side. An aff plan's alias
    (`medicare for all`) is counted apart.

### Blocks under each CP (the first pass, all 2,070 negative sources)

**The CPs selected:** `advantage-cp`, plus every CP with a block holding two or more `should`
analytics. That adds `states-cp` and `nhs-cp`, and no other CP.

| | advantage-cp | states-cp | nhs-cp |
|---|---|---|---|
| Blocks with a CP text by its place (blocks, documents, teams) | 31, 30, **14** | 101, 100, 40 | 6, 6, 4 |
| ... with 2 or more `should` analytics | **1, 1, 1** | 13, 13, 6 | 1, 1, 1 |
| ... with 2 or more past the actor guard | 0 | 8, 8, 5 | 0 |
| ... with an inline plank label (`Plank 2:`, `2.`, `Second,`) | 7, 6, 5 | 29, 12, 4 | 0 |
| ... with a plank label on its own paragraph | 0 | 0 | 0 |
| Plank headings (`Plank 1 ...`) in the CP's section | 3 headings, 1 doc, 1 team | 0 | 0 |
| **One paragraph with numbered planks** (2 or more `1.`, `(1)` or `Plank 1`) | 0 | 0 | 0 |
| One `should` analytic with 2 or more ordinals (`first ... second`) | 0 | 0 | 0 |
| One `should` analytic with 2 or more `should`s | 0 | 2, 2, 2 | 0 |

The other CPs with a CP text by its place have no block with two `should` analytics:
* `public-option-cp`: 13 blocks, 8 teams;
* `vouchers-cp`: 5 blocks, 4 teams;
* `delay-cp` and `smokers-pic`: 3 blocks each;
* `taxes-pic`: 1 block.

### What follows the CP text (the second pass)

This pass re-read every negative source holding the CP's section: a stored card any of whose path
prefixes places under the CP, or a CP-text block from the first pass. That is 264 sources for the
three CPs, then 25 for the others. In it, the "list" is every paragraph after the CP text in its
block, up to the first card or heading, that is an analytic, undertag or unstyled paragraph the
store does not keep.

| CP text by its place | advantage-cp | states-cp |
|---|---|---|
| CP texts (texts, documents, teams) | 32, 30, 14 | 114, 100, 40 |
| ... under 20 words | 30 | 75 |
| **... ending in a colon** (a stem) | **24, 23, 12** | 65, 64, 25 |
| Stems followed by 2 / 3 / 4 / 5 or more list paragraphs | 2 / 3 / 4 / **15** | 20 / 5 / 4 / 36 |
| Stems whose list ends at a card / a heading / the CP's end | 22 / 1 / 1 | 65 / 0 / 0 |
| Texts not ending in a colon (documents, teams) | 8, 8, 4 | 49, 42, 25 |
| Distinct texts; teams on the commonest | 6; **12** | 38; 9 |

**Every stem passes the actor guard:** 24 of 24 under `advantage-cp` and 68 of 68 under the other
CPs. **No list plank passes it on its own words:** 0 of 143, and 6 of 279 elsewhere. The plank names
no actor; the stem does.

**Other findings in the `advantage-cp` section.** 80 negative documents (38 teams) hold the section,
counting cards anywhere under it.
* **50 documents (26 teams) hold no CP text by its place.** 44 of them hold the CP's cards only:
  solvency files, or a text the store keeps as a card's tag.
* **Cards naming an advantage:** 32 tags in 20 documents, 13 teams. 9 lists (6 teams) are followed,
  before the next CP text, by such a card. It comes after the whole list, so it names no one plank.
* **Headings naming an advantage** (`Solves <advantage>`): 14 in 10 documents, 4 teams. None follows
  a list.
* **`solves` with words that are no alias** (an impact the taxonomy does not name): 87 card tags (21
  teams) and 27 headings (9 teams).

### The planks under the proposed rule

The rule is [below](#the-proposed-plank-rule). A list plank is at most 60 words; the longest found
is 47.

| | advantage-cp | states-cp | public-option-cp, taxes-pic, vouchers-cp |
|---|---|---|---|
| **Planks** (planks, teams) | **152, 14** | 297, 28 | 4, 4 and 5; one team each |
| ... in a list after a stem | 143, 12 | 266, 25 | all 13 |
| ... separate, in the CP text's block (a further `should` analytic past the guard, or a labelled plank) | 9, 3 | 31, 4 | 0 |
| List planks' words: median, 90th percentile, longest | 9, 23, 31 | 7, 17, 47 | |
| **Named by a heading or card under it** | **0** | 0 | 0 |
| **Named by its own words, one advantage** | **24, 10** | 10, 5 | 2 (`public-option-cp`) |
| ... of which say `solves <advantage>` | 1 | 0 | 0 |
| Its own words name 2 advantages or more | 0 | 4, 2 | 0 |
| **Naming none** | **128, 14** | 283, 28 | 11 |
| Its own words name an aff plan (not counted as solving) | 5, 2 | 20, 5 | 0 |
| **Naming a school** (to be withheld) | 0 | 0 | 0 |
| Distinct planks, by normalized words; read by one team | 103; **92** | 66; 47 | 13; 13 |
| Team-plank pairs; on the top 3 / 5 / 10 | 114; **6** / 10 / 20 | 152; 44 / 72 / 87 | |

**The advantages planks name in their own words, all by a one-word alias.**
* Under `advantage-cp`: `costs` 6, `budgets` 5, `innovation` 3, `disease` 3, `coverage` 2,
  `inequality` 2, `pandemics` 2 and `bioterror` 1. No multi-word alias matched.
* Under `states-cp`: `coverage` 7, `costs` 4, `access` 4, `budgets` 2 and `innovation` 1.

**Short list paragraphs.** 16 list paragraphs under `advantage-cp` are 3 words or fewer. 14 of them
are unstyled, and 4 of those are an advantage's alias and nothing more. They may be a label naming
the next plank; the counts cannot tell.

**t11's cross-check.** In the first pass's multi-plank blocks, t11 keeps plank 1 as its CP text by
place in 4 of the 6 `advantage-cp` blocks, and keeps none of planks 2 onward (13 planks).

### Runtimes

| Pass | What it read | Wall-clock |
|---|---|---|
| Sample | 52 negative sources | 40.1 s, the reader 31.6 s of it |
| **First pass**, 8 shards, 7 workers | all 2,070 negative sources | 60.6, 55.5, 52.8, 74.4, 65.7, 63.5, 59.7 and 53.7 s; the reader 25.9 to 33.6 s of each |
| **Second pass**, 2 shards, 7 workers | the 264 sources with the three CPs' sections | 45.5 to 64.0 s a shard, three times (two more fields were added each time) |
| Second pass, the other CPs | 25 sources | 32.3 s |
| Aggregations | the reader and the scratch files | under 40 s each |

## The proposed plank rule

1. **A plank hangs off a CP text t11 already reads**, by label or by its place, past t11's guard. A
   CP text has planks in one of two shapes:
   * **A list.** The CP text ends in a colon. Its planks are the paragraphs that follow it in its
     block, up to the first card or heading. Each is an analytic, undertag or unstyled paragraph the
     store does not keep, of at most 60 words. A list paragraph that is only an advantage's alias
     (4 today) names the plank after it and is not a plank (question 1).
   * **Separate planks.** In the CP text's block, each further `should` analytic past the actor
     guard is a plank, and so is each paragraph opening with a plank label (`Plank 2:`, `2.`,
     `Second,`).

   A CP text with neither shape stays one text, as today.
2. **The actor guard** applies to every plank. A list plank passes it through its stem, since the
   stem names the actor and the plank never does (0 of 143). A separate plank passes it on its own
   words, or by its label (question 2).
3. **What it solves**, never guessed. A plank solves every advantage named:
   * by a card under it, between it and the next plank, whose tag says `solves <alias>` or is an
     alias;
   * by a heading under it that normalizes to an alias or to `solves <alias>`;
   * or by its own words holding an advantage's alias as a whole phrase.

   Otherwise it shows "solves: not named". Only positions of kind `advantage` count. A card after a
   whole list names no one plank. An impact the taxonomy does not name is not shown (question 3).
4. **Shown in report.md only,** under the CP's texts, never beside a school or team code. Planks are
   grouped by their normalized words (t11's digest), with their team counts, and cut off at t11's
   top 3 (question 4). A plank naming a school of the caselist is withheld and counted: 0 today.

## Files changed

* This report only. The counting script is a scratch file outside the repository.

## Deviations from the spec

None so far.

## Decisions and assumptions

1. **A list was counted although the spec names only `should` analytics, labels and numbered
   paragraphs.** The `should` count alone (1 block) could not explain 14 teams. The second pass
   looked at what follows the CP text, and found the planks there.
2. **The CPs counted** are `advantage-cp` and every CP with a block of two or more `should`
   analytics (`states-cp`, `nhs-cp`), as asked. The other CPs were then checked for lists too:
   three have one, each one team's.
3. **"An alias of an aff-side position"** was split into advantages and aff plans. A plank naming the
   plan (`medicare for all`) says what it changes, not what it solves.
4. **The pull guard fired once, falsely.** It matched another session's shell, whose own command line
   held the text `pgrep -f "caselist pull"`. I made the script skip shell processes (`zsh`, `bash`,
   `sh`) and kept everything else. A real pull runs as `uv` or Python, and would still stop it. That
   shard was then run again.

## Operator follow-ups

None yet. The cache refill and the dry run (ac3) come after the build, in t11's shape.

## Follow-up work

None yet.

## Questions for the PM

Paste-ready:

```text
v1-e32-t16 counts (session, 2026-10-25). Counts only, nothing built.
hspolicy26 through 2026-10-20, taxonomy 1.2.0, t11's reader and placement
(section_paragraphs_of, heading_placement, the actor guard), all 2,070
negative sources re-read in memory, 0 failed; then the 264 holding the CPs'
sections. Every run guarded and time-limited, no worker left behind.

What the counts show. An advantage CP's planks are a list, not more "should"
analytics. Under advantage-cp, 14 teams have a CP text by its place; only 1
block holds two "should" analytics and 6 blocks (5 teams) label their planks.
But 24 of the texts (23 docs, 12 teams) are a short stem ending in a colon
("... should:"), followed by one paragraph per plank with no "should" and no
actor (2 to 5+ paragraphs, ending at the first card). Word's list numbers are
not in the text. So t11 shows the stem (its 12-team "text") and drops every
plank, not only plank 2 onward. No CP has one paragraph with numbered planks.

Under the proposed rule (below):
- advantage-cp: 152 planks, 14 teams (143 in lists, 9 separate).
  No heading or card under a plank names an advantage. 24 planks (10 teams)
  name one in their own words, each by a one-word alias (costs 6, budgets 5,
  innovation 3, disease 3, coverage 2, inequality 2, pandemics 2, bioterror 1).
  128 name none. 9 lists are followed by a card naming an advantage, after
  the whole list. 0 name a school.
- states-cp: 297 planks, 28 teams; 10 name one advantage, 4 name two or
  more, 283 none. Three other CPs: 13 planks, one team each.
- advantage-cp's planks are almost all different: 103 distinct, 92 read by
  one team, 114 team-plank pairs; a top 3 per CP covers 6 of them.

The proposed rule. A plank hangs off a CP text t11 already reads. (a) A list:
the CP text ends in a colon, and its planks are the following paragraphs in
its block up to the first card or heading (analytic, undertag or unstyled, not
kept, at most 60 words). (b) Separate: further "should" analytics past the
guard, or paragraphs opening "Plank 2:", "2.", "Second,", in the CP text's
block. What it solves: a card or heading under the plank naming an advantage
by alias or "solves <alias>", or its own words holding an advantage's alias as
a whole phrase; every one named is listed; otherwise "solves: not named".
report.md only; a plank naming a school withheld and counted.

1. Approve the rule, lists included? And the 4 list paragraphs that are only
   an advantage's alias: (a) a label naming the plank after it, not a plank;
   (b) a plank like any other.
   Recommendation: the rule as written, and (a). Without lists the section
   would show 9 advantage-cp planks from 3 teams.

2. The actor guard on every plank. 24 of 24 stems pass it; 0 of 143 list
   planks do on their own words, since the plank names no actor.
   (a) A list plank passes through its stem; a separate one on its own words
       or its label.
   (b) Every plank on its own words: no list plank would show.
   Recommendation: (a).

3. What counts as naming. (a) Advantages only, by any alias, one-word ones
   included (all 24 matches are one-word); (b) also aff plans (5 advantage-cp
   planks name a plan); (c) multi-word aliases only (0 matches). Impacts the
   taxonomy does not name ("solves <other words>": 87 card tags, 27 headings)
   are not shown; showing them would quote a team's heading.
   Recommendation: (a).

4. The cut-off. (a) t11's top 3 distinct planks per CP, then "and N more
   planks, read by M teams": advantage-cp shows 6 of 114 team-plank pairs.
   (b) The top 3 per advantage solved within each CP, "not named" as one
   group: advantage-cp shows up to 27 planks (8 advantages and "not named").
   Recommendation: (b), since that is what the coach asked to see per plank;
   (a) if "top 3 per plank" meant per CP.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

# Session report: v1-e32-t51-late-disclosures-from-pre-topic-tournaments-counted

| | |
|---|---|
| Task | `v1-e32-t51-late-disclosures-from-pre-topic-tournaments-counted` — Late disclosures from tournaments before the de-extinction topic are counted on 2026-11-10 and 2026-11-17, and weekly after |
| Spec | [`plan_specs/v1/e32-argument-landscape/t51-late-disclosures-from-pre-topic-tournaments-counted.yaml`](../../plan_specs/v1/e32-argument-landscape/t51-late-disclosures-from-pre-topic-tournaments-counted.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t51-late-disclosures-from-pre-topic-tournaments-counted` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Built to the PM's rulings of 2026-11-12. ac2 passes; ac1 has its 2026-11-10 count and waits for the
2026-11-17 count, which no session can take before 2026-11-19. The Goal stays `InProgress`.

* **The 2026-11-10 count** (operator run over v1-e39-t18's copy, read-only): 356 of 1,639 hsld26
  disclosures were late (21.7%), and 277 of their 336 files hold only space colonization words against
  2 holding only de-extinction words. Both triggers were met.
* **The rule (Q1, option b):** in a snapshot a newer topic's range covers, a disclosure whose tournament
  spelling was first seen before that range began, that no entry matches and that holds none of the
  newer topic's entry spellings is on the earlier topic. It applies behind
  `late_disclosures_on_earlier_topic` on the range in `topics.yaml`, on for hsld26's de-extinction
  range only. It lives in `debate_core.domain.landscape` (`TopicMap.is_late`,
  `resolve_disclosure`), and seeding passes it the caselist's spelling history, so the report, the
  trends and every seeding script read it. It amends v1-e32-t06's Decision 1 for this rule only
  (Deviation 1, the PM's amendment).
* **The weekly line (Q2):** beside "Part of a week" in report.md, even at 0, and `late_disclosures` in
  `landscape report --json`, both counted by the script's own function, with each topic's
  `check_words` as the check. It names no tournament.
* **No spelling named (Q3):** the script and the line print counts only. The tournament spellings
  from the operator's pasted output are nowhere in this branch's commits, report, tests, fixtures or
  logs. The one commit that held some was rewritten. Two things the PM should know: the operator's
  output reached the session with tournament spellings, which (i) now prevents; and one name from that
  output has been in dev's history since v1-e32-t06's test (#837), in `OTHER_TOURNAMENTS` of
  `tests/config/test_landscape_topic_map.py`. This branch replaces it with an invented name. Details under "The PM's rulings (2026-11-12,
  second)".
* **Evidence:** the PM's five rule tests and the line's tests, shown red against a skeleton that moves
  nothing (9 failed); 17 mutants of the rule and the line all caught; the changed directories and the
  always-run list 3,962 passed. The 385-file affected set is the pull request's `ci` (agreement 10).

The PM should look first at the rule's home and its required `first_seen` argument (Decision 1), the
`label` and `check_words` fields (Deviation 2), the `--json` key in `debate_cli` (Deviation 3), and the
history rewrite (the second rulings' section).

## The count as first built (2026-11-12, before the second rulings)

The first build counted one snapshot's late disclosures with their share and the topic-word check, and
named a late spelling when two schools or more used it and it held no school or team-code word. That is
the build the 2026-11-10 count ran (`b8baeb5`). The second rulings changed it as described below: late
is now the domain's own test, the check words come from `topics.yaml`, and no spelling is named. Its
tests were shown red against a count-nothing skeleton (16 of 17 failed) and 19 mutants were caught. Two
of those mutants were on the naming rule and one on a validation guard; all three pieces of code are
gone now.

## The PM's rulings (2026-11-12, first)

> 1. Accepted: the block runs from the t51 worktree's .venv. Add a guard that stops, naming the path,
>    if that .venv or its python is missing; never fall back to another interpreter.
> 2. Accepted: a late spelling is named only when 2 or more schools use it and it holds no school or
>    team-code word (as v1-e32-t06's Deviation 3); otherwise it is counted, not named.
>
> The copy: v1-e39-t18 has finished measuring. v1-e31-t32's and v1-e31-t23's counts run on it first,
> then yours, third. Hand the operator your 2026-11-10 block now; the operator runs it when the PM says.

How the build follows them: the block's guard stops on a missing worktree or `.venv/bin/python`,
naming the path, and calls that python by its full path, so no other interpreter can run it. Tried in
zsh: a `.venv/bin/python` symlink to a missing file stops; a missing worktree stops; the real
worktree, run from `/tmp` over a synthetic copy, gives `exit 0`. The naming rule was built as ruled,
and the second rulings' Q3 removed it.

## The 2026-11-10 count (2026-11-12)

The operator ran the block from this worktree at `b8baeb5`, over v1-e39-t18's copy, after the PM
released it. Every guard passed: the restore marker was there, the newest hsld26 manifest was
`2026-11-10.jsonl`, and the parsed version was `2026.11.03-docx-9`. The result was `exit 0` and
`copy unchanged`, in 6.6 s. The topic was `ld-2026-nov-dec-de-extinction` from its range, which starts
2026-11-06; `first_seen_through` was 2026-11-03, and the entry spellings were `bluekey` and `fbk`.

| | Count |
|---|---|
| Live hsld26 disclosures in the snapshot (sources) | 1,639 (1,512) |
| Off the topic, naming no tournament | 0, 0 |
| Under Florida Blue Key's spellings | 34 |
| **Late** (sources, schools, spellings) | **356** (336, 51, 56) |
| **Late share** | **21.7%** (356 of 1,639) |
| Late by first-seen snapshot: 2026-11-03 / 2026-10-27 / 2026-10-20 / earlier | 37 / 28 / 103 / 188 |

The topic-word check, by source (de-extinction words: `de-extinct`; space colonization words:
`space col`, `coloniz`; in tags and headings):

| Group | De-extinction only | Both | Space only | Neither | Not parsed |
|---|---|---|---|---|---|
| Late (336 sources) | 2 | 0 | 277 | 54 | 3 |
| Florida Blue Key's spellings (33) | 24 | 1 | 2 | 6 | 0 |
| Other (1,146) | 955 | 49 | 12 | 106 | 24 |

Three sources are disclosed in two groups, so the groups hold 1,515 between them.

**Late spellings.** 22 were named (two or more schools, no hsld26 school or team-code word): 182
disclosures. 21 one-school spellings (50 disclosures) and 13 spellings holding a school or team-code
word (124) were counted, not named, as ruled. Of the 22 named, the session judges 8 (44 disclosures)
to be a school's own name: a host school that does not disclose on hsld26 under that name, so the
withholding words cannot catch it. They are left out of this report, as v1-e32-t06 left four out (its
Deviation 3). The output the operator pasted names them. That is the ruled naming rule's gap, and
Q3 below asks about it. The other 14 named spellings are tournament names with no school in them.
Two of these are named for the host university, and three for a person who is not a debater.

### The judgement

* **The 5% trigger is met:** 21.7% of the snapshot's disclosures are late, about four times the
  threshold. 319 of the 356 were first seen two weeks or more before the topic began, so they are
  not tournaments that straddled the cut.
* **The check says space colonization files land in de-extinction counts.** Of the late sources, 277
  of 336 hold only space colonization words and 2 hold only de-extinction words. Of the 279 that hold
  either topic's words, 277 (99%) are space colonization. Today the landscape report counts all 356
  as de-extinction rounds. Their headings mostly match no de-extinction position, so they swell its
  rounds, teams and unclassified share.
* **Late counts few de-extinction files.** 2 of 336 late sources hold de-extinction words. Among the
  rest of the week, 955 of 1,146 sources hold only de-extinction words and 12 only space words. So
  spellings first seen before the topic began separate the two topics far better than a space
  colonization entry list can, because most late disclosures cannot be listed (below).

## The proposal (2026-11-12, for the PM's ruling)

Kept as sent, with one change: the tournament names and spellings it listed are left out, under the
PM's Q3 ruling (below).

> Q1. The remedy. Options:
>   (a) Space colonization tournament entries in topics.yaml, as v1-e32-t06's Decision 1 keeps it: one
>       per tournament on ld-2026-sep-oct-space-colonization, caselist hsld26, from 2026-11-10 to
>       2026-12-31 (an older topic's entry may reach forward into a newer range; the loader allows it).
>       Only spellings two or more schools use, holding no school's name or a hsld26 school or
>       team-code word, and whose late files hold no de-extinction words. Eight tournaments, by
>       spelling, with 44, 29, 27, 13, 7, 5, 4 and 1 late disclosures. [Their names and spellings are
>       left out here under the PM's Q3 ruling of 2026-11-12.]
>       They reach 130 of the 356 (36.5%). The late share
>       falls to at most 13.8% (226 of 1,639), still above 5%. The other 226 cannot be configured
>       under t51's forbidden list: 124 are under spellings holding a hsld26 school's word
>       (tournaments named for a disclosing school), 44 under spellings that are a school's name, 50
>       under one-school spellings, 7 under one tournament whose late files hold some de-extinction
>       words (2 of its 6 sources), and 1 under a spelling too short
>       to match safely by "holds".
>   (b) A rule from spelling history, named in configuration. In a snapshot a newer topic's range
>       covers, a disclosure whose spelling was first seen before that range began, and holds none of
>       the newer topic's own entry spellings, is on the earlier topic. It is switched on by a key on
>       the range in topics.yaml, so only hsld26's de-extinction range uses it. No snapshot before
>       2026-11-10 moves, and no tournament or school is named. On 2026-11-10 it moves all 356. Of
>       their 336 sources, 2 hold only de-extinction words: that is the error the check measures.
>       Risk: a November tournament sharing an earlier spelling moves off de-extinction. The weekly
>       line counts what the rule moved, with the topic-word check, so that risk is seen every week.
>       This is a code change in debate_core.domain.landscape (t51's packages include it), so it is a
>       scope change, and it goes against Decision 1 keeping the remedy in configuration.
>   (c) Neither: keep counting, and the weekly line reports it.
>   Recommended: (b). (a) reaches barely a third of the late disclosures, and lists tournament names
>   week by week. (b) reaches every one the count found, names nothing, and is the measure the PM
>   already ruled the count by. It is not a topic-word rule: the words only check it.
>
> Q2. The weekly report line (so later weeks need no session):
>   Where: report.md's header notes, beside the "Part of a week" notice, and one additive key in
>   `landscape report --json`, `late_disclosures`, written only when it applies. It applies when the
>   snapshot is on its topic by a range and the caselist has an earlier topic's range, so on hsld26
>   from 2026-11-10 and on no Policy report.
>   What it counts: as the script does, from the same function. The check words come from topics.yaml,
>   one `check_words` list per topic (de-extinction: [de-extinct]; space colonization: [space col,
>   coloniz]). They are a check that decides nothing. Without words the line gives the count and share
>   alone.
>   Its words under (b): "Earlier topic: 356 of 1,639 disclosures this week (21.7%) name a tournament
>     first disclosed before this topic began on 2026-11-06, and are counted on Space colonization, not
>     here. Of their 336 files, 2 hold only this topic's words in tags and headings, and 277 only the
>     earlier topic's."
>   Its words under (a) or (c): "Late disclosures: 356 of 1,639 disclosures this week (21.7%) name a
>     tournament first disclosed before this topic began on 2026-11-06, and are counted here. Of their
>     336 files, 277 hold only the earlier topic's words in tags and headings, and 2 only this
>     topic's."
>   The line names no tournament; spellings stay in the script's output for the operator.
>   Recommended: as above, with the line shown even when the count is 0, so it is visibly checked.
>
> Q3. The naming rule's gap: 8 of the 22 spellings the script named are a school's own name (host
>   schools that do not disclose on hsld26 under that name, so the withholding words miss them). They
>   are in the output the operator pasted into the session, and left out of the report. Options:
>   (i) the script names no spelling at all, counts only; (ii) keep naming for the operator, and the
>   session screens before anything is written. Recommended: (i) for the 2026-11-17 count, since (b)
>   needs no names. Under (a), (ii).
>
> Q4. The 2026-11-17 count: the run of 2026-11-18 is a Wednesday, so its restore goes on 2026-11-19 or
>   later. It is my own guarded restore, read-only count, deleted after use (policy 1.18), unless
>   another task's copy of that week is available. Under (b) it runs with the ruled topics.yaml, so it
>   shows what the rule moves and what is left.

## The PM's rulings (2026-11-12, second)

> Q1. (b), the rule from spelling history, behind its key on the range in topics.yaml: in a snapshot a
> newer topic's range covers, a disclosure whose tournament spelling was first seen before that range
> began, and holds none of the newer topic's entry spellings, is counted on the earlier topic. This
> amends v1-e32-t06's Decision 1 (topic placement by configuration alone) for this rule only; record it
> under Deviations as the PM's amendment, and the PM's next batch writes it into the spec. Tests on
> synthetic stores shown failing first: the 2026-11-10 shape (late spellings move, an entry spelling
> stays), no snapshot before the range moves, a newer-topic entry always wins over the rule, the key off
> changes nothing, and Policy (no earlier topic in range) never moves. Not (a): it reaches about a third
> and lists names week by week. Not (c): the reports would keep counting about a fifth of the snapshot
> on the wrong topic.
>
> Q2. The weekly report line as proposed, with (b)'s wording: report.md's header notes beside "Part of
> a week", and the additive --json key late_disclosures, shown even at 0, counted by the same function
> as the script, with the check words from topics.yaml's per-topic check_words (a check only, deciding
> nothing). It names no tournament.
>
> Q3. (i). The script names no spelling at all: counts only, with "named" removed from its output. The
> eight host-school spellings and every other spelling from the operator's pasted output appear
> nowhere: not in a commit, the report, a test, a fixture or a log. If any such name is already in this
> branch, remove it from the commit history before the report and say so. Note in the report that the
> operator's output reached the session with tournament spellings, and that (i) prevents it.
>
> Q4. Accepted: the 2026-11-17 count on 2026-11-19 or later, never on a Wednesday. The restore is hsld26
> only (restore-run-state --caselist hsld26), read-only, deleted after use (policy 1.18), the Mac on
> mains power with its lid open. If v1-e39-t18's fresh restore for its ac2 is made on or after
> 2026-11-19, read that copy instead, and say so. It runs with the ruled topics.yaml from a build
> carrying this branch.
>
> Operator follow-up to write, not run: after the merge and the next dev deploy, republish the hsld26
> landscape report so the pilot's landscape pages count the late disclosures on their earlier topic,
> never on a Wednesday, and record the de-extinction counts before and after.
>
> Then build, by tests shown failing first, and stop at the session report. Do not open a pull request.

### How the build follows them

* **Q1.** `CaselistRange.late_disclosures_on_earlier_topic` (default off). `TopicMap.earlier_topic` is
  the topic of the caselist's latest range ending before the covering range begins. `TopicMap.late_cut`
  gives the covering range, its topic and that earlier topic, or None. `TopicMap.is_late` is the
  ruling's test, the key aside. `TopicMap.resolve_disclosure` now takes the spelling history
  (`first_seen`, from `first_seen_spellings`) and, after the entries and before the range, puts a late
  disclosure on the earlier topic when the covering range's key is on. The loader refuses the key on a
  range with no earlier topic of its caselist. `read_seed_sources` builds the history from the
  caselist's live disclosures. `topics.yaml` sets the key on hsld26's de-extinction range. The PM's five
  tests are in `test_landscape_late_disclosure_rule.py`, with the real file's in
  `tests/config/test_landscape_topic_map.py`.
* **Q2.** `LateDisclosures` (domain) carries the counts to `ReportHeader.late_disclosures`. The run
  counts the week with `count_late_disclosures`, the script's function, whenever the snapshot's range has
  an earlier topic. `render.py` writes the line after "Part of a week", in the ruled (b) wording when the
  key is on and the (a)/(c) wording when it is off. The line's check sentence uses each topic's
  `check_words` and is left out when a topic has none or no file is late. `landscape report --json` adds
  `late_disclosures` only when the line applies.
* **Q3.** The script prints counts only: `late_spellings_named` and `late_spellings_not_named` are gone,
  and with them the withholding words and the school-name check. The commit that held the proposal's
  eight names and spellings (`4afe41a`, the report's proposal) was amended into `20eddeb` before any later
  commit. `git log -p 3cfd4af..HEAD`, searched for every name and spelling from the operator's output,
  finds none. Three things are left for the PM:
  * The replaced commit was never pushed. Its object stays in the local object store, which every
    worktree shares, until git's own expiry. I tried to expire the reflog and prune; the session's
    permission check refused it, rightly, because it reaches every worktree's history. I did not try
    again. Whether to prune is the operator's call.
  * One tournament name from that output has been in `OTHER_TOURNAMENTS` of
    `tests/config/test_landscape_topic_map.py` on dev since v1-e32-t06 (#837). This branch replaces it
    with "Ridgeline Cup", an invented name. Dev's history keeps it, and so does this branch's commit
    that removes it: a diff that deletes a line shows the line. Rewriting dev is not a session's to do.
  * **The operator's output reached the session with tournament spellings.** The first build named
    late spellings two schools or more used, and the 2026-11-10 output the operator pasted held 22.
    Eight were a host school's own name, which the withholding words cannot catch. They are in this
    session's conversation, not in the repository. With (i) the script prints no spelling, so a pasted
    output can carry none.
* **Q4.** The blocks are under Operator follow-ups: hsld26 only, no raw sources, guards for a Wednesday,
  mains power and a closed lid, read-only with a fingerprint before and after, deleted after use. A copy
  of v1-e39-t18's restored on or after 2026-11-19 may be read instead.
* **Republish.** Written under Operator follow-ups, not run. The "before" counts come from a dry run of
  the same week with the key taken out of a scratch copy of the configuration, so before and after
  differ only by the rule.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| late-disclosures-from-pre-topic-tourname | Done but for ac1's second count | The count (2026-11-10), the rule, the weekly line and the blocks are built; the 2026-11-17 count is an operator run on 2026-11-19 or later |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the counts on 2026-11-10 and 2026-11-17 recorded with their share and the topic-word check, entries proposed if the 5% trigger or the check says so | NOT RUN (2026-11-10 done) | 2026-11-10 recorded: 356 of 1,639 late (21.7%), late files 277 space-only and 2 de-extinction-only of 336; both triggers met; remedy proposed and ruled (option b). **2026-11-17: NOT RUN**: the snapshot is recorded by the run of 2026-11-18, and the PM's Q4 puts its count on 2026-11-19 or later (Operator follow-ups 2). The copies: v1-e39-t18's for 2026-11-10 (deleted by that task, policy 1.18); this task's for 2026-11-17, deleted by its last block. |
| ac2: the weekly report line, as ruled, by tests on synthetic stores shown failing first | PASS | Red against a skeleton that moves nothing, refuses no key, renders no line and writes no key: **9 failed, 35 passed** (the passes assert that nothing moves; mutants prove them). Green: the line's run tests, `--json` tests and the rule's tests pass (below); 17 mutants caught. |
| Node: `uv run pytest packages/debate_core/tests -k late_disclosure` | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k late_disclosure -q` → **32 passed in 21.5 s** (the count's 17, the rule's 11, three run tests, and one of v1-e32-t06's) |

### Tests, red run and mutants

* **New and changed tests.**
  * `packages/debate_core/tests/domain/test_landscape_late_disclosure_rule.py` (11): the PM's five, plus
    the earlier topic, the key's refusal, no history, first-seen spellings, check words and the report
    value's checks.
  * `tests/config/test_landscape_topic_map.py` (+5, over the committed file): only hsld26's de-extinction
    range carries the key; the check words; every snapshot before 2026-11-10 of all three caselists
    resolves the same with a history as without; a late hsld26 disclosure goes to space colonization
    while Florida Blue Key's stays; Policy never moves.
  * `test_landscape_late_disclosures.py` (17): the count's, now with the key and the config's words, and
    seeding with the key on.
  * `test_landscape_run.py` (+4): the line with the key on, the key off, at zero without check words,
    and none for Policy.
  * `packages/debate_cli/tests/test_landscape_command.py` (+2): `late_disclosures` at zero, and no key
    without an earlier topic.
  * `tests/scripts/test_count_late_disclosures.py` (5): no spelling in the output, the config's words,
    and one word option alone refused.
  * Every expected value was written by hand from what the test plants. The `first_seen={}` argument
    was added to v1-e32-t06's calls in `test_landscape_tournament_entries.py` and the config test (no
    history: nothing is late, so each assertion keeps its meaning).
* **Red run** (after `6fa5b0c`): a skeleton that disables the rule's branch, the key's refusal, the
  line, the run's count and the JSON key. The new tests gave **9 failed, 35 passed**. The 9 are the
  2026-11-10 shape, the newer-topic entry, the key's refusal, the real file's late disclosure, seeding
  under the key, the three line tests and the JSON key. The passes assert that nothing moves (before the
  range, key off, Policy, no history), which a skeleton that moves nothing satisfies. The mutants below
  are what show those tests fail when the rule over-reaches. Two cases were added to the rule test so
  that they would: a summer spelling read at a snapshot under an older range with no key, and a Policy
  range that starts after an LD range ends.
* **Mutants**, 17, each run against the six test files with no bytecode written and the file restored
  from `HEAD` after. All caught:

  | Mutant | Result |
  |---|---|
  | The rule ignores the range's key | 3 failed |
  | Late against the snapshot, not the range's start | 1 failed |
  | The topic's entry spellings not excluded | 4 failed |
  | A matching entry does not stop the rule | 1 failed |
  | The earliest earlier range, not the latest | 3 failed |
  | An earlier topic from any caselist | 2 failed |
  | A key on any range of the map moves | 1 failed (the summer spelling) |
  | No refusal of a key with no earlier topic | 1 failed |
  | First seen keeps the latest snapshot | 14 failed |
  | Seeding passes no history | 2 failed |
  | The count misses moved disclosures | 5 failed |
  | The report's value swaps the check's counts | 3 failed |
  | The line left out at zero | 1 failed |
  | The line's two wordings swapped | 3 failed |
  | The line without its check sentence | 2 failed |
  | The run gives the report no count | 4 failed |
  | The JSON key left out at zero | 1 failed (the test's lookup of the key: `KeyError`) |

  The last one's failure is a `KeyError` in the test reading the key the mutant removed. That is the
  missing key itself, not code crashing before the check.
* **Checks before this report.**
  * The affected set: `uv run scripts/affected_tests.py` chose **385 test files**, more than half the
    suite and well past two minutes. Under agreement 10 it is left to the pull request's `ci` check.
    Run instead, within the limit: the always-run list (`tests/architecture`, `tests/specs`, the CLI's
    `test_app.py`, `test_container_factories.py`, `test_help_rendering.py`, `test_installation.py`)
    and the directories and files of what changed: `packages/debate_core/tests/domain`,
    `.../arguments/landscape`, every `test_landscape_*.py` in `.../application`,
    `test_aff_assignment.py`, `tests/config`, the CLI's `test_landscape_command.py`,
    `tests/smoke/test_landscape_smoke.py`, the six landscape scripts' tests and `tests/docs` →
    **3,962 passed in 52.0 s**.
  * `ruff format --check .` → 2,098 files already formatted; `ruff check .` → all passed.
  * `pyright packages/debate_core packages/debate_cli`, the script and its test, `tests/config` → 0
    errors.
  * `lint-imports` → 20 kept, 0 broken; `scripts/check_thin_handlers.py` → 74 handlers within 25.
  * `docs_index.py --check-descriptions`, `check_links.py` and `check_command_blocks.py --base
    origin/dev` → OK; `scripts/validate_specs.py` → OK.

## Files changed

* **`debate_core.domain.landscape`**: the range's key, `Topic.label` and `Topic.check_words`,
  `TopicMap.earlier_topic`, `late_cut`, `is_late`, the rule in `resolve_disclosure` (now with
  `first_seen`), the key's refusal, `LateCut`, `LateDisclosures` and `first_seen_spellings`.
* **`debate_core.domain.landscape_report`**: `ReportHeader.late_disclosures`.
* **`debate_core.application.landscape_late_disclosures`** (new): the count, from the domain's test, for
  the script and the report.
* **`debate_core.application.landscape_seeding`**: the spelling history passed to the rule.
* **`debate_core.application.landscape_report`**, **`landscape_run`**: the count carried to the header.
* **`debate_core.arguments.landscape.render`**: the line.
* **`debate_cli.commands.landscape`**: the `late_disclosures` key (Deviation 3).
* **`config/landscape/topics.yaml`**: the key on hsld26's de-extinction range, both LD topics' labels and
  check words, and a comment.
* **`scripts/count_late_disclosures.py`** (new): the count as JSON, counts only.
* **`docs/guides/landscape-taxonomy.md`**: late disclosures, `check_words`, `label` and the line.
* **Tests**: as listed above.

## Deviations from the spec

1. **The PM's amendment of v1-e32-t06's Decision 1** (the PM's Q1 ruling of 2026-11-12). A disclosure's
   topic is no longer placed by configuration alone: a late disclosure goes to the earlier topic by the
   caselist's spelling history, behind a key in configuration, for this rule only. The PM's next batch
   writes it into the spec.
2. **`label` and `check_words` on a topic in `topics.yaml`.** The ruling names `check_words`. `label` is
   added so the ruled wording reads "counted on Space colonization" rather than the topic's id. A topic
   without one shows its id.
3. **One additive `--json` key in `debate_cli`** (`late_disclosures`), and two tests in
   `packages/debate_cli/tests`. Neither package is in `constraints.packages`, but Q2 rules the key.
4. **The 2026-11-10 block ran from this worktree's `.venv`**, not the main clone's (accepted, the PM's
   ruling 1 of 2026-11-12). The main clone's `.venv` imports dev's `debate_core`, which lacked the
   module. The 2026-11-17 block does the same, with the same guard.
5. **Tests outside `constraints.packages`:** `tests/scripts/test_count_late_disclosures.py` (the scripts'
   tests live in `tests/scripts`). Also v1-e32-t06's `test_landscape_tournament_entries.py`, given the new
   required argument, and `tests/config/test_landscape_topic_map.py`, which is in the list.
6. **No smoke check added.** The report line and the JSON key are a user-facing change (agreement 5), but
   `tests/smoke` is outside the packages and the spec has no smoke node. The landscape smoke file passes
   unchanged: its synthetic caselist has no earlier topic, so it shows no line. Follow-up work.

## Decisions and assumptions

1. **`first_seen` is a required keyword of `resolve_disclosure`.** A caller that forgot the history would
   otherwise apply no rule without saying so. Every caller passes one: seeding the caselist's history,
   the count its own, and the earlier tests `{}`.
2. **`is_late` does not read the key**, so the count and the line work with the key off: then the line
   says the disclosures "are counted here". `resolve_disclosure` reads the key.
3. **The earlier topic is the caselist's latest range ending before the covering range begins**, not any
   earlier range: hsld26's space colonization, not a summer topic, if one were ever listed.
4. **The report counts the week the run reads** (the run's weekly snapshot), with the parsed version the
   report reads, so the line and the report agree on their week. It reads that week's documents again for
   the check; the script took 6.6 s over hsld26's 2026-11-10 week.
5. **The JSON key is written only when the line applies** (the snapshot's range has an earlier topic), and
   then even at 0. A Policy report's JSON has no such key, as the proposal said.
6. **The line's check sentence is left out** when a topic has no `check_words` or no file is late, rather
   than printing "Of their 0 files".
7. **Unchanged from the first build:** the cut is the covering range's first day; first seen among live
   disclosures only; the share is of all the snapshot's live disclosures.

## Operator follow-ups

1. **The 2026-11-10 count**: run 2026-11-12 from `b8baeb5` (`exit 0`, `copy unchanged`, 6.6 s; results
   above). That build named spellings; the build of this branch's tip names none.
2. **The 2026-11-17 count (ac1). Not before 2026-11-19, never on a Wednesday**, from this worktree, which
   carries the ruled `topics.yaml`. If this branch has merged and the worktree is gone, the count block's
   guard stops; then set `WT` to the main clone pulled to dev, which carries it. Four blocks, in one
   terminal window.

   **First, the checks.** Every line prints something to read.

   **Operator command** (expected runtime a few seconds)
   Where: your Mac, in a new terminal window
   ```bash
   COPY="$HOME/.debate-research/landscape-copy-hsld26"
   WT=/Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t51-late-disclosures-from-pre-topic-tournaments-counted
   date +%A
   pmset -g batt | head -1
   ioreg -r -k AppleClamshellState -d 4 | grep AppleClamshellState
   debate-research --json --version | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"]["tag"])'
   ls "${WT}/.venv/bin/python"
   df -g "$HOME" | awk 'NR == 2 { print $4 " GB free" }'
   ```
   Success looks like a day that is not Wednesday, `Now drawing from 'AC Power'`,
   `"AppleClamshellState" = No` (the lid open), a dev release tag, the python's path, and 5 GB free or
   more.

   **If v1-e39-t18 has restored a copy on or after 2026-11-19** for its ac2, read that copy instead: set
   `COPY` to its directory, skip the restore and the delete, and run only the count block, whose guards
   check the copy's restore date and its 2026-11-17 manifest. Say so when pasting the output.

   **The restore** (runbook step 1, hsld26 only, without `--with-sources`: the count reads manifests, the
   suppression list and the parsed store, never a raw source). It refuses a Wednesday, battery power, a
   closed lid, a `DEBATE_` override, a running pull and a copy that exists already.

   **Operator command** (expected runtime ~2 to 10 min: hsld26's manifests and its parsed store, about
   7,000 objects on 2026-11-05)
   Where: your Mac, in the same window
   ```bash
   if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif ! pmset -g batt | head -1 | grep -q "AC Power"; then echo "STOP: the Mac is not on mains power"; elif ioreg -r -k AppleClamshellState -d 4 | grep -q '"AppleClamshellState" = Yes'; then echo "STOP: the lid is closed"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif [ -e "$COPY" ]; then echo "STOP: ${COPY} exists already"; else aws sso login --profile debate-dev-evidence && cd "$HOME" && caffeinate -i env DEBATE_ENV=dev debate-research --json caselist restore-run-state --into "$COPY" --caselist hsld26 > /tmp/t51-restore.json; echo "exit $?"; grep -oE '"(manifests|parsed_version|parsed_objects|suppressed)": ("[^"]*"|[0-9]+)|"code": "[A-Z_]+"' /tmp/t51-restore.json; fi
   ```
   Success looks like `exit 0`, `"parsed_version"` the build's (`2026.11.03-docx-9` or later), and
   `"parsed_objects"` above zero. `RUN_LOCK_HELD`: a cloud run holds the lock; wait, and run the block
   again. Any other stop: run the delete block, then tell the PM.

   **The count**: read-only, from this worktree's python and nothing else, with the ruled `topics.yaml`
   and its check words. It stops, naming the path, if the worktree or its python is missing; if the copy
   has no restore marker, was restored before 2026-11-19, or holds no hsld26 manifest of 2026-11-17. It
   fingerprints the copy's files before and after.

   **Operator command** (expected runtime under a minute; 6.6 s for 2026-11-10)
   Where: your Mac, in the same window
   ```bash
   WT=/Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t51-late-disclosures-from-pre-topic-tournaments-counted
   PY="${WT}/.venv/bin/python"
   RESTORED=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["restored_at"][:10])' "${COPY}/debate-research-restored-copy.json" 2>/dev/null)
   if [[ ! -d "${WT}" ]]; then
     echo "STOP: no worktree at ${WT}"
   elif [[ ! -x "${PY}" ]]; then
     echo "STOP: no python at ${PY}; this block runs no other interpreter"
   elif [[ ! -f "${COPY}/debate-research-restored-copy.json" ]]; then
     echo "STOP: ${COPY} is not a restored copy"
   elif [[ "${RESTORED}" < "2026-11-19" ]]; then
     echo "STOP: the copy was restored on ${RESTORED:-an unknown day}, before 2026-11-19"
   elif [[ ! -f "${COPY}/objects/manifests/hsld26/2026-11-17.jsonl" ]]; then
     echo "STOP: the copy holds no hsld26 manifest of 2026-11-17"
   else
     cd "${WT}"
     BEFORE=$(find "${COPY}" -type f -print0 | xargs -0 stat -f '%N %z %m' | LC_ALL=C sort | shasum -a 256)
     git -C "${WT}" log -1 --format='commit %h'
     "${PY}" "${WT}/scripts/count_late_disclosures.py" --data-dir "${COPY}" --caselist hsld26 --snapshot 2026-11-17 --config-dir "${WT}/config/landscape"
     echo "exit $?"
     AFTER=$(find "${COPY}" -type f -print0 | xargs -0 stat -f '%N %z %m' | LC_ALL=C sort | shasum -a 256)
     if [[ "${BEFORE}" == "${AFTER}" ]]; then echo "copy unchanged"; else echo "STOP: the copy changed"; fi
   fi
   ```
   Success looks like a `commit` line, the JSON, `exit 0` and `copy unchanged`. In the JSON:
   `"snapshot": "2026-11-17"`, `"topic": "ld-2026-nov-dec-de-extinction"`, `"moved_to":
   "ld-2026-sep-oct-space-colonization"`, `"first_seen_through": "2026-11-03"`, `"disclosures"` above
   zero, and a `"topic_word_check"` that is not `null`. Paste the whole output back: it holds counts,
   dates and public configuration, and no tournament. A `STOP` or `Refused:` line: paste it and stop.

   **Delete the copy** (runbook step 5), after the count or after any stop. Not when `COPY` names
   v1-e39-t18's copy: that one is its own to delete.

   **Operator command** (expected runtime about a minute)
   Where: your Mac, in the window that set `COPY`
   ```bash
   case "$COPY" in "$HOME/.debate-research/landscape-copy-"*) rm -rf "$COPY" && echo "removed ${COPY}" ;; *) echo "STOP: ${COPY} is not a landscape copy" ;; esac
   rm -f /tmp/t51-restore.json
   find -H "$HOME" /tmp \( -path "$HOME/Library" -o -path "$HOME/.Trash" \) -prune -o -type f -name debate-research-restored-copy.json -print 2>/dev/null | sed 's|/debate-research-restored-copy.json$||' | grep -vxF -e "$HOME/.debate-research/dev" -e "$HOME/.debate-research/prod" | awk '{ print } END { print "restored copies: " NR }'
   find -H "$HOME" /tmp -maxdepth 3 \( -path "$HOME/Library" -o -path "$HOME/.Trash" \) -prune -o -name debate.sqlite3 -print 2>/dev/null | sed 's|/debate.sqlite3$||' | grep -vxF -e "$HOME/.debate-research/dev" -e "$HOME/.debate-research/prod" | while IFS= read -r FOUND; do [ -f "$FOUND/debate-research-restored-copy.json" ] || echo "$FOUND"; done | awk '{ print } END { print "restored before the marker: " NR }'
   ```
   Success looks like `removed …`, and then the counts of copies left on this Mac. A copy listed that is
   another task's is that task's to delete.

3. **Republish the hsld26 landscape report: written, not run. After this branch merges and the next dev
   deploy, never on a Wednesday.** It is
   [the runbook](../runbooks/landscape-report-from-the-cloud-run.md) with `CASELIST=hsld26`, a build
   carrying this branch, and `CFG` the main clone's `config/landscape` pulled to dev. There is one extra
   dry run, for the "before" counts.
   1. The runbook's "Before you start" and steps 1 and 2.
   2. A scratch copy of the configuration without the key: the "before" a pilot page showed, with the
      late disclosures counted on de-extinction.

      **Operator command** (expected runtime a second)
      Where: your Mac, in the runbook's window
      ```bash
      CFG_BEFORE="$(mktemp -d /tmp/t51-config-before.XXXXXX)"
      cp -R "$CFG/" "$CFG_BEFORE/"
      sed -i '' '/late_disclosures_on_earlier_topic: true/d' "$CFG_BEFORE/topics.yaml"
      grep -c 'late_disclosures_on_earlier_topic: true' "$CFG/topics.yaml" "$CFG_BEFORE/topics.yaml"
      ```
      Success looks like `1` for `$CFG` and `0` for `$CFG_BEFORE`.
   3. The "before" dry run. It neither publishes nor asks a bucket, and writes only the text caches,
      as step 3 does.

      **Operator command** (expected runtime as the runbook's step 3)
      Where: the same window
      ```bash
      if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif [ ! -d "$COPY" ]; then echo "STOP: no copy at ${COPY}"; elif [ ! -f "$CFG_BEFORE/topics.yaml" ]; then echo "STOP: no topics.yaml in ${CFG_BEFORE}"; else cd "$HOME" && caffeinate -i env DEBATE_ENV=dev debate-research --json landscape report --caselist hsld26 --restored-copy "$COPY" --config-dir "$CFG_BEFORE" --model-mode none --dry-run > /tmp/t51-dry-run-before.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); d = e.get("data") or {}; c = d.get("counts") or {}; print("code", (e.get("error") or {}).get("code"), "snapshot", d.get("snapshot")); print("sources", c.get("sources"), "cards", c.get("cards"), "counted", c.get("cards_counted"), "positions", c.get("positions"), "rounds", c.get("rounds"), "teams", c.get("teams"), "aff_rounds_unidentified", c.get("aff_rounds_unidentified"), "neg_rounds_unplaced", c.get("neg_rounds_unplaced")); print("late_disclosures", d.get("late_disclosures"))' /tmp/t51-dry-run-before.json; fi
      ```
      Success looks like `exit 0`, the newest week's `snapshot`, counts above zero, and
      `late_disclosures` with `"moved": false`.
   4. The runbook's step 3 with `$CFG`: the "after" dry run, with its scan and page checks. Then the same
      counts from its file:

      **Operator command** (expected runtime a second)
      Where: the same window
      ```bash
      python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); d = e.get("data") or {}; c = d.get("counts") or {}; print("code", (e.get("error") or {}).get("code"), "snapshot", d.get("snapshot")); print("sources", c.get("sources"), "cards", c.get("cards"), "counted", c.get("cards_counted"), "positions", c.get("positions"), "rounds", c.get("rounds"), "teams", c.get("teams"), "aff_rounds_unidentified", c.get("aff_rounds_unidentified"), "neg_rounds_unplaced", c.get("neg_rounds_unplaced")); print("late_disclosures", d.get("late_disclosures"))' /tmp/landscape-dry-run.json
      ```
      Success looks like the same `snapshot`, `late_disclosures` with `"moved": true` and the same
      `late`, and `sources`, `rounds` and `teams` lower than before by about the late disclosures'
      share. **Send the PM both prints** (counts only), with the runbook's step 3 lines.
   5. After the PM has read them: the runbook's step 4 (publish) and step 5 (delete the copy), then
      `rm -rf "$CFG_BEFORE" /tmp/t51-dry-run-before.json`. The de-extinction counts before and after go
      into the PM's record of the week.

## Follow-up work

* **A smoke check for the late-disclosure line** (agreement 5): a synthetic caselist with an earlier
  topic and the key, asserting the line and the `--json` key. `tests/smoke` is outside this task's
  packages (Deviation 6). For E32.
* **The landscape runbook's step 3 could print `late_disclosures`** beside its counts, so each week's
  publish records the line's numbers without the extra block. For E40, which owns the runbook.
* **The shared object store** still holds the replaced commit `4afe41a` until git's own expiry (the
  second rulings' section). The operator decides whether to expire and prune.
* **One tournament name from the operator's output in dev's history** since v1-e32-t06 (#837), in the
  config test's `OTHER_TOURNAMENTS`: this branch removes it from the tree, not from history. For the PM.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-12

**Notes:**

Accepted for a partial merge (`scripts/task pr --partial`; `scripts/task sync` first if asked). ac2
passes. ac1 has its 2026-11-10 count and waits for the 2026-11-17 count, on 2026-11-19 or later.

* **The finding is the task's value.** 21.7% of hsld26's 2026-11-10 disclosures were late, and 99% of
  the late files that hold either topic's words are space colonization. So the de-extinction report has
  been counting about a fifth of the week on the wrong topic. The rule moves all 356, and the check
  measures its error at 2 of 336.
* **The rulings are built as given.**
  * The rule sits behind its key, on hsld26's de-extinction range only.
  * A newer-topic entry always wins.
  * No snapshot before the range moves, Policy never moves, and a key with no earlier topic is refused
    at load.
  * The weekly line and the `--json` key show even at 0 and name no tournament.
  * The script names no spelling.
* **Decision 1 is a good choice:** a required `first_seen` means a caller cannot silently skip the
  rule.
* **The evidence is enough.** The red run on a move-nothing skeleton had 9 failures; the 35 that passed
  are the "nothing moves" guards, and the 17 mutants prove them. The 2026-11-10 count ran read-only
  with the copy fingerprinted unchanged.
* **Q3, handled correctly.** The spellings are gone from this branch's history: the one commit that held
  them was amended before any later commit and never pushed. The orphaned object stays in the local
  store until git's normal expiry. That is the operator's to prune if he wishes, never a session's, and
  it is not required. The one tournament name in dev's history since #837 is removed from the tree by
  this branch, and dev's history is not rewritten for it.
* **Deviations 1 to 6: accepted.** The PM's next batch writes Decision 1's amendment into the spec and
  adds `debate_cli`, `packages/debate_cli/tests` and `tests/scripts` to the packages. The smoke check
  becomes a follow-up.
* **The operator blocks are accepted as written.**
  * The 2026-11-17 count runs on 2026-11-19 or later: hsld26 only, read-only, the lid checked open by
    `ioreg`, deleted after.
  * The republish runs after the merge and the next dev deploy, never on a Wednesday. Its before and
    after dry runs differ only by the key, and the PM reads both prints before the publish.
* **The affected set** (385 files) goes to `ci` under agreement 10.
* **Follow-ups, into the next PM batch:** the landscape smoke check (E32, p3); step 3 of the landscape
  runbook printing `late_disclosures` (a PM doc edit).

`scripts/task pr --partial`

# Session report: v1-e32-t51-late-disclosures-from-pre-topic-tournaments-counted

| | |
|---|---|
| Task | `v1-e32-t51-late-disclosures-from-pre-topic-tournaments-counted` — Late disclosures from tournaments before the de-extinction topic are counted on 2026-11-10 and 2026-11-17, and weekly after |
| Spec | [`plan_specs/v1/e32-argument-landscape/t51-late-disclosures-from-pre-topic-tournaments-counted.yaml`](../../plan_specs/v1/e32-argument-landscape/t51-late-disclosures-from-pre-topic-tournaments-counted.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t51-late-disclosures-from-pre-topic-tournaments-counted` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Stopped at step 3 of the PM's order of work (2026-11-12), waiting for the PM's ruling.** The 2026-11-10 count is in: 356 of 1,639 hsld26 disclosures are late (21.7%), and 277 of their 336 sources hold only space colonization words. Both triggers are met. The proposal (Q1 to Q4) is below.
The counting rule is in `debate_core.application.landscape_late_disclosures`, and
`scripts/count_late_disclosures.py` prints it as one JSON object of counts. Both are tested on
synthetic stores (18 tests), shown red against a skeleton that counts nothing (16 of 17 failed), with
19 mutants caught. The operator block for the 2026-11-10 count over v1-e39-t18's copy is under
Operator follow-ups, with the guard the PM's ruling 1 asked for. Nothing has been run over the copy,
and no session command has touched it.

The PM should look first at the rule as built (below): the cut is the topic range's first day; "FBK
spellings excluded" is read from `topics.yaml`; and spellings are named under a stricter test than
the brief's (Decision 5). Also at Deviation 1: the block runs from this worktree, not from the main
clone, because the main clone's `.venv` imports dev's `debate_core`, which does not have this module.

Still to do after the count: the 5% and topic-word judgement and the weekly report line's proposal
(step 3, for the PM's ruling); then the line itself, red first (ac2), and the 2026-11-17 count's block
for after the run of 2026-11-18 (step 4). The Goal stays `InProgress`.

## The count, as built (2026-11-12)

For one snapshot of one caselist (`--snapshot 2026-11-10 --caselist hsld26`):

* **The snapshot must be on its topic by a range.** `topics.yaml` gives 2026-11-10 to
  `ld-2026-nov-dec-de-extinction` by its range, 2026-11-06 to 2026-12-31. A snapshot that only a
  tournament entry covers (2026-11-03) is refused, and so is a snapshot the store holds no manifest of.
* **Late** means a live disclosure of the snapshot that resolves to that topic and that meets both of
  these:
  * its tournament spelling (`tournament_key`: lower case, letters and digits only) was first seen,
    among the caselist's live disclosures in any snapshot, in a snapshot dated before the range's first
    day, 2026-11-06. With weekly Tuesday snapshots that is "on or before 2026-11-03". The JSON prints
    the newest snapshot before the cut as `first_seen_through`, so the run shows the 2026-11-03 it
    used;
  * its spelling holds none of the topic's own tournament-entry spellings, read from `topics.yaml`
    (`bluekey`, `fbk`). This is "FBK spellings excluded", matched as the entry matches ("holds", Q4).

  A disclosure that names no tournament is never late.
* **The share** is late disclosures over all the snapshot's live disclosures, on any topic or none.
* **The topic-word check** classes each source of the snapshot by what its cards' tags and the
  headings over them hold: the topic's words only, both, the other topic's only, neither, or not parsed
  (no document in the parsed version read). The words are command-line options, never a list in code:
  `--topic-word de-extinct`, `--other-topic-word "space col"` and `--other-topic-word coloniz`, the
  words v1-e32-t06 used. They are matched on letters and digits without case, so `De-Extinction`
  holds `de-extinct`. The class decides nothing. The JSON gives it for three groups that partition
  the snapshot's on-topic disclosures: `late`, `tournament entry spellings` (FBK's) and `other`, by
  disclosure and by source.
* **Spellings.** A late spelling is named, with its first-seen snapshot, its school count, its
  disclosures and sources, and its sources' word classes, only when two schools or more disclosed under
  it (in any snapshot) and it holds no school or team-code word. That word test has two parts: a word
  of the landscape report's withholding words (`caselist_words`) in any tournament text written for
  the spelling, or a school word of four letters or more inside the run-together spelling. Every
  other late spelling is counted, not named, under one of two headings: fewer than two schools, or
  holding a school or team-code word.

It reads the manifests, the suppression list and the parsed store; it opens no database, writes
nothing and calls no model. A disclosure that cannot be read as one refuses the whole count, and the
refusal never quotes the school or team code that pydantic's error text would carry.

## The PM's rulings (2026-11-12)

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
worktree, run from `/tmp` over a synthetic copy, gives `exit 0`. The naming rule is as built (Decision 5).

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

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| late-disclosures-from-pre-topic-tourname | In progress | Steps 1 and 2 of the PM's order done (the count, the held block); 3 and 4 wait on the count and the ruling |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the counts on 2026-11-10 and 2026-11-17 recorded with their share and the topic-word check, entries proposed if the 5% trigger or the check says so | NOT RUN (2026-11-10 done) | 2026-11-10 recorded: 356 of 1,639 late (21.7%); late sources 277 space only and 2 de-extinction only of 336; both triggers met; remedy proposed (The 2026-11-10 count, The proposal). 2026-11-17 waits on the run of 2026-11-18 and the PM's ruling. |
| ac2: the weekly report line, as ruled, by tests on synthetic stores shown failing first | NOT RUN | Waits on the count and the PM's ruling on the line (step 3). |
| Node: `uv run pytest packages/debate_core/tests -k late_disclosure` | PASS (so far) | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k late_disclosure -q` → **15 passed in 50.8 s**: this task's 14, plus one in v1-e32-t06's `test_landscape_tournament_entries.py` whose name holds the same words. Run again when the report line lands. |

### Tests, red run and mutants

* **Tests.** `packages/debate_core/tests/application/test_landscape_late_disclosures.py` (15 with the
  parameters) and `tests/scripts/test_count_late_disclosures.py` (3). The second runs the script over a
  planted `hsld26` with this checkout's real `topics.yaml`. Its checks: `first_seen_through` is
  2026-11-03, the entry spellings are `bluekey` and `fbk`, and every file of the data directory has
  the same bytes after the run. Every expected count was written by hand from what each test plants.
  `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <both files> -q -n 0` →
  **18 passed in 0.23 s**.
* **Red run** against a skeleton of the module that counts nothing and refuses nothing (the checks'
  word validation and classing removed too): **16 failed, 1 passed**. The one that passes is the
  script's own missing-directory refusal, which is not in the module. The first red run, before three
  tests were strengthened, had 15 failed and 2 passed. The suppressed-file test asserted only that
  nothing was late, which the skeleton also satisfies, so it now has a live control that must be
  counted.
* **Mutants**, 19, each run against the two test files with no bytecode written and the module
  restored from `HEAD` after. All were caught, each by an assertion:

  | Mutant | Result |
  |---|---|
  | The topic's entry spellings not excluded | 2 failed |
  | Late by the snapshot's date, not the range's first day | 4 failed |
  | First seen read over suppressed files too | 1 failed |
  | Off-topic disclosures kept on the topic | 1 failed |
  | A spelling named with one school | 2 failed |
  | No run-together school-word test | 1 failed |
  | No whole-word withholding of tournament texts | 1 failed |
  | Both empty-tournament guards removed (a disclosure naming no tournament can be late) | 1 failed |
  | Both words classed as topic only | 2 failed |
  | Unparsed sources classed as neither | 1 failed |
  | Sources counted once per disclosure | 1 failed |
  | The share over on-topic disclosures only | 1 failed |
  | An entry-only snapshot not refused | 1 failed |
  | A snapshot the store lacks not refused | 2 failed |
  | Headings not read | 1 failed |
  | Tags not read | 1 failed |
  | Check words matched unreduced | 4 failed |
  | A disclosure's validation error let through | 1 failed |
  | That refusal raised with its context kept (`from None` removed) | 1 failed |

  One more, removing only the guard in `_first_seen`, survived. It is equivalent: the late test guards
  an empty spelling as well. The mutant that removes both guards is in the table.

## Files changed

* **`debate_core.application.landscape_late_disclosures`** (new): the count, its JSON and its refusals.
* **`scripts/count_late_disclosures.py`** (new): reads one data directory's stores by hand and prints the JSON.
* **Tests**: `packages/debate_core/tests/application/test_landscape_late_disclosures.py` (new) and
  `tests/scripts/test_count_late_disclosures.py` (new).

## Deviations from the spec

1. **The block runs from this worktree, with its `.venv`, not from the main clone at dev's tip** (accepted, the PM's ruling 1 of 2026-11-12). The
   PM's brief asked for the main clone. Its `.venv` imports the main clone's `debate_core`
   (`.../debate-intelligence/packages/debate_core/src`), which does not hold the new module until this
   branch merges, so the script could not run there. This worktree was started from dev's tip
   (`3cfd4af`, the main clone's `HEAD` and `origin/dev` on 2026-11-12) and changes no dependency
   (`uv.lock` and `pyproject.toml` are unchanged). The block prints the commit it ran. If the PM wants
   the main clone's interpreter anyway, the same block works with
   `PYTHONPATH=<worktree>/packages/debate_core/src` in front of that interpreter.
2. **`tests/scripts/test_count_late_disclosures.py` is outside `constraints.packages`.** The list names
   `scripts` and `packages/debate_core/tests`, and the scripts' tests live in `tests/scripts`. The rule's
   own tests are in `packages/debate_core/tests`, as the node's criterion runs them.

## Decisions and assumptions

1. **The rule is in `debate_core.application`, not only in the script,** so that step 4's weekly
   report line can count with the same function rather than a copy of it.
2. **The cut is the covering range's first day, not a date in code or on the command line.** "First
   seen on or before 2026-11-03" and "first seen before 2026-11-06" are the same with weekly Tuesday
   snapshots. The JSON's `first_seen_through` shows the 2026-11-03 it used.
3. **"FBK spellings" are the topic's own entry spellings from `topics.yaml`,** matched by "holds", as
   the entry is matched. Another topic's entry that covers the snapshot takes its disclosures off the
   topic, and they are counted as `off_topic`, so a later space-colonization entry would show up there.
4. **First seen among live disclosures only.** A spelling seen earlier only in a suppressed file is not
   late, because that earlier disclosure no longer counts anywhere.
5. **Spellings are named under a stricter test than the brief's** (accepted, the PM's ruling 2 of 2026-11-12). The brief named a spelling more
   than one school uses. This also withholds one that holds a school or team-code word, because a
   tournament named after its host school is a school's name: v1-e32-t06 left four such names out of its
   report (its Deviation 3). Schools are counted across every snapshot, as "uses" means for
   configuration.
6. **The parsed version is named in the block** (`--version 2026.11.03-docx-9`, the copy's parser per
   the brief), so a copy with another version refuses rather than reading a different one.

## Operator follow-ups

1. **The 2026-11-10 count: run 2026-11-12 (`exit 0`, `copy unchanged`, 6.6 s; results above).** It is
   read-only and opens no database. It stops, naming the path, if the worktree or its
   `.venv/bin/python` is missing (the PM's ruling 1: never another interpreter), if
   `~/t18-measure/copy` has no restore marker, or if the copy's newest hsld26 manifest is not
   `2026-11-10.jsonl`. It takes a fingerprint of the copy's files
   (names, sizes, times) before and after.

   **Operator command** (expected runtime under a minute, likely about 10 s)
   Where: any terminal on the Mac, when the PM says the copy is free (third, after v1-e31-t32's and
   v1-e31-t23's counts)
   ```bash
   WT=/Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t51-late-disclosures-from-pre-topic-tournaments-counted
   PY="${WT}/.venv/bin/python"
   COPY="$HOME/t18-measure/copy"
   NEWEST=$(ls "${COPY}/objects/manifests/hsld26" 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}[.]jsonl$' | LC_ALL=C sort | tail -1)
   if [[ ! -d "${WT}" ]]; then
     echo "STOP: no worktree at ${WT}"
   elif [[ ! -x "${PY}" ]]; then
     echo "STOP: no python at ${PY}; this block runs no other interpreter"
   elif [[ ! -f "${COPY}/debate-research-restored-copy.json" ]]; then
     echo "STOP: ${COPY} is not a restored copy"
   elif [[ "${NEWEST}" != "2026-11-10.jsonl" ]]; then
     echo "STOP: the copy's newest hsld26 manifest is ${NEWEST:-none}, not 2026-11-10.jsonl"
   else
     cd "${WT}"
     BEFORE=$(find "${COPY}" -type f -print0 | xargs -0 stat -f '%N %z %m' | LC_ALL=C sort | shasum -a 256)
     git -C "${WT}" log -1 --format='commit %h'
     "${PY}" "${WT}/scripts/count_late_disclosures.py" --data-dir "${COPY}" --caselist hsld26 --snapshot 2026-11-10 --version 2026.11.03-docx-9 --topic-word de-extinct --other-topic-word "space col" --other-topic-word coloniz
     echo "exit $?"
     AFTER=$(find "${COPY}" -type f -print0 | xargs -0 stat -f '%N %z %m' | LC_ALL=C sort | shasum -a 256)
     if [[ "${BEFORE}" == "${AFTER}" ]]; then echo "copy unchanged"; else echo "STOP: the copy changed"; fi
   fi
   ```
   Success looks like this:
   * a `commit` line, the JSON, `exit 0` and `copy unchanged`;
   * in the JSON: `"snapshot": "2026-11-10"`, `"newest_snapshot": "2026-11-10"`,
     `"topic": "ld-2026-nov-dec-de-extinction"`, `"first_seen_through": "2026-11-03"`,
     `"parsed_version": "2026.11.03-docx-9"`, `"tournament_entry_spellings": ["bluekey", "fbk"]`, and
     `"disclosures"` above zero.

   Paste the whole output back. It holds counts, dates, public configuration, and only those
   tournament spellings that two schools or more use and that hold no school or team-code word.

   If it prints `STOP`, paste that line and stop. `exit 2` comes with one `Refused:` line on stderr:
   paste it. `STOP: the copy changed` cannot come from this script, which writes nothing, so it means
   something else wrote to the copy during the run. Say so, and the PM decides whether the count stands.
   The copy is v1-e39-t18's to delete (policy 1.18), not this block's.
2. **The 2026-11-17 count**, after the run of 2026-11-18: its block is written in step 4, after the
   PM's ruling.

## Follow-up work

None yet.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

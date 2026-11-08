<!-- docs-index: Re-recording the landscape model evaluation under a new prompt version, then breaking it down as JSON -->
# Re-recording the landscape model evaluation

`debate-research landscape evaluate --model-mode record` asks the model about every card the coach
labelled, through the ModelRouter on the environment's route, and writes the calls as cassettes under
`~/.debate-research/<env>/landscape/model-cassettes/`. `--breakdown` then replays those cassettes with
no model call, card by card ([the replay runbook](landscape-model-evaluation-replay.md)).

`v1-e32-t40` wrote this for prompt `landscape.classify_position` 1.1.0, on the same 47 cards `v1-e32-t07`
recorded under 1.0.0 ([the counts](../data/landscape-model-evaluation.md)). A recording made under one
prompt version is never served to another: a 1.1.0 request finds no 1.0.0 cassette. Since `v1-e32-t46` a
checkout runs prompt 1.2.0, whose answers carry a stance: its re-record, on both routes, after the coach's
relabelling sitting, is [its section](#prompt-120-the-coachs-relabelling-sitting-then-both-routes-v1-e32-t46).
Since `v1-e32-t55` a checkout runs prompt 1.3.1, re-recorded on `deep_audit` by
[the last section](#prompt-131-the-re-record-on-deep_audit-v1-e32-t55).

## Before you start

* **The coach has approved the position descriptions**, or corrected them and the corrections are
  committed. The descriptions are sent with every call, so a recording made before the approval would
  have to be made again. The PM relays the approval; until then, do not run step 3.
* The data-use policy records its open question 4 as answered (version 1.20). The command refuses a
  recording otherwise (`MODEL_USE_NOT_YET_ALLOWED`).
* The calls are live: 47 cards in 3 batches of at most 20, on dev's `high_volume` route. Expect 3 or 4
  calls (one more if a batch is repaired), about 30,000 input tokens, a few cents.
* **The labels file has its sidecar** ([the guarded labels file](#the-labels-file-is-guarded-v1-e32-t58)).
  Every block below refuses the file without it.

## What to paste back

**Only the JSON's counts.** Steps 3 and 4 print one JSON object each: counts, taxonomy ids and sample
row numbers, which may be pasted into a session. Never paste the terminal listing of the scan's hits
(step 5) anywhere, a Claude session included: it prints schools, team codes and tournaments with words
of card text around them (`docs/policies/caselist-data-use.md`, model provider use, condition 1,
version 1.21).

## The labels file is guarded (`v1-e32-t58`)

On 2026-11-05 Microsoft Excel saved an older copy over the coach's labels file, and two sittings were lost
before any command noticed (`v1-e32-t55`'s report). Since `v1-e32-t58`:

* **The file is opened only through the sitting script** (`scripts/relabel_coach_sample.py`), never in a
  spreadsheet app (Excel, Numbers) or an editor, not even to look. A label is changed only in a sitting
  the PM rules.
* **Its SHA-256 is recorded beside it**, in `policy-2026-27-nhi-coach-sample-labelled.csv.sha256`: one line
  in the format `shasum -a 256` prints, the digest in lower-case hex, two spaces and the file's name. Only
  a sitting writes it, after the file, and once the one-time step below.
* **Every command that reads the file checks it first:** `landscape evaluate` in every mode
  (`--check-sample`, the replay, `--breakdown`, `--model-mode record`), the sitting itself and
  `compare_local_classifier.py score-sample`. A file whose SHA-256 differs is refused with
  `LABELS_FILE_CHANGED`, exit 1, naming both digests shortened, the sidecar and the command that writes
  it; a file with no sidecar with `LABELS_DIGEST_MISSING`; a sidecar that is not that one line with
  `LABELS_DIGEST_UNREADABLE`. On any of them, stop: do not record a new digest, keep the file as it is,
  and paste the error's code and the two shortened digests to the PM, nothing else.
* **Every sitting keeps the file it replaces**, beside it, under the sitting's date and time:
  `policy-2026-27-nhi-coach-sample-labelled.before-sitting-YYYY-MM-DD-HHMM.csv`, with `-2`, `-3` after the
  time for a second sitting in the same minute. A copy is never overwritten. The sitting then writes the
  file through its `.incoming` file and a rename, and only then the sidecar, so a sitting that stops in
  between leaves a refusal, never a file the sidecar wrongly vouches for. A dated copy has no sidecar of
  its own, so a command refuses it until the PM rules it back into place.
* **The file is read-only between sittings:**

```bash
chmod a-w ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
```

A spreadsheet app then cannot save over it. A sitting's block makes it writable first (`chmod u+w`) and
read-only again after (`chmod a-w`), as [the sitting's block](#1-the-coachs-relabelling-sitting) does: the
sitting puts a new file in place, and a new file starts writable.

### Once: record the digest of the coach's labels of 2026-11-06

The file the coach's sitting of 2026-11-06 wrote has SHA-256
`553374704519fd29f13a43e279a08537b28c87fbfc58372be845bc0de2b0a922` (`v1-e32-t55`'s report), and no
sidecar, since the sidecar did not exist then. This block records it once, from a checkout holding
`v1-e32-t58` (its task worktree until it merges, a checkout of `dev` after), and only if the file still
has that digest. It refuses a set `DEBATE_` variable, a running Excel and a sidecar already there; the
script itself refuses again if the digest differs and never overwrites a sidecar. Then it makes the file
read-only and reads it with `--check-sample`: a few seconds, no card read, no model asked.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t58-the-coach-sample-labels-file-guarded
```

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
EXPECT=553374704519fd29f13a43e279a08537b28c87fbfc58372be845bc0de2b0a922
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -x "Microsoft Excel" >/dev/null; then echo "STOP: Microsoft Excel is running; quit it first, so it cannot save over the labels file"; elif [ -e "${SAMPLE}.sha256" ]; then echo "STOP: the sidecar is already there; record nothing and paste this line"; elif [ "$(shasum -a 256 "$SAMPLE" | cut -d ' ' -f 1)" != "$EXPECT" ]; then echo "STOP: the labels file is not the one the sitting of 2026-11-06 wrote; record nothing and tell the PM"; elif ! uv run python scripts/record_coach_sample_digest.py --sample "$SAMPLE" --expect "$EXPECT"; then echo "STOP: nothing was recorded; paste the Refused line"; elif ! chmod a-w "$SAMPLE"; then echo "STOP: the digest is recorded, but the file could not be made read-only"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample; fi
```

Success: `Recorded 553374704519fd29… for policy-2026-27-nhi-coach-sample-labelled.csv in …`, then the JSON
with `labelled` 47, `by_label_kind` advantage 16, aff 1, cp 7, da 5, k 9, none 2, t 7, and `by_stance`
answers 9, reads 36. Paste back the `Recorded` line, or the `STOP:` or `Refused:` line, and the JSON:
digests, paths and counts only.

## 1. Go to the checkout

Run it from a source checkout of `dev` (the model stage reads `prompts/`), on the Mac that holds the
parsed store. `dev` is checked out in the main clone, so use it there:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence
git fetch origin && git merge --ff-only origin/dev
```

Then read the coach's sample against the taxonomy (`v1-e32-t41`). It takes a few seconds, reads no
card, asks no model and writes nothing. It must exit 0 with `labelled` 47 before anything else here:

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --check-sample; fi
```

A refusal names the row and the rule, or the labels file's digests (`LABELS_FILE_CHANGED`,
`LABELS_DIGEST_MISSING`): record nothing and tell the PM; the file is changed only in a sitting the PM
rules. If step 3 below fails with
`ModelAccessDenied` before any call, check the Bedrock profile's login with
`aws sts get-caller-identity --profile debate-dev-bedrock`, which also refreshes the role's
credentials, then run step 3 again (2026-11-02).

## 2. Check what the recording will read, with no model call

Expected runtime: about a minute. A replay before anything is recorded: it reads the labels, the
snapshot and the cards, then stops at the first batch, because no cassette of the checkout's prompt version
exists yet (1.1.0 when `v1-e32-t40` wrote it; 1.2.0 since `v1-e32-t46`).

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl; fi
```

What to read: `error.code` is `MISSING_FIXTURE_ERROR` and its message says there is no recorded answer
for prompt `landscape.classify_position@` and the checkout's version. That is the expected stop, and no model was called. Stop, and do not go on to step 3, on
anything else: a `STOP:` line, `EVALUATION_REFUSED` (the labels, the snapshot or the taxonomy), or an
exit 0 (something already recorded under that version, which the PM should hear about first).

## 3. Record

Expected runtime: about a minute. The live calls are made here, once.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --model-mode record; fi
```

What to read:

* `prompt_version` is the checkout's (`1.1.0` when this was written, `1.2.0` since `v1-e32-t46`), and
  `labelled`, `found` and `asked` are 47.
* `calls` is above zero, and `pipeline.accuracy` against `target` 0.85 says whether it meets the bar
  (`bar_reads` is `pipeline`, since `v1-e32-t43`): the cards as students meet them, the headings' sure
  placements first and the model's answers for the rest. `model_alone` is the model's score on every
  card, and the top-level `accuracy` is its. Exit 0
  means it meets the bar and every scan is clean; exit 1 `EVALUATION_BELOW_BAR` puts the same counts in
  `error.details`.
* `scan`: `prompt_inputs`, `cassettes` and `repair_cassettes`, each with its `texts` and its counts of
  schools, team codes and tournaments. The cassettes scanned are this prompt version's; `v1-e32-t39`'s
  1.0.0 cassettes stay on the Mac, unread by this scan. Since `v1-e32-t44` a text whose every hit is marked
  a JSON key's name or a taxonomy word (and none a team's name or words its cards sent) leaves `clean`
  true; `set_aside` counts those texts and their hits by mark. The counts above still count every hit.
* Paste the whole JSON object back.

## 4. Break it down, as JSON

Expected runtime: about a minute, no model call: the replay of what step 3 recorded.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --breakdown; fi
```

What to read: the same counts as step 3, and `breakdown.outcomes` summing to 47. `breakdown.scan_hits`
counts the hits by kind and field and holds none of their words. Paste the whole JSON object back.

## 5. Only if a scan count is above zero: the hits, in the terminal

**Do not paste or copy this step's output anywhere: not into a Claude session, a chat, a report or an
issue.** Skip it when every scan count in step 3 is zero. It is the same command as step 4 without
`--json`, and it lists each hit with words of card text around it, for your eyes only.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --breakdown; fi
```

To report on them, give each hit's number and whether its words name a team, a school or a tournament,
or are an ordinary word that shares them: numbers and judgements, never the words.

## Recording on another route (`v1-e32-t43`)

`landscape evaluate --route <task class>` measures the same cards on another generative route of the
routing file: that route's model answers the prompt's `high_volume` calls, and the budget guard prices
that model's ceiling. Its cassettes go to `~/.debate-research/<env>/landscape/model-cassettes-<route>/`,
never the default directory, so the 1.1.0 `high_volume` cassettes are neither replaced nor served in its
place; `--route` on a replay or a `--breakdown` reads that directory alone. `landscape cassettes --route
<route>` lists and deletes them.

The PM approved dev's `deep_audit` route (Claude Sonnet 4.6) for the coach's 47 cards on 2026-11-03.
Priced from `config/model_pricing.yaml` at the 1.1.0 recording's tokens it costs about $0.17, and the
guard's ceiling for its three calls is about $1.11 (about $1.49 with a repair), inside dev's $2 a day.

Run it from a checkout that has `--route` (go to it as step 1 says), after the step 1 sample check has
exited 0 once. One block, in this order: the sample check, the Bedrock login check, the recording, and
the breakdown replaying what it recorded. Each `STOP:` line stops it before any model call. Expected
runtime: 3 to 5 minutes.

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif ! uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample; then echo "STOP: the sample check failed; paste its JSON and record nothing"; elif ! aws sts get-caller-identity --profile debate-dev-bedrock >/dev/null; then echo "STOP: the Bedrock profile is not logged in; log in and paste again"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --model-mode record --route deep_audit; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

What to read, and paste back: **the three JSON objects, and nothing else.**

* The sample check: `labelled` 47.
* The recording: `route` `deep_audit`, `prompt_version` `1.1.0`, `labelled`, `found` and `asked` 47, and
  `calls` 3 or 4. Exit 0 means the pipeline meets the bar and every scan is clean; exit 1
  `EVALUATION_BELOW_BAR` puts the same counts in `error.details`. A stop before any answer
  (`MODEL_ACCESS_DENIED`, or a budget refusal) recorded nothing: paste it, and do not run it again
  before the PM has read it.
* The breakdown: the same counts with no call made, and `breakdown.outcomes` summing to 47.

If any `scan` count in the recording is above zero, read the hits as step 5 says, in the terminal only,
with this block, which is step 5's with `--route deep_audit`. **Never paste or copy its output**; give
each hit's number and whether its words name a team, a school or a tournament, or are an ordinary word
that shares them.

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; else uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

## Prompt 1.2.0: the coach's relabelling sitting, then both routes (`v1-e32-t46`)

Prompt 1.2.0 asks the model whether each card reads its position or answers it, and the coach's sample
says the same with `at:<id>` for a card that answers ([the guide](../guides/landscape-taxonomy.md#your-labelled-sample-of-cards)).
Two blocks, in order, each run once. Run them from a checkout holding `v1-e32-t46`: its task worktree until
it merges, a checkout of `dev` after (step 1). Go to it:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t46-prompt-1-2-0-refusal-fixes-and-answering-stances
```

### 1. The coach's relabelling sitting

The coach sits at the terminal. The PM ruled the rows (2026-11-05): the 13 that may answer a position,
mixed with 6 control rows drawn at random from the other labelled rows by the seed 20261105, all 19 in one
random order and unmarked. Each card shows the coach's own tag and headings from the CSV, the side its file
was disclosed on, and the coach's label; nothing about the model's answers, the recordings or the score.
Type a label (`at:politics-da` for a card that answers the politics DA, a plain id for one that reads it,
`none`, or `unsure`), or press Enter to keep it. A label the evaluation would refuse is asked again.

The script first checks the labels file against its sidecar and stops on a file the sidecar does not
record ([the guarded labels file](#the-labels-file-is-guarded-v1-e32-t58)). It reads the store for each
card's side (about half a minute), and writes only changed labels, once, at the end; Ctrl-C writes nothing.
Before it writes, it keeps the file it replaces as a dated copy beside it
(`policy-2026-27-nhi-coach-sample-labelled.before-sitting-YYYY-MM-DD-HHMM.csv`), then writes the file, then
its sidecar. (Until `v1-e32-t58` it kept one copy, `.before-stance-relabel.csv`, and wrote no sidecar.) It
ends with one line of counts, then `--check-sample` reads the result: a few seconds, no card read and no
model asked. The block makes the file writable for the sitting and read-only again after it, whether the
sitting finished or stopped; it refuses to start while Excel runs.

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif pgrep -x "Microsoft Excel" >/dev/null; then echo "STOP: Microsoft Excel is running; quit it first, so it cannot save over the labels file"; elif ! chmod u+w "$SAMPLE"; then echo "STOP: the labels file could not be made writable for the sitting"; elif ! uv run python scripts/relabel_coach_sample.py --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --rows 5,11,13,16,20,21,25,26,31,33,41,57,59 --seed 20261105; then chmod a-w "$SAMPLE"; echo "STOP: the sitting stopped; paste its last line only"; else chmod a-w "$SAMPLE"; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample; fi
```

What to paste back: **the sitting's last line** (`Done. Listed: ... Control: ...`, counts only) **and the
JSON object**, nothing else. The cards the sitting showed stay in the terminal. Success: exit 0, `labelled`
47 (fewer only if the coach turned a row `unsure`), and `by_stance` with `answers` above zero if the coach
wrote any `at:` label. Stop on a `STOP:` line, on `EVALUATION_REFUSED` (its message names the row and the
rule), or on a `Stopped:` line from the sitting. This block is the shape of every sitting from now on; the
PM gives each sitting's rows and seed.

### 2. The re-record on both routes, then the breakdowns

The PM ruled both routes (2026-11-05): `high_volume` (Claude Haiku 4.5), the route the landscape stage runs
on and the bar must meet, and `deep_audit` (Claude Sonnet 4.6). Priced from `config/model_pricing.yaml` at
the 1.1.0 recordings' tokens with 1.2.0's longer instructions, about $0.06 and $0.19. The budget guard
prices each call's ceiling from its variables, which 1.2.0 leaves as they were: $0.154 for Haiku's three
calls and $1.106 for Sonnet's (about $0.21 and $1.50 with a repair), inside dev's $2.00 a day if nothing
else spent that day. 1.2.0's cassettes go beside 1.1.0's, under their own keys, in
`model-cassettes/` and `model-cassettes-deep_audit/`; nothing is replaced.

One block, in this order: the sample check, the Bedrock login check, the recording on each route, then
the breakdown replaying each. Each `STOP:` line stops it before any model call. Expected runtime: 4 to 6
minutes.

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif ! uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample; then echo "STOP: the sample check failed; paste its JSON and record nothing"; elif ! aws sts get-caller-identity --profile debate-dev-bedrock >/dev/null; then echo "STOP: the Bedrock profile is not logged in; log in and paste again"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --model-mode record; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --model-mode record --route deep_audit; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

What to read, and paste back: **the five JSON objects, and nothing else.** They hold counts, taxonomy ids
and sample row numbers.

* The sample check: `labelled` as the sitting left it, 47.
* Each recording: `prompt_version` `1.2.0`; `labelled`, `found` and `asked` 47; `calls` 3 or 4; and for
  the second, `route` `deep_audit`. `pipeline.accuracy` against `target` 0.85 is the bar. Exit 0 means the
  pipeline meets it and every scan is clean; exit 1 `EVALUATION_BELOW_BAR` puts the same counts in
  `error.details`. A stop before any answer (`MODEL_ACCESS_DENIED`, or a budget refusal) recorded nothing
  on that route: paste it, and do not run the block again before the PM has read it.
* Each breakdown: the same counts with no call made, `breakdown.outcomes` summing to 47, `wrong_stance`
  among them.

If any `scan` count in either recording is above zero, read the hits in the terminal only, with this
block (step 5's, for each route). **Never paste or copy its output**; give each hit's number and whether
its words name a team, a school or a tournament, or are an ordinary word that shares them.

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; else uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown; uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

## Prompt 1.3.0: the re-record on `deep_audit` (`v1-e32-t49`)

Prompt 1.3.0 carries the PM's rulings of 2026-11-05. A card defending its own side's position against
answers reads it. An answer to a position is that position answered, never the answering side's own case.
A definition the affirmative reads against a counterplan answers that counterplan. A generic kritik is
chosen by its theory, and may carry a high confidence. The evaluation and the report also give READS to
any placement in a file disclosed only on its position's own side
([the evaluation's record](../data/landscape-model-evaluation.md#prompt-130-and-the-own-side-rule-v1-e32-t49-ruled-2026-11-05)).
The coach's labels are unchanged since 1.2.0's re-record, so there is no sitting.

The PM ruled one route, `deep_audit` (Claude Sonnet 4.6): prompts are tuned on it, and Haiku is not
re-recorded. The price comes from `config/model_pricing.yaml` ($0.003 and $0.015 per 1,000 input and output
tokens), at 1.2.0's recorded tokens (40,240 and 4,847) plus 1.3.0's 1,591 more characters of instructions in
each of the 3 calls, about 1,200 tokens. That is about 41,400 input and 4,850 output tokens: **about
$0.20**. The budget guard prices each call's ceiling from its variables, which 1.3.0 leaves as 1.2.0 had
them. So the ceiling is 1.2.0's: $1.106 for the three calls, about $1.50 with a repair, inside dev's $2.00 a
day if nothing else spent that day. 1.3.0's cassettes go beside 1.2.0's in `model-cassettes-deep_audit/`,
under their own keys, and nothing is replaced.

Run it from a checkout holding `v1-e32-t49`: its task worktree until it merges, a checkout of `dev` after.
Go to it:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t49-prompt-1-3-0-own-side-answers-and-the-coachs-rulings
```

One block, in order: the sample check, the Bedrock login check, the recording on `deep_audit`, then the
breakdown replaying it. Each `STOP:` line stops it before any model call. Expected runtime: 2 to 4
minutes.

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif ! uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample; then echo "STOP: the sample check failed; paste its JSON and record nothing"; elif ! aws sts get-caller-identity --profile debate-dev-bedrock >/dev/null; then echo "STOP: the Bedrock profile is not logged in; log in and paste again"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --model-mode record --route deep_audit; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

What to read, and paste back: **the three JSON objects, and nothing else.** They hold counts, taxonomy ids
and sample row numbers.

* **The sample check:** `labelled` 47, `by_stance` answers 10 and reads 35, as 1.2.0's re-record left
  them.
* **The recording:**
  * `prompt_version` `1.3.0`, `route` `deep_audit`; `labelled`, `found` and `asked` 47; `calls` 3 or 4.
  * `pipeline.accuracy` against `target` 0.85 is the bar. Exit 0 means the pipeline meets it and every
    scan is clean. Exit 1 `EVALUATION_BELOW_BAR` puts the same counts in `error.details`.
  * A stop before any answer (`MODEL_ACCESS_DENIED`, or a budget refusal) recorded nothing. Paste it, and
    do not run the block again before the PM has read it.
* **The breakdown:**
  * the same counts with no call made, and `breakdown.outcomes` summing to 47;
  * `breakdown.generic_answers`, the PM's condition on the generic-confidence clause: the answers naming
    a generic position, how many are above the threshold, and how many of those are right and wrong.
    `named_label_rows` lists any row labelled with a named kritik that was answered generic. Look for
    rows 12 and 55 there, and in their cards' outcomes in `breakdown.cards`.

If the recording's `scan` counts are above zero, read the hits in the terminal only, with this block.
**Never paste or copy its output.** For each hit, give its number and whether its words name a team, a
school or a tournament, or are an ordinary word that shares them.

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; else uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

## Prompt 1.3.1: the re-record on `deep_audit` (`v1-e32-t55`)

Prompt 1.3.1 is 1.3.0 with one sentence taken out, the generic-confidence one ("A generic position is never
named by a tag or heading: give it 0.9 or more ..."). Every other line of the prompt is 1.3.0's. 1.3.0's
re-record failed the PM's condition on that sentence: above the threshold, the answers naming a generic
position were right 0 times and wrong once (row 26)
([the evaluation's record](../data/landscape-model-evaluation.md#the-re-record-under-130-v1-e32-t49-ac3-2026-11-05)).
The coach's labels, the bar and the threshold are unchanged since 1.3.0's re-record, so there is no sitting.

One route, `deep_audit` (Claude Sonnet 4.6), as for 1.3.0. The price comes from `config/model_pricing.yaml`
($0.003 and $0.015 per 1,000 input and output tokens). 1.3.0's re-record took 41,332 input and 4,737 output
tokens. 1.3.1 sends 215 fewer characters of instructions in each of the 3 calls, about 160 tokens in all.
That is about 41,170 input and 4,740 output tokens: **about $0.19**. The budget guard prices each call's
ceiling from its variables, which 1.3.1 leaves as 1.3.0 had them, so the ceiling is the one 1.3.0's section
gives: $1.106 for the three calls, about $1.50 with a repair, inside dev's $2.00 a day if nothing else spent
that day. 1.3.1's cassettes go beside 1.3.0's in `model-cassettes-deep_audit/`, under their own keys, and
nothing is replaced. Nothing is published: `landscape evaluate` writes only those local cassettes and never
touches the bucket.

Run it from a checkout holding `v1-e32-t55`: its task worktree until it merges, a checkout of `dev` after.
Go to it:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t55-prompt-1-3-1-without-the-generic-confidence-sentence
```

One block, in order: the sample check, the Bedrock login check, the recording on `deep_audit`, then the
breakdown replaying it. Each `STOP:` line stops it before any model call. The sample check must show the
coach's labels of 2026-11-06, which the PM chose on 2026-11-07 (by kind advantage 16, aff 1, cp 7, da 5, k 9,
none 2, t 7; by stance answers 9, reads 36), or the block stops: the first run of this block, on 2026-11-06, recorded against an older labels file
because it checked those counts only in the prose below. Expected runtime: 2 to 4 minutes.

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif ! CHECK=$(uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample); then echo "$CHECK"; echo "STOP: the sample check failed; paste its JSON and record nothing"; elif ! printf '%s\n' "$CHECK" | grep -qF '"by_label_kind": {"advantage": 16, "aff": 1, "cp": 7, "da": 5, "k": 9, "none": 2, "t": 7}' || ! printf '%s\n' "$CHECK" | grep -qF '"by_stance": {"answers": 9, "reads": 36}'; then echo "$CHECK"; echo "STOP: these are not the coach's labels of 2026-11-06; paste this JSON and nothing else"; elif ! aws sts get-caller-identity --profile debate-dev-bedrock >/dev/null; then echo "STOP: the Bedrock profile is not logged in; log in and paste again"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --model-mode record --route deep_audit; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

What to read, and paste back: **the three JSON objects, and nothing else.** They hold counts, taxonomy ids
and sample row numbers.

* **The sample check:** `labelled` 47, `by_stance` answers 9 and reads 36: the coach's re-sitting of
  2026-11-06, which the PM chose after Excel overwrote the 2026-11-04 file (`v1-e32-t55`'s report).
* **The recording:**
  * `prompt_version` `1.3.1`, `route` `deep_audit`; `labelled`, `found` and `asked` 47; `calls` 3 or 4.
  * `pipeline.accuracy` against `target` 0.85 is the bar. Exit 0 means the pipeline meets it and every
    scan is clean. Exit 1 `EVALUATION_BELOW_BAR` puts the same counts in `error.details`.
  * A stop before any answer (`MODEL_ACCESS_DENIED`, or a budget refusal) recorded nothing. Paste it, and
    do not run the block again before the PM has read it.
* **The breakdown:**
  * the same counts with no call made, `breakdown.outcomes` summing to 47, and `breakdown.cards` giving
    each row's outcome, for the PM's row-by-row comparison with 1.3.0;
  * `breakdown.generic_answers`: the answers naming a generic position, how many are above the threshold,
    and how many of those are right and wrong, with `named_label_rows`;
  * the rows to look at in `breakdown.cards`: 26 (`at:cap-k`, answered `at:generic-k` at 0.62 under
    1.3.0), 12 and 55 (`cap-k`, right under 1.3.0), and 9 and 53 (right under 1.2.0, below the threshold
    under 1.3.0).

### Re-scoring the recording on the right labels, with no model call

The recording's answers do not depend on the labels: the model is sent the cards, never the coach's labels.
So a recording scored against the wrong labels file is re-scored by replaying it, once the right file is
back at `$SAMPLE`. This block checks the labels' counts first and makes no model call. Expected runtime:
about a minute.

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif ! CHECK=$(uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample); then echo "$CHECK"; echo "STOP: the sample check failed; paste its JSON and record nothing"; elif ! printf '%s\n' "$CHECK" | grep -qF '"by_label_kind": {"advantage": 16, "aff": 1, "cp": 7, "da": 5, "k": 9, "none": 2, "t": 7}' || ! printf '%s\n' "$CHECK" | grep -qF '"by_stance": {"answers": 9, "reads": 36}'; then echo "$CHECK"; echo "STOP: these are not the coach's labels of 2026-11-06; paste this JSON and nothing else"; else echo "$CHECK"; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

Paste back the two JSON objects, nothing else: the sample check, and the breakdown with `prompt_version`
`1.3.1` and `calls` 5 (the 3 calls and 2 repairs recorded on 2026-11-06).

If the recording's `scan` counts are above zero, read the hits in the terminal only, with this block.
**Never paste or copy its output.** For each hit, report only its number and whether it is an ordinary
word.

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; else uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

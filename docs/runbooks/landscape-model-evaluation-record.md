<!-- docs-index: Re-recording the landscape model evaluation under a new prompt version, then breaking it down as JSON -->
# Re-recording the landscape model evaluation

`debate-research landscape evaluate --model-mode record` asks the model about every card the coach
labelled, through the ModelRouter on the environment's route, and writes the calls as cassettes under
`~/.debate-research/<env>/landscape/model-cassettes/`. `--breakdown` then replays those cassettes with
no model call, card by card ([the replay runbook](landscape-model-evaluation-replay.md)).

`v1-e32-t40` wrote this for prompt `landscape.classify_position` 1.1.0, on the same 47 cards `v1-e32-t07`
recorded under 1.0.0 ([the counts](../data/landscape-model-evaluation.md)). A recording made under one
prompt version is never served to another: a 1.1.0 request finds no 1.0.0 cassette.

## Before you start

* **The coach has approved the position descriptions**, or corrected them and the corrections are
  committed. The descriptions are sent with every call, so a recording made before the approval would
  have to be made again. The PM relays the approval; until then, do not run step 3.
* The data-use policy records its open question 4 as answered (version 1.20). The command refuses a
  recording otherwise (`MODEL_USE_NOT_YET_ALLOWED`).
* The calls are live: 47 cards in 3 batches of at most 20, on dev's `high_volume` route. Expect 3 or 4
  calls (one more if a batch is repaired), about 30,000 input tokens, a few cents.

## What to paste back

**Only the JSON's counts.** Steps 3 and 4 print one JSON object each: counts, taxonomy ids and sample
row numbers, which may be pasted into a session. Never paste the terminal listing of the scan's hits
(step 5) anywhere, a Claude session included: it prints schools, team codes and tournaments with words
of card text around them (`docs/policies/caselist-data-use.md`, model provider use, condition 1,
version 1.21).

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

A refusal names the row and the rule; fix the sample before recording. If step 3 below fails with
`ModelAccessDenied` before any call, check the Bedrock profile's login with
`aws sts get-caller-identity --profile debate-dev-bedrock`, which also refreshes the role's
credentials, then run step 3 again (2026-11-02).

## 2. Check what the recording will read, with no model call

Expected runtime: about a minute. A replay before anything is recorded: it reads the labels, the
snapshot and the cards, then stops at the first batch, because no 1.1.0 cassette exists yet.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl; fi
```

What to read: `error.code` is `MISSING_FIXTURE_ERROR` and its message says there is no recorded answer
for prompt `landscape.classify_position@1.1.0`. That is the expected stop, and no model was called. Stop, and do not go on to step 3, on
anything else: a `STOP:` line, `EVALUATION_REFUSED` (the labels, the snapshot or the taxonomy), or an
exit 0 (something already recorded under 1.1.0, which the PM should hear about first).

## 3. Record

Expected runtime: about a minute. The live calls are made here, once.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --model-mode record; fi
```

What to read:

* `prompt_version` is `1.1.0`, and `labelled`, `found` and `asked` are 47.
* `calls` is above zero, and `pipeline.accuracy` against `target` 0.85 says whether it meets the bar
  (`bar_reads` is `pipeline`, since `v1-e32-t43`): the cards as students meet them, the headings' sure
  placements first and the model's answers for the rest. `model_alone` is the model's score on every
  card, and the top-level `accuracy` is its. Exit 0
  means it meets the bar and every scan is clean; exit 1 `EVALUATION_BELOW_BAR` puts the same counts in
  `error.details`.
* `scan`: `prompt_inputs`, `cassettes` and `repair_cassettes`, each with its `texts` and its counts of
  schools, team codes and tournaments. The cassettes scanned are this prompt version's; `v1-e32-t39`'s
  1.0.0 cassettes stay on the Mac, unread by this scan.
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

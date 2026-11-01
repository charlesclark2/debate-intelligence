<!-- docs-index: Replaying a recorded landscape model evaluation, broken down card by card, with no model call -->
# Replaying the landscape model evaluation, broken down

`debate-research landscape evaluate --breakdown` (`v1-e32-t39`) replays an evaluation the operator
recorded with `--model-mode record`. It gives every labelled card one outcome beside what the headings
alone place, says what the structured-output guard did with each batch, and lists the name scan's
hits. It calls no model: the router it builds holds none, so a request no cassette recorded fails with
`MISSING_FIXTURE` and is never sent. `--breakdown` with `--model-mode record` is refused.

It writes nothing to the repository or a bucket. A replay adds the caselist's slug to a cassette that
does not name it yet; the recorded cassettes already name it.

## What it reads

* The coach's labelled sample, the CSV the coach filled, and the rows file `v1-e32-t21` wrote beside it.
  The replay must use the same labelled CSV as the recording: the cards asked about, and so the
  batches, come from its labels.
* The parsed store and the weekly snapshot the recording read. Name the snapshot with `--snapshot`, so a
  newer week does not change the cards.
* The cassettes under `~/.debate-research/<env>/landscape/model-cassettes/`: the classify prompt's, and
  the repair prompt's filed under the caselist.

## Where the hits go

The scan's hits name schools, team codes and tournaments. They are printed **in a terminal only**: not
in `--json`, never in a log or a file, and not when stdout is a pipe or a file (`| tee`, `>`), where
the command prints only how many it withheld. Never paste them into a session, a report, a document, an
issue or a commit (`docs/policies/caselist-data-use.md`). The counts of hits, by kind and field, are in
`--json` and may be written down.

## 1. Go to a checkout

Run it from a source checkout (the model stage reads `prompts/`), on the Mac that holds the cassettes.
A checkout replays only what was recorded under the prompt version and the scrub it holds:

* since `v1-e32-t40`, prompt 1.1.0 with every disclosing team's names taken out, recorded by
  [the record runbook](landscape-model-evaluation-record.md), from a worktree of `dev`, or `v1-e32-t40`'s
  until it merges;
* the first recording, under 1.0.0, only from a checkout of `dev` at `28d4c88` (`v1-e32-t39`'s merge) or
  earlier. A later checkout asks for 1.1.0 and stops with `MISSING_FIXTURE_ERROR`.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t40-model-stage-reads-the-argument-not-the-subject
```

## 2. The counts, as JSON

Expected runtime: about a minute (it reads the caselist's parsed sources, as a landscape dry run does).
The block refuses a leftover `DEBATE_*` override and a running `caselist pull`, which could change the
store under it.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --breakdown; fi
```

What to read:

* An evaluation under the bar exits `1` with `error.code` `EVALUATION_BELOW_BAR`, and the counts are in
  `error.details`; one that meets it exits `0`, with them in `data`. `labelled`, `found` and `asked` are
  above zero, and `breakdown.outcomes` sums to `labelled`.
* `MISSING_FIXTURE_ERROR` means a request differs from every recorded one: the labels, the snapshot, the
  parsed store or the taxonomy changed since the recording. No model was called. Stop; the evaluation
  has to be recorded again, which waits on the PM.
* This output holds counts and taxonomy ids only, so it may be pasted into a session.

## 3. The hits, in the terminal

**Do not paste or copy this step's output anywhere: not into a Claude session, a chat, a report or an
issue.** Everything to send back is in step 2's JSON. This step is only for reading the hits.

The same command without `--json`. It prints the counts again, then one numbered line per hit: the text
(`input batch 2`, `cassette 1`, `repair cassette 1`), the field (heading path, tag, short cite, excerpt,
model rationale, taxonomy positions, repaired prompt, cassette metadata, across fields), the kind
(school, team-code word, tournament), its marks (a team's name, a taxonomy word, a JSON key, in the
cards sent), and the matched words with four words either side. Step 2's JSON counts the marks by
field (`marks_by_field`).

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --breakdown; fi
```

Read the hits here and do not paste them anywhere. To report on them, give each one's number and
whether its matched words name a team, a school or a tournament there, or are an ordinary word that
shares them (a surname, a city, a journal, a common word): numbers and judgements, never the words.

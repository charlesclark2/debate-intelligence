<!-- docs-index: Publishing a caselist's landscape report from the weeks the cloud run pulled: restore a copy, parse it, dry run, publish, delete the copy -->
# A landscape report from the cloud run's weeks

Since the cutover (2026-10-27) the weekly caselist run is the cloud task, and the weeks it pulls are in
the dev bucket. Your dev data directory (`~/.debate-research/dev`) stops at this Mac's last pull, so a
report run over it alone reads "through 2026-10-20" whatever the cloud has pulled since. This runbook
publishes a caselist's landscape report from the newest week (`v1-e40-t17`, the PM's ruling of
2026-10-30):

1. restore a copy of the run's state from the dev bucket, with the caselist's raw sources;
2. parse the copy with this build, into the copy;
3. dry run the report over the copy, and read its counts;
4. publish it;
5. delete the copy.

**What lives where.** `landscape report --restored-copy <copy>` reads the caselist's cards from the
copy: its manifests, its parsed store, its suppression list, the cloud run's log and the raw sources.
Everything the landscape keeps stays in your dev data directory, where deleting the copy cannot touch
it: the classification cache, the review queue, the plan-text and analytic-text caches, the scan hits
you have accepted, the model cassettes, the model usage log that dev's budget is counted from, and the
bundle under `reports/landscape/`. So a card classified once is never classified again because a copy
went away.

**When.** Never on a Wednesday, the cloud run's day, and never while the run lock is held: the restore
and the publish both take the dev run lock, and stop with `RUN_LOCK_HELD` while a run holds it. Every
block below refuses a Wednesday. Thursday after the run has recorded, or any later day, is the time.

**What refuses what.** In dev, which is in bucket mode, `landscape report --publish` without
`--restored-copy` is refused with `PUBLISH_NEEDS_A_RESTORED_COPY`: the data directory's newest snapshot
is not the newest week. A report over a copy whose newest parsed directory is not this build's parser
version is refused with `PARSED_VERSION_NOT_IN_STORE`, which is what step 2 is for. A `--restored-copy`
naming the data directory, a directory inside it or holding it, or one inside a checkout is refused with
`RESTORED_COPY_REFUSED`.

**One caselist per pass, in one terminal window**, which keeps `CASELIST` and `COPY` from the first block
to the last. The output files under `/tmp` hold counts, except the scan's lines, which can name a school
or a team: those are for your terminal only, and the last block deletes the files.

## Before you start

The build on this Mac must be a dev release carrying `v1-e40-t17`. Set the caselist, then check the build,
the day and the room:

**Operator command** (expected runtime a few seconds)
Where: your Mac, in a new terminal window
```bash
CASELIST=hspolicy26
COPY="$HOME/.debate-research/landscape-copy-${CASELIST}"
debate-research --json --version | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"]["tag"])'
debate-research landscape report --help | grep -c -- '--restored-copy'
date +%A
df -g "$HOME" | awk 'NR == 2 { print $4 " GB free" }'
```
Success looks like a tag of the release carrying `v1-e40-t17` or later, then a count of 1 or more, a
day that is not Wednesday, and 15 GB free or more. A count of `0` means the build is older: install a
newer dev release first. The copy needs about 6 GB for hspolicy26: its raw sources (1.1 GB through
2026-10-20, measured from the manifests, plus the cloud's weeks) and the parsed store step 2 writes
(the data directory's hspolicy26 parsed store is 4.0 GB).

## 1. Restore the copy, with the caselist's raw sources

The block refuses a Wednesday, a shell with a `DEBATE_` override, a pull running on this Mac and a copy
that exists already. Then it signs in to dev and restores, holding the dev run lock while it reads. It
fetches every raw source of the caselist the restored manifests name (no `--snapshot`), each checked
against its digest, because a report re-reads the quoted texts from their sources on every run.

**Operator command** (expected runtime ~3 to 10 min: 1.1 GB of hspolicy26 sources through 2026-10-20 in
3,869 objects, plus the cloud's weeks; the cutover's restore moved 9.1 GB in about 4.5 minutes on this
Mac, so most of the time is the number of objects, not their size)
Where: your Mac, in the window that set `CASELIST` and `COPY`
```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif [ -e "$COPY" ]; then echo "STOP: ${COPY} exists already"; else aws sso login --profile debate-dev-evidence && cd "$HOME" && caffeinate -i env DEBATE_ENV=dev debate-research --json caselist restore-run-state --into "$COPY" --caselist "$CASELIST" --with-sources > /tmp/landscape-restore.json; echo "exit $?"; grep -oE '"(manifests|parsed_version|parsed_objects|named|fetched|fetched_bytes|suppressed)": ("[^"]*"|[0-9]+)|"code": "[A-Z_]+"' /tmp/landscape-restore.json; fi
```
Before it fetches it prints `Fetching <n> raw source(s), <bytes> bytes, that <m> restored manifest(s)
name; <s> skipped as the suppression list holds them.` Success looks like `exit 0`, then
`"parsed_version": "2026.10.27-docx-7"` (this build's), and `"fetched"` equal to `"named"` less
`"suppressed"`, above zero.

`"parsed_objects": 0` is expected until the parsed store of `2026.10.27-docx-7` is published to the dev
bucket: the run image deployed on 2026-10-29 was built before the parser bump and parses with
`2026.10.20-docx-6`, and a restore brings back only this build's version. Step 2 then parses the
whole caselist. Above zero, step 2 parses only what the copy lacks.

A stop says the directory is not a copy to publish from. Delete it with step 5 before anything else, and:

* `RUN_LOCK_HELD`: a cloud run holds the lock; wait for it to record, then run step 1 again.
* `RESTORED_SOURCES_INCOMPLETE`: a source a manifest names is neither in the bucket nor suppressed. Tell
  the PM, with the file; do not go on.
* `TOO_LITTLE_ROOM_FOR_SOURCES`: make room, then run step 1 again.

## 2. Parse the copy with this build, into the copy

`landscape report` reads the parsed store of this build's parser version. `caselist parse` writes it,
and the parsed store's card statistics, into the data directory it runs over. So this one command runs
with `DEBATE_STORAGE__DATA_DIR` naming the copy, set by `env` for that command alone, and never with
`--publish`: it writes nothing in your dev data directory and nothing to any bucket. It is the only
place in this runbook where that variable is set. First its dry run, which writes nothing:

**Operator command** (expected runtime under a minute)
Where: your Mac, in the same window
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif [ ! -d "$COPY" ]; then echo "STOP: no copy at ${COPY}"; else cd "$HOME" && env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" debate-research --json caselist parse --caselist "$CASELIST" --dry-run > /tmp/landscape-parse-dry-run.json; echo "exit $?"; grep -oE '"(version|parser_version|sources|skipped|suppressed|to_parse)": ("[^"]*"|[0-9]+)|"code": "[A-Z_]+"' /tmp/landscape-parse-dry-run.json; fi
```
Success looks like `exit 0`, `"parser_version": "2026.10.27-docx-7"`, and `"sources"` above zero. With
`"parsed_objects": 0` in step 1, `"to_parse"` equals `"sources"`; with a restored directory, it is
what that directory lacks, and `0` means the copy is parsed already: go to step 3.
`"parser_version": "2026.10.20-docx-6"` means the build is older than the parser bump: stop, delete the
copy, and install a newer release.

Then the parse, under `caffeinate`:

**Operator command** (expected runtime ~12 to 15 min for hspolicy26 from nothing: its full parses took
611 to 747 s for 2,657 sources in October (`docs/data/caselist-parse-report.md`), and the cloud's weeks
add some; much less when step 1 restored a directory)
Where: your Mac, in the same window
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif [ ! -d "$COPY" ]; then echo "STOP: no copy at ${COPY}"; else cd "$HOME" && caffeinate -i env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" debate-research --json caselist parse --caselist "$CASELIST" > /tmp/landscape-parse.json; echo "exit $?"; grep -oE '"(version|attempted|parsed|cards|failure_rate|threshold_exceeded|elapsed_seconds)": ("[^"]*"|[0-9.]+|true|false)|"code": "[A-Z_]+"' /tmp/landscape-parse.json; fi
```
Success looks like `exit 0`, `"version"` starting `2026.10.27-docx-7`, `"parsed"` and `"cards"` above
zero, and `"threshold_exceeded": false`. `PARSE_FAILURE_RATE_EXCEEDED` (exit `1`): stop and send the PM
the file, which holds counts only.

## 3. The dry run, and its counts

The report over the copy, writing nothing: not the classification cache, not the review queue, not the
bundle, not the bucket. It signs in to dev, because it asks the bucket which files would go up, and it
says how many cards it would ask the model about.
With `--model-mode none` that is 0, and it asks none.

**Operator command** (expected runtime ~5 to 12 min the first time this build reports the caselist, a
few minutes after: the plan-text and analytic-text caches hold only `2026.10.20-docx-6` readings, so
the first report on this build reads every on-topic source again, and a dry run keeps none of it; the
analytic texts' first fill took 551 s on 2026-10-24)
Where: your Mac, in the same window
```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif [ ! -d "$COPY" ]; then echo "STOP: no copy at ${COPY}"; else aws sso login --profile debate-dev-evidence && cd "$HOME" && caffeinate -i env DEBATE_ENV=dev debate-research --json landscape report --caselist "$CASELIST" --restored-copy "$COPY" --model-mode none --publish --dry-run > /tmp/landscape-dry-run.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); d = e.get("data") or (e.get("error") or {}).get("details") or {}; c = d.get("counts") or {}; m = (d.get("classification") or {}).get("model") or {}; s = d.get("scan") or {}; print("code", (e.get("error") or {}).get("code")); print("snapshot", d.get("snapshot"), "parsed_version", d.get("parsed_version"), "stale", (d.get("staleness") or {}).get("stale")); print("sources", c.get("sources"), "cards", c.get("cards"), "counted", c.get("cards_counted"), "positions", c.get("positions")); print("would_ask", m.get("would_ask"), "held_back", m.get("held_back"), "model_calls", d.get("model_calls")); print("scan_hits", len(s.get("hits") or []), "not_yet_accepted", s.get("not_yet_accepted"), "digest", s.get("digest")); print("planned", [one["action"] for one in (d.get("publish") or {}).get("planned") or []])' /tmp/landscape-dry-run.json; fi
```
Success looks like:

* `exit 0` and `code None`;
* `snapshot` the newest week the cloud imported (later than `2026-10-20`), and `parsed_version`
  starting `2026.10.27-docx-7`;
* `stale False`;
* `sources`, `cards` and `counted` above zero;
* `would_ask 0`, `held_back 0` and `model_calls 0`;
* `not_yet_accepted 0`, and `planned` seven entries, each `UPLOAD` or `UNCHANGED`.

**Send the PM these lines** before the publish. They hold counts only. **Stop** on:

* `PARSED_VERSION_NOT_IN_STORE` (exit `2`): step 2 did not parse the copy. Run it.
* a `snapshot` of `2026-10-20` or earlier: the copy is not the cloud's newest week. Tell the PM.
* `stale True`: the cloud run's last record failed, or the week is old. Run the same command without
  `--json` and read the line that starts `STALE:`; tell the PM.
* `not_yet_accepted` above zero: the scan found lines no earlier publish accepted. Read them with the
  next block; they are for this terminal only, never for a report, a document, an issue or a commit.

**Operator command** (expected runtime a second)
Where: your Mac, in the same window, only when `not_yet_accepted` is above zero
```bash
python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); d = e.get("data") or (e.get("error") or {}).get("details") or {}; [print(h["file"], h["line"], h["kind"], h["text"]) for h in (d.get("scan") or {}).get("hits") or []]' /tmp/landscape-dry-run.json
```
It prints every hit, the ones accepted before among them. If no line names a team, publish with the
digest the dry run printed, in step 4's second block. If one does, stop and tell the PM that a hit names
a team, without the line.

**A model run** (`v1-e32-t06`'s LD report, never hspolicy26's proof): the same blocks, from a checkout of
`dev`, with `uv run debate-research` in place of `debate-research` and `--model-mode live` in place of
`--model-mode none`. Then `would_ask` is the number of cards the publish would send to the model and
`held_back` the number over `--max-model-items` left for a later run. The PM reads both before the
publish block runs.

## 4. Publish

The same report, written to the data directory and uploaded to `reports/landscape/<caselist>/<snapshot>/`
in the dev bucket, under the dev run lock. Only after the PM has read the dry run's lines.

**Operator command** (expected runtime about as long as the dry run, since it reads the same sources
again and keeps them this time)
Where: your Mac, in the same window
```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif [ ! -d "$COPY" ]; then echo "STOP: no copy at ${COPY}"; else aws sso login --profile debate-dev-evidence && cd "$HOME" && caffeinate -i env DEBATE_ENV=dev debate-research --json landscape report --caselist "$CASELIST" --restored-copy "$COPY" --model-mode none --publish > /tmp/landscape-publish.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); d = e.get("data") or (e.get("error") or {}).get("details") or {}; p = d.get("publish") or {}; print("code", (e.get("error") or {}).get("code")); print("snapshot", d.get("snapshot"), "model_calls", d.get("model_calls"), "cards", (d.get("counts") or {}).get("cards")); print("uploaded", len(p.get("uploaded") or []), "unchanged", len(p.get("unchanged") or []), "refused", p.get("refused"))' /tmp/landscape-publish.json; fi
```
Success looks like `exit 0`, `code None`, the dry run's `snapshot` and `cards`, `model_calls 0`, and
`uploaded` plus `unchanged` equal to 7, with `uploaded` above zero for a week not published before.
`RUN_LOCK_HELD`: a run holds the lock; wait and run this block again. `STORE_CREDENTIALS_EXPIRED`: run it
again, which signs in first. A scan refusal (exit `1`, `refused` naming the scan) means hits the dry run
did not show: read them as step 3 says, then the next block.

When the dry run found hits you read and accepted, set `DIGEST` to the digest it printed and publish with
it. It is accepted only while it is the digest of the hits this run finds:

**Operator command** (expected runtime as the block above)
Where: your Mac, in the same window
```bash
DIGEST=
if [ -z "$DIGEST" ]; then echo "STOP: set DIGEST to the dry run's digest"; elif [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif [ ! -d "$COPY" ]; then echo "STOP: no copy at ${COPY}"; else aws sso login --profile debate-dev-evidence && cd "$HOME" && caffeinate -i env DEBATE_ENV=dev debate-research --json landscape report --caselist "$CASELIST" --restored-copy "$COPY" --model-mode none --publish --accept-scan-hits "$DIGEST" > /tmp/landscape-publish.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); d = e.get("data") or (e.get("error") or {}).get("details") or {}; p = d.get("publish") or {}; print("code", (e.get("error") or {}).get("code")); print("snapshot", d.get("snapshot"), "model_calls", d.get("model_calls")); print("uploaded", len(p.get("uploaded") or []), "unchanged", len(p.get("unchanged") or []), "refused", p.get("refused"), "accepted_now", (d.get("scan") or {}).get("accepted_now"))' /tmp/landscape-publish.json; fi
```
Success is the block above's, with `accepted_now True`. The acceptance is recorded in your dev data
directory, so next week's publish stops only on new hits.

## 5. Delete the copy

After the publish, or after any stop. The copy holds raw disclosures that a removal does not reach, so it
is kept for the length of these steps and no longer
([data-use policy](../policies/caselist-data-use.md)). This also deletes this runbook's files under
`/tmp`, which can hold the scan's lines.

**Operator command** (expected runtime under a minute)
Where: your Mac, in the window that set `COPY`
```bash
case "$COPY" in "$HOME/.debate-research/landscape-copy-"*) rm -rf "$COPY" && echo "removed ${COPY}" ;; *) echo "STOP: ${COPY} is not a landscape copy" ;; esac
rm -f /tmp/landscape-restore.json /tmp/landscape-parse-dry-run.json /tmp/landscape-parse.json /tmp/landscape-dry-run.json /tmp/landscape-publish.json
ls -d "$HOME"/.debate-research/landscape-copy-* 2>/dev/null | wc -l
```
Success looks like `removed …` and then `0`: no landscape copy is left on this Mac.

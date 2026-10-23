# Session report: v1-e40-t01-cloud-run-adr

| | |
|---|---|
| Task | `v1-e40-t01-cloud-run-adr` — ADR-0020: the weekly caselist run in the cloud, its credentials and its state |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t01-cloud-run-adr.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t01-cloud-run-adr.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t01-cloud-run-adr` |
| Session status | COMPLETE. The Goal stays `InProgress`: ac1 closes on the PM's acceptance and ac2 on the coach's merge <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

[ADR-0020](../adr/0020-weekly-caselist-run-in-the-cloud.md) is written, measured first, and
`Proposed`. It decides the eight questions:

1. **Runtime.** One on-demand `arm64` Fargate task, 8 vCPU, 16 GB and 100 GiB, started by an
   EventBridge Scheduler schedule. Not Batch, not Spot, not Lambda.
2. **Credentials.** A weekly login task whose role alone reads the Tabroom password. Both secrets sit
   under one KMS key of their own, enforced by the key policy and each secret's own policy. The coach
   writes the password and never reads it back, and every read is in CloudTrail.
3. **State.** The evidence bucket is the record, and each run works on a restored copy.
4. **One runner.** A leased lock object written with S3 conditional writes, taken by every command
   that writes a bucket, with a cutover order.
5. **Configuration.** The caselists are `caselist.sync_caselists`.
6. **Alerts.** Email through SNS.
7. **Environments.** One home environment at a time: dev now, prod from the pilot's promotion.
8. **Cost and V2.** About $4.90 a month. The ADR also says what V2's E10 adopts and what E40 must
   not build.

The data-use policy is amended to version 1.12 in the same commit.

Three things to look at first:

- **Two of the brief's figures did not hold when measured.** A full re-parse takes 33 to 40 minutes
  on the Mac, not hours. The "14 GB" was the parsed store while it held two version directories.
- **The policy amendment goes beyond item 3.** The cloud run is otherwise still forbidden, by gate
  item 8 and by the list of places personal data may live.
- **The ADR proposes changes to the specs of `t02` to `t06`.** Question 2 and question 3 in the PM
  block below cover the two that matter most.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `adr` — ADR-0020 | Done | Measured (below), then wrote the ADR, its index row and policy 1.12. Its criterion passes |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `adr`: "Docs checks pass" (`uv run pytest tests/docs`) | PASS | `uv run pytest -q tests/docs tests/architecture/test_single_interpreter_source.py` → `74 passed in 3.16s` |
| ac1 — ADR-0020 decides the eight questions, each with its measured figure or the reason none applies, and is accepted by the PM | NOT RUN | The eight questions are decided in the ADR's sections (1) to (8). Each figure is measured, read from a dated price page, or marked *estimate* with its reason. **Acceptance is the PM's.** The ADR is `Proposed` until then (ADR README, step 5) |
| ac2 — the data-use policy's access rule is amended for the cloud run and approved by the coach in the same pull request | NOT RUN | Policy version 1.12: E34 gate items 3 and 8, the places personal data may live, Prohibited use 10, the dev exception's locations, Retention and Removal, and the Approval section's note and table. **The coach's approval is the merge of this pull request**, per the brief |

Both open criteria are sign-offs no session can give, so the Goal is left `InProgress`.

## What was measured, and how

Every figure in the ADR's "What was measured" came from these reads. All were read-only, on the
operator's Mac, on 2026-10-22, and each finished in seconds (working agreement 2). They printed
counts, sizes and times only: no school, team code, path or file name.

| Figure | Source | Command (shape) | Runtime |
|---|---|---|---|
| Run `20261022T052044Z`: 9,585.6 s, its counts and its stage reasons | `<data_dir>/caselist-sync-runs.jsonl`, `caselist-sync-run-details.jsonl`, `caselist-sync-runs/20261022T052044Z.json` | `tail -1 … \| python3 -c 'json…'` printing keys and the `stages` list | 0.07 s |
| No stage timing in the record, details or logs | The same files, and `~/Library/Logs/debate-research/caselist-sync.err.log` | Key listing, `cat` of the 18-line error log | under 1 s |
| Stage bounds | Modification times in the data directory, grouped by area, inside 05:20–08:01Z | A `python3` heredoc walking `os.walk` and printing area, first and last time, count | 1.4 s |
| The aggregates were rewritten at 19:47–20:10 local | `stat` of `parsed/*/2026.10.20-docx-6/*.jsonl` | `stat -f '%Sm %z %N'` | under 1 s |
| Store size by area | `du -sk`, then `find … -type f` counts and the sum of `stat -f %z` | — | 0.9 s |
| Index sizes and documents | `tub-index/*/manifest.json` (`counts`, `sqlite_file`, `gzip_object`) | `python3 -c 'json.load…'` | under 1 s |
| Database contents | `debate.sqlite3`, opened `mode=ro`, table names and `count(*)` only | `python3 -c 'sqlite3…'` | 0.13 s |
| The Mac's cores and memory | `sysctl -n hw.ncpu hw.memsize machdep.cpu.brand_string` | — | under 1 s |
| The 205 s build, the 100 s second read, full re-parse times | [search-index.md](../data/search-index.md), [v1-e39-t12's report](v1-e39-t12-card-only-results.md), [caselist-parse-report.md](../data/caselist-parse-report.md) | Read | — |

AWS behaviour and prices were read from AWS's public documentation and pricing pages on 2026-10-22;
the ADR lists each page.

## Files changed

- `docs/adr/0020-weekly-caselist-run-in-the-cloud.md`: the new record.
- `docs/adr/README.md`: its index row (`Proposed 2026-10-22`); the next free number is now 0021.
- `docs/policies/caselist-data-use.md`: version 1.12 (see Deviation 2).
- `docs/session-reports/v1-e40-t01-cloud-run-adr.md`: this report.
- `plan_specs/v1/e40-cloud-caselist-run/t01-cloud-run-adr.yaml`: unchanged by this session beyond
  the `InProgress` the start commit set.

## Deviations from the spec

1. **Two of the brief's figures, corrected by measurement** (working agreement 7).
   - **A full re-parse is not multi-hour on the Mac.** It took 1,970 s on 2026-10-16 and 2,423 s
     on 2026-10-19, over 12,701 sources, including the rebuild and the publish. That is about 40 to
     50 minutes at today's 15,327 sources (*estimate*). The ADR still sizes the cloud task for one,
     because a Fargate vCPU is slower than an M3 Pro core: about 1 to 1.5 hours at 8 vCPU
     (*estimate*).
   - **The local store is about 16.8 GB, not 14.** "14 GB" was the parsed store alone on
     2026-10-21, when it held the `docx-5` and `docx-6` directories. Today the parsed store is
     9.14 GB, raw sources 4.23 GB, three index builds 3.33 GB.
   - **The index figures in the brief are the run's own build.** 839,438,336 and 314,054,035 bytes
     are `767b9c7c056b80cb` (52,059 documents). `f29b81c276dd67c5` holds 50,434 documents in
     834,973,696 bytes, 311,899,269 gzipped.
   - **The run record does not time its stages,** so the per-stage durations the brief asks for
     come from file modification times, with the bounds stated. About 1 h 53 min of the run, the
     parsed-store publish by difference, is unexplained by any record. The ADR has `t03` add stage
     start and end times.
2. **The policy amendment changes more than the access item.** The brief says version 1.12 "loosens
   nothing else". On its own, item 3 would leave the cloud run forbidden:
   - E34 gate item 8 says the job "runs on the operator's own machine".
   - A run's working copy is a new place personal data lives, outside the list in Personal data, in
     Prohibited use 10 and in the dev exception's "Two locations".

   So 1.12 also amends those, adds the run-state bundle to Retention and to what a removal rewrites,
   and says plainly in its version note that it loosens. Nothing else changes. Question 1 below.
3. **The ADR proposes changes to `t02` to `t06`.** The epic allows it ("the tasks after it may be
   amended by that ADR"). The changes are listed in the ADR's [What each E40 task builds](../adr/0020-weekly-caselist-run-in-the-cloud.md#what-each-e40-task-builds).
   No spec was edited here: they are the PM's to make. The two with scope consequences are questions
   2 and 3 below.
4. **AWS documentation and price pages were read from this session.** They are public pages, not
   the account or any system the task works on. Every price carries its date, and two tables that
   did not load (SNS, S3) were taken from AWS's own FAQ and guides, as the ADR says. No AWS call was
   made with the operator's profiles, and no call reached OpenCaselist.

## Decisions and assumptions

1. **A Fargate vCPU does about half the parse work of an M3 Pro performance core.** This is an
   assumption, not a measurement, and it sizes the task at 8 vCPU. `t03` records the first full
   parse and resizes if it is wrong. The cost is small either way: $0.32 an hour at 8 vCPU.
2. **The login runs every week and always logs in.** The alternative was to log in only when the
   token is near expiry. Weekly logins keep expiry logic out of the code, let a token revoked early
   heal itself, and make the audit trail regular: one read a week, by one role.
3. **The run-state bundle (manifests plus database) is saved only when everything it records is
   confirmed in the bucket.** A crash then costs a repeated download, never a week recorded as
   imported whose bytes died with a task. This trades a little of the 5-a-day budget for
   correctness; ADR-0017 makes a deferred week a delay.
4. **The lock fences every named-object write, not only the run's start.** A Mac that slept
   through its lease would otherwise wake and publish beside the cloud run. That is the case the
   forbidden "two runners able to publish at once" most plausibly hits.
5. **One home environment at a time.** Two scheduled runs, one per environment, would keep two
   download ledgers against one Tabroom account's 5 a day.
6. **The run's network is interim.** It uses public subnets and a public IP, because a NAT gateway
   costs more than dev's whole budget. `v2-e10-t05` forbids that shape for V2 and replaces it. The
   ADR says this rather than pre-empting ADR-0011.
7. **Charlie's two answers (2026-10-23) are recorded in the ADR, not the policy.** Tabroom's login
   never asks for more than the password, so the unattended login stands and the hand login is a
   contingency only. The maintainer has been told the downloads are likely to move to the cloud and
   is fine with it. Clause 12's terms do not depend on where the job runs, so policy 1.12 gains no
   line for it; the PM block offers one.
8. **The ADR does not edit the store layout document.** It names the new keys
   (`reports/sync/run-lock.json`, `reports/sync/state/`, `manifests/_run-state/`), all under
   existing prefixes, so no Terraform listing grant changes. `t04` writes them into the layout, as
   its packages allow.

## Questions for the PM

One block, to paste to the PM. Each question has a recommendation.

````text
PM questions from v1-e40-t01-cloud-run-adr (ADR-0020, Proposed). Please rule on 1-4; the FYIs need
no answer unless you disagree.

1. Policy 1.12 is wider than "Access item 3".
   Fact: E34 gate item 8 says the job "runs on the operator's own machine", and a cloud run holds a
   working copy of the store (team codes included) on its task's storage while it runs, a place the
   policy does not list (Personal data, Prohibited use 10, dev exception "Two locations"). Amending
   item 3 alone leaves the cloud run forbidden.
   Options: (a) 1.12 amends item 3, item 8 and those three place lists, adds the run-state bundle to
   Retention and Removal, and says it loosens (as written); (b) 1.12 amends item 3 only, and item 8
   and the places wait for a 1.13 before t06.
   Recommendation: (a). It is one decision, the coach's of 2026-10-22, and the merge records one
   approval; (b) leaves an approved policy that forbids the thing it was amended for.

2. The lock in every bucket-writing command (t04's scope).
   Fact: today only `caselist pull` and the inbox purge take a lock (a local flock). `caselist
   remove`, `caselist publish`, `caselist parse --publish`, `tub index publish` and `store sync
   --push` take none, so any of them run on the Mac during a cloud run would be a second publisher.
   t03 says the run "refuses to start while the lock is held"; no spec covers the other commands.
   Recommendation: amend t04's description to "every command that writes to an evidence bucket
   takes the bucket lock in bucket mode, renewing it before every named-object write", and add a
   forbidden entry "A command that writes to a bucket without the lock in bucket mode".

3. t06's comparison cannot be two runs of the same week.
   Fact: a second run of a week downloads its archives again (3-4 of the account's 5 a day) and
   publishes twice, which the epic forbids.
   Recommendation: amend t06 ac1 to "a dev cloud run agrees with the Mac's offline reproduction of
   its parse and index from the same inputs (records, parse counts, index document count)".

4. One home environment, moving to prod at the pilot's promotion.
   Fact: one Tabroom account, one 5-a-day cap, so one ledger and one schedule. A dev home publishing
   to prod would need a dev-named role reading prod evidence (ADR-0010 rule 4).
   Recommendation: accept ADR-0020 (7): dev is home from the cutover, prod is published by hand from
   a restored copy until promotion, then the home moves to prod and the dev bucket stops getting
   the weekly corpus. t06 already says "repeat in prod at its promotion"; its runbook names the move.

Answered by Charlie on 2026-10-23, and recorded in ADR-0020's Context:
- Tabroom's login never asks for more than the password, so t02's unattended login needs no design
  change; the hand login on the Mac stays a contingency for a future change.
- Charlie has told the OpenCaselist maintainer that the downloads are likely to move to the cloud,
  and the maintainer is fine with it. Clause 12 does not depend on where the job runs, so policy
  1.12 does not record this; say if you want a line in the clause register.

FYI (proceeding as written unless you say otherwise):
- An administrator (DebateBreakGlassAdmin, or the account's own AdministratorAccess) can still reach
  the password by first changing a key policy, a resource policy, the login role or its task
  definition. Each such change is in CloudTrail and emailed to the coach. No role can read it
  without one. I read the forbidden entry ("any role but the login job's can read the password") as
  met on that basis; ADR-0010's prod-account trigger is what removes the administrator.
- A build older than the lock, run by hand against a bucket, ignores the lock. Same class of risk
  as the runbook's "never run a build older than v0.1.0-dev.13"; the cutover replaces the Mac's
  installed build before the cloud schedule is enabled.
- No V2 task names the CaselistRepository (v2-e11-t03 lists other ports), so the run-state bundle's
  database has no V2 successor yet.
- t05's "existing mail path" is SNS email: the account has no general one (budgets use AWS's own
  email; the pilot's SES identity belongs to its pool and is in the sandbox).
- The run record has no stage times. About 1 h 53 min of the 2026-10-22 run (the parsed-store
  publish, by difference) is unexplained. ADR-0020 has t03 add stage start and end times.
- t12's "second read compaction" note: not needed for sizing. The 305 s build is about 5% of a
  cloud run (estimate).

Reply with a ruling on 1-4 (a letter or "as recommended").
````

## Operator follow-ups

Nothing has to run for this task. The merge is the coach's approval of policy 1.12 (ac2), after the
PM's review. One optional read helps `t02`: the stored token's lifetime. It reads the keychain on
the Mac, makes no network call and prints no token.

Where: your Mac, any directory. Expected runtime: about a second.

```bash
DEBATE_ENV=dev debate-research --json caselist auth status | jq '.data | {stored_at, expires_at, last_validated_at}'
```

Success looks like three timestamps. The gap between `stored_at` and `expires_at` is how long a
token lasts. If `expires_at` is `null`, the API gave no expiry, which is the case the weekly login
was chosen for.

## Follow-up work

- **Stage start and end times in the run's details** (E34, or `t03`). Without them the next sizing
  question is again answered from file times.
- **The parsed-store publish's 1 h 53 min** from the Mac on 2026-10-22 (E31 or E34). Worth one look
  at its per-object pattern if the cloud run's figure is also large.
- **A V2 home for the caselist records** (V2 E11). No task names the `CaselistRepository`; when one
  does, the run-state bundle holds manifests only.
- **The store layout document** gains `reports/sync/run-lock.json`, `reports/sync/state/` and
  `manifests/_run-state/` in `t04`, and `store sync` should skip `manifests/_run-state/` as it skips
  `_suppression/`.

## Checks run before the report

- **The affected set.** `uv run scripts/affected_tests.py` chose 21 of 407 test files (5.2%) from 5
  changed files. They were run as `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -q -n
  auto -m "not slow and not live" <the 21 files>` → `1079 passed, 1 warning in 35.48s`. The warning
  is the test harness's blocked-socket notice.
- `uv run pytest -q tests/docs tests/architecture/test_single_interpreter_source.py` → `74 passed`.
- `uv run scripts/check_links.py` → `OK: 2072 relative links and anchors in 310 Markdown files`.
- `uv run scripts/check_command_blocks.py` → `OK: no # comments in 352 shell code blocks`.
- `uv run python scripts/docs_index.py --check-descriptions` → `All 43 indexed documents under
  docs/ have a description`.
- `uv run ruff format --check .` → `1130 files already formatted`. `uv run ruff check .` → `All
  checks passed!`. `uv run lint-imports` → `15 kept, 0 broken`.
- Pyright: not run. No Python changed, so there is no changed package to check.
- `uv run scripts/validate_specs.py` → `OK: 426 files, 40 epics, 364 tasks, 22 releases`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED, with conditions closed in-session
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-23

**Notes:**

A strong record. It was measured first, and two of my own figures were corrected by it: the re-parse
is 33 to 40 minutes on the Mac, not hours, and the 14 GB was two parsed versions at once. Every
price carries its date, and the estimates are labelled. The credential design meets the forbidden
entry as the coach set it. The lock that fences every named-object write, not only the run's
start, is the right reading of "two runners able to publish at once". **ADR-0020 is accepted**
(ac1).

**Rulings**

1. **(a).** Version 1.12 amends item 3, item 8 and the three place lists, adds the run-state bundle
   to Retention and Removal, and says plainly that it loosens. It is one decision, and the merge
   records one approval. The PM will tell the coach, before he merges, that this merge approves a
   loosening.
2. **As recommended.** Every command that writes to an evidence bucket takes the bucket lock in
   bucket mode, renewing it before every named-object write. Add the forbidden entry with it.
3. **As recommended.** t06 ac1 becomes the Mac's offline reproduction of a dev cloud run's parse
   and index from the same inputs.
4. **As recommended:** ADR-0020 (7).

The FYIs are accepted as written, including the administrator reading of the forbidden entry, on
the condition below.

**Conditions, to close in this session before the PR:**

1. **Make the ADR's changes to the t02 to t06 specs here,** each marked `PM amendment 2026-10-23
   (ADR-0020)`, from its table "What each E40 task builds":
   * t02: the writer permission set, `set-password`, and the weekly login three hours before the
     run.
   * t03: each stage's start and end in the run's details, and the 70% storage warning.
   * t04: ruling 2's wording in its description and the new forbidden entry, plus the store layout
     document's three new keys, and `store sync` skipping `manifests/_run-state/`.
   * t05: the CloudTrail rules on the credentials, and SNS as the mail path.
   * t06: ruling 3's ac1, and the move of the home at promotion.

   The epic allows the ADR to amend them, and you hold the detail. Run `validate_specs.py` after.
2. **Set ADR-0020 to `Accepted`, 2026-10-23, by the PM,** with its README index row.
3. **Say the administrator caveat in the policy itself,** in one sentence under item 3, so the
   coach approves knowingly: an administrator of the account can reach the password only by a
   change that CloudTrail records and that emails the coach, and a separate prod account would end
   that.
4. **Add one dated line to clause 12 of the clause register:** the coach told the maintainer on
   2026-10-23 that the downloads are likely to move to the cloud, and the maintainer is fine with
   it. It loosens nothing and sits inside 1.12.
5. **Set the Goal to `Succeeded`.** ac2 completes on the merge, as for every earlier policy
   version. Update the stale parts of this report. No re-review is needed.

**The PR:** opened without `--partial`. The optional token-lifetime read is welcome before t02
starts, and is not needed for this merge.

**Follow-up work:** stage times are now t03's (condition 1). The parsed-store publish's 1 h 53 min
is recorded, and is looked at once t03's stage times show the cloud figure. The V2 home for the
caselist records is recorded for V2 E11. The store layout's keys are t04's (condition 1).

If anything comes out differently, stop and ask for another review.

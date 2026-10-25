# Session report: v1-e40-t04-run-state-on-s3

| | |
|---|---|
| Task | `v1-e40-t04-run-state-on-s3` — A cloud run keeps its state in the evidence bucket |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t04-run-state-on-s3.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t04-run-state-on-s3.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t04-run-state-on-s3` |
| Session status | IN PROGRESS: stopped for the PM's ruling on the plan <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The PM asked for a plan before any code, then a stop (PM context, 2026-10-24). This report holds
that plan. No code, test or Terraform has changed yet. The plan is under
[Plan for the PM's ruling](#plan-for-the-pms-ruling) and the questions are in one paste-ready block
under [Questions for the PM](#questions-for-the-pm).

Three findings the PM should read first:

1. **No principal needs a new IAM grant.** The run role and the operator get everything bucket mode
   does from the EvidenceOperator document they share: the lock's conditional writes, the state
   files, the bundle, the parsed-store restore and the raw fetch. The removal credential's purge of
   the bundle's noncurrent versions is already inside its `manifests/` grants, and the removal
   writes the bundle and the lock through the everyday profile, as it writes rewritten manifests
   today. So nothing goes into `operator_policy_json`, and the run role gets no inline policy.
2. **The run's task definition does not set bucket mode.** `DEBATE_CASELIST__RUN_STATE=bucket` has
   to go into `infrastructure/modules/caselist_run/run_task.tf`, which is outside this task's
   `constraints.packages` (only the module's `tests/` is in). Question 1.
3. **Two bucket-writing commands are missing from ADR-0020 (4)'s list:** `caselist retire --bucket`
   (it writes object tags) and `landscape report --publish`. The spec's forbidden list covers every
   command that writes a bucket, so the plan gives both the lock. Question 2.

The run-state bundle measures **9,882,693 bytes gzipped** (61.5 MB raw). Restoring today's state is
dominated by the parsed store's 9.14 GB in 15,344 objects. Its local cost is small: hashing every
file took 12.7 s on the Mac and decompressing the bundle 0.74 s. The transfer time needs AWS, so it
is an estimate here (see [Measurements](#measurements-read-only-on-the-operators-mac-2026-10-24)).

## Plan for the PM's ruling

### What is added or changed

Everything below is in `debate_core.application`, `debate_core.integrations` and `debate_cli`. New
logic goes into new modules, not into `caselist_sync.py`, which is a hub module and would widen the
affected test set. Only thin wiring touches it.

**1. Bucket mode: a setting.** `caselist.run_state`, `"local"` (the default) or `"bucket"`, in
`CaselistSettings`. `config show` and `doctor` show it. Nothing in the bundled profiles changes;
until `v1-e40-t06` only the cloud task's environment sets it.

**2. The lock and its lease** (`application/caselist/run_lock.py`, with a port for a conditional
object and an S3 adapter in `integrations/s3/`). This is ADR-0020 (4) exactly:

* The lock is `reports/sync/run-lock.json`, with the ADR's body. `holder.kind` is `cloud` in ECS and
  `mac` otherwise. `moved` is reserved for t06.
* **Never start without a lock object.** Existence is answered by listing the prefix
  `reports/sync/run-lock.json`, which the everyday grant allows. A `GetObject` of a missing key
  under a prefix-conditioned `ListBucket` answers 403, not 404, as the removal found on 2026-10-01.
  So "absent" and "cannot read" are told apart, and both refuse: `RUN_STATE_NOT_SEEDED`, or the
  existing expired-session failure. Nothing is restored and nothing is written.
* **Taking it:** read the body and its ETag. Refuse when `home_environment` is not this environment
  (`RUN_LOCK_WRONG_HOME`). When the lock is `free`, or `held` with `lease_expires_at` more than five
  minutes past, write the new holder with `If-Match`. A `412` means another runner moved first, and
  this one stops.
* **A live lease held by another runner:** a refused second runner ends `skipped`, with the holder's
  run id and lease in its notification. It writes its record locally only, as ADR-0020 (4) says.
* **Takeover:** a lease expired past the skew margin is taken automatically. The new body records
  `took_over_from`, and the run's details, its summary and its notification say "took over an
  expired lease from run X, expired at T". The record's own schema is frozen (`sync_runs.py`), so
  this goes in the details and the notification text, not in a new record field.
* **The lease:** 30 minutes, renewed every 5 by a background thread with `If-Match` on the ETag it
  last wrote, using the injected clock.
* **Fencing:** one chokepoint, a botocore `before-call` handler registered on every S3 client the
  CLI container builds in bucket mode, the everyday client and the removal client alike. Before
  each write it checks the lease. A write is a `PutObject`, `CompleteMultipartUpload`, `CopyObject`,
  `PutObjectTagging`, `DeleteObject` or `DeleteObjects`. For a named key, the handler renews first.
  For a content-addressed key (`raw/.../sha256/...`), it only checks that the lease is not lost.
  With no lease held in bucket mode, the write is refused. So a command that forgets to take the
  lock fails closed instead of writing unfenced.
* **Renewal cost:** concurrent writers that are waiting share one in-flight renewal, but only one
  that started after their request. That keeps "renewed before every named-object write" true
  without one serial conditional PUT per parsed file (question 5).
* **Lock lost** (a renewal gets `412` or `404`): every later write is refused. The run ends with the
  code `RUN_LOCK_LOST`, writes its record locally only, saves nothing to the bucket, and is notified.
  Under v1-e34-t32's rule, a RUN_LOCK_LOST run reads stale until the record of the run that took
  over lands. The PM noted this is acceptable, and this report records it.
* **Release:** write `state: free` with `If-Match`. The lock is never deleted.
* **Who takes it in bucket mode:**
  * `caselist pull` (every non-dry mode)
  * `caselist publish`
  * `caselist parse --publish`, including `--publish-only`
  * `caselist remove --execute`
  * `caselist unsuppress`
  * `caselist retire --bucket --execute`, and `--restore`
  * `landscape report --publish`
  * `tub index publish`
  * `store sync --push`
  * the seed (item 6), which creates the lock

  A dry run reads and takes nothing. The local `flock` stays.
* **A guard against a new command slipping through:** a test enumerates every registered Typer
  command and requires each to be classified as bucket-writing or not.

**3. The restore** (`application/caselist/run_state.py`; `parsed_restore.py` for the parsed store).
It runs after the lock is taken, before the select stage. A dry run restores the bundle and state
files only, without the lock, and never the parsed store.

* **Run-state bundle.** Download it, check it against the publisher's recorded SHA-256, and unpack
  it into a staging directory under the data directory. Then ask the publisher's own withholding
  rule (`withheld_manifest_reason`, the callable `store sync --push` uses, through the same
  `WithheldManifests` type) about each manifest in it. If any is withheld, the run refuses with the
  publisher's message and installs nothing. There is no second copy of the rule. Otherwise it
  replaces `objects/manifests/` and `debate.sqlite3` by rename.
* **State files** under `reports/sync/state/`: list the prefix, then fetch what is there. A file the
  bucket does not hold is one the Mac never wrote, and is treated as the local code treats a missing
  file today.
* **Suppression list:** reconcile the local copy from the bucket's, as the search index stage
  already does, before anything imports.
* **Published index:** fetch `current.json` and that build's `manifest.json` into
  `tub-index/<id>/manifest.json`. The stage keeps the newest local index current when the digests
  match and nothing is published. For a manifest-only directory I make two rules explicit, by test:
  it is never published from, and a changed digest rebuilds. Without a gzip object it cannot be
  published, so the gzip object is not restored (question 6).
* **Parsed store:** list `parsed/<caselist>/<version>/` for each configured caselist and `openev`,
  with the version this build's parser and profile versions name. Download each object, and check
  the bytes against the SHA-256 in the object's metadata, which `GetObject` returns. A mismatch
  stops the run (`RESTORE_DIGEST_MISMATCH`). On the Mac, a file whose local SHA-256 already matches
  is skipped after a `HeadObject`. The restore never writes `parsed/` in the bucket. A version the
  bucket does not hold is a full parse.
* **Raw sources on demand:** in bucket mode the parse's blob store reads through to `raw/` for a
  digest it lacks. The key is the digest, so the check is the key itself. It writes the fetched
  bytes into `blobs/`. The publish plan already verifies a source the bucket lists before asking
  for local bytes (`publish_plan.py:775`), and the importer re-stores bytes it does not hold, so
  an empty `blobs/` needs no other change.

**4. The save** (`run_state.py`):

* **State files**, each written as ADR-0020 (3)'s table says:
  * the download ledger before each download starts, as the local file is written today;
  * the OpenEv deliveries file when an import completes;
  * the pending-work file whenever the local copy is written;
  * the run log and details at the end of the run. Their records are still published to
    `reports/sync-runs/` and `reports/sync-run-details/` as today.
* **The bundle**, saved only when both checks pass:
  * every local manifest is in the bucket with the same SHA-256 (about 50 `HeadObject` calls);
  * no local manifest is one the publisher withholds (the same callable).

  It is attempted after a publish stage that confirmed everything, and at the end of the run.
  Otherwise the previous bundle stays, and the summary says why. The database is copied with
  SQLite's online backup API, not tarred live, because the agent's database has a WAL. The key is
  `manifests/_run-state/run-state.tar.gz`, which holds no school, team code or file name.

**5. SIGTERM** (from t03's follow-up). The CLI installs a SIGTERM handler for `caselist pull`, and
for every other bucket-writing command in bucket mode. The handler cancels the run's task. The
cancellation becomes `RunTerminated` (`RUN_TERMINATED`), which unwinds through `SyncRunMonitor`, so
a failed record is written. In the remaining time the run then:

1. saves the state files;
2. saves the bundle, only if item 4's checks pass;
3. publishes the record and details;
4. releases the lock.

It has an internal 90-second budget inside ECS's 120 seconds. When the budget runs out, the bundle
is the first thing skipped, and the release is always attempted. A hard kill (SIGKILL, or the second
signal from `timeout`) skips all of this. The lease then expires, and the next run takes over with
the message above.

**6. The seed:** `debate-research caselist seed-run-state`. It is a dry run by default. With
`--execute` it seeds, and prod also needs `--confirm-prod`. It refuses unless every local manifest
is confirmed in the bucket and none is withheld (the save's two checks). Then it:

1. creates the lock with `If-None-Match: *` and takes it, so a bucket already seeded refuses;
2. uploads the bundle and the five state files;
3. checks each one back against its SHA-256;
4. releases the lock.

It is built and tested here, never run in this session. Its two runbook blocks follow working
agreement 11: a dry run, then `--execute`.

**7. The removal** (`removal_service.py`). In bucket mode `caselist remove --execute` restores the
working copy under the lock. It then runs as today, and after the local records step it:

1. rebuilds the bundle from the rewritten manifests and database;
2. writes it with the everyday profile;
3. confirms it: a `HeadObject` shows the new version is current and its recorded SHA-256 is the
   local digest;
4. only then lists `manifests/_run-state/` versions with the removal credential and deletes every
   noncurrent one.

An unconfirmed rewrite purges nothing and ends `INCOMPLETE`, and running it again finishes it. The
removal log's scope records the bundle's new version. The runbook's removal page gains the step.

**8. store sync and the layout document.** `store sync` skips `manifests/_run-state/` as it skips
`manifests/_suppression/`, with a new skip reason. `docs/architecture/evidence-store-layout.md`
gains three prefixes:

* `reports/sync/run-lock.json` (no personal data, never deleted);
* `reports/sync/state/` (no personal data);
* `manifests/_run-state/` (personal data, removal-reachable).

**9. Terraform** (question 1). `run_task.tf` gains `DEBATE_CASELIST__RUN_STATE=bucket`. A new test
run, `the_run_role_never_deletes`, covers every inline policy the exclusive set names. It matches
IAM wildcards too (`s3:Delete*`, `s3:*Object*`), not only the literal names t03's assertion lists.
Its red run is against a mutated `roles.tf`: an extra run-role statement, which the variable's
validation cannot see. No apply from the branch. The change merges `--partial`, and the PM reads
the plan of the new task definition revision.

### IAM: what each principal needs, and holds today

| Principal | Bucket mode needs | Granted today by | New grant |
|---|---|---|---|
| Run role (`debate-<env>-caselist-run`) | List `reports/sync/run-lock.json`, `reports/sync/state/`, `parsed/<c>/<v>/` | `ListDocumentedEvidencePrefixes` (`reports/*`, `parsed/*`) | None |
| | Get and conditional Put of the lock; Get and Put of the state files and the bundle | `ReadAndPublishEvidenceObjects` (`s3:GetObject`, `s3:PutObject` on `<bucket>/*`); `If-Match` and `If-None-Match` need no other action | None |
| | Get `raw/`, `parsed/`, `reports/tub/search/` | The same statement | None |
| | Use the evidence key | `UseEvidenceKey` | None |
| Operator (`Debate<Env>EvidenceOperator`): seed, fallback week, the removal's everyday half | The same as the run role | The same document | None |
| Removal (`Debate<Env>EvidenceRemoval`) | List versions under `manifests/_run-state/` | `ListEvidenceObjectVersionsForTakedown` (`manifests/*`) | None |
| | Delete the bundle's noncurrent versions | `DeleteDisclosedMaterialOnRequest` (`s3:DeleteObjectVersion`, `s3:GetObjectVersion` on `manifests/*`) | None |
| | Read and write the bundle and the lock | Not needed: the everyday profile does both, as it writes rewritten manifests today | None |

The run role never gets `s3:DeleteObject` or `s3:DeleteObjectVersion`, and gets no inline policy.
One option that is not in this task's packages: a bucket-policy deny on a `PutObject` of
`reports/sync/run-lock.json` without `s3:if-match` or `s3:if-none-match`. That would make every
lock write conditional at the bucket. It belongs to the evidence bucket module, so it is listed
under follow-up work.

### Measurements, read-only on the operator's Mac, 2026-10-24

Taken from `~/.debate-research/dev`. Another session's work had the Mac at load 8.8 to 10.2 on 11
cores, so the times run high. Nothing was written to the data directory or kept: the tar streams
went to `wc`, and the hashing script printed counts only.

| What | Command | Result | Time |
|---|---|---|---|
| Manifests | `find objects/manifests -type f`, sizes summed | 50 files, 18,655,784 bytes | under 1 s |
| Database | `stat` of `debate.sqlite3` (the WAL was 0 bytes) | 42,803,200 bytes | — |
| **Bundle, gzip -6** | `tar -cf - -C $D objects/manifests debate.sqlite3 \| gzip -6 \| wc -c` | **9,882,693 bytes** (manifests alone 1,933,827; the database alone 7,948,800) | 0.55 s |
| Bundle, unpacked | the same stream through `gunzip \| wc -c` | 61,624,320 bytes | 0.74 s |
| Parsed store, SHA-256 of every file | a Python `hashlib` walk over `parsed/` (script in the session scratchpad, run with `-I`) | 15,344 files, 9,140,691,684 bytes. By caselist: hsld26 6,125 files, 3.15 GB, 4.5 s; hspf26 5,237 files, 1.53 GB, 2.8 s; hspolicy26 3,872 files, 4.27 GB, 5.2 s; openev 107 files, 0.20 GB, 0.2 s; testcl26 3 files, 0 bytes | 12.7 s |

**A restore of today's state, estimated.** The bundle, the state files and the index manifest take
seconds. The parsed store's transfer is the cost, and it cannot be measured without AWS reads,
which are the operator's.

* **In region, the cloud run** (*estimate*): 15,344 GETs moving 9.14 GB. At 100 MB/s with 16 to 32
  concurrent requests, that is about 3 to 6 minutes, with the hash check overlapped. ADR-0020 said
  under 10.
* **From the Mac, a fallback week** (*estimate*): about 12 minutes at 100 Mbit/s and about 4
  minutes at 300 Mbit/s, depending on the home connection.

The cloud figure is measured by the first bucket-mode run. The restore's start and end go into the
run's details, beside t03's stage times. They do not become a new `SyncStage`: the record's stage
list is read by installed builds, and an unknown stage name would make them skip the record.
Question 7 offers a hand-off that times the Mac figure now.

### Tests (offline: moto 5.2.3 for S3)

moto here answers `If-Match` with `412`, a missing key under `If-Match` with `404`, and
`If-None-Match: *` with `412` on `PutObject` and `CompleteMultipartUpload`. I read this in
`moto/s3/responses.py`. The tests:

* **ac1:** a run on an empty data directory against a seeded moto bucket. Its parse counts, its
  parsed files' digests and the index's document count and digests equal those of the same run on
  a full directory. Run separately, a full re-parse fetches raw on demand.
* **ac2:** a fault injector that "kills" the run after each stage, and after the Nth bucket write
  inside the publish, parse and index stages. From the bucket's side, a dropped process is all
  later writes failing and no cleanup running. Each kill is followed by a fresh run on an empty
  directory with the clock past the lease. That run must take over, complete, and leave a bucket
  that store status, `caselist status` and the index pointer read as whole. The same matrix runs
  for SIGTERM: the handler path saves, records `failed` and releases. One subprocess test sends a
  real SIGTERM to the CLI entry point.
* **ac3:**
  * live lease → refused, skipped, nothing written to the bucket (object versions unchanged);
  * expired lease → taken over, and the message names the old run;
  * renewal answered `412` → `RUN_LOCK_LOST`, and no bucket write after it;
  * no lock object → refused before any restore;
  * wrong home → refused;
  * one parametrised test per bucket-writing command: the lock versions show held, then free, and
    a held lock refuses the command;
  * the classification test over every registered command.
* **ac4:** a removal against moto leaves no noncurrent version of the bundle holding the removed
  rows. A fake that fails the rewrite's confirmation shows no purge, and an ordered call log shows
  the purge after the confirm. The Terraform test is `the_run_role_never_deletes`. **The red runs
  come first:** the removal test against today's removal service, which leaves the bundle alone,
  and the Terraform test against a mutated `roles.tf`. Both go in this report.
* **Mutants**, about 20 by hand under working agreement 10, in `run_lock.py`, `run_state.py` and
  the removal's purge step:
  * the lease length and renewal interval;
  * the skew margin's comparison;
  * takeover's `If-Match` dropped;
  * `took_over_from` not written;
  * the lost flag not set, or not checked by the fence;
  * a content-addressed key fenced as named, and the reverse;
  * the no-lock refusal inverted, or skipped when the listing answers 403;
  * the purge before the confirm;
  * the confirm comparing the version and not the digest;
  * the bundle saved with one manifest unconfirmed;
  * the withheld check skipped on save, and on restore.

### Order of work

1. The setting.
2. The lock: port, adapter and service, with its tests.
3. The fence on the container's S3 clients.
4. The lock taken in each command.
5. The restore.
6. The save and the bundle.
7. SIGTERM.
8. The seed.
9. The removal: red run first.
10. store sync and the layout document.
11. Terraform, after question 1: red run first.
12. The runbooks: t03's step 8 gains the seed before it, and the removal runbook gains the bundle.
13. Mutants.
14. The affected set, ruff, pyright, lint-imports, `check_thin_handlers.py`, validate_specs.

## Questions for the PM

Paste-ready, one block, each with my recommendation.

```text
v1-e40-t04 questions (session report: docs/session-reports/v1-e40-t04-run-state-on-s3.md, "Plan for the PM's ruling")

1. Bucket mode in the task definition. ADR-0020 (5) puts bucket mode in the run task's environment,
   but run_task.tf is outside constraints.packages (only infrastructure/modules/caselist_run/tests
   is in). Recommend: amend packages to add infrastructure/modules/caselist_run, for one line
   (DEBATE_CASELIST__RUN_STATE=bucket) and its test assertion. Merge --partial. You read the plan
   (expect the run task definition replaced and the run schedule repointed), applied after the
   seed. No new IAM grant anywhere (the report's IAM table), so no policy changes.

2. Two more bucket-writing commands. ADR-0020 (4)'s list leaves out `caselist retire --bucket`
   (--execute and --restore write object tags) and `landscape report --publish`. The forbidden
   list says no command writes a bucket without the lock in bucket mode. Recommend: both take the
   lock, and the ADR's list gains them in your next batch.

3. A local-mode Mac on a seeded bucket. Between the seed and t06, a Mac in local mode that pulls
   would download against a ledger the bucket does not share and publish from state older than the
   bucket's. Recommend two things:
   (a) in local mode, a bucket-writing command with a session refuses once the bucket holds a lock
       object ("this bucket keeps its run state; set caselist.run_state = bucket"). With no lock
       object, nothing changes;
   (b) the seed runs only after the Mac's agent is unloaded (ADR-0020 (4) cutover step 3). So the
       seed is t06's step 4, and t03's step 8 (the first bucket-mode run) follows it.
   This also settles the removal: once seeded, a removal always runs in bucket mode and rewrites
   the bundle.

4. The seed's name and shape: `debate-research caselist seed-run-state`, a dry run by default,
   `--execute` to seed, `--confirm-prod` in prod. It refuses unless every local manifest is
   confirmed in the bucket and none is withheld. Recommend as named.

5. Fencing's cost. "Renewed before every named-object write" over about 2,700 parsed-store and
   manifest writes a run is about 2,700 conditional PUTs, serial by ETag. Recommend: writers waiting
   at the same moment share one renewal, but only one that started after their request. Each write
   is then still preceded by a confirmed renewal. Recommend yes.

6. The index stage's restore. It compares digests with the newest local index's manifest, so a
   restored tub-index/<id>/manifest.json is enough. The gzip object (312 MB) is not restored. A
   manifest-only directory is never published from, and a changed digest rebuilds (about 305 s).
   Recommend as planned.

7. Restore timing. The cloud figure comes from the first bucket-mode run's restore times, in its
   details. If you want the Mac's fallback-week figure now, it is a one-block hand-off: time a
   download of parsed/hspf26/<version>/ (5,237 objects, 1.53 GB) into a directory under the data
   directory, then remove that directory. Recommend: skip it, since the fallback week is rare and
   its time is the home connection's.
```

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `state` — Run state on S3 | NOT STARTED | Waiting on the PM's ruling on the plan |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — empty directory restores and matches a full one | NOT RUN | Not built yet |
| ac2 — killed at each stage leaves the bucket readable | NOT RUN | Not built yet |
| ac3 — lease, takeover, RUN_LOCK_LOST, every command takes the lock | NOT RUN | Not built yet |
| ac4 — removal purges after confirm; run role has no delete; red runs first | NOT RUN | Not built yet |
| Node `state`: `uv run pytest packages/debate_core/tests/application -k caselist_sync` | NOT RUN | Not built yet |

## Files changed

* `docs/session-reports/v1-e40-t04-run-state-on-s3.md`: this plan.

## Deviations from the spec

None yet. Questions 1 and 2 would each be one if ruled as recommended: the packages amendment, and
two commands beyond ADR-0020 (4)'s list.

## Decisions and assumptions

* The record's schema is frozen (`sync_runs.py`), so `RUN_LOCK_LOST`, `RUN_TERMINATED`, the
  takeover and the restore's times go into the run's details, codes and notification. The record
  gains nothing.
* The restore replaces the local manifests and database by rename. A seeded bucket is the record
  (ADR-0020 (3)), so the working copy follows it one way.

## Operator follow-ups

None yet. The seed, the Terraform apply and t03's step 8 follow the PM's ruling and the merge,
block by block.

## Follow-up work

* **Evidence bucket module (outside this task):** optionally, a bucket-policy deny on a `PutObject`
  of `reports/sync/run-lock.json` without `s3:if-match` or `s3:if-none-match`, so the bucket itself
  refuses an unconditional lock write.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

# Session report: v1-e29-t09-store-error-loose-ends

| | |
|---|---|
| Task | `v1-e29-t09-store-error-loose-ends` — Loose ends in how store errors are classified, worded and wrapped |
| Spec | [`plan_specs/v1/e29-cloud-evidence-store/t09-store-error-loose-ends.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t09-store-error-loose-ends.yaml) |
| Epic / release | `v1-e29-cloud-evidence-store` / `v1.1` |
| Branch | `task/v1-e29-t09-store-error-loose-ends` |
| Session status | COMPLETE |

## Summary

All nine loose ends are closed and every acceptance criterion passed, so the Goal is `Succeeded`.
Each fix was first shown by a test that failed on the unchanged code. In summary:

* A missing profile now ends `store sync`, `caselist publish` and the parsed-store publish at the
  first object, as an expired session does. The pull's parse stage stops offering caselists to the
  bucket after the first one that meets it.
* A credential fault now has its own sentence.
* The listing hint is now limited to listings of the bucket root.
* A takedown preflight failure now carries its cause's code and fields in `error.details`.
* A passing preflight now deletes the probes that earlier preflights left.
* `doctor` now says when an everyday profile is signed in as the other environment's permission set.
* The caller-identity question now gives up after 10 seconds.
* An `OSError` is now reported by its class and errno, never its text, on all four routes.

The PM should look first at two choices, both under Decisions:

* How "older than its own probe" is decided: by call order, not by clock.
* What a sweep that fails does: it fails the preflight.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `store-error-loose-ends` (Store error loose ends fixed) | Done | All seven Goal criteria and the node criterion pass. Commits: one per item, in spec order. |

## Acceptance criteria

The fail-first runs used `-p no:randomly`. The before and after outputs were kept in the session's
scratchpad and are quoted below.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the three services re-raise `StoreProfileNotConfigured` as they do an expired session, and a pull's parse stage stops at the first caselist that meets it, each shown failing first | PASS | **Before the fix:** `uv run pytest -k "profile_the_aws_config_lacks or profile_is_not_defined"` over `test_evidence_sync.py`, `test_publish_service.py`, `test_caselist_parse.py` and `test_pull_parses_new_sources.py` gave **4 failed**. Three were `DID NOT RAISE StoreProfileNotConfigured`. The parse stage's failure showed both caselists offered to the bucket: `Left contains one more item: ('publish', 'openev')`. **After:** the same four files gave **145 passed**. |
| ac2: a credential fault gets a sentence of its own, and a keyless `AccessDenied` from a call that is not a listing does not get the listing hint, by test | PASS | **Before:** `test_s3_error_mapping.py` gave **6 failed, 41 passed**. The failures were credential faults told "lacks a grant", and the keyless `GetCallerIdentity`, `CreateSession` and `GetObject` given the listing hint. **After:** `uv run pytest packages/debate_core/tests/integrations/s3/` gave **132 passed**. |
| ac3: `TakedownPreflightFailed` carries its cause's code and details in the JSON envelope, by test, with the exit unchanged | PASS | **Before:** 5 failed. These were three `test_output.py` cases (expired session, then exit 3; missing profile, then exit 1; outage, then exit 3) and two real-composition-root envelopes in `test_missing_profile_and_missing_grant.py` (wrapped missing profile, then exit 1; everyday role, then exit 1). **After:** with `test_recorded_failure_codes.py` and `test_takedown_preflight_identity.py` added to the run, **157 passed**. The envelope now reads `"cause_code": "STORE_PROFILE_NOT_CONFIGURED", "cause_profile": …, "cause_setting": "DEBATE_REMOVAL_PROFILE"`. |
| ac4: the runbook says `unsuppress` runs the same preflight; a passing preflight deletes any version under `manifests/_suppression/preflight/` older than its own probe, with the takedown profile, by test against moto; the by-hand section says when it is still needed | PASS | **Before:** the new `test_preflight_sweeps_earlier_probes.py` gave **4 failed, 2 passed**. The 2 that passed are controls: nothing left to sweep, and the everyday profile deletes nothing. **After:** `uv run pytest packages/debate_core/tests -k "removal or preflight"` gave **321 passed**. Runbook: in `caselist-removal.md`, step 5 now names `unsuppress --execute`, and "A probe a preflight left behind" gained "The next takedown removes it" and "Remove one by hand only when". `scripts/check_links.py` OK; `scripts/check_command_blocks.py` OK. |
| ac5: `doctor --evidence-profiles` says when an everyday profile is signed in as the other environment's permission set, without failing the check, by test with the identity stubbed at the port | PASS | **Before:** 4 failed, 34 passed. These were three core cases (prod's operator set in dev, dev's in prod, prod's takedown set in dev) and the CLI `doctor --evidence-profiles` case. **After:** 46 passed, counting `test_runbook_reinstall_runs_the_profile_check.py`. The CLI case exits `0`, and the finding stays `defined: true`. |
| ac6: the identity question gives up after a bounded time of its own and reports that AWS did not answer, well inside `--check-launchd`'s 60 seconds, by test | PASS | **Before:** the test module could not import `IDENTITY_TIME_LIMIT_SECONDS`, because no limit existed. Behaviour: a script ran the unchanged adapter against a client that hangs 4 s, and it "waited 4.0s: as long as the client did". **After:** `test_sts_caller_identity.py` gave **24 passed**. With a 0.2 s limit the adapter raises `StoreUnavailable` ("AWS did not answer within 0.2 seconds") in under 2 s, and the profile check reports `no_answer` for both profiles in under 3 s. A test also asserts 10 s × 2 profiles ≤ 60 / 3, and reads the 60 from `install.sh`. |
| ac7: each of the four routes names a non-`DomainError` by its class and errno, never its text, with a probe path and title absent from text and JSON, each shown failing first | PASS | **Before:** 6 failed, each with the probe path in the output, e.g. `"[Errno 13] Permission denied: '/Users/zqxprobe-home/…/Zqxprobe Lantern Camp Release.docx'"`. The six were `store sync --apply`, `caselist publish` (sources), `caselist publish` (manifest), `RemovalIncomplete`, `RemovalCompletedUnlogged` and `ParsedObjectOutcome`. **After:** 6 passed; each now says `PermissionError (errno 13)`. |
| Node `store-error-loose-ends`: `uv run pytest packages/debate_core/tests -k "s3 or removal or preflight or publish"` | PASS | **729 passed in 37.03s.** |
| Whole suite (final run, as `--part K/4`) | PASS | Part 1: 1795 passed (61 s). Part 2: 1808 passed, 1 xfailed (58 s). Part 3: 1810 passed, 1 skipped (55 s). Part 4: 1801 passed, 1 xfailed (56 s). The three warnings come from the network-guard tests and are their own. |
| Static checks | PASS | Full-project `uv run --frozen pyright`: 0 errors (9.6 s). `uv run --frozen lint-imports`: 12 contracts kept, 0 broken. `ruff check` and `ruff format --check`: clean. `uv run scripts/validate_specs.py`: OK. |

## Files changed

* **`debate_core.application`**
  * `errors.py` adds two things:
    * `STORE_ERRORS_TRUE_OF_EVERY_OBJECT`, the errors that end a run over many objects.
    * `reported_error_message`, which names a class and errno and never quotes text.
  * `evidence_sync.py`, `caselist/publish_service.py` and `caselist/parsed_publish.py` re-raise
    that tuple and report a recorded failure through the helper.
  * `caselist_sync.py`: a missing profile now stops the parse stage's publishes.
  * `caselist/removal_service.py` has three changes:
    * The preflight failure carries `cause_code` and each `cause_<field>`.
    * The sweep.
    * Removal messages go through the helper.
  * `evidence_profiles.py` adds the other-environment sentence.
* **`debate_core.integrations.s3`**
  * `errors.py` adds `CREDENTIAL_FAULT_CODES`, with its own sentence, and `LISTING_OPERATIONS`,
    which scopes the listing hint.
  * `caller_identity.py` adds `IDENTITY_TIME_LIMIT_SECONDS`. The call now runs in a daemon thread
    and is waited on with a deadline.
  * `__init__.py` exports the constant.
* **Tests**
  * New: `test_preflight_sweeps_earlier_probes.py` (moto) and `debate_cli/tests/test_os_error_text_in_results.py`
    (real composition root and moto, plus the CLI handler).
  * Additions to the existing service, adapter, doctor and output tests.
  * One existing parametrization changed: `InvalidAccessKeyId` is no longer expected to say "lacks
    a grant".
  * One existing envelope expectation changed: it now includes the cause's fields.
* **`docs/runbooks`**
  * `caselist-removal.md`: step 5, and the by-hand probe section.
  * `caselist-scheduled-sync.md`: the profile-check table now covers the other-environment sentence
    and the 10-second limit.
* **Spec**: the Goal phase only.

## Deviations from the spec

None.

## Decisions and assumptions

1. **"Older than its own probe" is read from the order of the calls, not from a clock.** The
   preflight already lists `preflight/` before it writes its own probe. Whatever that listing
   finds was there first, and once its own probe is deleted and checked gone, those versions are
   deleted. S3's `LastModified` is given to the second, so a clock comparison could not order two
   probes written in the same second. A probe written after the listing is left alone; only a
   second takedown running at the same moment could write one. A test covers that case.
2. **A sweep that is refused fails the preflight.** It is the same grant the preflight has just
   proven, so a refusal means something changed. The takedown has not begun at that point. The
   message still says *nothing was deleted*, which is true of evidence. Some stale probes may
   already be gone; the error's `step` field says "delete the probes an earlier preflight left".
   Its own probe is no longer reported as left, and a test checks that.
3. **Credential faults stay `StoreAccessDenied`** (same code, same exit). Only the sentence changed,
   because the exit-code rule is out of scope. The sentence names the profile and says "renew or
   replace the credentials the profile supplies". It also still points to the grants runbook,
   which explains how profiles are added.
4. **The listing hint goes to `ListObjectsV2` and `ListObjectVersions` with no prefix.** Those are
   the only listing operations the adapters pass. A refused listing with a prefix already had a key
   and got the general sentence.
5. **The cause's facts are flat `cause_<name>` fields, not a nested object.** The CLI's `details`
   keeps scalars only, and the panel prints one line per field. The cause's own `hint` is left out,
   because it is already the envelope's `hint`.
6. **The other-environment sentence is for the everyday profile only**, as item 7 says. A takedown
   profile signed in as the other environment's removal set already reads "a takedown runs only as
   …" (Follow-up work 2).
7. **The time limit is 10 s per profile, and botocore's own timeouts are unchanged.** The question
   runs in a daemon thread. A question given up on therefore cannot hold the process at exit, as a
   thread from asyncio's own pool would (`asyncio.run` waits for those). The abandoned thread ends
   when botocore gives up. The same adapter serves the takedown preflight, so an offline takedown
   now fails after 10 s with `STORE_UNAVAILABLE`, which is exit 3, and nothing is written.
8. **`reported_error_message` says `PermissionError (errno 13)`.** It gives just the class when
   there is no errno, and a `DomainError`'s own message otherwise.
   * The error code, e.g. `PERMISSION_ERROR`, is unchanged on every route.
   * `ParsedObjectOutcome` is rendered nowhere, so its test checks the outcome and its `repr`.
   * The two removal errors are raised the way the service raises them, from an `OSError`, with a
     stand-in report, and are printed by the CLI's real handler. `test_output.py` already builds
     them this way.

### What an install now waits for when AWS is unreachable

Since `v1-e34-t24`, `ops/launchd/install.sh` runs `doctor --evidence-profiles` before it writes
anything. It runs it with only `HOME`, `PATH` and `DEBATE_ENV`, so `DEBATE_REMOVAL_PROFILE` is
unset and only the everyday profile is asked.

* **Unreachable AWS:** the install now waits **at most 10 seconds** for that question, on top of
  `doctor`'s local checks. The row then reads "defined; AWS did not answer when asked which
  permission set it is signed in as", the check exits `0`, and the install goes on.
* **`--check-launchd`:** it is the same single question under launchd, so at most 10 s of its 60.
  With both profiles configured it would be 20 s.
* **Before this task, nothing of ours bounded the wait.** With no network at all, botocore fails in
  seconds. With packets dropped, it waits for its 60-second connect timeout on each attempt it
  makes, which could pass `--check-launchd`'s 60 s and hold an install for minutes.

## Operator follow-ups

Nothing is required: every criterion was closed offline. The PM's notes route any check against a
real profile to the operator, so here is one, optional. It confirms that the profiles on this Mac
still read as before, with no new sentence. Run it in a terminal on this Mac. It takes about
5 seconds, and you need to be signed in to the dev everyday profile.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e29-t09-store-error-loose-ends
DEBATE_ENV=dev uv run debate-research doctor --evidence-profiles
```

Success: the row reads `debate-dev-evidence (storage.s3.aws_profile): defined, and signed in as
DebateDevEvidenceOperator`, and the exit status is 0. If the row says *which is prod's permission
set*, the dev profile's block in the AWS config names prod's role: paste the row back.

## Follow-up work

1. **`v1-e30-t21` and this task both touch `caselist/publish_service.py`** (E30). `dev` had not
   moved when this report was written (merge base `1261b3d`). Whichever task merges second runs
   `scripts/task sync` and keeps both changes. In this file, this task changed only:
   * the two `except` clauses that re-raise;
   * the two `str(failure)` uses, now `reported_error_message`;
   * three docstrings.
2. **A takedown profile signed in as the other environment's removal set** (E29 or E34). `doctor`
   says only that a takedown will refuse it. It could also say that the set is the other
   environment's, as it now does for the everyday profile.
3. **`caselist_sync._failure` names a non-`DomainError` by its class alone, without the errno**
   (E34). It could use `reported_error_message`, so that a stage reason and a publish result
   describe one `OSError` the same way.
4. **The STS client could be given short botocore timeouts and fewer attempts** (E29). The deadline
   already bounds what an operator waits for. Short timeouts would also end the abandoned thread
   sooner in a long-lived process. Nothing long-lived asks the question today.
5. **`ops/launchd/install.sh`'s comment on the profile check** (E34; `ops/` is outside this
   task's packages). It says the install "asks AWS one question for each profile". It could also
   say how long that question may wait.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** CHANGES_REQUESTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-16

**Notes:**

One change, to Decision 2. Everything else is accepted as it stands, and the phase stays
`InProgress` until the change is in.

**Decision 2 is the one thing to change: a refused sweep must not stop a takedown.** The preflight
exists to prove that this credential, signed in as this environment's takedown set, may write,
list and delete under `preflight/`. Its own probe proves that. Deleting the earlier probes is
housekeeping. A takedown withdraws a student's data; holding it back over leftover probes puts
the housekeeping above the duty. The case is unlikely but sticky: if an old probe version could
not be deleted for a reason particular to it, every later takedown would fail on it until someone
removed it by hand. So:

1. **A sweep that is refused, or partly refused, leaves the preflight passed.** The takedown goes
   ahead. What was not deleted is reported, as a count, in the command's output and JSON and in
   the removal log entry if it has a free-text field for it, never as a failure. Keys are fine in
   the JSON, since they are random hex under `preflight/`.
2. **Its own probe's delete still fails the preflight exactly as now.** That is the proof, and
   nothing about it changes.
3. **Tests, against moto:**
   * one earlier probe whose delete is refused while the others are deleted: the takedown
     completes, and the leftover count is 1;
   * the existing controls still hold.

   Show the new test failing first against the current code.
4. **The runbook's by-hand section** says when a sweep leaves probes: when the output reports
   some, remove them as it describes.

**What is accepted:**

* **ac1 to ac3, ac5 to ac7, and ac4's other half** (the runbook naming `unsuppress`), each shown
  failing first.
* **Decision 1, call order rather than clock,** is right. S3's second-granularity timestamps
  cannot order two probes, and the listing-before-writing order can. A version already deleted by
  a concurrent preflight is a no-op delete in S3, so the race you describe cannot fail either run.
* **Decision 7, a daemon thread under a deadline,** keeps an abandoned question from holding the
  process at exit. The test that reads the 60 seconds from `install.sh` ties the limit to the
  thing it protects.
* **"What an install now waits for"** is exactly what I asked for: at most 10 seconds for the one
  question, where before it was unbounded with packets dropped.
* **Decisions 3 to 6 and 8:** accepted.

**Follow-ups:**

* **1 (merge order with `v1-e30-t21`):** as you say. Whichever merges second syncs and keeps both.
* **2 (the takedown profile signed in as the other environment's set) and 3
  (`caselist_sync._failure` without the errno):** go in the next PM batch, E34 p3, beside
  t24's follow-ups.
* **4 (short botocore timeouts on STS):** no task while nothing long-lived asks the question.
* **5 (`install.sh`'s comment):** with t24's Follow-up 2, the next task that touches `ops/launchd`.

**Operator follow-up:** the optional `doctor --evidence-profiles` run is recorded when it comes.

## Changes after PM review (2026-10-16)

The review asked for one change, to Decision 2: a sweep that is refused, or partly refused, must
not stop a takedown. That change is made, and Decision 2 is replaced by the rule below. Everything
else stands as reviewed. The Goal is back at `InProgress` until the PM accepts.

### What changed

* **The sweep never fails the preflight.** `preflight` still deletes each earlier probe version
  with the takedown profile, but now one version per call. The S3 adapter stops a batch at its
  first refused delete, and a single refusal must not stop the deletes after it. A refused version
  is not raised: it is returned, and the takedown goes ahead.
  * The returned versions travel on `RemovalReport.preflight_probes_left` and
    `UnsuppressReport.preflight_probes_left`. These are empty when the credential was proven by an
    earlier call of the same service.
  * The `remove --execute` and `unsuppress --execute` output adds one line when any are left:
    *N probe version(s) an earlier preflight left under manifests/_suppression/preflight/ could not
    be deleted: remove them by hand (docs/runbooks/caselist-removal.md, "A probe a preflight left
    behind").*
  * `--json` always carries `data.preflight_probes_left` on an executed run: `{"versions": N,
    "keys": [...]}`, where the keys are the random-hex probe keys.
* **The preflight's own probe is unchanged.** A refused delete of it still fails the preflight, the
  error still names the probe it left, and no sweep runs. A test now pins this down.
* **The removal log entry does not carry the count.** `RemovalLogEntry` has no free-text field.
  Adding a field would also break the rule that a log line's keys are what every installed build
  reads (`test_suppression_list_is_read_by_every_build.py`). The count is in the command's output
  and JSON only.
* **The runbook (`caselist-removal.md`) changed in two places:**
  * Step 5 says the request is still carried out when the bucket refuses to delete an earlier
    probe, and gives what the output and the JSON then report.
  * "A probe a preflight left behind" has a new paragraph, "A takedown may report probes it left",
    and a first case under "Remove one by hand only when": a takedown or an un-suppress reported
    probes it could not delete.
* **Tests:**
  * The test that expected a refused sweep to fail the preflight is replaced by the PM's case: one
    earlier probe's delete refused, the other's versions and marker deleted, the takedown
    completed, and the leftover count 1. There is an un-suppress twin.
  * A new control covers the preflight's own probe being refused.
  * The control "nothing left to sweep", and the existing un-suppress sweep, now also assert an
    empty leftover count.
  * In `test_missing_profile_and_missing_grant.py`, the real-composition-root test of the takedown
    profile now asserts `{"versions": 0, "keys": []}`. Beside it, a new test runs `caselist remove
    --execute` against moto with one planted probe whose delete is refused. It asserts exit 0, the
    count and key in the JSON, the line in the text output, and that only that probe is left.

### Red, then green

Red, before the change: the new and changed tests were run against the code as reviewed.

```text
uv run pytest -q -p no:randomly packages/debate_core/tests/application/caselist/test_preflight_sweeps_earlier_probes.py
E   debate_core.application.caselist.removal_service.TakedownPreflightFailed: the takedown profile debate-dev-evidence-removal could not delete the probes an earlier preflight left (STORE_ACCE…
E   AttributeError: 'RemovalReport' object has no attribute 'preflight_probes_left'
E   AttributeError: 'UnsuppressReport' object has no attribute 'preflight_probes_left'
FAILED …::TestAPreflightThatPasses::test_an_earlier_probe_whose_delete_is_refused_is_left_and_counted_and_the_takedown_completes
FAILED …::TestAPreflightThatPasses::test_it_deletes_every_version_an_earlier_preflight_left_with_the_takedown_profile
FAILED …::TestAPreflightThatPasses::test_unsuppress_counts_an_earlier_probe_it_could_not_delete_and_appends_its_entry
FAILED …::TestAPreflightThatPasses::test_unsuppress_sweeps_the_same_way
4 failed, 4 passed in 4.46s

uv run pytest -q -p no:randomly packages/debate_cli/tests/test_missing_profile_and_missing_grant.py -k "takedown_profile_is_not_refused or earlier_probe"
E   KeyError: 'preflight_probes_left'
E   assert <ExitCode.RETRIEVAL_FAILURE: 3> == <ExitCode.OK: 0>
FAILED …::TestATakedownThatNamesTheEverydayProfile::test_the_takedown_profile_is_not_refused
FAILED …::TestATakedownThatNamesTheEverydayProfile::test_an_earlier_probe_it_may_not_delete_is_reported_and_the_takedown_goes_ahead
2 failed in 8.37s
```

* **The PM's case** (one earlier probe refused) and its un-suppress twin failed for the reason under
  review: the refused sweep raised `TakedownPreflightFailed`.
* **Through the CLI**, that same failure was exit 3 with no removal carried out.
* **The other two failures** are new assertions on a field that did not exist yet.
* **The four that passed** are the controls:
  * nothing left to sweep;
  * a probe written after the listing is kept;
  * the everyday profile deletes no earlier probe;
  * the preflight's own probe refused still fails it.

Green, after the change:

| Command | Result |
|---|---|
| The two files above | **31 passed** in 6.95 s |
| Node selector: `uv run pytest packages/debate_core/tests -k "s3 or removal or preflight or publish"` | **731 passed** in 52.17 s |
| Four-part suite, `uv run pytest --part K/4`, at load averages up to 51 | Part 1: 1796 passed (61 s). Part 2: 1808 passed, 1 xfailed (81 s). Part 3: 1810 passed, 1 skipped (77 s). Part 4: 1803 passed, 1 xfailed (65 s). |
| `uv run --frozen pyright` | 0 errors |
| `uv run --frozen lint-imports` | 12 contracts kept |
| `ruff check` and `ruff format --check` | clean |
| `scripts/check_links.py` and `scripts/check_command_blocks.py` | OK |

The three warnings in the suite are the network-guard tests' own, as before.

### ac4's evidence, restated

Unchanged:

* The runbook names `unsuppress`.
* The sweep deletes, with the takedown profile, every version the first listing found.
* The by-hand section says when it is still needed, now including when a request reports
  leftovers.

New:

* A refused earlier probe is left, counted (1 in the PM's case) and reported.
* The takedown completes.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

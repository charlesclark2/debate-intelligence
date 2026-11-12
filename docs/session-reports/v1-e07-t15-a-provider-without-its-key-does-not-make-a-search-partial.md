# Session report: v1-e07-t15-a-provider-without-its-key-does-not-make-a-search-partial

| | |
|---|---|
| Task | `v1-e07-t15-a-provider-without-its-key-does-not-make-a-search-partial` — A provider the profile enables but no key configures is named, and no longer makes every search partial |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t15-a-provider-without-its-key-does-not-make-a-search-partial.yaml`](../../plan_specs/v1/e07-discovery-adapters/t15-a-provider-without-its-key-does-not-make-a-search-partial.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t15-a-provider-without-its-key-does-not-make-a-search-partial` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Before this change, a GovInfo with no api.data.gov key made every NHI search PARTIAL (exit 6), though
no retry can ever get more from it. Now a provider that the profile enables and settings cannot build
(its key or the email missing) is handled differently. It stays in the footer, `providers`, `reasons`
and `provider_calls`, in the same order as before, and its reason ends with its cure. It is also left
out of the status. A search whose other providers answered is COMPLETE (exit 0, or 7 with no
results). A search in which nothing else answered is still FAILED. All of this is built as the PM
ruled on 2026-11-09.

The footer line is `govinfo: not configured: not counted as partial: no api.data.gov key
(DEBATE_PROVIDERS__API_DATA_GOV_KEY); get a free key at api.data.gov/signup to ask GovInfo`. A provider
named with `--providers` keeps today's rule and today's words, so it still makes the search PARTIAL.
`daily` asks its preset's providers as configuration, so `nhi` without the key is COMPLETE and exits 0.

**Look at first:**

* **The narrow reading, under Decisions.** Only a provider settings *enable* without its credential is
  left out. A preset provider the profile does not enable at all is still a missing answer (PARTIAL),
  as before. A follow-up proposal is below.
* **The rule lives in `debate_core.application`.** `FanOutStage.uncounted` decides which providers
  are left out, and `search_status(..., uncounted=)` leaves them out. The presenters only add
  `not counted as partial:` to those providers' reasons.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-provider-without-its-key-does-not-make`: Not configured is not partial | Done | Skeleton (`98e97ce`), tests shown red (`9a85e63`), the rule, the cure and the presenters (`782b99c`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a profile-enabled provider that is not configured is named with its cure and no longer makes a search partial, a search with no answer stays FAILED, and the ruled `--provider` case holds, by tests shown failing first | PASS | **Red:** against the skeleton (`98e97ce`), where every new name exists and does nothing, the new and changed tests in six files, selected with `-k "not_configured or nhi or govinfo or key_missing"`: **20 failed, 120 passed**, every failure at an assertion. The new tests that already passed describe rules that already held: the `--providers` case (ruling 2, three tests), a preset provider not enabled or off its topic, nothing answered is FAILED, and the skeleton's defaults (the `providers_named` JSON, no cure for a keyless provider). **Green:** the same selection, 140 passed; the changed files whole, **421 passed in 10.97s**. **Mutants:** 15 on the partial reckoning, each run from a fresh Hypothesis directory, all caught at assertions (list below). |
| Node: `uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "search_status or not_configured"` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "search_status or not_configured"`. Result: **64 passed in 12.95s**. Two earlier attempts were stopped at the 115-second limit during collection, under a load of about 9 to 12. The same `-k` over the 12 files a grep found to match gave 64 passed in 54.57s. A collection of each package separately chose 53 + 11 = 64 tests, the same set. |

### What the tests pin

Core, `packages/debate_core/tests/application/test_not_configured_is_not_partial.py`:

* `search_status`:
  * leaves out the `not_configured` calls of an uncounted provider, and only those: one that timed
    out, errored, was rate-limited or had its breaker open still counts;
  * an answer that was itself partial still makes the search PARTIAL;
  * nothing else answered is FAILED.
* The service, on a search with no `--providers`:
  * GovInfo, enabled without its key, is `not_configured` with the cure, `uncounted == ("govinfo",)`,
    and COMPLETE, stored COMPLETE too;
  * off its topic, GovInfo is neither asked nor named;
  * only GovInfo selected is FAILED, and so is GovInfo beside an OpenAlex that failed.
* Ruling 2: `providers=("openalex", "govinfo")` is PARTIAL, stored PARTIAL, with today's reason and
  no cure.
* Ruling 3: `providers_named=False` leaves GovInfo out. A preset naming `gdelt` (not enabled), or
  GovInfo on a topic that does not list it, is still PARTIAL.
* `missing_credential_cure`: words for the four credentialed providers, None for keyless and unknown
  ones.

Digest, `test_digest_service.py`:

* a preset provider without its credential leaves the digest COMPLETE and named, with the cure;
* the same provider beside one that failed leaves it PARTIAL.

CLI:

* `test_search_presenter_not_configured.py`:
  * the footer line;
  * the JSON's `providers` (same order, same keys, the cure in `reasons`) and `provider_calls`;
  * exit 7 with no results, with the message `every provider asked answered, …`;
  * the named case's footer, unchanged.
* `test_search_command.py`:
  * the two NHI tests t13 wrote now expect `Providers: COMPLETE`, exit 0 and the new GovInfo line;
  * a new `--providers openalex,govinfo` test: exit 6, `SEARCH_PARTIAL`, today's reason;
  * a new test with OpenAlex answering 503: exit 3, `Providers: FAILED`, GovInfo named with its cure.
* `test_daily_command.py`, the PM's test: `daily nhi` with all five preset providers enabled and no
  api.data.gov key. It exits 0, the JSON is `COMPLETE`, and GovInfo is named with its cure in
  `providers`. The groups are the same as the existing NHI test's. The Markdown digest says
  `- Status: COMPLETE` and ends with `- govinfo: not configured on 8 of 8 queries: not counted as
  partial: …`. GovInfo's host is never asked.

### Mutants (each restored from HEAD; tree clean after every batch)

| # | Mutant | Caught by |
|---|---|---|
| 1 | `search_status` leaves out every call of an uncounted provider, not only `not_configured` | 4 (the asked-and-failed cases) |
| 2 | `search_status` ignores `uncounted` | 11 |
| 3 | COMPLETE compares the answers with every call, not the counted ones | 11 |
| 4 | Providers a person named are left out too | 3 (all three ruling-2 tests) |
| 5 | Left out only when `providers` was given | 11 |
| 6 | The topic gate is skipped | 1 (preset provider off its topic) |
| 7 | Every selected provider counts as unbuilt | 12 |
| 8 | The cure goes on named providers too | 3 |
| 9 | No cure at all | 14 |
| 10 | The stored status counts every not-configured provider | 8 |
| 11 | `daily` asks its preset's providers as named ones | 3 |
| 12 | The digest's status counts every not-configured provider | 2 |
| 13 | The digest names no uncounted provider | 3 |
| 14 | The presenter never says `not counted as partial` | 8 |
| 15 | The presenter says it for every failed provider | 6 |

The first run of the 15 mutants in one loop was stopped by the operator partway through. It would
have taken longer than two minutes, which was my mistake, and it left mutant 7 in place. I restored
that file from HEAD and reran the mutants in three batches (1 to 4, 5 to 10, 11 to 15), each under
`hard_stop.py 115`, about 8 s a mutant.

### Checks before the report

* **Affected set:** `uv run scripts/affected_tests.py` chose **254 of 742 test files** (34.2%) from 16
  changed files. That is over two minutes, so it is **not run here** and is left to the pull
  request's `ci` (agreement 10).
* **Run within the limit:**
  * the always-run list plus `packages/debate_core/tests/integrations/discovery` → `1465 passed in 34.42s`;
  * `packages/debate_core/tests/application` → `5658 passed in 105.49s`;
  * the changed CLI test files and `test_doctor_providers.py` → 421 passed, as above;
  * `tests/smoke/test_search_smoke.py`, which pins the `--providers govinfo` reason as unchanged →
    `9 passed in 12.33s`.
* **Stopped at the limit:** the 92 affected CLI test files, run in halves and then in quarters. A
  quarter of 23 files was still stopped at 115 s, so `packages/debate_cli/tests` as a whole is left
  to CI.
* **Static checks:**
  * `ruff format --check .` → 2054 files already formatted;
  * `ruff check .` → All checks passed;
  * `pyright packages/debate_core packages/debate_cli` → 0 errors;
  * `lint-imports` → 20 kept, 0 broken;
  * `validate_specs.py` → OK;
  * `check_command_blocks.py` → OK;
  * `check_thin_handlers.py` → OK.
* **The spec against `origin/dev`** (the local ref, at `995b05f`): only `status.phase` differs, so
  there is no amendment.

## Files changed

* `packages/debate_core/src/debate_core/application/`
  * `federated_search.py`:
    * `search_status(..., uncounted=)`;
    * `FanOutStage.uncounted(request)`;
    * the cure after the registry's reason for an uncounted provider;
    * the stored status and `SearchOutcome.uncounted`;
    * the module's Status section.
  * `federated_search_types.py`: `SearchRequest.providers_named` (default True, left out of the JSON
    when True) and `SearchOutcome.uncounted`.
  * `provider_credentials.py`: a `cure` in each provider's words, and `missing_credential_cure`.
  * `digest_service.py`: preset searches set `providers_named=False`; `Digest.uncounted` and its
    status use it.
* `packages/debate_cli/src/debate_cli/presenters/`
  * `search_presenter.py`: `uncounted` on `provider_summaries` and `status_footer_lines`; the footer,
    JSON and failure panel pass it; the exit-7 message says `every provider asked answered`.
  * `daily_presenter.py` and `batch_report_presenter.py`: pass `uncounted`.
* `packages/debate_cli/README.md`: the exit-code table, the GovInfo paragraphs and the daily section.
* Tests:
  * new: `test_not_configured_is_not_partial.py` and `test_search_presenter_not_configured.py`;
  * changed: `test_digest_service.py`, `test_government.py` (the uncounted reason gains the cure),
    `test_search_command.py` and `test_daily_command.py`.
* The spec: `status.phase` Succeeded.

## Deviations from the spec

* **The spec asked for a proposal on the `--providers` case and a stop for the ruling.** The PM ruled
  it in the session's opening prompt (2026-11-09, ruling 2), so the proposal is recorded below and the
  work went on without stopping. The proposal was the rule the PM ruled: a provider the student names
  keeps today's rule, because missing a provider asked for by name is a missing answer.
* **`daily` is changed** (the PM's ruling 3) in `debate_core.application.digest_service` and
  `debate_cli`'s daily presenter. Both are inside the spec's packages; its description does not name
  `daily`.
* **The spec says `--provider`; the option is `--providers`.** The tests use the real option.

## Decisions and assumptions

* **"Settings cannot configure" is read narrowly:** the registry's `not_configured`, a provider enabled
  in `providers.enabled` whose factory refused it for a missing credential. Today that is only
  GovInfo without its key. Crossref and Semantic Scholar without theirs still search, in a public
  pool.
  * A name settings do not enable at all is still counted, even from a preset. So is a government
    provider the topic does not list.
  * So `daily nhi` on the test profile, which enables only `rss`, is still PARTIAL, and the existing
    test `test_an_nhi_digest_reads_only_the_health_insurance_feeds_and_names_its_unasked_providers` is
    unchanged. `config/daily_presets.yaml`'s comment ("One the environment does not enable … makes it
    partial") stays true.
* **Where the cure goes:** in the call's own reason, `<registry reason>; <cure>`, written by the
  application. It is therefore the same in the footer, `reasons` and `provider_calls[].error`. The cure
  is added only for an uncounted provider. A named one keeps today's words, which also keeps the
  smoke pin in `tests/smoke/test_search_smoke.py` as it is.
* **The words:** GovInfo `get a free key at api.data.gov/signup to ask GovInfo`. The registry's
  reason before it already names `DEBATE_PROVIDERS__API_DATA_GOV_KEY`. Crossref, OpenAlex and Semantic
  Scholar also have cure words, though none of them can be `not configured` today.
* **The exit-7 message** now says `every provider asked answered, and nothing matched …`, because an
  uncounted provider was not asked. Nothing pinned the old text. The `--help` exit lines and the
  smoke-pinned help text are unchanged.
* **`batch report`'s `partial_providers`** still lists every provider whose outcome is not `ok`, an
  uncounted GovInfo included, beside `search_status: COMPLETE`. Nothing is hidden, and the key's
  meaning is unchanged; see the follow-up below.
* **The daily test's clock:** Crossref's pacer waits on the container clock, and the daily tests' clock
  never moves, so an eight-query preset would wait until the deadline. That one test uses a clock that
  moves 0.4 s each time it is read, and an invented contact email, so Crossref's pace stays out of the
  test. Real waiting is none; the test runs in about 3 s.

## Operator follow-ups

None. The affected set (254 files) runs in the pull request's `ci`.

## Follow-up work

For the PM:

1. **A preset provider the profile does not enable at all** (for example `nhi`'s `openalex` on a
   profile that leaves it off) still makes `daily` partial every day, as v1-e08-t07's follow-up 3
   described. Retrying can't cure it either: the cure is `providers.enabled`. I propose the same
   treatment for a preset's providers: named with `enable it in providers.enabled`, and not counted.
   That is a one-line change in `FanOutStage.uncounted` plus that cure. Not built; ruling 1 defined
   the case as a missing key or email.
2. **The named case's reason has no cure.** `search --providers govinfo` without a key says what is
   missing and names the variable, but not where to get a key. Adding the cure there would change the
   smoke pin. Not built, because ruling 2 kept today's rule.
3. **`batch report`'s `partial_providers`** lists an uncounted GovInfo on a COMPLETE search. Leave it
   (nothing hidden), or exclude uncounted providers? I recommend excluding them, because the key's
   name says partial.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-11

**Notes:**

The PM read the rule in the worktree.
- `search_status(..., uncounted=)` leaves out only the `NOT_CONFIGURED` calls of an uncounted
  provider, so any other outcome it had still counts.
- `FanOutStage.uncounted` returns nothing when a person named the providers, and otherwise the
  selected providers that the registry could not build and that the topic allows.
- The cure is appended in the application, so the footer, `reasons` and `provider_calls[].error`
  carry the same words.
- `providers_named` defaults to True, which counts a provider. So any caller that doesn't say
  otherwise keeps today's rule, and only `daily` sets it to False.

This is the rule as ruled on 2026-11-09, and the business logic stays in `debate_core.application`.

1. **ac1 passes.**
   - Red ran against a skeleton that has the names and no behaviour: 20 failed, each at an assertion.
     The new tests that already passed are explained as rules that already held.
   - Green: 140 in the selection, and 421 over the changed files.
   - All 15 mutants on the partial reckoning are caught. They cover:
     - leaving out every call against only `not_configured` ones;
     - named providers left out;
     - the topic gate;
     - the cure on named providers;
     - the stored status;
     - `daily` asking as named.
   - The interrupted first mutant loop is reported plainly, its leftover mutant restored, and the run
     repeated in bounded batches. That is the right handling.
2. **Rulings 1 to 4 hold.**
   - GovInfo without a key leaves an NHI search COMPLETE (exit 0) and still names GovInfo with its
     cure.
   - `--providers openalex,govinfo` is still PARTIAL, exit 6, with today's reason.
   - `daily nhi` without the key exits 0, COMPLETE.
   - Nothing is hidden or reordered.
   - The PM checked the cure's address: api.data.gov/signup is api.data.gov's key sign-up page (read
     2026-11-11).
3. **Deviations accepted.**
   - The `--providers` proposal was recorded and not stopped on, as the prompt ruled.
   - `daily` was changed inside the spec's packages.
   - The option is really `--providers`.
4. **Decisions accepted.**
   - The narrow reading: a missing key or email only. Ruling 1 said exactly that; ruling 3 extended
     it to a preset's providers, not to providers the profile leaves off.
   - The cure's place and words, and the exit-7 message.
   - `partial_providers` left unchanged.
   - The daily test's moving clock, which keeps Crossref's pace out of a test about GovInfo with no
     real waiting.
5. **Follow-ups 1 to 3:** the PM files them in the next batch as one E07 task (p3), as ruled here:
   - **(1) Yes.** A daily preset's provider that the profile does not enable is configuration too.
     It is named with `enable it in providers.enabled` and not counted.
   - **(2) Yes.** A named provider without its key gets the cure in its reason too, and stays
     PARTIAL. The smoke pin moves with it.
   - **(3) Yes.** `batch report`'s `partial_providers` excludes uncounted providers, since the key's
     name says partial. They stay listed in `providers`.
6. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.

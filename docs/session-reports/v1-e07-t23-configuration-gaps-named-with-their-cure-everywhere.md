# Session report: v1-e07-t23-configuration-gaps-named-with-their-cure-everywhere

| | |
|---|---|
| Task | `v1-e07-t23-configuration-gaps-named-with-their-cure-everywhere` — A provider missing only configuration is named with its cure wherever it appears, and counts as partial only when a person asked for it |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t23-configuration-gaps-named-with-their-cure-everywhere.yaml`](../../plan_specs/v1/e07-discovery-adapters/t23-configuration-gaps-named-with-their-cure-everywhere.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t23-configuration-gaps-named-with-their-cure-everywhere` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

A provider that lacks only configuration is now named with its cure everywhere it appears. It is
counted as partial only when a person named it with `--providers`. This covers the PM's three
follow-ups and the fourth item folded in:

1. **A daily preset's provider that the profile does not enable at all** is left out of the status.
   Its reason ends `; enable it in providers.enabled`. So `daily nhi` on a profile that enables only
   `rss` is now COMPLETE (exit 0), not PARTIAL.
2. **A provider named with `--providers` that lacks its key** gets its cure in its reason, and the
   search is still PARTIAL. The smoke pin moves with it.
3. **`partial_providers`** (for `search --auto-cut` and `daily --auto-cut`) leaves out uncounted
   providers. They stay in `providers` with their reasons.
4. **When no provider was asked**, the message of `search` and `daily` names each selected provider
   on a line of its own, in the footer's words. That line is either "not enabled …; enable it in
   providers.enabled", or the registry's reason with its cure. It no longer says "none of X is
   enabled". The code and exit stay `NO_PROVIDER_ENABLED`, 1.

The rule lives in `debate_core.application.federated_search`: `FanOutStage.uncounted`, the cure on
every not-configured reason, and a new `partial_providers()` that counts the way `search_status`
does. The presenters only render what it returns.

**Look at first:**

* **Decision 1:** a provider named with `--providers` that is *not enabled* now carries the cure too.
  Ruling 4 needed it in the panel, and putting it in the reason makes the footer, `reasons` and the
  message say the same thing. This changes three existing pins (listed under Files changed).
* **Decision 3:** the property test was too weak at first and passed against the skeleton. The fix is
  recorded below.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `configuration-gaps-named-with-their-cure`: Cures everywhere | Done | Skeleton `1b85a2a`, tests shown red `4007759`, the rule and the presenters `937ba2c`, docstrings and guides `959dc25`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a preset provider the profile does not enable is named with its cure and not counted; a named provider without its key is named with its cure and still PARTIAL; partial_providers leaves out uncounted providers; by tests shown failing first | PASS | **Red** against the skeleton `1b85a2a` (new names, old behaviour). The new and changed tests in the eight changed files, with the node's `-k "not_configured or uncounted or partial_providers"`: **28 failed, 43 passed**. All 50 error lines are `AssertionError`. The smoke pin `test_a_topic_alone_names_the_government_provider_it_could_not_ask` also failed at its assertion. The new tests that already passed describe rules that already held: off its topic a provider is still counted; a reason with no known cure stays bare; the `NOT_ENABLED_CURE` words; an uncounted provider's other failures still count (4 outcomes); a named not-configured provider stays in `partial_providers`; t15's two digest tests. **Green:** the same nine files whole (eight test files and the smoke file), **262 passed in 7.63s**. **Mutants:** 17, each run with a fresh Hypothesis directory and restored from HEAD, all caught at assertions (list below). |
| Node: `uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "not_configured or uncounted or partial_providers"` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests packages/debate_cli/tests -k "not_configured or uncounted or partial_providers"` → **88 passed in 43.03s**. A `--collect-only` of the two new files gives 25 tests with and without the `-k`, so the selection picks up every new test. The digest test and the renamed tests match it by name. |

### What the tests pin

Core, `packages/debate_core/tests/application/test_configuration_gaps_named_with_their_cure.py`:

* **Ruling 1, a preset's provider that is not enabled:**
  * `gdelt` beside an OpenAlex that answers: uncounted, reason `gdelt: not enabled in settings
    (providers.enabled); enable it in providers.enabled`, COMPLETE, and stored COMPLETE;
  * a preset that mixes not enabled (`google_news`, `gdelt`) with no key (`govinfo`): all three are
    uncounted, in selection order;
  * beside a provider that failed, the search is FAILED; with no other provider, nothing is asked
    and it is FAILED;
  * a government provider that is not enabled and off its topic is still counted, with the topic's
    refusal and no cure.
* **Ruling 2, named providers:** GovInfo and Semantic Scholar without keys, and `gdelt` not enabled,
  each carry the cure, are not uncounted, and the search is PARTIAL (stored PARTIAL). A
  registry reason that has no cure in `provider_credentials` keeps its words alone.
* **Ruling 3, `partial_providers`:**
  * it leaves out only the `not_configured` calls of an uncounted provider; a timeout, error, rate
    limit or open breaker still counts (parametrized);
  * it names each provider once, in the order first asked, including partial answers;
  * on a real search it leaves out the uncounted ones;
  * a Hypothesis property: for any status but FAILED, COMPLETE holds exactly when
    `partial_providers` is empty.
* **Changed pins:**
  * `test_not_configured_is_not_partial.py`: the named case gains the cure; the preset-not-enabled
    test flips to uncounted and COMPLETE, and is renamed to match;
  * `test_federated_search.py`: the named-not-enabled reason gains the cure.
* **Digest,** `test_digest_service.py`: a preset provider the profile does not enable leaves the
  digest COMPLETE and written, and is named with the cure.

CLI, `packages/debate_cli/tests/test_presenters_configuration_gaps_named_with_their_cure.py`:

* **No provider asked:**
  * a keyless Semantic Scholar that settings select: the message is `no provider was asked:` and
    then its footer line, `panel_message` is `no provider was asked`, the panel's details are
    unchanged, and "is enabled" appears nowhere;
  * named `gdelt,govinfo`: one line each in the order asked, each with its cure, and the same
    reasons in the JSON `providers`;
  * settings that select nothing: `no provider was asked: no provider is enabled; enable one in
    providers.enabled`;
  * `daily`: `no provider was asked, so no digest was written:` and then the lines.
* **`partial_providers`:** `search --auto-cut`'s `report_payload` gives `["rss"]` beside uncounted
  GovInfo and Semantic Scholar, which are still in `providers`; a named GovInfo is still listed;
  `daily --auto-cut`'s `auto_cut_payload` gives `["rss"]` beside uncounted `govinfo` and `gdelt`.

CLI commands:

* `test_search_command.py`:
  * named not-enabled Semantic Scholar: footer line with the cure, exit 6;
  * `--providers semantic_scholar` alone: exit 1, the JSON message names its state;
  * keyless Semantic Scholar alone (t20's test): stderr no longer says "is enabled", and the JSON
    message is the footer line;
  * named Semantic Scholar and GovInfo without keys: the reasons carry the cure, and the search is
    still PARTIAL.
* `test_daily_command.py`: the NHI test on the test profile (which enables only `rss`) now exits 0
  and is COMPLETE. Its four other preset providers are named `not counted as partial: not enabled
  …; enable it in providers.enabled`.
* `tests/smoke/test_search_smoke.py`: `--topic … --providers govinfo` with no key. The pin moves to
  the reason with its cure, and the JSON message is checked too.
* `test_search_presenter_not_configured.py`: t15's named-footer test gains the cure.

### Mutants (each restored with `git checkout HEAD --`; tree clean after every batch)

| # | Mutant | Failed tests |
|---|---|---|
| 1 | Named providers are left out too | 14 |
| 2 | A preset's not-enabled provider is counted (t15's rule) | 10 |
| 3 | The topic gate is dropped from `uncounted` | 2 |
| 4 | The cure goes only on uncounted providers (t15's rule) | 8 |
| 5 | No cure after a not-enabled reason | 13 |
| 6 | `partial_providers` ignores `uncounted` | 6 |
| 7 | `partial_providers` leaves out every call of an uncounted provider | 5 |
| 8 | `partial_providers` ignores partial answers | 2 |
| 9 | `partial_providers` sorted by name | 3 |
| 10 | `_counted` leaves out every `not_configured` call, named ones too | 16 |
| 11 | `search_status`'s COMPLETE ignores the counted failures | 42 |
| 12 | The message names only the first provider | 1 |
| 13 | The panel prints the message's lines again (no `panel_message`) | 2 |
| 14 | An empty selection reads as before (`none of  is enabled`) | 1 |
| 15 | `daily`'s message drops "so no digest was written" | 1 |
| 16 | `batch report` counts every provider | 1 |
| 17 | `daily --auto-cut` counts every provider | 1 |

Each mutant ran over the nine test files above, `-n 4`, in three batches under
`hard_stop.py 115` (85 s, 56 s and 26 s). The second batch stopped at mutant 15, whose target
string the formatter had reflowed; the harness asserts the string appears once, so it applied
nothing. I corrected the target and reran 15 to 17.

### Checks before the report

* **Affected set:** `uv run scripts/affected_tests.py` chose **260 of 746 test files (34.9%)** from 23
  changed files, 96 of them in `packages/debate_cli/tests`. That is over two minutes (t15's 254
  files could not run in parts within the limit), so it is **not run here**. It is left to the pull
  request's `ci` (agreement 10).
* **Run within the limit:**
  * the always-run list and `packages/debate_core/tests/integrations/discovery` → **1540 passed in
    30.75s**;
  * `packages/debate_core/tests/application` without `caselist/` → **3831 passed in 41.60s**;
    `caselist/` → **1908 passed in 72.12s**;
  * the 11 affected CLI files about search, daily, presenters, output and the providers doctor →
    **262 passed in 5.29s**;
  * the nine changed test files, `tests/smoke/test_search_smoke.py` among them → 262 passed, as above;
  * the neighbouring search tests (`test_search_presenter*.py`, `test_government.py`,
    `test_semantic_scholar.py`, dedupe, ranking, articles, `test_discovery.py`,
    `test_doctor_providers.py`) → **777 passed in 2.28s**.
* **Static checks:**
  * `ruff format --check .` → 2068 files already formatted;
  * `ruff check .` → All checks passed;
  * `pyright packages/debate_core packages/debate_cli` → 0 errors;
  * `lint-imports` → 20 kept, 0 broken;
  * `check_thin_handlers.py` → 74 handlers within 25 statements;
  * `check_command_blocks.py` → OK;
  * `validate_specs.py` → OK, 669 files.
* **The spec against `origin/dev`** (local ref `9e77a71`): only `status.phase` differs, so there is
  no amendment.

## Files changed

* `packages/debate_core/src/debate_core/application/`:
  * `federated_search.py`:
    * `FanOutStage.uncounted` leaves out any selected provider that was not built, enabled or not,
      unless a person named it;
    * every unbuilt reason gets its cure, named providers' too;
    * the not-enabled reason ends with `NOT_ENABLED_CURE`;
    * new `partial_providers()`, sharing `_counted` and `_in_full` with `search_status`;
    * the module's Fan-out and Status sections.
  * `federated_search_types.py`: the docstrings of `SearchOutcome.uncounted` and
    `SearchRequest.providers_named`.
  * `digest_service.py`: the module docstring's account of a not-enabled preset provider.
* `packages/debate_cli/src/debate_cli/`:
  * `presenters/search_presenter.py`: `no_provider_asked_message` and `NO_PROVIDER_ASKED`; the
    NO_PROVIDER_ENABLED failure uses them, with `panel_message`; the module docstring.
  * `presenters/daily_presenter.py`: the same for `daily`; `partial_providers` comes from core.
  * `presenters/batch_report_presenter.py`: `partial_providers` comes from core.
  * `commands/search.py`, `commands/daily.py`, `exit_codes.py`: the exit-1 docstrings and `--help`
    lines.
  * `search_auto_cut.py`: the docstring on `partial_providers`.
* Docs:
  * `packages/debate_cli/README.md`, the search guide: the named GovInfo reason, named not-enabled
    providers, the daily paragraph, both exit-1 rows;
  * `docs/guides/provider-credentials.md`: one sentence in the Semantic Scholar row.
* Tests:
  * new: the core and CLI test files named above;
  * changed: `test_not_configured_is_not_partial.py`, `test_federated_search.py`,
    `test_digest_service.py`, `test_search_presenter_not_configured.py`, `test_search_command.py`,
    `test_daily_command.py`, `tests/smoke/test_search_smoke.py`.
* The spec: `status.phase` Succeeded.

## Deviations from the spec

* **Item 4 is not in the spec.** The PM folded v1-e07-t20's follow-up 2 into this task in the
  session's opening prompt, as an amendment for the next PM batch. It is built as ruled. The spec's
  description and ac1 do not name it yet.
* **The packages go one step past the spec's five,** as the PM ruled: `docs/guides/provider-credentials.md`,
  for its one sentence. The search guide is `packages/debate_cli/README.md`, inside `debate_cli`, as
  v1-e07-t13 established.
* **Renamed tests.** Eight existing tests were renamed because what each asserts changed.
  * Five did not match the node's `-k` before, and now do:
    * t15's daily NHI test (`…names_its_unasked_providers` became `…names_its_uncounted_providers`);
    * t20's two Semantic Scholar tests (keyless alone, and named without a key);
    * in `test_search_command.py`, the named not-enabled footer test and the
      `--providers semantic_scholar` exit-1 test.
  * Three already matched, and their names now say the new rule:
    * t15's preset-not-enabled test in core (`is_still_partial` became `is_uncounted`);
    * t15's named-footer presenter test;
    * t15's named-GovInfo command test (gains `and_names_its_cure`).

## Decisions and assumptions

1. **The not-enabled cure goes in the reason, for every provider that is not enabled.** That includes
   one named with `--providers`, which stays PARTIAL. Ruling 4 asks the no-provider panel to name a
   not-enabled provider with `enable it in providers.enabled`, and outside a preset only a named
   provider can be not enabled. Writing the cure in core, into the call's reason, means
   `debate_cli` decides nothing about state. It also makes the footer, the JSON `reasons`,
   `provider_calls[].error` and the message agree. The reason reads `not enabled in settings
   (providers.enabled); enable it in providers.enabled`. That repeats itself, but it keeps the
   existing reason word for word and adds the PM's cure, in the same `<reason>; <cure>` shape as
   GovInfo's. The GovInfo and Semantic Scholar lines are unchanged apart from the cure that ruling 2
   adds when they are named.
2. **The words when no provider was asked.** The message is the heading (`no provider was asked`,
   or `… , so no digest was written` for `daily`), a colon, then each provider's footer line on its
   own line, indented two spaces as the footer is. An uncounted provider's line therefore keeps
   `not counted as partial:`, exactly as the footer just above it prints it. The panel already
   printed those lines as its details, so it shows only the heading (`panel_message`, as `caselist
   pull` does), which keeps each line from printing twice. The JSON `message` carries the lines.
   When settings select no provider at all, which `providers.enabled = []` allows, the message is
   `no provider was asked: no provider is enabled; enable one in providers.enabled`. Before, it
   printed `none of  is enabled`. The hint is unchanged, as the ruling kept everything but the
   message and the details. Follow-up 2 says why it is worth a look.
3. **The property test was too weak at first.** Its first strategy rarely produced a COMPLETE search
   with an uncounted provider (about 2% of examples), so it passed against the skeleton: 100
   passing, 0 failing. I checked the case by hand and it does break the skeleton. I then weighted the
   strategy toward `ok` and `not_configured` calls, shortened the lists, kept at least one uncounted
   name and raised `max_examples` to 300. I also added an `event` for the case. After that it failed
   against the skeleton in 6 of 6 runs, each with a fresh database. It was committed red with the
   other tests.
4. **No new JSON field.** Every provider's state is already in its `reasons` (and in `provider_calls`),
   in `debate_core`'s words, and the error details change only through them. No key was removed or
   renamed, and no provider is hidden from the footer, `providers` or `reasons`.
5. **`partial_providers` is a core function, not a property on the outcome.** It takes
   `(statuses, uncounted)` as `search_status` does, and both presenters call it. So the rule sits next
   to `search_status`, and the two cannot disagree: the property pins that.
6. **The order of uncounted providers** follows the selection: enabled, then unbuilt, each in the
   registry's order. In one of my own CLI tests I had written the stand-in's two unbuilt providers
   in the wrong order. The green run caught it, and I corrected the expectation from the fixture's
   order, not from the code's output.

## Operator follow-ups

None. The affected set (260 files) runs in the pull request's `ci`.

## Follow-up work

For the PM:

1. **`config/daily_presets.yaml`'s comment is now wrong.** Its `providers:` entry says "One the
   environment does not enable is reported "not configured" in the digest's footer, which makes it
   partial." It no longer makes the digest partial. `config/` is outside this task's packages, so
   I did not change it. Proposed words: "One the environment does not enable is named "not
   configured" in the digest's footer, with `enable it in providers.enabled`, and does not make it
   partial (v1-e07-t23)."
2. **The NO_PROVIDER_ENABLED hint** still says "Name enabled providers with --providers, or enable
   them in providers.enabled". For a keyless Semantic Scholar or GovInfo, which is already enabled,
   the cure is the key, and the message above the hint now says so. The ruling kept the hint, so I
   left it. One option is to drop the hint's second clause when every provider is enabled but
   unbuilt, or to drop the hint entirely now that each line carries its cure.
3. **The SEARCH_PARTIAL message counts uncounted providers.** `N of M providers did not answer in
   full: openalex (timeout), govinfo (not configured)` still lists an uncounted GovInfo next to the
   provider that made the search partial. `daily` says the same. Using `partial_providers` there
   would match `report.json`'s key. Not built: the spec named only `batch report`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-12

**Notes:**

Accepted. ac1 and the node pass, and the Goal is `Succeeded`.

* **Scope, checked against the branch:** six commits on dev's tip (`9e77a71`), with the skeleton
  `1b85a2a` and the red tests `4007759` before the code `937ba2c`. The rule lives in
  `federated_search.py` (`uncounted`, the cure on every unbuilt reason, `partial_providers()` beside
  `search_status`). The presenters only render it, as ruled.
* **The evidence is enough.** The red run had 28 failures, all at assertions. The 17 mutants were all
  caught. Decision 3 is the most useful note in the report: a property test that passed against the
  skeleton was found, strengthened, and committed red. Keep doing that.
* **Decision 1: accepted.** A named provider that is not enabled now carries `enable it in
  providers.enabled` and stays PARTIAL. The reason repeats itself, but it keeps t15's words and has
  the `<reason>; <cure>` shape, and the footer, `reasons`, `provider_calls` and the message agree.
  Wording can be tightened later. Not now.
* **Decisions 2, 4, 5 and 6: accepted.** On the panel: printing the heading only, with the lines once
  as details, is right. The empty selection now reads properly instead of `none of  is enabled`. No
  new JSON field was needed and none was removed. `partial_providers()` in core means it and the
  status cannot disagree, and the property pins it.
* **The deviations are accepted.** Item 4 and the guide sentence were the PM's to add, and go into the
  next PM batch as an amendment to this spec's description and ac1. The eight renamed tests are
  justified one by one.
* **The affected set (260 files)** goes to the pull request's `ci` under agreement 10. The report
  lists what ran within the limit, about 7,500 tests.
* **Follow-ups, into the next PM batch:**
  1. the comment in `config/daily_presets.yaml`, in the session's proposed words, as a PM edit;
  2. and 3. one new E07 task at p3: the NO_PROVIDER_ENABLED hint when every provider is enabled but
     unbuilt, and the SEARCH_PARTIAL message (`search` and `daily`) listing only the providers
     `partial_providers` counts.

`scripts/task pr`

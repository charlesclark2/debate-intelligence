# Session report: v1-e07-t20-semantic-scholar-enabled-after-its-live-smoke

| | |
|---|---|
| Task | `v1-e07-t20-semantic-scholar-enabled-after-its-live-smoke` — Semantic Scholar is enabled in both profiles once its live smoke has passed |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t20-semantic-scholar-enabled-after-its-live-smoke.yaml`](../../plan_specs/v1/e07-discovery-adapters/t20-semantic-scholar-enabled-after-its-live-smoke.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t20-semantic-scholar-enabled-after-its-live-smoke` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

<!-- 3-6 sentences: what was built, how it fits the epic, anything the PM should look at first. -->

**Stopped for the operator's two smokes (the PM's ruling 2 of 2026-11-12).** The code half is done
(ac3, the PM's "ac2"). Without a key, the factory builds nothing: the registry reports
`semantic_scholar` as not configured. A search names it with its cure, and does not count it as partial
when settings enabled it and the search did not name it. With a key it is built and asked at the
keyed pace, as before. Neither profile enables Semantic Scholar yet. That waits for the keyed smoke
and the keyless single query below to pass and for the PM to record them (ac1); then the profiles,
the guides and ac2 follow.

**Look first at** Decision 1 (the footer's words, the PM's sentence with the variable inserted, as for
GovInfo) and Decision 3 (the adapter keeps its keyless mode, which no factory builds now).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `semantic-scholar-enabled-after-its-live` (Semantic Scholar enabled) | In progress | Code half done: tests red `1732fac`, code `369ff8a`. Waits for the operator's smokes, then the profiles and the guides. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the operator's live smokes, keyless and keyed, have passed and are recorded by the PM | NOT RUN | Waiting for the operator's blocks under Operator follow-ups, and then for the PM's record. |
| ac2: both profiles enable semantic_scholar and the guides say what a student without a key sees, by tests on the committed profiles shown failing first | NOT RUN | Waits for ac1 (the spec forbids enabling before the smoke has passed). |
| ac3: without a key Semantic Scholar is not configured, named with its cure and not counted as partial, and with one it is built and asked, by tests shown failing first | PASS | Red and green below. |
| Node: `uv run pytest packages/debate_cli/tests -k profile` | NOT RUN | Run once the profiles are enabled. |

### ac3: red, then green

**Red.** The new and changed tests were committed alone as `1732fac` and run against the pre-task code:

```text
.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/integrations/discovery/test_semantic_scholar.py packages/debate_core/tests/application/test_not_configured_is_not_partial.py packages/debate_cli/tests/commands/test_doctor_providers.py packages/debate_cli/tests/test_search_command.py -n 4 -q --tb=line
13 failed, 314 passed
```

Every failure was at an assertion, grouped by reason:
* 3 `DID NOT RAISE ProviderNotConfigured` (the factory without a key: unset, empty, spaces);
* 1 the registry built the provider (`assert (ResilientProvider…,) == ()`);
* 1 the fan-out record: `semantic_scholar` `ok` where `not_configured` with the cure was expected;
* 1 the cure: `'set a Semantic Scholar key' == 'request one …'`;
* 2 the doctor rows (the keyed row and the keyless one);
* 3 the CLI footer: `semantic_scholar: ok, 1 result` where the not-counted line was expected
  (unset, empty, spaces);
* 2 the CLI exit code: 0 where 6 (named with `--providers`) and 1 (Semantic Scholar alone) were
  expected.

The first red run had a 14th failure, a `TypeError` in my own test (it passed `enabled` twice). I
fixed it and ran that test alone against the pre-task code. It then failed at its assertion: `ok`
where `not_configured` was expected.

Two new tests passed at red, as they should: the keyed build test, because a key already built the
provider and asked it, and the container redaction test, because the key was already kept out of
output and logs. They pin the keyed path that this task keeps.

One expectation was mine, and wrong: with Semantic Scholar as the only enabled provider and no key,
I expected exit 3. The existing presenter rule answers a search in which every call was not
configured with exit 1, `NO_PROVIDER_ENABLED`, as it does for GovInfo alone. The test now expects
that, with the cure in the footer. It was red at the pre-task code too (exit 0).

**Green.** The same four files: `327 passed`, then the neighbours:

```text
.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests/commands/test_doctor.py packages/debate_cli/tests/commands/test_doctor_providers.py packages/debate_cli/tests/test_installation.py packages/debate_cli/tests/test_container_factories.py packages/debate_cli/tests/test_config_command.py packages/debate_cli/tests/test_daily_command.py packages/debate_cli/tests/test_search_command.py packages/debate_core/tests/application/test_not_configured_is_not_partial.py packages/debate_core/tests/application/test_federated_search.py packages/debate_cli/tests/test_search_presenter_not_configured.py tests/smoke/test_search_smoke.py -n 6 -q -m "not slow and not live"
320 passed in 22.88s
```

**One process, the adapters after the discovery suites** (`-n 0 -p no:randomly`): the OpenCaselist
suite, `test_http_fetcher.py`, `test_crossref_doi.py`, the 15 other discovery test files, and
`test_semantic_scholar.py` last → `1482 passed in 5.85s`.

**Mutants.** Five, each applied to the committed file, run over the four test files with
`PYTHONDONTWRITEBYTECODE=1` and a fresh `HYPOTHESIS_STORAGE_DIRECTORY`, and restored with
`git checkout HEAD --`. The tree was clean after the run. All five were caught at assertions:

| Mutant | Failed |
|---|---|
| a key of spaces counts as a key | 2 (the factory's and the CLI's `[spaces]` cases) |
| the factory never refuses | 10 |
| the reason names no variable | 10 |
| the old cure, `set a Semantic Scholar key` | 6 |
| the adapter's constructor protects no log | 7, all t04's `test_the_adapter_alone_protects_the_logs_from_its_key` |

The last row matters for the redaction claim. My container-level test did not catch that mutant,
because nothing in this build writes the key to a log line: the key travels only in a header, and
httpx logs the URL. t04's adapter test is what pins the protection. My test pins the outcome
through the container: no output and no log record at DEBUG carries the key.

## Files changed

* `packages/debate_core/src/debate_core/integrations/discovery/semantic_scholar.py`: the factory
  raises `ProviderNotConfigured` without a key, using `missing_key_reason()` and
  `SEMANTIC_SCHOLAR_KEY_VARIABLE`. The module and factory docstrings say why.
* `packages/debate_core/src/debate_core/application/provider_credentials.py`: Semantic Scholar's
  doctor words with a key and without one, and its cure.
* Tests:
  * `packages/debate_core/tests/integrations/discovery/test_semantic_scholar.py`: four new tests
    (six cases), and `keyless_adapter`/`adapter_factory` for the adapter's own keyless tests.
  * `packages/debate_core/tests/application/test_not_configured_is_not_partial.py`: the cure.
  * `packages/debate_cli/tests/commands/test_doctor_providers.py`: the two rows.
  * `packages/debate_cli/tests/test_search_command.py`: four new tests (six cases), including the
    redaction check through the container.
* This report, and the spec's phase (InProgress, set at the start).

## Deviations from the spec

1. **Criterion ids.** The PM's message of 2026-11-12 calls the code criterion "ac2". In the spec it
   is ac3, and ac2 is the profiles. This report uses the spec's ids.

## Decisions and assumptions

1. **The footer's words.** The registry's reason is `semantic_scholar: no Semantic Scholar key
   (DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY)`, and the cure is `request one through the form on
   Semantic Scholar's API page, semanticscholar.org/product/api`. So the footer reads
   `semantic_scholar: not configured: not counted as partial: no Semantic Scholar key
   (DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY); request one through the form on Semantic Scholar's
   API page, semanticscholar.org/product/api`. That is the PM's sentence with the variable inserted,
   the shape GovInfo's line has.
2. **The doctor rows.**
   * With a key: `API key set (<source>): asked at one request a second`.
   * Without one: `no Semantic Scholar key: Semantic Scholar not asked; request one through the form
     on Semantic Scholar's API page, semanticscholar.org/product/api`.

   GovInfo's row says `GovInfo not asked` with no cure. I added the cure to Semantic Scholar's row,
   because the form is the only way to a key, and `doctor --providers` is where a student checks
   their setup.
3. **The adapter keeps its keyless mode.** `SemanticScholarProvider(api_key=None)` still sends no
   header, keeps `KEYLESS_PACE`, and says "an API key would identify this caller but raises nothing
   today" in a "not asked" reason. Only the factory refuses. I left it because the ruling names the
   factory, and removing the mode would rewrite t04's and t22's keyless tests, among them the
   night's case. Those tests now build the keyless adapter directly (`keyless_adapter`, over a client
   like the factory's) and pass unchanged in what they assert. Follow-up 1 asks whether to remove the
   mode.
4. **A blank key is no key** (empty or spaces), as the adapter and the doctor rows already treat it.

## Operator follow-ups

Both blocks run on the **installed** dev build, not this branch, and each stops before searching
unless three things hold:
* no `DEBATE_` variable is set in the shell (it prints only the names of any that are);
* no `caselist pull` is running;
* the installed tag is `v1.1.0-dev.412` or later. v1-e07-t22 merged as `06e1a63`, which is
  `v1.1.0-dev.412`.

A stable tag or an untagged build also stops, and so does an installed build of this branch: its
keyless Semantic Scholar is not configured, so block (b) could not test the shared pool.

Each block makes one search with Semantic Scholar as the only provider, in a few seconds, and costs
nothing. Like any search, it writes the search and up to 20 discovery-only Articles to your local
dev store. It prints statuses, counts and the providers' reasons only, never a title, a name or the
key.

1. **(a) The keyed smoke**, now. The block `cd`s to your home folder, so no worktree `.env` takes
   part and the key comes from `~/.debate-research/dev.env`. It also stops if `doctor --providers`
   does not see the key. Success looks like this:
   * `status: COMPLETE`;
   * `semantic_scholar: ok, 1 queries, 0 failed, N results` with N above zero;
   * `results:` above zero and equal to `with an S2 id`;
   * `calls not asked: 0 of 1`;
   * `breaker: closed, errors 0, skipped 0`.

   What a failure says:
   * `HTTP 403` in a reason means Semantic Scholar refused the key;
   * `HTTP 429` means the key was throttled too.

   Please paste the output back either way.

   ```bash
   cd ~
   if env | grep -q '^DEBATE_'; then
     echo "STOP: DEBATE_ variables are set in this shell. Unset each of these and paste the block again:"
     env | grep '^DEBATE_' | cut -d= -f1
   elif pgrep -f "debate-research caselist pull" > /dev/null; then
     echo "STOP: a caselist pull is running. Paste the block again once it has finished."
   else
     TAG=$(debate-research --json --version | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"]["tag"] or "untagged")')
     case "${TAG}" in
       v1.1.0-dev.*) NUMBER="${TAG#v1.1.0-dev.}" ;;
       *) NUMBER=0 ;;
     esac
     KEYED=$(env DEBATE_PROVIDERS__ENABLED='["semantic_scholar"]' debate-research --json doctor --providers | python3 -I -c 'import json, sys; d = json.load(sys.stdin).get("data") or {}; print(any(r["provider"] == "semantic_scholar" and r["set"] for r in (d.get("providers") or {}).get("enabled", [])))')
     if [ "${NUMBER}" -lt 412 ]; then
       echo "STOP: the installed build is ${TAG}. v1-e07-t22 merged in v1.1.0-dev.412: install that dev release or a later one first."
     elif [ "${KEYED}" != "True" ]; then
       echo "STOP: doctor --providers sees no Semantic Scholar key. Check the DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY line in ~/.debate-research/dev.env, and run debate-research doctor --providers to see why."
     else
       echo "installed build: ${TAG}"
       OUT=$(mktemp)
       env DEBATE_PROVIDERS__ENABLED='["semantic_scholar"]' debate-research search "carbon capture subsidies" --format json > "${OUT}"
       python3 -I - "${OUT}" keyed <<'EOF'
   import json
   import sys

   document = json.load(open(sys.argv[1]))
   body = document.get("data") or (document.get("error") or {}).get("details") or {}
   results = body.get("results") or []
   print(f"--- {sys.argv[2]} run")
   if not body:
       print(f"no search answer: error code {(document.get('error') or {}).get('code')}")
   print(f"status: {body.get('status')}")
   for provider in body.get("providers") or []:
       print(f"{provider['provider']}: {provider['outcome']}, {provider['queries']} queries, {provider['failed']} failed, {provider['results']} results")
       for reason in provider["reasons"]:
           print(f"  reason: {reason}")
   print(f"results: {len(results)}")
   print(f"with an S2 id: {sum(1 for item in results if item['identifiers'].get('semantic_scholar_id'))}")
   calls = body.get("provider_calls") or []
   print(f"calls not asked: {sum(1 for call in calls if call['partial'])} of {len(calls)}")
   for health in body.get("provider_health") or []:
       print(f"breaker: {health['state']}, errors {health['error_count']}, skipped {health['skipped_count']}")
   EOF
       rm -f "${OUT}"
     fi
   fi
   ```

2. **(b) One keyless single query**, at a quiet hour: early morning US time is my suggestion, not a
   measured fact. The key is blanked for the search command alone, and nothing changes in your file.
   This must return results. Success is the same as (a): `status: COMPLETE`, `semantic_scholar: ok`,
   results above zero, `breaker: closed, errors 0`. **If it answers `HTTP 429` again, stop there and
   paste the output: the PM decides**, and this session enables nothing.

   ```bash
   cd ~
   if env | grep -q '^DEBATE_'; then
     echo "STOP: DEBATE_ variables are set in this shell. Unset each of these and paste the block again:"
     env | grep '^DEBATE_' | cut -d= -f1
   elif pgrep -f "debate-research caselist pull" > /dev/null; then
     echo "STOP: a caselist pull is running. Paste the block again once it has finished."
   else
     TAG=$(debate-research --json --version | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"]["tag"] or "untagged")')
     case "${TAG}" in
       v1.1.0-dev.*) NUMBER="${TAG#v1.1.0-dev.}" ;;
       *) NUMBER=0 ;;
     esac
     if [ "${NUMBER}" -lt 412 ]; then
       echo "STOP: the installed build is ${TAG}. v1-e07-t22 merged in v1.1.0-dev.412: install that dev release or a later one first."
     else
       echo "installed build: ${TAG}"
       OUT=$(mktemp)
       env DEBATE_PROVIDERS__ENABLED='["semantic_scholar"]' DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY= debate-research search "carbon capture subsidies" --format json > "${OUT}"
       python3 -I - "${OUT}" keyless <<'EOF'
   import json
   import sys

   document = json.load(open(sys.argv[1]))
   body = document.get("data") or (document.get("error") or {}).get("details") or {}
   results = body.get("results") or []
   print(f"--- {sys.argv[2]} run")
   if not body:
       print(f"no search answer: error code {(document.get('error') or {}).get('code')}")
   print(f"status: {body.get('status')}")
   for provider in body.get("providers") or []:
       print(f"{provider['provider']}: {provider['outcome']}, {provider['queries']} queries, {provider['failed']} failed, {provider['results']} results")
       for reason in provider["reasons"]:
           print(f"  reason: {reason}")
   print(f"results: {len(results)}")
   print(f"with an S2 id: {sum(1 for item in results if item['identifiers'].get('semantic_scholar_id'))}")
   calls = body.get("provider_calls") or []
   print(f"calls not asked: {sum(1 for call in calls if call['partial'])} of {len(calls)}")
   for health in body.get("provider_health") or []:
       print(f"breaker: {health['state']}, errors {health['error_count']}, skipped {health['skipped_count']}")
   EOF
       rm -f "${OUT}"
     fi
   fi
   ```

## Follow-up work

1. **For the PM: remove the adapter's keyless mode?** No factory builds it now (Decision 3). Removing
   `KEYLESS_PACE`, the keyless "not asked" suffix and the keyless kit binding would make the adapter
   require a key. It is a small E07 change, and this task leaves it alone.
2. **For the PM: the "none of … is enabled" panel.** When every selected provider is not configured,
   the panel says `no provider was asked: none of semantic_scholar is enabled` above the line that
   names the cure. Semantic Scholar *is* enabled; it is not configured. GovInfo alone gets the same
   words today. That is v1-e07-t15's presenter, outside this task.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

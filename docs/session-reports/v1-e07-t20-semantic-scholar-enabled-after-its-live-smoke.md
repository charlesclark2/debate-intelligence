# Session report: v1-e07-t20-semantic-scholar-enabled-after-its-live-smoke

| | |
|---|---|
| Task | `v1-e07-t20-semantic-scholar-enabled-after-its-live-smoke` — Semantic Scholar is enabled in both profiles once its live smoke has passed |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t20-semantic-scholar-enabled-after-its-live-smoke.yaml`](../../plan_specs/v1/e07-discovery-adapters/t20-semantic-scholar-enabled-after-its-live-smoke.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t20-semantic-scholar-enabled-after-its-live-smoke` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

<!-- 3-6 sentences: what was built, how it fits the epic, anything the PM should look at first. -->

**PARTIAL: the code half, for a `scripts/task pr --partial` (the PM, 2026-11-12). The Goal stays
InProgress.** ac3 passes. Without a key, the factory builds nothing: the registry reports
`semantic_scholar` as not configured. A search names it with its cure, and does not count it as
partial when settings enabled it and the search did not name it. With a key it is built and asked
at the keyed pace, as before. No profile enables Semantic Scholar, so this changes nothing a student
sees today.

ac1 is NOT RUN. The keyed smoke (a) was tried once on `v1.1.0-dev.413`: one request, answered
HTTP 429 with no Retry-After. The breaker stayed closed with 1 error, and nothing more was sent
(v1-e07-t22 holding as intended). The key's shape in the per-user file is clean. The PM rules this
not yet a fair try. Next is one diagnostic request with curl after 13:00 Chicago, then (a) and (b)
if it answers 200. ac2 (the profiles and the guides) and the node's `-k profile` criterion wait for
ac1. Also found on the way: the caselist-sync LaunchAgent had come back loaded after a reboot, and
it is now disabled (under Operator follow-ups).

**Look first at** Decision 1 (the footer's words, the PM's sentence with the variable inserted, as for
GovInfo) and Decision 3 (the adapter keeps its keyless mode, which no factory builds now).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `semantic-scholar-enabled-after-its-live` (Semantic Scholar enabled) | Partial | Code half done: tests red `1732fac`, code `369ff8a`. The profiles and the guides wait for ac1. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the operator's live smokes, keyless and keyed, have passed and are recorded by the PM | NOT RUN | (a) tried once, 2026-11-12, on `v1.1.0-dev.413`: one request, HTTP 429, no Retry-After, breaker closed with 1 error, nothing more sent. The PM rules it not yet a fair try (NOT RUN, not FAIL). (b) runs only after (a) passes. Next is the curl diagnostic under Operator follow-ups. |
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

### Checks before the report

* **Dev** had moved only by the generated-files refresh (`f918c97`), which this branch does not
  touch. The spec on `origin/dev` differs only in its phase. No sync was needed.
* **Affected set:** `uv run scripts/affected_tests.py` chose **124 of 744 test files** (16.7%) from
  8 changed files, smoke, e2e and the partition proof among them. Run once as
  `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run`: **stopped at its
  115-second limit at 63%, with about 3,488 passed and none failed before the stop**, and no process
  left behind. It is over two minutes, so under agreement 10 it is left to the pull request's `ci`.
* **Within two minutes instead:** `tests/architecture`, `tests/specs`, the three CLI always-run
  files, the discovery test directory, `test_not_configured_is_not_partial.py`,
  `test_federated_search.py`, `packages/debate_cli/tests/commands`, `test_search_command.py`,
  `test_search_presenter_not_configured.py`, `test_installation.py`, `test_config_command.py` and
  `tests/smoke/test_search_smoke.py`, with `-m "not slow and not live" -n 6` → `2305 passed in
  46.39s`. Also the one-process run above (`1482 passed`).
* **Whole-repo checks:**
  * `uv run --frozen ruff format --check .` → `2064 files already formatted`
  * `uv run --frozen ruff check .` → `All checks passed!`
  * `uv run --frozen pyright packages/debate_core packages/debate_cli` → `0 errors, 0 warnings, 0 informations`
  * `uv run --frozen lint-imports` → `Contracts: 20 kept, 0 broken.`
  * `scripts/check_thin_handlers.py` → `OK: 74 CLI command and API route handlers within 25 statements`
  * `uv run scripts/validate_specs.py` → `OK: 669 files, 41 epics, 606 tasks, 22 releases`
  * `scripts/docs_index.py --check-descriptions` → `All 70 indexed documents under docs/ have a description`
  * `scripts/check_links.py` → `OK: 3782 relative links and anchors in 648 Markdown files`
  * `scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments in 702 shell code blocks`

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
* `docs/guides/provider-credentials.md`: Semantic Scholar's row, without a key (Deviation 2).
* This report, and the spec's phase (InProgress, set at the start).

## Deviations from the spec

1. **Criterion ids.** The PM's message of 2026-11-12 calls the code criterion "ac2". In the spec it
   is ac3, and ac2 is the profiles. The PM confirmed the same day: keep the spec's ids.
2. **One guide row now, not with ac2.** `docs/guides/provider-credentials.md` said Semantic Scholar
   "is asked without a key, from the pool every keyless caller shares". That stops being true when
   this code half merges, so its row now says what the code does: not asked, named `not configured`
   with the cure, not counted as partial, and no profile enables it yet. The guides' full update for
   ac2 (what a key gives: one request a second, the later queries of an expanded search not asked,
   a 429 held with backoff) waits for the profiles.

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

**First attempt, 2026-11-12.** Block (a) stopped at its own guard: `the installed build is
v1.1.0-dev.407`. Nothing was searched. The PM's answers of the same day:
* install `v1.1.0-dev.413`, but only after the operator's landscape republish has finished (its
  publish and its delete), behind two guards: no `debate-research` command running, and the
  caselist-sync LaunchAgent not loaded;
* blocks (a) and (b) are accepted as written;
* (b) runs once right after (a). If it answers 429, it runs once more in the US afternoon. If
  that is 429 too, the operator stops and gives the PM both outputs.

**The install guard fires today (checked read-only from the session, 2026-11-12, about 00:40
Chicago).** `launchctl print gui/<uid>/com.debate-intelligence.caselist-sync` answers: the agent is
loaded, `state = not running`, `runs = 0`, `last exit code = (never exited)`. It is not in
`launchctl print-disabled`, its schedule is Weekday 3, 06:00 (Wednesday), and its plist and wrapper
are dated Oct 25. The likely cause is the cutover runbook's Step 2, which unloads the agent with
`launchctl bootout` and keeps the plist in `~/Library/LaunchAgents` for the fallback week. launchd
loads every plist in that folder at login, so a restart reloads it. The Mac's uptime was 2 h 14 min at
00:28, so it was booted around 22:14 on 2026-11-11, after that Wednesday's 06:00 slot. That fits
`runs = 0`, but the timeline is inferred, not measured. As the PM ruled, the install waits for the PM.

**The PM's answer (2026-11-12): option A.** The fallback week ended in early November, and no Mac run
is meant to happen. So the agent is unloaded with the cutover runbook's Step 2 block, verbatim, once the
landscape republish has finished. It is then disabled, so the unload survives a login. The plist and
the wrapper stay where they are; `launchctl enable` undoes the disable if a fallback is ever needed.
The PM files the runbook fix (Step 2 disables, and the fallback week's end retires the plist). It is
not this task's. Once the operator has run the blocks, launchctl's own lines are recorded here
(pending).

Unload, the cutover runbook's Step 2, verbatim. Success: `booted out`, `agent unloaded`, and the
plist's path listed.

```bash
if pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; else launchctl bootout "gui/$(id -u)/com.debate-intelligence.caselist-sync" && echo "booted out"; fi
launchctl print "gui/$(id -u)/com.debate-intelligence.caselist-sync" >/dev/null 2>&1 && echo "STOP: the agent is still loaded" || echo "agent unloaded"
ls "$HOME/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist"
```

Disable, the PM's block. Success: `disabled`, then `"com.debate-intelligence.caselist-sync" =>
disabled` (or `=> true`, as macOS may print it).

```bash
launchctl disable "gui/$(id -u)/com.debate-intelligence.caselist-sync" && echo "disabled"
launchctl print-disabled "gui/$(id -u)" | grep caselist-sync
```

**Run by the operator, 2026-11-12 (night, Chicago).**

* **The agent, found loaded after a reboot, unloaded and disabled.** Step 2 printed `booted out` and
  `agent unloaded`, and the plist is still in place. The disable printed `disabled`, then
  `launchctl print-disabled` printed `"com.debate-intelligence.caselist-sync" => disabled`.
* **The install.** `Installed debate-research 1.1.0.dev413 from v1.1.0-dev.413` and `installed
  build: v1.1.0-dev.413`. The check table read `Integrations failing none` and `Integrations import
  yes`. The runbook's "which uv manages" line fell outside `tail -5`. The session checked the
  interpreter read-only instead: the tool's Python resolves to uv's own `cpython-3.12.13`. It also
  checked the installed `semantic_scholar.py`, which sends `x-api-key` whenever a key is set, and the
  installed `resilience.py`, which carries v1-e07-t22 (`turn_came`, the 2 s backoff base).
* **(a) The keyed smoke: FAIL.** `status: FAILED`; `semantic_scholar: rate limited, 1 queries, 1
  failed, 0 results`; `reason: HTTP 429`, with no Retry-After; `results: 0`; `calls not asked: 0 of
  1`; `breaker: closed, errors 1, skipped 0`. Before the search, `doctor --providers` had reported
  the key as set. One request went out and was answered 429. (b) was not run: the PM's rulings
  cover a 429 on the keyless query, not on the keyed one.

* **The key's shape**, checked by the operator with two local commands. Neither used the network,
  and neither printed the value: one line names the variable, not commented out, the name exact,
  no quotes, no `export`, no carriage return, no spaces, no `#`. The value is 44 ASCII characters,
  and the one that is not a letter or digit is a `HYPHEN-MINUS` inside. There is no sign of a paste
  artefact. Whether 44 is the issued key's length is the operator's to compare (not recorded).
  The next live request is the PM's call.

0. **Install `v1.1.0-dev.413`**, about 2 minutes, from this worktree, after the landscape republish
   has finished. The block stops before installing if any `debate-research` command is running (it
   prints only the PIDs), or if `com.debate-intelligence.caselist-sync` is loaded. The cutover left
   that plist rewritten and not loaded, so **if the block says it is loaded, stop and tell the
   PM**. The install itself is the runbook's step (caselist-scheduled-sync.md, "Install the
   build"). Success ends with the build's `complete` line and `The build runs on the Python at …,
   which uv manages.`, then `installed build: v1.1.0-dev.413`.

   ```bash
   cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e07-t20-semantic-scholar-enabled-after-its-live-smoke
   if pgrep -f 'debate-research ' > /dev/null; then
     echo "STOP: a debate-research command is running (PIDs below). Let it finish, then paste the block again:"
     pgrep -f 'debate-research '
   elif launchctl print "gui/$(id -u)/com.debate-intelligence.caselist-sync" > /dev/null 2>&1; then
     echo "STOP: the caselist-sync LaunchAgent is loaded. The cutover left it not loaded: install nothing and tell the PM."
   else
     scripts/install_channel.sh v1.1.0-dev.413 2>&1 | tail -5
     echo "installed build: $(cd ~ && debate-research --json --version | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"]["tag"] or "untagged")')"
   fi
   ```

**Next, the PM's answer of 2026-11-12: one diagnostic request, after 13:00 Chicago.** A key issued
hours ago may not be active yet, so the 429's message is the point.
* **200 with `papers: 1`:** (a) runs once through debate-research, then (b) once right after it.
* **429 or 403:** its message goes to the PM, and nothing more is sent until the PM rules.

The key goes to curl on stdin (`-H @-`), never on a command line or in the output. The block prints
the status, the `Retry-After` and `x-ratelimit-*` headers, the body's `message` and `code`, and the
paper count. It never prints a title.

```bash
cd ~
OUT=$(mktemp)
HEAD=$(mktemp)
grep '^DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY=' ~/.debate-research/dev.env | sed 's/^DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY=/x-api-key: /' | curl -sS -o "${OUT}" -D "${HEAD}" -w 'HTTP %{http_code}\n' -H @- -G 'https://api.semanticscholar.org/graph/v1/paper/search' --data-urlencode 'query=carbon capture subsidies' --data-urlencode 'limit=1' --data-urlencode 'fields=paperId'
grep -iE '^(retry-after|x-ratelimit)' "${HEAD}"
python3 -I -c 'import json, sys; d = json.load(open(sys.argv[1])); print("message:", d.get("message")); print("code:", d.get("code")); print("papers:", len(d.get("data") or []))' "${OUT}"
rm -f "${OUT}" "${HEAD}"
```

Both smoke blocks run on the **installed** dev build, not this branch, and each stops before searching
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

2. **(b) One keyless single query**, once right after (a) (the PM, 2026-11-12: the quiet hour is
   unmeasured). The key is blanked for the search command alone, and nothing changes in your file.
   This must return results. Success is the same as (a): `status: COMPLETE`, `semantic_scholar: ok`,
   results above zero, `breaker: closed, errors 0`. **If it answers `HTTP 429`, run the same block
   once more in the US afternoon. If that is also 429, stop and give the PM both outputs.** This
   session enables nothing until the PM has recorded a pass.

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

0. **The rest of this task, after this partial merge.** The Goal stays InProgress. Once ac1 passes
   and the PM has recorded it, the task:
   * enables `semantic_scholar` in `config/profiles/dev.toml` and `prod.toml`, with the profiles'
     comments;
   * writes the tests on the committed profiles, shown failing first;
   * updates the search guide and `docs/guides/provider-credentials.md` with what a key gives;
   * runs the node's `-k profile` criterion;
   * sets the Goal to `Succeeded`.

1. **The adapter's keyless mode stays** (the PM, 2026-11-12). Only the factory refuses, and the tests
   pin both paths. If the shared pool ever proves usable, the PM can rule the factory back in with no
   new adapter code. Nothing to file.
2. **The "none of … is enabled" panel.** When every selected provider is not configured, the panel
   says `no provider was asked: none of semantic_scholar is enabled`. That is wrong for a provider
   that is enabled but not configured. The PM folds it into v1-e07-t23, which owns not-configured
   wording everywhere; this task leaves it alone.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-12

**Notes:**

Accepted for a partial merge (`scripts/task pr --partial`). The Goal stays InProgress: ac3 passes,
while ac1, ac2 and the node's `-k profile` criterion wait for the live smokes.

* **ac3, checked against the branch.** `semantic_scholar_factory` raises `ProviderNotConfigured` with
  `missing_key_reason()` when the key is unset, empty or spaces, before any client is built. The
  reason names the variable and never a value. `provider_credentials.py` carries the PM's cure in
  both the doctor row and the footer. The red commit `1732fac` comes before the code commit `369ff8a`,
  with 13 failures at assertions, grouped by reason. The five mutants were all caught. The note on the
  fifth is the right reading: the container test pins the outcome, and t04's adapter test pins the
  protection. The branch is on dev's tip (`d121fab`) and touches no profile, so nothing a student
  sees changes until ac2.
* **Decisions 1 to 4: accepted.**
  * The footer is the PM's sentence with the variable inserted, the GovInfo shape.
  * The cure on the doctor row is accepted: `doctor --providers` is where a student checks their setup.
  * Keeping the adapter's keyless mode matches the PM's ruling of 2026-11-12 (Follow-up 1).
  * A blank key is no key.
* **Deviation 2: accepted.** The guide row has to change when this half merges, or the guide would
  describe a keyless pool that no factory builds.
* **The keyed attempt (a).** The operator records call it FAIL. The PM records it as ac1 NOT RUN, not
  FAIL: one request, HTTP 429 with no Retry-After, on a key issued hours earlier. The breaker stayed
  closed and nothing more was sent, which is v1-e07-t22 working as agreed with Semantic Scholar. The
  next live request is the curl diagnostic after 13:00 Chicago. If it answers 200, (a) runs and then
  (b), each once. A 429 or 403 goes to the PM, and nothing more is sent. The PM records the outcome in
  the next batch. This report is not edited after its pull request opens.
* **Into the next PM batch:**
  * the caselist-sync LaunchAgent, found loaded after a reboot, then unloaded and disabled;
  * the cutover runbook fix: Step 2 disables the agent, and the fallback week's end retires the plist;
  * Follow-up 2, the "none of … is enabled" wording for an enabled provider that is not configured,
    folded into v1-e07-t23.
* **The rest of the task, after this merge:** the profiles, the guides' account of what a key gives,
  the tests on the committed profiles shown failing first, and `-k profile`. The session resumes them
  only after the PM has recorded ac1 as passed.

`scripts/task pr --partial`

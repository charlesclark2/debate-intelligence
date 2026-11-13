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

## Operator records (recorded by the PM, 2026-11-12)

Added by the PM. Nothing above is changed, and this section is not a review.

| Request (2026-11-12, Chicago) | Client and scheme | Answer |
|---|---|---|
| (a), the keyed smoke, at night | `debate-research` on `v1.1.0-dev.413`, HTTPS, `/paper/search` | HTTP 429, no Retry-After; one request, the breaker closed with 1 error |
| The diagnostic, about 19:40 | curl, HTTPS, `/paper/search`, the key on standard input | HTTP 429, "Too Many Requests. Please wait and try again or apply for a key for higher rate limits", no rate-limit headers |
| About 20:00, and again later | curl, HTTPS, `/paper/search/bulk` | the same 429 and message |
| Then | Insomnia, HTTP, `/paper/search/bulk` | **200**, `total` 484 |
| Then | Insomnia, HTTPS, the same request | 429 |
| Then | Insomnia, HTTP again | 200 |

The key in `~/.debate-research/dev.env` matches the emailed key (compared in the shell, 44 characters,
never printed). A listener on `127.0.0.1` showed that curl sends `x-api-key` with all 44 characters and
no whitespace. Semantic Scholar's tutorial (read by the PM, 2026-11-12) sends the key as `x-api-key`,
as the adapter does. So the same key, client and minute are recognised over HTTP and refused over
HTTPS. The operator reported it to Semantic Scholar on 2026-11-12. ac1 stays NOT RUN, not FAIL.

## Resumed 2026-11-12: Semantic Scholar's HTTP opt-in (ac4)

### Summary

**PARTIAL again. The Goal stays InProgress.** ac4 passes. `providers.semantic_scholar_insecure_http` is
false by default, and the per-user credentials file is now allowed to set it. With it on, the Semantic
Scholar adapter alone asks `http://api.semanticscholar.org`. Every other provider stays on HTTPS, and so
does Semantic Scholar with the setting off. No redirect is followed: over HTTP, one to HTTPS is a refusal
that says so. `doctor --providers` and a search that asked Semantic Scholar both say "Semantic Scholar
asked over HTTP: the key is sent unencrypted", and their JSON carries `asked_over_http`. No committed
profile sets the opt-in, and a test pins all three. The key never reaches a URL, a log line or any output,
in either mode. The guides say what the opt-in does, that it is the operator's choice for their own key,
and that it comes out with v1-e07-t26.

ac1 is still NOT RUN. Its two smokes are written under Operator follow-ups (resumed) and were not run. They
wait for the PM to say that v1-e39-t18's work on the operator's Mac has finished and that a dev build
carrying this branch is installed. ac2 (dev enables `semantic_scholar`, narrowed by the amendment) and the
node's `-k profile` criterion wait for ac1.

**Look first at** Deviations 3 and 4, which the PM ruled on 2026-11-12 (Decisions 6 and 7). Both stand as
built: the footer names the opt-in only on a search that asked Semantic Scholar, and the opt-in may be set
wherever any setting may be, except a committed profile.

### Plan nodes

| Node | Status | Notes |
|---|---|---|
| `semantic-scholar-enabled-after-its-live` (Semantic Scholar enabled) | Partial | ac4 done: tests red `e0d83db`, skeleton `889a57f`, code `e31d330`, a footer test `924af28`, guides `f512d37`, smoke `b6caa0c`. The profile and the node's criterion wait for ac1. |

### Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the operator's live smokes, keyless and keyed, have passed and are recorded by the PM | NOT RUN | Needs the operator, a dev build carrying this branch and the key. Blocks (a) and (b) are written below and were not run (the PM: no command today). |
| ac2: the dev profile enables semantic_scholar (narrowed, the PM's amendment of 2026-11-12) and the guides say what a student without a key sees, by tests on the committed profiles shown failing first | NOT RUN | Waits for ac1. The spec forbids enabling before the smoke has passed. |
| ac3: without a key Semantic Scholar is not configured, named with its cure and not counted, and with one it is built and asked | PASS (unchanged) | Merged in the partial (`dd13602`). Its tests ran green again below, inside `test_semantic_scholar.py`, `test_doctor_providers.py` and `test_search_command.py`. |
| ac4: with the opt-in unset the adapter asks HTTPS only; with it true it asks HTTP, follows no redirect and is named as unencrypted in doctor and the footer; no committed profile sets it; by tests shown failing first | PASS | Red, green, the planted profiles and the mutants below. |
| Node: `uv run pytest packages/debate_cli/tests -k profile` | NOT RUN | Run once the dev profile enables Semantic Scholar. |

### ac4: red, then green

**Red at the pre-task code.** The new and changed tests were committed alone. The command ran over the
five files they touch:

```text
.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/integrations/discovery/test_semantic_scholar.py packages/debate_core/tests/application/test_settings_user_credentials.py packages/debate_core/tests/application/test_settings.py packages/debate_cli/tests/commands/test_doctor_providers.py packages/debate_cli/tests/test_search_command.py -n 6 -q --tb=line -p no:cacheprovider
27 failed, 422 passed in 7.52s
```

At this commit the setting does not exist, so most of the 27 failed because an unknown setting was
refused, not at the assertions about the behaviour. Pydantic refused it in the adapter tests (`Extra inputs
are not permitted`), and the CLI refused it as a `CONFIGURATION_ERROR`. The settings tests failed on the
per-user file's message, which names four credentials where five are now expected. To get failures at the
assertions about the behaviour, I added a skeleton: the setting and its per-user-file name, and nothing
that reads them (`889a57f`). Its first run had 17 failures, and 8 of them were a `KeyError` or an
`IndexError`, not an assertion: the CLI tests indexed `asked_over_http` and a footer line that were not
there. I changed those tests to read the key with `.get()` and to slice the footer, folded the change
into the red commit (`e0d83db`, amended before the skeleton was committed), and ran again. The 27 above
were run on the red commit's first form.

**Red at the skeleton**, the same command, on the amended tests: `17 failed, 432 passed in 5.35s`. Every failure was at an
assertion:
* 7 `assert None == []`: no `asked_over_http` in the doctor or search JSON;
* 4 the redirect: `'…redirected to api.semanticscholar.org' == '…redirected to HTTPS at
  api.semanticscholar.org, not followed'`;
* 1 the request was `https://…`, not `http://…`;
* 1 the request schemes, `{'https'} == {'http'}`, in the redaction test in HTTP mode;
* 1 the doctor rows: no `Warning` row;
* 1 the doctor JSON pin, which now has `"asked_over_http": []`;
* 1 the footer: `[] == ['  Semantic Scholar asked over HTTP: the key is sent unencrypted']`;
* 1 `assert False`: the search's redaction test found no request over `http`.

These passed at the skeleton, as they should: the three that pin HTTPS when the setting is unset or false
(`test_with_the_opt_in_unset…`, `…off_explicitly…`, the redaction test in HTTPS mode), the redirect to
another host, which keeps its old message, and the settings tests, because the skeleton is what they test.

**No committed profile sets it.** `test_no_committed_profile_sets_semantic_scholar_s_http_opt_in` reads
every `config/profiles/*.toml` as TOML and looks for the key at any depth. It passes on the committed
profiles. I planted `semantic_scholar_insecure_http = true` under `[providers]` in each profile in turn,
ran the test alone, and restored the file from a copy (checked with `cmp`):

| Planted in | Result |
|---|---|
| `dev.toml` | `1 failed`: `AssertionError: dev.toml` |
| `prod.toml` | `1 failed`: `AssertionError: prod.toml` |
| `test.toml` | first try `1 failed` with `TOMLDecodeError` (I had appended a second `[providers]` table), not a catch; redone under its existing `[providers]`: `1 failed`: `AssertionError: test.toml` |

**Green.** The same five files: `449 passed in 5.23s`. With the footer test added afterwards (`924af28`),
`-k http`: `6 passed`.

**Mutants.** Each was applied to the committed file and run over the five test files with
`PYTHONDONTWRITEBYTECODE=1` and a fresh `HYPOTHESIS_STORAGE_DIRECTORY`, then restored with
`git checkout HEAD --`. The tree was clean after each batch. All were caught at assertions.

| Mutant | Failed |
|---|---|
| the base URL always HTTPS | 8 |
| the base URL always HTTP | 55 |
| the factory does not pass the setting | 8 |
| over HTTP, a redirect to HTTPS gets the plain redirect message | 4 |
| over HTTP, the client follows redirects | 5 (`TooManyRedirects` where the named refusal was expected) |
| "built" ignores the key | 1 (doctor, opted in without a key) |
| "built" ignores `providers.enabled` | 1 (doctor, opted in and not enabled) |
| the naming ignores the opt-in | 4 |
| the warning loses "unencrypted" | 3 |
| the search names it whether or not it asked Semantic Scholar | 1 |
| the footer never prints the warning | 1 |
| the search JSON's `asked_over_http` always empty | 1 |
| doctor prints no `Warning` row | 1 |
| the container passes no providers asked over HTTP | 1 |
| the per-user file refuses the opt-in | 10 |

`924af28`'s footer test was written after the code, so it passed on its first run. Under the two redirect
mutants it failed: the plain message (the footer line differed) and following redirects (exit code). The
smoke check (`b6caa0c`) failed under "doctor prints no `Warning` row" and "the per-user file refuses the
opt-in".

### Checks before the report

* **Dev** moved by `3cfd4af` (v1-e08-t26, the end-to-end auto-cut tests) and the generated-files refresh.
  Neither touches a file this branch changes, so no sync was needed. The spec and this report on
  `origin/dev` are the same as on the branch.
* **Affected set:** `uv run scripts/affected_tests.py` chose **755 test files**, effectively the whole
  selection. `settings.py` changed, and the root `conftest.py` imports it. That is well over two minutes,
  so under agreement 10 it is left to the pull request's `ci`, and I did not hand it over.
* **Run within two minutes instead**, each with `-m "not slow and not live" -n 6` under `hard_stop.py 115`:
  * `tests/architecture`, `tests/specs`, the CLI's always-run files (`test_app.py`,
    `test_help_rendering.py`, `test_container_factories.py`), the discovery test directory,
    `packages/debate_cli/tests/commands`, `test_search_command.py`, the four search presenter test files,
    `test_presenters_configuration_gaps_named_with_their_cure.py`, `test_installation.py`,
    `test_config_command.py`, `test_daily_command.py`, `tests/smoke/test_cli_smoke.py` and
    `tests/smoke/test_search_smoke.py` → `2408 passed in 52.01s`;
  * the application tests that touch what changed (`test_digest_service.py`, the five
    `test_federated_*.py`, `test_not_configured_is_not_partial.py`, the nine `test_settings*.py`) →
    `668 passed in 4.50s`;
  * the whole `packages/debate_core/tests/application` directory: **stopped at its 115-second limit at
    about 98%, with no failure printed before the stop**, so it is left to `ci`. My first attempt put it
    in the run above, and that run was stopped at its limit too.
* **One process, the logging tests after their neighbours** (`-n 0 -p no:randomly`): the OpenCaselist
  suite, `test_http_fetcher.py`, the 15 other discovery test files, then `test_semantic_scholar.py` last →
  `1525 passed in 3.77s`.
* **Whole-repo checks:**
  * `uv run --frozen ruff format --check .` → `2091 files already formatted`
  * `uv run --frozen ruff check .` → `All checks passed!`
  * `uv run --frozen pyright` (the whole project, as CI runs it) → `0 errors, 0 warnings, 0 informations`
  * `uv run --frozen lint-imports` → `Contracts: 20 kept, 0 broken.`
  * `uv run scripts/check_thin_handlers.py` → `OK: 74 CLI command and API route handlers within 25 statements`
  * `uv run scripts/validate_specs.py` → `OK: 678 files, 41 epics, 615 tasks, 22 releases`
  * `uv run scripts/docs_index.py --check-descriptions` → `All 71 indexed documents under docs/ have a description`
  * `uv run scripts/check_links.py` → `OK: 3816 relative links and anchors in 658 Markdown files`
  * `uv run scripts/check_command_blocks.py --base origin/dev`, run again with this report →
    `OK: no # comments in 712 shell code blocks in 259 Markdown files (1 session reports changed since origin/dev)`

### Files changed

* `packages/debate_core/src/debate_core/application/settings.py`: `ProviderSettings.semantic_scholar_insecure_http`
  (false by default, with its description), and `DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_INSECURE_HTTP` in
  `USER_CREDENTIAL_VARIABLES`, with the docstring saying why it is the one name there that is not a
  credential.
* `packages/debate_core/src/debate_core/integrations/discovery/semantic_scholar.py`:
  `PAPER_SEARCH_URL_OVER_HTTP`, `paper_search_url()`, `redirect_to_https_failure()`, the adapter's
  `insecure_http`, and the factory passing the setting through. The module and factory docstrings are
  updated.
* `packages/debate_core/src/debate_core/application/provider_credentials.py`: `providers_asked_over_http()`
  (the opt-in on, Semantic Scholar enabled, a key that is not blank), `over_http_warning()`,
  `OverHttpNotice`, and the report's `asked_over_http`.
* `packages/debate_core/src/debate_core/application/federated_search.py` and `federated_search_types.py`:
  `FederatedSearchService(asked_over_http=…)` and `SearchOutcome.asked_over_http`, keeping only the
  providers this search asked.
* `packages/debate_cli/src/debate_cli/container.py`: passes `providers_asked_over_http(settings.providers)`.
* `packages/debate_cli/src/debate_cli/presenters/search_presenter.py`: the warning line under the
  provider's footer line, and the JSON's `asked_over_http`.
* `packages/debate_cli/src/debate_cli/commands/doctor.py`: the `Warning` row.
* Tests: `test_semantic_scholar.py` (6 tests, 10 cases), `test_settings_user_credentials.py` (1 new
  test; 5 changed for the fifth name: the list itself, the secret-or-excluded check, and the three
  refusal messages that name every credential), `test_settings.py` (the committed-profile pin),
  `test_doctor_providers.py` (2 new tests, 5 cases, and the JSON pin), `test_search_command.py`
  (6 new tests, and a redirect switch in the recorded answers), `tests/smoke/test_cli_smoke.py`
  (1 new check, Deviation 1).
* `docs/guides/provider-credentials.md`: a table row and the section "Semantic Scholar over HTTP: your
  choice for your own key". `packages/debate_cli/README.md`: the search guide's paragraph (Deviation 2)
  and the doctor section.
* This report.

### Deviations from the spec

1. **A smoke check outside the task's packages.** `tests/smoke/test_cli_smoke.py` is not in
   `constraints.packages`. Agreement 5 asks for a smoke check when a user-facing surface changes, and
   `doctor --providers` has a new row and a new JSON key. The check shows that the build reads the opt-in
   from the per-user file and that `doctor` names it. It reaches no network. v1-e07-t13 did the same for
   `test_search_smoke.py`.
2. **The search guide is the CLI README's search section**, as v1-e07-t13 found and the PM accepted:
   there is no search guide under `docs/guides/`.
3. **The footer names the opt-in only when the search asked Semantic Scholar.** The PM's words are
   "whenever the opt-in is on and Semantic Scholar is built". A search that does not ask Semantic Scholar
   (`--providers openalex,crossref`, or a topic that leaves it out) sends no key. Saying "Semantic Scholar
   asked over HTTP" there would be untrue, so its footer says nothing about HTTP, and a test pins that.
   `doctor --providers` follows the PM's words exactly: it names the opt-in whenever Semantic Scholar is
   built. The PM ruled this as built on 2026-11-12 (Decision 6).
4. **The opt-in is read from a variable or a `.env` too.** The amendment says it is "set only in a
   person's own credentials file and never in a committed profile". The PM's ruling for this session
   adds it to `USER_CREDENTIAL_VARIABLES` and pins the profiles, and it is what I built. Like every
   setting, the opt-in can also come from `DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_INSECURE_HTTP` in the shell
   or a `.env`. The CLI tests set it that way. Refusing it from those places would be a new rule for one
   setting. The PM ruled this as built on 2026-11-12 (Decision 7).
5. **The daily digest's footer is not wired.** No preset in `config/daily_presets.yaml` asks Semantic
   Scholar, so the line could never appear there and could not be tested. I removed the digest property
   I had started on, rather than leave code no test reaches. A preset that adds Semantic Scholar would
   pass `asked_over_http` to `status_footer_lines` in `daily_presenter.digest_footer`. The `research`
   batch report goes through `footer_lines(outcome)`, so it gets the line already.

### Decisions and assumptions

1. **The JSON shape.** `asked_over_http` is a list of `{"provider": "semantic_scholar", "warning":
   "Semantic Scholar asked over HTTP: the key is sent unencrypted"}`. In doctor's report it sits under
   `providers`. In a search it is top-level in `data`, or in `error.details` on a failure. It is an empty
   list otherwise. Carrying the sentence lets any client print the PM's words without knowing them.
2. **The doctor row is labelled `Warning`** and comes after the provider rows: `Warning | Semantic Scholar
   asked over HTTP: the key is sent unencrypted`.
3. **The redirect's words:** `semantic_scholar: HTTP 301: redirected to HTTPS at api.semanticscholar.org,
   not followed`. That is the scheme and host only, as `redirect_failure` names only the host. A redirect
   to another plain-HTTP host keeps the existing message.
4. **"Built" means enabled, with a key that is not blank, and the opt-in on.** That is exactly what the
   factory builds. The rule is in `debate_core` (`providers_asked_over_http`), and doctor and the
   container both read it. Without a key, Semantic Scholar is not configured, so nothing is said, as the
   PM's "and Semantic Scholar is built" asks.
5. **The guides call the opt-in the operator's choice for their own key**, say what crossing the network
   unencrypted means, and say that it comes out with v1-e07-t26, whose spec refuses a file that still
   sets it.
6. **The PM's ruling on Q1, 2026-11-12: option A, as built.** The footer line "Semantic Scholar asked over
   HTTP: the key is sent unencrypted" appears only on a search that asked Semantic Scholar. A search that
   left it out sent no key and says nothing about HTTP. `doctor --providers` names the opt-in whenever
   Semantic Scholar is built (enabled, with a key, and the opt-in on). Pinned by
   `test_with_the_http_opt_in_a_search_that_does_not_ask_semantic_scholar_says_nothing_of_http` and by the
   doctor tests. Nothing changed.
7. **The PM's ruling on Q2, 2026-11-12: option A, as built.** The opt-in may be set wherever any setting
   may be (the per-user file, an exported variable, a `.env`) except a committed profile. That exception
   is pinned by `test_no_committed_profile_sets_semantic_scholar_s_http_opt_in`. The guides point people
   to the per-user file. Nothing changed.

### Operator follow-ups (resumed, 2026-11-12): written, not run

**Do not run these today.** Both wait until the PM says that v1-e39-t18's work on the operator's Mac has
finished and that a dev build carrying this branch is installed. The PM handles the install, so no install
block is given here. The key is never printed, logged, put on a command line or committed.

**(a1) Add the opt-in line to your own file**, once, before (a). This is your consent to Semantic Scholar
alone being asked over plain HTTP, which sends your key unencrypted. The block changes only
`~/.debate-research/dev.env`. If the file is missing, it stops. If the line is already there, it does
nothing. If the file's last line has no newline, it adds one first, so the new line never joins your key's
line. It prints how many opt-in lines the file has and the file's permissions, never a value. Success:
`opt-in lines: 1` and `-rw-------`.

```bash
cd ~
if [ ! -f ~/.debate-research/dev.env ]; then
  echo "STOP: ~/.debate-research/dev.env is not there. docs/guides/provider-credentials.md says how to write it."
elif grep -q '^DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_INSECURE_HTTP=' ~/.debate-research/dev.env; then
  echo "already set, nothing changed"
else
  if [ -n "$(tail -c1 ~/.debate-research/dev.env)" ]; then printf '\n' >> ~/.debate-research/dev.env; fi
  printf 'DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_INSECURE_HTTP=true\n' >> ~/.debate-research/dev.env
  echo "added the opt-in line"
fi
echo "opt-in lines: $(grep -c '^DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_INSECURE_HTTP=' ~/.debate-research/dev.env)"
stat -f '%Sp' ~/.debate-research/dev.env
```

**(a) The keyed smoke, over HTTP.** One search, Semantic Scholar alone, from your home folder so no `.env`
takes part. It prints statuses and counts only, never a title or the key. It stops before searching in
these cases:
* a `DEBATE_` variable is set in the shell (it prints the names only);
* a `caselist pull` is running;
* the installed build does not carry this branch: `doctor --providers` has no `asked_over_http`;
* the build carries it but `doctor` does not name Semantic Scholar: the opt-in line or the key is missing
  from the file.

Like any search, it writes the search and up to 20 discovery-only Articles to your local dev store. It
takes a few seconds and costs nothing.

Success looks like this:
* `asked over HTTP: semantic_scholar`;
* `status: COMPLETE`;
* `semantic_scholar: ok, 1 queries, 0 failed, N results`, with N above zero;
* `results:` above zero, and equal to `with an S2 id`;
* `calls not asked: 0 of 1`;
* `breaker: closed, errors 0, skipped 0`.

A reason of `HTTP 429` means HTTP throttled the key too. One that reads `redirected to HTTPS … not
followed` means Semantic Scholar now sends HTTP to HTTPS. Paste the output back either way.

```bash
cd ~
if env | grep -q '^DEBATE_'; then
  echo "STOP: DEBATE_ variables are set in this shell. Unset each of these and paste the block again:"
  env | grep '^DEBATE_' | cut -d= -f1
elif pgrep -f "debate-research caselist pull" > /dev/null; then
  echo "STOP: a caselist pull is running. Paste the block again once it has finished."
else
  TAG=$(debate-research --json --version | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"]["tag"] or "untagged")')
  OVER_HTTP=$(env DEBATE_PROVIDERS__ENABLED='["semantic_scholar"]' debate-research --json doctor --providers | python3 -I -c 'import json, sys; d = (json.load(sys.stdin).get("data") or {}).get("providers") or {}; print("absent" if "asked_over_http" not in d else ",".join(n["provider"] for n in d["asked_over_http"]) or "none")')
  if [ "${OVER_HTTP}" = "absent" ]; then
    echo "STOP: the installed build ${TAG} does not carry v1-e07-t20's opt-in. Tell the PM."
  elif [ "${OVER_HTTP}" != "semantic_scholar" ]; then
    echo "STOP: doctor --providers does not name Semantic Scholar as asked over HTTP. Run debate-research doctor --providers: the key or the opt-in line is missing from ~/.debate-research/dev.env."
  else
    echo "installed build: ${TAG}"
    OUT=$(mktemp)
    env DEBATE_PROVIDERS__ENABLED='["semantic_scholar"]' debate-research search "carbon capture subsidies" --format json > "${OUT}"
    python3 -I - "${OUT}" <<'EOF'
import json
import sys

document = json.load(open(sys.argv[1]))
body = document.get("data") or (document.get("error") or {}).get("details") or {}
results = body.get("results") or []
if not body:
    print(f"no search answer: error code {(document.get('error') or {}).get('code')}")
print(f"asked over HTTP: {', '.join(n['provider'] for n in body.get('asked_over_http') or []) or 'none'}")
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

**(b) The keyless query: one curl request over HTTPS, with no key header.** It needs no particular build,
and the amendment asks for it on a quiet day. `-q` keeps curl from reading a `~/.curlrc`, so no header can
come from one. It prints the status, the body's `message` and the paper count, never a title. Success:
`HTTP 200` and `papers: 1`. A `429` goes to the PM with its message, and nothing more is sent.

```bash
cd ~
OUT=$(mktemp)
curl -q -sS -o "${OUT}" -w 'HTTP %{http_code}\n' -G 'https://api.semanticscholar.org/graph/v1/paper/search' --data-urlencode 'query=carbon capture subsidies' --data-urlencode 'limit=1' --data-urlencode 'fields=paperId'
python3 -I -c 'import json, sys; d = json.load(open(sys.argv[1])); print("message:", d.get("message")); print("papers:", len(d.get("data") or []))' "${OUT}"
rm -f "${OUT}"
```

**If (a) passes,** the session resumes for ac2 as narrowed: the dev profile enables `semantic_scholar`,
with its comment, and prod waits for v1-e07-t26. That comes with tests on the committed profiles shown
failing first, the guides' account of what a key gives, and the node's `-k profile` criterion. Then the
Goal can be Succeeded.

### Questions for the PM (relay block)

Answered by the PM on 2026-11-12: Q1 A and Q2 A, both as built (Decisions 6 and 7). The block is kept as
it was asked.

```text
v1-e07-t20 (resumed 2026-11-12), two questions on ac4. Both are built as recommended; either answer is a small change.

Q1. When does a search's footer say "Semantic Scholar asked over HTTP: the key is sent unencrypted"?
  A (built, recommended): only when this search asked Semantic Scholar. A search that left it out (--providers openalex,crossref, or a topic without it) sent no key, so saying it was "asked over HTTP" would be untrue. doctor --providers names it whenever Semantic Scholar is built, as the amendment says.
  B: on every search while the opt-in is on and Semantic Scholar is built, asked or not.
  Why A: the footer describes what this search did; doctor describes the setup.

Q2. Where may the opt-in be set?
  A (built, recommended): wherever any setting may be, except a committed profile, which a test pins. That means the per-user file, an exported variable or a .env. The guides tell people to use the per-user file.
  B: the per-user file only. Loading would refuse DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_INSECURE_HTTP from a variable or a .env, a rule no other setting has.
  Why A: an exported variable is still the person's own act, on their own machine. v1-e07-t26 removes the setting soon, and the tests set it as a variable.
```

### Follow-up work

1. **The rest of this task** after (a) passes, as above.
2. **If a daily preset ever asks Semantic Scholar** while the opt-in exists, `digest_footer` needs to pass
   `asked_over_http` (Deviation 5). Nothing to file while v1-e07-t26 is due to remove the opt-in.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

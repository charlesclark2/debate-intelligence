# Session report: v1-e06-t06-cut-command

| | |
|---|---|
| Task | `v1-e06-t06-cut-command` — `debate-research cut` command |
| Spec | [`plan_specs/v1/e06-card-cutting/t06-cut-command.yaml`](../../plan_specs/v1/e06-card-cutting/t06-cut-command.yaml) |
| Epic / release | `v1-e06-card-cutting` / `v1.3` |
| Branch | `task/v1-e06-t06-cut-command` |
| Session status | COMPLETE |

## Summary

`debate-research cut <URL> --need "..." [--argument ...] [--format team-default|flow|plain] --output card.docx [--json]`
is built. The composition root wires it: CardService (CardSelector over the real guard and router,
CitationService with the Crossref client over a `FileDoiCache`, the verifier, the SQLite and blob
stores), ExportService with `render_cards_docx`, and the prompt registry and format profiles read from
an installed build's bundled copy. The command runs ArticleFetch, CardService and ExportService in
order and holds no business logic. It prints one progress line per stage on stderr, and exits with the
PM's codes: 0 verified, 2 usage, 3 not retrievable or the provider did not answer, 4 `CARD_UNVERIFIED`
(the card is written with its banner), 1 could not run. `stamp_build.py` now bundles `prompts/` and
`config/format_profiles/`. An installed-build smoke check cuts a verified .docx offline. It was shown
red on a wheel stamped by the old script and green on this branch's.

Every criterion passes. The Goal is `Succeeded`. The PM should look first at:

1. **Deviation 3, `--json` and the manifest.** stdout carries the manifest's identity, not its
   evidence text, because `output.py` forbids evidence text in any `--json` payload.
2. **Deviation 2.** `scripts/stamp_build.py` and its tests are outside `constraints.packages`.
3. **The affected set** (208 files, before the pyproject edit) stopped at the 115-second limit at 16%,
   with no failure up to then. After the pyproject edit the whole selection is affected. Both are left
   to the pull request's `ci`, as agreement 10 says.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `command-wiring` (Typer command and service wiring) | Done | `commands/cut.py`; `ServiceContainer.card_cutting()`, `format_profiles()` and the cut router in `container.py`; registered in `command_registry.py`. |
| `progress-and-errors` (Rich progress and explicit failure messages) | Done | `presenters/cut_presenter.py`: stage lines, words for each access status and failure reason, the payload, the exit-3 and exit-4 panels. `ExitCode.CARD_UNVERIFIED = 4`. |
| `fixture-cli-tests` (CLI tests on recorded fixtures) | Done | `packages/debate_cli/tests/test_cut_command.py`, 23 tests, over e04-t06's cassettes, respx Crossref answers, and the fixture fake and scripted routers. |
| PM amendments: python-docx, bundled prompts, verify wording, smoke | Done | `debate_core` `docx` extra and `uv.lock`; `stamp_build.py`; `verify.py` and the CLI README; `tests/smoke/test_cut_smoke.py`. |

## Acceptance criteria

All commands ran in the task worktree. Each test run was bounded by `scripts/hard_stop.py 115`.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a recorded accessible article with fake-router fixtures, `--format team-default --output out.docx`, exits 0 with tag, cite, underlined evidence and manifest | PASS | `test_a_verified_card_exit_code_is_0_and_the_docx_holds_tag_cite_underlined_evidence_and_manifest`. It reads the .docx back: Heading4 tag, the full cite, the three underlined passages (worked out by hand from the markup fixture's offsets), and the embedded manifest card with `EVIDENCE` and VERIFIED. `test_the_embedded_manifest_verifies_against_the_stored_snapshot` runs `verify` on the embedded manifest: exit 0. The criterion's command line omits `--need`, which the description requires (Decisions 1). |
| ac2: a recorded paywalled URL exits 3 with PAYWALLED and the canonical URL; no DOCX | PASS | `test_a_paywalled_url_exit_code_is_3_with_its_status_and_canonical_url_and_no_docx`: exit 3, PAYWALLED and the canonical URL on stderr, no file, no card row, zero model calls. `test_every_other_retrieval_status_exit_code_is_3_and_writes_nothing` covers BLOCKED, ROBOTS_DISALLOWED and NOT_FOUND. |
| ac3: an UNVERIFIED card exits 4, each reason printed, banner in the DOCX | PASS | `test_an_unverified_card_exit_code_is_4_with_each_reason_printed_and_the_banner_in_the_docx`: a refused markup (t02's e2e case) gives exit 4. MODEL_OUTPUT_INVALID, EVIDENCE_UNVERIFIED and CARD_INCOMPLETE are all on stderr. The .docx holds `UNVERIFIED — not a finished card: MODEL_OUTPUT_INVALID, EVIDENCE_UNVERIFIED, CARD_INCOMPLETE`. The JSON form is `test_an_unverified_card_under_json_exit_code_is_4_with_the_reasons_in_the_error`. |
| ac4: `--json` writes one object (CutResult with manifest) to stdout, progress to stderr; `cut --help` documents every option and exit code | PASS, with Deviation 3 | `test_json_writes_one_object_to_stdout_and_progress_to_stderr` (with `--json` before and after the command): one line on stdout, and five event objects on stderr, in stage order. `test_the_help_documents_every_option_and_exit_code` covers the help. The manifest in the payload is its identity, not its evidence text. |
| ac5: an installed wheel holds `prompts/` and the command loads the registry from it, by an installed-build smoke test; a refused model call exits with the non-retryable code, by test | PASS | `tests/smoke/test_cut_smoke.py`, run against two locally stamped, installed builds of commit `9c5832f`, built offline: one stamped by the start commit's `stamp_build.py` gave `2 failed, 1 passed`, with no bundled prompts and `cut` exiting 1. The one stamped by this branch's gave `3 passed`, and `check-wheels` on its dist printed `publishable`. Against the checkout's console script, as CI runs it: `3 passed`. The refused call: `test_a_model_call_that_failed_exit_code_is_its_own_and_saves_and_writes_nothing`, where MODEL_ACCESS_DENIED and MODEL_REQUEST_REJECTED give 1, PROVIDER_UNAVAILABLE and PROVIDER_RATE_LIMITED give 3, and nothing is saved or written. validate-dev runs the smoke check against the published pre-release after merge. |
| `command-wiring`: cut help renders | PASS | `uv run --frozen debate-research cut --help` → exit 0 |
| `progress-and-errors`: presenter and exit-code tests pass | PASS | `uv run --frozen pytest packages/debate_cli/tests/test_cut_command.py -k exit_code` → `15 passed` |
| `fixture-cli-tests`: cut command tests pass offline | PASS | `uv run --frozen pytest packages/debate_cli/tests/test_cut_command.py` → `23 passed in 3.56s` |
| `fixture-cli-tests`: import boundaries hold | PASS | `uv run --frozen lint-imports` → `Contracts: 20 kept, 0 broken.`; `scripts/check_thin_handlers.py` → `71 ... handlers within 25 statements` |

### Red first

* **Against a skeleton** (options and help only, success with nothing done, commit `58a6c5f`):
  `test_cut_command.py` gave `20 failed, 2 passed`. The two that passed were the help and the
  missing `--need`, which the skeleton's options already satisfy.
* **Pinned wiring lists**, before they were updated: 7 failed, each for the new integration, service
  or command.
* **verify's wording**: 3 failed (help line, README row, the newer-build hint).
* **stamp_build**: 7 failed, either nothing bundled or the members not yet required.
* **Installed build**: as in ac5.

### Mutants

Each mutant was run against `test_cut_command.py` and restored with `git checkout HEAD --`. Every one
failed at an assertion.

| Mutant | Result |
|---|---|
| An UNVERIFIED card exits 0: its failure carries `ExitCode.OK` | caught by both exit-4 tests |
| An UNVERIFIED card exits 0: the unverified branch is skipped | caught by both exit-4 tests |
| A DOCX is written for a paywalled URL (bytes written before the exit-3 report) | caught by the paywalled test and all three other statuses |
| Progress goes to stdout under `--json` (`print` in place of `event_line`) | caught by 12 tests, the `--json` and progress tests among them |
| A refused model call exits 3 (the `REFUSED_MODEL_CALLS` check removed from `exit_code_for`) | caught by MODEL_ACCESS_DENIED and MODEL_REQUEST_REJECTED |
| CitationService built without the Crossref client | caught by `test_a_journal_pdf_is_cited_from_crossref_through_the_file_cache_and_asked_once` (exit 4 instead of 0) |

### Before the report

* **Affected set**: `scripts/affected_tests.py --run` on commit `326eabc`, before the pyproject edit.
  It selected 208 files and was stopped by `hard_stop.py` at 115 s, at 16%, with no failure up to the
  stop. Load average was 3 to 9. It is left to the pull request's `ci` (agreement 10).
* **Changed areas and the always-run list**, in one bounded run: `tests/architecture`, `tests/specs`,
  `test_app`, `test_help_rendering`, `test_container_factories`, `test_cut_command`,
  `test_verify_command`, `test_installation`, `test_doctor`, `test_bucket_mode_lock`, `test_output`,
  `test_fetch_command`, `tests/integration/test_fetch_cli.py`, `tests/scripts/test_stamp_build.py`,
  and `tests/smoke/test_cut_smoke.py`, `test_cli_smoke.py` and `test_fetch_smoke.py`. Result:
  `753 passed in 47.79s`.
* **After the pyproject and lock edit**: `uv sync --frozen --offline --all-packages`, then the wiring
  tests, the cut tests and the cut smoke check: `132 passed`. `affected_tests.py` now reports "The
  whole selection is affected: packages/debate_core/pyproject.toml is shared test ground". That run
  is CI's.
* **Lint and checks**:
  * `ruff format --check .` → `1784 files already formatted`; `ruff check .` → `All checks passed!`.
  * `pyright packages/debate_cli packages/debate_core` plus the new test and script files → `0 errors`.
  * `lint-imports` → 20 kept.
  * `validate_specs.py` → `OK: 567 files`.
  * `check_command_blocks.py` and `check_links.py` → OK.
  * `uv lock --check --offline` → exit 0 on the committed lock, and exit 1 on the old lock against
    the new pyproject.

## Files changed

* **`packages/debate_cli/src/debate_cli/`**
  * `commands/cut.py` (new): the command.
  * `presenters/cut_presenter.py` (new): stages, words, payload, panels.
  * `container.py`: `card_cutting`, `format_profiles`, the cut router, `CardCutting`,
    `LOCAL_OWNER_ID`, `CARD_CASSETTES_DIRECTORY`, the empty edit log, and lookup of the committed
    prompts and profiles.
  * `exit_codes.py`: `CARD_UNVERIFIED = 4`, and the docstring contract.
  * `command_registry.py`: registers `cut`.
  * `commands/verify.py`: the exit-2 wording and the newer-build hint.
  * `build_info.py`: docstring.
* **`packages/debate_cli/README.md`**: exit code 4, verify's exit-2 row, and a `cut` section.
* **`packages/debate_cli/tests/`**
  * `test_cut_command.py` (new).
  * `test_verify_command.py`: the wording.
  * The lists pinned where the wiring changed: `test_installation.py` (crossref_doi, 35
    integrations, httpx), `commands/test_doctor.py`, `test_app.py` (the `card_cutting` service) and
    `bucket_mode/test_bucket_mode_lock.py` (`cut` writes no bucket).
* **`tests/smoke/test_cut_smoke.py`** (new): the installed-build check.
* **`packages/debate_core/pyproject.toml`, `uv.lock`**: python-docx in the `docx` extra.
* **`scripts/stamp_build.py`, `tests/scripts/test_stamp_build.py`**: bundle `prompts/` and
  `config/format_profiles/`; `check-wheels` requires both card prompts and `team-default.yaml`
  (Deviation 2).
* **`plan_specs/v1/e06-card-cutting/t06-cut-command.yaml`**: the PM's exit-code amendment, and the
  Goal set to `Succeeded`.

## Deviations from the spec

1. **The exit codes** (the PM's ruling, written into the spec as the dated amendment of 2026-11-01).
   It supersedes the description's "5 model/config error". `exit_code_for`'s mapping needed no change,
   because every "could not run" case is already a `DomainError` (exit 1): `NotFound`,
   `SnapshotIntegrityError`, `UnknownPromptError`, `MissingFixtureError` and `ConfigurationError`. A
   refused call was already 1, and an outage or throttle 3. The only change is the new member,
   `CARD_UNVERIFIED = 4`, which the command reports as an outcome, as `verify` reports its exit 1.
   `exit_codes.py`'s docstring now gives `1` as "`verify` found a card UNVERIFIED", because `cut`'s
   UNVERIFIED is 4.
2. **Two files outside `constraints.packages`.** ac5's bundled `prompts/` cannot come from a
   pyproject: uv_build packs only the module root. So the stamp step that already bundles `config/`
   bundles `prompts/` too, and `config/format_profiles/` beside it, which `--format` needs in an
   installed build. That step is `scripts/stamp_build.py`, with its tests in
   `tests/scripts/test_stamp_build.py`. Proposed spec edit: add both paths to `constraints.packages`.
3. **ac4's "CutResult with manifest" on stdout.** The manifest is the card as the domain serializes
   it, `evidence_text` included. `debate_cli/output.py` says a `--json` payload never carries evidence
   text, "and that rule is not relaxed because the output is machine-readable". So `data` (exit 0) and
   `error.details` (exit 4) carry:
   * the CutResult: card id, status, every reason with its detail, fields and verifier code, and each
     model call's provenance;
   * the source: requested and canonical URL, status, snapshot id, whether it was fetched;
   * the manifest's identity: version, `generated_at`, card ids, snapshot references (ids, hashes,
     URL, no text) and the SHA-256 of the manifest bytes embedded in the .docx.

   The whole manifest is in the .docx, where `verify` reads it (the ac1 test above). If the PM wants
   the whole manifest on stdout, it is one line in `cut_payload`, plus a sentence in `output.py`'s
   rule naming the exception (question 1).

## Decisions and assumptions

1. **`--need` is required.** The description's command line has it unbracketed, and `CutRequest`
   refuses a blank need. ac1's shorthand command and the epic's omit it, so I read them as written
   with the need. Without `--need` the command exits 2 and nothing is fetched.
2. **Model mode comes from `DEBATE_MODEL_MODE` alone, defaulting to replay.** That is the one
   control v1-e05-t03 set, "so that a program nobody configured never reaches a real model". `cut`
   adds no option. Cassettes are kept in `<data dir>/cards/model-cassettes/`, never committed, because
   they hold the articles' numbered text, as the landscape's do. So a coach's run needs
   `DEBATE_MODEL_MODE=live`. Without it, an unrecorded call exits 1 with `MISSING_FIXTURE_ERROR`, and
   the error's own hint says to record. The help, the command docstring and the README say so
   (question 3).
3. **Prompts and format profiles come from the build itself.** An installed build reads its
   `_bundled_config/`. A source checkout reads the checkout its code runs from
   (`find_repository_root` of the package directory), not the checkout around the working directory,
   because a prompt is rendered by the code beside it. That is also what lets CI's smoke run, which
   uses the checkout's script from a scratch directory, cut a card. With neither, the command exits 1
   with a `CONFIGURATION_ERROR` before anything is fetched. A broken profile directory is reported as
   a `ConfigurationError`, where it would otherwise be a bare `FormatProfileError` (exit 70).
4. **Owner.** Every card `cut` saves has `LOCAL_OWNER_ID` (`0…01`), because V1's CLI is one person's
   tool and `Card.owner_id` is required. It identifies nobody; V2's accounts replace it.
5. **The edit log.** CitationService requires a `CardEditLog`, but no production adapter exists ("No
   V1 command edits a card"). The container gives it `_NoCardEditsYet`, which holds no entries and
   refuses an append. Only `re_resolve`, which `cut` never calls, reads it.
6. **Order of refusals.** `--format` and the `--output` directory are checked before the container
   builds anything that holds a connection, and before any fetch. The .docx is written to a sibling
   temporary file and renamed into place, so a failed run leaves no half-written card. A file already
   at `--output` is replaced only by a finished export.
7. **Progress.** ArticleFetch does fetch and extract in one call, and CardService does select, cite
   and verify in one. So `fetch` and `extract` are printed when the fetch returns, `select` before
   `cut_card` (the stage a person waits on), `verify` when it returns, and `export` after the write.
   Under `--json` each is an `event_line` object on stderr. For a person, exit 0 and exit 4 print the
   card table on stdout, and exit 4 adds a panel on stderr with one line per reason (code, the
   verifier's code, a sentence, the detail).
8. **Seams for tests.** The container takes overrides named `crossref_transport` (like
   `article_fetch_transport`) and `card_model_router`, used the same way as the existing seams.
9. **The lock was edited by hand.** `uv lock --offline` cannot resolve, because fastapi is not in uv's
   cache. python-docx was already locked as a root dev dependency, so the change is two lines: the
   extra's entry and its `requires-dist`. `uv lock --check --offline` accepts the result (exit 0) and
   refuses the old lock against the new pyproject (exit 1). CI's `uv sync --locked` checks it again.
10. **Smoke planting.** The smoke check stores the snapshot from pytest's process with the checkout's
    adapters, as the landscape smoke check plants its run. The two cassettes are the committed
    news-article answers, wrapped in a record-shaped response with an invented route. A build whose
    prompt numbering or variables differed would find no cassette.

## Operator follow-ups

**Optional, after this merges and a dev pre-release containing it is installed: one live `cut` on
dev.** It cuts a public article the coach picks, so the exit code and status can be seen on the real
route. The model call runs on dev's Bedrock route, with zero retention on, so nothing is logged
there. Expected cost: cents, under dev's $2.00 daily budget. Runtime: about a minute.

**Operator command 1: check the installed build** (seconds)
Where: your Mac, any terminal
```bash
debate-research --json --version | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"]["tag"])'
debate-research cut --help | grep -c -- '4  the card is UNVERIFIED'
```
Success looks like: the tag of a dev pre-release built after this merge, then `1`. A `0` means the
installed build has no `cut`: install the newer pre-release first.

**Operator command 2: one live cut** (about a minute)
Where: the same terminal. Set `URL` and `NEED` to the coach's article and research need, and `ARG` to
the argument it is for, or leave `ARG` empty.
```bash
URL=
NEED=
ARG=
if [ -z "$URL" ] || [ -z "$NEED" ]; then echo "STOP: set URL and NEED to the coach's article and need"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else aws sso login --profile debate-dev-bedrock && cd "$HOME" && env DEBATE_ENV=dev DEBATE_MODEL_MODE=live debate-research --json cut "$URL" --need "$NEED" --argument "$ARG" --output "$HOME/Desktop/cut-check.docx" > /tmp/cut-check.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); r = e.get("error") or {}; d = e.get("data") or r.get("details") or {}; s = d.get("source") or d; print("code", r.get("code"), "exit_code", r.get("exit_code")); print("status", d.get("verification_status"), "card", d.get("card_id"), "output", d.get("output")); print("reasons", [x["reason"] for x in d.get("reasons") or []]); print("calls", [(c["prompt_id"], c["route"]["model_id"]) for c in d.get("model_calls") or []]); print("source", s.get("access_status"), s.get("canonical_url"))' /tmp/cut-check.json; fi
```
Success looks like:

* `exit 0` and `code None exit_code None`;
* `status VERIFIED`, a card id, and `output` ending in `Desktop/cut-check.docx`;
* `reasons []`;
* `calls` naming `card.select` and `card.markup` with dev's routed model id;
* `source ACCESSIBLE` and the article's canonical URL.

The file then opens in Word as one tagged, cited, underlined card. Other outcomes, all worth pasting
back:

* `exit 4`, `code CARD_UNVERIFIED`: the card was written with its banner, and `reasons` says why.
* `exit 3`, `code SOURCE_NOT_ACCESSIBLE`: `source` gives the status (PAYWALLED and the rest), nothing
  was written, and the coach should pick a public article.
* `exit 1`, `code MODEL_ACCESS_DENIED`: the SSO session or the role's model grant.

**Operator command 3, optional: see what it cost** (seconds)
Where: the same terminal
```bash
cd "$HOME" && env DEBATE_ENV=dev debate-research usage
```
Success looks like: today's spend, which includes two `card.select`/`card.markup` calls costing cents.

## Follow-up work

1. **Cutting from pasted text** (E04/E06). `cut` cuts only from a PUBLISHER_RETRIEVED snapshot,
   because `ArticleService.retrieve` reuses only those. But `fetch`'s exit-3 hint says "store your
   copy with --paste" right after "nothing can be cut from this source", which implies a pasted copy
   can be cut. Either `cut` gains a way to cut a stored USER_SUPPLIED snapshot (its card carries that
   provenance), or the hint changes.
2. **A cut-specific hint for an unrecorded replay** (`v1-e06` or E05). The `MISSING_FIXTURE_ERROR`
   hint says to record with `DEBATE_MODEL_MODE=record` and points at the committed cassettes' README.
   For `cut`, "set `DEBATE_MODEL_MODE=live`" is the likelier fix.
3. **A published `cut_result.v1.json` schema** (beside `fetch_result.v1.json`), so a script can check
   the payload. It lives in `debate_core/schemas`, outside this task.
4. **A production `CardEditLog`** arrives with V2's editor (the port's own note). `_NoCardEditsYet`
   goes then.
5. **`--refresh` for `cut`**, if the coach wants to re-fetch inside `articles.refetch_after_hours`.
   `fetch --refresh URL` followed by `cut URL` does it today.

### Questions for the PM

```text
PM questions from v1-e06-t06-cut-command (2026-11-01)

1. ac4's --json "CutResult with manifest". The manifest holds evidence_text; output.py rules evidence
   text out of every --json payload. Built: the CutResult (card id, status, reasons, model calls),
   the source, and the manifest's identity (version, generated_at, card ids, snapshot references,
   SHA-256 of the bytes embedded in the .docx); the whole manifest is in the .docx.
   Options: (a) keep it; amend ac4 to "CutResult with the embedded manifest's identity".
   (b) put the whole manifest under data.manifest and write the exception into output.py.
   Recommendation: (a). One rule for every --json payload, and the manifest verify reads is the
   one in the document.

2. scripts/stamp_build.py and tests/scripts/test_stamp_build.py are outside constraints.packages;
   bundling prompts/ (ac5) and config/format_profiles/ (--format in an installed build) needs them,
   because uv_build packs only the module root.
   Options: (a) add both to constraints.packages. (b) move the bundling elsewhere.
   Recommendation: (a). The stamp already bundles config/ the same way.

3. Model mode for cut. Only DEBATE_MODEL_MODE chooses it (v1-e05-t03's one control), default replay,
   cassettes under <data dir>/cards/model-cassettes/. A coach's live run is
   DEBATE_MODEL_MODE=live debate-research cut ...; without it an unrecorded call exits 1.
   Options: (a) keep it. (b) add --model-mode to cut, as landscape has. (c) default cut to live.
   Recommendation: (a) for Friday, with follow-up 2's hint; (c) would break "nobody configured it,
   so no model is reached".

4. Follow-up 1: fetch's exit-3 hint suggests --paste, but cut cannot cut a pasted snapshot. Which
   task, and should the hint change first?
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

v1.3's headline command is built, and it fails closed. A URL in, a verified card out, or an explicit
status and exit code. No business logic sits in the CLI.

1. **ac1–ac5 pass:**
   * ac1 reads the .docx back: the tag, the cite, the underlining worked out by hand from the
     offsets, and the embedded manifest, which `verify` then accepts.
   * ac2 covers all four retrieval statuses, with no file, no card row and zero model calls.
   * ac3 shows the banner and every reason.
   * ac5 is proven on two installed builds: red on a wheel stamped by the old script, green on this
     branch's.
2. **Red first and mutants:** 20 of 22 tests failed against the skeleton, and the pinned wiring
   lists, verify's wording and stamp_build each went red too. All six mutants were caught, including
   the PM's four.
3. **Exit codes:** written into the spec as the PM's dated amendment. `exit_code_for` needed no change;
   `CARD_UNVERIFIED = 4` is the only new member.
4. **The rulings on your questions:**
   * **Q1, (a).** Keep it. One rule for every `--json` payload: no evidence text. The manifest
     `verify` reads is the one inside the document. Write ac4's amendment into the spec: "the
     CutResult with the embedded manifest's identity (version, generated_at, card ids, snapshot
     references, SHA-256 of the embedded bytes)".
   * **Q2, (a).** Add `scripts/stamp_build.py` and `tests/scripts` to `constraints.packages` in the
     same dated amendment. Deviation 2 is accepted.
   * **Q3, (a).** Keep `DEBATE_MODEL_MODE` as the one control, defaulting to replay. Follow-up 2 (a
     `cut`-specific hint that says `DEBATE_MODEL_MODE=live`) is filed by the PM as a p3 task.
   * **Q4.** Cutting from a stored pasted copy is valuable: library-access articles that the fetcher
     sees as paywalled. The PM files one E06 p2 task for it. The card carries USER_SUPPLIED
     provenance and is verified against that snapshot. Until it lands, `fetch`'s exit-3 hint says the
     copy can be stored, not cut. The coach may veto this.
5. **Decisions accepted:**
   * `--need` is required;
   * prompts and profiles come from the build itself;
   * `LOCAL_OWNER_ID`;
   * `_NoCardEditsYet`;
   * refusals before any connection;
   * the temp-file-and-rename write;
   * the progress mapping;
   * the test seams.
6. **The lock edited by hand** (Decision 9) is accepted. python-docx was already locked as a dev
   dependency, `uv lock --check --offline` accepts it, and `ci`'s `uv sync --locked` checks it again.
7. **Checks:** the affected set is the whole selection after the pyproject edit, so it is left to
   `ci` (agreement 10). The bounded changed areas (753, then 132 passed), ruff, pyright, lint-imports,
   thin handlers, the specs and the doc checks are clean.
8. **The operator follow-up** (a live cut on dev) is optional and needs a dev pre-release carrying this
   installed on the Mac. The Mac's CLI is dev.289, which has no `cut`. It does not hold the merge.
   The PM gives the install and the cut one block at a time when the coach picks an article.
9. **Before the PR:** write the dated PM amendment (ac4's wording and the two packages) into the spec,
   then run validate_specs and commit. Don't edit this report further.
10. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.

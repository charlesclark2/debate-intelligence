# Session report: v1-e31-t30-parsed-store-publish-only

| | |
|---|---|
| Task | `v1-e31-t30-parsed-store-publish-only` — Publish the parsed store without rebuilding it |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t30-parsed-store-publish-only.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t30-parsed-store-publish-only.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t30-parsed-store-publish-only` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`debate-research caselist parse --caselist <slug> --publish-only` publishes the running parser's
current version directory, the one `--publish` publishes, without parsing or rebuilding. It calls
the same `ParsedStorePublisher.publish(caselist, version)`, built by the same container method. So
suppression, held uploads, the occurrence-table guard, aggregates going last and the idempotent
skip all come from the existing publisher. None of them is checked again in the new code.

Before any upload, `CaselistParseService.publishable_version` refuses a directory that is missing,
lacks an aggregate, has an index naming a source with no per-source file, holds sources parsed under
another parser or profile version, or carries a fingerprint stamp that is not this build's. Each
refusal has its own code and a hint naming the command to run instead. `--publish` and every option
that only shapes a rebuild are refused beside it, exit 2. The guide is
`docs/guides/parsed-store-publish-only.md`. The phase is `Succeeded`.

**Look at these first:**

1. **Deviation 1.** A per-source record stamped with an *older* fingerprint version is published, not
   refused. Refusing it would refuse directories that `--publish` publishes today.
2. **The PM question below.** Aggregates rebuilt against one environment's suppression list can be
   published to an environment whose list holds a removal the first lacks. The guide tells the
   operator to rebuild after any removal. No code guard was added, because adding one is a scope call.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `publish-only` | Done | Core check, CLI option, pull text and guide; red runs recorded before green; 21 of 21 mutants killed |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: publishing an existing complete version directory uploads the same objects the rebuild's publish would, without rebuilding, by test shown failing first | PASS | **Red, core, no publish-only path** (`publishable_version` raising `NotImplementedError`): `.venv/bin/python -m pytest packages/debate_core/tests/application/test_caselist_parse_publish_only.py -q -p no:randomly` → `19 failed`. **Red, CLI, the command as of `d5dccd5`:** `.venv/bin/python -m pytest packages/debate_cli/tests/test_caselist_parse_publish_only.py -q -p no:randomly` → `14 failed`, each `No such option: --publish-only` (exit 2). **Green:** the same two files → `19 passed` and `14 passed`. The ac1 tests compare the second bucket with the first, key for key and byte for byte. They compare every object's outcome with the rebuild's publish, and the CLI's `publish` object with `--publish`'s, `bucket` aside. They also check every parsed-store file's bytes and mtime are unchanged, and that the parser was asked for nothing: `test_publish_only_sends_exactly_what_the_rebuilds_publish_sends_and_reports_it_alike`, `..._after_a_partial_publish_...`, `test_publish_only_to_prod_sends_what_publish_sent_to_dev_and_reports_it_alike` |
| ac2: an incomplete directory, or one written by another parser or fingerprint version, is refused with its reason, by test | PASS (see Deviation 1) | **Red against a refuse-nothing skeleton** (`refuse_unpublishable` returning the directory unchecked): core file → `13 failed, 6 passed`. All 12 refusal tests failed with `DID NOT RAISE PublishOnlyRefused`. The 13th was `test_publish_only_after_a_partial_publish_...`, which failed on its own wrong count (3 uploads, not 4). That count was fixed in `baa76fe` to the one `test_caselist_parse.py` derives. The 6 that passed need no refusal. **Green:** `19 passed` (core), `14 passed` (CLI). Each refusal test asserts the class, the code (`error_code_of`), the exact message, an empty bucket, nothing parsed, and no fictional school or team in the message or hint |
| ac3: the guide gives the command and when to use it; `scripts/check_command_blocks.py` passes | PASS | `docs/guides/parsed-store-publish-only.md`. `uv run scripts/check_command_blocks.py` → `OK: no # comments in 338 shell code blocks in 137 Markdown files`. `uv run --frozen python scripts/docs_index.py --check-descriptions` → `All 42 indexed documents under docs/ have a description`. `uv run scripts/check_links.py` → `OK: 1942 relative links and anchors in 296 Markdown files` |
| Node `publish-only`: Parse publish tests pass (`uv run pytest packages/debate_core/tests/application -k "parsed_publish or publish"`) | PASS | Run as `.venv/bin/python -m pytest packages/debate_core/tests/application -k "parsed_publish or publish" -q` under `perl -e 'alarm 115'` → `376 passed in 17.43s` |

### Mutation check (completeness refusals and option conflicts)

A scratch script, not committed: one exact-string mutant at a time, run against its own test
file with `-x`, restored from the original bytes afterwards. Worktree clean after each batch.
**21 of 21 killed:**

| # | Mutant | Result |
|---|---|---|
| 1 | No missing-directory refusal | killed (2 failed) |
| 2–4 | The index / failures file / occurrence table not required | killed (2 failed each) |
| 5 | An index naming a missing per-source file ignored | killed (1 failed) |
| 6 | Profile version ignored (parser version only) | killed (1 failed) |
| 7 | Older occurrence-table stamps pass (newer only refused) | killed (2 failed) |
| 8 | Occurrence-table stamps not checked | killed (3 failed) |
| 9 | Older per-source stamps refused (strict equality) | killed (1 failed) |
| 10 | Per-source stamps not checked | killed (1 failed) |
| 11 | Stamp hint inverted | killed (3 failed) |
| 12 | A single missing aggregate passes | killed (3 failed) |
| 13–17 | `--publish` / `--reparse` / `--snapshot` / `--dry-run` / `--failures` allowed beside it | killed (1 failed each) |
| 18 | No conflict check at all | killed (5 failed) |
| 19 | No environment guard | killed (1 failed) |
| 20 | No prod confirmation | killed (1 failed) |
| 21 | The CLI skips the directory check (`_current_version` instead of `publishable_version`) | killed (2 failed) |

Mutants 7, 9 and 10 were re-run after `a67d7ac` changed the lines they target: all killed.

### Affected set and whole-repo checks

* `uv run scripts/affected_tests.py` selects **205 of 387** test files. Run directly as
  `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" <selection>`,
  it reached **76% at 115 s** and was stopped. Over two minutes, so by agreement 10 the whole set is
  the PR's `ci` check, with no operator hand-off.
* That cut run found **one failure**:
  `test_occurrence_table_guard.py::test_every_path_that_moves_an_occurrence_table_asks_the_one_rule`.
  That test allows only the guard to call `is_newer_fingerprint_version`, and my per-source check
  called it directly. Fixed in `a67d7ac`, which uses the guard's `newer_stamp` instead. The guard
  test passes again, and the test is unchanged.
* Then, inside two minutes, the changed modules' test directories plus the always-run list:
  * `tests/architecture tests/specs tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py packages/debate_cli/tests/*.py packages/debate_cli/tests/commands/test_caselist_pull.py packages/debate_core/tests/application/*.py`
    → `2292 passed, 4 skipped in 44.71s`.
  * `packages/debate_core/tests/application/caselist` → `1534 passed in 64.40s`.
* The new tests in one process, `-n 0 -p no:randomly` → `33 passed`.
* `uv run ruff format --check packages/debate_core packages/debate_cli` → `617 files already
  formatted`. `uv run ruff check …` → `All checks passed!`. `uv run pyright packages/debate_core
  packages/debate_cli` → `0 errors` (`--stats` confirms it resolves the workspace). `uv run
  lint-imports` → `15 kept, 0 broken`. `uv run scripts/validate_specs.py` → `OK: 404 files, 39
  epics, 344 tasks, 21 releases`.

## Files changed

* **`packages/debate_core/src/debate_core/application/caselist/parsed_publish_only.py`** (new): the
  refusals (`PublishOnlyRefused` and its five subclasses, each its own code) and
  `refuse_unpublishable`, which reads only through the `ParsedStore` port. The occurrence table's
  stamps come from `read_occurrence_stamps`, which uses `fingerprint_stamps_of_file`. Each per-source
  record's stamp comes from its entry (`read_entries`). It adds no reader, no port method and no
  adapter change.
* **`packages/debate_core/src/debate_core/application/caselist_parse.py`**:
  `CaselistParseService.publishable_version(caselist)`. It validates the slug, takes
  `_current_version` (the newest generation of the running parser version, the directory `--publish`
  publishes) and runs the check.
* **`packages/debate_cli/src/debate_cli/commands/caselist_parse.py`**: the `--publish-only` option,
  `ConflictingPublishOnly` (usage error, exit 2), and `_publish_only`, which applies `--publish`'s two
  guards, runs the check, then calls `cli.services.parsed_publisher().publish`. Also
  `publish_only_summary` (its `publish` object is `_publish_summary`, shared) and the table.
  `PARSED_PUBLISH_INCOMPLETE` is now built by one `_publish_failure` for both modes. Its hint says
  to retry with `--publish-only`, because the directory is already rebuilt by then.
* **`packages/debate_cli/src/debate_cli/commands/caselist_pull.py`**: the docstring says when a
  failed parse stage is finished by `--publish-only` and when it still needs `--publish`. The
  `--publish-pending` help says it publishes snapshots, never the parsed store.
* **Tests:** `packages/debate_core/tests/application/test_caselist_parse_publish_only.py` (19) and
  `packages/debate_cli/tests/test_caselist_parse_publish_only.py` (14). No AWS or network: two
  on-disk object stores in core, moto in the CLI.
* **`docs/guides/parsed-store-publish-only.md`** (new): the command, the two uses (a failed publish
  after its rebuild; a second environment), when to rebuild instead, the refusals table, and what it
  reports. `docs/data/parsed-card-store.md` was not touched (`v1-e29-t12` is editing it).
* **The task spec:** phase `Succeeded`.

## Deviations from the spec

1. **A per-source record stamped with an older fingerprint version is published, not refused.** The
   PM context said to refuse when "the per-source records' … fingerprint stamps aren't the running
   fingerprint version". That rule refuses directories this build has just rebuilt.
   `ports/parsed_store.py` ("The skip key") says a fingerprint bump re-parses nothing: the next
   rebuild rewrites only the occurrence table, and "the per-source records keep the stamp of the day
   they were parsed". `FINGERPRINT_VERSION` has been bumped three times (v1 to v4), so the real
   directories hold older per-source stamps. Under the literal rule, `--publish-only` would refuse
   every caselist parsed before the last bump until a `--reparse`, while `--publish` sends those
   same files. That breaks ac1.

   What is implemented:
   * Every occurrence-table row must equal this build's version. The rebuild stamps the table whole,
     so an older stamp means the table was not rebuilt by this build.
   * A per-source record is refused only when a **newer** build stamped it. That question goes to
     the guard's `newer_stamp`, as `test_occurrence_table_guard.py` requires of every such comparison.

   `test_records_stamped_before_a_fingerprint_bump_are_published_as_the_rebuild_publishes_them` shows
   the case. Mutant 9 (strict equality) is killed by it. The spec's ac2 wording ("written by another
   … fingerprint version") reads naturally as this rule. If the PM wants the literal rule, it is a
   one-line change, and that test then becomes the record of what it refuses.

## Decisions and assumptions

* **The profile version is checked too** (`PARSED_BY_ANOTHER_PARSER_VERSION`). A directory holding
  sources parsed under another style profile is not what `--publish` publishes: its rebuild starts a
  new generation and publishes that. This is ac2's "written by another parser … version", read as the
  skip key the store uses, which is the parser and profile versions together.
* **`--failures` is refused beside `--publish-only`** as well as the rebuild options. Otherwise
  `--failures` would run and `--publish-only` would be silently ignored, which is the unclear
  behaviour the PM ruled out.
* **The check reads the store through the parse service** (`caselist_parse(with_bucket=False)`),
  which has the parser's versions and the existing "current version" rule. The check reads no
  suppression list, so it needs no bucket. The publish is built by `parsed_publisher()`, as
  `--publish`'s is.
* **The weekly pull's own fix text (`caselist_sync._UNPUBLISHED_PARSED_STORE_FIX`, the banners and
  `sync_runs.PARSE_COMMAND`) still says `--publish`.** That one text covers a parse stage that failed
  to rebuild and one left `pending` whose aggregates may come from this Mac's copy of the suppression
  list alone. The stage says those aggregates "must never be what is published", so `--publish-only`
  would be wrong there. Splitting the text per caselist means changing persisted run records and
  several pinned banner tests (Follow-up 1). The pull command's docstring now says when
  `--publish-only` is enough instead.
* **Refusals name SHA-256 prefixes, versions and counts only.** The aggregate names are written as
  words ("index", "failures file", "occurrence table"), and no path or file name is printed. The CLI
  tests check the fictional schools, team codes and the data directory are absent from the output.

## PM question (relay prompt)

```text
v1-e31-t30 (caselist parse --publish-only), one question.

--publish-only publishes the aggregates as the last rebuild wrote them. That rebuild filtered them
by the suppression list of the environment it ran under. The publisher (the one we reuse) then
withholds suppressed per-source files using the TARGET environment's list, but it does not touch the
aggregates. So if prod's list holds a removal dev's does not, then
  DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR=<dev> caselist parse --publish-only --confirm-prod
withholds that source's per-source file but sends an index and occurrence table that still name it
(sha256 and disclosure digests only, no paths). --publish would have rebuilt them without it.
On one machine this does not happen, since local and bucket copies of a list are kept equal. A
removal on the machine itself deletes the aggregates, and --publish-only then refuses.

Options:
A. Leave it to the guide (done): "after a removal, in either environment, use --publish".
B. Add a refusal: refuse when the target environment's list stops a source the index names, or a
   disclosure an occurrence row names (asks SuppressionState, re-implements nothing). This is a new
   check in the publish-only path, which your context said not to add, so it needs your ruling and
   likely a spec line.
C. Record in the version directory which suppression-list digest the aggregates were built under,
   and refuse publish-only when the target's differs (search index already does this with
   occurrences/suppression digests). Larger: touches the rebuild and the store layout.

Recommendation: A now, and B as a small follow-up task. B closes the gap with a readable refusal
and no layout change.

Also please confirm Deviation 1 (older per-source fingerprint stamps are published, as --publish
publishes them).
```

## Operator follow-ups

1. **The affected set: nothing to run.** It is past two minutes here (76% at 115 s), so the pull
   request's `ci` check runs it (agreement 10). If `ci` fails, paste the failing part's output into
   the session.
2. **After this merges: one dev run of `--publish-only` over the current version** (PM context).
   Where: a checkout of `dev` at or after the merge, set up as the runbooks say, on your Mac, with a
   dev SSO session. Expected runtime: under a minute (it heads every object and uploads nothing).
   Success looks like exit `0` and a `Published` row reading `0 uploaded, <n> skipped, 0 failed`.
   Any upload means dev's bucket was behind this Mac's store, and the run will have caught it up.

   ```bash
   aws sso login --profile debate-dev-evidence
   DEBATE_ENV=dev uv run debate-research caselist parse --caselist hsld26 --publish-only
   ```

## Follow-up work

1. **The weekly pull's parse-stage fix could name `--publish-only` per caselist (E34).** Only when
   the publish itself failed after a rebuild that read every copy of the list. Its text is persisted
   in run records and pinned by banner tests, so it is a task of its own. See Decisions.
2. **A smoke check for `--publish-only` (E31).** `plan_specs/README.md` asks for one when a CLI
   surface changes. This spec had no smoke node, and `tests/smoke` is outside its packages. The
   offline check that fits is the option-conflict refusal (exit 2, nothing written), which needs no
   bucket.
3. **The PM question above (option B)**, if the PM wants the refusal.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

Accepted, on four conditions closed in this session before the pull request. The largest is the
refusal in ruling 2, which is now in scope. Record what you did under a "PM conditions" heading,
keep the phase `Succeeded`, and open the pull request with no `--partial`. If anything comes out
differently from what is written here, stop and ask for another review.

**What the PM checked.** The branch is clean, 9 commits on origin/dev at `ecc2739`, and the diff
is the 9 files listed. The publish goes through the existing `parsed_publisher()`, and the new
module reads only through the `ParsedStore` port. The base predates v1-e29-t12 (#397), which
changed `occurrence_table_guard.py` and its test. That is the test your per-source check now
depends on, so the sync in condition 4 is required.

**Rulings.**

1. **Deviation 1 is accepted. The PM context was wrong.** The skip key keeps each per-source
   record's stamp from the day it was parsed, so the literal rule would refuse what `--publish`
   sends and break ac1. The implemented rule stands:
   * occurrence table rows must equal this build's version;
   * a per-source record is refused only when a newer build stamped it, asked of the guard's
     `newer_stamp`.

   Add a comment above ac2: `# PM ruling 2026-10-22: "another fingerprint version" means an
   occurrence table not stamped by this build, or a per-source record a newer build stamped; older
   per-source stamps are published, as --publish publishes them.`
2. **The PM question: option B, in this session, not as a follow-up.** Publishing to a second
   environment is half of what this task is for, and the next use is the prod promotion. Prod's
   suppression list is exactly the one that may hold a removal dev's lacks: v1-e39-t07 adds prod
   removal grants, and the promotion checks the prod list exists. A guide line is not enough
   protection for that path. Fail closed, as the pilot's view and copy do.
   * **The check.** Before any upload, load the *target* environment's suppression state, the
     same `load_suppression_state` over the same list the publisher is given. Then ask the existing
     rule, `parse_sources.live_disclosures` and `held_only_sources` over `enumerate_sources`,
     whether every source the index names, and every disclosure an occurrence row names, is still
     live there. If any is not, refuse with its own code (`PUBLISH_ONLY_SUPPRESSION_CHANGED`, or a
     clearer name of your choosing). The refusal gives counts and SHA-256 prefixes only, uploads
     nothing, and hints `--publish`.
   * **Not a second implementation.** It writes no rule of its own: the rebuild's own predicates
     answer it. If the rebuild filters aggregates through a predicate that is not yet one shared
     function, extract it so both call it, and say so in the report. This supersedes the context's
     "don't re-check in the new path" for this one question. The forbidden entry stands, because
     nothing is re-implemented.
   * **Tests, red first:**
     * dev-built aggregates with a prod list holding one extra removal: refused, an empty bucket;
     * a prod list holding one extra path hold: refused;
     * equal lists: publishes exactly as now;
     * the refusal message holds no fictional school or team.

     Then mutation-check the new refusal.
   * **Spec:** add an ac4 for the refusal, with
     `# PM ruling 2026-10-22: aggregates are refused where the target environment's list stops
     what they name`.
   * **Guide:** keep the "after a removal, use `--publish`" advice, and add that the command now
     refuses such a case.

   Option C (recording the list's digest in the version directory) is not needed once B exists.
3. **The smoke check, now.** `plan_specs/README.md` asks for one when a CLI surface changes, so it
   is a standing rule, not a follow-up. Add the offline option-conflict check (exit 2, nothing
   written) to `tests/smoke`, and add `tests/smoke` to `constraints.packages` with
   `# PM ruling 2026-10-22: a CLI surface change carries its smoke check.`
4. **Sync, then re-run** (`scripts/task sync`):
   * the guard test (`test_occurrence_table_guard.py`), which v1-e29-t12 changed;
   * both new test files, with the new refusal, plus the one-process run;
   * the two closing pytest commands, ruff, pyright and `lint-imports`;
   * `validate_specs.py`, `check_command_blocks.py`, `check_links.py` and `docs_index.py
     --check-descriptions`.

   Record the results.

**Accepted as written.**

* The profile-version check, and refusing `--failures` beside `--publish-only`.
* Leaving the weekly pull's persisted fix text as `--publish`. Follow-up 1 is right, and the PM
  files it for E34 in the next batch.
* `PARSED_PUBLISH_INCOMPLETE`'s hint naming `--publish-only`, since the directory is rebuilt by
  then. With ruling 2, a target list that has since changed is refused rather than published.
* The affected set left to the PR's `ci` (agreement 10).
* **The operator follow-up,** run once after merge from the main checkout. Add `cd` to the
  checkout first: the installed `debate-research` and the checkout's `.env` disagree on the
  OpenAlex key until the agent is upgraded, which is why it says `uv run`.

**Noted.** Catching the cut affected-set run's guard failure, and fixing it by asking the guard
rather than relaxing its test, was the right call.

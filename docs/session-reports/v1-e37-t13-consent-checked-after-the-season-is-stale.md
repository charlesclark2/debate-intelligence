# Session report: v1-e37-t13-consent-checked-after-the-season-is-stale

| | |
|---|---|
| Task | `v1-e37-t13-consent-checked-after-the-season-is-stale` — A consent entry checked after its season ends is stale to the build, for names and images |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t13-consent-checked-after-the-season-is-stale.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t13-consent-checked-after-the-season-is-stale.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t13-consent-checked-after-the-season-is-stale` |
| Session status | COMPLETE |

## Summary

`isStale` (`site/src/lib/media-consent.ts`) now treats a `dateChecked` after the season's last
day, 31 July of its second year, as stale, as it already treated one before 1 August. The end
comes from a new `seasonEnd(label)`, built from `seasonStart(label)`, so the season label is
parsed in one place. Because the name rule and the image rule both call `isStale`, a name or an
image published against an entry checked on 2027-08-02 for season 2026-27 now fails a prod build
and is printed in a dev build. An entry checked on 2027-07-31 still builds. On the results page
such a student's result switches to the team-level form; it is not refused. The shipped results
are unchanged: `loadResults()` output on the shipped content is byte-identical before and after
the change. The shipped site's prod build and its export checks pass. Two sentences of the coach
guide said a check counts "since the season began"; they now say "during that season". The PM
may want to look first at Follow-up work 1: the header comment in `site/content/media-consent.yaml`
is now incomplete, and this task may not change `site/content/`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `consent-checked-after-the-season-is-stal` (Consent after the season) | Done | Red tests committed alone (`9e1d5b7`), then the fix and the guide (`0b1a35f`). Four mutants caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a name or an image published against an entry checked after its season ends fails a prod build and is printed in a dev build, an entry checked within its season builds, and the results page is unchanged for the shipped content, by tests shown failing first | PASS | **Red** at `9e1d5b7`, before the fix: `pnpm exec vitest run tests/content-policy.test.ts tests/results.test.tsx` (in `site/`) → `6 failed \| 150 passed (156)`. Every failure was an assertion, not an error: prod on a name and on an image, "expected function to throw an error, but it didn't"; dev on both, "expected '' to match /names "Jordan Rivera", whose consent …/" and the image's equivalent; the `isStale` boundary, "expected false to be true"; the results page, "expected true to be false" (`named`). The two 31 July cases passed, as they should before and after. **Green** at `0b1a35f`: the same command → `157 passed (157)` (one more test, the `seasonEnd` pin added with the fix). **Shipped results unchanged:** a scratch vitest file (deleted, never committed) wrote `JSON.stringify(loadResults())` for the shipped content before and after the fix; `cmp` → identical, 3285 bytes, 4 named results and 0 team-level. **Shipped prod build:** `SITE_ENV=prod SITE_URL=https://wfbdebate.com site/scripts/export-checks.sh` at `0b1a35f` → exit 0 in 14 s: `Compiled successfully`, 17 static pages, export checks `12 passed (12)` files / `109 passed (109)` tests; `site/out/robots.txt` reads `Allow: /`, so it was a prod build. |
| Node criterion "Consent after the season tests pass": `pnpm --dir site test` | PASS | At `0b1a35f`: exit 0 in 11 s, `Test Files 27 passed (27)`, `Tests 969 passed (969)`. |

### Mutants (working agreement 8)

Each mutant was applied to `site/src/lib/media-consent.ts` in the working tree, run against
`tests/content-policy.test.ts` and `tests/results.test.tsx`, and restored with
`git checkout HEAD -- site/src/lib/media-consent.ts`. The site tests use no Hypothesis, so there
was no example database to isolate. Every mutant ran; none failed at collection.

| Mutant | Caught | Tests that failed |
|---|---|---|
| The end check removed (`\|\| checked > seasonEnd(currentSeason)` deleted) | Yes, 6 failed | prod and dev for a name and an image; the `isStale` boundary test; the results page's team-level fallback |
| The end off by one day (`seasonEnd` returns 1 August, so 1 August is accepted) | Yes, 2 failed | "calls an entry stale when it was last checked after the season ended, on 31 July" (its 2027-08-01 case) and the `seasonEnd` pin. The prod and dev cases use 2 August, so they do not catch this one; the boundary test does. |
| The end taken from the start year (`+ 1` dropped: 31 July 2026) | Yes, 19 failed | Every current-season entry turns stale: the 31 July cases, "passes when the student has a current-season consent entry", the shipped-manifest entry checks, the results page's named lines and the boundary tests |
| The end two years on (`+ 2`: 31 July 2028) | Yes, 7 failed | prod and dev for a name and an image, the boundary test, the `seasonEnd` pin, the results page's fallback |

### Checks before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `42 of 583 test files (7.2%) chosen in 14.1 s from 7 changed files`, and "site/ changed: the site's own pnpm checks test it; pytest does not." |
| The 42 files under `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live"` (what `--run` runs, with the limit on the interpreter) | **Stopped by the alarm at 115 s at about 95%, with no failure printed** (load average about 18 from other sessions). The orphaned collection workers of `tests/scripts/test_ci_workflow_test_job.py` were killed afterwards. Under working agreement 10 the full affected set is left to the pull request's `ci` check. `--explain` shows most edges are incidental: shell scripts and `scripts/install_channel.sh` naming site files, and the spec and this report's paths. |
| What the change reaches, plus the always-run files: the 8 "always run" files, `tests/docs`, `test_file_recipes.py`, `test_file_recipes_attributed_and_held.py`, `test_check_promotion_source.py`, `test_check_command_blocks.py`, `test_single_interpreter_source.py`, same interpreter and markers | `863 passed in 22.18s` |
| `.venv/bin/python -m pytest -n auto -m "not slow and not live" tests/specs` | `82 passed in 4.43s` |
| `pnpm --dir site typecheck`, `pnpm --dir site lint` | both clean |
| `uv run --frozen ruff format --check .`, `uv run --frozen ruff check .` | `1635 files already formatted`; `All checks passed!` |
| `uv run --frozen lint-imports` | `Contracts: 19 kept, 0 broken.` |
| pyright | Not run: the branch changes no Python package. |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | `All 59 indexed documents under docs/ have a description` |
| `uv run --frozen python scripts/check_links.py` | `OK: 3028 relative links and anchors in 468 Markdown files` |
| `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` | `OK: no '#' comments in 592 shell code blocks in 199 Markdown files` |
| `uv run scripts/validate_specs.py` (after setting the phase) | `OK: 519 files, 40 epics, 457 tasks, 22 releases` |

The task spec on `origin/dev` differs from the branch's only in `status.phase`; the PM has not
amended it since the branch was cut.

## Files changed

- `site/src/lib/media-consent.ts`: new `seasonEnd(label)`; `isStale` refuses a check dated after it.
- `site/src/lib/publishing-policy.ts`: one comment, which said a current entry "has been checked
  since the season began", now says "was last checked within it (isStale)". No code change.
- `site/tests/content-policy.test.ts`: a `seasonEnd` pin and an `isStale` boundary test in "the
  start-of-season check"; a new block, "a consent entry checked after its season ends", with prod,
  dev and 31 July cases for a name and for an image.
- `site/tests/results.test.tsx`: a student checked after the season ends gets the team-level line;
  one checked on 31 July is still named.
- `docs/guides/coach-website-editing.md`: when a check counts (two sentences).
- `plan_specs/.../t13-consent-checked-after-the-season-is-stale.yaml`: Goal phase `Succeeded`.

Nothing under `site/content/` changed, and no manifest or lockfile changed. `pnpm install
--frozen-lockfile --offline` populated `site/node_modules` from the local store (3 s), and
`git status` was clean afterwards. Every name and reference in the new tests is invented
(`Jordan Rivera`, `MC-PLANT-001`, `MC-PLANT-002`, `/photos/planted-orientation.jpg`).

## Deviations from the spec

None.

## Decisions and assumptions

- **What was reused for the season's end.** `seasonEnd(label)` is
  `new Date(Date.UTC(seasonStart(label).getUTCFullYear() + 1, 6, 31))`. It takes its year from
  `seasonStart`, the existing parse of the label's first four digits, so the label is parsed only
  in `seasonStart`. `dateChecked` is an ISO date, so `new Date(dateChecked)` is UTC midnight. A
  check on 31 July therefore equals `seasonEnd` and is not stale, and one on 1 August is later and
  is stale. `isStale` compares with `<` against the start and `>` against the end. The other test
  is unchanged.
- **Messages unchanged.** A refused name or image already prints "whose consent entry is for
  season 2026-27, checked 2027-08-02", which states the problem. The warning for an entry nothing
  publishes still says the start-of-season check "has not been recorded". That is loose for a
  date after the season, but it is not false: no check inside the season is on record. Follow-up
  work 2 proposes clearer wording.
- **What the change means for `site/src/lib/results.ts`.** `isStale` is used once there, in
  `canBeNamed`, which decides whether a result prints the student's name or the team-level form.
  Nothing in `results.ts` throws on `isStale`, so the change can refuse nothing that ships. A
  student whose entry is checked after the season ends is printed in team-level form, the same as
  a lapsed form (the new results test). On the shipped content all three student entries are
  checked inside 2026-27 (2026-10-01 and 2026-10-27), there are no image entries, and the page's
  loaded form is byte-identical.
- **`tournaments.ts` and `results.ts` keep their own season-end strings.** Each builds
  `` `${year + 1}-07-31` `` to range-check tournament and result dates. That logic is outside this
  task's rule, and changing it would widen the change, so both are left as they are (Follow-up
  work 3).
- **The v1-e37-t11 shipped-manifest checks are kept as they are.** `imageEntryProblems` in
  `content-policy.test.ts` still tests `isStale(...) || image.dateChecked > lastDay`, and the
  student-entry test still compares with its own `lastDay`. These are now partly redundant with
  `isStale`. They are kept because they compute the season's end independently of the code under
  test (working agreement 6).
- **Guide.** The two sentences that described when a check counts now say "during that season
  (1 August to 31 July)" and "a check dated outside the season". No other passage gives the rule.

## Operator follow-ups

None. The full affected set (42 files) runs in the pull request's `ci` check; see Checks before
the report.

## Follow-up work

1. **The manifest's header comment is incomplete** (`site/content/media-consent.yaml`, lines
   22-26, outside this task: nothing under `site/content/` may change). It says an entry "whose
   `dateChecked` predates the start of `season` WARNS" and calls a lapsed entry one "not checked
   this season". Both are still true, but neither mentions a check dated after the season ends.
   Proposed wording for the first bullet: "an entry whose `dateChecked` is outside `season`
   (before 1 August or after 31 July) WARNS on its own". This is content, so it belongs in a coach
   or `site/` content change, not a code task.
2. **Warning wording for a check dated after the season** (`publishing-policy.ts`, the two
   `isStale` warnings): add something like "or dated after the season ends, which is usually a
   mistyped year" when `dateChecked > seasonEnd`. This is optional and belongs to E37.
3. **One season-end definition for the date range checks.** `loadSchedule` (`tournaments.ts`)
   and `loadResults` (`results.ts`) could use `seasonEnd(season)` in place of their own
   `` `${year + 1}-07-31` `` strings. E37, small.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

A consent check dated after its season ends is now stale to the build, for names and images alike,
through `isStale`.
1. **ac1 passes.**
   * Red: 6 failed, every one an assertion. Green: 157 passed, and the node criterion 969.
   * The 31 July boundary builds and 1 August is stale. The boundary test, not the prod cases,
     catches the off-by-one mutant, as you note.
   * All four mutants were caught.
   * The shipped results are byte-identical before and after, and the shipped prod build passes.
2. **Decisions accepted:**
   * `seasonEnd` derived from `seasonStart`, so the label is parsed once;
   * messages left as they are;
   * results.ts falling back to the team-level form, never refusing;
   * t11's independent shipped-manifest checks kept under agreement 6;
   * the guide's two sentences.
3. **Follow-ups:**
   * **1, the manifest's header comment:** the PM's next batch extends the comment its batch of
     2026-10-31 rewrote, with your wording for a check outside the season. It reaches main with the
     next promotion.
   * **2 and 3:** one p3 E37 task, covering the warning that names a check dated after the season
     and one season-end definition for the schedule's and the results' range checks.
4. **Closing checks:** the pytest affected set (42 files, mostly incidental edges) is left to the PR's
   `ci` under agreement 10. The site's own suite, typecheck and lint, the always-run files and the
   whole-repo checks pass.
5. **Merge:** once the PR's `ci` is green. It is a plain `scripts/task pr`. Like any site/ code
   change, it goes live with the next promotion.

# Session report: v1-e37-t12-stale-image-consent-refused

| | |
|---|---|
| Task | `v1-e37-t12-stale-image-consent-refused` — The prod build refuses an image whose consent has lapsed, as it refuses a lapsed name |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t12-stale-image-consent-refused.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t12-stale-image-consent-refused.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t12-stale-image-consent-refused` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Before this task, a page could show an image whose consent entry had lapsed, and the guard only
warned. Now `checkPublishingPolicy` reports it as an error, the same way it reports a named
student whose consent has lapsed. A prod build fails on it. A dev build prints it with the other
problems and still comes up. "Lapsed" covers three cases: the entry is for another season, it was
not checked this season, or its consent reference is still to come.

"Current season" comes from `isStale`, the function the name rule already uses. The "still to
come" test comes from the manifest's own `[[TBD]]` reference check, which is now one named
function that both rules call.

The tests were shown failing first: 9 failed for the right reason. They now pass, and all four
mutants are caught. The shipped manifest lists no image, and a prod build of the shipped site
passes. The guide and the site README now say that photographs follow the same consent rule as
names.

Look first at one existing test that pinned the old behaviour, a lapsed image on a page passing
with only a warning. It now checks the warning on an entry that no page shows (Decisions).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `stale-image-consent-refused` (Lapsed image consent) | Done | Guard and tests in `6ac0931`, the guide and site README in `8bff273`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a prod build refuses an image whose consent is for another season, unchecked this season or still to come, a dev build warns, and a consented image builds, by tests shown failing first; the guide says so | PASS | **Red.** I wrote the tests against the unchanged guard. `pnpm exec vitest run tests/content-policy.test.ts` (in `site/`) → `Tests 9 failed \| 72 passed (81)`. Every failure was an assertion. 3 were "expected function to throw an error, but it didn't", one per prod case. 3 were the dev cases, where nothing matched in the errors or the printed problems. 3 were integration cases on a copy of the shipped content, where the guard reported nothing about the page, or only the manifest's placeholder for the still-to-come reference. The unchanged guard refuses nothing here, so it served as the refuse-nothing skeleton. The consented-image case passed, which is right for a case that should build on any code. **Green.** The same command → `Tests 81 passed (81)`. The new tests are in `describe('an image whose consent has lapsed')`. Prod throws `PublishingPolicyError` naming the image and the lapse, once for each of the three cases. Dev returns the error and prints it under "Publishing policy problems, which will fail a prod build:", for the same three. A consented image, current season, has no errors in prod or dev. The three integration cases sit under "every image entry": a page in a copy of the shipped content shows a planted image with each lapse, and `guardErrors` reports it against `content/pages/about.md`. **The guide:** `docs/guides/coach-website-editing.md`, under Publish a change (the prod build in `validate-dev`) and under the start-of-season steps. |
| Node `stale-image-consent-refused`: `pnpm --dir site test` | PASS | `pnpm lint && pnpm typecheck && pnpm test` in `site/` → eslint and tsc silent, `Test Files 27 passed (27)`, `Tests 959 passed (959)`, 17 s. |
| Prod build of the shipped site | PASS | `SITE_ENV=prod SITE_URL=https://wfbdebate.com site/scripts/export-checks.sh` → exit 0 in 11 s, `Test Files 12 passed (12)`, `Tests 109 passed (109)`, no publishing-policy output. The shipped manifest has `images: []`, so nothing in it is refused. |
| Mutants (the PM's three, agreement 8) | PASS | Each mutant was applied to the committed file. `tests/content-policy.test.ts` and `tests/shipped-content.test.ts` were run, then the file was restored with `git checkout HEAD --`, and `git status` was clean after each. **(1) A lapsed image back to a warning in prod** (both new `errors.push` changed to `warnings.push`) → 9 fail: all 3 prod cases, all 3 dev cases (nothing in the errors or the printed problems), and all 3 integration cases. **(2) A dev build refusing it** (`enforcePublishingPolicy` also throws when an error says "whose consent") → 3 fail, the three dev cases. **(3a) "Current season" one season early in the image rule** (the season passed to `isStale` moved back a year) → 6 fail. These are the consented image in the unit cases, in "builds … in prod and in dev" and in the shipped copy; "another season" in prod and in dev; and the integration case for last season. **(3b) The season start one year early, inside the shared `isStale`** → 6 fail: "not checked this season" in prod, in dev, in t11's check and in the integration case; the `isStale` unit case; and the warning case. My first form of 3b moved `seasonStart` itself. That also moved the schedule loader's season, and `content-policy.test.ts` failed at collection ("2026-10-30 is outside the 2026-27 season"), so it is not counted as a catch. I redid it inside `isStale`. vitest keeps no Hypothesis database, so agreement 8's fresh-database rule has nothing to apply to. |
| Affected set (agreement 10) | Over two minutes; left to the pull request's `ci` | `uv run scripts/affected_tests.py` → 46 test files, `site/ changed: the site's own pnpm checks test it; pytest does not.` Its pytest command, `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" -q $(cat affected.txt)`, reached about 92% with no failure and was stopped by the alarm at 115 s, with load 7 to 11. I stopped its orphaned workers. Most of the 46 files are false edges: `ops/caselist_run/check_image.sh` and `scripts/install_channel.sh` mention `media-consent`. The pull request's `ci` runs the same set. Within the two minutes, as agreement 10 says, I ran the always-run directories and every file that reads the guide, the site README or the spec. That was `tests/architecture tests/specs tests/docs`, the four `test_file_recipes*`/`test_caselist_sync_*` files that name them, and 11 files under `tests/scripts/` (promotion source, promotion guard, site deploy, validate-dev, back-merge, refresh, command blocks, docs index, task restart). Result: `1691 passed in 36.06s`. After writing this report, I ran `tests/architecture` again, because it reads session reports: `247 passed in 20.77s`, along with `check_command_blocks.py --base origin/dev` (OK, the report included) and `check_links.py` (OK). |
| Whole-repo checks | PASS | `uv run --frozen ruff format --check` → `1620 files already formatted`. `uv run --frozen ruff check` → `All checks passed!`. `uv run --frozen pyright packages` → `0 errors, 0 warnings, 0 informations` (no Python changed). `uv run --frozen lint-imports` → `Contracts: 19 kept, 0 broken.` `check_thin_handlers.py` → OK, 68 handlers. `check_links.py` → OK, 3000 links. `check_command_blocks.py` → OK, 588 blocks. `docs_index.py --check-descriptions` → all 59 described. `uv run scripts/validate_specs.py` (after setting the Goal to Succeeded) → `OK: 512 files, 40 epics, 450 tasks, 22 releases`. |

## Files changed

* **`site/src/lib/publishing-policy.ts`**: when a page references an image that has a consent
  entry, the entry is now checked as well as found. The rule finds the entry by path. A reference
  still to come is an error, and so is a lapsed entry by `isStale`. Each error names the image by
  its path, never by who it shows. An image with no entry and no `nonPersonImages` line is still
  refused as before.
* **`site/src/lib/media-consent.ts`**: `isReferenceToCome(reference)`, lifted out of
  `consentPlaceholders` so that the placeholder finding and the image rule share one test. The
  `isStale` docstring now says what is a warning and what is an error.
* **`site/tests/content-policy.test.ts`**:
  * the new `describe('an image whose consent has lapsed')` (seven cases);
  * three integration cases under "every image entry";
  * the reworded warning case (Decisions);
  * `vi` imported for the `console.warn` spy.
* **`site/README.md`**: the content guard's table and its warning paragraph.
* **`docs/guides/coach-website-editing.md`**: two sentences, at Publish a change and at the start
  of a new season.
* **`plan_specs/.../t12-stale-image-consent-refused.yaml`**: Goal phase only.
* Not changed:
  * any dependency manifest or lockfile under `site/`, and anything under `site/content/`:
    `git diff --stat origin/dev...HEAD -- site/package.json site/pnpm-lock.yaml site/content` is
    empty. I installed the dependencies with `pnpm install --frozen-lockfile --offline`, which
    writes neither;
  * any workflow file.

## Deviations from the spec

None.

## Decisions and assumptions

* **What I reused for "current season".** I used `isStale(entry, consent.season)` from
  `src/lib/media-consent.ts`, the test the name rule in the same loop applies. An entry is stale
  when its `season` is not the manifest's, or its `dateChecked` is before `seasonStart` (1 August).
  "A reference still to come" is the `[[TBD]]` test from `consentPlaceholders`. I lifted it out as
  `isReferenceToCome` and did not copy it. There is no second definition of either.
* **A reference still to come is refused by the image rule itself.** In the build it was already
  an error on `content/media-consent.yaml`, through `consentGuardedContent`. That only works when a
  caller passes those pages, so the image rule now refuses one too, against the page that shows
  it. A prod build with such an entry therefore reports two errors, one on the manifest and one on
  the page. A lapsed name works the same way: a warning on the entry, and an error on the page.
* **"A warning in a dev build" is the guard's existing dev path.** The lapse is an error in the
  report. `enforcePublishingPolicy` prints errors in dev under "Publishing policy problems, which
  will fail a prod build:" and does not throw, as it does for every other error. The dev tests
  check the printed block as well as the report.
* **The entry-level warning stays.** An entry no page shows, with stale consent, still only warns.
  That is the start-of-season reminder, and nothing is published against it. The existing case
  "warns, rather than failing, when an entry predates the current season" used to put the stale
  image on a page and expect no error. That pinned the behaviour this task removes, and with the
  change it failed (red run of the changed file). It now shows the image on no page, under the
  name "…when an entry nothing shows predates the current season", and still asserts the warning
  and no error. The new describe block covers the case with the image on a page. This makes the
  guard stricter, not weaker.
* **An image path listed in both `images` and `nonPersonImages` is now checked against its
  consent.** Before, either list was enough. Listing a photograph of a person as "nobody in it"
  should not exempt it, so the consent entry governs. The shipped manifest has no such path.
* **Messages name the image by its path, never by who it shows.** That matches the existing
  no-entry message, and the policy already keeps student names out of paths (Students 10-11).
* **Fixtures are synthetic:** `/photos/planted-orientation.jpg`, `MC-PLANT-001`,
  "2 team members, both covered". No person's name.

## Operator follow-ups

None.

## Follow-up work

* **The manifest's header comment understates the build (site content, not touched).**
  `site/content/media-consent.yaml` says an entry whose `dateChecked` predates the season "WARNS".
  That is true of the entry. But a name or an image that a page publishes against such an entry
  has failed a prod build since v1-e36 (names) and since this task (images). The PM asked me not to
  touch shipped content. A one-line comment fix could go through the site lane, or into the next
  task that edits the manifest.
* **A `dateChecked` after the season ends is not stale to the build, for names or for images.**
  For a manifest in `2026-27`, `isStale` accepts an entry checked on `2027-08-02`. t11's tests
  refuse that date for both image and student entries, so CI catches it, but a prod build on its
  own does not. Adding it to `isStale` would change both rules at once, and the results page
  reuses it too (`site/src/lib/results.ts`). If the PM wants it, it belongs in E37 as a small `site/src/` task.
* No CI change is needed. The new tests are in `site/tests/`, which the site job already runs.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

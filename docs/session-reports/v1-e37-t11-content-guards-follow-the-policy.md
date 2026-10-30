# Session report: v1-e37-t11-content-guards-follow-the-policy

| | |
|---|---|
| Task | `v1-e37-t11-content-guards-follow-the-policy` — The shipped-content checks follow the publishing policy, and a season change is one edit of three files |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t11-content-guards-follow-the-policy.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t11-content-guards-follow-the-policy.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t11-content-guards-follow-the-policy` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

This task closes the three loose ends v1-e37-t10 left.

* **(a) The schedule's no-`@` check follows the allowlist.** It is now one of the checks in
  `site/tests/shipped-content.test.ts`, and it reads the raw file. An `@` passes only as part of a
  whole address that the guard's own `contactDetails` finds and that the guard's allowlist lists.
  That allowlist is `contactEmails` in content/site.yaml. The coach's address in a tournament's
  notes passes every check. Any other address fails, and so does the coach's address inside a
  longer one, a bare `@`, and every phone number, including one next to the coach's address.
* **(b) The guide's start-of-season steps** say to change `season` in the schedule, the results
  and the consent file in one edit.
* **(c) The `images: []` pin is gone.** In its place is a check that every image entry has a
  consent reference that has been filled in, and consent for the manifest's season, checked
  inside it. A consented image in a copy of the shipped content passes both this check and the
  guard. Unconsented images fail.

Each change was shown red first. The PM's four mutants are caught, and three more besides.

Look first at one deviation. Probing the season change for (b) showed that three of the guard's
own unit cases borrowed the shipped season. Two of them failed after a season change even with
every consent entry re-checked, so a season change still needed a test edit. I gave those cases
a fixed season of their own. After that fix, a full season change passes 947/947 with no test
edit.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `content-guards-follow-the-policy` (Content guards and the policy) | Done | (a) and (c) in `207d402`, (c)'s end-of-season case in `ca1bb0d`, the guide in `b029738`, the unit cases' own season in `3c5bb59`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the allowlisted address in a tournament's notes passes, any other address and a phone number still fail; a consented image passes the content checks; tests shown failing first | PASS | **Red, (a).** I moved the check into the `checks` table unchanged (any `@` refused). `pnpm exec vitest run tests/shipped-content.test.ts` → `Tests 2 failed \| 20 passed (22)`. The two failures: "the allowlisted coach address in a tournament's notes", where the check threw for the address, and "a phone number beside the allowlisted address", where it threw for the `@` before reaching the phone. A refuse-nothing skeleton (the check returns at once) → `5 failed \| 17 passed (22)`: every refusal case fails. **Red, (c).** With the image check written as the old pin (any image is a problem), `pnpm exec vitest run tests/content-policy.test.ts -t "every image entry"` → `4 failed \| 3 passed`. The consented image fails, and the three refusal cases fail on their messages. A refuse-nothing skeleton, with the end-of-season case added → `4 failed \| 4 passed`. **Green.** `pnpm exec vitest run tests/content-policy.test.ts tests/shipped-content.test.ts` → `93 passed (93)`. That covers: the coach's address passes every check on a copy; another address, the coach's address inside a longer one, a bare `@`, a seven-digit phone number and a phone next to the coach's address are each refused; a consented image passes the image check and the guard; images with last season's consent, consent not checked this season, consent checked after the season ended, a reference still to come, no reference, or no manifest entry at all are each refused. |
| ac2: the guide's start-of-season steps name the three files together | PASS | `docs/guides/coach-website-editing.md`, "At the start of a new season" (line 176) names `site/content/tournaments.yaml`, `site/content/results.yaml` and `site/content/media-consent.yaml` to change in one edit, and says what else changes in each. Both of its claims were probed on the shipped content, uncommitted and then restored. Changing `season` in the schedule alone → the `oneSeason` check fails. Changing all three, with the results emptied → only the consent-entry checks fail (4 tests). Adding a simulated start-of-season check (entries moved to 2027-28 and re-checked, the 2027 graduate's entry removed) → `Tests 947 passed (947)`, with no test edit. |
| Node `content-guards-follow-the-policy`: `pnpm --dir site test` | PASS | `pnpm lint && pnpm typecheck && pnpm test` in `site/` → eslint and tsc silent, `Test Files 27 passed (27)`, `Tests 949 passed (949)`. |
| Prod export checks (the PM's list) | PASS | `SITE_ENV=prod SITE_URL=https://wfbdebate.com site/scripts/export-checks.sh` → exit 0, `Test Files 12 passed (12)`, `Tests 109 passed (109)`, 11 s. |
| Mutants (the PM's four, agreement 8) | PASS | Each mutant was applied to the committed file, its suite run in full, then restored with `git checkout HEAD --`. **(1) Allowlist ignored** (`allowlisted` an empty set) → 2 fail: the coach's address in a note, and the phone next to the coach's address (refused for its `@` instead). **(2) Any address allowed** (every address `contactDetails` finds counted as listed) → 2 fail: another address, and the coach's address inside a longer one. **(3) Phone number allowed** (the phone rule `if (false)`) → 2 fail: the seven-digit number, and the phone next to the coach's address. **(4) An unconsented image passing.** (4a) the image check emptied → 4 fail (last season, not checked this season, checked after the season, reference to come). (4b) the season rule removed → 3 fail. (4c) the reference rule removed → 1 fails. (4d) only the after-the-season-ends date removed → 1 fails. The case for (4d) was added after the first round showed that sub-rule had none (`ca1bb0d`). vitest keeps no Hypothesis database, so agreement 8's fresh-database rule has nothing to apply to. |
| Affected set (agreement 10) | PASS | `uv run scripts/affected_tests.py` → 28 test files: the always-run list, plus the docs and script tests that `docs/guides/` and the report reach. I ran the same pytest command `--run` uses (`python -m pytest -n auto -m "not slow and not live"` over those files), but called it directly with the time limit on the interpreter: `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" $(cat affected.txt)` → `1663 passed in 91.57s`, exit 0 after 94 s. It also printed `site/ changed: the site's own pnpm checks test it; pytest does not.` |
| Whole-repo checks | PASS | `uv run --frozen ruff format --check` → `1609 files already formatted`; `uv run --frozen ruff check` → `All checks passed!`; `uv run --frozen pyright packages` → `0 errors, 0 warnings, 0 informations` (no Python changed); `uv run --frozen lint-imports` → `Contracts: 18 kept, 0 broken.`; `uv run --frozen python scripts/check_thin_handlers.py` → OK, 68 handlers; `uv run --frozen python scripts/check_links.py` → OK, 2960 links; `uv run --frozen python scripts/check_command_blocks.py` → OK, 587 blocks; `uv run --frozen python scripts/docs_index.py --check-descriptions` → all 59 described; `uv run scripts/validate_specs.py` → `OK: 509 files, 40 epics, 447 tasks, 22 releases` (after setting the Goal to Succeeded). |

## Files changed

* **`site/tests/shipped-content.test.ts`**
  * The old `it` ("carry no email address or phone number in the schedule") becomes the
    `scheduleContactDetails` check. It reads each tournament's published words from the raw file
    (`publishedText`: name, where, `byEvent` where, condition, notes), the same fields as before.
    It reads the allowlist from `loadSiteSettings(directory).contactEmails` and finds addresses
    with the guard's `contactDetails`.
  * `ALLOWLISTED` (the coach's address, read from content/site.yaml) is used for the plants.
  * A new block, "an edit the publishing policy allows passes every check", runs every check on a
    copy with the coach's address in a note.
  * Five new refusal cases.
* **`site/tests/content-policy.test.ts`**
  * The pin "with no photograph in it yet" becomes "has a media-consent manifest for the current
    season", plus the new `describe('every image entry')`. That block has one check on the shipped
    manifest, a consented image passing on a planted copy, and six refusals.
  * New module-level helpers: `imageEntryProblems`, `consentedImage`, `withImage` (which plants an
    entry at the head of `images:`, whether the list is `[]` or holds entries) and `guardErrors`.
  * `CASE_SEASON` for the three guard unit cases (Deviations).
* **`docs/guides/coach-website-editing.md`**: the start-of-season steps.
* **`plan_specs/.../t11-content-guards-follow-the-policy.yaml`**: Goal phase only.
* No file under `site/src/` and no dependency manifest or lockfile under `site/` changed:
  `git diff --stat origin/dev...HEAD -- site/package.json site/pnpm-lock.yaml` is empty. I
  installed the dependencies with `pnpm install --frozen-lockfile --offline`, which writes
  neither.

## Deviations from the spec

* **Three guard unit cases now carry their own season. This goes beyond the spec's (a), (b) and
  (c).**
  * The cases are in `content-policy.test.ts`: "accepts an image with a current-season consent
    entry", "passes when the student has a current-season consent entry", and "warns, rather than
    failing, when an entry predates the current season".
  * Each one set its entry's season to the shipped manifest's (`consent.season`) but hard-coded
    2026 dates. One also expected the text "for 2026-27".
  * The probe for (b) moved all three content files to 2027-28 and re-checked every consent entry.
    The second and third cases still failed, so a season change needed a test edit. That is the
    thing the task's title says it no longer needs, and the guide's new sentence would have been
    wrong. The first case kept passing, but only because a stale image entry is a warning, not an
    error.
  * They now set `CASE_SEASON = '2026-27'` on both the entry and the manifest they check, so they
    test the guard as before, whatever season ships. Nothing is weakened: each still asserts what
    it did, against a season it states. Commit `3c5bb59`, kept separate so it can be reviewed on
    its own.
* **The affected set was run as the same pytest command `--run` uses**, not through
  `affected_tests.py --run`. The reason is agreement 10's rule that a time limit goes on the
  interpreter, not on `uv`: the load average was 15 to 19, and t10's set of similar size took
  167 s. The file list is the script's own, and so are the markers and `-n auto`.

## Decisions and assumptions

* **"Follows the allowlist" means a whole address, judged the way the guard judges it.** The check
  counts the `@`s in a field and the allowlisted addresses `contactDetails` finds there. One `@`
  more than the listed addresses fails the field. This leaves the guard's address pattern and the
  allowlist in one place each, as the PM asked. It also means the coach's address embedded in a
  longer one (`team.<address>`) fails, as it does in the build. Removing the allowlisted string
  from the text before looking for `@` would have let that through.
* **The rest of the check stays exactly as strict as before.** It still refuses any `@` that is
  not part of an allowlisted address: a handle, or "Meet @ the east doors". It still uses the old
  phone pattern `\d{3}[\s.-]\d{4}`, which catches a seven-digit local number that the guard's
  3-3-4 pattern does not. The forbidden list allows loosening only as far as the allowlist.
* **The check reads the raw file, not `loadSchedule`.** `loadSchedule` runs the policy guard
  itself, so a planted address would be refused by the loader first. That would hide mutant (2),
  which is the masking t10's design avoids for every other check.
* **The image check is as strict as the student-entry check beside it, which is stricter than the
  build.** The build only warns on a stale image entry (`isStale` → warning). The test fails on
  one, as it already does for a stale student entry. The policy says consent does not carry over
  between seasons. The image's season and date-checked are the "season" the PM named, and a
  `[[TBD]]` reference fails a prod build, so the check counts it as no reference.
* **The guide says what happens to the results at a season change.** The season-dates check
  refuses last season's results, so the steps say to take them out (`results: []` until the new
  season's first). The steps also say the consent entries are Charlie's start-of-season check,
  linked to the policy's section, and that the tests fail until it is done. The probe confirmed
  both statements.
* **The plants contain no person's name.** They are an image path under `/photos/planted-…`, the
  reference `MC-PLANT-001`, alt text "Two team members at orientation", and the invented tournament
  "Plantedtown". The probes edited the real consent file only in an uncommitted working tree,
  restored afterwards, and no name from it is printed here.

## Operator follow-ups

None.

## Follow-up work

* **The build publishes an image whose consent has lapsed, with only a warning (v1-e36/v1-e37,
  the PM's ruling).**
  * In `checkPublishingPolicy`, a referenced image needs only a manifest entry. A stale image
    entry is a warning, while a named student with stale consent is an error.
  * The publishing policy says a photograph publishes only against a current-season form.
  * After this task, `pnpm --dir site test` (and so CI) refuses a stale image entry, but a prod
    build on its own would publish one.
  * If the PM agrees, the guard could treat a stale image the way it treats a stale name. That
    change is in `site/src/`, so it is outside this task.
* **A graduated student's consent entry fails the tests at a season change.**
  * "Entry 1 publishes a whole name with a plausible graduation year" fails once a student's
    graduation year is before the new season's end.
  * That is correct: the entry should go at the start-of-season check. The guide covers it as
    "brings each entry up to date".
  * The PM may want the policy's start-of-season checklist to name removing graduates explicitly.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-30

**Notes:**

The content checks follow the policy, and a whole season change now needs no test edit, shown.
1. **ac1 passes.**
   * (a): red twice, the moved-unchanged check and a refuse-nothing skeleton. The coach's address in a
     note passes every check. Any other address fails, and so do the coach's address inside a longer
     one, a bare `@`, a seven-digit number and a phone next to the coach's address.
   * (c): red twice. A consented image passes the check and the guard, and six unconsented shapes fail.
2. **ac2 passes, probed.** The schedule alone fails `oneSeason`. All three files with the results
   emptied fail only the consent entries. A simulated start-of-season check passes 947/947 with no
   test edit.
3. **Mutants:** the PM's four, with (4) four ways. All are caught. The after-the-season-ends date had
   no case until the first round showed it, and now it does. Good.
4. **Deviation 1, the three guard cases' own season: accepted, and right.** The probe found that a
   season change still needed a test edit, the one thing this task's title rules out. Each case now
   states its season, and asserts what it did before. **Deviation 2** (the affected set run directly,
   with the time limit on the interpreter): accepted.
5. **Decisions accepted:**
   * a whole address judged by the guard's own `contactDetails` and allowlist, so an embedded
     address still fails;
   * everything else as strict as before;
   * the raw file read, so the loader's guard doesn't mask mutant (2);
   * the image check as strict as the student check;
   * the guide's results and consent sentences;
   * plants with no person's name.
6. **Follow-up work, the PM's rulings:**
   * **A stale image published with only a warning:** the publishing policy says a photograph needs a
     current-season form, so the prod build should refuse a stale image as it refuses a stale name.
     The PM's next batch files it at E37 p2, a change in `site/src/`. No image is published today.
   * **Graduates at a season change:** the PM proposes to the coach adding "remove the entries of
     students who have graduated" to the publishing policy's start-of-season checklist, in its next
     version.
7. **The affected set ran:** 28 files, 1,663 passed in 92 s. The site's checks (949 and the 109 export
   checks), ruff, pyright, lint-imports, the links, the command blocks, the docs index and the specs
   pass.
8. **Merge:** any time. It changes only `site/tests/` and the guide, so nothing on the public site
   changes. The next lane run that syncs from dev carries it to `main`.

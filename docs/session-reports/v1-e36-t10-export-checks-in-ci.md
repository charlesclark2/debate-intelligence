# Session report: v1-e36-t10-export-checks-in-ci

| | |
|---|---|
| Task | `v1-e36-t10-export-checks-in-ci` — The export checks run against an export |
| Spec | [`plan_specs/v1/e36-team-website/t10-export-checks-in-ci.yaml`](../../plan_specs/v1/e36-team-website/t10-export-checks-in-ci.yaml) |
| Epic / release | `v1-e36-team-website` / `v1.6` |
| Branch | `task/v1-e36-t10-export-checks-in-ci` |
| Session status | COMPLETE |

## Summary

The tests that read the built site now run on every CI run, against an export built from the tree under test, and fail rather than skip or pass when that export is missing or stale. The spec names four tests. **The real number was 76 tests in 10 files.** A clean-tree run of CI's own invocation reported `668 passed | 76 skipped`, exit 0. The 76 include the whole third-party-script suite from v1-e37-t05, the stylesheet check written after the unstyled-export incident, and the axe pass over the exported HTML. None of them had ever run in CI. I moved all 76 into their own suite, `site/tests/export/`, which runs as a second pass straight after the build (`site/scripts/export-checks.sh`, called at the end of `pre-commit-checks.sh`), so `pnpm test`, the inner loop, is unchanged. Each build records what it was built from, and the export suite refuses to load unless that record matches the sources, the `SITE_*` settings and the export bytes. Both mutations (an unallowed address and a third-party `<script src>`) are shown passing in CI's invocation before the change and failing, by name, after it.

**For the PM, first:**
- **Deviations 1 and 2:** scope widened from 4 tests to 76, and edits outside `constraints.packages`. The runbook edit is the one that matters; without it the prod-promotion precondition would have silently stopped checking the export.
- **Follow-up 1:** a Succeeded spec's command that now finds no file.
- **Recurring pattern:** a fourth candidate instance of the check-that-reports-success-while-checking-nothing pattern.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `show-the-skip` (show that the checks never run in CI) | Done | Clean worktree, no `site/out`, `site/scripts/pre-commit-checks.sh` → exit 0, `Tests 668 passed \| 76 skipped (744)`. Per file below. I also ran both mutations and the incident replay under this arrangement before changing anything, so the "before" half of the mutation node comes from the unmodified code. |
| `make-them-run` (build before the checks, and fail on a missing or stale export) | Done | Export-reading tests moved to `site/tests/export/*.export-test.ts`. A recorded build (`build-export.mjs`) feeds a freshness check (`export-fingerprint.mjs`, enforced on import by `built-export.ts`), and `export-checks.sh` runs build then checks. A guard test in the ordinary `pnpm test` covers the arrangement. |
| `mutation` (prove the checks by mutation) | Done | Both mutations run from a clean tree through `pre-commit-checks.sh`, old arrangement and new. Restored; tree clean (`git status --short` empty). |

**Baseline, per file** (old arrangement, clean tree, CI's invocation):

```
✓ tests/content-policy.test.ts (48 tests | 2 skipped)
✓ tests/navigation.test.tsx (39 tests | 13 skipped)
✓ tests/no-third-party-scripts.test.ts (11 tests | 9 skipped)
✓ tests/visual-qa.test.ts (19 tests | 1 skipped)
✓ tests/routes.test.ts (41 tests | 16 skipped)
✓ tests/login-flag.test.tsx (10 tests | 1 skipped)
✓ tests/contact.test.ts (8 tests | 2 skipped)
✓ tests/stylesheet-ships.test.ts (12 tests | 10 skipped)
✓ tests/faq.test.tsx (77 tests | 5 skipped)
✓ tests/pages-a11y.test.tsx (43 tests | 17 skipped)
Test Files  20 passed (20)
     Tests  668 passed | 76 skipped (744)
site checks: pnpm --dir site build
→ exit 0
```

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: the export checks run against an export built from the tree under test, in CI and on a developer's machine, every time | PASS | `rm -rf site/out site/.next <build record>; site/scripts/pre-commit-checks.sh` (the exact `run:` step of the `site` job in `ci.yml`, and the `site-checks` pre-commit hook's entry) → exit 0 in 17.1s: `pnpm test` 683 passed, 0 skipped; `site export: recorded 69 exported files against source 085bb9ef7c05`; export suite `Test Files 10 passed (10)`, `Tests 78 passed (78)`. The 78 are the 76 previously skipped tests plus the two pattern tests that moved with `no-third-party-scripts`. The run cannot pass without a build of the current sources (see ac3 and ac4). The first ubuntu run happens on this PR; if the export suite did not run or found no export, that run fails. |
| **ac2**: mutation proves it in CI's own invocation, before and after | PASS | Both mutations were saved as patches and applied identically to both arrangements, each from a clean tree (no `site/out`, `.next` or build record), through `site/scripts/pre-commit-checks.sh`. **Address** (`Questions: debate@wfbschools.com` added to `SiteFooter.tsx`, so it is on every page): before → exit 0, `668 passed \| 76 skipped`, while `site/out/index.html` contained the address. After → exit 1, `content-policy.export-test.ts` fails with `/404/ publishes debate@wfbschools.com` and the policy message `publishes the email address "debate@wfbschools.com", which is not in the allowlist`. **Script** (`<script async src={visitCounter} />`, URL `https://counter.example.org/count.js`, in `SiteFooter.tsx`): before → exit 0, `668 passed \| 76 skipped`, script present in `site/out/index.html`. After → exit 1, 3 failures, including `no-third-party-scripts` with `404/index.html loads a script from another origin` and `"<script src=\"https://counter.example.org/count.js\">"`. **Restored**, clean tree → exit 0, 683 + 78 passed. `git status --short` empty. |
| **ac3**: skipping is loud | PASS | **No export:** `rm -rf site/out` then the export suite → exit 1, `Failed Suites 10`, each with `ExportFreshnessError: There is no export in site/out/ … They fail rather than skip`. **Reordered script:** check moved before build in `export-checks.sh`, run on a clean tree → exit 1, same error. The ordinary `pnpm test` also fails, on `builds before it checks in export-checks.sh`. **Export step deleted** from `pre-commit-checks.sh` → `pnpm test` fails with `pre-commit-checks.sh no longer runs export-checks.sh`. **`it.runIf(hasExport)` reintroduced** in `contact.test.ts` → `pnpm test` fails with `has no runIf, skipIf, skip, todo or only in any site test`. All restored. |
| **ac4**: a stale export cannot produce a pass | PASS | **Twice without rebuilding**, unchanged tree → both runs exit 0, 78 passed. That is correct: same bytes from the same tree. **The incident, replayed:** export built from the mutated tree, then sources restored. Before → exit 1, with 3 assertion failures against a correct tree. After → exit 1, before any test runs: `site/out/ is stale … Since it was built: changed src/components/SiteFooter.tsx`. **Unrecorded export** (a plain `pnpm build`, which could be from any commit) → exit 1, `was not built by site/scripts/build-export.mjs`. Other cases are pinned by unit tests in `tests/export-checks-run.test.ts` (17 tests, in every `pnpm test`): a source file added or removed, a different `SITE_ENV` or `SITE_DEBATER_LOGIN`, a git-ignored `site/.env.local` appearing, and the export edited after the build. All fail naming what differs. An unrelated variable does not count, and neither does an edit under `tests/`. |
| Node `show-the-skip`: the four export tests are shown skipping on a clean tree | PASS | Baseline above: exit 0 with 76 skipped, among them the spec's four (`contact.test.ts` built contact page, `content-policy.test.ts` ×2 over `builtPages`, `faq.test.tsx` exported FAQ). |
| Node `make-them-run`: `site/scripts/pre-commit-checks.sh` passes from a clean tree | PASS | See ac1: exit 0, 17.1s. |
| Node `mutation`: both mutations fail after the change and pass before it | PASS | See ac2. |

**What it costs.** The PM asked me to measure both acceptable shapes. Timings are warm-cache, two runs each, on the operator's Mac; this machine's timings are noisy.

| | Old arrangement | Second pass (chosen) | Build before tests (not chosen) |
|---|---|---|---|
| Inner loop, `pnpm --dir site test` after an edit | 5.2–7.0s, checks nothing built | 5.2–7.0s, unchanged; reads only sources and skips nothing | Rebuild needed first: + 2.3–2.7s warm (5.2s cold). Otherwise the stale check fails the run |
| `site/scripts/pre-commit-checks.sh` (CI, hook) | 12.5–16.5s | 16.8–20.1s warm; 17.1–18.5s from a clean tree | About the old figure plus the 78 tests' run time (vitest is started once, not twice) |
| Added to CI | — | Export pass 2.9–4.1s, mostly a second vitest start-up. The record adds ~15ms per check; the build itself is unchanged (2.3–2.7s warm) | Roughly 2s less than the second pass |

I chose the second pass. It costs CI about 2s more than reordering would, and in exchange `pnpm test` never needs a build. Reordering would make every inner-loop run after an edit either rebuild or fail on staleness, and that is the bypass the PM warned about. The `site` job stays far inside the 5-minute budget.

## Files changed

- **`site/scripts/`**: `export-fingerprint.mjs` (new; what an export was built from, and the freshness check), with `export-fingerprint.d.mts` holding its types. `build-export.mjs` (new): runs `pnpm build` and writes the record to `site/node_modules/.cache/site-export-build.json`, outside `site/out`, so it can never be deployed. It deletes the old record first, and writes none if the sources changed during the build. `export-checks.sh` (new): build, then the export suite. `pre-commit-checks.sh`: lint, typecheck and test, then `export-checks.sh`.
- **`site/tests/export/`** (new): `vitest.config.ts` (the export suite: the site config with its own `include`), `built-export.ts` (every export check reads the export through it, and it throws on import unless the export is fresh), and ten `*.export-test.ts` files holding the 76 tests, moved verbatim apart from their gating and paths. No assertion was changed. `no-third-party-scripts` moved whole (`git mv`), its two pattern tests included.
- **`site/tests/`**: the ten source files lose their export sections and `hasExport`. `export-checks-run.test.ts` (new, 17 tests) pins the freshness check, bans `runIf`/`skipIf`/`skip`/`todo`/`only` across the site tests, and checks the wiring: `pre-commit-checks.sh` runs `export-checks.sh` after the source tests, `export-checks.sh` builds before it checks, and `ci.yml` runs `pre-commit-checks.sh`.
- **`.github/workflows/ci.yml`**: comment only; the job already calls the script.
- **`site/README.md`, `docs/runbooks/team-website.md`, `docs/guides/parent-email-updates.md`**: see Deviation 2.

## Deviations from the spec

1. **Scope is 76 tests in 10 files, not "four tests".** The spec, the epic node and the PM note all count four, in `contact`, `content-policy` and `faq`. The baseline shows 76 tests gated the same way, all skipped in CI. They include `no-third-party-scripts` (9, v1-e37-t05's built-output guarantee), `login-flag` (1, no live login link in the export), `routes` (16), `navigation` (13), `pages-a11y` (17, axe over the exported HTML), `stylesheet-ships` (10, written after the unstyled export) and `visual-qa` (1). The spec forbids "leaving any publishing-policy check able to pass by skipping", which covers at least the third-party-script and login-link tests. Moving only four would also have left the suite with the exact failure mode this task exists to remove. So I moved all 76 through the same mechanism and changed none of their assertions. The PM may want the spec's description amended to say 76.
2. **Edits outside `constraints.packages`** (`site/scripts`, `site/tests`, `.github/workflows`), all documentation:
   - **`docs/runbooks/team-website.md`, promotion preconditions 1–3. This is the one that matters.** Precondition 3 ran `pnpm --dir site test` after a prod build to check the export. After this change that command no longer contains the export checks, so the runbook would silently have stopped checking the export before a prod promotion, which is this task's pattern again. It now runs `SITE_ENV=prod SITE_URL=https://wfbdebate.com site/scripts/export-checks.sh`, which I ran: exit 0, 78 passed against a prod export. The source half stays `pnpm test`.
   - **`site/README.md`** documented the old arrangement as intended ("skip themselves when it is absent rather than failing"), so it is rewritten as a section on the export checks.
   - **`docs/guides/parent-email-updates.md`** gets a one-line path fix for the moved test.
   - `site/package.json` and `site/vitest.config.ts` are deliberately untouched. The export suite has its own config under `site/tests/export/`, and is invoked by script rather than through a new `pnpm` script.

## Decisions and assumptions

- **Fail, not rebuild, when stale.** The spec allows either. Having a test runner build behind the user's back hides a multi-second step and a build failure inside "tests". So the suite fails, says what differs, and gives the one command that fixes it. `export-checks.sh` always builds first, so CI and the hook never hit this.
- **What counts as a build input:** every file under `site/` that git sees (tracked, or untracked and not ignored), minus `tests/`, plus `site/.env*`. Next reads `.env*` files even though the root `.gitignore` ignores them. Also every `SITE_*` and `NEXT_PUBLIC_*` variable. Over-inclusion only costs a rebuild; under-inclusion is the bug. `tests/` is left out so that editing an export check does not need a rebuild; the build never reads it. The record also hashes the export, so an export changed after the build (a plain `pnpm build`, a hand edit) is caught too.
- **No vitest `globalSetup`.** I tried one, so a failure would print once. But when it throws, vitest first prints "No test files found, exiting with code 1", which points at the wrong problem. The per-file check gives "Failed Suites 10", each with the real reason, so I kept that.
- **Where the address mutation goes.** ac2 says to "change a published address". Every published address today comes from `site/content`, and the source suite already checks those, so changing one fails under both arrangements and proves nothing about the export. The mutation has to sit where only the export shows it, so it adds an address in a component (the footer). For the same reason the script mutation passes its URL through a variable: `offline.test.ts` catches a literal `<script src="https://…">` in source.
- **Running the export checks by hand** uses the build's settings: `export-checks.sh` defaults `SITE_ENV=dev` as `pre-commit-checks.sh` does. Re-running only the suite needs the same `SITE_ENV`, and a mismatch fails with `changed SITE_ENV (environment)`.

## Operator follow-ups

None. Everything ran in seconds and offline.

## Follow-up work

1. **`plan_specs/v1/e37-calendar-and-announcements/t05-parent-email-signup.yaml`** (Succeeded) has a criterion command `pnpm --dir site test tests/no-third-party-scripts.test.ts`. The file moved, so that command now fails loudly (`No test files found, exiting with code 1`, exit 1); it does not pass by matching nothing. The equivalent today is `site/scripts/export-checks.sh`. I have not edited another task's spec; the PM may want to amend it.
2. **The recurring pattern: this is the third instance, and I found one more candidate.** These are checks that report success while checking nothing:
   - **First:** the import-linter key nobody read.
   - **Second:** the promotion guard whose job never ran.
   - **Third (this task):** 76 export tests that passed by skipping.

   **A candidate fourth, fixed after review in `fd86920`, as the PM asked:** `contact.export-test.ts` › "sets no cookie and uses no browser storage **anywhere in the export**" read only `contact/index.html`. It now reads all 69 exported files, unfiltered by extension, and is green against the current export. To see it fail for the reason it exists, I put `localStorage.setItem` on the FAQ page only. The old version passed (`Tests 2 passed`, exit 0); the widened one failed with `faq/__next._full.txt uses /localStorage/`. Mutation restored; a clean `pre-commit-checks.sh` run then gave exit 0, 683 + 78 passed.
3. **A smaller near-miss, renamed after review in `3b3f5e1`:** `content-policy.export-test.ts` › "publishes no address outside the allowlist and no phone number" checked only addresses. It is now "publishes no address outside the allowlist on any built page", with a comment saying that phone numbers are checked by the test before it, which runs the full policy over every built page. No assertion changed. That test's own name ("loads nothing from another origin and embeds no iframe") still understates it: the phone-number guarantee sits under a name that doesn't mention phones, so narrowing that test would remove it without any name warning you. Left as it is; the comment marks it.
4. **`pnpm --dir site qa`** (operator-only, v1-e36-t08) also reads `site/out/` and has no freshness check. The runbook now runs it straight after `export-checks.sh`, which makes it fresh in practice. Giving it `assertFreshExport()` would make that a guarantee.

**The two post-review commits are kept separate from the move** (`791774d`), so that commit stays a pure move: 76 tests relocated, no assertion changed. `fd86920` widens the storage check; `3b3f5e1` renames the address check. `scripts/task sync` was a no-op: `origin/dev` is still `b74dd15`, which this branch was created from.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED

**Reviewed by / date:** PM, 2026-10-01

**Notes:**

Accepted, phase `Succeeded`, with two small follow-on commits asked for below. This is the best
piece of work this project has produced, and the reason is the first paragraph of the summary.

**I wrote "four tests" and it was seventy-six.** I counted the failures I happened to see in one
pasted terminal output and wrote that number into the spec, the epic node and the kickoff prompt,
three times, as though it were a census. The session counted the gating instead. What that found is
materially worse than what I specified: beyond the four, the third-party-script guard from
v1-e37-t05, seventeen axe checks over the exported HTML, and the ten stylesheet-ships tests written
*after* an unstyled export reached the site had all never run in CI either. The accessibility of the
shipped pages and the question of whether the CSS actually ships were both being asserted by tests
that were not running. Moving only the four I named would have satisfied my words and left the
failure mode intact, which is the trap this task exists to close. Taking the spec's forbidden entry
("leaving any publishing-policy check able to pass by skipping") over its description was the right
reading of two instructions that disagreed.

**The arrangement chosen is the one I would not have thought to ask for, and the measurement is why
I believe it.** I said reordering or a second pass were both acceptable and to measure. You
measured: the inner loop stays at 5.2 to 7.0 seconds and reads only sources, while reordering would
add a rebuild-or-fail to every run after an edit. That is precisely the bypass I warned about, and
you showed it with numbers rather than agreeing with me in prose. Two seconds of CI for an inner
loop nobody is tempted to route around is the right trade.

**The freshness record is the part that makes it hold.** A build that records what it was built
from, a check enforced on import so no suite can read a stale export by accident, and the record
kept in `node_modules/.cache` rather than in `site/out` so it can never be deployed. Over-including
build inputs because "over-inclusion only costs a rebuild; under-inclusion is the bug" is the right
default stated the right way round, and excluding `tests/` so editing a check does not force a
rebuild is the detail that keeps the inner loop honest.

**ac3 is self-defending, which is more than it asked for.** `export-checks-run.test.ts` fails if
`pre-commit-checks.sh` stops calling `export-checks.sh`, if `export-checks.sh` stops building before
checking, if `ci.yml` stops running the script, and if anyone reintroduces `runIf`, `skipIf`, `skip`,
`todo` or `only` anywhere in the site tests. The mechanism now guards its own wiring. Every instance
of this pattern we have found was created by someone reordering or relaxing something innocuous;
this is the first fix that notices.

**Deviation 2's runbook edit is the single best catch in the report.** Promotion precondition 3 ran
`pnpm --dir site test` after a prod build to check the export. After this change that command no
longer contains the export checks, so the runbook would have gone on passing while checking nothing,
before a production promotion. The fix created a fresh instance of the bug it was fixing, one file
away, and you found it and ran the prod-settings version to prove the replacement works. Noticing
that your own change has moved someone else's guarantee out from under them is the hardest thing on
this list to do reliably.

**The mutation placement reasoning is test design of a high order.** Recognising that a content-file
address mutation would fail under *both* arrangements and therefore prove nothing about the export,
and moving it into a component so only the export shows it, is the difference between a mutation
test and a mutation-shaped ritual. Same for passing the script URL through a variable because
`offline.test.ts` already catches a literal one in source. You knew what each test actually covers.

**Two follow-on commits before you open the PR, both small, and both kept separate from the move so
that "76 tests moved, no assertion changed" stays verifiable as a pure move:**

1. Widen `contact.export-test.ts`'s "sets no cookie and uses no browser storage anywhere in the
   export" to read every exported file rather than `contact/index.html`. You were right that it
   belongs to v1-e36-t04's lineage, but you now own that file, the test's own name already claims
   the wider scope, and leaving a check whose name overstates what it reads is the pattern this task
   is named after. Your grep of all 69 files says the claim is true today, so this is cheap.
2. Rename `content-policy.export-test.ts`'s "publishes no address outside the allowlist and no phone
   number" to say what it checks. You established the phone guarantee holds through the test before
   it; a name that misleads the next reader is worth one commit to fix.

**Follow-up 1 handled, follow-up 4 filed.** I have amended v1-e37-t05's criterion to
`site/scripts/export-checks.sh` in this branch, and corrected t10's own description from four to 76
so the next reader is not misled by my count. `pnpm --dir site qa` reading `site/out` with no
freshness check is a real gap; the runbook now runs it straight after `export-checks.sh`, which
makes it fresh in practice but not by guarantee. I will file it rather than widen this task again.

**On the pattern count: you are right that this is the third instance, and your fourth candidate is
a genuine one.** Import-linter's unread key, the promotion guard whose job never ran, 76 tests that
passed by skipping. What the three share is not carelessness; each was created by a reasonable local
decision whose effect nobody checked from the outside. The useful generalisation, which I would like
in the next report that touches a check: a check earns trust only when someone has seen it fail for
the reason it exists.
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

# Session report: v1-e36-t08-prelaunch-visual-qa

| | |
|---|---|
| Task | `v1-e36-t08-prelaunch-visual-qa` — Pre-launch visual QA and launch readiness |
| Spec | [`plan_specs/v1/e36-team-website/t08-prelaunch-visual-qa.yaml`](../../plan_specs/v1/e36-team-website/t08-prelaunch-visual-qa.yaml) |
| Epic / release | `v1-e36-team-website` / `v1.6` |
| Branch | `task/v1-e36-t08-prelaunch-visual-qa` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The two guards from the `v1-e36-t07` review are in: the publishing-policy guard now **fails a prod
build while a required announcement field is unset**, and the media-consent name allowlist is
**phrases rather than bare words**, so reviewing "Blue Valley West High School" no longer leaves
Blue, Valley and West permitted on their own for ever. `scripts/site_smoke.py` gained the launch
surfaces, so `validate-dev` checks what the pages say and not only that they are up. The browser
QA command ships as `pnpm --dir site qa`, and the runbook carries a promotion checklist.

**The measured sweep has run and every page passes.** All eight pages score 100 on accessibility,
best practices and SEO and 95 or 96 on performance against a local **prod** build; axe-core is
clean on every page at all three widths with the colour-contrast rule enabled; nothing scrolls
sideways at 390, 768 or 1280px. The full output is under
[Measured results](#measured-results-the-qa-sweep). The room now carries `value: To be announced`
and the prod build exits 0 with the guard silent.

**Two things still need a human, so the Goal stays `InProgress`.** ac4 is a keyboard-only walk,
the FAQ print check and the two phone browsers; ac6 needs Charlie to tick the pre-publication
checklist against the commit to be promoted. Both have a block under **Operator follow-ups**.

**The guard did its job on the way through.** Before the room was filled, a prod build stopped
with one error and only one:

```
content/home.yaml: the Room of the "Parent information session" announcement is still unset
("The room is not set yet. It will be posted here before the session."). Replace unsetNote
with the value, or, if not knowing is the answer, with a value that says so such as
"To be announced".
```

That is the finding the review asked for, and the one the site had no way of producing since
`v1-e36-t06` replaced the `[[TBD]]` marker with a sentence.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `qa-command` — Operator-run browser QA command | DONE | `site/scripts/visual-qa.mjs`, the `qa` package script, `site/scripts/visual-qa-tools/` and the README section. Its offline parts are covered by `site/tests/visual-qa.test.ts` (19 tests) |
| `measured-sweep` — Scores, browser axe and responsive screenshots | DONE | Run by the operator on 2026-09-20 against a local prod build, after the one-time toolchain install. Output in [Measured results](#measured-results-the-qa-sweep); 24 screenshots written to the gitignored `site/qa-artifacts/screenshots/` |
| `human-checks` — Keyboard walk, print check and phone browsers | NOT RUN | A human at a keyboard and two phones. Follow-up 2 |
| `fill-room-and-prod-build` — Fill the October 1 room and prove a clean prod build | DONE | Charlie set the Room to `To be announced` in `fdd5122`, which the guard accepts as a decision rather than a gap. `SITE_ENV=prod SITE_URL=https://wfbdebate.com pnpm --dir site build` → exit 0, no publishing-policy output. See Decisions |
| `launch-readiness` — Promotion checklist and Charlie's sign-off | PARTIAL | The promotion checklist is in `docs/runbooks/team-website.md`. Charlie's pre-publication checklist tick is his. Follow-up 4 |

Beyond the graph, the four items the Goal description adds from the `v1-e36-t07` review:

| Review item | Status |
|---|---|
| A guard that fails a prod build while a required announcement field is unset | DONE |
| The media-consent allowlist as phrases rather than bare words | DONE |
| The first `tests/smoke/` entries for the site | DONE, with a correction — see Deviations |
| Home entry-point card labels aligned with the page titles | NOT DONE, left to `v1-e36-t09` — see Deviations |

## Acceptance criteria

### Goal criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** Per-page Lighthouse scores in the report; the audit exits non-zero below 95 on accessibility or best practices | PASS | `pnpm --dir site qa -- --min-accessibility 95 --min-best-practices 95` against a local prod build → exit 0, `8 pages clear the floor with axe clean at every width`. Scores for all eight sitemap pages under [Measured results](#measured-results-the-qa-sweep): accessibility and best practices 100 everywhere, performance 95 to 96, SEO 100. The floor itself is tested separately: `pnpm --dir site test visual-qa` → `19 passed`, including "fails a page below the accessibility floor" and "fails a page whose score was never produced, rather than assuming it" |
| **ac2** Per-page checklist at 390, 768 and 1280px; screenshots regenerated by one command and not committed | PASS | The widths table under [Measured results](#measured-results-the-qa-sweep): no horizontal overflow on any of the eight pages at any of the three widths. 24 screenshots (8 pages x 3 widths) written by the one command to `site/qa-artifacts/screenshots/`; `git status --porcelain` prints nothing, and `pnpm --dir site test offline` → `11 passed` includes "never commits a screenshot, an audit file or a score report". The navigation, hero and panel readings are the operator's, under ac4 |
| **ac3** axe-core in a real browser, no WCAG 2.1 AA violations, colour-contrast included, rule sets named | PASS | axe-core 4.13.0 in Chromium: **no violations on any page, at any width**. Rule sets are named in the output and are `wcag2a, wcag2aa, wcag21a, wcag21aa` with `color-contrast` explicitly enabled, which is the rule jsdom cannot evaluate and the reason this criterion exists. The jsdom pass (`pnpm --dir site test` → `647 passed`) stands alongside it, not instead of it |
| **ac4** Keyboard-only walk of every interactive element; FAQ prints every answer; both recorded item by item | NOT RUN | Needs a human. Follow-up 2 carries the item-by-item table to fill in |
| **ac5** The October 1 room filled in, no placeholder left, prod build exits 0 with the guard clean, alongside passing lint, typecheck and tests | PASS | `SITE_ENV=prod SITE_URL=https://wfbdebate.com pnpm --dir site build` → **exit 0**, with no publishing-policy output at all. The built export carries `<meta name="robots" content="index, follow">`, a `robots.txt` that allows crawling, a sitemap on `https://wfbdebate.com/`, and **no gap badge on the home page**. `pnpm --dir site lint` → exit 0; `typecheck` → exit 0; `test` → `647 passed`. The room reads `To be announced`, which is a decision rather than a gap; see Decisions |
| **ac6** Promotion checklist in the runbook; Charlie has ticked the pre-publication checklist for the launch commit | PARTIAL | Checklist: `grep -n "Promotion checklist" docs/runbooks/team-website.md` → line 836; it carries the six preconditions, the seven promotion steps and a table of what to do if it looks wrong. Charlie's tick: Follow-up 4 |

### Node criteria

| Node → criterion | Status | Evidence |
|---|---|---|
| `qa-command` → QA script exists and enforces a score floor (`site/scripts/visual-qa.mjs` contains `min-accessibility`) | PASS | `grep -c 'min-accessibility' site/scripts/visual-qa.mjs` → 3 lines |
| `qa-command` → Lint, test and build stay offline and unaffected (`pnpm --dir site test offline`) | PASS | `pnpm --dir site test offline` → `Test Files 1 passed`, `Tests 11 passed`. Three of them are new and are the actual guarantee: the QA toolchain is absent from `site/package.json`, absent from all four offline scripts, and lives in its own package |
| `measured-sweep` → Every page clears the floor with axe clean (`pnpm --dir site qa -- --min-accessibility 95 --min-best-practices 95`) | PASS | exit 0, `visual-qa: 8 pages clear the floor with axe clean at every width.` |
| `measured-sweep` → Report records the per-page scores and the three widths (`1280` in this file) | PASS | [Measured results](#measured-results-the-qa-sweep), pasted unaltered from `site/qa-artifacts/visual-qa-report.md` |
| `human-checks` → Keyboard-only walk and print check pass | NOT RUN | Follow-up 2 |
| `human-checks` → The site looks right on a real phone in Safari and Chrome | NOT RUN | Follow-up 2 |
| `fill-room-and-prod-build` → Prod build succeeds with no placeholder left | PASS | As ac5: exit 0, guard silent, no gap badge in the export |
| `fill-room-and-prod-build` → Full site suite passes offline (`pnpm --dir site test`) | PASS | `Test Files 18 passed (18)`, `Tests 647 passed (647)`, 4.5s |
| `fill-room-and-prod-build` → Type check passes (`pnpm --dir site typecheck`) | PASS | exit 0, 1s |
| `launch-readiness` → Runbook carries the promotion checklist | PASS | `docs/runbooks/team-website.md:836` |
| `launch-readiness` → Charlie signs off the launch commit | NOT RUN | Follow-up 4 |

### Other gates

| Check | Status | Evidence |
|---|---|---|
| Python suites touched by this task | PASS | `uv run pytest tests/scripts tests/smoke -q` → `139 passed` in 15s |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 282 files, 38 epics, 224 tasks, 20 releases` |
| The whole offline site gate | PASS | `site/scripts/pre-commit-checks.sh` → exit 0 in 10s (lint, typecheck, test, build), well inside the CI budget |
| The QA command's static server against the real export | PASS | Verified by hand before the sweep (8 pages at 200 with correct content types, a `_next/static` stylesheet as `text/css`, an unknown path served the 404 page with status 404), and then by the sweep itself, which served all 24 page loads and the Lighthouse runs through it |
| The QA toolchain, as installed | PASS | Chromium via playwright 1.63.0, Lighthouse 13.5.0, axe-core 4.13.0, recorded by the run rather than assumed |

## Measured results: the QA sweep

Run by the operator on 2026-09-20, after the one-time toolchain install, against a local **prod**
build (`SITE_ENV=prod SITE_URL=https://wfbdebate.com pnpm --dir site build`). Pasted unaltered
from `site/qa-artifacts/visual-qa-report.md`, which the command writes; the command exited 0 with
`visual-qa: 8 pages clear the floor with axe clean at every width.`

### Lighthouse scores

Run 2026-09-21 03:16 UTC against a local static export, Chromium (playwright 1.63.0), Lighthouse 13.5.0, form factor mobile. Floor: accessibility 95, best practices 95.

| Page | Performance | Accessibility | Best practices | SEO |
|---|---|---|---|---|
| `/` | 96 | 100 | 100 | 100 |
| `/about/` | 96 | 100 | 100 | 100 |
| `/events/` | 95 | 100 | 100 | 100 |
| `/join/` | 96 | 100 | 100 | 100 |
| `/coaches/` | 96 | 100 | 100 | 100 |
| `/faq/` | 95 | 100 | 100 | 100 |
| `/contact/` | 95 | 100 | 100 | 100 |
| `/accessibility/` | 96 | 100 | 100 | 100 |

### axe-core

axe-core 4.13.0 in Chromium, rule sets wcag2a, wcag2aa, wcag21a, wcag21aa, with the colour-contrast rule enabled. Every page was checked at each of the three widths.

No violations on any page, at any width.

### Widths

| Page | 390 | 768 | 1280 |
|---|---|---|---|
| `/` | no horizontal overflow | no horizontal overflow | no horizontal overflow |
| `/about/` | no horizontal overflow | no horizontal overflow | no horizontal overflow |
| `/events/` | no horizontal overflow | no horizontal overflow | no horizontal overflow |
| `/join/` | no horizontal overflow | no horizontal overflow | no horizontal overflow |
| `/coaches/` | no horizontal overflow | no horizontal overflow | no horizontal overflow |
| `/faq/` | no horizontal overflow | no horizontal overflow | no horizontal overflow |
| `/contact/` | no horizontal overflow | no horizontal overflow | no horizontal overflow |
| `/accessibility/` | no horizontal overflow | no horizontal overflow | no horizontal overflow |

Screenshots for each cell are in the output directory, named `<page>-<width>.png`. They are review artifacts and are never committed.

Two things worth saying about this run beyond the numbers. The pages measured are **every URL in
`sitemap.xml`**, read at run time rather than listed anywhere, so a page cannot be missed by being
forgotten. And performance sits at 95 to 96 rather than 100 on a static export with no third-party
script, which is the mobile form factor's simulated throttling rather than anything the site does;
the floor the spec sets is on accessibility and best practices, both of which are 100 everywhere.

## Files changed

**The announcement guard** (the `v1-e36-t07` review's main ruling)
* `site/src/lib/content.ts` — `parentSessionFactSchema`: a panel fact carries either a `value` or an `unsetNote`, exactly one. `AnnouncementField` and `announcementFields()` give the guard the facts as fields rather than as copy.
* `site/src/lib/publishing-policy.ts` — an unset announcement field is an error, naming the field and the announcement.
* `site/src/app/layout.tsx` — passes `announcementFields()` through the guard at build time.
* `site/src/app/page.tsx` — an unset fact renders in the same gap badge a `[[TBD]]` marker does.
* `site/content/home.yaml` — the Room became an `unsetNote`, which is what made it fail a prod build for the first time since `v1-e36-t06`; Charlie then set it to `To be announced` in `fdd5122`.

**The phrase allowlist**
* `site/src/lib/publishing-policy.ts` — `unreviewedNames` covers a run of capitals with listed phrases end to end instead of checking word by word.
* `site/src/lib/media-consent.ts`, `site/content/media-consent.yaml` — `permittedNameWords` becomes `permittedNamePhrases`; the bare words are replaced by the institutions and places they came from.

**The browser QA command**
* `site/scripts/visual-qa.mjs` — new. Serves `site/out`, walks the sitemap, screenshots at three widths, runs axe and Lighthouse, writes the score table, enforces the floor.
* `site/scripts/visual-qa-tools/{package.json,README.md}` — new. The browser and the scorer, kept out of the site's install graph.
* `site/package.json` — the `qa` script. `site/.gitignore` — `qa-artifacts/` and the tools lockfile.

**The smoke checks for `validate-dev`**
* `scripts/site_smoke.py` — the October 1 panel, the FAQ disclosures, and gap badges (a failure on prod, a reported count on dev).
* `tests/smoke/test_site.py`, `tests/smoke/README.md` — say what the suite now asks.

**Tests**
* `site/tests/visual-qa.test.ts` — new, 19 tests over the QA command's offline parts.
* `site/tests/content-policy.test.ts` — the announcement guard and the phrase allowlist, including the review's own example (a reviewed school must not leave its words permitted alone).
* `site/tests/home.test.tsx` — an unset fact shows in the gap badge, not as ordinary copy.
* `site/tests/offline.test.ts` — the QA toolchain stays out of `site/package.json` and the four offline scripts.
* `tests/scripts/test_site_smoke.py` — the new checks, including a gap badge on prod meaning the build guard was bypassed.

**Docs**
* `docs/runbooks/team-website.md` — the promotion checklist.
* `site/README.md` — the `qa` command, its operator setup, and the two new guard rows.

## Deviations from the spec

1. **The `[[TBD]]` marker the plan node says to replace does not exist.** `fill-room-and-prod-build`
   says to "replace the `[[TBD]]` marker in site/content/pages/home.md (and the panel fields the
   home page reads)". There is no marker in `home.md`; `v1-e36-t06` moved the room into
   `content/home.yaml` and replaced the marker with a sentence, which is exactly the hole the
   review found. The room was filled in by replacing the Room fact's `unsetNote` with a `value` in
   `content/home.yaml`; `home.md` was not touched, and the plan node's own instruction could not
   have been followed as written.

2. **`tests/smoke/` already had its first site entries.** The Goal description says `tests/smoke/`
   "gains its first site entries for the validate-dev tier, which no task has added yet".
   `tests/smoke/test_site.py` has existed since `v1-e36-t05` (commit `acd14fb`). The real gap was
   narrower and this task closed that instead: the suite checked that the site was up, served
   safely and serving the right commit, but nothing about what the pages said. It now also checks
   the October 1 panel, the FAQ disclosures and gap badges.

3. **The home entry-point card labels are left to `v1-e36-t09`.** The Goal description lists them
   among the four things "this task also owns", but the same specs commit (`9f976d6`) created
   `v1-e36-t09` with a plan node for it ("Entry-point card labels matched to their destination
   pages"), its own acceptance criterion, a constraint, and Charlie's approval step, and the epic's
   `t09` entry says so too. Doing it in both tasks guarantees a conflict in `content/home.yaml`,
   which `t09` also edits to add the academic-case section, and the two specs run in parallel. The
   more specific owner wins; **the PM should strike the clause from the `t08` description** so the
   next reader is not left checking which task did it.

4. **No screenshot, score or axe result was recorded before a run produced one.** ac1 to ac3 were
   left NOT RUN, with no score table, until the operator's sweep on 2026-09-20; the numbers now in
   [Measured results](#measured-results-the-qa-sweep) are that run's output pasted unaltered. The
   spec forbids "recording a score not produced by a run", and a template filled with plausible
   numbers is the failure that rule exists to prevent. On the record so the sequence is visible,
   not because anything was done differently from the spec.

## Decisions and assumptions

* **An unset fact is a schema state, not a sentence.** The obvious alternative was to put a
  `[[TBD]]` marker in the Room's `value` and rely on the existing placeholder scan. That would
  have worked for the room and not for the class of problem: a fact that is simply absent from a
  panel leaves nothing for a text rule to find. Making "unset" a field the schema requires is what
  makes the absence itself checkable, and it lets `To be announced` pass as what it is, a decision.
  E37's announcements and calendar entries join `announcementFields()` rather than growing a second
  guard.
* **The phrase allowlist covers a run with several entries, not one.** Requiring each capitalised
  run to match a single listed phrase would have forced "The Whitefish Bay High School Debate Team"
  into the list as a sentence. Tiling lets "The", "Whitefish Bay High School" and "Debate Team"
  cover it between them while still refusing "Blue Rivera". A one-word entry permits nothing on its
  own, because a single capitalised word is never a run.
* **The QA toolchain is a package, not a devDependency.** `pnpm --dir site install --frozen-lockfile`
  currently takes 2.8s and the whole offline gate 10s. Adding Playwright and Lighthouse to
  `site/package.json` would put a browser download into every CI install for a command CI never
  runs. `tests/offline.test.ts` now fails if either turns up there, so this is a rule rather than
  a habit.
* **The tools lockfile is gitignored.** A prod deploy refuses a checkout that is not clean, and an
  operator installing a review tool should not have to commit anything before deploying. The
  versions that produced a given set of numbers are recorded in the report each run writes, which
  is what actually makes a score reproducible.
* **The QA command is tested without a browser.** Path resolution, the sitemap walk, the floor and
  the report are pure functions and are covered offline, so the operator's one expensive run is not
  the first time the script has executed. There is deliberately no test that fetches from the local
  server: `site/tests/setup.ts` fails any call to `fetch` on purpose, and weakening that guard to
  cover twenty lines of `readFile` is a bad trade. The server was exercised by hand against the
  real export instead, with the result recorded under Other gates.
* **A Lighthouse category that could not be computed fails the floor.** Treating "not measured" as
  a pass is how a run that half worked gets recorded as a green launch gate.
* **The room reads "To be announced", and that is a decision rather than a gap.** Charlie set it in
  `fdd5122`, whose message calls it a stand-in. The guard accepts it for exactly the reason the
  review gave: a room of "To be announced" is an answer, an empty one is an oversight. **What it
  settles** is the build gate, ac5 and the promotion: nothing on the site is now unfinished in a
  way a machine can see. **What it does not settle** is whether that is the wording parents should
  read on October 1. If a real room arrives, follow-up 3 has the one-line change, and the sweep is
  repeated because the home page will have changed.
* **The tripwire test was turned around rather than deleted.** `content-policy.test.ts` carried
  "still owes the October 1 room, which is what stops a prod build today", written to fail the day
  the room was supplied. It fired, and `fdd5122` rewrote it as "leaves no October 1 announcement
  fact unset", which guards the other direction: no announcement fact goes back to being silently
  unset before October 1. That is the better test to be left holding, and its docstring records
  the history.
* **Playwright's named export did not survive the CommonJS boundary, and the operator fixed it.**
  `loadQaToolchain` destructured `{ chromium }` from the dynamic import; playwright's entry point
  is CommonJS and `cjs-module-lexer` does not find `chromium` among its re-exports, so the named
  import was undefined. `fdd5122` takes `module.chromium ?? module.default?.chromium` and raises a
  `VisualQaError` naming the version if neither works, instead of a `TypeError` deep in `main()`.
  This was a real bug in the committed script and is the one thing the offline tests could not have
  caught, since they never load the toolchain.

## Operator follow-ups

Two of the four are done. They are kept here, marked, because the commands are what the next
person repeats rather than reconstructs.

### 1. Install the QA toolchain, then run the sweep — DONE 2026-09-20

```bash
pnpm --dir site/scripts/visual-qa-tools install
pnpm --dir site/scripts/visual-qa-tools exec playwright install chromium
pnpm --dir site build          # SITE_ENV=prod SITE_URL=https://wfbdebate.com for the recorded run
pnpm --dir site qa -- --min-accessibility 95 --min-best-practices 95
```
Result: exit 0, `visual-qa: 8 pages clear the floor with axe clean at every width.` Output in
[Measured results](#measured-results-the-qa-sweep). Nothing from `site/qa-artifacts/` was
committed; it is gitignored and `git status` is clean.

**Repeat this run after any change to the site's copy, layout or tokens**, and in particular once
the October 1 room is replaced with a real one. A non-zero exit lists what failed, page by page.
Anything below the floor, any axe violation or any page that scrolls sideways is a fix in `site/`,
not a number to write down: the floor is not to be lowered and no page is to be skipped (spec
constraints).

### 2. The keyboard walk, the print check and the two phones

A human at a keyboard, on the dev preview at `https://dev.wfbdebate.com/`. Fill this in as you go
and paste it into this report under ac4.

| Page | Skip link | Nav menu (Enter/Space opens, Escape closes, focus returns) | Every `<summary>` | Every button and link | Focus ring visible throughout | No focus trap |
|---|---|---|---|---|---|---|
| `/` | | | n/a | | | |
| `/about/` | | | | | | |
| `/events/` | | | | | | |
| `/join/` | | | | | | |
| `/coaches/` | | | | | | |
| `/faq/` | | | | | | |
| `/contact/` | | | | | | |
| `/accessibility/` | | | | | | |

Then, with the mouse untouched: **print `/faq/` to PDF from the browser** and confirm every answer
appears, including the ones whose disclosure was closed on screen. Record the number of questions
in the PDF against the number on the page.

Then open `https://dev.wfbdebate.com/` on **an iPhone in Safari** and **an Android phone in
Chrome**, and confirm the home hero, the October 1 panel, the events cards and the FAQ disclosures
read correctly with nothing cut off or overlapping. Note the phone and browser versions.

### 3. The October 1 room, then the prod build — DONE 2026-09-20

Charlie set the Room to `To be announced` in `fdd5122`, which the guard accepts as a decision
rather than a gap, and `SITE_ENV=prod SITE_URL=https://wfbdebate.com pnpm --dir site build` now
exits 0 with no publishing-policy output. See Decisions for what that does and does not settle.

**If a real room number arrives before October 1**, it is one line in `site/content/home.yaml`:

```yaml
    - label: Room
      value: <the room>
```

followed by a prod build and a repeat of follow-up 1's sweep, because the home page will have
changed.

### 4. Charlie's sign-off

Charlie reviews this report and the QA output, agrees the site is ready to show parents, and ticks
every item of the pre-publication checklist in
[`docs/policies/website-publishing.md`](../policies/website-publishing.md) against the commit that
will be promoted, on or before **September 30, 2026**. Items 17 and 18 apply too: this is the
season's first deploy. Record the commit sha and the date here.

Then the launch itself follows the
[Promotion checklist](../runbooks/team-website.md#promotion-checklist), which is operator-run
throughout.

## Follow-up work

* **Strike the entry-point card labels from the `t08` Goal description** so it is not owned by two
  tasks. `v1-e36-t09` has the plan node, the acceptance criterion and Charlie's approval step.
  (Deviation 3.)
* **The guard does not read alt text.** `visibleText()` strips tags before the name rules run, so a
  student's name in an `alt` attribute would not be flagged. No image of a person is published yet,
  so nothing is wrong today, but the hole should close before the first photograph. Belongs with
  the published-names allowlist in `v1-e37-t03`.
* **The phrase allowlist has no test that it stays minimal.** Nothing stops a future entry being a
  bare word again. A check that every entry is either multi-word or on a short reviewed list of
  ordinary words would keep the review's ruling from eroding. `v1-e37-t03`.
* **`site/scripts/visual-qa-tools` pins no versions.** It asks for `latest` and the report records
  what ran, which is the right trade for a review tool but would not be for anything that gates a
  deploy. The first install resolved playwright 1.63.0 and Lighthouse 13.5.0, and those are the
  versions behind the numbers in this report. If the QA run ever becomes a required check, pin it
  and commit the lockfile.
* **The QA command has nothing automatic that exercises it end to end.** The playwright import bug
  fixed in `fdd5122` reached a commit because the offline tests deliberately never load the
  toolchain, and a browser download has no place in the PR path. Nothing cheap fixes that, but it
  is worth knowing that the first real run of this command is always its first real test.
* **Repeat the QA sweep if the room wording changes.** The recorded run measured `To be announced`
  on the home page. A real room number is a different home page, and the numbers should be the
  ones the launch commit actually produces.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

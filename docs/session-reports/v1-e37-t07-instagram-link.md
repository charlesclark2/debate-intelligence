# Session report: v1-e37-t07-instagram-link

| | |
|---|---|
| Task | `v1-e37-t07-instagram-link` — A link to the team's Instagram account, never an embed |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t07-instagram-link.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t07-instagram-link.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t07-instagram-link` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The team's Instagram account is now a plain text link in the footer of every page and in a
"Follow the team" section on the contact page. Its visible text, `@wfbdebate on Instagram (opens
Instagram's site)`, is also its accessible name. The address and every word of it live in
`site/content/site.yaml`, and a schema accepts only an `https://www.instagram.com/<handle>/`
account address. It is an ordinary `<a>` with `rel="noopener noreferrer"`. It has no icon and
loads nothing from Instagram or Meta, so the accessibility page's line that the site loads no
social media widgets stays true and was not touched. A new block in the export's third-party
suite refuses any Instagram or Meta host anywhere in `site/out/` (pages, bundles, stylesheets,
React payloads) except that one address on an `<a href>`. Twelve mutants showed each new check
failing for its own reason. The PM may want to look first at the one rule that is not in the
spec: the link sits outside the footer's utility `<nav>`. The spec does not say where in the
footer it goes, and that `<nav>` is pinned to this site's own pages.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `instagram-link` (Instagram link) | Done | Settings block and schema, `InstagramLink` component, footer and contact page, source tests, export tests |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the footer of every page and the contact page carry a link to the Instagram account, its address from `site/content/site.yaml`, labelled as opening Instagram's site | PASS | `pnpm --dir site exec vitest run tests/instagram-link.test.tsx` → 9 passed: one link in the footer, named `/opens Instagram's site/`, with text `label (externalLinkNote)` from the settings; one in the contact page's `<main>` under the `contactHeading` heading, and none in another Markdown page's body; no source file under `src/` holds the account address. In the export (`site/scripts/export-checks.sh`): each of the 13 exported HTML documents has exactly one such link in its `<footer>`, with that text and `noopener noreferrer`, and `contact/index.html` has one in `<main>`. |
| ac2: no page loads anything from Instagram or Meta; a test over the built export finds no script, iframe, image or stylesheet from instagram.com, cdninstagram.com, facebook.com or fbcdn.net; the existing third-party and cookie checks pass | PASS | `site/scripts/export-checks.sh` → 12 files, 109 passed. The new block "the built site and Instagram, site/out" checks: every fetching element (the suite's existing `FETCHING_ATTRIBUTES` list: script, link, img/srcset, source, iframe, frame, embed, object, video, audio, track, form, SVG image/use) against instagram.com, cdninstagram.com, instagr.am, facebook.com, facebook.net, fbcdn.net and fbsbx.com; the address only on `<a href>`; no mention of those hosts in any `.html`, `.js`, `.css` or `.txt` file once the account address is taken out. Existing third-party checks (`content-policy.export-test.ts` "loads nothing from another origin and embeds no iframe", `no-third-party-scripts.export-test.ts`) and the cookie and storage check (`contact.export-test.ts` "sets no cookie and uses no browser storage anywhere in the export") pass unchanged. |
| ac3: `pnpm --dir site lint`, `typecheck`, `test` and `build` pass offline | PASS | `site/scripts/pre-commit-checks.sh` (lint, typecheck, test, then build and export checks) → exit 0 in 23 s: lint and typecheck with no findings, `test` 26 files / 914 passed, build exported 80 files, export checks 109 passed. Offline in the repository's sense: `tests/offline.test.ts` fails any fetch, the package scripts set `NEXT_TELEMETRY_DISABLED=1`, the build reads only files under `site/`, and the dependencies were installed with `pnpm --dir site install --frozen-lockfile --offline` (from the local store, 3.5 s). The network was not physically cut off during the run. |
| Node `instagram-link`: "The site tests pass" (`pnpm --dir site test`) | PASS | Within the pre-commit run above: 26 files, 914 passed. |

### The checks failing for their reason

Each mutant was applied to the committed tree, the source test file and (where marked) the build
plus export checks were run, and the tree was restored from the commit. The driver script is not
committed.

| Mutant | Caught by |
|---|---|
| Footer link rendered as nothing (`instagram ? null : …`), export | source: "carries one link…", "makes it an ordinary anchor…"; export: "links the account from the footer of every page…" |
| Footer link removed outright, export | source: the same two. The export attempt failed at the build's type check (unused import), which is not a catch for the export test, so it was redone as the mutant above. |
| An `<img>` from cdninstagram.com in the footer, export | export: "fetches nothing from Instagram or Meta…", "names Instagram or Meta nowhere else…", plus the existing off-origin checks in both export suites |
| An Instagram `embed.js` `<script>` on the contact page, export | export: the same two new tests, plus the existing script and off-origin checks |
| The address on a `data-embed` attribute in the footer, export | export: "carries the address only on <a href>…" |
| The "(opens Instagram's site)" note dropped from the text, export | source: "carries one link to the account, labelled as opening Instagram's site"; export: the footer test |
| The contact section switched off, export | source: "carries the link in its body, under its own heading"; export: "links it from the body of the contact page too" |
| The address written into `InstagramLink.tsx` | "are the only place the address is written…" |
| The schema accepting any `https://` address | "accept only an account address, and a note that names Instagram" |
| An inline SVG icon inside the link | "makes it an ordinary anchor…" |
| `rel` removed | "makes it an ordinary anchor…" |
| The section rendered on every Markdown page | "is the only Markdown page that carries it outside the footer" |
| The link added to the utility `<nav>` | "keeps it out of the utility navigation…" and "carries one link…" (two links) |

### Repository checks before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` (list), then `.venv/bin/python -m pytest -m "not slow and not live"` over it under `perl -e 'alarm 115'` | 105 files chosen ("site/ changed: the site's own pnpm checks test it; pytest does not"). First attempt, at load average 11: cut by the alarm at 98% with no failure. Second attempt: 4887 passed, 2 xfailed in 111.79 s. |
| Always-run list: `tests/architecture/ tests/specs/ packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py` | 316 passed in 21.99 s |
| `uv run --frozen ruff format --check .` / `ruff check .` | 1236 files already formatted / All checks passed |
| `pyright` | Not run: no Python changed |
| `uv run --frozen lint-imports` / `scripts/check_thin_handlers.py` | 16 kept, 0 broken / 50 handlers within 25 statements |
| `uv run scripts/validate_specs.py` | OK: 435 files, 40 epics, 373 tasks, 22 releases |
| `scripts/docs_index.py --check-descriptions` / `scripts/check_command_blocks.py` | All 46 indexed documents have a description / OK: no `#` comments in 389 shell code blocks in 148 Markdown files (1 session report changed since origin/dev) |

## Files changed

* `site/content/site.yaml`: the `instagram` block (address, label, external-link note, contact
  heading), with a comment pointing at the policy item it follows.
* `site/src/lib/content.ts`: `instagramLinkSchema`, required in `siteSettingsSchema`.
* `site/src/components/InstagramLink.tsx` (new): the one anchor.
* `site/src/components/SiteFooter.tsx`, `SiteFrame.tsx`, `site/src/styles/layout.css`: the link
  under the footer note, outside the utility `<nav>`, styled like the footer links (44 px target).
* `site/src/app/[slug]/page.tsx`: the "Follow the team" section on the contact page.
* `site/tests/instagram-link.test.tsx` (new): settings, footer and contact page tests.
* `site/tests/export/no-third-party-scripts.export-test.ts`: the Instagram and Meta block; the
  signup-address remover generalised to `withoutAddress` so both blocks share it (the signup
  address is removed exactly as before).
* `site/tests/layout.test.tsx`, `site/tests/design-system.test.tsx`, and the four
  `site/tests/fixtures/*/site.yaml`: supply the new required settings field with a fictional
  `fixture.team` account. No assertion or pinned number in them changed.

## Deviations from the spec

None in the code. One working agreement this task did not meet: agreement 5 asks a task that
changes a user-facing surface to add or update its smoke checks. The site's live check is
`scripts/site_smoke.py`, which is outside this task's `constraints.packages`, so it was not
touched. It does not inspect outbound links, and the deployed CSP does not block a top-level
navigation, so nothing there will fail because of this change. See Follow-up work.

## Decisions and assumptions

* **No icon.** The PM allowed none or a local inline SVG. Text alone has nothing to fetch, and
  nothing for a screen reader to read twice. A test pins that the anchor has no child elements,
  so adding an icon later means changing that test on purpose.
* **Same tab, with `rel="noopener noreferrer"` anyway.** The email-updates link does the same, for
  the same reason: most visitors are on phones. `noreferrer` also keeps the page a visitor came
  from out of the request to Instagram.
* **Outside the footer's utility `<nav>`.** That list is this site's published pages, and
  `tests/navigation.test.tsx` pins it to exactly `buildNavigation().utility`. Putting the
  Instagram link in it would have meant changing that test's meaning. It is a paragraph of its
  own under the footer note.
* **The address is the full URL, not a bare handle.** The spec asks for "its address" in
  `site.yaml`, and the PM gave both handle and URL. The label `@wfbdebate on Instagram` repeats
  the handle as copy, in the same file. No code holds either, and a test checks that.
* **The schema is strict.** It requires `https://www.instagram.com/<1–30 of A-Z a-z 0-9 . _>/`, so
  a post, a `/embed/` path, `http:`, a bare `instagram.com` or a look-alike host fails the build.
  The note has to name Instagram.
* **The host list goes past the spec's four.** It adds `instagr.am`, `facebook.net` (the SDK's
  `connect.facebook.net`) and `fbsbx.com` alongside instagram.com, cdninstagram.com, facebook.com
  and fbcdn.net.
* **The PM's warning about pinned counts.** No export test counted links or anchors in a way this
  change moves. The new tests compute what they expect from the settings and the export (for
  example, one link per exported document), and no existing number was edited.
* **Dependencies** were installed into the worktree from the local pnpm store with `--offline`,
  because `site/node_modules` was missing.

## Operator follow-ups

None. The branch goes through `dev` and the normal promotion, not a hotfix.

## Follow-up work

* `scripts/site_smoke.py` could confirm on the deployed site that the footer carries the
  Instagram link and that no page names an Instagram or Meta host other than as that link. This
  would be a small change to the smoke script and `tests/scripts/test_site_smoke.py`, outside
  this task's packages (epic E36, the site deploy and smoke task, or a new E37 task). Agreement 5
  asks for it.
* If Charlie later wants posts shown on the site, that is a change to the publishing policy for
  him to approve first, as the spec says. The schema and the export check would both refuse it
  until then.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

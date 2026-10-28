<!--
Website change: site/<slug> into main, the site lane (v1-e37-t09). For the public website's
content, pages and assets only. The promotion-source check refuses this pull request if the branch
changes anything outside site/, changes a dependency manifest or lockfile (site/package.json,
site/pnpm-lock.yaml and the like: those go through a promotion of dev), or changes nothing.
How to run the whole lane: docs/guides/coach-website-editing.md, "Publish a change".
https://github.com/charlesclark2/debate-intelligence/blob/dev/docs/guides/coach-website-editing.md

The promotion-source check fails while the "Dev build:" line below is blank, and runs again
whenever this description is edited. Guidance sits in comments like this one, so a line holding
only its comment still counts as blank.

There is no line for the validate-dev run. protect-main requires the `validate-dev` commit status
on the head commit. For a site branch it comes from dispatching validate-dev.yml from dev with
site_only=true, which runs the site's prod build and export checks against this commit.
-->

## Change

<!-- What changes on the website, in a sentence a parent would understand: "Results from the Ronald
Reagan tournament", "The November schedule". -->

## Validation in dev

Dev build: <!-- the commit the dev preview's version.json names after scripts/site_deploy.sh dev from this branch -->

The `validate-dev` status on the head commit is the validation: for a site branch it says
`site only` and links the run that built this commit for prod. GitHub blocks the merge until it is
green for the current head.

## Pre-publication checklist

From [`docs/policies/website-publishing.md`](https://github.com/charlesclark2/debate-intelligence/blob/dev/docs/policies/website-publishing.md#pre-publication-checklist).
A "no" on any item stops the publication until it is fixed.

- [ ] 1. Names and consent: every student named has a current-season consent form and is in the allowlist; no opponent student is named
- [ ] 2. No age, date of birth, grade level or birthday
- [ ] 3. No student contact details anywhere, including alt text and file names
- [ ] 4. Every image of a person has a current-season consent entry; EXIF stripped
- [ ] 5. Nothing about discipline, grades, health, family or team selection for a named student
- [ ] 6. Results: published form, both partners in a partner event, placing or advancement only
- [ ] 7. No named student paired with a room, ride, hotel, arrival time or solo travel plan
- [ ] 8. No script, iframe, embed, tracker, remote font, stylesheet or image; no cookie
- [ ] 9. Every outbound link labelled as leaving the site
- [ ] 10. No form, input or payment field
- [ ] 11. Accessibility: axe clean, alt text, headings in order, works by keyboard at phone width
- [ ] 12. Plain language: no em dashes in body copy, acronyms spelled out
- [ ] 13. Branding as the district allows; footer says team-run
- [ ] 14. Deployed to the intended environment; the dev preview still carries `noindex`
- [ ] 15. Everything published about a person can come down by editing content and redeploying
- [ ] 16. **Charlie has seen the exact content that will publish**, for anything that names or depicts a student

## Checklist

- [ ] `ci`, `promotion-source`, `back-merge` and `validate-dev` are green
- [ ] The dev build above is the commit the dev preview's `version.json` names, and the preview was read on a phone
- [ ] **Only when this changes `site/src`, `site/public` or a configuration file the build reads** (`site/next.config.ts`, `site/tsconfig.json`, `site/scripts/`): `pnpm --dir site qa -- --min-accessibility 95 --min-best-practices 95` exits 0 against a build of this commit. A change to `site/content/` alone does not need it
- [ ] Merge with **Create a merge commit**, never squash or rebase
- [ ] After the merge: prod deployed from the `prod-deploy` worktree with `scripts/site_deploy.sh prod`, and `scripts/site_smoke.py --env prod --expect-sha` passes
- [ ] The back-merge pull request is merged into `dev` with a merge commit the same day. Until it merges, the next site change and every promotion are blocked by `back-merge`

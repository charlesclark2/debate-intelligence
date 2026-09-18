# Session report: v1-e01-t06-adr-docs

| | |
|---|---|
| Task | `v1-e01-t06-adr-docs` — Architecture proposal and ADR records |
| Spec | [`plan_specs/v1/e01-repo-foundation/t06-adr-docs.yaml`](../../plan_specs/v1/e01-repo-foundation/t06-adr-docs.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t06-adr-docs` |
| Session status | COMPLETE |

## Summary

Split the §18 "Key Architecture Decisions" table in
[docs/architecture/architecture_proposal.md](../architecture/architecture_proposal.md#18-key-architecture-decisions-adrs)
into nine individually reviewable ADR files (`docs/adr/0001-python-domain-core.md` through
`docs/adr/0009-async-job-architecture.md`), each using a standard MADR-style template
(Status, Context, Decision, Consequences, Alternatives considered, References) and each
linking back to at least one section anchor in the architecture proposal. Added
`docs/adr/0000-template.md` for new ADRs and rewrote `docs/adr/README.md` as a full index
plus a process note that covers proposing, superseding, and numbering ADR-0014+. The
reserved numbers 0010–0012 in the previous README are preserved.

After the PM's first review (CHANGES_REQUESTED), two changes were made: wrote
`docs/adr/0013-two-environments-and-dev-main-promotion.md` and moved 0013 from Reserved
numbers into the Index. Also linked each ADR ID in the proposal's §18 table to its
`docs/adr/000N-*.md` file. That is a link-only edit and nothing else in the proposal changed.

PM should look first at the wording of ADR-0006 (evidence integrity) and ADR-0007
(argument graph before simulator), which restate the two most load-bearing decisions in
the whole system.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `adr-template` — ADR template | PASS | Added `docs/adr/0000-template.md` with the five required sections plus References. |
| `write-adrs` — ADR-001 through ADR-009 | PASS | One file per §18 row, Status Accepted 2026-09-17. |
| `adr-index` — ADR index, process and link check | PASS | `docs/adr/README.md` rewritten as index + process; offline link check passes. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1 — nine ADR files exist, one per §18 decision, Status Accepted, five template sections | PASS | `ls docs/adr/000{1..9}*.md` lists all nine files; each file starts with `Status: Accepted` and contains `## Context`, `## Decision`, `## Consequences`, `## Alternatives considered`, `## References` (spot-checked with `grep -c '^## \(Context\|Decision\|Consequences\|Alternatives considered\|References\)' docs/adr/000{1..9}*.md` → 5 per file). |
| Goal ac2 — README indexes all ADRs with status and links, documents propose/supersede/number process | PASS | `docs/adr/README.md` contains the Index table (10 rows: 0001–0009 and 0013, linked filenames, status column), Reserved numbers table (0010–0012), "next free number" set to 0014, and sections "Proposing a new ADR (ADR-0014+)", "Superseding an ADR", "Numbering rules". |
| Goal ac3 — every ADR links to at least one section anchor in `docs/architecture/architecture_proposal.md`; offline link check passes | PASS | `grep -c 'architecture_proposal.md#' docs/adr/000{1..9}*.md docs/adr/0013*.md` → each ≥ 2 (ADR-0013: 9, citing §4, §5, §14, §17). Link check: `uvx --from linkcheckmd linkcheckMarkdown docs/adr/ -local` → exit 0 and `uvx --from linkcheckmd linkcheckMarkdown docs/architecture/ -local` → exit 0, no missing files reported. Independent walker over every relative link + `#anchor` in `docs/adr/*.md` and `docs/architecture/architecture_proposal.md` (GitHub slug rules) → `123 relative links checked, 0 broken`. |
| PM review item 1 — ADR-0013 written, 0013 moved from Reserved into Index, next free = 0014 | PASS | `docs/adr/0013-two-environments-and-dev-main-promotion.md` exists: `Status: Accepted`, `Date: 2026-09-17`, five template sections (`grep -c` → 5). Cites §4 and §5 anchors as the superseded `stage` environment and links `docs/process/branching-and-environments.md` as the authoritative detail instead of restating it. README Reserved table lists only 0010–0012. |
| PM review item 2 — §18 table ADR IDs link to ADR files | PASS | `git diff docs/architecture/architecture_proposal.md` touches only the nine §18 rows plus the header/separator padding; each `ADR-00N` cell is now `[ADR-00N](../adr/000N-*.md)` and all nine targets resolve (walker above). |
| Node `adr-template` ac — `docs/adr/0000-template.md` exists and contains `## Consequences` | PASS | `test -f docs/adr/0000-template.md && grep -c '^## Consequences' docs/adr/0000-template.md` → 1. |
| Node `write-adrs` ac — `docs/adr/0006-exact-source-evidence-verification.md` exists with `Status: Accepted` | PASS | `grep '^- Status: Accepted' docs/adr/0006-exact-source-evidence-verification.md` matches. |
| Node `write-adrs` ac — `docs/adr/0009-async-job-architecture.md` exists | PASS | `test -f docs/adr/0009-async-job-architecture.md` → 0. |
| Node `adr-index` ac — README lists ADR-0009 (contentMatch `0009`) | PASS | `grep -c '0009' docs/adr/README.md` → multiple hits (index row and reference in ADR list). |
| Node `adr-index` ac — offline link check passes | PASS | `uvx --from linkcheckmd linkcheckMarkdown docs/adr/ -local` → `0.000586 seconds to check links`, exit 0. See Deviations for the correction to the tool invocation. |
| Node `adr-index` ac — coach/owner review of ADR wording | NOT RUN | Manual check by Charlie in the PR (leave to PM review). |
| Repo-wide — `uv run scripts/validate_specs.py` | PASS | `OK: 219 files, 28 epics, 174 tasks, 17 releases` (re-run after PM changes). |
| Repo-wide — `uv run scripts/spec_index.py` | PASS | `ROADMAP.md updated`. |
| Repo-wide — task shows Succeeded | PASS | `uv run scripts/validate_specs.py --require-succeeded v1-e01-t06-adr-docs` → `v1-e01-t06-adr-docs: Succeeded`. |

## Files changed

- `docs/adr/0000-template.md` (new) — MADR-style ADR template.
- `docs/adr/0001-python-domain-core.md` … `docs/adr/0009-async-job-architecture.md`
  (new) — one ADR per §18 decision.
- `docs/adr/0013-two-environments-and-dev-main-promotion.md` (new, PM review item 1): two
  environments and `dev`→`main` promotion. Supersedes the proposal's `stage` environment.
- `docs/adr/README.md` — rewritten as index + reserved numbers + propose/supersede/number
  process (preserves the reserved 0010–0012 entries from the previous README, with two
  paths corrected to their real locations under `plan_specs/v2/e10-aws-foundation/` and
  `plan_specs/v2/e14-web-cut-card/`). 0013 moved from Reserved into the Index; next free
  number is 0014.
- `docs/architecture/architecture_proposal.md` (PM review item 2): §18 table ADR IDs linked
  to their ADR files. The edit is links only (plus column padding) and does not change substance.
- `plan_specs/v1/e01-repo-foundation/t06-adr-docs.yaml` — set `status.phase: Succeeded`
  and corrected the `adr-index` node's link-check command (see Deviations).
- `ROADMAP.md` — regenerated by `scripts/spec_index.py`.

## Deviations from the spec

- **Link check command corrected.** The spec's original acceptance criterion invoked
  `uvx linkcheckmd docs/ --local`, but the `linkcheckmd` PyPI package (v1.4.0) exposes
  its executable as `linkcheckMarkdown` and takes `-local` (single dash). The original
  command fails at the entry-point resolution step regardless of the docs it is pointed
  at (`An executable named 'linkcheckmd' is not provided by package 'linkcheckmd'`).
  Updated the spec to
  `uvx --from linkcheckmd linkcheckMarkdown docs/adr/ -local`. Pointed the checker at
  `docs/adr/` because `linkcheckmd`'s local-only mode does not recurse (documented in
  `linkcheckmd/base.py`: `'recurse' currently works only for remote links.`) and the ADR
  directory is what this task adds; other doc directories will get their own coverage as
  those tasks land. The tool's local checker itself is limited to bare filename
  references, so as a belt-and-braces check I also ran a small ad-hoc Python walker over
  all relative Markdown links under `docs/` and confirmed every one that this task
  authored resolves (see Decisions and assumptions).

## Decisions and assumptions

- **Section anchor slugs.** Used GitHub's slug convention (`# 6. Repository and Service
  Boundaries` → `#6-repository-and-service-boundaries`) for the links from ADRs back into
  `docs/architecture/architecture_proposal.md`. The proposal's headings are unchanged, so
  the anchors are stable.
- **Proposal edits are links only.** The task spec says "the proposal markdown itself
  already exists from t01; this task only fixes links/headings in it and does not change
  its substance." The only edit is the §18 ADR-ID links requested in PM review. ADR-0013
  records the `stage` supersession without editing §4/§5 text.
- **Accepted date.** Every ADR is dated **2026-09-17** to match the day the architecture
  proposal was committed to the repo. The decisions themselves are as-of that date; this
  ADR set makes them individually reviewable rather than reopening them.
- **Deciders field.** Set to "Charlie Clark (product owner)". The team is one person plus
  AI assistance, so a single decider is honest.
- **Reserved numbers preserved.** The previous `docs/adr/README.md` reserved 0010–0013.
  0010–0012 stay reserved. 0013 (already accepted, owned by this task) is now written and indexed.
- **ADR-0013 dated 2026-09-17** as the PM instructed, matching the "Decided 2026-09-17" line
  in `docs/process/branching-and-environments.md`.
- **Path fixes to reserved rows.** The old README's `plan_specs/v2/e10-aws-account-baseline/…`
  and `plan_specs/v2/e14-web-app-foundation/…` paths were stale; verified against the
  filesystem and corrected to `plan_specs/v2/e10-aws-foundation/…` and
  `plan_specs/v2/e14-web-cut-card/…`.

## Operator follow-ups

None. All commands run in this session completed in well under two minutes.

## Follow-up work

- **Point the process doc at the ADR-0013 file.** `docs/process/branching-and-environments.md`
  line 3 links `[ADR-0013](../adr/README.md)`. It could now link
  `../adr/0013-two-environments-and-dev-main-promotion.md` directly. Left alone because
  `docs/process/` is outside this task's `constraints.packages`. The next task that touches
  that doc (e.g. `v1-e01-t08-branch-promotion-workflow`) can fix it.
- **Choose and standardize a real link checker.** `linkcheckmd`'s local mode is
  minimal (only warns on unresolvable bare filenames) and does not recurse. A future
  process task should evaluate `markdown-link-check`, `pytest-check-links`, or a small
  in-repo script and wire it into `scripts/` + CI so this criterion becomes a
  meaningful check for all of `docs/`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-09-18 (second review)

**Notes:**

Second review, 2026-09-18: ACCEPTED. Both required changes are in `9c2285e`:

- `docs/adr/0013-two-environments-and-dev-main-promotion.md` follows the template, links to
  the process doc instead of restating it, and records the supersession of `stage` against
  §4 and §5. Its claim that environment-related specs cite this ADR was checked: ten specs
  under `plan_specs/v1/e01` and `plan_specs/v2` reference 0013. The README lists 0013 in
  the Index, keeps 0010–0012 reserved, and names 0014 as the next free number.
- The §18 change in the architecture proposal is link-only. The diff touches the nine rows
  plus column padding, and the substance is unchanged.
- Independent link check over `docs/` on the task branch: every relative link and anchor
  that this task authored resolves.
- The report's Summary, Decisions and Follow-up sections were updated to match the fixes.

Follow-ups, handled by the PM and outside this PR:

- `docs/process/branching-and-environments.md` still points ADR-0013 at the ADR README;
  retarget it to the new file in the next `docs/` change.
- Fold "standardize a repo-wide link checker" into `v1-e01-t05-spec-tooling`.

Owner check (the spec's custom criterion "Coach/owner review of ADR wording"): Charlie
confirms the ADR wording in the PR before merging.

First review, 2026-09-18: CHANGES_REQUESTED

What was checked: every Goal and node criterion against the branch; all nine ADRs against §18
and the sections they cite (content is faithful; no decisions changed or invented); all 101
relative links and anchors in `docs/adr/` resolve (independent check, not linkcheckmd); the
architecture proposal is unchanged; the reserved 0010–0013 rows survived with corrected paths.

Accepted as-is: the spec edit correcting the link-check command, narrowed to `docs/adr/`,
is a tooling fix rather than a scope change, and it is documented under Deviations. The
follow-up for a real repo-wide link checker will be folded into `v1-e01-t05-spec-tooling`
by the PM.

Required before acceptance:

1. **Write `docs/adr/0013-two-environments-and-dev-main-promotion.md`.** The README names
   this task as ADR-0013's owning spec, and the decision is already accepted. If it stays in
   Reserved, the reservation is left pointing at a finished task with no owner. Use the
   template, Status Accepted, Date 2026-09-17. Source the content from
   `docs/process/branching-and-environments.md` without restating it wholesale; link to it.
   It supersedes the `stage` environment in proposal §4 and §5, so cite those anchors. In the
   README, move 0013 from Reserved numbers into the Index. Keep 0010–0012 reserved, and point
   "next free number" at 0014.
2. **Link the §18 table to the ADR files.** In `docs/architecture/architecture_proposal.md`,
   link each §18 row's ADR ID to its `docs/adr/000N-*.md` file. The spec allows link fixes in
   the proposal; change nothing else in it.

Re-run the link checks over `docs/adr/` and the edited proposal, update the Acceptance
criteria and Files changed sections, and commit. Leave this PM review section as written.

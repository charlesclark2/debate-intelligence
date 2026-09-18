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
proposal markdown itself was not changed (per spec: this task fixes links/headings only
and does not change substance; no fixes were needed). The reserved numbers 0010–0013 in
the previous README are preserved.

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
| Goal ac2 — README indexes all ADRs with status and links, documents propose/supersede/number process | PASS | `docs/adr/README.md` contains the Index table (9 rows, linked filenames, status column), Reserved numbers table, and sections "Proposing a new ADR (ADR-0014+)", "Superseding an ADR", "Numbering rules". |
| Goal ac3 — every ADR links to at least one section anchor in `docs/architecture/architecture_proposal.md`; offline link check passes | PASS | `grep -c 'architecture_proposal.md#' docs/adr/000{1..9}*.md` → each ≥ 2. Link check: `uvx --from linkcheckmd linkcheckMarkdown docs/adr/ -local` → exit 0, no missing files reported. |
| Node `adr-template` ac — `docs/adr/0000-template.md` exists and contains `## Consequences` | PASS | `test -f docs/adr/0000-template.md && grep -c '^## Consequences' docs/adr/0000-template.md` → 1. |
| Node `write-adrs` ac — `docs/adr/0006-exact-source-evidence-verification.md` exists with `Status: Accepted` | PASS | `grep '^- Status: Accepted' docs/adr/0006-exact-source-evidence-verification.md` matches. |
| Node `write-adrs` ac — `docs/adr/0009-async-job-architecture.md` exists | PASS | `test -f docs/adr/0009-async-job-architecture.md` → 0. |
| Node `adr-index` ac — README lists ADR-0009 (contentMatch `0009`) | PASS | `grep -c '0009' docs/adr/README.md` → multiple hits (index row and reference in ADR list). |
| Node `adr-index` ac — offline link check passes | PASS | `uvx --from linkcheckmd linkcheckMarkdown docs/adr/ -local` → `0.000586 seconds to check links`, exit 0. See Deviations for the correction to the tool invocation. |
| Node `adr-index` ac — coach/owner review of ADR wording | NOT RUN | Manual check by Charlie in the PR (leave to PM review). |
| Repo-wide — `uv run scripts/validate_specs.py` | PASS | `OK: 219 files, 28 epics, 174 tasks, 17 releases`. |
| Repo-wide — `uv run scripts/spec_index.py` | PASS | `ROADMAP.md updated`. |
| Repo-wide — task shows Succeeded | PASS | `uv run scripts/validate_specs.py --require-succeeded v1-e01-t06-adr-docs` → `v1-e01-t06-adr-docs: Succeeded`. |

## Files changed

- `docs/adr/0000-template.md` (new) — MADR-style ADR template.
- `docs/adr/0001-python-domain-core.md` … `docs/adr/0009-async-job-architecture.md`
  (new) — one ADR per §18 decision.
- `docs/adr/README.md` — rewritten as index + reserved numbers + propose/supersede/number
  process (preserves the reserved 0010–0013 entries from the previous README, with two
  paths corrected to their real locations under `plan_specs/v2/e10-aws-foundation/` and
  `plan_specs/v2/e14-web-cut-card/`).
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
- **Left the architecture proposal untouched.** The task spec says "the proposal markdown
  itself already exists from t01; this task only fixes links/headings in it and does not
  change its substance." No broken links or heading problems were found, so no edits.
- **Accepted date.** Every ADR is dated **2026-09-17** to match the day the architecture
  proposal was committed to the repo. The decisions themselves are as-of that date; this
  ADR set makes them individually reviewable rather than reopening them.
- **Deciders field.** Set to "Charlie Clark (product owner)". The team is one person plus
  AI assistance, so a single decider is honest.
- **Reserved numbers preserved.** The previous `docs/adr/README.md` reserved 0010–0013 for
  upcoming decisions and marked 0013 (two-environments) as already accepted with a
  pointer to `docs/process/branching-and-environments.md`. All four rows are kept in the
  new README; the full ADR-0013 file will be written under a follow-up task rather than
  in this one (out of scope).
- **Path fixes to reserved rows.** The old README's `plan_specs/v2/e10-aws-account-baseline/…`
  and `plan_specs/v2/e14-web-app-foundation/…` paths were stale; verified against the
  filesystem and corrected to `plan_specs/v2/e10-aws-foundation/…` and
  `plan_specs/v2/e14-web-cut-card/…`.

## Operator follow-ups

None. All commands run in this session completed in well under two minutes.

## Follow-up work

- **Write the ADR-0013 file** (two environments and `dev`→`main` promotion). The
  decision is already accepted per `docs/process/branching-and-environments.md`; the
  standalone ADR file remains. Belongs to a small follow-up task in
  `v1-e01-repo-foundation` or to whatever task next touches the promotion workflow.
- **Choose and standardize a real link checker.** `linkcheckmd`'s local mode is
  minimal (only warns on unresolvable bare filenames) and does not recurse. A future
  process task should evaluate `markdown-link-check`, `pytest-check-links`, or a small
  in-repo script and wire it into `scripts/` + CI so this criterion becomes a
  meaningful check for all of `docs/`.
- **Cross-link §18 to the ADR files.** The proposal's §18 table currently lists ADRs by
  name only. A tiny follow-up (in a task that touches `docs/architecture/`) could add
  links from each row into `docs/adr/000N-…md` without changing the decision content.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

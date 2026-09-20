# Session report: v1-e30-t01-caselist-data-use-policy

| | |
|---|---|
| Task | `v1-e30-t01-caselist-data-use-policy` — Caselist and OpenEv data-use policy |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t01-caselist-data-use-policy.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t01-caselist-data-use-policy.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t01-caselist-data-use-policy` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Wrote [docs/policies/caselist-data-use.md](../policies/caselist-data-use.md) v1.0 and
[docs/runbooks/caselist-removal.md](../runbooks/caselist-removal.md), and indexed both from
[docs/README.md](../README.md). The policy covers scope, sources and terms, community disclosure
norms, permitted and prohibited uses, model-provider use, personal data, retention, attribution,
removal, the ADR-0013 dev exception, gates on E34 / E32 / v2-e35, open questions, change control
and approval. The runbook is a ten-step procedure around
`debate-research caselist remove`, with a manual section for the window before v1-e30-t07 ships.

**Status is PARTIAL, by the spec's own design, for two things only a human can do.** (1) The
*Sources and terms* section is a structured register, a clause-by-clause checklist and a fill-in
table — not transcribed clauses. The OpenCaselist terms sit behind a Tabroom login and the spec
itself says they "could not be retrieved automatically"; the session did not attempt a live fetch
and did not invent any clause text. (2) The *Approval* section is `_pending_`. Goal `ac1` is
therefore partly met and `ac6`'s approval half is not met; everything else passes. Both are in
**Operator follow-ups** with exactly what to record and where.

Because the terms are unconfirmed, every decision in the policy is written deliberately
**stricter than any plausible reading of them**, so a confirmed term can only relax a rule. That
choice is stated in the policy's preamble so a later reader knows why it reads conservatively.

Two things for the PM to look at first: the **model-provider decision** (yes, disclosed card text
may go to Bedrock through the ModelRouter, under seven conditions, gated on written no-training
terms), and the **`EvidenceOperator` permission gap** found while writing the runbook — v1-e29-t03
gives that permission set no `s3:DeleteObject`, but v1-e30-t07's `caselist remove` must delete
objects and their noncurrent versions. That is recorded as open question 8 and under Follow-up work.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `terms-review` — Record OpenCaselist and OpenEv terms and norms | PARTIAL | `## Sources and terms` written as a source register (4 sources with URLs and what we take), a 7+3-item clause checklist for the coach, a fill-in table, and `### Community disclosure norms` (5 norms). Verbatim clauses and dates read are pending the coach; each is an entry in `## Open questions`. |
| `use-decisions` — Permitted/prohibited uses, model-provider use, retention | PASS | `## Permitted uses` (7 numbered uses with conditions), `## Prohibited uses` (10 rules), `## Model provider use` (yes, with 7 conditions), `## Retention` (two-season clock, 8-row table, annual purge). |
| `personal-data` — Debater names and initials handling | PASS | `## Personal data`: what the corpus contains, 8 rules, the four places it may live, a per-report maximum-identity table, access. |
| `attribution-and-removal` — Attribution rules and removal runbook | PASS | `## Attribution` (6 rules incl. the provenance line format) and `## Removal` (requesters, channel, response-time table, what removal does and does not do, shared content). `docs/runbooks/caselist-removal.md` written, including the manual pre-t07 procedure. |
| `dev-exception` — ADR-0013 dev-data exception | PASS | `## Dev environment exception`: the exception, why necessary, why acceptable, 8 binding limits, and a note that ADR-0013 is not amended. |
| `gates-and-approval` — Downstream gates and coach approval | PARTIAL | `## Gates` written for E34 (8 conditions), E32 (4) and v2-e35 (9); policy linked from `docs/README.md`; `## Approval` table in place with version 1.0. Charlie's name and date are `_pending_` — his action, at PM review. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1 — terms recorded with URLs and date read, norms summarized, unconfirmed terms marked as open questions | PARTIAL | Structure, URLs, norms and open questions: PASS. `grep -c '^## Sources and terms' docs/policies/caselist-data-use.md` → `1`; the section holds a 4-row source register with URLs (`opencaselist.com`, `api.opencaselist.com`, archives, OpenEv), a clause checklist, an empty fill-in table, and `### Community disclosure norms`; `## Open questions` rows 1–3 are the unconfirmed terms. Transcribed clauses and dates read: **NOT RUN** — login-gated, coach's action (Operator follow-up 1). |
| Goal ac2 — explicit Permitted/Prohibited uses covering research, landscape, file building, no redistribution, no sharing outside the team, and model-provider use | PASS | `grep -c '^## Prohibited uses' …` → `1`. `## Permitted uses` rows 1–3 and 7 cover team-internal research, landscape reports and file building; `## Prohibited uses` items 1–2 cover public redistribution/re-hosting and sharing outside the team; `## Model provider use` states the decision (yes, via the ModelRouter only) with 7 binding conditions. |
| Goal ac3 — Personal data section (team codes as disclosed, never expanded/joined, never in logs/fixtures/S3 keys; reports show school + team code at most) and a per-season Retention period | PASS | `grep -c '^## Personal data' …` → `1`, `grep -c '^## Retention' …` → `1`. Personal-data rules 1–2 (kept as disclosed, never expanded or joined, no `debater_names` field), 3 (never in S3 keys or metadata), 4 (never in logs), 5 (never in committed fixtures); the report table sets circuit-wide = nothing and per-school = "School plus team code, as disclosed. Never more." Retention: season = 1 Aug–31 Jul, snapshots kept for their season plus the following one (2026-27 → deleted by 31 Aug 2028). |
| Goal ac4 — Attribution rules for disclosed and camp cards, and a Removal section with requesters, response time and the runbook steps | PASS | `grep -c '^## Removal' …` → `1`; `docs/runbooks/caselist-removal.md` exists and `grep -c 'caselist remove' docs/runbooks/caselist-removal.md` → `8`. Attribution rule 1 keeps the cite verbatim, rule 2 adds the provenance line (`[Disclosed: <caselist> <snapshot> — <School> <TeamCode>, <Side> vs. <Tournament> <Round>]` / `[OpenEv: <Camp> <Year> — <Event>, <Title>]`), rule 4 forbids presenting them as verified. Removal names 5 requester categories, a 4-row response-time table (ack 3 business days, removed and built files flagged within 7 calendar days), and the runbook's dev→prod `--execute` / `--confirm-prod` sequence with suppression-list confirmation and built-file flagging. |
| Goal ac5 — Dev environment exception recording the ADR-0013 exception with justification and limits | PASS | `grep -c '^## Dev environment exception' …` → `1`. States the exception, why necessary (real volume and real path shapes; ~2,342 .docx per v1-e30-t06; "validated in dev" promotion rule), why acceptable (already public, not student account data, operator-only access, same bucket controls), and 8 binding limits including operators only, two locations, never CI data, same retention clock, removals applied to dev and prod together, and no extension to V2 accounts. |
| Goal ac6 — Gates section for E34 and v2-e35, and Charlie's approval (name, date, version) recorded | PARTIAL | Gates: PASS — `## Gates` has `### E34 — automated caselist download (v1.2)` (8 conditions), `### E32 — model classification of the corpus` (4) and `### v2-e35 — debate tub (v2.1)` (9). Approval: `grep -c 'Approved by' …` → `2` (header table and `## Approval` table), policy version `1.0` recorded, **name and date `_pending_`** — Charlie's action at PM review (Operator follow-up 2). |
| Node `terms-review` ac — `docs/policies/caselist-data-use.md` contains `## Sources and terms` | PASS | `grep -c -- '## Sources and terms' docs/policies/caselist-data-use.md` → `1`. |
| Node `terms-review` ac — coach confirms the transcribed terms | NOT RUN | Manual check by Charlie; nothing is transcribed yet, so there is nothing to confirm. Operator follow-up 1. |
| Node `use-decisions` ac — contains `## Prohibited uses` | PASS | `grep -c -- '## Prohibited uses' …` → `1`. |
| Node `use-decisions` ac — contains `## Retention` | PASS | `grep -c -- '## Retention' …` → `1`. |
| Node `personal-data` ac — contains `## Personal data` | PASS | `grep -c -- '## Personal data' …` → `1`. |
| Node `attribution-and-removal` ac — `docs/runbooks/caselist-removal.md` exists and contains `caselist remove` | PASS | `test -f docs/runbooks/caselist-removal.md` → exit 0; `grep -c 'caselist remove' …` → `8`. |
| Node `attribution-and-removal` ac — policy contains `## Removal` | PASS | `grep -c -- '## Removal' …` → `1`. |
| Node `dev-exception` ac — policy contains `## Dev environment exception` | PASS | `grep -c -- '## Dev environment exception' …` → `1`. |
| Node `gates-and-approval` ac — policy contains `Approved by` | PASS | `grep -c 'Approved by' …` → `2`. |
| Node `gates-and-approval` ac — Charlie approves the policy | NOT RUN | Manual approval by Charlie at PM review. Operator follow-up 2. |
| Repo-wide — offline link check over the new and changed docs | PASS | Walker over every relative link (plus `#anchor`, GitHub slug rules) in `docs/policies/caselist-data-use.md`, `docs/runbooks/caselist-removal.md` and `docs/README.md` → `65 relative links checked, 0 broken`. Every `plan_specs/...` path cited in the two new docs resolves on disk (7/7 `OK`). |
| Repo-wide — `uv run scripts/validate_specs.py` | PASS | `OK: 261 files, 35 epics, 207 tasks, 19 releases`. |
| Repo-wide — task shows Succeeded | PASS | `uv run scripts/validate_specs.py --require-succeeded v1-e30-t01-caselist-data-use-policy` → `v1-e30-t01-caselist-data-use-policy: Succeeded`. |

`ROADMAP.md` was deliberately **not** regenerated (`scripts/spec_index.py` not run), per CLAUDE.md.

## Files changed

- `docs/policies/caselist-data-use.md` (new, 540 lines) — the policy, version 1.0, status Draft.
- `docs/runbooks/caselist-removal.md` (new, 215 lines) — the removal procedure, plus the manual
  procedure that applies until v1-e30-t07 ships.
- `docs/README.md` — index rows for the policy and the runbook; the trailing paragraph updated so
  it no longer lists `policies/` and `runbooks/` as directories yet to be created.
- `plan_specs/v1/e30-caselist-ingestion/t01-caselist-data-use-policy.yaml` — `status.phase`
  set to `Succeeded` via `scripts/task_helper.py`.
- `docs/session-reports/v1-e30-t01-caselist-data-use-policy.md` — this report.

No code changed; the spec's `packages` constraint is `[docs/policies, docs/runbooks]` and the only
file touched outside it is `docs/README.md`, which the `gates-and-approval` node explicitly
requires ("link the policy from docs/README.md").

## Deviations from the spec

1. **`## Sources and terms` holds a register and a checklist, not transcribed clauses.** The
   `terms-review` node assumes a loop with the coach ("the coach reads … the session transcribes")
   that a non-interactive session cannot run, and the Goal description itself notes the pages
   "could not be retrieved automatically". Rather than fabricate clause text — which would be the
   worst possible failure mode for a policy whose whole job is to record what the sources actually
   say — the section was built as the structure the transcription drops into: a source register
   with URLs, an explicit `Transcription status: PENDING` banner, a clause-by-clause checklist of
   what to look for in each source, an empty fill-in table, and three matching open questions.
   Goal `ac1` is therefore PARTIAL. No live fetch of the OpenCaselist or OpenEv pages was
   attempted from this session.
2. **`## Approval` records the fields but not an approval.** `ac6` wants Charlie's name, date and
   policy version *in* the document. Version 1.0 is recorded; name and date are `_pending_`,
   since the approval happens at PM review, after this report. The policy opens by stating that
   nothing it governs may happen until that table is filled in, which is the behaviour `ac6` is
   protecting.
3. **Three sections were added beyond the spec's list:** `## Scope`, `## Open questions` and
   `## Review and change control`. `ac1` requires unconfirmed terms to be "marked as an open
   question", which needs somewhere to put them; scope and change control keep the policy usable
   across seasons. No section required by the spec was dropped or renamed.
4. **`## Model provider use` is its own `##` section** rather than a subsection of the use
   sections. `ac2` folds it into Permitted/Prohibited uses, but it carries seven binding
   conditions and its own gate, and burying it in a table row would have lost them. Both use
   sections cross-reference it.

## Decisions and assumptions

Decisions the spec left to this task. Each is written to be revisable at approval.

- **Model provider use: permitted, conditionally.** Disclosed and camp card text may reach the
  configured provider (Bedrock) through the ModelRouter, because the argument landscape (E32)
  cannot be built otherwise and the alternative is a human reading 2,000+ documents. The seven
  conditions bind it to: ModelRouter only (never a consumer chat UI), written no-training and
  no-retention terms confirmed before the first full-corpus run, bounded excerpts only, no school
  name / team code / debater name / path / tournament / round in any prompt, metadata-only output
  (ids, confidence, rationale — never evidence text), synthetic committed cassettes, and cached
  results. Conditions 3–5 restate constraints v1-e32-t02 already imposes, so the policy and that
  spec cannot drift.
- **Retention: two seasons.** A season is 1 Aug – 31 Jul; a season's snapshots and everything
  derived from them are deleted by 31 August after the *following* season ends (2026-27 → 31 Aug
  2028). Rationale: year-over-year trend work (v1-e32-t04) needs the prior season, and nothing
  needs the one before that. Circuit-wide landscape reports carry no personal data and are kept
  indefinitely; per-school views expire with their sources. Noncurrent S3 versions follow the
  v1-e29-t03 lifecycle (IA at 30 days, expire 365 prod / 30 dev), except that a removal purges
  them immediately instead of waiting.
- **Response times: acknowledge in 3 business days, removed in 7 calendar days.** Short enough to
  be a real commitment, long enough to survive a tournament weekend, and achievable by one
  operator running the runbook by hand.
- **Shared content defaults to staying.** If the same bytes were disclosed by two teams, the
  default removal drops only the requesting team's `Disclosure` records; removing the blob needs
  `--include-shared` and a judgement call, and the requester is told what stayed. This matches
  v1-e30-t07's flag design.
- **Provenance line format.** `[Disclosed: <caselist> <snapshot> — <School> <TeamCode>, <Side> vs.
  <Tournament> <Round>]` and `[OpenEv: <Camp> <Year> — <Event>, <Title>]`, appended below an
  untouched cite. Chosen to be readable in Word next to a Verbatim cite, and to carry exactly the
  fields v1-e33-t02's sidecar manifest already records.
- **Tub audit retention: 400 days.** The v2-e35-t05 spec says the TTL comes from this policy; 400
  days covers a full season plus a season-over-season comparison, and is the common one-year-plus
  -slack default.
- **Examples in both documents are fictional** (`Maple Grove QX`, `Riverbend Invitational`,
  `Cascade Institute 2026`), matching the fixture convention in v1-e30-t03 and the spec's
  prohibition on real names in the repository. The caselist slugs (`hsld26`) are real but are
  already used throughout the E30/E34 specs and identify no person.
- **Removal contact address left as a placeholder.** `<removal contact address — filled in at
  approval>`; the session has no address it is entitled to publish. Open question 5.
- **ADR-0013 was not edited.** The dev exception is recorded in the policy and points at the ADR,
  because the spec's `packages` constraint is `[docs/policies, docs/runbooks]` and a policy-level
  exception is reversible in a way an ADR amendment is not. The policy notes that a superseding
  ADR is the right move if the exception outlives V1.

## Operator follow-ups

Neither is a long-running command; both are things only Charlie can supply. They are the two
reasons this report is PARTIAL.

**1. Transcribe the OpenCaselist and OpenEv terms** (~30–45 min, closes `ac1` and the
`terms-review` custom criterion)

Where: a browser, signed in to opencaselist.com with your Tabroom account.

1. Open the OpenCaselist terms-of-use and privacy pages and note their exact URLs.
2. Work down the "Clauses to transcribe" checklist in
   [docs/policies/caselist-data-use.md § Sources and terms](../policies/caselist-data-use.md#sources-and-terms)
   — 7 items for OpenCaselist, 3 for OpenEv.
3. Paste each relevant clause verbatim into the fill-in table with its URL and the date read, and
   tick the "Terms recorded?" boxes in the source register.
4. Delete the `Transcription status: PENDING` banner once the table is filled.
5. Confirm or correct the five bullets under "Community disclosure norms" — they are the
   session's account of circuit practice, not quoted rules.
6. For anything the pages do not answer, leave it in `## Open questions` rather than guessing.

Success looks like: every row of the fill-in table populated, and open questions 1–3 either
answered or explicitly accepted as gaps.

**2. Approve the policy** (~20 min, closes `ac6` and the `gates-and-approval` custom criterion)

Where: this worktree, or the PR.

1. Read the policy and the runbook end to end.
2. Fill in the removal contact address in `## Removal` (open question 5).
3. Resolve or accept each remaining open question and list the numbers in the Approval table.
4. Fill in the `## Approval` table: `Approved by`, `Approval date`, and change the header
   `Status` row from "Draft — not yet approved" to approved.

Until that table is filled in, the policy blocks publishing any import, loading the real corpus
into dev, automated download, and model classification over real disclosed text — which is also
what v1-e30-t06 and v1-e34-t01 already refuse to do.

**3. Before the first full-corpus classification run** (not blocking this task): get written
confirmation of the model provider's no-training / no-retention terms for the AWS account and
record it in the policy (open question 4, E32 gate).

## Follow-up work

1. **`EvidenceOperator` cannot delete.** v1-e29-t03 defines the `EvidenceOperator` permission set
   with "no `DeleteObject`", but v1-e30-t07's `caselist remove` must delete `raw/` and `parsed/`
   objects *and all noncurrent versions*, and rewrite manifests. As specified, a removal cannot be
   executed by the operator profile it is designed for. Either t07 runs under a separate scoped
   role, or v1-e29-t03's permission set gains a narrow delete right. Recorded as open question 8
   in the policy and as a permissions note in the runbook; **it should be resolved before the
   7-day removal window in the policy is treated as a real commitment.** Belongs to v1-e30-t07
   (with a spec change to v1-e29-t03 if that is the answer).
2. **No un-suppress path.** v1-e30-t07's suppression list is append-only JSONL with no documented
   way to reverse an entry, so a removal run against the wrong selector cannot be undone — the
   noncurrent versions are purged and re-import is refused. The runbook's "If you removed the
   wrong thing" section treats it as an escalation. A tombstone entry or a documented
   `--unsuppress` (operator-only, logged) belongs in v1-e30-t07's spec.
3. **Removal register file.** The runbook asks the operator to create
   `docs/data/caselist-removal-requests.md` on the first request. `docs/data/` does not exist yet
   (v1-e30-t06 creates it). Harmless, but if E30 wants a template the way the backfill summary has
   one, that is a small addition to v1-e30-t06 or t07.
4. **Annual retention purge has no owner task.** The policy commits to a September purge of the
   season that has aged out, in dev and prod, with counts recorded in `docs/data/`. Nothing in
   E30–E34 implements or schedules it. First purge is due September 2028, so there is time, but it
   should become a task in a later release rather than live only in the policy.
5. **The E34 gate list should be mirrored into v1-e34-t01's acceptance criteria** when that task is
   picked up, so the conditions are machine-checked rather than only written here.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

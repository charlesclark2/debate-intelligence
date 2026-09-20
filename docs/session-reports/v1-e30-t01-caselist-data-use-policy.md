# Session report: v1-e30-t01-caselist-data-use-policy

| | |
|---|---|
| Task | `v1-e30-t01-caselist-data-use-policy` — Caselist and OpenEv data-use policy |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t01-caselist-data-use-policy.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t01-caselist-data-use-policy.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t01-caselist-data-use-policy` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Wrote [docs/policies/caselist-data-use.md](../policies/caselist-data-use.md) v1.0 and
[docs/runbooks/caselist-removal.md](../runbooks/caselist-removal.md), and indexed both from
[docs/README.md](../README.md). The policy covers scope, sources and terms, community disclosure
norms, permitted and prohibited uses, model-provider use, personal data, retention, attribution,
removal, the ADR-0013 dev exception, gates on E34 / E32 / v2-e35, open questions, change control
and approval. The runbook is a ten-step procedure around `debate-research caselist remove`, with a
manual section for the window before v1-e30-t07 ships.

**The first review returned CHANGES_REQUESTED; all four items are addressed and the task is now
COMPLETE.** The PM read the OpenCaselist Terms & Conditions at `https://opencaselist.com/terms` on
2026-09-19 — they are public, not login-gated as the first draft assumed — and supplied a clause
summary. That summary is now a **clause register** of eleven rows in `## Sources and terms`, each
paraphrased with the site's own phrases quoted, each tied to the rule it backs. Charlie confirmed
the register and the disclosure norms and **approved version 1.0 on 2026-09-19**, so the policy's
status is Approved, the removal contact address is recorded, and every acceptance criterion now
passes.

**What the terms changed, and what they did not.** No term is stricter than a rule already in the
policy — the prohibitions covered every relevant Acceptable Use item — so no decision was
reversed. What they *added* is a real constraint on E34: rate limits bind "manual or automated",
access is limited to "publicly supported interfaces", and the terms state **neither a rate nor
whether the documented API counts as such an interface for a scheduled job**. Open question 2 was
rewritten around those two points, and the E34 gate now requires Charlie to get the maintainer's
written confirmation before E34 is built or run, with the weekly pull staying manual until the
reply is recorded. That is the single most important consequence of this review.

Three open questions remain by Charlie's decision: 2 (maintainer confirmation, before E34), 4
(Bedrock data-protection terms, an E32 gate), and 6 (school or district review, before V2 student
accounts). Two were accepted as known gaps: 1 (the privacy page) and 3 (OpenEv terms). None
blocks the v1.1 work that follows this task.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `terms-review` — Record OpenCaselist and OpenEv terms and norms | PASS | `## Sources and terms` holds a 4-row source register, an 11-row **clause register** from the Terms & Conditions read 2026-09-19 (URL and date on the section), an assessment line, a "Still to read" list for the privacy page and OpenEv, and `### Community disclosure norms` (5 norms). Charlie confirmed the register and the norms at approval. |
| `use-decisions` — Permitted/prohibited uses, model-provider use, retention | PASS | `## Permitted uses` (7 numbered uses with conditions), `## Prohibited uses` (10 rules), `## Model provider use` (yes, with 7 conditions), `## Retention` (two-season clock, 8-row table, annual purge). |
| `personal-data` — Debater names and initials handling | PASS | `## Personal data`: what the corpus contains, 8 rules, the four places it may live, a per-report maximum-identity table, access. |
| `attribution-and-removal` — Attribution rules and removal runbook | PASS | `## Attribution` (6 rules incl. the provenance line format) and `## Removal` (requesters, contact address, response-time table, what removal does and does not do, shared content). `docs/runbooks/caselist-removal.md` written, including the manual pre-t07 procedure. |
| `dev-exception` — ADR-0013 dev-data exception | PASS | `## Dev environment exception`: the exception, why necessary, why acceptable, 8 binding limits, and a note that ADR-0013 is not amended. |
| `gates-and-approval` — Downstream gates and coach approval | PASS | `## Gates` for E34 (8 conditions, item 2 now the maintainer-confirmation gate), E32 (4) and v2-e35 (9); policy linked from `docs/README.md`; `## Approval` records Charlie Clark, product owner and head coach, 2026-09-19, version 1.0, with each open question's disposition. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1 — terms recorded with URLs and date read, norms summarized, unconfirmed terms marked as open questions | PASS | `grep -c -- '## Sources and terms' docs/policies/caselist-data-use.md` → `1`. The section carries the URL `https://opencaselist.com/terms` and "read **2026-09-19**" above an 11-row clause register (Your Stuff, Your Responsibilities, Our Stuff, seven Acceptable Use items, Termination, Modifications), each with what it says and what it means for us; a 4-row source register with per-source "Terms recorded?" state; `### Community disclosure norms` (5 norms, confirmed by Charlie); and a "Still to read" list. The two unread sources are `## Open questions` 1 and 3, both marked **Accepted as a known gap, 2026-09-19**. |
| Goal ac2 — explicit Permitted/Prohibited uses covering research, landscape, file building, no redistribution, no sharing outside the team, and model-provider use | PASS | `grep -c -- '## Prohibited uses' …` → `1`. `## Permitted uses` rows 1–3 and 7 cover team-internal research, landscape reports and file building; `## Prohibited uses` items 1–2 cover public redistribution/re-hosting and sharing outside the team; `## Model provider use` states the decision (yes, via the ModelRouter only) with 7 binding conditions. Clause-register rows 2, 3 and 8 are now cited as the written backing for prohibitions 1–3. |
| Goal ac3 — Personal data section (team codes as disclosed, never expanded/joined, never in logs/fixtures/S3 keys; reports show school + team code at most) and a per-season Retention period | PASS | `grep -c -- '## Personal data' …` → `1`, `grep -c -- '## Retention' …` → `1`. Personal-data rules 1–2 (kept as disclosed, never expanded or joined, no `debater_names` field), 3 (never in S3 keys or metadata), 4 (never in logs), 5 (never in committed fixtures); the report table sets circuit-wide = nothing and per-school = "School plus team code, as disclosed. Never more." Retention: season = 1 Aug–31 Jul, snapshots kept for their season plus the following one (2026-27 → deleted by 31 Aug 2028); Charlie kept this at approval (open question 7, Resolved). |
| Goal ac4 — Attribution rules for disclosed and camp cards, and a Removal section with requesters, response time and the runbook steps | PASS | `grep -c -- '## Removal' …` → `1`; `grep -c 'caselist remove' docs/runbooks/caselist-removal.md` → `8`. Attribution rule 1 keeps the cite verbatim, rule 2 adds the provenance line (`[Disclosed: <caselist> <snapshot> — <School> <TeamCode>, <Side> vs. <Tournament> <Round>]` / `[OpenEv: <Camp> <Year> — <Event>, <Title>]`), rule 4 forbids presenting them as verified. Removal names 5 requester categories, the contact address `ctcb57@gmail.com`, and a 4-row response-time table (ack 3 business days; removed, flagged and confirmed within 7 calendar days), over the runbook's dev→prod `--execute` / `--confirm-prod` sequence with suppression-list confirmation and built-file flagging. |
| Goal ac5 — Dev environment exception recording the ADR-0013 exception with justification and limits | PASS | `grep -c -- '## Dev environment exception' …` → `1`. States the exception, why necessary (real volume and real path shapes; ~2,342 .docx per v1-e30-t06; the "validated in dev" promotion rule), why acceptable (already public, not student account data, operator-only access, same bucket controls), and 8 binding limits including operators only, two locations, never CI data, same retention clock, removals applied to dev and prod together, and no extension to V2 accounts. |
| Goal ac6 — Gates section for E34 and v2-e35, and Charlie's approval (name, date, version) recorded | PASS | `## Gates` has `### E34 — automated caselist download (v1.2)` (8 conditions), `### E32 — model classification of the corpus` (4) and `### v2-e35 — debate tub (v2.1)` (9). `grep -c 'Approved by' …` → `2` (header table and `## Approval`). Approval records **Charlie Clark, product owner and head coach, 2026-09-19, version 1.0**, with three rows giving each open question's disposition (resolved 5, 7, 8; accepted 1, 3; open 2, 4, 6). Header `Status` is now "**Approved**, version 1.0, 2026-09-19". |
| Node `terms-review` ac — `docs/policies/caselist-data-use.md` contains `## Sources and terms` | PASS | `grep -c -- '## Sources and terms' …` → `1`. |
| Node `terms-review` ac (custom) — coach confirms the transcribed terms | PASS | Charlie, 2026-09-19: "I confirm the OpenCaselist terms summary from the PM notes as read on 2026-09-19." Recorded in the policy's Approval table under *Scope of approval*. |
| Node `use-decisions` ac — contains `## Prohibited uses` | PASS | `grep -c -- '## Prohibited uses' …` → `1`. |
| Node `use-decisions` ac — contains `## Retention` | PASS | `grep -c -- '## Retention' …` → `1`. |
| Node `personal-data` ac — contains `## Personal data` | PASS | `grep -c -- '## Personal data' …` → `1`. |
| Node `attribution-and-removal` ac — `docs/runbooks/caselist-removal.md` exists and contains `caselist remove` | PASS | `test -f docs/runbooks/caselist-removal.md` → exit 0; `grep -c 'caselist remove' …` → `8`. |
| Node `attribution-and-removal` ac — policy contains `## Removal` | PASS | `grep -c -- '## Removal' …` → `1`. |
| Node `dev-exception` ac — policy contains `## Dev environment exception` | PASS | `grep -c -- '## Dev environment exception' …` → `1`. |
| Node `gates-and-approval` ac — policy contains `Approved by` | PASS | `grep -c 'Approved by' …` → `2`. |
| Node `gates-and-approval` ac (custom) — Charlie approves the policy | PASS | Charlie, 2026-09-19: "I approve policy version 1.0: Charlie Clark, product owner and head coach, 09/19/2026", recorded in `## Approval` as 2026-09-19 (ISO, same date, matching the repo's date convention). |
| PM review item 1 — record the terms; drop the login-gated framing; rewrite open question 2 and E34 gate item 2 | PASS | Banner replaced with "Read 2026-09-19; privacy page and OpenEv terms still open". Clause register added (11 rows). Source register "Terms recorded?" column updated per source. "Clauses to transcribe" replaced by "Still to read" (privacy page, OpenEv). Assessment line records that no term is stricter than the policy. Open question 2 rewritten around the unstated rate and the "publicly supported interfaces" question. E34 gate item 2 rewritten as the maintainer-confirmation gate with "**Until that reply is recorded, the weekly pull stays manual.**" The word "login-gated" no longer appears in either document (`grep -ci 'login-gated\|transcri\|pending\|draft' docs/policies/caselist-data-use.md docs/runbooks/caselist-removal.md` → `0`). |
| PM review item 2 — record Charlie's approval exactly as stated, nothing he did not state | PASS | Approval table holds only what Charlie said: name, role, 2026-09-19, version 1.0, address `ctcb57@gmail.com`, and his disposition of each open question. No field was inferred; the privacy page and OpenEv rows say "Accepted as a known gap", not "confirmed". |
| PM review item 3 — reword open question 4 around the Bedrock data-protection documentation and third-party invocation logging | PASS | Open question 4 now asks for the AWS Bedrock data-protection documentation (Bedrock does not store prompts or completions and does not use them to train models), recorded by URL and date read, **plus** a check that no model-invocation logging to a third-party destination is enabled in the account. Status **Open**, resolver Operator, blocking the E32 gate and explicitly "not a blocker for this approval". |
| PM review item 4 — leave open question 8 in place with the PM spec change as resolver | PASS | Open question 8 status is "**Resolved by a spec change to v1-e29-t03 / v1-e30-t07 (PM)**", resolver "PM, in a separate specs pull request". The runbook's permissions note and its "If you removed the wrong thing" section both now point at that spec change instead of asking the operator to raise one. Follow-up 4 (annual purge) left unchanged for the PM backlog. |
| Repo-wide — offline link check over the new and changed docs | PASS | Walker over every relative link (plus `#anchor`, GitHub slug rules) in `docs/policies/caselist-data-use.md`, `docs/runbooks/caselist-removal.md`, `docs/README.md` and this report → `95 relative links checked, 0 broken`. Every `plan_specs/...` path cited in the two documents resolves on disk (7/7 `OK`). |
| Repo-wide — `uv run scripts/validate_specs.py` | PASS | `OK: 261 files, 35 epics, 207 tasks, 19 releases`. |
| Repo-wide — task shows Succeeded | PASS | `uv run scripts/validate_specs.py --require-succeeded v1-e30-t01-caselist-data-use-policy` → `v1-e30-t01-caselist-data-use-policy: Succeeded`. |

`ROADMAP.md` was deliberately **not** regenerated (`scripts/spec_index.py` not run), per CLAUDE.md.

## Files changed

- `docs/policies/caselist-data-use.md` (new, 568 lines) — the policy, version 1.0, **Approved
  2026-09-19**. Second pass rewrote `## Sources and terms` (clause register), `## Open questions`
  (status column, questions 1–5, 7, 8 revised), `## Approval` (Charlie's approval recorded), E34
  gate item 2, the removal contact address, the header status rows and the preamble.
- `docs/runbooks/caselist-removal.md` (new, 216 lines) — the removal procedure, plus the manual
  procedure for the window before v1-e30-t07 ships. Second pass updated the `EvidenceOperator`
  permissions note and the erroneous-removal section to point at the PM's spec change.
- `docs/README.md` — index rows for the policy and the runbook; the trailing paragraph updated so
  it no longer lists `policies/` and `runbooks/` as directories yet to be created.
- `plan_specs/v1/e30-caselist-ingestion/t01-caselist-data-use-policy.yaml` — `status.phase`
  set to `Succeeded` via `scripts/task_helper.py`; unchanged in the second pass.
- `docs/session-reports/v1-e30-t01-caselist-data-use-policy.md` — this report.

No code changed. The spec's `packages` constraint is `[docs/policies, docs/runbooks]` and the only
file touched outside it is `docs/README.md`, which the `gates-and-approval` node explicitly
requires ("link the policy from docs/README.md").

## Deviations from the spec

1. **The terms were not login-gated, and the first draft said they were.** The Goal description
   states the terms "could not be retrieved automatically", and the first pass took that at face
   value, left `## Sources and terms` as a register plus a checklist, and marked Goal `ac1`
   PARTIAL rather than invent clause text. The PM then read
   `https://opencaselist.com/terms` — a public page — on 2026-09-19 and supplied the clauses,
   which are now recorded. The spec's premise was wrong on this point; nothing else in it was.
   Refusing to fabricate the clauses was the right call and is why the register now contains the
   site's words rather than a guess, but the session should have established whether the page was
   actually reachable before assuming it was not.
2. **Three sections were added beyond the spec's list:** `## Scope`, `## Open questions` and
   `## Review and change control`. `ac1` requires unconfirmed terms to be "marked as an open
   question", which needs somewhere to put them; scope and change control keep the policy usable
   across seasons. No section required by the spec was dropped or renamed.
3. **`## Model provider use` is its own `##` section** rather than a subsection of the use
   sections. `ac2` folds it into Permitted/Prohibited uses, but it carries seven binding
   conditions and its own gate, and burying it in a table row would have lost them. Both use
   sections cross-reference it.

## Decisions and assumptions

Decisions the spec left to this task. Each is revisable through
[Review and change control](../policies/caselist-data-use.md#review-and-change-control).

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
  needs the one before that. Charlie kept this unchanged at approval. Circuit-wide landscape
  reports carry no personal data and are kept indefinitely; per-school views expire with their
  sources. Noncurrent S3 versions follow the v1-e29-t03 lifecycle (IA at 30 days, expire 365 prod
  / 30 dev), except that a removal purges them immediately instead of waiting.
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
  days covers a full season plus a season-over-season comparison, and is the common one-year-plus-
  slack default.
- **Clause register style: paraphrase, quote what matters.** Per the PM's instruction, each row
  paraphrases the clause and quotes only the phrases that carry weight ("manual or automated",
  "publicly supported interfaces"). That keeps the register readable and avoids reproducing the
  page wholesale, while the phrases that decide an argument are the site's own.
- **Examples in both documents are fictional** (`Maple Grove QX`, `Riverbend Invitational`,
  `Cascade Institute 2026`), matching the fixture convention in v1-e30-t03 and the spec's
  prohibition on real names in the repository. The caselist slugs (`hsld26`) are real but are
  already used throughout the E30/E34 specs and identify no person.
- **Approval date recorded as `2026-09-19`.** Charlie wrote `09/19/2026`; the ISO form is the same
  date and matches every other date in the repository.
- **ADR-0013 was not edited.** The dev exception is recorded in the policy and points at the ADR,
  because the spec's `packages` constraint is `[docs/policies, docs/runbooks]` and a policy-level
  exception is reversible in a way an ADR amendment is not. The policy notes that a superseding
  ADR is the right move if the exception outlives V1.

## Operator follow-ups

Nothing here blocks this task or the v1.1 work that follows it. None is a long-running command.

**1. Contact the OpenCaselist maintainer before E34** (open question 2 — the one that gates
scheduled download)

The Terms & Conditions forbid downloading beyond "set rate limits", manual or automated, and
limit access to "publicly supported interfaces", but state neither a rate nor whether the
documented API qualifies for a scheduled job. Through the site's Contact link, ask whether
scheduled weekly archive downloads through `api.opencaselist.com` are acceptable and what rate to
stay under. Record the reply — date, who answered, what they said — in the clause register in
[§ Sources and terms](../policies/caselist-data-use.md#sources-and-terms).

Success looks like: a recorded reply, and open question 2 moved to Resolved. **Until then the
weekly pull stays manual and v1-e34-t01 does not start.**

**2. Before the first full-corpus classification run** (open question 4, E32 gate)

Record the AWS Bedrock data-protection documentation by URL and date read (Bedrock does not store
prompts or completions and does not use them to train models), and confirm in the account that no
model-invocation logging to a third-party destination is enabled. Both go in the clause register.

**3. When convenient** (open questions 1 and 3, accepted as known gaps at approval)

Read the OpenCaselist privacy page and OpenEv's distribution terms and record them; the
"Still to read" list in § Sources and terms says exactly what to look for in each.

**4. Before V2 student accounts** (open question 6)

Decide with the school whether a school or district review is needed before students — who may be
minors — get tub accounts. Gate item 9 on v2-e35 depends on it.

## Follow-up work

1. **`EvidenceOperator` cannot delete.** v1-e29-t03 defines the `EvidenceOperator` permission set
   with "no `DeleteObject`", but v1-e30-t07's `caselist remove` must delete `raw/` and `parsed/`
   objects *and all noncurrent versions*, and rewrite manifests. As specified, a removal cannot be
   executed by the operator profile it is designed for. **The PM is amending v1-e29-t03 and
   v1-e30-t07 in a separate specs PR** (open question 8). Until that lands, the runbook's manual
   procedure requires an administrator profile, which it now says explicitly.
2. **No un-suppress path.** v1-e30-t07's suppression list is append-only JSONL with no documented
   way to reverse an entry, so a removal run against the wrong selector cannot be undone — the
   noncurrent versions are purged and re-import is refused. **Also covered by the PM's spec
   change**; the runbook's "If you removed the wrong thing" section now says the un-suppress path
   is coming rather than asking the operator to raise it.
3. **Removal register file.** The runbook asks the operator to create
   `docs/data/caselist-removal-requests.md` on the first request. `docs/data/` does not exist yet
   (v1-e30-t06 creates it). Harmless, but if E30 wants a template the way the backfill summary has
   one, that is a small addition to v1-e30-t06 or t07.
4. **Annual retention purge has no owner task.** The policy commits to a September purge of the
   season that has aged out, in dev and prod, with counts recorded in `docs/data/`. Nothing in
   E30–E34 implements or schedules it. First purge is due September 2028, so there is time.
   **On the PM's backlog**; no change made here.
5. **The E34 gate list should be mirrored into v1-e34-t01's acceptance criteria** when that task
   is picked up, so the eight conditions — especially the maintainer confirmation — are
   machine-checked rather than only written here.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED

**Reviewed by / date:** PM (Claude, project chat), 2026-09-19

**Notes:**

The policy is strong and I agree with its decisions: model use through the ModelRouter under the
seven conditions, retention of the season plus the following one, 3 business days / 7 calendar
days for removals, shared content staying by default, the provenance line format, and recording
the dev exception in the policy instead of amending ADR-0013. Not inventing clause text was the
right call. Two gaps block acceptance, both now closable:

1. **Terms were not actually login-gated. Record them.** The PM read
   https://opencaselist.com/terms ("Terms & Conditions") on 2026-09-19. Fill in the Sources and
   terms fill-in table from the summary below, one row per clause, with that URL and date. Use a
   short key phrase in quotation marks where the wording matters, and paraphrase the rest. Charlie
   confirms the rows (the `terms-review` custom criterion) when he approves. Remove the
   PENDING banner and replace it with "Read 2026-09-19; privacy page and OpenEv terms still open".
   Then revise: the "login-gated" wording in the banner, the source register, open question 1 and
   this report; open question 2 (below); and the E34 gate item 2.
   - **Your Stuff:** uploaders keep ownership of their files; the site gets rights to store,
     archive and display them.
   - **Your Responsibilities:** don't copy, upload, download or share content unless you have the
     right to. Content may be protected by others' intellectual property rights. The site is not
     responsible for user content.
   - **Our Stuff:** no rights in the Services or in others' content are granted.
   - **Acceptable Use** (relevant items):
     - no downloading beyond set rate limits, manual or automated;
     - no circumventing security or authentication;
     - no accessing non-public areas;
     - no overloading the service;
     - no accessing, searching or creating accounts except through "publicly supported
       interfaces" (scraping and bulk account creation are the examples given);
     - no selling the Services;
     - no violating others' privacy or rights.
   - **Termination:** access can be suspended at the site's discretion.
   - **Modifications:** terms may change, and continued use means acceptance.

   Rate limits are not stated. Whether the documented API at api.opencaselist.com counts as a
   "publicly supported interface" for scheduled downloads is not stated either. Rewrite open
   question 2 to cover these two points. Add to the E34 gate that Charlie contacts the
   maintainer (site Contact link) to confirm scheduled weekly archive downloads through the API,
   and the rate to stay under, and records the reply. Until then the pull stays manual. Terms
   stricter than the policy: none found. The policy's prohibitions already cover every relevant
   Acceptable Use item. The privacy page and OpenEv terms stay open questions; Charlie may accept
   them as known gaps at approval.
2. **Approval.** Charlie will give the removal contact address, his decision on each open
   question, and his approval in the session. Record exactly what he says in the Approval table
   and the header, and change Status to Approved. Do not fill in approval fields he has not
   stated.
3. **Open question 4 (model provider terms).** Reword it to say what is needed: the AWS Bedrock
   data-protection documentation (Bedrock does not store prompts or completions or use them to
   train models), recorded by URL and date read, plus a check that no model-invocation logging to
   a third party is enabled in the account. It stays an E32 gate, not a blocker for this approval.
4. **Follow-ups 1 and 2 (EvidenceOperator cannot delete; no un-suppress path).** Agreed. The PM is
   amending v1-e29-t03 and v1-e30-t07 in a separate `specs/` PR. Leave open question 8 in place,
   with "resolved by spec change to v1-e29-t03 / v1-e30-t07 (PM)" as the resolver.
   Follow-up 4 (annual purge has no owner) goes to the PM backlog; no change here.

After these edits, commit the policy, the runbook and this report together, keep the phase
Succeeded, and change Session status to COMPLETE.

**Round 2 (2026-09-19): ACCEPTED.** All four items are addressed. The clause register matches the
terms as the PM read them on 2026-09-19 and follows the paraphrase-with-key-phrases rule. The
approval table records exactly the dispositions Charlie gave. Open question 4 is reworded as
requested, and the E34 gate now requires the maintainer's confirmation. The follow-ups carry
forward as tracked: open question 2 before E34, open question 4 before the first full-corpus E32
run, open question 6 before V2 student accounts, and the removal-permission and un-suppress spec
change in PR `specs/evidence-removal-permissions`.


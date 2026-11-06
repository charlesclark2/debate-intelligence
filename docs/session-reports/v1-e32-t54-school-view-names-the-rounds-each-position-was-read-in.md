# Session report: v1-e32-t54-school-view-names-the-rounds-each-position-was-read-in

| | |
|---|---|
| Task | `v1-e32-t54-school-view-names-the-rounds-each-position-was-read-in` — The per-school view names, under each position, the rounds whose disclosed file holds it |
| Spec | [`plan_specs/v1/e32-argument-landscape/t54-school-view-names-the-rounds-each-position-was-read-in.yaml`](../../plan_specs/v1/e32-argument-landscape/t54-school-view-names-the-rounds-each-position-was-read-in.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t54-school-view-names-the-rounds-each-position-was-read-in` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Under policy 1.23, `schools.md` now lists each team's rounds under each of its positions, beneath its
school's table. The page and the pilot's per-school page each show:

- the positions the team reads, in the table's order, then the positions it only answers, marked
  *(answers only)*;
- one line per round, newest snapshot first;
- on each line, the tournament and round as disclosed, the side, `reads` or `AT`, and "one file for N
  rounds" when the file holding the position was disclosed for several of that team's rounds.

`school_rounds.csv` holds the same lines, one row each, with the ruled columns. `schools.csv` is
unchanged. The new file is a school-view file everywhere one is reached: the removal's deletion,
`caselist status`'s residue count, the bundle scan's exclusions, the annual purge and the season
window (Step 2), and the removal credential's grant. The circuit-wide files are byte for byte what
they were.

The PM should look first at two things:

- **The removal credential's grant.** The grant had to name the new file, which takes the change
  outside the spec's packages (Deviations). `evidence-store.md` still records `v1-e32-t13`'s grant
  as not applied in either environment (Operator follow-ups).
- **The page-size margin.** The largest real school page fits ADR-0019's 150 KB, with about 5 KB
  (50 to 76 round lines) to spare. That is about one snapshot at the season's rate. The PM ruled to
  ship as built and filed the collapsed view as a p1 follow-up (Operator follow-ups, item 1).

ac3 is the operator's republish after the merge, so the Goal stays `InProgress`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `school-view-names-the-rounds-each-positi` (Rounds per position) | Done | Counted and ruled first (ac1). Tests were run red against stubs, the code built to the PM's ruling of 2026-11-06, then 22 mutants. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts and the page's shape sent to the PM and ruled on before the build | PASS | The operator ran the count script over `~/.debate-research/landscape-copy-hspolicy26` (counts only; 0 copy files changed or removed; 65.9 s). The counts and a Maple Grove / QX example went to the PM, who ruled on 2026-11-06: accepted, with Q1 (a) and Q2 to Q4 as proposed, plus the order rules. See **The counts** below. |
| ac2: the view, its page and school_rounds.csv list positions with rounds, stance and side; a file for several rounds marked; the new file reached by removal, purge, season window, status and scan; tests on synthetic stores shown failing first | PASS | Red run at `81271d1` (types and an empty renderer): **54 failed, 402 passed**, each failure for its own reason (below). Green after the build: the same 8 files plus `test_landscape_scan.py`, **470 passed**. After the rebase onto `380c020`: the 89 affected files nearest the change, **1,777 passed**, and both smoke tests, **7 passed**. Mutants: 22 run, all caught once one test was tightened (below). |
| ac3: the operator republishes the hspolicy26 report after the merge, and the PM records it | NOT RUN | Operator, after the merge: the last section of this report. |
| Node: `uv run pytest packages/debate_core/tests -k "school and round"` | PASS | **40 passed** in 54.7 s. |

**What each test proves, on synthetic stores:**

- **The round lines** (`packages/debate_core/tests/application/test_landscape_schools.py`):
  - the synthetic caselist's 36 lines, worked out by hand from the fixture's table (`EXPECTED_ROUNDS`);
  - the reads add up to the rows;
  - shuffled inputs give the same lines;
  - an assigned aff is held by every file of its round.
- **The hand-built rounds, all invented names**, covering:
  - the PM's order: newest snapshot, then case-folded tournament, then elims before prelims, a
    higher prelim before a lower one, and an unrecognised label after those;
  - a missing tournament or round sorting last;
  - the mark, counted by this team's rounds alone and only from files that hold the position;
  - read positions in row order, then answered ones;
  - no line for a round by no team or on no side;
  - the commonest spelling, with ties going to the first in text order.
- **The renderer** (`packages/debate_core/tests/arguments/landscape/test_render.py`):
  - golden `schools.md` and a new golden `school_rounds.csv`, both written by hand from that table;
  - the CSV's columns, and a sample row;
  - escaping of a label that would start a list or emphasis;
  - a school whose teams only answer;
  - tournaments appearing in `schools.md` and `school_rounds.csv` and nowhere else, `schools.csv` and
    the circuit-wide files included;
  - no tag or cite in any school-view file;
  - the scan taking `school_rounds.csv` as a school view, while the same lines under a circuit-wide
    name are hits.
- **The pilot page** (`packages/debate_api/tests/test_landscape_pages.py`): `schools.md` as
  `debate_core` renders it, served by the pilot, puts the lists on the school's own page. The front
  page lists the four schools and no team.
- **The page budget** (same file, after the operator's measurement): the synthetic bundle's largest
  school now carries hspolicy26's largest school page: 151 rows and 1,158 round lines, with a body of
  at least 121,739 bytes (122,605 rendered). The test checks all three and holds the page, script and
  stylesheet under 150 KB: **149,208 bytes of 153,600**. Two longer drafts of the same lines (bodies
  of 154,267 and 135,067 bytes) failed on the budget assertion itself, at 180,870 and 161,670 bytes.
  The file then ran **148 passed**.
- **The removal, the residue count and the purge:**
  - `test_removal_reaches_landscape_school_views.py`: the bundles carry the eight files; the plan
    lists and `--execute` deletes all three school-view files on both sides, every version; the
    residue count is 6 per side.
  - `test_removal_school_view_selection.py`: `is_school_view` takes `school_rounds.csv`, and the
    grant names it.
  - `tests/docs/test_annual_purge_runbook.py`: the runbook's own Step 2 script deletes an aged-out
    `school_rounds.csv`, every version, and keeps one inside the window.
  - `tests/smoke/test_caselist_remove_smoke.py`: the installed build deletes 6 local files and 6
    bucket versions.
- **The Terraform grant** (`infrastructure/modules/evidence_bucket`): `terraform test`, offline
  through the provider mirror, ran in scratch copies. With the old grant it gave **14 passed, 1
  failed** (two assertions in `removal_permission_set_deletes_disclosed_material_and_nothing_else`).
  With the new grant, **15 passed**. `terraform fmt -check` and tflint are clean.

**Why the red run failed** (54 failures, by file, from the run's own output):

| File | Failures | Why |
|---|---|---|
| `test_removal_reaches_landscape_school_views.py` | 13 | `UnknownLandscapeFile` on `school_rounds.csv`: the removal stops on a file it cannot place |
| `test_removal_school_view_selection.py` | 2 | The same error for the key; `school_view_files` in the Terraform lacks the name |
| `test_landscape_schools.py` | 10 | The round lines are `[]` |
| `test_render.py` | 10 | `KeyError: 'school_rounds.csv'`, the golden `schools.md` differing, the file missing from `SCHOOL_VIEW_FILES`, and no tournament in the school view |
| `test_landscape_command.py` | 16 | The bundle's seven files where the pins name eight: marks, help, docstring, "Wrote 8 files", publish keys |
| `test_landscape_run.py` | 1 | The seven files where eight are pinned |
| `test_landscape_pages.py` | 1 | No round list on the school page |
| `test_annual_purge_runbook.py` | 1 | Step 2's `STOP: … school_rounds.csv is neither a school view nor a circuit-wide file` |

Two of the `test_landscape_schools.py` failures were first a `ValidationError` from my own invalid
digest prefixes (`g1`, `h1`). I fixed those, and both then failed for their own reason (`assert [] ==
…`).

**Mutants.** Each was applied in the worktree, run against the school-view, render and page tests,
and restored with `git checkout HEAD --`. All 20 of the first batch were caught except one: replacing
the commonest spelling with `max()`. It survived because the commonest spelling also sorted last. I
rewrote that test so the commonest spelling sorts first, and added a tie case. Then `max()` and a
count-only `max` were both caught. The others caught were:

- elims after prelims;
- a lower prelim first;
- unrecognised labels first;
- oldest snapshot first;
- the tournament not case-folded;
- no-tournament rounds first;
- the mark counting every team's rounds;
- the mark ignoring which files hold the position;
- the mark taking the smallest file;
- an answer beating a read;
- answered positions by id alone (caught once that test was tightened in `9dfa3b3`);
- read positions by id rather than row order;
- rounds on no side listed;
- ANSWERS cards giving no answer;
- other-side reads giving no answer;
- no marker escape;
- *(answers only)* dropped;
- a one-round file marked;
- team lines written as headings.

**The affected set** is 370 of 713 test files (from 35 changed files, after the rebase). A bounded
run reached 19% in 115 s with no failure, so the whole set takes about 8 minutes. As the working
agreement says, it is left to the pull request's CI. I ran these myself:

- the 89 affected files whose paths name the landscape, school views, removal, status, the purge or
  the scan;
- both smoke tests;
- `ruff check` and `ruff format --check` (whole repo);
- `pyright` on the three packages: 0 errors;
- `lint-imports`: 20 kept;
- `check_thin_handlers.py`, `docs_index.py --check-descriptions`, `check_links.py` and
  `check_command_blocks.py --base origin/dev`: all OK;
- `validate_specs.py`: OK.

### The counts (ac1, hspolicy26 through 2026-11-03, 17 snapshots, counts only)

| | |
|---|---|
| Disclosures in range / in the newest snapshot | 6,863 / 1,106 |
| No round label, no tournament, no team, no readable side | 0 each |
| Round labels not recognised | 148 in range, **15 in the newest snapshot**; shown as disclosed and not flagged, as the PM ruled |
| Files disclosed by one team for more than one round | 521 of 5,132 (2 rounds: 383; 3: 91; 4-5: 35; 6+: 12; at most 8). Of these, 359 hold a placed card |
| Files disclosed by more than one team | 50 |
| Positions per team | read: median 3, max 26 (591 teams); read or answered: median 5, max 52 (610 teams) |
| Rounds per team and position | median 2; max 26 reads, 36 counting AT |
| Lines per team | median 10, max 257, counting positions answered only |
| Rounds that both read and answer one position | 0 |
| Rounds with two or more files holding the position | 90 |

## Files changed

- **`packages/debate_core`**
  - **domain:** `landscape_schools` gains `RoundStance`, `SchoolRound` and `SchoolView.round_lines`.
  - **application:**
    - `landscape_counts`: `CountedReads.answers` and `holding`.
    - `landscape_report`: the count records the answering rounds and the files holding each
      placement; the bundle writes `school_rounds.csv`.
    - `landscape_schools`: the round lines, in the ruled order.
    - `landscape_bundle_files`: `SCHOOL_VIEW_FILES` gains `school_rounds.csv`.
    - `landscape_run`: `BUNDLE_FILES` holds eight files.
    - `landscape_scan` and `removal_plan`: the text names the new file.
  - **arguments:** `render.py` writes the round lists, the **Round lines** header row, the lead
    paragraph and `render_school_rounds_csv`.
- **`packages/debate_cli`:** the `landscape`, `caselist` and `caselist remove` docstrings and help
  name the eight files. The marks come from `SCHOOL_VIEW_FILES`.
- **Tests:**
  - `packages/debate_core/tests`, `packages/debate_cli/tests` and `packages/debate_api/tests`: new
    and updated tests, as above.
  - `tests/fixtures/landscape/golden/`: `schools.md` and the new `school_rounds.csv`.
  - `tests/docs/test_annual_purge_runbook.py`, and in `tests/smoke/`: `test_landscape_smoke.py`,
    `test_caselist_remove_smoke.py` and `README.md`.
- **`infrastructure/modules/evidence_bucket`:** `operator_access.tf` lists `school_rounds.csv` in
  `school_view_files`; `tests/evidence_bucket.tftest.hcl` updates its three assertions.
- **`docs/runbooks`:**
  - `annual-purge.md`: Step 2's set and its success text.
  - `caselist-removal.md`: the three files.
  - `evidence-store.md`: a **Later applies** row.
  - `landscape-report-from-the-cloud-run.md`: eight planned and uploaded files.
- **`docs/guides/landscape-taxonomy.md`:** a **Round by round** paragraph.

## Deviations from the spec

1. **Files outside `constraints.packages`.** The spec's own criteria need the purge, the season
   window, the removal and the smoke checks to reach the new file, and their tests and grant live
   outside the listed packages:
   - `infrastructure/modules/evidence_bucket/operator_access.tf` and its `tftest.hcl`. A removal's
     `--execute` deletes in the bucket under the removal credential, whose inline policy names the
     school-view files one by one. Without the new name, a takedown would be refused on
     `school_rounds.csv`, and `test_removal_school_view_selection.py` pins the two lists together.
   - `tests/docs/test_annual_purge_runbook.py`: the purge and the season window are that runbook's
     Step 2, and its script is tested there.
   - `tests/smoke/` (two tests and the README) and `tests/fixtures/landscape/golden/`: they pin the
     bundle's files and the golden school view.

   The spec's `constraints.packages` may want `infrastructure/modules/evidence_bucket`, `tests/docs`,
   `tests/smoke` and `tests/fixtures/landscape` added; that is the PM's to amend.
   The PM approved the grant file being outside the task's packages on 2026-11-06.
2. **The grant needs an apply.** The code reaches the new file at once. The bucket deletion by the
   removal credential needs the module applied in each environment (Operator follow-ups, item 2,
   which has dev's plan). Nothing in the spec named it.

## Decisions and assumptions

- **Stance.**
  - A line is `reads` when the report counts the round as reading the position.
  - It is `AT` when an ANSWERS card at or above the threshold sits in one of the round's files, or a
    READS card under a position of the other side does: the report's "counted as answers, not reads".
  - A round that does both is one `reads` line. hspolicy26 has none.
  - A READS card of an aff in a round `v1-e32-t09` assigned another aff is neither, as the report
    counts it.
  - An ANSWERS card under an unknown or retired position gives no line and refuses nothing
    (`_answered_position`). The report never counted answers, and refusing on them would newly stop
    a report.
- **Answered positions' order.** The PM ruled reads first, then answers. Among the answered I put
  most-answered first, then by id, mirroring the rows' order.
- **"Unrecognised label … in disclosed order".** I read this as the order of the label's own text,
  case-folded, so a week's page is the same whatever order the manifest listed files in. A week's
  disclosure order is not stable, which the ruling's aim (the same page every week) needs.
- **A missing tournament or round.** It shows as "no tournament disclosed" or "no round disclosed"
  and sorts after the others. None of the 6,863 disclosures in range lack either.
- **Spelling.** A round's tournament and label show the spelling most of its disclosures in range
  use, ties to the first in text order, as a team's name already does.
- **The mark.** N is the most of this team's rounds that one file holding the position is disclosed
  for. A round assigned its aff counts every file of the round for that aff.
- **The page.** Each team gets a bold line and nested bullets, never a heading: the pilot makes a
  page of every heading under "By school". A school whose teams only answer gets its heading and
  "No team of this school read a counted position." The header table gains **Round lines** (`36: 29
  reads, 7 AT` on the fixture). "By school" gains a lead paragraph saying how to read the lines, and
  the opening paragraph names what the page now shows.
- **`school_rounds.csv`'s header block** is the same metadata as `schools.csv`'s, with its own
  `shows=` line citing policy 1.23. Empty cells stand for a missing tournament or round, or for no
  team page.

## Operator follow-ups

1. **Before the merge: the page-size measurement.** This needs the copy, and the operator block is in
   this session's last message. It renders the real `schools.md` through the pilot's renderer and
   prints byte and line counts only.

   *Result (2026-11-06, snapshot 2026-11-03).* Exit 0, 79.0 s, no file in the copy changed, added or
   removed.

   | Figure | Value |
   |---|---|
   | Round lines | 16,000: 8,632 reads, 7,368 AT; 5,063 under positions answered only |
   | Lines marked "one file for N rounds" | 2,801, largest N 8 |
   | Lines with no tournament or no round | 0 and 0 |
   | Teams and schools with lines | 610 and 185 (the rows hold 591 and 180) |
   | Lines per team | median 10, max 257 |
   | `schools.md`, `schools.csv`, `school_rounds.csv` | 1,541,850, 262,065 and 2,193,663 bytes |
   | School pages | 185; one over 100 KB, none over 150 KB |
   | Largest five page bodies (bytes, rows, lines) | 121,739/151/1,158; 73,380/99/791; 67,795/101/569; 65,469/77/657; 64,380/77/633 |
   | Scan hits | 75 in all, counted before earlier acceptances apply, and not counted by file. The school-view files are scanned for paths only. The republish's dry run (step 3) lists any hit not yet accepted, and step 4's digest block covers it. |

   The pilot adds 26,603 bytes to a school page's body: 2,020 of page chrome and 24,583 of script and
   stylesheet, as measured on the synthetic page. So the largest real page is about **148,342 bytes of
   153,600**, which is 96.6% of the budget and leaves 5,258 bytes. The page-budget test now carries a
   school that large (Tests, "The page budget"). Nothing refuses an oversized page at run time; the
   budget is held by that test alone. A larger page would still be served, just slower to load on a
   Chromebook.

   **The PM's ruling (2026-11-06): (a).** Ship as built for this weekend. The collapsed view stays out
   of scope. The PM files it as a p1 follow-up, wanted before the hspolicy26 report is republished
   from the snapshot after the 2026-11-11 run. It includes a check at report time that names any school
   page over ADR-0019's budget, so such a page is never published silently. ADR-0019's figure stands.

   **How fast the largest page grows (an estimate).**
   - *Round lines per snapshot.* The page holds 1,158 round lines after 17 snapshots: **68.1 per
     snapshot** over the season. That is a season average. The lines of that one school were not
     counted snapshot by snapshot, so the recent rate may differ. `school_rounds.csv`'s `snapshot`
     column holds it, on the operator's machine.
   - *Bytes per round line.* Two figures, from the measured body of 121,739 bytes:
     - an upper bound of **105.1**, which counts the whole body as round lines (121,739 / 1,158);
     - an estimate of **69.4**, which takes out the table. In the pilot's renderer, a school-view
       table row costs 272.7 bytes (measured on an invented row with a team-page link) and the page's
       empty frame 198 bytes. That leaves (121,739 − 151 × 272.7 − 198) / 1,158 = 69.4 bytes per line,
       counting each line's share of the position and team lines.
   - *Room left.* 5,258 bytes is about **50 to 76 round lines**: 0.73 to 1.11 snapshots at the season
     average. So the snapshot after the 2026-11-11 run may be the first to take the page over, which
     is the PM's deadline for the collapsed view.

2. **The removal credential's grant, dev first, then prod before promotion item 9.**

   *Confirmed in this branch.* `infrastructure/modules/evidence_bucket/operator_access.tf` line 101
   reads `school_view_files = ["schools.csv", "school_rounds.csv", "schools.md"]`. In
   `test_removal_school_view_selection.py`, both
   `test_it_names_exactly_the_school_view_files_the_code_deletes` (the list equals
   `SCHOOL_VIEW_FILES`) and `test_it_grants_the_school_rounds_file_a_removal_deletes` pass. The file
   ran 22 passed on 2026-11-06. The PM approved the file being outside the task's packages
   (Deviation 1). This session ran no plan and no apply.

   *What is waiting.* `docs/runbooks/evidence-store.md`, **Later applies**, records `v1-e32-t13`'s
   statement as not applied in either environment, as well as this task's addition to it. Until both
   are applied, a `caselist remove --execute` that reaches a landscape bundle is refused in the
   bucket. That record also shows `v1-e40-t07`'s bucket-policy statement not applied in either
   environment. If that is still so, this plan shows the bucket policy too, and stops (below).

   *What the dev plan should show.* `Plan: 0 to add, 1 to change, 0 to destroy.`, and exactly one
   resource line: `module.evidence_store.aws_ssoadmin_permission_set_inline_policy.evidence_removal[0]
   will be updated in-place`. Nothing created, destroyed or replaced, and no account assignment or
   permission set. Inside that one inline policy:
   - the statement `DeleteLandscapeSchoolViews` allows exactly `s3:DeleteObject` and
     `s3:DeleteObjectVersion` on three ARNs, `arn:aws:s3:::debate-dev-evidence-a7508de8/reports/landscape/*/`
     followed by `schools.csv`, `school_rounds.csv` and `schools.md`, with no condition;
   - `ListEvidenceObjectVersionsForTakedown` gains at most the prefixes `reports/landscape/` and
     `reports/landscape/*`, and loses none;
   - no other statement changes.

   If `v1-e32-t13` really is unapplied, the statement and the two prefixes are new. If it was applied
   after all, the statement only gains `school_rounds.csv`. The checker below accepts either shape
   and says which it found. Any other change stops. It was tested on eight synthetic plan files:
   - both OK shapes print `PLAN OK`;
   - each of these prints `PLAN STOP`: a bucket-policy change alongside, a replace, a grant missing
     `school_rounds.csv`, another statement changing, the listing gaining `reports/`, and no change
     at all.

   *Its guards.* Never on a Wednesday, the cloud run's day. No `DEBATE_` variable set, no caselist
   pull or backfile import running, and no Terraform override. The checkout must be on `origin/dev`
   with this task merged. It must hold the `owner.auto.tfvars` of the checkout that last applied dev:
   without it, the plan proposes destroying every account assignment. The plan runs as
   `debate-admin`, as evidence-store.md Step 3 does, and is saved to a file so that what is applied is
   what the PM read.

   **The PM reads the plan and the checker's line before any apply, dev first.** The apply, and
   prod's plan and apply (the same blocks with `ENVIRONMENT=prod` and `debate-prod-evidence-a7508de8`),
   come after the PM's word. Prod's apply comes before promotion item 9 (`v1-e39-t07`'s prod removal
   exercise, [evidence-search.md](../runbooks/evidence-search.md)). After each apply, the record's
   `v1-e32-t13` and `v1-e32-t54` rows in evidence-store.md take that day's date.

   **Operator command, the checkout** (expected runtime a few seconds)
   Where: your Mac, in a new terminal window, after this task has merged into `dev`. Replace
   `/path/to/your/apply/checkout` with the checkout that last applied dev, the one holding its
   `owner.auto.tfvars`.
   ```bash
   WT=/path/to/your/apply/checkout
   ENVIRONMENT=dev
   BUCKET="debate-${ENVIRONMENT}-evidence-a7508de8"
   cd "$WT" || echo "WT does not exist: $WT"
   git fetch origin
   git switch --detach origin/dev
   grep -c '^  school_view_files = \["schools.csv", "school_rounds.csv", "schools.md"\]' infrastructure/modules/evidence_bucket/operator_access.tf
   grep -c -E '^(evidence_operator_user_names|evidence_removal_user_names) ' "infrastructure/envs/${ENVIRONMENT}/owner.auto.tfvars"
   date +%A
   ```
   Success looks like `1` (this task is in the checkout), `2` (the file names the evidence operator
   and the removal user) and a day that is not Wednesday. On a `0`, stop. On a `0` or `1` on the
   second line, copy the tfvars from the checkout that last applied dev, and do not plan.

   **Operator command, sign in** (expected runtime ~1 min)
   Where: your Mac, the same window
   ```bash
   aws sso login --sso-session debate
   aws sts get-caller-identity --profile debate-admin --query Arn --output text
   ```
   Success looks like an ARN containing `AWSReservedSSO_DebateBreakGlassAdmin`.

   **Operator command, the plan** (expected runtime ~2 min; plans only, applies nothing)
   Where: your Mac, the same window
   ```bash
   cd "$WT"
   if [ "$(date +%A)" = "Wednesday" ]; then echo "STOP: it is Wednesday, the cloud run's day; plan on another day"; elif env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set in this shell; open a new window"; elif pgrep -fl 'debate-research( --json)? caselist (pull|backfile-import)'; then echo "STOP: a caselist pull or backfile import is running on this Mac (above)"; elif env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" init -input=false >/dev/null && AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" plan -input=false -no-color -out=school-rounds-grant.tfplan | tee "/tmp/school-rounds-grant-${ENVIRONMENT}-plan.txt" | tail -5; fi
   grep -E '^Plan:|must be replaced|will be destroyed|will be created' "/tmp/school-rounds-grant-${ENVIRONMENT}-plan.txt"
   grep -E '^  # ' "/tmp/school-rounds-grant-${ENVIRONMENT}-plan.txt"
   ```
   Success looks like `Plan: 0 to add, 1 to change, 0 to destroy.`, with no line saying that a
   resource is replaced, destroyed or created. Then exactly one resource line, for
   `module.evidence_store.aws_ssoadmin_permission_set_inline_policy.evidence_removal[0]`, updated in
   place. No `Plan:` line at all means the plan failed: read the end of the file.

   **Operator command, the plan checked against that shape** (expected runtime a few seconds)
   Where: your Mac, the same window
   ```bash
   cd "$WT"
   AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" show -json school-rounds-grant.tfplan > "/tmp/school-rounds-grant-${ENVIRONMENT}-plan.json"
   python3 -I - "/tmp/school-rounds-grant-${ENVIRONMENT}-plan.json" "$BUCKET" <<'GRANTPLAN'
   import json, sys
   plan = json.load(open(sys.argv[1]))
   bucket = sys.argv[2]
   target = "module.evidence_store.aws_ssoadmin_permission_set_inline_policy.evidence_removal[0]"
   views = sorted("arn:aws:s3:::" + bucket + "/reports/landscape/*/" + name for name in ("schools.csv", "school_rounds.csv", "schools.md"))
   listing, deleting = "ListEvidenceObjectVersionsForTakedown", "DeleteLandscapeSchoolViews"
   landscape = {"reports/landscape/", "reports/landscape/*"}
   def as_list(value):
       return sorted(value) if isinstance(value, list) else [value]
   def by_sid(policy):
       return {s.get("Sid"): s for s in json.loads(policy or "{}").get("Statement", [])}
   def prefixes(statement):
       return set(as_list(((statement or {}).get("Condition") or {}).get("StringLike", {}).get("s3:prefix", [])))
   def without_prefixes(statement):
       copy = json.loads(json.dumps(statement or {}))
       copy.get("Condition", {}).get("StringLike", {}).pop("s3:prefix", None)
       return copy
   changes = [c for c in plan.get("resource_changes", []) if c["change"]["actions"] not in (["no-op"], ["read"])]
   problems, shape = [], ""
   others = sorted(c["address"] + " " + "/".join(c["change"]["actions"]) for c in changes if c["address"] != target)
   if others:
       problems.append("changes other than the removal set's inline policy: " + str(others))
   found = [c["change"] for c in changes if c["address"] == target]
   if not found:
       problems.append("the removal set's inline policy does not change: is v1-e32-t54 merged in this checkout, or applied already?")
   for change in found:
       if change["actions"] != ["update"]:
           problems.append(target + " is " + "/".join(change["actions"]) + ", expected an update in place")
       before, after = change["before"] or {}, change["after"] or {}
       unknown = change.get("after_unknown") or {}
       changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k) or unknown.get(k))
       if changed != ["inline_policy"]:
           problems.append(target + " changes " + str(changed) + ", expected only inline_policy")
           continue
       old, new = by_sid(before.get("inline_policy")), by_sid(after.get("inline_policy"))
       for sid in sorted(set(old) | set(new), key=str):
           if sid not in (listing, deleting) and old.get(sid) != new.get(sid):
               problems.append("statement " + str(sid) + " changes too")
       grant = new.get(deleting) or {}
       if (grant.get("Effect"), as_list(grant.get("Action")), as_list(grant.get("Resource")), "Condition" in grant) != ("Allow", ["s3:DeleteObject", "s3:DeleteObjectVersion"], views, False):
           problems.append(deleting + " is not exactly the delete of the three school-view files: " + json.dumps(grant, sort_keys=True))
       gained, lost = prefixes(new.get(listing)) - prefixes(old.get(listing)), prefixes(old.get(listing)) - prefixes(new.get(listing))
       if lost or not gained <= landscape or without_prefixes(old.get(listing)) != without_prefixes(new.get(listing)):
           problems.append(listing + " changes beyond gaining the landscape prefix: lost " + str(sorted(lost)) + ", gained " + str(sorted(gained)))
       if deleting in old:
           shape = "school_rounds.csv added to v1-e32-t13's statement, which was applied already"
       else:
           shape = "v1-e32-t13's statement and listing prefix arrive with it, as evidence-store.md's record says"
   if problems:
       print("PLAN STOP: " + "; ".join(problems))
   else:
       print("PLAN OK: 0 to add, 1 to change, 0 to destroy; only the removal set's inline policy changes, in place; " + shape)
       print(json.dumps({"before": old.get(deleting), "after": new.get(deleting), "listing prefixes gained": sorted(gained)}, indent=2, sort_keys=True))
   GRANTPLAN
   ```
   Success looks like a `PLAN OK: 0 to add, 1 to change, 0 to destroy; …` line that names the shape
   it found, followed by the `DeleteLandscapeSchoolViews` statement before and after. Send the PM the
   `PLAN` line and `/tmp/school-rounds-grant-dev-plan.txt`, and wait for the PM's word before applying.
   **A `PLAN STOP` line, or any other resource in the plan, stops everything.** Never apply that plan;
   send the line and the plan to the PM. The usual causes are:
   - `v1-e40-t07`'s bucket policy still waiting for its own apply, which the PM sequences;
   - an `owner.auto.tfvars` that is not the one the last apply used.

## Follow-up work

- **A collapsed view for long teams** (v1-e32, p1, filed by the PM): one team has 257 lines, and the
  median is 10. The largest school page is at 96.6% of the page budget, which is 50 to 76 round
  lines of room against 68.1 a snapshot (Operator follow-ups, item 1). It is wanted before the
  hspolicy26 report is republished from the snapshot after the 2026-11-11 run, with a check at report
  time that names any school page over ADR-0019's budget.
- **Filters on the pilot's school page** (v1-e39 or v1-e32): by side, stance or tournament. The PM
  ruled both of these out of scope for this weekend.
- **The spec's `constraints.packages`** (this spec): see Deviation 1.

## The republish (ac3), after the merge

Steps 3 and 4 of [landscape-report-from-the-cloud-run.md](../runbooks/landscape-report-from-the-cloud-run.md),
over the existing copy, run from the main clone with `uv run`. Step 5, deleting the copy, is the
PM's. Run all three blocks in one terminal window.

**Operator command** (expected runtime a few seconds; pulls the main clone on `dev`, checks it carries this task)
Where: your Mac, in a new terminal window
```bash
CASELIST=hspolicy26
COPY="$HOME/.debate-research/landscape-copy-${CASELIST}"
MAIN="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence"
CFG="$MAIN/config/landscape"
if [ "$(git -C "$MAIN" branch --show-current)" != dev ]; then echo "STOP: ${MAIN} is not on dev"; elif [ ! -f "$COPY/debate-research-restored-copy.json" ]; then echo "STOP: ${COPY} holds no debate-research-restored-copy.json"; else git -C "$MAIN" pull --ff-only && git -C "$MAIN" grep -c school_rounds.csv HEAD -- packages/debate_core/src/debate_core/application/landscape_bundle_files.py; grep -c -E "caselist: ${CASELIST}\$" "$CFG/topics.yaml"; date +%A; fi
```
Success looks like the pull's summary, then a count of 1 or more (the clone carries this task), a
count of `1` (the topic), and a day that is not Wednesday.

**Operator command** (expected runtime ~5 to 12 min; the dry run, writing only the text caches in your data directory)
Where: your Mac, in the same window
```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif [ ! -f "$COPY/debate-research-restored-copy.json" ]; then echo "STOP: ${COPY} holds no debate-research-restored-copy.json"; elif [ ! -f "$CFG/topics.yaml" ]; then echo "STOP: no topics.yaml in ${CFG}"; elif ! git -C "$MAIN" grep -q school_rounds.csv HEAD -- packages/debate_core/src/debate_core/application/landscape_bundle_files.py; then echo "STOP: ${MAIN} does not carry v1-e32-t54"; else aws sso login --profile debate-dev-evidence && cd "$MAIN" && caffeinate -i env DEBATE_ENV=dev uv run debate-research --json landscape report --caselist "$CASELIST" --restored-copy "$COPY" --config-dir "$CFG" --model-mode none --publish --dry-run > /tmp/landscape-dry-run.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); d = e.get("data") or (e.get("error") or {}).get("details") or {}; c = d.get("counts") or {}; m = (d.get("classification") or {}).get("model") or {}; s = d.get("scan") or {}; print("code", (e.get("error") or {}).get("code")); print("snapshot", d.get("snapshot"), "parsed_version", d.get("parsed_version"), "stale", (d.get("staleness") or {}).get("stale")); print("sources", c.get("sources"), "cards", c.get("cards"), "counted", c.get("cards_counted"), "positions", c.get("positions")); print("would_ask", m.get("would_ask"), "held_back", m.get("held_back"), "model_calls", d.get("model_calls")); print("scan_hits", len(s.get("hits") or []), "not_yet_accepted", s.get("not_yet_accepted"), "digest", s.get("digest")); print("planned", [one["action"] for one in (d.get("publish") or {}).get("planned") or []]); print("school_view", d.get("school_view"))' /tmp/landscape-dry-run.json; fi
```
Success looks like:

- `exit 0` and `code None`;
- `snapshot 2026-11-03` and `stale False`;
- `would_ask 0` and `model_calls 0`;
- `not_yet_accepted 0`;
- `planned` with eight entries: `UPLOAD` for at least `school_rounds.csv` and `schools.md`,
  `UNCHANGED` or `UPLOAD` for the rest;
- `school_view` with 591 team codes.

**Stop and send the PM the lines** on `PARSED_VERSION_NOT_IN_STORE` (dev's parser changed since the
copy was parsed; run step 2 again), on `stale True`, or on `not_yet_accepted` above zero (step 3's
reading block; the lines are for the terminal only).

**Operator command** (expected runtime a few minutes; publishes to the dev bucket under the run lock)
Where: your Mac, in the same window, after the PM has read the dry run's lines
```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif [ ! -f "$COPY/debate-research-restored-copy.json" ]; then echo "STOP: ${COPY} holds no debate-research-restored-copy.json"; elif [ ! -f "$CFG/topics.yaml" ]; then echo "STOP: no topics.yaml in ${CFG}"; elif ! git -C "$MAIN" grep -q school_rounds.csv HEAD -- packages/debate_core/src/debate_core/application/landscape_bundle_files.py; then echo "STOP: ${MAIN} does not carry v1-e32-t54"; else aws sso login --profile debate-dev-evidence && cd "$MAIN" && caffeinate -i env DEBATE_ENV=dev uv run debate-research --json landscape report --caselist "$CASELIST" --restored-copy "$COPY" --config-dir "$CFG" --model-mode none --publish > /tmp/landscape-publish.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); d = e.get("data") or (e.get("error") or {}).get("details") or {}; p = d.get("publish") or {}; print("code", (e.get("error") or {}).get("code")); print("snapshot", d.get("snapshot"), "model_calls", d.get("model_calls"), "cards", (d.get("counts") or {}).get("cards")); print("uploaded", len(p.get("uploaded") or []), "unchanged", len(p.get("unchanged") or []), "refused", p.get("refused"))' /tmp/landscape-publish.json; fi
```
Success looks like:

- `exit 0` and `code None`;
- the dry run's `snapshot` and `cards`;
- `model_calls 0`;
- `uploaded` plus `unchanged` equal to 8, with `uploaded` 2 or more.

`RUN_LOCK_HELD` means a run holds the lock: wait, then run the block again. A scan refusal is step
4's digest block in the runbook. Then the pilot's school pages show the round lists the next time the
shelf reads the bucket.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

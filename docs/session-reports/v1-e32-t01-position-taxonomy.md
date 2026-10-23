# Session report: v1-e32-t01-position-taxonomy

| | |
|---|---|
| Task | `v1-e32-t01-position-taxonomy` — Topic position taxonomies |
| Spec | [`plan_specs/v1/e32-argument-landscape/t01-position-taxonomy.yaml`](../../plan_specs/v1/e32-argument-landscape/t01-position-taxonomy.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t01-position-taxonomy` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

All five plan nodes' code and files are done and every machine-checked criterion passes. What is
still open is the coach's review and approval of the drafted Policy taxonomy at 1.0.0 (ac5's
second half, and the seed-and-curate node's custom criterion). So the Goal stays **InProgress**:
the review can go ahead with those two criteria open. The work is the taxonomy and topic-map models
(`debate_core.domain.landscape`), a `TaxonomyRepository` port with a YAML adapter, a pure heading
normalizer and seeding function in a new `debate_core.arguments` layer, a store reader in the
application layer, `scripts/seed_landscape_taxonomy.py`, `config/landscape/` (topics.yaml, a
54-position Policy NHI draft and a 19-position generic.yaml), the config test and the coach's
guide. The seeding run was read-only and took under a minute, so I ran it myself with the PM's
guards rather than handing it over (Deviations 3). The store disagrees with the coach's prep on
affs: `single payer` is the only plan the headings name (137 teams), with no heading for Medicare
for All or an ACA expansion. The review sheet says so in counts. **Look first at** Deviations 2
(the store holds no sections, so the level is certain only on a full path) and the CSV privacy
note under Decisions 6.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| taxonomy-models | Done | `domain/landscape.py`; red run against a skeleton that refused nothing: 30 failed, 39 passed |
| yaml-repository | Done | `application/ports/taxonomy_repository.py`, `integrations/landscape/yaml_taxonomy_repository.py`; red run: 13 failed, 9 passed |
| heading-normalizer | Done | `arguments/landscape/headings.py` and `seeding.py`, `application/landscape_seeding.py`, `scripts/seed_landscape_taxonomy.py`. Every strip rule's case was shown failing first, across five red runs (below) |
| seed-and-curate | Partial | Seeded (counts below); `topics.yaml`, `policy-2026-27-nhi.yaml` and `generic.yaml` drafted from the CSV; review sheet written. **Coach review not yet done** |
| coach-guide | Done | `docs/guides/landscape-taxonomy.md`; pyright and lint-imports pass |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: models (extra=forbid) load every taxonomy file and refuse duplicate ids, unknown parents, cycles, a merge into nothing, an alias two positions claim | PASS | `uv run pytest packages/debate_core/tests/domain/test_landscape_taxonomy.py` → 69 passed; `tests/config/test_landscape_taxonomies.py` loads every committed file → 17 passed |
| ac2: topics.yaml resolves (caselist, snapshot) to one topic and a semver taxonomy_version; overlapping ranges fail | PASS | domain tests (overlap within and across topics, adjacent ranges, both ends inclusive) and `uv run pytest packages/debate_core/tests/integrations/landscape/test_yaml_taxonomy_repository.py` → 22 passed. On the committed file: hspolicy26 on 2026-11-07 → `policy-2026-27-nhi` 1.0.0; hsld26 on 2026-10-01 → the Sept–Oct LD topic, no taxonomy; hsld26 on 2026-11-07 → none |
| ac3: the Policy taxonomy and generic.yaml exist, each with at least 12 active positions, each with kind and side | PASS | 54 and 19 active positions; `test_each_taxonomy_has_enough_active_positions_each_with_a_kind_and_a_side` passes for both |
| ac4: deterministic seeding writes a candidates CSV (normalized heading, level, documents, distinct teams, suggested id), stripping round prefixes, numbering and AT/A2 | PASS | `uv run pytest packages/debate_core/tests/arguments/landscape/test_headings.py` → 157 passed; `test_seeding.py` 49 passed; `tests/scripts/test_seed_landscape_taxonomy.py` 6 passed, whose CSV and counts were written by hand from the planted sources (working agreement 6). Real run below |
| ac5: guide explains add position, add alias, retire/merge, bump taxonomy_version; **and the coach has reviewed the seeded Policy file and generic.yaml** | NOT RUN (guide part PASS) | Guide: `docs/guides/landscape-taxonomy.md` covers all four, with worked examples (add alias, add position, split a DA, merge two K labels). The coach's review has not happened yet: the sheet is ready for him (Operator follow-ups) |
| taxonomy-models: Taxonomy model validation tests pass | PASS | 69 passed (above) |
| yaml-repository: repository and topic-resolution tests pass | PASS | 22 passed (above) |
| heading-normalizer: normalizer and seeding tests pass on synthetic parsed-store fixtures | PASS | 157 passed (above); every fixture is invented (`School One`/`CodeOne`, `Sample Squad`, `Harbor Classic`) |
| seed-and-curate: topic map lists the Policy caselist | PASS | `config/landscape/topics.yaml` contains `hspolicy26` |
| seed-and-curate: every committed taxonomy file validates and has no personal data | PASS | `uv run pytest tests/config/test_landscape_taxonomies.py` → 17 passed, including seven synthetic cases the personal-data check must refuse (a team-code-shaped alias `spending da qx`, a team-code tag keyword, `RiOs` and `QX` in labels, a name in a label, a school word in an alias and in a description) |
| seed-and-curate: coach curates the seeded taxonomies and approves 1.0.0 | NOT RUN | Waiting on the coach's review (Operator follow-ups). Counts of keep/merge/rename/drop/add go here when he has answered |
| coach-guide: guide exists and contains `merged_into` | PASS | 7 lines contain it; first line is its `docs-index` comment |
| coach-guide: `uv run pyright packages/debate_core` | PASS | 0 errors, 0 warnings |
| coach-guide: `uv run lint-imports` | PASS | 15 kept, 0 broken |

The pytest commands above were run as `.venv/bin/python -m pytest <file>` under `perl -e 'alarm 100'`
(the environment `uv run` uses, with the time limit on the interpreter, working agreement 10).

### Checks shown failing for their reason

* **Red runs, each against a skeleton or before the rule existed:** models 30 failed / 39 passed;
  repository 13 / 9; normalizer 82 / 31 (47 of 49 rule cases failing, the two passing being the
  skeleton's own case-fold and whitespace); then four more normalizer rounds as the real store
  showed shapes the synthetic cases had not (3, 14, 7 and 1 failing, each the new cases only); the
  reader's tournament name (1 failed); the caselist-name scrub (4 failed).
* **Seeding mutants**, six, each in a fresh process: teams counted per document instead of per
  identity (5 failed), the minimum-teams filter ignored (2), own names not stripped (1), an
  untagged card's open tag kept (1), level read from a shortened path (2), sides swapped (4). All
  caught. No Hypothesis is used in these tests.
* **Config plants** into the committed Policy file, restored byte for byte: a team-code-shaped
  alias failed the personal-data test; an alias no heading normalizes to failed the fixed-point
  test; an alias two positions claim failed the load (4 tests); a version topics.yaml does not name
  failed the load.
* **lint-imports:** the pre-edit pyproject breaks the layers contract with "debate_core.arguments
  not listed as a layer"; an `arguments → application` import planted in `headings.py` breaks it
  naming that import.
* **One near miss, recorded for what it teaches:** after the mutation run, the last mutant (the side
  swap, the same byte length as the original) stayed in `__pycache__`, because the byte-identical
  restore landed in the same second. The next run of a different suite tested the mutant. The
  script test's hand-written CSV caught it; the cache was cleared and the source checked unchanged.

### Seeding run (hspolicy26, parser `2026.10.20-docx-6`, the last of five runs)

| Count | Value |
|---|---|
| Source entries in the version directory | 3,869 |
| Parsed sources read, all on the topic (0 with no live disclosure in its range, 0 with no readable team) | 3,825 |
| Cards | 126,681 |
| Heading occurrences counted (one per normalized heading per document) | 33,373 |
| Distinct normalized headings | 8,577 |
| Left out, used by fewer than 2 teams | 6,231 |
| Candidate rows written | 2,346 |
| Runtime | 55.5 s wall (the five runs took 38.6 to 55.5 s) |
| Drafted: topic positions / aliases | 54 / 151 |
| Drafted: generic positions / aliases | 19 / 39 |
| Kept, merged, renamed, dropped, added by the coach | NOT RUN: waiting on his review |

The first run wrote 2,768 rows from 11,101 distinct headings. The four later runs followed normalizer
fixes for shapes the real headings showed (`OFF---1NC` was the commonest heading left), so the drafts
are built from the last run. Every drafted alias was checked by script against that CSV: present,
with at least two teams.

### Before the report (working agreement 10)

* `uv run scripts/affected_tests.py` listed 93 files; run with CI's markers under a 115 s limit, it
  was stopped by the limit (exit 142). So it is the pull request's `ci` check's to run.
* Within the limit instead, the changed modules' test directories, the always-run list and the
  docs checks: `packages/debate_core/tests/domain`, `.../integrations/landscape`, `.../arguments`,
  `.../application/test_landscape_seeding.py`, `tests/scripts/test_seed_landscape_taxonomy.py`,
  `tests/config`, `tests/architecture`, `tests/specs`, the CLI's `test_app.py` and
  `test_help_rendering.py`, `tests/docs`, `test_check_command_blocks.py`, `test_docs_index.py`
  → **1,565 passed in 20.4 s**.
* `uv run --frozen ruff format --check .` → 1147 files already formatted; `ruff check .` → all
  checks passed; `pyright packages/debate_core` → 0 errors; `lint-imports` → 15 kept, 0 broken;
  `scripts/check_thin_handlers.py` → 46 handlers within 25 statements; `scripts/check_command_blocks.py`
  → OK; `scripts/check_links.py` → OK; `scripts/docs_index.py --check-descriptions` → OK;
  `uv run scripts/validate_specs.py` → OK, 426 files.
* The pyproject edit came last, after the affected set was measured. It changes shared test ground,
  so the next `affected_tests.py` run will say the whole selection is affected.

## Files changed

* **`packages/debate_core/src/debate_core/domain/landscape.py`**: Position, Taxonomy, Topic,
  CaselistRange, TopicMap and their rules; generic positions merge into a topic by event.
* **`application/ports/taxonomy_repository.py`, `integrations/landscape/`**: the port and the YAML
  adapter, which checks the files as one configuration and refuses duplicate YAML keys.
* **`arguments/`** (new layer): `landscape/headings.py`, the normalizer; `landscape/seeding.py`,
  counting, suggested ids, the CSV and the review sheet.
* **`application/landscape_seeding.py`**: the reader that joins the parsed store with live manifest
  disclosures.
* **`testing/landscape_store.py`**: a synthetic caselist store, parsed sources plus manifests, shared
  by the reader's and the script's tests.
* **`scripts/seed_landscape_taxonomy.py`**: the `candidates` and `review` commands.
* **`config/landscape/`**: `topics.yaml`, `taxonomies/policy-2026-27-nhi.yaml`, `taxonomies/generic.yaml`.
* **Tests**: `tests/domain/test_landscape_taxonomy.py`, `tests/integrations/landscape/`,
  `tests/arguments/landscape/`, `tests/application/test_landscape_seeding.py` (all under
  `packages/debate_core`), `tests/scripts/test_seed_landscape_taxonomy.py`, `tests/config/`.
* **`docs/guides/landscape-taxonomy.md`**: the coach's guide.
* **`pyproject.toml`**: import-linter only. `debate_core.arguments` is placed beside evidence and
  retrieval in the layers contract (which is exhaustive, so a new subpackage fails until placed), and
  it and `debate_core.integrations.landscape` join the boto3, httpx, keyring, lxml and defusedxml
  lists; `arguments` also joins the delivery-framework list.

## Deviations from the spec

1. **Two files, not three.** The plan's description and the seed-and-curate node's name still say
   "the three topic files". Following the PM amendment of 2026-10-22: the Policy taxonomy and
   generic.yaml only. topics.yaml keeps the Sept–Oct LD and PF topics as ids and date ranges, with
   no resolution text and no taxonomy, and has nothing for November onward (v1-e32-t06).
2. **The store holds no FileSections.** The heading-normalizer node says seeding "reads FileSections
   from the parsed card store", but a stored document leaves `sections` out
   (`DocumentRecord`). Seeding reads each stored card's `section_path` instead. That path drops the
   levels a file skipped, so pocket/hat/block is certain only when the path has all three. A
   heading takes the level most of its documents show, or `unknown`. In a 300-source sample,
   two-thirds of cards sat under a full path. An untagged card's path can end with the tag still
   open above it, which is a claim, not a heading; seeding drops it when it matches a tag in the same
   document, and drops anything past the third level.
3. **I ran the seeding run myself.** seed-and-curate says "Operator-run". The run is read-only over
   the operator's files apart from the CSV the PM placed outside the repository, and I measured it
   first (a 300-source validated read projected 23 s). Working agreement 2 and the PM's own
   condition ("if the run may take over ~2 minutes") make it the session's. Each run kept the
   guards the PM set for the block: it stopped on any `DEBATE_*` variable or a running caselist pull,
   ran under a 115 s limit, and fails loudly on 0 sources or 0 candidates.
4. **Packages beyond `constraints.packages`.** The yaml-repository node's own output is in
   `debate_core.application` (the port). I also put the store reader in the application layer
   (`landscape_seeding.py`), because `arguments` must stay below `application` for t02 and t03
   to compose it, and their specs put application services over `arguments`. The synthetic store
   helper is in `debate_core.testing`, because two test trees share it and a shared suite cannot
   live under `tests/`. `pyproject.toml` changed for import-linter only. The PM may want
   `constraints.packages` amended to name `debate_core.application`, `debate_core.testing`,
   `pyproject.toml`, `docs/guides` and `tests/config`.
5. **More columns and more strip rules than ac4 lists.** The CSV also has `suggested_kind`,
   `cluster_teams` (distinct teams over every heading suggesting the same id), `answer`, `aff_teams`
   and `neg_teams`. Beyond round prefixes, numbering, AT/A2 and Off/Shell/Block, the normalizer
   strips trailing opponents (`vs`, `v.`), tournament and round segments (the PM's ruling 4),
   Frontlines/Extensions, T/L, versions, leading preliminary rounds, separators made of hyphen
   runs, and side-only segments. Each rule has a synthetic case that was shown failing first.

## Decisions and assumptions

1. **The season's range is mine to propose.** The amendment says "for the whole season". I wrote
   2026-07-01 to 2027-06-30: the store's first snapshot is 2026-07-07 and NSDA Nationals end in June.
   The review sheet asks the coach to confirm.
2. **One taxonomy version, written twice.** topics.yaml's `taxonomy_version` must equal the file's,
   and the repository refuses a mismatch, so a report always names the version it counted under. An
   edit to generic.yaml bumps its own version and every affected topic's (the guide says so).
3. **Aliases are written in normalized form**, checked twice: by the domain model's pattern, and by
   the config test, which requires every alias to be a fixed point of the normalizer and not an
   answer. So t02 can normalize a heading and look it up.
4. **Advantages are standalone**, with no parent: the CSV cannot show which aff a hat sits under.
   With single payer the only plan, the sheet asks the coach.
5. **Drafting choices for the coach to confirm**, all listed on the sheet: seven merges (econ and
   economy DA, IRS and IRS tradeoff DA, stocks and stock market DA, rates and interest rates DA,
   court clog and clog DA, cost and costs advantages, medical devices and devices DA); generic Ks,
   framework/T-USFG, politics DA, process CP and the theory shells in generic.yaml with `events:
   [POLICY]` only (LD-only positions stay out for t06); bare card-structure words (`costs`,
   `solvency`, `framework`) and the ambiguous `cp adv` left unplaced. `tag_keywords` are empty:
   seeding produces none, and writing some would be inventing them.
6. **What the CSV can still hold.** It has normalized headings and counts, and no path, file name,
   school or team-code field. Heading text is the teams' own writing, though. Seeding strips the
   disclosing team's school, code and tournament from its file's headings, and strips every school
   the caselist's paths name (with that school's codes where they stand beside it) from every
   heading. It also leaves out every heading fewer than two teams used. A school written in a short
   form its directory does not use, or a code standing away from its school's name, can still pass
   when two or more teams share the heading. A few low-count rows of that shape remain in the local
   CSV. The CSV stays under `~/Documents/debate/landscape-seed/`, the script refuses a path inside
   the repository, and nothing from it is committed. The committed files pass the personal-data
   check, and every alias in them was checked by hand as well.
7. **The id rule is documented, not enforced.** Nothing yet compares a taxonomy with its last
   released version to refuse a deleted or reused id (Follow-up work).

## Operator follow-ups

1. **Hand the coach the review sheet** (about an hour, by 2026-11-02):
   `~/Documents/debate/landscape-seed/policy-2026-27-nhi-review.md`. It opens with the decisions
   needed and his prep set against the store's counts, then lists each drafted position with its
   aliases and the counts behind them, then the 40 headings most teams use that no position claims.
   It holds real headings, so share it with him directly, not through a repository or a public link.
2. **Bring his answers back to this session** (`scripts/task resume v1-e32-t01-position-taxonomy`),
   as keep / rename / merge / drop / add per position and whether the season range is right. I will
   apply them to the two files, record the counts of each decision in this report, run the checks,
   and set the Goal to Succeeded once he approves 1.0.0.
3. No whole-selection run is handed over: the pull request's `ci` check runs it (working agreement 10).

## Follow-up work

* **Released ids, enforced** (E32, before the first report is published): a check that compares
  each taxonomy file with its version on `dev` and refuses a deleted or reused id. Today the guide
  says it and nothing enforces it.
* **Heading level from sections** (E31 or E32): with the stored path dropping skipped levels, a third
  of headings have no certain level. Storing each heading's unit in the card's path would settle it.
* **Short school forms in headings** (E32, t02): the matcher should treat a heading that names a
  school or tournament by a short form as unplaced rather than as a position. The two-team rule and
  the coach's review keep such headings out of the committed aliases for now.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED, with conditions closed in-session
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

Good work on a hard input:
* red runs for every layer, six seeding mutants caught, config plants;
* a normalizer driven by the real headings' shapes rather than guessed ones;
* every committed alias checked against the CSV with two or more teams.

The privacy handling of the CSV and the review sheet (Decisions 6) is right: local, outside the
repository, and refused by the script inside it.

**Deviations 1 to 5 and Decisions 1 to 7 are accepted.**
* Deviation 2 (no stored sections) is a real limit, and "certain only on a full path" is the
  honest way to say it.
* Deviation 3 is within the condition I set.
* Deviation 4's placement keeps `arguments` below `application`, which t02 and t03 need.

**Conditions, to close in this session before the PR:**

1. **Check the affirmative finding before the coach reads it.** The store showing `single payer`
   as the only plan, with no Medicare for All or ACA heading, is the most surprising thing here. It
   is also exactly what the team will act on.
   * Count, over all 8,577 distinct normalized headings including those under two teams (counts
     only, read-only, seconds): how many headings and distinct teams contain `m4a`, `medicare`,
     `mfa`, `aca`, `affordable care`, `obamacare`, `public option`, `subsid`, `medicaid` or
     `expansion`.
   * Also count how many of the 137 `single payer` teams' files hold a card-level tag or cite with
     "Medicare for All" in it, as a count of files.
   * Put the counts on the review sheet's first page. If teams write the Medicare for All aff as
     "single payer", the coach needs to know before he merges or renames anything.
2. **Apply the coach's review.** He reviews the sheet by 2026-11-02, sooner if he can.
   * Apply his keep, rename, merge, drop and add answers, and record the counts of each in this
     report.
   * Confirm the season range he gives, and set the Goal `Succeeded` when he approves 1.0.0.
   * If his answers need anything beyond edits to the two YAML files and the review sheet (a new
     kind, a model change, a normalizer rule), stop and ask for another review.
3. **Amend `constraints.packages` in the spec**, with a PM-ruling comment: `debate_core.application`,
   `debate_core.testing`, `pyproject.toml` (import-linter only), `docs/guides` and `tests/config`.
4. **Update the stale parts of this report** (Summary, the seed-and-curate row, ac5, the seeding
   table's last row). No new review is needed unless condition 2 says so.

**The PR:** opened without `--partial`, once the coach has approved and the Goal is `Succeeded`.
v1-e32-t02 depends on this task. If the coach cannot review by Sunday 2026-10-25, tell the PM: the
approval would then move to v1-e32-t05's first dev run, so that t02 and t03 (which use synthetic
fixtures) are not held up.

**Follow-up work:**
* Released ids, enforced: filed by the PM as an E32 task, due before t05's first published report.
* Heading level from sections: recorded and not filed now. It is filed if t02's matcher shows the
  unknown levels cost it.
* Short school forms in headings: added to v1-e32-t02's brief in the next PM batch.

If anything comes out differently, stop and ask for another review.

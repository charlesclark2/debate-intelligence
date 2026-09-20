# Session report: v1-e31-t01-cardmirror-evaluation

| | |
|---|---|
| Task | `v1-e31-t01-cardmirror-evaluation` — CardMirror evaluation and editor decision |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t01-cardmirror-evaluation.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t01-cardmirror-evaluation.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t01-cardmirror-evaluation` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The paper half of the spike is done and the tooling half is built and proven; the two halves that
need Charlie — the 25-file round-trip on his own files, and the decision itself — are not.
[`docs/architecture/cardmirror-evaluation.md`](../architecture/cardmirror-evaluation.md) maps every
CardMirror node and mark to our structural units and to the Verbatim style ids each side writes,
lists the public TypeScript API, records what is frozen and what is draft in the plugin API, names
the two features a Debate Decoded membership actually buys, and reviews PolyForm Noncommercial 1.0.0
use by use. All of it was read from the source at commit `bc92e6b` (CardMirror 1.11.0) or produced
by running that commit, not from CardMirror's marketing.

[`scripts/cardmirror-roundtrip/`](../../scripts/cardmirror-roundtrip/README.md) plus
[`scripts/compare_docx_roundtrip.py`](../../scripts/compare_docx_roundtrip.py) are the harness, and
they work end to end: this session round-tripped synthetic files through the real pinned CardMirror
and compared them. Those probes already produced the finding that matters most for t02 and t03 — a
heading expressed only as an outline level, without Verbatim's bold-and-size signature, is not
recognised as a heading, and a file with neither styles nor outline levels imports completely flat.
The real 25-file sample is the operator's to run; its section in the note is ready for the results.

[ADR-0014](../adr/0014-debate-file-editor.md) is drafted with the options, the evidence, the
consequences for every downstream task and the "never in CI" stance on the Node harness, and it is
`Proposed`, not `Accepted`: it asks Charlie two separate questions (is CardMirror a compatibility
target? is it the team's editor this season?) and has blanks for his answers. **The PM should look
first at the Decision section of the ADR and at the license verdict table in the note** — those are
the two places a human has to sign.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `schema-and-api-review` | Done | Read the schema, importer, exporter, style tables, plugin API reference and manual at the pinned commit; exercised pockets/hats/blocks/tags/cites/analytics/undertags through synthetic files rather than by hand in the app (see Deviations). |
| `license-review` | Partly done | The per-use verdict table and the three open questions for the author are written; Charlie's sign-off is pending. |
| `roundtrip-harness` | Done | `roundtrip.mjs`, a pinned `package.json` + `package-lock.json`, the README marking it operator-only, `compare_docx_roundtrip.py` and 26 tests. Verified against the real pinned CardMirror. |
| `roundtrip-run` | Not run | Operator-run on Charlie's Mac against files that must stay off this repository. Command block below. |
| `adr-0014` | Partly done | Drafted, indexed, and left `Proposed` for Charlie's decision. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1: node/mark mapping, public API list, plugin-bridge maturity, subscription-gated features | PASS | [`docs/architecture/cardmirror-evaluation.md`](../architecture/cardmirror-evaluation.md): "Schema mapping" tables cover all 21 node types and all 20 mark types in `src/schema/nodes.ts` and `src/schema/marks.ts` at `bc92e6b`; "Public TypeScript API" lists every export in `src/index.ts`; "Plugin bridge" records the DRAFT renderer API vs the FROZEN bridge handshake and HTTP routes; "Debate Decoded subscription" names card sharing and relay-backed co-editing as the only paid features. |
| Goal ac2: ≥25 files (≥8 team, 12 caselist incl. ≥3 non-Verbatim and ≥2 wiki-converted, 5 camp) round-tripped, results per category with each failure categorized | NOT RUN | Needs real team, caselist and camp files, which exist only on Charlie's machine and must never enter the repository. The harness is built and proven; see **Operator follow-ups**. Synthetic probes are recorded in the note under "Synthetic probes" and are explicitly not this sample. |
| Goal ac3: license section reviews PolyForm Noncommercial 1.0.0 per intended use, marks each permitted / not permitted / needs author confirmation, signed off by Charlie | NOT RUN (written, unsigned) | The section exists with seven per-use verdicts and three open questions for the author: `grep -c "PolyForm Noncommercial 1.0.0" docs/architecture/cardmirror-evaluation.md` → `1`. The "Signed off by" line is blank; only Charlie can fill it. |
| Goal ac4: ADR-0014 is Accepted, states the chosen option and rejected alternatives, names consequences for t02, v1-e33-t02, v2-e35-t04, the V2 card editor and v3-e20, and says whether the harness runs in CI | FAIL (drafted, not accepted) | `grep -n "^- Status:" docs/adr/0014-debate-file-editor.md` → `- Status: Proposed`. Everything else in the criterion is present: three rejected alternatives, a consequence bullet per named task, and an explicit "The Node round-trip harness is never run in CI". Accepting it is Charlie's call, and writing `Accepted` without his decision would be a lie in a permanent record. |
| Goal ac5: Charlie's decision recorded (who, date, option) and docs/adr/README.md moves 0014 from Reserved numbers to the Index | PARTIAL | Index move done: `grep -c "0014-debate-file-editor.md" docs/adr/README.md` → `1`, and the 0014 row is gone from the Reserved numbers table. The decision itself is pending; the ADR's Deciders line and the two answer blanks are unfilled. |
| Node `schema-and-api-review`: evaluation note has the schema mapping | PASS | `grep -c "Schema mapping" docs/architecture/cardmirror-evaluation.md` → `1` |
| Node `license-review`: license review section exists | PASS | `grep -c "PolyForm Noncommercial 1.0.0" docs/architecture/cardmirror-evaluation.md` → `1` |
| Node `license-review`: Charlie signs off the license review | NOT RUN | Human check. The verdict table and open questions are ready to read. |
| Node `roundtrip-harness`: harness README marks it operator-only | PASS | `grep -c "not run in CI" scripts/cardmirror-roundtrip/README.md` → `2` |
| Node `roundtrip-harness`: comparison script tests pass on synthetic documents | PASS | `uv run pytest tests/scripts/test_compare_docx_roundtrip.py` → `26 passed in 1.67s` |
| Node `roundtrip-run`: round-trip results recorded | PASS (criterion) / node incomplete | `grep -c "Round-trip results" docs/architecture/cardmirror-evaluation.md` → `1`. The section holds the synthetic probe results and the empty per-category table for the operator run. The typed criterion passes; the node's real work does not. |
| Node `adr-0014`: ADR-0014 is accepted | FAIL | `grep -n "Status: Accepted" docs/adr/0014-debate-file-editor.md` → no match (it is `Proposed`). |
| Node `adr-0014`: ADR index lists 0014 | PASS | `grep -c "0014-debate-file-editor.md" docs/adr/README.md` → `1` |
| Node `adr-0014`: Charlie makes the editor decision | NOT RUN | Human check. Two questions, with a recommendation on each, in the ADR's Decision section. |
| Repository checks (not in the spec, run anyway) | PASS | `uv run scripts/validate_specs.py` → `OK: 261 files, 35 epics, 207 tasks, 19 releases`; `uv run pytest` → `34 passed`; `uv run ruff check` → `All checks passed!`; `uv run ruff format --check` → `49 files already formatted`; `uv run pre-commit run --all-files` → all hooks pass on this task's files. |

## Files changed

* **`docs/architecture/cardmirror-evaluation.md`** (new) — the evaluation: schema mapping, public
  API, plugin bridge, subscription features, license review, round-trip results, and what each
  finding means for t02, t03, v1-e33-t02, v2-e35-t04 and v3-e20.
* **`docs/adr/0014-debate-file-editor.md`** (new) — the decision record, `Proposed`.
* **`docs/adr/README.md`**, **`docs/README.md`** — 0014 moved from Reserved numbers into the Index;
  the evaluation note added to the documentation index, as
  [working-agreements §3](../process/working-agreements.md#3-documentation-lives-in-predictable-places)
  requires.
* **`scripts/cardmirror-roundtrip/`** (new) — `roundtrip.mjs`, `package.json` and
  `package-lock.json` pinning CardMirror at `bc92e6b`, `README.md`, and a `.gitignore` that refuses
  `*.docx` and the manifests.
* **`scripts/compare_docx_roundtrip.py`** (new) — the comparison and the aggregate JSON summary.
* **`tests/scripts/test_compare_docx_roundtrip.py`** (new) — 26 offline tests that build their own
  synthetic `.docx` files.
* **`pyproject.toml`**, **`uv.lock`** — `python-docx` and `lxml` added to the dev dependency group;
  ruff's `scripts` exclude anchored to the repository root (see Deviations).

## Deviations from the spec

* **`pyproject.toml` is outside the task's `constraints.packages`** (`docs/adr`,
  `docs/architecture`, `scripts/cardmirror-roundtrip`, `scripts`, `tests/scripts`). Two changes were
  necessary to satisfy the spec's own plan:
  * The `roundtrip-harness` node specifies `compare_docx_roundtrip.py` as "python-docx + lxml", and
    its acceptance criterion is `uv run pytest tests/scripts/test_compare_docx_roundtrip.py`. That
    command uses the default environment, so both libraries had to join the `dev` dependency group.
  * Ruff's `extend-exclude = ["scripts"]` matches a directory named `scripts` at any depth, so it
    silently excluded the new `tests/scripts/` as well. It is now `["./scripts"]`, which is anchored
    to the repository root: `uv run ruff check scripts/` → `No Python files found` (still excluded),
    `uv run ruff check tests/scripts` → `All checks passed!` (now linted). The root `scripts/`
    exclusion is unchanged, so no pre-existing file newly fails lint.
* **The schema and API review was done from the source, not from the running apps.** The node
  description says to install the desktop app and build the web app from a pinned commit and
  exercise the structural units by hand. This session read the pinned source and exercised the
  structural units by round-tripping synthetic `.docx` files through the real `fromDocx`/`toDocx` —
  which is stronger evidence for the schema mapping than clicking through the UI, but it is not the
  same as using the editor. Installing an unsigned desktop build and forming a judgement about
  whether debaters would like it is Charlie's, and it is part of the decision he has to make.
* **Two nodes are incomplete and the Goal is left `InProgress`, not `Succeeded`.** `roundtrip-run`
  needs the operator; `adr-0014` needs Charlie's decision. Four of the five Goal criteria depend on
  one or both. Marking the Goal `Succeeded` would assert work that was not done.

## Decisions and assumptions

* **The harness depends on CardMirror by git URL, not by npm package.** CardMirror is `"private":
  true` and unpublished, so `package.json` pins
  `github:ant981228/cardmirror#bc92e6bd99cb9b3ce97ddacfa2362100db96360e` and `package-lock.json`
  pins everything under it. There is no built entry point, so `roundtrip.mjs` runs under `tsx` and
  imports CardMirror's TypeScript sources directly — the same way CardMirror's own
  `npm run round-trip` works. Verified: `npm install` → `added 28 packages in 4s`, then
  `npm run roundtrip` against synthetic files → `3 ok, 0 failed`.
* **The comparison works on character ranges, not runs.** Any editor may split or merge runs without
  changing what a debater sees, so comparing runs would report noise as loss. Spans are character
  offsets over the paragraph text; paragraphs are aligned with `difflib` so one inserted paragraph
  does not misalign everything after it.
* **Underline re-encoding is a normalization, not a difference.** CardMirror deliberately rewrites
  underline per slot — the `StyleUnderline` character style in body text, a direct `<w:u>` in tags
  and headings — and on export writes *both* on body runs. When the underlined character range is
  unchanged, the comparison records the encoding change separately instead of calling it a loss.
  This is the single most important thing the note hands to t02.
* **Nothing identifying goes in the summary.** The aggregate JSON is keyed by an 8-character sha256
  prefix and carries indices, offsets, counts and formatting values only — no document text, file
  names or paths. A test asserts it (`test_summary_keys_files_by_sha256_prefix_and_holds_no_document_text`).
  `roundtrip.mjs` additionally refuses to write into a git working tree; verified by pointing
  `--output` inside this worktree and getting the refusal.
* **No subscription was bought and no real file touched a hosted instance,** per the spec's
  forbidden list. Everything ran locally against source pulled from GitHub.
* **The ADR recommends, it does not decide.** The recommendation is: yes to CardMirror as a
  compatibility target (cheap, and the only machine-readable check on our writer that exists), and
  "allowed, not mandated" as a team editor (a five-month-old project with one maintainer and
  unsigned builds is a poor thing to bet a tournament on). Both are Charlie's to overrule.

## Operator follow-ups

**1. Install the harness** (expected runtime ~30 s)
Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e31-t01-cardmirror-evaluation`
```bash
cd scripts/cardmirror-roundtrip && npm install
```
Success looks like: `added 28 packages`. It pulls CardMirror from GitHub at the pinned commit;
`node_modules/` is gitignored.

**2. Gather the sample** (no command; ~20 min of picking files)
Put at least 25 `.docx` files **outside this repository**, in a directory with these
subdirectories — the names become the categories in the results table:
```
~/debate-files/team/                    # ≥8, across Policy / LD / PF
~/debate-files/caselist/                # hsld26 snapshot files using Verbatim styles
~/debate-files/caselist-non-verbatim/   # ≥3 that do not use Verbatim styles
~/debate-files/caselist-wiki/           # ≥2 converted from wiki text
~/debate-files/camp/                    # 5 OpenEv / camp files
```
`caselist/` + `caselist-non-verbatim/` + `caselist-wiki/` must total at least 12.

**3. Round-trip them** (expected runtime ~1–5 min, depending on file sizes)
Where: your Mac, in the task worktree
```bash
npm --prefix scripts/cardmirror-roundtrip run roundtrip -- \
  --input ~/debate-files \
  --output ~/cardmirror-roundtrip-out
```
Success looks like: a per-file `ok` line and a closing `N ok, 0 failed`. Any `FAILED` line is
itself a result — paste it. The harness will refuse to run if `--output` is inside a git repository.

**4. Compare** (expected runtime ~30 s)
Where: your Mac, in the task worktree
```bash
uv run python scripts/compare_docx_roundtrip.py \
  --manifest ~/cardmirror-roundtrip-out/roundtrip-manifest.json \
  --output ~/cardmirror-roundtrip-out/summary.json
```
Success looks like: `25 file(s): N clean, M with differences, 0 error(s)`. Paste that line and the
`totals` and `categories` blocks of `summary.json` back into the session; they contain no document
text, so they are safe to paste anywhere.

**5. Open three of them by hand** (~20 min)
Open three round-tripped files in the CardMirror desktop app and in Word with Verbatim, edit and
re-save each one, and confirm nothing looks wrong to a debater. This is the check no script does.

**6. Sign the license review and make the decision**
In [`docs/architecture/cardmirror-evaluation.md`](../architecture/cardmirror-evaluation.md), fill in
the "Signed off by" and "Date" lines under the license review, and say whether any "needs a
decision" row has to be resolved first. In [ADR-0014](../adr/0014-debate-file-editor.md), answer the
two questions in the Decision section, put your name and the date on the Deciders line, and change
`Status: Proposed` to `Status: Accepted`. Then update the 0014 row's Status in
[`docs/adr/README.md`](../adr/README.md), fill in the round-trip results table in the note, and
finish the task:
```bash
uv run scripts/task_helper.py set-phase v1-e31-t01-cardmirror-evaluation Succeeded
uv run scripts/validate_specs.py
```

**7. Fresh-worktree note (not specific to this task)**
`uv run pytest` in a newly created worktree fails four smoke tests with `ModuleNotFoundError` until
the workspace members are installed. `uv sync --all-packages` fixes it (`uv run pytest` → `34
passed`). Worth knowing before reading any CI failure in a new worktree as real.

## Follow-up work

* **Workspace members are not installed by a plain `uv sync`** (follow-up 7 above). A fresh worktree
  needs `uv sync --all-packages`, which is easy to trip over and reads like broken tests. Fixing it
  properly — listing the members as dependencies of a group, or documenting the command in
  [task-workflow.md](../process/task-workflow.md) — belongs to `v1-e01-t03-uv-workspace-tooling`'s
  area, not here.
* **CardMirror's `ARCHITECTURE.md` §19 still lists footnotes and endnotes as out of scope** while
  `src/schema/footnotes.ts` and `src/import/footnotes.ts` model them. Noted in the evaluation note.
  Only matters if t02 or t03 reads their docs instead of their code — which is why the note says to
  read the code.
* **The pinned commit will drift.** Nothing breaks when it does; we simply stop knowing whether the
  compatibility claim still holds. Re-running the harness before each major file-format change is
  the cheap fix, and ADR-0014 says so under Consequences. A future task could add it to the
  `v1-e33` file-builder checks.
* **`fromDocx`'s `provenanceOut` map** (heading UUID → source paragraph index) is the one part of
  CardMirror's API that overlaps our provenance model. If we ever want CardMirror-sourced
  provenance, that is the hook — and question 3 in the note's open questions is whether the author
  considers it supported API.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

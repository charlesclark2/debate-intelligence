# Session report: v1-e31-t01-cardmirror-evaluation

| | |
|---|---|
| Task | `v1-e31-t01-cardmirror-evaluation` — CardMirror evaluation and editor decision |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t01-cardmirror-evaluation.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t01-cardmirror-evaluation.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t01-cardmirror-evaluation` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The spike is done and ADR-0014 is Accepted. CardMirror is a compatibility target for every debate
`.docx` this platform writes, and an allowed — not mandated — team editor this season, with two
conditions: keep the Verbatim original, and do not re-save a file containing images until an
upstream defect is fixed.

[`docs/architecture/cardmirror-evaluation.md`](../architecture/cardmirror-evaluation.md) maps all 21
CardMirror node types and all 20 mark types to our structural units and to the Verbatim style ids
each side writes, lists the public TypeScript API, separates the plugin API's draft renderer surface
from its frozen bridge protocol, names the two features a Debate Decoded membership buys, and
reviews PolyForm Noncommercial 1.0.0 across seven intended uses — signed off by Charlie.

The round-trip harness ([`scripts/cardmirror-roundtrip/`](../../scripts/cardmirror-roundtrip/README.md)
plus [`scripts/compare_docx_roundtrip.py`](../../scripts/compare_docx_roundtrip.py)) was built here
and run by Charlie over 36 real files. **31 came back clean, 4 differed only by dropped soft
hyphens, and 1 failed — on a CardMirror defect, not on ours.** No structural unit changed, no cite
styling was lost, and no underline, highlight or bold span moved anywhere in the sample. Two defects
came out of it: soft hyphens (U+00AD) are silently dropped on import, and image alt text containing a
quotation mark is written unescaped into an XML attribute, producing a `.docx` Word cannot read —
silently, because the save reports success. Both are written up in the note under "Known CardMirror
defects"; the second is drafted as an upstream issue in
[`cardmirror-upstream-issues.md`](../architecture/cardmirror-upstream-issues.md), synthetic
reproduction only, **not filed**.

**The PM should look first at** the two answers in ADR-0014's Decision section, and at the
"Known CardMirror defects" section of the note — the alt-text defect is the one with a standing
instruction attached to it.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `schema-and-api-review` | Done | Schema, importer, exporter, style tables, plugin API reference and manual read at the pinned commit; structural units exercised by round-tripping synthetic files through the real `fromDocx`/`toDocx` rather than by hand in the app (see Deviations). |
| `license-review` | Done | Seven per-use verdicts and three open questions for the author; signed off by Charlie 2026-09-20. |
| `roundtrip-harness` | Done | `roundtrip.mjs`, a pinned `package.json` + `package-lock.json`, an operator-only README, `compare_docx_roundtrip.py` and 30 tests. |
| `roundtrip-run` | Done | 36 files run by Charlie; results, the hand check in Word and CardMirror, and both defects recorded in the note. |
| `adr-0014` | Done | Accepted 2026-09-20 with both decisions recorded; ADR index updated. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1: node/mark mapping, public API list, plugin-bridge maturity, subscription-gated features | PASS | [Evaluation note](../architecture/cardmirror-evaluation.md): the "Schema mapping" tables cover all 21 node types and all 20 mark types in `src/schema/nodes.ts` and `src/schema/marks.ts` at `bc92e6b` (checked programmatically against the source — every type name appears in the note); "Public TypeScript API" lists every export in `src/index.ts`; "Plugin bridge" records the DRAFT renderer API against the FROZEN bridge handshake and HTTP routes; "Debate Decoded subscription" names card sharing and relay-backed co-editing as the only paid features. |
| Goal ac2: ≥25 files (≥8 team, 12 caselist incl. ≥3 non-Verbatim and ≥2 wiki-converted, 5 camp) round-tripped, results per category with each failure categorized | PASS | Operator-run: 36 files — 14 team (Policy/LD/PF), 12 caselist with Verbatim styles, 3 non-Verbatim, 2 wiki-converted, 5 camp. `compare_docx_roundtrip.py` → `36 files, 31 clean, 4 with differences, 1 error`. Per-category table in the note's "Round-trip results"; paragraph text, heading levels, cite styling and underline/highlight/bold runs reported unchanged in every file that imported. Both failure classes categorized: dropped U+00AD (4 files) and the alt-text export defect (1 file). |
| Goal ac3: license section reviews PolyForm Noncommercial 1.0.0 per intended use, marks each permitted / not permitted / needs author confirmation, signed off by Charlie | PASS | `grep -c "PolyForm Noncommercial 1.0.0" docs/architecture/cardmirror-evaluation.md` → `1`. Seven verdicts (six permitted, one not permitted, one needing a decision that ADR-0014 removes), three open questions for the author, and "Signed off by: Charlie Clark, 2026-09-20". |
| Goal ac4: ADR-0014 is Accepted, states the chosen option and rejected alternatives, names the consequences for t02, v1-e33-t02, v2-e35-t04, the V2 card editor and v3-e20, and says whether the Node round-trip script is ever run in CI | PASS | `grep -c "Status: Accepted" docs/adr/0014-debate-file-editor.md` → `1`. Two decisions recorded, four rejected alternatives (adopt and embed, fork, ignore CardMirror, run the harness in CI), a consequence bullet for each named task, and "**The Node round-trip harness is never run in CI.**" |
| Goal ac5: Charlie's decision recorded (who, date, option) and docs/adr/README.md moves 0014 from Reserved numbers to the Index | PASS | ADR Deciders line: "Charlie Clark, 2026-09-20"; both answers carry his name and the date. `grep -c "0014-debate-file-editor.md" docs/adr/README.md` → `1`, in the Index table with status `Accepted 2026-09-20`; the 0014 row is gone from Reserved numbers. |
| Node `schema-and-api-review`: evaluation note has the schema mapping | PASS | `grep -c "Schema mapping" docs/architecture/cardmirror-evaluation.md` → `1` |
| Node `license-review`: license review section exists | PASS | `grep -c "PolyForm Noncommercial 1.0.0" docs/architecture/cardmirror-evaluation.md` → `1` |
| Node `license-review`: Charlie signs off the license review | PASS | Signed 2026-09-20: the team's use is noncommercial, and the one "needs a decision" row (embedding in the V2 web app) needs no decision because ADR-0014 rules embedding out. |
| Node `roundtrip-harness`: harness README marks it operator-only | PASS | `grep -c "not run in CI" scripts/cardmirror-roundtrip/README.md` → `2` |
| Node `roundtrip-harness`: comparison script tests pass on synthetic documents | PASS | `uv run pytest tests/scripts/test_compare_docx_roundtrip.py` → `30 passed` |
| Node `roundtrip-run`: round-trip results recorded | PASS | `grep -c "Round-trip results" docs/architecture/cardmirror-evaluation.md` → `1`; the section holds the 36-file per-category table, the hand check, and the synthetic probes that isolate each behaviour. |
| Node `adr-0014`: ADR-0014 is accepted | PASS | `grep -n "^- Status:" docs/adr/0014-debate-file-editor.md` → `- Status: Accepted` |
| Node `adr-0014`: ADR index lists 0014 | PASS | `grep -c "0014-debate-file-editor.md" docs/adr/README.md` → `1` |
| Node `adr-0014`: Charlie makes the editor decision | PASS | Compatibility target: **yes**. Team editor: **allowed, not mandated**, with the Verbatim-original and no-image-re-save conditions. Both recorded in the ADR with his name and the date. |
| Repository checks (not in the spec, run anyway) | PASS | `uv run scripts/validate_specs.py` → `OK: 261 files, 35 epics, 207 tasks, 19 releases`; `uv run pytest` → `38 passed`; `uv run ruff check` → `All checks passed!`; `uv run ruff format --check` → `50 files already formatted`; `uv run pre-commit run --all-files` → all hooks pass on this task's files. |

## Files changed

* **`docs/architecture/cardmirror-evaluation.md`** (new) — the evaluation: schema mapping, public
  API, plugin bridge, subscription features, license review with sign-off, round-trip results for
  all 36 files, the hand check in Word and CardMirror, the two known defects, and what each finding
  means for t02, t03, t04, v1-e33-t02, v2-e35-t04 and v3-e20.
* **`docs/architecture/cardmirror-upstream-issues.md`** (new) — the alt-text defect drafted as an
  upstream issue with a synthetic reproduction, plus why the soft-hyphen behaviour is not drafted as
  one. **Not filed**; filing is Charlie's call.
* **`docs/adr/0014-debate-file-editor.md`** (new) — Accepted, with both decisions, four rejected
  alternatives and the consequences.
* **`docs/adr/README.md`**, **`docs/README.md`** — 0014 moved from Reserved numbers into the Index as
  `Accepted 2026-09-20`; both new architecture documents added to the documentation index, as
  [working-agreements §3](../process/working-agreements.md#3-documentation-lives-in-predictable-places)
  requires.
* **`scripts/cardmirror-roundtrip/`** (new) — `roundtrip.mjs`, `package.json` and
  `package-lock.json` pinning CardMirror at `bc92e6b`, `README.md`, and a `.gitignore` that refuses
  `*.docx` and the manifests.
* **`scripts/compare_docx_roundtrip.py`** (new) — the comparison and the aggregate JSON summary,
  including the soft-hyphen normalization rule.
* **`tests/scripts/test_compare_docx_roundtrip.py`** (new) — 30 offline tests that build their own
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
    silently excluded the new `tests/scripts/` as well. It is now `["./scripts"]`, anchored to the
    repository root: `uv run ruff check scripts/` → `No Python files found` (still excluded),
    `uv run ruff check tests/scripts` → `All checks passed!` (now linted). The root `scripts/`
    exclusion is unchanged, so no pre-existing file newly fails lint.
* **`.gitignore` gained `/*.docx` and `/*.doc`,** also outside `constraints.packages`. A
  round-tripped debate file (`testing.roundtripped.docx`, 1.5 MB) was left at the repository root
  during the operator run and was picked up by `git add -A` in this session; the large-file hook
  caught it before it was committed. It is unstaged and untouched on disk, and the root is now
  ignored so the same accident cannot happen again. The pattern is anchored to the repository root,
  so the scrubbed fixtures t02 will add under `tests/fixtures/` are unaffected. **Charlie: that file
  is still sitting in the worktree — move or delete it.**
* **`docs/architecture/cardmirror-upstream-issues.md` is a document the spec did not ask for.** The
  spike found a defect that corrupts files on save; recording it only inside the evaluation note
  would have buried the reproduction and left nothing to paste upstream. It is in
  `docs/architecture/`, which the task's `constraints.packages` allows, and it is indexed.
* **The schema and API review was done from the source, not from the running apps.** The node
  description says to install the desktop app and build the web app from a pinned commit and
  exercise the structural units by hand. This session read the pinned source and exercised the
  structural units by round-tripping synthetic `.docx` files through the real `fromDocx`/`toDocx` —
  stronger evidence for the schema mapping than clicking through the UI. Charlie's hand check in the
  desktop app and in Word covered the part a script cannot judge, and its result is in the note.

## Decisions and assumptions

* **Soft-hyphen loss is a normalization, not a failure.** CardMirror strips U+00AD on import. The
  characters are invisible and the visible text is unchanged, so the comparison strips them from
  both sides before comparing — which also keeps character offsets aligned, so an underlined range
  containing a soft hyphen still matches — and reports the change in count as `soft_hyphens_dropped`.
  Normalizations are now aggregated per category in the summary, so this is *reported*, not merely
  not-failed. A real text change in the same paragraph is still reported as a difference alongside
  it; there is a test for exactly that.
* **Our parser must not copy this behaviour.** t03 records U+00AD positions and t04's fingerprints
  ignore them, so the same card fingerprints identically whether or not it passed through an editor
  that strips soft hyphens. Recorded in the note, in ADR-0014's consequences, and below.
* **The alt-text defect is CardMirror's, and it was verified here, not inferred.** A synthetic file
  whose image alt text contains `&quot;` round-trips to `descr="Emissions chart, "Figure 3""` —
  invalid XML — while an otherwise identical file with no quotation mark round-trips cleanly. The
  cause is `escText` (which escapes `&`, `<`, `>`) being used for a double-quoted attribute value in
  `buildDrawingXml`, where `escAttr` is required; `escAttr` is defined immediately below it in the
  same file. Our comparison script correctly reported the sample file as an `error`.
* **The harness depends on CardMirror by git URL, not by npm package.** CardMirror is
  `"private": true` and unpublished, so `package.json` pins
  `github:ant981228/cardmirror#bc92e6bd99cb9b3ce97ddacfa2362100db96360e` and `package-lock.json`
  pins everything under it. There is no built entry point, so `roundtrip.mjs` runs under `tsx` and
  imports the TypeScript sources directly, the same way CardMirror's own `npm run round-trip` does.
* **The comparison works on character ranges, not runs.** Any editor may split or merge runs without
  changing what a debater sees. Paragraphs are aligned with `difflib`, so one inserted paragraph does
  not misalign everything after it.
* **Nothing identifying goes in the summary.** The aggregate JSON is keyed by an 8-character sha256
  prefix and carries indices, offsets, counts and formatting values only — no document text, file
  names or paths. A test asserts it. `roundtrip.mjs` additionally refuses to write into a git working
  tree. The upstream issue draft holds to the same rule: synthetic reproduction only.
* **No subscription was bought and no real file touched a hosted instance,** per the spec's forbidden
  list.

## Operator follow-ups

All of this task's operator steps are done. For the record, what Charlie ran and reported back:

* `npm install` in `scripts/cardmirror-roundtrip`, then
  `npm run roundtrip -- --input <files> --output <outside the repo>` over 36 files, then
  `uv run python scripts/compare_docx_roundtrip.py --manifest … --output …` →
  `36 files, 31 clean, 4 with differences, 1 error`.
* Hand check: round-tripped files opened in the CardMirror desktop app and in Word, edited and
  saved. Word opens all of them and edits saved from Word persist; the formatting is visibly not
  what a Verbatim-configured Word produces.
* Diagnosis of every flagged file, the license sign-off, and both ADR decisions.

One thing is left deliberately undone, and it is Charlie's call, not a blocker:

* **File the alt-text issue upstream** when he judges the time is right. The draft is ready to paste
  at [`docs/architecture/cardmirror-upstream-issues.md`](../architecture/cardmirror-upstream-issues.md).
  Send no debate file if a maintainer asks for a repro — build a fresh synthetic one.

**Fresh-worktree note (not specific to this task):** `uv run pytest` in a newly created worktree
fails four smoke tests with `ModuleNotFoundError` until the workspace members are installed.
`uv sync --all-packages` fixes it (`uv run pytest` → `38 passed`). Worth knowing before reading a
failure in a new worktree as real.

## Follow-up work

* **t02/t03: the parser records U+00AD positions.** Soft hyphens are not stripped on import; their
  positions travel with the parsed text so the lossless writer (v1-e33-t02) can put them back in a
  file that came from a Verbatim user who hyphenated. This is the opposite of what CardMirror does,
  deliberately.
* **t04: card fingerprints ignore U+00AD.** Soft hyphens are removed in fingerprint normalization so
  the same card disclosed by two teams fingerprints identically whether or not one copy passed
  through an editor that strips them. CardMirror is one such editor and will not be the only one.
* **v1-e33-t02: the writer should parse what it emits.** The alt-text defect is precisely the failure
  mode that slips past a writer with no read-back check — a save that reports success and produces a
  file Word cannot open. Worth an explicit "every emitted part parses" assertion.
* **v1-e33-t02: emit the team's own style definitions.** The hand check found CardMirror regenerates
  style definitions from its own defaults, so a round-tripped file reads as "not cut in Verbatim"
  even though its structure is correct. A built file should carry the team's template appearance, not
  a normalized one.
* **The pinned commit will drift.** Re-running the harness before each major file-format change keeps
  the compatibility claim honest; ADR-0014 says so under Consequences. A future task could fold it
  into the `v1-e33` file-builder checks.
* **Workspace members are not installed by a plain `uv sync`** (see the note above). Fixing it
  properly — listing the members as dependencies of a group, or documenting the command in
  [task-workflow.md](../process/task-workflow.md) — belongs to `v1-e01-t03-uv-workspace-tooling`'s
  area, not here.
* **CardMirror's `ARCHITECTURE.md` §19 still lists footnotes and endnotes as out of scope** while
  `src/schema/footnotes.ts` and `src/import/footnotes.ts` model them. Noted in the evaluation note.
  Only matters if t02 or t03 reads their docs instead of their code.
* **`fromDocx`'s `provenanceOut` map** (heading UUID → source paragraph index) is the one part of
  CardMirror's API that overlaps our provenance model. Question 3 in the note's open questions is
  whether the author considers it supported API.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

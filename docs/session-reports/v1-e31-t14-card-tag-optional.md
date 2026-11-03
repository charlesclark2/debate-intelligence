# Session report: v1-e31-t14-card-tag-optional

| | |
|---|---|
| Task | `v1-e31-t14-card-tag-optional` — A card with no tag has no tag in memory and in every output |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t14-card-tag-optional.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t14-card-tag-optional.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t14-card-tag-optional` |
| Session status | COMPLETE |

## Summary

`ParsedCard.tag` and `CardOccurrence.tag` are now `str | None`. Reading takes `""` and `null` alike
as "no tag" and gives `None` in memory. Every JSON output says `null`, including
`caselist cards --json`, which said `""` until now. The cards statistics still count "no tag" as `""`
when they choose a cluster's label, so ties go as they always went, and a tagged card's cluster
keeps its label and its place. The ac3 test builds and rebuilds a real parsed store and passes
unchanged on `v1.1.0-dev.61` (the start commit's code), on `v1.1.0-dev.18` and on this build. **No
stored record changed.** The per-source documents already wrote `null` under `schema_version` 2,
and the stored occurrence table has no tag field at all. There is no schema bump, no parser bump,
no re-parse, and the docx-5 store stays valid as it is. **The PM should look first at Deviation 2:**
the notes say v1-e39-t02 reads `CardOccurrence.tag` from the occurrence table, but no stored
occurrence record carries a tag. t02 has to take the tag from the document records.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `tag-optional` (Optional tag everywhere) | Done | Red tests first (`f668bda`), then the type change and outputs (`c25c322`), the store doc (`9f91908`), the PM's ac4 amendment in the spec (`5bc6cf5`) and the cross-build check (`46e8f1d`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: `ParsedCard.tag` is `str \| None`, and pyright passes with no ignore added for it | PASS | `ParsedCard.tag: str \| None = None` in `debate_files.py`. `uv run pyright` (project-wide, run after the last `ruff format`) → `0 errors, 0 warnings, 0 informations`. `git diff 13ed0bf -- packages \| grep '^+' \| grep -i ignore` → no line. To get there, two test lines that indexed or searched a tag were narrowed, and one line of the docx file writer (Deviation 1) |
| **ac2**: `CardOccurrence.tag` and `caselist cards --json` give `null` for a card with no tag, shown failing first, and parsed-card-store.md says what changed | PASS | **Red** (`f668bda`, against the start commit's source). The new and changed tests in six files → `20 failed, 116 passed`, every failure for the reason meant. 10 were `assert '' is None`, on `ParsedCard` and on the occurrence. 3 were `ValidationError: 1 validation error for CardOccurrence`: its `str` field refuses `None`, the trap in the PM's notes. The CLI's `--json` failed twice with `('Thorne 26', '') != ('Thorne 26', None)`. The table failed once with an empty Tag cell. The stats labels failed with `('Pellam 26', '')` and `('Thorne 26', '')` for `None`. The parsed store failed with `('', False)` for `(None, False)`. ac4's description failed once. **Green** (`c25c322`): the same six files plus the ac3 test → `141 passed`. `test_cards_json_says_null_for_a_cluster_whose_cards_have_no_tag` gives `null` whether the input file said `null` or `""`. `test_card_occurrence.py` gives `None`, and `"tag": null` in JSON, for either spelling. **Doc**: `docs/data/parsed-card-store.md`, "A card with no tag", now has a table of what each output says, before and after |
| **ac3**: the aggregates' ordering is unchanged for tagged cards, by a test that rebuilds a store before and after | PASS | `test_untagged_cards_keep_the_order_of_tagged_cards.py` has four synthetic `.docx` files and seven cards, two of them untagged, with the order worked out by hand in its docstring. They go through the real importer, the real parser and `caselist parse`. The test checks that a rebuild writes `index.jsonl` and `occurrences.jsonl` byte for byte, that the occurrence rows are ordered by cluster, source and paragraph, and that each cluster gets the label and place the old rule gives. One of those labels is a tie between "no tag" and a tag, which "no tag" wins as `""` did. **Before and after:** the test asks nothing of a tag but `tag or None`, so it runs on older code. With `v1.1.0-dev.61`'s `debate_core` first on `PYTHONPATH` (`3366695`, this branch's parent, so the start commit's code) → `5 passed`. With `v1.1.0-dev.18` → `5 passed`. On this build → `5 passed`. It was also committed in the red commit and passed there, before any source changed |
| **ac4**: the `fingerprint_version` description says the digest is the same in v1, v2, v3 and v4 (as amended by the PM, 2026-10-19) | PASS | `CardFingerprint.fingerprint_version` now reads "…the digest, is the same in card-fingerprint-v1, v2, v3 and v4; only the clusters changed." `test_the_fingerprint_version_description_says_the_digest_is_the_same_in_v1_through_v4` failed red on the old text and passes. The amendment is written into the spec's ac4 as the PM's |
| Node `tag-optional`: Card tests pass (`uv run pytest packages/debate_core/tests -k "card or tag or occurrence"`) | PASS | `1327 passed, 1 xfailed in 15.04s` |

### What else was run

* **The affected set was not run, by the PM's ruling of 2026-10-19.**
  `uv run scripts/affected_tests.py` lists 283 of the 318 test files. The root `conftest.py`
  imports `debate_core.testing`, which imports the changed `debate_files.py`, so nearly the whole
  selection is affected (about six minutes). The PR's CI runs it. Within the two-minute line I ran
  the test directories of what changed:
  `uv run pytest packages/debate_core/tests/domain packages/debate_core/tests/application packages/debate_cli/tests/test_caselist_cards.py packages/debate_cli/tests/test_caselist_parse.py packages/debate_cli/tests/commands/test_caselist_pull_parses.py -m "not slow and not live"`
  → `2872 passed in 75.15s`. I also ran the parser, writer, store and evidence directories
  (`packages/debate_core/tests/integrations/docx_parser`, `…/docx_file_writer`,
  `…/test_local_parsed_store.py`, `packages/debate_core/tests/evidence`). The first run gave
  `2 failed, 2344 passed`: two hand-written parser expectations that spelled "no tag" `""`, now
  `None`. The file then gave `167 passed`. The always-run list
  (`uv run pytest tests/architecture tests/specs`) gave `181 passed in 4.24s`.
* **Repo checks.** `uv run ruff format --check .`: 890 files already formatted.
  `uv run ruff check .`: all checks passed. `uv run pyright`: 0 errors. `uv run lint-imports`:
  `Contracts: 12 kept, 0 broken`. `uv run scripts/check_thin_handlers.py`: 22 handlers within 25
  statements. `uv run scripts/validate_specs.py`: `OK: 394 files, 39 epics, 334 tasks, 21 releases`.
  `--require-succeeded v1-e31-t14-card-tag-optional`: `Succeeded`.
* **Docs checks.** `uv run scripts/check_links.py`: 1792 links and anchors OK.
  `uv run scripts/check_command_blocks.py --base origin/dev`: no `#` comments.
  `uv run scripts/docs_index.py --check-descriptions`: 36 described.

### The cross-build check

`packages/debate_core/tests/application/check_an_older_build_reads_untagged_cards_this_build_writes.py`
runs by its path in two steps over the ac3 test's four files. In the write step, this build imports
and parses them into a parsed store, writes the stored cards as `ParsedCard` JSONL (what
`caselist cards --parsed` reads) and prints its statistics. It wrote
`2026.10.18-docx-5: 7 cards, 2 with tag None`, and `jq` over the per-source files shows two
`schema_version` 2 cards with `"tag": null` and five tagged ones. In the read step, an older build's
`debate_core` source (`git archive <tag> packages/debate_core/src`) goes first on `PYTHONPATH`. Its
store reads every record, its `read_parsed_cards` reads the JSONL, its cards statistics report over
the stored cards, and its parse pipeline runs over the copy. `v1.1.0-dev.61` was fetched from origin
for this (`git fetch origin tag v1.1.0-dev.61`). It is the newest dev tag on the remote, and the
local tags stopped at dev.60.

| Reader | Read | Its statistics, before and after its own parse | Its parse |
|---|---|---|---|
| this build, the control | 4 per-source files, 7 cards (2 with no tag), 4 index, 0 failure, 7 occurrence rows; JSONL 7 cards (2) | `('Pellam 26', 'Canopy loss kills', 4), ('Thorne 26', None, 2), ('Okonkwo 26', 'Grid reserve margins are thinning', 1)`; 7 occurrences, 2 with no tag | `2026.10.18-docx-5` again, 0 parsed, 4 sources, 7 cards, 7 occurrences |
| `v1.1.0-dev.61` (`3366695`), the newest dev tag | the same | the same | the same |
| `v1.1.0-dev.18` (`0268cf7`), the agent's | the same | the same | `2026.10.12-docx-3`, new, 4 parsed, 4 sources, 7 cards, 7 occurrences |

Both older builds read every file this build writes and rank and label the clusters as this build
does. The commands, with `SP` set to a scratch directory:

```bash
CHECK_UNTAGGED=write CHECK_UNTAGGED_DIR=${SP}/copy uv run pytest packages/debate_core/tests/application/check_an_older_build_reads_untagged_cards_this_build_writes.py -n0 -s -q
```

```bash
git archive v1.1.0-dev.18 packages/debate_core/src | tar -x -C ${SP}/v1.1.0-dev.18
PYTHONPATH=${SP}/v1.1.0-dev.18/packages/debate_core/src CHECK_UNTAGGED=read CHECK_UNTAGGED_DIR=${SP}/copy uv run pytest packages/debate_core/tests/application/check_an_older_build_reads_untagged_cards_this_build_writes.py -n0 -s -q
```

### Mutation runs

There were 14 mutants, aimed at the boundary mapping and the JSON outputs. Each ran only the test
files that cover its module (`-n 4`), with a fresh, empty `HYPOTHESIS_STORAGE_DIRECTORY` (agreement
8). None of these tests uses Hypothesis. The file was restored after each run and its SHA-256
checked. The tree was clean afterwards.

| # | Mutant | Result |
|---|---|---|
| 1 | `ParsedCard`: no before-validator, so `""` stays `""` | Caught: 9 assertion failures in the domain tests. The 4 errors in the store tests are fixture setup: the parser's `""` is then refused as whitespace. They are not counted |
| 2 | `ParsedCard`: the validator maps `None` to `""`, the pre-t14 rule | Caught: 13 failures (4 setup errors, not counted) |
| 3 | `ParsedCard`: a serializer writes no tag as `""` | Caught: 9 failures, among them the store's version-2 guards |
| 4 | `ParsedCard.has_tag` always true | Caught: 6 failures (4 setup errors, not counted) |
| 5 | `CardOccurrence`: no before-validator | Caught: 3 failures |
| 6 | `CardOccurrence`: the validator maps `None` to `""` | Caught: 7 failures |
| 7 | `CardOccurrence`: a serializer writes no tag as `""` | Caught: 2 failures |
| 8 | Stats: no tag sorts after every tag in a label (`"￿"`) | Caught: 6 failures, including ac3's `test_the_cards_statistics_rank_and_label_the_clusters_as_before` and the CLI's |
| 9 | Stats: untagged cards do not vote for a label | Caught: 6 failures, including ac3's |
| 10 | Stats: a label's tag passed on as `""` | Caught: 5 failures |
| 11 | Stats: an occurrence carries no tag at all | Caught: 2 failures, including ac3's occurrence test |
| 12 | Stats: an occurrence is given `item.card.tag or ""` | **Survived, equivalent.** `CardOccurrence`'s own validator turns `""` back into `None`: the boundary mapping working |
| 13 | CLI `--json`: a cluster with no tag says `""` | Caught: 2 failures |
| 14 | CLI table: an empty cell for no tag | Caught: 1 failure |

I left out two mutants, equivalent by construction. Defaulting `ParsedCard.tag` to `""` changes
nothing, because `validate_default=True` sends the default through the validator. Testing for
whitespace with `self.tag and …` in place of `self.tag is not None and …` changes nothing either,
because `""` never reaches memory.

## Files changed

* `debate_core.domain.debate_files`: `ParsedCard.tag` is `str | None`. The before-validator reads
  `""` as `None`; the `""`-avoiding serializer is gone, since `None` dumps as `null` on its own. The
  whitespace check and `has_tag` use `is not None`, and the docstrings now say what "no tag" is in
  memory.
* `debate_core.domain.card_occurrence`: `CardOccurrence.tag` is `str | None` with the same
  before-validator. The module docstring says an occurrence is built in memory and never stored.
  The `fingerprint_version` description now covers v1 through v4 (ac4).
* `debate_core.application.caselist_card_stats`: `ClusterSummary.tag` is `str | None`, and a label
  counts no tag as `""`, as before.
* `debate_cli.commands.caselist_cards`: the table shows `-` for no tag, and the `--json` docs say
  `null`.
* `debate_core.integrations.docx_file_writer.writer`: one line, `card.has_tag` → `card.tag is not
  None`, for pyright (Deviation 1).
* `docs/data/parsed-card-store.md`: what each output says for a card with no tag.
* `plan_specs/…/t14-card-tag-optional.yaml`: the PM's ac4 amendment; the phase.
* Tests:
  * new: `tests/domain/test_card_occurrence.py`, the ac3 test, and the cross-build check;
  * extended: `test_debate_files.py`, `test_caselist_card_stats.py` and the CLI's
    `test_caselist_cards.py`;
  * `""` → `None` in four hand-written expectations: `test_parser.py`,
    `test_first_corpus_parse_findings.py` (two) and `test_parsed_store_schema_versions.py`;
  * two lines narrowed for pyright: `test_caselist_parse.py` and `test_structural_fixtures.py`.

## Deviations from the spec

1. **One line outside `constraints.packages`.** `debate_core.integrations.docx_file_writer.writer`
   hashed `card.tag` under `card.has_tag`, and pyright cannot narrow through a property. So ac1
   needed `card.tag is not None` there. The behaviour is identical, and the writer's tests pass
   (part of the 2344 above).
2. **The PM's notes describe a stored occurrence table that carries a tag, and none does.** The
   notes say that v1-e39-t02 "reads `CardOccurrence.tag` from the occurrence table", and that "the
   stored occurrence table keeps writing `""` for a card with no tag". In the code:
   * `CardOccurrence` is built in memory by `CaselistCardStatsService.report`, and nothing writes it;
   * the stored `occurrences.jsonl` is `OccurrenceRecord`, which has no `tag` field;
   * in the store, a card's tag lives only in the per-source `document` records, which have said
     `null` since `v1-e31-t09`.

   So no stored record says `""` for no tag in this build, and there was nothing to keep. I changed
   no record, so the conservative path holds with nothing to prove: `schema_version` stays 2, and
   the cross-build check shows dev.18 and dev.61 read everything. The tag source for t02 is a
   question for the PM, in the relay block below.
3. **Four one-line edits in `docx_parser` tests, which are t24's ground.** These are tests
   (`packages/debate_core/tests/integrations/docx_parser/`), which are in this task's packages, not
   the `debate_core.integrations.docx_parser` module. Three hand-written expectations said `""` for
   no tag and now say `None`, and one assertion message now indexes `card.tag or ""`. If t24 edits
   the same lines, the merge conflict is one line each.

### For the PM (paste-ready)

```text
v1-e31-t14 finding for v1-e39-t02 (search index build): the stored occurrence table carries no tag.

parsed/<caselist>/<version>/occurrences.jsonl rows are OccurrenceRecord: cluster, fingerprint,
membership, completeness, disclosure digest, element range, snapshots. No tag, no cite.
CardOccurrence (which has a tag) is built in memory by the cards statistics and never stored.
A card's tag in the store is in its source's document record: "tag": null under schema_version 2
(every directory from 2026.10.10-docx-2, including docx-5), "tag": "" under schema_version 1
(2026.09.20-docx-1 only).

Options for t02:
A. Read the tag from the document records via DocumentRecord.to_parsed_document, which gives
   ParsedCard.tag None for both spellings since v1-e31-t14. No record changes. (Recommended)
B. Add a tag to OccurrenceRecord. A shape change: schema_version 3, a reader plan for the agent's
   build, and a duplicate of text the document already holds.

Recommendation: A. t02 already joins documents for the evidence text it indexes, so the tag comes
with it, and nothing stored has to change. If you agree, t02's spec could say "the tag, from the
document record" where it says "the tag".
```

## Decisions and assumptions

1. **"No tag" keeps its place in the label sort.** A label is the most frequent (short cite, tag),
   with ties broken by the smallest. I count no tag as `""` there, exactly as before. The other
   choice, sorting `None` after every tag, would hand a tied cluster's label to a tagged copy and
   change `caselist cards` output for tagged clusters. Mutant 8 is that choice, and it is caught.
2. **The table shows `-` for no tag**, as the Short cite column already does for no short cite.
   The empty cell read the same as a missing value.
3. **`ParsedCard`'s serializer was removed, not kept.** It existed to turn the in-memory `""` into
   `null`. `""` can no longer be held: the validator maps it, and `validate_assignment` and `evolve`
   revalidate. So `None` serializes as `null` by itself. Mutant 3 shows that a serializer writing
   `""` back would be caught by the store's version-2 guards.
4. **`CardOccurrence` got the same before-validator,** although nothing reads it from a file
   today. The PM's rule is that reading takes both spellings. It also means a caller handing it
   `""` still gets `None` (mutant 12).
5. **"Before and after" in ac3 is read two ways, and the test covers both.** Before and after the
   code change: the same test passes on dev.61's code and on this build's. Before and after a
   rebuild: a second `caselist parse` over the store rewrites its aggregates byte for byte from
   the stored `null` tags.
6. **A new cross-build check, not an extension of t26's.** t26's parse world has no untagged card
   (all five of its cards carry a tag), so it could not show an older build reading `null` tags.
7. **No agent reinstall is needed for this task.** Nothing the agent's build writes or reads
   changed shape, and its parse writes what it always did.

## Operator follow-ups

None. The affected set is near the whole selection and goes to the PR's CI under the PM's
2026-10-19 ruling, not to the operator.

## Follow-up work

1. **v1-e39-t02: where the tag comes from** (the relay block under Deviations). For e39.
2. **`has_tag` is now `tag is not None`.** It stays: 5 source and 20 test call sites use it, and
   read better for it. A later clean-up may inline it; no task is needed.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-19

**Notes:**

Accepted, with the phase `Succeeded`. The pull request needs no `--partial`.

**The work itself:**

* **No stored record changed, and the session proved why there was nothing to keep** rather than
  following my note blindly. The trap I named (an older reader refusing `null`) is real, and the red
  run shows it. It does not apply to a store whose tags already say `null`.
* **The label rule keeps "no tag" as `""`,** so tied clusters keep their labels. Mutant 8, the other
  choice, is caught.
* **The ac3 test passes on the old code, on dev.18 and on this build,** which is what "before and
  after" has to mean.
* **The cross-build check was written fresh,** because t26's world had no untagged card. dev.18 and
  dev.61 read everything this build writes.
* **The one surviving mutant (12) is argued equivalent,** and it is the boundary doing its job.

**Rulings:**

1. **Deviation 2: my note was wrong.** The stored `occurrences.jsonl` carries no tag; tags live in
   the per-source document records. **Option A** for v1-e39-t02: the tag, and the cite, come from
   the document record through `DocumentRecord.to_parsed_document`. The PM amends t02's description
   in the next batch.
2. **Deviations 1 and 3 are accepted.** One writer line for pyright, and four test expectations in
   the parser's tests; v1-e31-t24 will meet them as one-line conflicts at most.
3. **Decisions 1 to 7 are accepted.** `-` for no tag in the table matches the short-cite column.
4. **The affected set was left to CI** by my ruling, and the session ran every directory it changed
   within the two-minute line.
5. **Follow-up 2** (`has_tag`) stays as it is; no task.

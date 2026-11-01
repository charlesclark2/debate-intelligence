# Session report: v1-e40-t36-parse-rebuild-streams-occurrence-rows

| | |
|---|---|
| Task | `v1-e40-t36-parse-rebuild-streams-occurrence-rows` — The aggregate rebuild reads cards source by source, so it no longer holds a whole caselist's cards in memory |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t36-parse-rebuild-streams-occurrence-rows.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t36-parse-rebuild-streams-occurrence-rows.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t36-parse-rebuild-streams-occurrence-rows` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The rebuild now reads one parsed source at a time and gives each card to an incremental placer
(`CardPlacer`). It keeps only a fingerprint per card, the text of each distinct full body, and each
row's place in the table. The rows are then made one at a time as the local store writes and hashes
them. The aggregates are byte for byte the same: on six synthetic stores, checked against the
pre-task rebuild kept as an oracle (which matches the real start-commit code on all six), and on
250 real `hspolicy26` sources, where the old and new SHA-256 values are equal. **Read this first: the
measurement shows the cards were not what made the rebuild large.** At 250 sources the peak went from
1.33 GB to 1.24 GB. 930 MiB of the new peak is the near-duplicate clusterer's `CutIndex`, which
builds string word lists and shingle sets for every distinct full body, about 180 bytes per word, and
lives in `debate_core.evidence`, outside this task's packages. t31's straight line to 13 GB came from
reading 1.28 GB as the end of reading; that moment was already inside the clusterer. The criterion's
literal wording holds (the peak no longer grows with every card), but its purpose, a full season's
rebuild that fits, now depends on the clusterer. The PM questions are below. The Goal stays
`InProgress`: the whole-store byte check runs past two minutes and is an operator follow-up, and the
memory outcome needs the PM's ruling.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `parse-rebuild-streams-occurrence-rows` (Streaming rebuild) | Built; its test criterion passes | The rebuild streams and is byte-identical. The peak is set by the clusterer, which this node does not cover (Deviations). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1, part 1: the main-process peak no longer grows with every card, measured before and after with t31's method, recorded in `docs/data` | PASS in its wording, not in its purpose | [`docs/data/caselist-rebuild-memory.md`](../data/caselist-rebuild-memory.md). 250 sources: before 1,333,706,752 bytes `VmHWM`, after 1,239,453,696. 500: before over 2.15 GB (t31, stopped at 112 s), after over 1.98 GB (stopped at 115 s, still placing). No card is held after the next source is read, but the peak still grows with the caselist, through the distinct full bodies in `CutIndex`. |
| ac1, part 2: aggregates byte-identical on synthetic stores | PASS | `test_caselist_parse_streams_occurrence_rows.py`, six stores (below) → 9 passed. The oracle copied into the test was also run against the start commit's own code (start source first on `PYTHONPATH`): the 6 byte tests passed there too. |
| ac1, part 3: byte-identical on the Mac's `hspolicy26` store | PASS on 250 sources; NOT RUN on the whole store | 250 sources, old code and new code in the run image over separate clones: `index.jsonl` `e002eebc…`, `failures.jsonl` `3f9e9744…`, `occurrences.jsonl` `74c61b01…` (6,664,090 bytes), equal for both. The whole store runs past two minutes: Operator follow-ups. |
| ac1, part 4: by tests shown failing first | PASS | Red against the start commit's real code (a scratch copy of the two memory tests adapted to its `place_cards` interface): 136 of the store's cards alive at placing (`assert 136 <= 1`), and peak growth 980,149 bytes against a limit of 165,255 (`assert 980149 < (661020 / 4)`). Against a mutant that collects every card behind the new interface: 128 alive, growth 1,092,810. |
| Node: "Streaming rebuild tests pass" (`uv run pytest packages/debate_core/tests -k "caselist_parse or occurrence"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -n 6 packages/debate_core/tests -k "caselist_parse or occurrence" -m "not slow and not live"` → 236 passed in 13.34 s |

### The tests

`packages/debate_core/tests/application/test_caselist_parse_streams_occurrence_rows.py`:

* **Memory, by counting:** a placer wrapper counts the store's `ParsedCard` objects still alive (via
  `gc.get_objects()`) when it is asked to place. 16 sources of 8 cards: today's code fails with 136,
  the streaming rebuild has at most 1, the loop's last card.
* **Memory, traced:** `tracemalloc` peak of a rebuild with nothing to parse, 4 sources and then 16, of
  8 bodies of about 7 KB. Growth must stay under a quarter of the added bodies (661,020 bytes):
  streaming grew by 29,727 bytes, the start commit's code by 980,149.
* **Bytes:** six stores compared, file by file by SHA-256, with the pre-task rebuild kept as the oracle:
  sources sharing one cluster across three sources, an abbreviated card in one source linked to
  another's full card, a disclosure in three weeks, cards out of paragraph order, a failed and an
  unsupported source; a stopped disclosure and a stopped source, stopped after the first parse,
  where the stopped source's near copy had named a cluster that two live sources share; camp files
  at two paths of one release, then a withdrawn camp path; and three generated stores of 30 sources,
  before and after a removal.
* **Placement:** Hypothesis, 150 examples of lists of cards from four bodies, their near copies, cuts
  under two cites and cite-only cards. `CardPlacer` gives exactly the old one-list `place`'s
  fingerprint, cluster and membership for each card.

### Mutants (agreement 8; each run with a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`)

| Mutant | Caught by | Result |
|---|---|---|
| 1. All cards collected into one list before any is placed | both memory tests | caught: `assert 128 <= 1`; `assert 1092810 < (661020 / 4)` |
| 2. A cluster spanning sources split (a new placer per source) | 6 byte tests | caught: `AssertionError: occurrences.jsonl`. The counting test crashed on it (unpacking several placements); that crash is not counted. |
| 3a. Rows not sorted | 6 byte tests | caught: `AssertionError: occurrences.jsonl` |
| 3b. Rows sorted without the snapshot and disclosure keys | generated store, seed 17 | caught: `AssertionError: occurrences.jsonl` |
| 4a. A stopped disclosure's row kept (spans from every disclosure) | stopped-disclosure store | caught: `AssertionError: occurrences.jsonl` |
| 4b. A stopped source's cards still placed | stopped-disclosure store | **survived at first**: the store's stopped source changed no live cluster. A near copy that names the shared cluster was added, and the mutant was then caught (`AssertionError: occurrences.jsonl`). |
| 5a. `camp_paths.jsonl` noting only each row's first camp path | camp store | caught: `AssertionError: camp_paths.jsonl` |
| 5b. `camp_paths.jsonl` naming the index's SHA-256 instead of the table's | camp store | caught: `AssertionError: camp_paths.jsonl` |

Mutants 1 to 5b, except 4b's second run, were run before the stopped-source test gained its near
copy. That change only adds a card and assertions, and `assert_written_as_before` is unchanged.

### Checks before the report

* `uv run scripts/affected_tests.py` selects 408 files: the parsed-store port's change reaches the root
  `conftest.py` (through `record_replay` → `cassette_filing` → `version_retention`), and
  `container.py`'s `_build_caselist_parse` changed. That is far past two minutes, so by agreement 10 it
  is left to the pull request's `ci` check. Within the limit, run instead:
  * `tests/architecture tests/specs packages/debate_core/tests/application/caselist packages/debate_core/tests/integrations/local`
    plus the parsed-store, card-statistics, short-card-recall, container-factory and CLI parse test files
    → 2585 passed in 101.30 s;
  * every other test file that calls `write_aggregates` (tub index, file build, recipes, search index
    build, stage and shrink guard, publish, `compare_card_clusters`, camp paths) → 499 passed in 16.99 s;
  * the store, removal, pull, cmir, untagged-order, schema-version and table-guard files → 138 passed;
  * `tests/docs` → 176 passed.
* `uv run ruff format --check .` → 1771 files already formatted. `uv run ruff check .` → all checks passed.
* `uv run pyright packages/debate_core packages/debate_cli` → 0 errors (after typing two fields of the new tests).
* `uv run lint-imports` → 20 kept, 0 broken. `scripts/check_thin_handlers.py` → OK.
* `uv run scripts/check_command_blocks.py --base origin/dev` → OK. `uv run scripts/validate_specs.py` → OK: 567 files, 41 epics, 504 tasks, 22 releases.

## Files changed

* `debate_core/application/caselist_card_stats.py`: `CardPlacer` (cards given one at a time) and
  `ClusterPlacement` (a placement without its card). `place()` is now built on `CardPlacer`, so every
  existing caller and test runs the same code; `placer()` makes one.
* `debate_core/application/caselist_parse.py`: the rebuild reads one source at a time, keeps a compact
  position per card and a sort key per row, and gives the store a generator of rows. The constructor
  takes `card_placer` (a factory) instead of `place_cards`. The module docstring has a section on it.
* `debate_core/application/ports/parsed_store.py`: `write_aggregates` takes `occurrences` as an
  `Iterable`, read once.
* `debate_core/integrations/local/parsed_store.py`: lines are written and hashed as they come; the
  table is streamed first and put in place after the index and the failures file (the order they
  always were), so a row that fails to build leaves all three as they were; camp paths are noted as
  rows go by.
* `debate_core/testing/fakes/parsed_store.py`: the same annotation.
* `debate_cli/container.py`: one line, `card_placer=self.caselist_card_stats().placer`.
* Tests: the new module; the constructor argument renamed in ten test files; two custom placements
  rewritten as placer classes; the four `check_an_older_build_*` scripts pass both `place_cards` and
  `card_placer`, so the build they run under takes the one it knows.
* `docs/data/caselist-rebuild-memory.md` (new): the measurement.

## Deviations from the spec

* **The memory goal is not reached by this task's change, and the spec's premise was wrong.** The spec,
  after t31, puts the rebuild's growth in holding the cards. Measured with t31's method, the cards cost
  about 85 MiB per 250 sources; the peak is the clusterer's `CutIndex` over the distinct full bodies
  (930 MiB of 1,239 MiB at 250). That is in `debate_core.evidence.near_duplicates`, outside
  `constraints.packages`, and changing how clustering holds its data needs its own byte-identity proof.
  So it was not changed. Question 1 below.
* **The measurement is in a new document, `docs/data/caselist-rebuild-memory.md`**, not in
  `docs/data/caselist-parse-memory.md` as the PM context asks. That file is only on t31's unmerged
  branch, and creating it here would make the two pull requests collide (add/add). The new document
  names it and corrects its "end of reading" reading. Question 2.
* **One line outside the task's packages:** `debate_cli/container.py` passes the new `card_placer`.
  The service cannot be given cards one at a time through the old `place_cards(cards)` callable,
  because reading a document is asynchronous and placement is not.
* **`debate_core.testing.fakes.parsed_store`** (outside the listed packages) changed one annotation to
  match the port.
* **The whole-store byte check is an operator follow-up** (over two minutes, and the old code cannot
  run on the whole store in Docker Desktop's 8 GB VM). Its oracle is the store's own aggregates: no
  manifest, suppression file or per-source file is newer than them, and their stamps are this build's.

## Decisions and assumptions

* **Exact order without one list.** The old rebuild sorted every card by source and first paragraph.
  The new one sorts entries by source and each document's cards by first paragraph; that is the same
  order, because `ParsedDocument` refuses a card naming another source. A document that names another
  source than its file is now refused with `ValueError`, next to the existing one for a missing
  document: before, its cards would have been filed under that other source.
* **Rows are sorted by the old key plus the card's and disclosure's positions**, which reproduces the
  old stable sort exactly, without building the rows first.
* **A full card's linker words come from the first body with its fingerprint**, not from the first card
  with each short cite. Equal because the fingerprint is the SHA-256 of the body under the
  normalization the words are read through (the Hypothesis test checks it against the old code). One
  word tuple is kept per fingerprint, not one per cite.
* **The formatting spans are no longer copied off each card**: no card outlives its source's reading, so
  there is nothing to save by it.
* **The counting test allows one live card**: the last card the loop read is still named by its loop
  variable when the placer is asked.

## Operator follow-ups

**The whole `hspolicy26` store: byte identity and the new code's peak** (expected runtime 10 to 20
minutes; it reads the data directory and writes only under the session's scratch folder). Run it with
little else using memory: Docker Desktop's VM has 8 GB and the container is capped at 7 GB.
Where: your Mac, in the task worktree. It copies the store copy-on-write into the scratch folder,
runs this branch's rebuild over the copy in the cloud run's image, then prints the SHA-256 of the
store's own aggregates.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e40-t36-parse-rebuild-streams-occurrence-rows
uptime
S=/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e40-t36-parse-rebuild-streams-occurrence-rows/e540e6f9-53dc-4b49-b801-1ceeeb7ed904/scratchpad
D=${HOME}/.debate-research/dev
mkdir -p ${S}/code/final ${S}/clones/whole/objects/manifests ${S}/clones/whole/parsed/hspolicy26 ${S}/out
git archive HEAD packages/debate_core/src packages/debate_cli/src | tar -x -C ${S}/code/final
cp -c -R ${D}/objects/manifests/hspolicy26 ${S}/clones/whole/objects/manifests/
cp -c -R ${D}/suppression ${S}/clones/whole/
cp -c -R ${D}/parsed/hspolicy26/2026.10.27-docx-7 ${S}/clones/whole/parsed/hspolicy26/
docker run --rm --name t36-whole --network none -m 7g -e PYTHONPATH=/code/packages/debate_core/src:/code/packages/debate_cli/src -v ${S}/code/final:/code:ro -v ${S}/measure:/measure:ro -v ${S}/clones/whole:/data --entrypoint /opt/debate-research/tools/debate-cli/bin/python debate-dev-caselist-run:v1.1.0-dev.289 /measure/rebuild_memory.py /data hspolicy26 2>&1 | tee ${S}/out/whole-new.txt | grep -v "^  "
shasum -a 256 ${D}/parsed/hspolicy26/2026.10.27-docx-7/index.jsonl ${D}/parsed/hspolicy26/2026.10.27-docx-7/failures.jsonl ${D}/parsed/hspolicy26/2026.10.27-docx-7/occurrences.jsonl
```

Success looks like: a line `sources 3869 parsed … cards 126681 occurrences 144841 clusters …`, then
three `sha256 <name> <digest>` lines whose digests equal the three `shasum` digests below them (the
index has 3,869 rows and the failures file 44). Paste back everything after the `docker run` line,
including the `rss … VmHWM …` line. If it ends with exit 137 or no `sources` line, the container ran out
of its 7 GB: paste that too, since it is a measurement as well. If the scratch folder is gone (a
restart clears it), say so and the session will write the block again.

## Follow-up work

**For the PM, paste-ready:**

> v1-e40-t36 built the streaming rebuild and it is byte-identical (synthetic stores against the old
> code kept as an oracle; 250 real hspolicy26 sources old vs new, equal SHA-256). But measuring it with
> t31's method shows the cards were not what made the rebuild large: the peak at 250 sources went
> from 1.33 GB to only 1.24 GB. 930 MiB of it is the near-duplicate clusterer's CutIndex, which holds
> every distinct full body's words and 5-word shingles as Python strings, about 180 bytes per word.
> t31 read its 1.28 GB at 23 s as the end of reading; reading had ended by then (about 290 MB), and the
> cards in one list cost about 85 MiB per 250 sources. Estimates: about 5.5 GB for the whole
> hspolicy26 store (the operator block in the report measures it), and for hspolicy25, whose archive
> is 3.6 times hspolicy26's stored sources, up to about 18 GB of CutIndex if its distinct bodies grew
> as fast as its bytes. Three questions:
>
> 1. **The clusterer's memory.** Options: (a) a new task in debate_core.evidence: CutIndex holds
>    shingles as 64-bit hashes in compact sorted arrays and drops each body's word list once its
>    shingles are made, proven byte-identical on the occurrence table like t36 (hash collisions would
>    have to be shown not to change a cluster, or checked by comparing strings on a hash match);
>    (b) size the run task to the clusterer's growth and measure the first season; (c) both: (b) for
>    the backfile imports now, (a) after. Recommendation: (c). A season is unmeasured, and (a) is
>    integrity-critical work that should not be rushed under the backfile schedule.
> 2. **Where the measurement lives.** t31's docs/data/caselist-parse-memory.md is not on dev, so t36
>    wrote docs/data/caselist-rebuild-memory.md. Options: (a) keep both, cross-referenced; (b) merge
>    t36's into t31's after both land. Recommendation: (a), with t31's straight-line 13 GB figure
>    marked as superseded by t36's.
> 3. **This task's status.** ac1's wording holds (no card is held after the next source is read; the
>    peak grows with distinct full bodies, not every card), but its purpose does not. Options:
>    (a) accept t36 as built once the operator's whole-store check matches, and file question 1's
>    task; (b) widen t36 to the clusterer. Recommendation: (a). The streaming change is still worth
>    having (about 1.3 GB at the whole store, and no list of rows or whole table held while writing),
>    and it is proven separately from a clusterer change.

**Also found:**

* `scripts/hard_stop.py` cannot stop a `docker run` container (t31 found this too). Here every container
  was named and had exited before the next was started (`docker ps` showed none left).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

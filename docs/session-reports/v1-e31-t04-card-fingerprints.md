# Session report: v1-e31-t04-card-fingerprints

| | |
|---|---|
| Task | `v1-e31-t04-card-fingerprints` — Card fingerprints and occurrences |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t04-card-fingerprints.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t04-card-fingerprints.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t04-card-fingerprints` |
| Session status | COMPLETE |

## Summary

Every parsed card now gets an exact fingerprint: SHA-256 of its evidence body under a documented,
versioned normalization (`card-fingerprint-v1`). Full cards are grouped into near-duplicate
clusters with seeded MinHash, LSH banding and confirmed Jaccard/containment. Abbreviated and
cite-only disclosures are linked to a full card's cluster only when exactly one cluster matches.
`CaselistCardStatsService` builds the occurrence table from parsed-card JSONL and the E30
disclosures, and `debate-research caselist cards` prints totals and the clusters read by the most
distinct teams. On the hand-labelled variant set, which was committed before the clusterer existed,
clustering scored **precision 1.000 and recall 0.947** (71 true-positive, 0 false-positive and
4 false-negative pairs). **What to check first:** Deviation 1. An occurrence is keyed by the
disclosing team and round as well as by source sha256 and element index. Without that, one file
disclosed by two teams (which the synthetic archives already contain) would count as one team.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| exact-fingerprint | Done | `domain/card_occurrence.py` (CardFingerprint, CardOccurrence), `evidence/fingerprints.py` (normalization, hash, cutter-mark reading) |
| near-duplicate-clusters | Done | Variant set written and committed first (`83e7303`), then `evidence/near_duplicates.py` (`c2753f1`); thresholds in `settings.fingerprints` |
| abbreviated-linking | Done | `evidence/abbreviated_links.py` |
| occurrence-table | Done | `application/caselist_card_stats.py` |
| cards-cli-and-smoke | Done | `debate_cli/commands/caselist_cards.py`, container factory, `tests/smoke/test_caselist_cards.py`, one README row |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: exact fingerprints are identical across tags, cites, highlighting, smart/straight quotes and whitespace, differ when a word changes, and carry fingerprint_version | PASS | `uv run pytest packages/debate_core/tests/evidence/test_fingerprints.py -k exact` → 21 passed. Expected digests are SHA-256 of normalized strings written by hand in the test. A subprocess test under two `PYTHONHASHSEED`s gets the same digest. |
| ac2: precision ≥ 0.98 and recall ≥ 0.90 on the synthetic variant set; cluster ids stable across runs and input order | PASS | `uv run pytest packages/debate_core/tests/evidence/test_near_duplicates.py` → 36 passed. Measured (`-n0 -s -k precision`): `71 true positive, 0 false positive, 4 false negative pairs; precision 1.000, recall 0.947`. Stability: identical ids across repeat runs, 5 seeded shuffles plus a reversal, two fresh interpreters with different `PYTHONHASHSEED`, and every permutation of a union order. |
| ac3: ABBREVIATED/CITE_ONLY cards link when short cite and first/last words match, and stay unlinked when they don't | PASS | `uv run pytest packages/debate_core/tests/evidence/test_fingerprints.py -k abbreviated` → 21 passed. Covers links from the body and from the cite line, a short cite or year that differs, opening or closing words that differ, an ambiguous two-cluster match, and too few anchor words. |
| ac4: three cumulative snapshots → one occurrence with first/last seen; per-cluster counts are distinct teams, not files | PASS | `uv run pytest packages/debate_core/tests/application/test_caselist_card_stats.py` → 14 passed (three snapshots give 1 occurrence spanning 09-01 to 09-15; a `(1)` re-upload collapses into it; one cluster read by 2 teams in 4 occurrences across 3 files). |
| ac5: `caselist cards --caselist --parsed [--snapshot] [--top N] [--json]` prints totals and top clusters; a smoke check covers it | PASS | `uv run pytest packages/debate_cli/tests/test_caselist_cards.py` → 6 passed; `uv run pytest tests/smoke/test_caselist_cards.py` → 4 passed. |
| Node: exact fingerprint tests pass | PASS | as ac1 |
| Node: near-duplicate precision/recall and stability tests pass | PASS | as ac2 |
| Node: abbreviated linking tests pass | PASS | as ac3 |
| Node: occurrence and statistics tests pass | PASS | as ac4 |
| Node: CLI tests pass | PASS | 6 passed |
| Node: smoke check passes | PASS | 4 passed, 1.8 s, unmarked (offline) |
| Node: type check passes | PASS | `uv run pyright packages/debate_core packages/debate_cli` → 0 errors, 0 warnings |
| Node: import boundaries hold | PASS | `uv run lint-imports` → Contracts: 5 kept, 0 broken |
| Whole suite and lint (not a spec criterion) | PASS | `uv run pytest -q` → 2629 passed, 1 skipped (the existing t05 parser-eval skip) in 48 s; `uv run ruff check .` → all passed; `uv run ruff format --check .` → 374 files formatted |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → OK: 284 files, 38 epics, 226 tasks, 20 releases |

### How the variant set keeps ac2 from being circular

`tests/fixtures/fingerprints/variants.jsonl` has 35 synthetic copies of 9 invented cards, which
makes 595 pairs, 75 of them the same card. Each row's `card` label was written by hand and committed
in `83e7303` before `near_duplicates.py` existed. It covers the variations the spec names (trimmed
start, trimmed end, extra paragraph, OCR-style spacing, re-highlighted), plus retagged copies and a
one-word typo. It also has these hard negatives:

* **A second card from the same article** that opens with the first card's last sentence. One cut of
  the first card also reaches into the second card's next two sentences.
* **The same author on adjacent pages**, sharing a whole sentence.
* **Two different authors** who open with the same 36-word statutory quotation.
* **Two short cards from one article** that share their first eleven words.

All hard negatives stayed apart (0 false positives). The 4 misses are all on one short card
(`ilves-unannounced-releases`):

* **The OCR copy (2 pairs), a genuine miss.** One split word removes enough of a 30-word card's
  shingles that containment falls to 0.81.
* **The trimmed copy (2 pairs), an LSH miss.** Its containment is 1.0, but its Jaccard is 0.44, so
  with 32×4 banding it never became a candidate pair.

## Files changed

* `packages/debate_core/src/debate_core/domain/card_occurrence.py`: CardFingerprint,
  CardOccurrence, the cutter-mark type (excluded from repr), membership and basis enums.
* `packages/debate_core/src/debate_core/evidence/`: `fingerprints.py` (normalization, exact hash,
  cutter-mark reading), `near_duplicates.py` (shingles, MinHash, LSH, union-find),
  `abbreviated_links.py`.
* `packages/debate_core/src/debate_core/application/`: `caselist_card_stats.py` (service, JSONL
  reader, totals, ranking); `settings.py` (new `fingerprints` group with the two thresholds).
* `packages/debate_cli/src/debate_cli/`: `commands/caselist_cards.py`, registration in
  `commands/__init__.py`, and `caselist_card_stats()` in `container.py`.
* Tests: `packages/debate_core/tests/evidence/test_fingerprints.py`, `test_near_duplicates.py`,
  `packages/debate_core/tests/application/test_caselist_card_stats.py`,
  `packages/debate_cli/tests/test_caselist_cards.py`, `tests/smoke/test_caselist_cards.py`.
* Fixtures: `tests/fixtures/fingerprints/variants.jsonl` (hand-written and hand-labelled),
  `tests/fixtures/fingerprints/parsed_cards_testcl26.jsonl` (4 invented input cards for the smoke
  check).
* `tests/smoke/README.md`: one table row and one command line.

Nothing in `tests/fixtures/debate_files/eval/` or `scripts/prelabel_docx.py` was touched, and the
parser was never run to produce a fixture.

## Deviations from the spec

1. **The occurrence key includes the disclosure.** The spec keys an occurrence by source sha256 plus
   element index. This task keys it by source sha256, element index, caselist (or camp), school,
   team code, side, tournament and raw round label, and never by snapshot or archive path
   (`CardOccurrence.occurrence_key`). Two things still hold: cumulative snapshots and `(1)`
   re-uploads collapse into one occurrence with first and last seen dates (ac4). But the same bytes
   disclosed by two teams become two occurrences, and so do the same file read in two rounds. With
   the spec's literal key, a shared file would be one occurrence that could name only one team, and
   ac4's "distinct teams, not files" would undercount. The synthetic archives already include this
   case (`grove-round-1-aff`, disclosed by QX and by ZaLu). The PM may want the spec text amended to
   match.
2. **"128 seeded MinHash permutations" are 128 seeded hash functions.** Each value comes from
   SHAKE-128 keyed by a fixed seed and the shingle; this is the standard hash-function form of
   MinHash. Nothing uses Python's `hash()` or unseeded `random`. There is no numpy in `debate_core`,
   and adding a dependency was outside this task's packages.
3. **A CITE_ONLY card is fingerprinted over its cite line.** The spec defines the fingerprint over
   the evidence body, and a cite-only card has none, so every cite-only card would share the hash of
   the empty string. The cite-line digest uses a separate prefix and says `basis: CITE_LINE`.
4. **Cutter marks are recognised only in the explicit `//mark` form at the end of the cite.** The
   parser does not extract a cutter mark; it keeps the whole cite line, which is where this task
   reads the mark from. A bare trailing word is not taken, because it is as likely to be a title or
   a URL, and a mark that goes unrecognised is the safe failure. The mark is stored verbatim on the
   occurrence and excluded from its `repr`. It never appears in the statistics, JSON, table, logs or
   any fixture; tests use only `zzTEST`.
5. **`--json` works after the command as well as at the root.** Every other command takes it only
   at the root (`debate-research --json …`). The spec writes it after `cards`, so the command
   accepts both, and both produce the same envelope.
6. **One fixture file not named in the spec's outputs:**
   `tests/fixtures/fingerprints/parsed_cards_testcl26.jsonl`, the "fixture JSONL" for the smoke
   check. Its 4 cards are invented, written as literal values and serialized through the
   `ParsedCard` model. It is input, not an expectation. The smoke check's expected counts are
   written by hand in the test's docstring, and a test fails if the fixture's source hashes stop
   matching the synthetic archives' bytes.
7. **Thresholds live in a new settings group**, `fingerprints.near_duplicate_jaccard` and
   `fingerprints.near_duplicate_containment` (`DEBATE_FINGERPRINTS__…`). Shingle size, the number of
   hash functions and the banding stay module constants, because they decide which pairs are ever
   compared.

## Decisions and assumptions

* **What the totals mean.** `cards` counts distinct card positions (one file plus one element
  index). `occurrences` counts positions multiplied by disclosing team and round. `clusters` counts
  distinct cards. The duplicate rate is `1 - clusters / cards`. `teams` counts only occurrences whose
  file has a disclosure on record; a card with no disclosure still counts as a card.
* **`--snapshot` means "as of".** It drops parsed cards and disclosures from later snapshots.
* **First and last seen come from disclosures when a file has any**, and otherwise from the
  snapshot the card was parsed under.
* **Cluster ids come from full cards only**, so linking an abbreviated card can never change one.
  An unlinked abbreviated card is its own cluster, keyed by its own fingerprint.
* **For matching only, a hyphen followed by whitespace is rejoined** (`commis- sion` becomes
  `commission`) and punctuation is dropped before shingling. Neither affects the exact fingerprint
  or any stored text.
* **`read_parsed_cards` reads two line shapes.** A line may be a `ParsedCard` or a `ParsedDocument`
  (the per-source record t06 plans to write). An unreadable line raises an error that names the file
  and line number, never the line's content.
* **The cluster table's short cite and tag** are the most common pair among the cluster's full
  cards, with ties broken by the smallest value, so the choice is stable.

## Operator follow-ups

None. Everything ran in the session; the longest step was the full suite, at 48 s.

## Follow-up work

* **LSH misses copies that are almost wholly contained but have low Jaccard** (v1-e31, a possible
  spec change). With 32×4 bands, a short trimmed copy with containment 1.0 and Jaccard 0.44 was
  never compared. That cost 2 of the 4 missed pairs in the variant set. A containment-oriented
  candidate step, such as indexing each body's first and last shingles, would catch these. It would
  change the banding the spec prescribes, so it needs a spec decision.
* **Accuracy and speed on the real corpus are unmeasured** (v1-e31-t06, operator run). The variant
  set is synthetic and says nothing about the corpus. MinHash is pure Python: one SHAKE-128 digest
  per shingle, roughly a millisecond per card by estimation, not by measurement. The t06 full-corpus
  parse should record clustering time and cluster counts in `docs/data/`, as aggregates only.
* **Persisting the occurrence table** (v1-e31-t06). `CaselistCardReport.occurrences` holds school,
  team code and cutter mark. t06 has to keep those out of logs at every level, keep the cutter mark
  out of anything published outside the private stores, and document the field in
  `docs/data/parsed-card-store.md`.
* **Other cutter-mark conventions** (v1-e31-t05). If the labelled set shows conventions besides
  `//mark`, the recogniser can be widened then, against real (in-place) data.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

Accepted, phase stays `Succeeded`. One spec amendment on this branch, one follow-up filed
elsewhere, nothing to send back.

**Deviation 1 is right and the spec was wrong.** ac4 asks for two things that its own stated key
cannot both deliver: the same disclosure across three cumulative snapshots collapsing to one
occurrence, and cluster counts that "count distinct teams, not files". Keyed by source sha256 plus
element index alone, one file disclosed by two teams is one occurrence and the distinct-team count
is 1 — ac4's second half made untrue by ac4's own key. Adding the disclosing team and round keeps
the first half intact (the same team's disclosure in a later snapshot still collapses) and makes
the second half true. The description and the `occurrence-table` node are amended here. Noticing
that a criterion contradicts itself, and saying so rather than picking the half that was easier to
implement, is the thing I most want from these sessions.

**ac2 was done the way it needed to be done.** 35 variants written, labelled by hand, and committed
*before the clusterer existed*, so `--check` on the numbers compares against an independent
expectation rather than against the algorithm's own output. The hard negatives are genuinely hard —
two cards from one article, the same author on adjacent pages, two authors opening with the same
statute quote, two short cards sharing eleven opening words — and precision 1.000 with zero false
merges across those is a real result rather than an easy one. This is working agreement 6 applied
where it was least convenient, for the second task running.

**The four misses are reported honestly and one of them is interesting.** A containment of 0.81 on
an OCR-split word is the algorithm behaving as specified. The other is not: containment 1.0 on a
trimmed copy that the 32x4 banding never paired for comparison, so the confirmation step never ran.
Declining to retune banding the spec prescribes, and listing it as follow-up instead, is correct.
Recall 0.947 clears the 0.90 bar with the miss disclosed rather than tuned away.

I have filed the consequence against **`v1-e31-t06-parse-pipeline`**, which is where the clustering
meets real data: it must now measure short-card recall separately and report it. The reason is not
the four misses themselves but what they are made of — an ABBREVIATED disclosure is first and last
words by construction, and those dominate wiki-converted caselists, so a banding weak on short
documents would undercount precisely the format the corpus mostly consists of. That is a landscape
correctness question, not a tuning preference, and it should be measured before anyone acts on a
cluster count.

**Checked directly rather than from the report.**

* `CardOccurrence.cutter_mark` carries `repr=False`, a 16-character ceiling, and an
  `AfterValidator` that *rejects* a whitespace-separated value because "that is a name, not a
  mark". The spec asked for opacity and minimisation; making it structurally hard to fit a full
  name in the field was not asked for and is better.
* Cite-only fingerprints are domain-separated with a `_CITE_LINE_DOMAIN` prefix and carry an
  explicit `basis` of `CITE_LINE` versus `EVIDENCE_BODY`. Without the prefix a body that happened
  to equal some card's cite line would have collided across two different meanings of the same
  hash. This was the second thing I went looking for and it was already handled.

**The smaller deviations are all accepted.** SHAKE-128 as the seeded hash family is a reasonable
reading of "128 seeded permutations" and satisfies the determinism the forbidden list demands —
the shuffled-input, reversed-input and varied-`PYTHONHASHSEED` tests are the evidence that matters.
Reading cutter marks only from the trailing `//mark` form is the conservative choice: a narrower
recogniser under-collects provenance, where a looser one would start capturing text that is not a
mark, and only one of those two errors is a privacy problem.

**One operational note, not a defect.** `.github/workflows/ci.yml` is not on dev yet — `v1-e01-t04`
is still open — so this pull request gets no CI run. The full suite at 2,629 passed is the only
gate this change goes through. That is the status quo for every task so far and is exactly what
t04 exists to end.

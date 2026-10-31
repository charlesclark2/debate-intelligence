<!-- docs-index: The parser over the real corpus in place: parse success rate, failures by reason, cards and timing; counts only (v1-e31-t05 ac5) -->
# Parser corpus health

Whether the `v1-e31-t03` parser reads every debate file the platform will import, measured over
the real corpus in place by `scripts/parser_corpus_health.py`. Unlabeled: this says whether a
file parsed and what came out, not whether the cards are right. Accuracy is the labeled
evaluation's job (`tests/evals/parser/`).

Counts only. No file name, path, school, team code, document text or exception message is
collected into this report; a crash is counted by its exception type, a refusal by its reason.

| | |
|---|---|
| Run on | 2026-10-31 |
| Parser version | `2026.10.27-docx-7` |
| Corpus | the hsld26 weekly caselist snapshots and the 2026-27 Policy camp files |
| Files seen | 2509 (2209 distinct by SHA-256) |
| Distinct `.docx` files | 2163 |
| **Parse success rate** | **0.9995** of distinct `.docx` files (target 0.98: MET) |

## Parse success rate by category

| Category | Files seen | Distinct | `.docx` | Parsed | Parse success rate |
|---|---|---|---|---|---|
| camp | 105 | 102 | 102 | 102 | 1.0000 |
| caselist | 2404 | 2107 | 2061 | 2060 | 0.9995 |
| **all** | 2509 | 2209 | 2163 | 2162 | 0.9995 |

## Failure reasons

Every `.docx` that did not parse, counted by reason.

| Reason | camp | caselist | all |
|---|---|---|---|
| refused: UNSUPPORTED_FORMAT | 0 | 1 | 1 |

Files not parsed because V1 reads `.docx` only (distinct files):

- `other`: 23
- `pdf`: 23

## Template families

From `scripts/survey_docx_styles.py`'s classifier. Parsed / distinct `.docx` per family.

| Family | camp | caselist | all | parse success rate |
|---|---|---|---|---|
| cardmirror | 71 | 1685 | 1756 | 1.0000 |
| other-heuristic | 3 | 149 | 152 | 1.0000 |
| unreadable | 0 | 1 | 1 | 0.0000 |
| verbatim | 28 | 186 | 214 | 1.0000 |
| wiki-converted | 0 | 40 | 40 | 1.0000 |

## What came out

| Category | Cards | FULL | ABBREVIATED | CITE_ONLY | Median cards per file | 90th percentile | Parsed files with no cards |
|---|---|---|---|---|---|---|---|
| camp | 8081 | 8001 (99.0%) | 0 (0.0%) | 80 (1.0%) | 46 | 167 | 0 (0.0%) |
| caselist | 30726 | 30513 (99.3%) | 0 (0.0%) | 213 (0.7%) | 15 | 23 | 11 (0.5%) |
| **all** | 38807 | 38514 (99.2%) | 0 (0.0%) | 293 (0.8%) | 15 | 24 | 11 (0.5%) |

## Parse time per file

| Category | Median | 95th percentile | Slowest | Total |
|---|---|---|---|---|
| camp | 0.296 s | 4.033 s | 9.318 s | 82.1 s |
| caselist | 0.102 s | 0.236 s | 1.113 s | 234.0 s |
| **all** | 0.103 s | 0.269 s | 9.318 s | 316.1 s |

Every failure reason above is filed against `v1-e31-t03`'s parser, not fixed inside the
evaluation.

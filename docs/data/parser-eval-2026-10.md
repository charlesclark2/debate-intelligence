<!-- docs-index: Parser evaluation baseline on 2026.10.18-docx-5: per-unit scores for the labelled tiers -->
# Parser evaluation — full tier

| | |
|---|---|
| Parser version | `2026.10.18-docx-5` |
| Profile version | `2026.09.20-verbatim-1` |
| Files | 30 |
| Labeled rows | 1851 of 5763 paragraphs (0.321 of the corpus), sampling plan `06a5e928bf1fc90f` |
| Label status | PRELABELED 0, CORRECTED 27, COACH_REVIEWED 3 |
| Gate | FAILED |

Scores are micro-averaged: counts are summed over every paragraph in a group before a ratio is
taken. `—` means nothing to measure (no labels and no predictions of that kind).

**Labeling is sampled**, so every row below states the labeled rows it was computed over: the
six-file PR subset is labeled in full, and about a quarter of every other file in contiguous
blocks. A card is scored only where it lies wholly inside a labeled block.

## Targets

| Group | Metric | Target | Measured | Status |
|---|---|---|---|---|
| template:verbatim | TAG F1 | 0.97 | 0.950 | MISSED |
| template:verbatim | CITE F1 | 0.97 | 0.751 | MISSED |
| template:verbatim | EVIDENCE F1 | 0.97 | 0.934 | MISSED |
| template:verbatim | POCKET F1 | 0.95 | 1.000 | MET |
| template:verbatim | HAT F1 | 0.95 | 1.000 | MET |
| template:verbatim | BLOCK F1 | 0.95 | 0.985 | MET |
| template:verbatim | ANALYTIC F1 | 0.85 | 0.872 | MET |
| template:verbatim | span F1 | 0.99 | 0.971 | MISSED |
| template:non-verbatim | TAG F1 | 0.90 | 0.908 | MET |
| template:non-verbatim | CITE F1 | 0.90 | 0.796 | MISSED |
| template:non-verbatim | EVIDENCE F1 | 0.90 | 0.908 | MET |

## Gate

- FAIL: no baseline is established for the full tier; run scripts/run_parser_eval.py --write-baseline and commit it with a coach-reviewed report

## Unit F1 by group

| Group | Files | Labeled rows | Rate | POCKET | HAT | BLOCK | TAG | CITE | EVIDENCE | ANALYTIC | UNDERTAG | OTHER |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| overall | 30 | 1851 of 5763 | 0.321 | 1.000 | 0.988 | 0.959 | 0.935 | 0.763 | 0.924 | 0.789 | 0.000 | 0.650 |
| family:cardmirror | 5 | 302 of 1170 | 0.258 | 1.000 | 1.000 | 0.933 | 0.897 | 0.742 | 0.950 | 0.791 | — | 0.542 |
| family:other-heuristic | 10 | 577 of 1540 | 0.375 | 1.000 | 0.960 | 0.982 | 0.961 | 0.818 | 0.950 | 0.800 | 0.000 | 0.759 |
| family:verbatim | 11 | 871 of 2774 | 0.314 | 1.000 | 1.000 | 1.000 | 0.969 | 0.754 | 0.928 | 0.941 | 0.000 | 0.616 |
| family:wiki-converted | 4 | 101 of 279 | 0.362 | 1.000 | 1.000 | 0.000 | 0.588 | 0.600 | 0.353 | 0.435 | — | 0.630 |
| format:LD | 18 | 653 of 2050 | 0.319 | 1.000 | 1.000 | 0.828 | 0.906 | 0.819 | 0.915 | 0.795 | — | 0.773 |
| format:PF | 5 | 535 of 1913 | 0.280 | 1.000 | 0.923 | 1.000 | 0.978 | 0.734 | 0.887 | 0.947 | — | 0.405 |
| format:Policy | 7 | 663 of 1800 | 0.368 | 1.000 | 1.000 | 1.000 | 0.934 | 0.745 | 0.966 | 0.720 | 0.000 | 0.662 |
| source:camp | 6 | 607 of 1604 | 0.378 | 1.000 | 1.000 | 1.000 | 0.929 | 0.720 | 0.962 | 0.720 | 0.000 | 0.640 |
| source:caselist | 12 | 469 of 1481 | 0.317 | 1.000 | 1.000 | 0.783 | 0.872 | 0.889 | 0.968 | 0.767 | — | 0.876 |
| source:team | 12 | 775 of 2678 | 0.289 | 1.000 | 0.963 | 1.000 | 0.985 | 0.731 | 0.874 | 0.966 | — | 0.520 |
| template:non-verbatim | 14 | 678 of 1819 | 0.373 | 1.000 | 0.966 | 0.931 | 0.908 | 0.796 | 0.908 | 0.655 | 0.000 | 0.712 |
| template:verbatim | 16 | 1173 of 3944 | 0.297 | 1.000 | 1.000 | 0.985 | 0.950 | 0.751 | 0.934 | 0.872 | 0.000 | 0.603 |

## Precision and recall, overall (1851 labeled paragraphs)

| Unit | Support | Precision | Recall | F1 |
|---|---|---|---|---|
| POCKET | 24 | 1.000 | 1.000 | 1.000 |
| HAT | 42 | 0.977 | 1.000 | 0.988 |
| BLOCK | 64 | 1.000 | 0.922 | 0.959 |
| TAG | 173 | 0.952 | 0.919 | 0.935 |
| CITE | 215 | 0.985 | 0.623 | 0.763 |
| EVIDENCE | 1054 | 0.971 | 0.882 | 0.924 |
| ANALYTIC | 81 | 0.845 | 0.741 | 0.789 |
| UNDERTAG | 6 | — | 0.000 | 0.000 |
| OTHER | 192 | 0.483 | 0.990 | 0.650 |

## Cards and spans by group

| Group | Labeled rows | Labeled cards | Boundary exact match | Card precision | Completeness accuracy | Span paragraphs | Underline F1 | Highlight F1 | Span F1 |
|---|---|---|---|---|---|---|---|---|---|
| overall | 1851 | 135 | 0.889 | 0.863 | 0.983 | 336 | 0.989 | 0.973 | 0.985 |
| family:cardmirror | 302 | 19 | 0.895 | 0.850 | 1.000 | 59 | 0.992 | 1.000 | 0.993 |
| family:other-heuristic | 577 | 42 | 0.929 | 0.907 | 0.949 | 94 | 0.999 | 1.000 | 0.999 |
| family:verbatim | 871 | 67 | 0.881 | 0.855 | 1.000 | 166 | 0.969 | 0.923 | 0.958 |
| family:wiki-converted | 101 | 7 | 0.714 | 0.714 | 1.000 | 17 | 1.000 | — | 1.000 |
| format:LD | 653 | 50 | 0.900 | 0.865 | 1.000 | 108 | 0.993 | 1.000 | 0.995 |
| format:PF | 535 | 38 | 0.816 | 0.816 | 1.000 | 105 | 0.941 | 0.759 | 0.904 |
| format:Policy | 663 | 47 | 0.936 | 0.898 | 0.955 | 123 | 0.996 | 1.000 | 0.997 |
| source:camp | 607 | 43 | 0.930 | 0.889 | 0.950 | 113 | 0.996 | 1.000 | 0.996 |
| source:caselist | 469 | 35 | 0.886 | 0.838 | 1.000 | 79 | 0.991 | 1.000 | 0.993 |
| source:team | 775 | 57 | 0.860 | 0.860 | 1.000 | 144 | 0.971 | 0.901 | 0.954 |
| template:non-verbatim | 678 | 49 | 0.898 | 0.880 | 0.955 | 111 | 0.999 | 1.000 | 0.999 |
| template:verbatim | 1173 | 86 | 0.884 | 0.854 | 1.000 | 225 | 0.977 | 0.948 | 0.971 |

## Labeled blind

A file labeled blind was corrected with the pre-label hidden. Its rows that differ from the
pre-label, beside the same figure for the other corrected files of its stratum (category and
template family), show whether accepting a default has inflated the scores. Files are named
by digest prefix, as `MANIFEST.md` names them.

| File | Stratum | Rows differing from the pre-label | Other files of its stratum |
|---|---|---|---|
| `bad8c9119196b60a` | camp, verbatim | 10 of 54 (0.185) | 17 of 135 (0.126), in 1 file |

## PR subset


| | |
|---|---|
| Parser version | `2026.10.18-docx-5` |
| Profile version | `2026.09.20-verbatim-1` |
| Files | 6 |
| Labeled rows | 410 of 410 paragraphs (1.000 of the corpus), sampling plan `06a5e928bf1fc90f` |
| Label status | PRELABELED 0, CORRECTED 3, COACH_REVIEWED 3 |
| Gate | FAILED |

Scores are micro-averaged: counts are summed over every paragraph in a group before a ratio is
taken. `—` means nothing to measure (no labels and no predictions of that kind).

**Labeling is sampled**, so every row below states the labeled rows it was computed over: the
six-file PR subset is labeled in full, and about a quarter of every other file in contiguous
blocks. A card is scored only where it lies wholly inside a labeled block.

### Targets

| Group | Metric | Target | Measured | Status |
|---|---|---|---|---|
| template:verbatim | TAG F1 | 0.97 | 0.952 | MISSED |
| template:verbatim | CITE F1 | 0.97 | 0.762 | MISSED |
| template:verbatim | EVIDENCE F1 | 0.97 | 0.895 | MISSED |
| template:verbatim | POCKET F1 | 0.95 | 1.000 | MET |
| template:verbatim | HAT F1 | 0.95 | 1.000 | MET |
| template:verbatim | BLOCK F1 | 0.95 | 1.000 | MET |
| template:verbatim | ANALYTIC F1 | 0.85 | 1.000 | MET |
| template:verbatim | span F1 | 0.99 | 0.808 | MISSED |
| template:non-verbatim | TAG F1 | 0.90 | 0.850 | MISSED |
| template:non-verbatim | CITE F1 | 0.90 | 0.882 | MISSED |
| template:non-verbatim | EVIDENCE F1 | 0.90 | 0.978 | MET |

### Gate

- FAIL: no baseline is established for the pr-subset tier; run scripts/run_parser_eval.py --write-baseline and commit it with a coach-reviewed report

### Unit F1 by group

| Group | Files | Labeled rows | Rate | POCKET | HAT | BLOCK | TAG | CITE | EVIDENCE | ANALYTIC | UNDERTAG | OTHER |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| overall | 6 | 410 of 410 | 1.000 | 1.000 | 1.000 | 1.000 | 0.902 | 0.816 | 0.956 | 0.682 | 0.000 | 0.848 |
| family:other-heuristic | 2 | 227 of 227 | 1.000 | 1.000 | 1.000 | 1.000 | 0.944 | 0.882 | 1.000 | 0.933 | 0.000 | 0.900 |
| family:verbatim | 3 | 153 of 153 | 1.000 | 1.000 | 1.000 | 1.000 | 0.952 | 0.762 | 0.895 | 1.000 | — | 0.897 |
| family:wiki-converted | 1 | 30 of 30 | 1.000 | — | — | — | 0.000 | — | 0.000 | 0.316 | — | 0.645 |
| format:LD | 2 | 98 of 98 | 1.000 | 1.000 | 1.000 | — | 0.857 | 0.957 | 0.800 | 0.480 | — | 0.846 |
| format:PF | 2 | 60 of 60 | 1.000 | 1.000 | 1.000 | 1.000 | 0.909 | 0.250 | 0.842 | 1.000 | — | 0.960 |
| format:Policy | 2 | 252 of 252 | 1.000 | 1.000 | 1.000 | 1.000 | 0.930 | 0.844 | 0.984 | 0.857 | 0.000 | 0.800 |
| source:camp | 2 | 252 of 252 | 1.000 | 1.000 | 1.000 | 1.000 | 0.930 | 0.844 | 0.984 | 0.857 | 0.000 | 0.800 |
| source:caselist | 2 | 98 of 98 | 1.000 | 1.000 | 1.000 | — | 0.857 | 0.957 | 0.800 | 0.480 | — | 0.846 |
| source:team | 2 | 60 of 60 | 1.000 | 1.000 | 1.000 | 1.000 | 0.909 | 0.250 | 0.842 | 1.000 | — | 0.960 |
| template:non-verbatim | 3 | 257 of 257 | 1.000 | 1.000 | 1.000 | 1.000 | 0.850 | 0.882 | 0.978 | 0.588 | 0.000 | 0.789 |
| template:verbatim | 3 | 153 of 153 | 1.000 | 1.000 | 1.000 | 1.000 | 0.952 | 0.762 | 0.895 | 1.000 | — | 0.897 |

### Precision and recall, overall (410 labeled paragraphs)

| Unit | Support | Precision | Recall | F1 |
|---|---|---|---|---|
| POCKET | 7 | 1.000 | 1.000 | 1.000 |
| HAT | 14 | 1.000 | 1.000 | 1.000 |
| BLOCK | 17 | 1.000 | 1.000 | 1.000 |
| TAG | 43 | 0.949 | 0.861 | 0.902 |
| CITE | 44 | 0.969 | 0.705 | 0.816 |
| EVIDENCE | 189 | 0.943 | 0.968 | 0.956 |
| ANALYTIC | 28 | 0.938 | 0.536 | 0.682 |
| UNDERTAG | 1 | — | 0.000 | 0.000 |
| OTHER | 67 | 0.736 | 1.000 | 0.848 |

### Cards and spans by group

| Group | Labeled rows | Labeled cards | Boundary exact match | Card precision | Completeness accuracy | Span paragraphs | Underline F1 | Highlight F1 | Span F1 |
|---|---|---|---|---|---|---|---|---|---|
| overall | 410 | 38 | 0.921 | 0.897 | 1.000 | 61 | 0.976 | 0.928 | 0.965 |
| family:other-heuristic | 227 | 18 | 0.944 | 0.944 | 1.000 | 33 | 0.999 | 1.000 | 1.000 |
| family:verbatim | 153 | 20 | 0.900 | 0.857 | 1.000 | 23 | 0.859 | 0.695 | 0.808 |
| family:wiki-converted | 30 | 0 | — | — | — | 5 | 1.000 | — | 1.000 |
| format:LD | 98 | 12 | 1.000 | 1.000 | 1.000 | 10 | 1.000 | 1.000 | 1.000 |
| format:PF | 60 | 5 | 0.800 | 0.800 | 1.000 | 10 | 0.781 | 0.370 | 0.670 |
| format:Policy | 252 | 21 | 0.905 | 0.864 | 1.000 | 41 | 0.997 | 1.000 | 0.997 |
| source:camp | 252 | 21 | 0.905 | 0.864 | 1.000 | 41 | 0.997 | 1.000 | 0.997 |
| source:caselist | 98 | 12 | 1.000 | 1.000 | 1.000 | 10 | 1.000 | 1.000 | 1.000 |
| source:team | 60 | 5 | 0.800 | 0.800 | 1.000 | 10 | 0.781 | 0.370 | 0.670 |
| template:non-verbatim | 257 | 18 | 0.944 | 0.944 | 1.000 | 38 | 0.999 | 1.000 | 1.000 |
| template:verbatim | 153 | 20 | 0.900 | 0.857 | 1.000 | 23 | 0.859 | 0.695 | 0.808 |

### Labeled blind

A file labeled blind was corrected with the pre-label hidden. Its rows that differ from the
pre-label, beside the same figure for the other corrected files of its stratum (category and
template family), show whether accepting a default has inflated the scores. Files are named
by digest prefix, as `MANIFEST.md` names them.

| File | Stratum | Rows differing from the pre-label | Other files of its stratum |
|---|---|---|---|
| `bad8c9119196b60a` | camp, verbatim | 10 of 54 (0.185) | 17 of 135 (0.126), in 1 file |

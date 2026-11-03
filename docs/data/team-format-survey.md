<!-- docs-index: How the team formats its cards (sizes, highlight colours, cite layout), measured from its own files without reading their text -->
# Team card formatting survey

How the team formats its cards, measured from its own season folders in place by
`scripts/analyze_team_formatting.py`. It reads style and run formatting only: every `w:t`
is removed from a part before anything looks at it. No file name, path, school, team code,
debater name or document text appears here. The format profiles in
`config/format_profiles/` cite the lines of the summary below.

| | |
|---|---|
| Files analysed | 314 |
| Run on | 2026-10-26 |
| Folders excluded | `Opencaselist`, `Camp Files` |
| Selection | every `.docx` below the inputs, by rule; none chosen by hand |

Sizes are `w:sz` values in half-points. Counts of runs weigh a long file more than a short
one, so each table also says in how many files a value is the most common.

## Summary

Each line is the value most files favour, among the files that have one.

- Evidence highlight colour: `cyan`, most common in 142 of 240 files with highlighting
- Underlined evidence size: 22 half-points (11 pt), most common in 229 of 246 files with underlining
- Not-underlined evidence size: 16 half-points (8 pt), most common in 199 of 249 files with text that is not underlined
- Full cite size: 22 half-points (11 pt), most common in 192 of 247 files with cites
- Evidence paragraphs holding text at or below the shrink maximum: 33732 of 40253
- Cite paragraphs led by a short cite in the cite style: 3725 of 4901
- Short cite runs that are bold: 7051 of 8182
- Full cite runs that are bold: 1320 of 23094

## Files

| Season | Event | Files |
|---|---|---|
| 2024-25 | LD | 130 |
| 2024-25 | PF | 32 |
| 2025-26 | LD | 93 |
| 2025-26 | PF | 24 |
| 2025-26 | Policy | 3 |
| 2026-27 | LD | 15 |
| 2026-27 | PF | 3 |
| 2026-27 | Policy | 14 |

Skipped:

| Reason | Files |
|---|---|
| duplicate bytes | 3 |
| in an excluded folder | 2543 |
| no season or event in the folder names | 4 |
| not a readable .docx | 1 |

Template families, by the style survey's classifier:

| Family | Files |
|---|---|
| cardmirror | 27 |
| other-heuristic | 43 |
| verbatim | 234 |
| wiki-converted | 10 |

## Structural units

What the shared style profile resolves each paragraph's style to. A style id is named only
when it is published vocabulary; any other id is counted as `custom`.

| Unit | Paragraphs | Files | Outline levels | Style ids |
|---|---|---|---|---|
| POCKET | 419 | 167 | 0 (382), 9 (11), none (26) | `Heading1` (404), `TOCHeading` (11), `custom` (4) |
| HAT | 1532 | 194 | 1 (1517), none (15) | `Heading2` (1532) |
| BLOCK | 5002 | 240 | 2 (4987), none (15) | `Heading3` (5001), `custom` (1) |
| TAG | 8776 | 299 | 3 (8512), none (264) | `Heading4` (8742), `tag` (29), `Tag2` (5) |
| EVIDENCE | 2 | 1 | none (2) | `custom` (2) |
| ANALYTIC | 47 | 19 | 3 (45), none (2) | `Analytic` (34), `custom` (13) |
| UNDERTAG | 5 | 3 | none (5) | `Undertag` (5) |

## Cite block

4901 cite paragraphs, 3725 of them led by a run in
the cite character style (the short cite). Runs in the cite style:

| Short cite size | Runs |
|---|---|
| 26 half-points (13 pt) | 6293 |
| 22 half-points (11 pt) | 845 |
| 16 half-points (8 pt) | 804 |
| 28 half-points (14 pt) | 142 |
| 32 half-points (16 pt) | 34 |
| 14 half-points (7 pt) | 20 |
| 20 half-points (10 pt) | 19 |
| 10 half-points (5 pt) | 13 |
| 24 half-points (12 pt) | 6 |
| 21 half-points (10.5 pt) | 3 |
| 8 half-points (4 pt) | 2 |
| 18 half-points (9 pt) | 1 |

The rest of the cite paragraph (the full cite):

| Full cite size | Runs | Files where most common |
|---|---|---|
| 22 half-points (11 pt) | 18279 | 192 |
| 24 half-points (12 pt) | 3215 | 51 |
| 16 half-points (8 pt) | 1101 | 3 |
| 14 half-points (7 pt) | 111 | 0 |
| 20 half-points (10 pt) | 102 | 0 |
| 26 half-points (13 pt) | 85 | 1 |
| 10 half-points (5 pt) | 50 | 0 |
| 12 half-points (6 pt) | 48 | 0 |
| 18 half-points (9 pt) | 47 | 0 |
| 15 half-points (7.5 pt) | 12 | 0 |
| 6 half-points (3 pt) | 11 | 0 |
| 8 half-points (4 pt) | 11 | 0 |
| 28 half-points (14 pt) | 11 | 0 |
| 21 half-points (10.5 pt) | 6 | 0 |
| 17 half-points (8.5 pt) | 4 | 0 |
| 27 half-points (13.5 pt) | 1 | 0 |

## Evidence

40253 evidence paragraphs: the paragraphs after a cite, up to the next heading.

Underlined runs (the text that is read):

| Underlined size | Runs | Files where most common |
|---|---|---|
| 22 half-points (11 pt) | 358941 | 229 |
| 24 half-points (12 pt) | 27796 | 14 |
| 26 half-points (13 pt) | 2153 | 1 |
| 28 half-points (14 pt) | 1180 | 1 |
| 16 half-points (8 pt) | 951 | 0 |
| 14 half-points (7 pt) | 459 | 0 |
| 30 half-points (15 pt) | 375 | 0 |
| 4 half-points (2 pt) | 318 | 0 |
| 12 half-points (6 pt) | 271 | 0 |
| 18 half-points (9 pt) | 269 | 0 |
| 13 half-points (6.5 pt) | 232 | 0 |
| 32 half-points (16 pt) | 172 | 0 |
| 2 half-points (1 pt) | 148 | 0 |
| 21 half-points (10.5 pt) | 145 | 0 |
| 8 half-points (4 pt) | 65 | 0 |
| 36 half-points (18 pt) | 61 | 0 |
| 20 half-points (10 pt) | 50 | 1 |
| 10 half-points (5 pt) | 16 | 0 |
| 40 half-points (20 pt) | 6 | 0 |
| 48 half-points (24 pt) | 6 | 0 |
| 38 half-points (19 pt) | 4 | 0 |
| 6 half-points (3 pt) | 1 | 0 |
| 11 half-points (5.5 pt) | 1 | 0 |
| 15 half-points (7.5 pt) | 1 | 0 |
| 34 half-points (17 pt) | 1 | 0 |

Runs that are not underlined (condensed, where the team shrinks them):

| Not-underlined size | Runs | Files where most common |
|---|---|---|
| 16 half-points (8 pt) | 140662 | 199 |
| 14 half-points (7 pt) | 19224 | 15 |
| 22 half-points (11 pt) | 17938 | 25 |
| 12 half-points (6 pt) | 6144 | 2 |
| 24 half-points (12 pt) | 4810 | 4 |
| 10 half-points (5 pt) | 2416 | 1 |
| 8 half-points (4 pt) | 2326 | 0 |
| 6 half-points (3 pt) | 2080 | 0 |
| 4 half-points (2 pt) | 1982 | 1 |
| 2 half-points (1 pt) | 1149 | 1 |
| 26 half-points (13 pt) | 1084 | 0 |
| 18 half-points (9 pt) | 151 | 0 |
| 15 half-points (7.5 pt) | 141 | 0 |
| 21 half-points (10.5 pt) | 97 | 0 |
| 11 half-points (5.5 pt) | 90 | 0 |
| 20 half-points (10 pt) | 69 | 1 |
| 32 half-points (16 pt) | 25 | 0 |
| 28 half-points (14 pt) | 22 | 0 |
| 5 half-points (2.5 pt) | 6 | 0 |
| 36 half-points (18 pt) | 5 | 0 |
| 27 half-points (13.5 pt) | 2 | 0 |
| 19 half-points (9.5 pt) | 1 | 0 |
| 23 half-points (11.5 pt) | 1 | 0 |
| 29 half-points (14.5 pt) | 1 | 0 |
| 40 half-points (20 pt) | 1 | 0 |

Highlight colours on evidence runs:

| Colour | Runs | Files where most common |
|---|---|---|
| `cyan` | 94341 | 142 |
| `green` | 43085 | 68 |
| `yellow` | 14307 | 30 |
| `magenta` | 131 | 0 |
| `white` | 77 | 0 |
| `lightGray` | 9 | 0 |
| `red` | 4 | 0 |
| `black` | 1 | 0 |

Highlighted runs that are not underlined: 5098. Bold evidence runs: 129185.

## By season

The most common value in each season's runs.

| Season | Files | Highlight | Underlined size | Not-underlined size | Full cite size |
|---|---|---|---|---|---|
| 2024-25 | 162 | `cyan` | 22 half-points (11 pt) | 16 half-points (8 pt) | 22 half-points (11 pt) |
| 2025-26 | 120 | `cyan` | 22 half-points (11 pt) | 16 half-points (8 pt) | 22 half-points (11 pt) |
| 2026-27 | 32 | `cyan` | 22 half-points (11 pt) | 16 half-points (8 pt) | 22 half-points (11 pt) |

## Organization names in short cites

Not counted, and not countable here. Whether a short cite names an organization whole
(`Federal Office of ... 26`) or by its last word is a fact about the cite's words; the
style of the run that carries it is the same either way, and this survey does not read
words.

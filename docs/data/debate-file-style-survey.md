# Debate file style survey

What Word styles real debate files actually use, measured rather than assumed. The style
profile in [`style_profile.py`](../../packages/debate_core/src/debate_core/domain/style_profile.py)
and the heuristic classifier in
[`style_classifier.py`](../../packages/debate_core/src/debate_core/evidence/style_classifier.py)
are grounded in these numbers.

Produced by `scripts/survey_docx_styles.py`, which reads only style information — `w:t` is
never touched — against files that stay on the machine holding them and never enter this
repository.

| | |
|---|---|
| Files surveyed | 2066 |
| Run on | 2026-09-20 |
| Reporting threshold | a style is named only if it appears in 3 or more files |
| Corpus | the hsld26-0915 caselist snapshot, camp files, and one team's files across the 2024-25, 2025-26 and 2026-27 seasons |

No file names, schools, team codes, debater names or document text appear below, and none
are collected in the first place. Style ids longer than 40 characters are elided in the
middle: Word builds a style id by concatenating every name the style has ever had, and the
fragment in the middle is occasionally the first name of whoever created it.

## Template families

Each file lands in exactly one template family, decided from its style *references* rather
than its style *definitions*: most debate files define the whole Verbatim style set whether
they use it or not.

`cardmirror` files are Verbatim files that also carry CardMirror's `pmd-heading-` bookmark
ids, so they have been through that editor at least once. `wiki-converted` files define the
Verbatim styles and reference none of them — everything is direct formatting, which is what
the caselist wiki-to-docx conversion produces.

| Category | Files | verbatim | cardmirror | wiki-converted | other-heuristic | unreadable |
|---|---|---|---|---|---|---|
| camp | 110 | 31 (28%) | 75 (68%) | 0 (0%) | 4 (4%) | 0 (0%) |
| caselist | 1582 | 162 (10%) | 1228 (78%) | 48 (3%) | 144 (9%) | 0 (0%) |
| team | 374 | 276 (74%) | 0 (0%) | 10 (3%) | 87 (23%) | 1 (0%) |
| **all** | **2066** | **469 (23%)** | **1303 (63%)** | **58 (3%)** | **235 (11%)** | **1 (0%)** |

## Which style ids this report names

A style id is named below only if it is published vocabulary — Verbatim's and CardMirror's
own ids, Word's built-in ids, or the ids the Google Docs and wiki-to-docx converters emit —
or is one of those with Word's numeric de-duplication suffix on it (`Heading4` →
`Heading411`, `Emphasis` → `Emphasis1`). Every other id is counted and not named, because a
style id a person chose is a place a person's name ends up; the corpus this survey was
first run against contains styles named after individual debaters. The operator sees the
full list in the `--json` aggregate, which is not committed.

## Paragraph styles referenced in the body

`files` is how many files reference the style at least once; `references` is the total
number of paragraphs carrying it.

| Style id | Style name(s) | Files | References |
|---|---|---|---|
| `Heading4` | heading 4, Heading 4 | 1964 | 50934 |
| `Heading3` | heading 3, Heading 3 | 1564 | 11502 |
| `Heading2` | heading 2, Heading 2 | 1441 | 4463 |
| `Heading1` | heading 1, Heading 1 | 1384 | 2061 |
| `Analytic` | Analytic | 296 | 1766 |
| `NormalWeb` | Normal (Web) | 114 | 2507 |
| `ListParagraph` | List Paragraph | 99 | 574 |
| `Undertag` | Undertag | 41 | 128 |
| `BodyText` | Body Text | 8 | 1428 |
| `Title` | Title | 7 | 17 |
| `Header` | header | 5 | 19 |
| `CiteParagraph` | Cite Paragraph | 4 | 11 |
| `CardBody` | Card Body | 4 | 43 |
| `Footer` | footer | 4 | 9 |
| `tag` | %tag, tag | 4 | 29 |
| `Heading5` | heading 5 | 3 | 6 |
| `TOC2` | toc 2 | 3 | 9 |
| `TOC3` | toc 3 | 3 | 72 |
| `Tag2` | Tag2 | 3 | 5 |
| _(custom or team-specific ids, not named)_ | — | 4 distinct ids, 40 file references | — |
| _(below the reporting threshold)_ | — | 24 distinct ids | — |

## Character styles referenced in the body

| Style id | Style name(s) | Files | References |
|---|---|---|---|
| `StyleUnderline` | Style Underline | 1733 | 1916037 |
| `Style13ptBold` | Style 13 pt Bold | 1726 | 43978 |
| `Emphasis` | Emphasis | 1628 | 794529 |
| `Hyperlink` | Hyperlink | 437 | 5552 |
| `Heading4Char` | Heading 4 Char | 86 | 457 |
| `TitleChar` | Title Char | 33 | 3042 |
| `Strong` | Strong | 22 | 139 |
| `normaltextrun` | normaltextrun | 16 | 3656 |
| `FootnoteReference` | footnote reference | 12 | 13 |
| `AnalyticChar` | Analytic Char | 12 | 70 |
| `eop` | eop | 11 | 207 |
| `apple-converted-space` | apple-converted-space | 10 | 675 |
| `IntenseEmphasis` | Intense Emphasis | 7 | 973 |
| `CommentReference` | annotation reference | 6 | 13 |
| `Heading3Char` | Heading 3 Char | 6 | 212 |
| `PageNumber` | page number | 4 | 43 |
| `Heading1Char` | Heading 1 Char | 3 | 4 |
| `apple-style-span` | apple-style-span | 3 | 59 |
| _(custom or team-specific ids, not named)_ | — | 9 distinct ids, 72 file references | — |
| _(below the reporting threshold)_ | — | 48 distinct ids | — |

## Alias candidates: styles that inherit from a Verbatim style

A style defined with its own id but `basedOn` a Verbatim style is how template drift shows
up. Two shapes matter, and the profile handles them differently. Word's numeric
de-duplication (`Heading411`, `Emphasis1`) is mechanical, so the profile resolves it by
stripping the suffix. A style somebody named themselves is not mechanical, so the profile
resolves it by following `basedOn` to a style it does know — which is why the count below
matters more than any individual id.

| Verbatim style inherited from | Distinct ids | Files |
|---|---|---|
| `Heading1` | 57 | 1205 |
| `Heading2` | 26 | 519 |
| `Heading4` | 62 | 505 |
| `Heading3` | 19 | 248 |
| `Emphasis` | 8 | 160 |
| `Analytic` | 6 | 15 |
| `Heading1Char` | 2 | 2 |
| `Undertag` | 1 | 1 |
| `UndertagChar` | 1 | 1 |
| `Heading2Char` | 1 | 1 |
| `Heading4Char` | 1 | 1 |

Of those, the ones that are Word's numeric de-duplication of a style id we already know:

| Style id | basedOn | Resolves to | Files |
|---|---|---|---|
| `Heading411` | `Heading1` | `heading4` | 197 |
| `NoSpacing61` | `Heading1` | `nospacing` | 63 |
| `TOCHeading` | `Heading1` | `tocheading` | 47 |
| `TOCHeading1` | `Heading1` | `tocheading` | 33 |
| `Hat2` | `Heading2` | `hat` | 29 |
| `CITE` | `Heading2` | `cite` | 21 |
| `hat` | `Heading1` | `hat` | 13 |
| `Emphasis1` | `Heading1` | `emphasis` | 10 |
| `Heading101` | `Heading1` | `heading1` | 9 |
| `Analytic0` | `Analytic` | `analytic` | 8 |
| `Emphasis20` | `Emphasis` | `emphasis` | 7 |
| `CITE1` | `Heading2` | `cite` | 7 |
| `Header2` | `Heading1` | `header` | 6 |
| `Heading7` | `Heading1` | `heading7` | 5 |
| `Heading8` | `Heading2` | `heading8` | 5 |
| `Heading9` | `Heading3` | `heading9` | 5 |
| `CITE0` | `Heading2` | `cite` | 4 |
| `Analytic2` | `Heading4` | `analytic` | 4 |
| `Header1` | `Heading1` | `header` | 3 |
| `tag10` | `Heading2` | `tag` | 3 |
| `analytic0` | `Heading4` | `analytic` | 3 |

## Outline levels

Outline level is the only structural signal a file with no Verbatim styles carries, and it
is what the heuristic classifier keys on. Level 0 is Heading 1.

| Outline level | Paragraphs |
|---|---|
| 0 | 26 |
| 1 | 95 |
| 2 | 301 |
| 3 | 3055 |

## Highlight colours

`w:highlight` values, which the profile lists so the parser and the writer agree on what a
debater's highlighting means.

| Colour | Runs |
|---|---|
| `cyan` | 875876 |
| `green` | 349204 |
| `yellow` | 83912 |
| `lightGray` | 4326 |
| `magenta` | 3646 |
| `white` | 1872 |
| `red` | 1417 |
| `darkCyan` | 741 |
| `darkGray` | 576 |
| `black` | 52 |
| `blue` | 1 |

## Refreshing this report

```bash
uv run python scripts/survey_docx_styles.py \
    --input caselist=<newest hsld26 snapshot directory> \
    --input camp=<camp files directory> \
    --input team=<team files directory> \
    --min-files 3 \
    --corpus-description "<one line naming the corpus>" \
    --output docs/data/debate-file-style-survey.md \
    --json <a path outside this repository>
```

`--input` is repeatable. `CATEGORY=PATH` puts everything under `PATH` in one category; a
bare path takes its categories from its immediate subdirectories, the layout
[`scripts/cardmirror-roundtrip/`](../../scripts/cardmirror-roundtrip/README.md) uses. Point
`caselist` at the newest snapshot only: successive hsld26 snapshots are cumulative, so
surveying all of them counts most files several times.

The `--json` aggregate carries every style id, including the ones this report withholds.
It stays outside the repository. The command overwrites this file; read the diff before
committing it, because a style id is the one field here a person could have put a name in.

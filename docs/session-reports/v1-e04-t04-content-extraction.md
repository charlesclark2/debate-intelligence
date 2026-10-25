# Session report: v1-e04-t04-content-extraction

| | |
|---|---|
| Task | `v1-e04-t04-content-extraction` — Readable-text extraction (HTML + PDF) |
| Spec | [`plan_specs/v1/e04-article-retrieval/t04-content-extraction.yaml`](../../plan_specs/v1/e04-article-retrieval/t04-content-extraction.yaml) |
| Epic / release | `v1-e04-article-retrieval` / `v1.3` |
| Branch | `task/v1-e04-t04-content-extraction` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Checkpoint 1 of 3 (2026-10-25): rules proposed, nothing built yet.** As the PM's context asked,
this commit proposes the de-hyphenation rule and the running header and footer rule, with counts from
the synthetic PDF fixture, before any extractor code is written. The fixture builder and the PDF are
committed; the dependencies are declared in `pyproject.toml` and locked by the operator (licences below). The
session stops here for the PM's ruling on the two rules and on two transitive licences.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

### Proposed for the PM's ruling: the de-hyphenation rule

**Where it applies.** A line that ends in a hyphen-like character (hyphen-minus U+002D, hyphen U+2010,
soft hyphen U+00AD, en dash U+2013, em dash U+2014) straight after a non-space character, followed by
a line that continues the same paragraph. Those two lines are joined **with no space**, and the join
is recorded. A line ending in a dash after a space (`word -`) is not a join: it is an ordinary line
break, joined with a space like every other. The only question the rule answers is whether the
line-end character stays.

**The rule, in order:**

1. **Soft hyphen: dropped** (`SOFT_HYPHEN`). U+00AD is the typesetter's discretionary hyphen, printed
   only where a line breaks, so it is never part of the word.
2. **Not between two letters: kept** (`NOT_A_WORD_BREAK`). A digit or punctuation on either side, or a
   dash rather than a hyphen: `2019-|2024`, `COVID-|19`, `Paris–|London`.
3. **Letters on both sides: the document decides.** The two spellings are looked up as whole words
   elsewhere in the document's body text: after running headers and footers are removed,
   case-folded, and without counting the fragments next to any line-end break. A word is a run of
   letters with internal hyphens or apostrophes, so `state-of-the-|art` compares `state-of-the-art`
   with `state-of-theart`.
   * the hyphenated form appears and the joined form does not: **kept** (`HYPHENATED_FORM_IN_DOCUMENT`);
   * the joined form appears and the hyphenated form does not: **dropped** (`JOINED_FORM_IN_DOCUMENT`);
   * neither appears, or both do: **kept** (`UNDETERMINED`).

**When it can't tell, the hyphen stays.** Keeping it leaves every printed character on the page in
the text, and never makes a word the author did not write (`costeffective`). The cost is a broken
word left hyphenated (`resur-rection`), which a reader and v1-e03's verification can see from the
join record. Dropping it would make the opposite error silently, and that error changes a word.

**Every join is recorded** in `ExtractedContent`: paragraph index, character offset in that
paragraph, page number, the line-end character, whether it was kept, the decision above, and both
counts (hyphenated and joined forms found elsewhere). No dictionary or word list is used: it would be
language-specific, another dependency to version, and it still could not tell `re-cover` from
`recover`.

**Counts on the fixture** (`tests/fixtures/extraction/journal-article.pdf`, 13 line-end hyphens: 6
broken words, 6 real hyphens, 1 either spelling). Measured by a scratch prototype of the rule over the
builder's lines, not by hand:

| Break | Really | Found elsewhere (hyphenated / joined) | Decision | Result |
|---|---|---|---|---|
| `extinc-` / `tion` | broken word | 0 / 2 | `JOINED_FORM_IN_DOCUMENT`: dropped | right |
| `de-` / `extinction` | compound | 2 / 0 | `HYPHENATED_FORM_IN_DOCUMENT`: kept | right |
| `well-` / `intentioned` | compound | 0 / 0 | `UNDETERMINED`: kept | right |
| `conser-` / `vation` | broken word | 0 / 3 | `JOINED_FORM_IN_DOCUMENT`: dropped | right |
| `2019-` / `2024` | year range | (digits) | `NOT_A_WORD_BREAK`: kept | right |
| `long-` / `term` | compound | 2 / 0 | `HYPHENATED_FORM_IN_DOCUMENT`: kept | right |
| `co-` / `operation` | either spelling | 1 / 1 | `UNDETERMINED`: kept | the printed spelling |
| `bio` + U+00AD / `diversity` | broken word | (soft hyphen) | `SOFT_HYPHEN`: dropped | right |
| `popu-` / `lations` | broken word | 0 / 3 | `JOINED_FORM_IN_DOCUMENT`: dropped | right |
| `cost-` / `effective` | compound | 1 / 0 | `HYPHENATED_FORM_IN_DOCUMENT`: kept | right |
| `resur-` / `rection` | broken word | 0 / 0 | `UNDETERMINED`: kept | **broken word left hyphenated** |
| `envi-` / `ronmental` (pages 2 to 3) | broken word | 0 / 1 | `JOINED_FORM_IN_DOCUMENT`: dropped | right |
| `Okonkwo-` / `Hale` | compound name | 1 / 0 | `HYPHENATED_FORM_IN_DOCUMENT`: kept | right |

Dropped 5, kept 8 (4 on the document's evidence, 1 not a word break, 3 undetermined). Compounds
joined without their hyphen: **0**. Broken words left hyphenated: **1**.

The two simpler rules on the same 13 breaks:

| Rule | Compounds fused (a word changed) | Broken words left hyphenated |
|---|---|---|
| Proposed (above) | 0 | 1 (`resur-rection`) |
| Drop whenever letters are on both sides | 5 (`deextinction`, `wellintentioned`, `longterm`, `costeffective`, `OkonkwoHale`) | 0 |
| Keep always, except a soft hyphen | 0 | 5 (`extinc-tion`, `conser-vation`, `popu-lations`, `resur-rection`, `envi-ronmental`) |

These counts show what the rule does on a fixture written to exercise every branch, not how often each
branch fires in real papers. On a real article the share of `UNDETERMINED` breaks depends on how many
broken words appear again unbroken; that is a measurement to take in place on open-access PDFs,
never by committing one (Follow-up work).

The mutants the PM asked for on this rule: a compound joined without its hyphen (`HYPHENATED_FORM` or
`UNDETERMINED` dropping), and a broken word left split (a join that inserts a space, or a
`JOINED_FORM` that keeps the hyphen).

### Proposed for the PM's ruling: running headers, footers and page numbers

* **Edge zones.** The three lines nearest the top and the three nearest the bottom of each page, by
  position on the page. Nothing outside them is ever removed.
* **Running header or footer.** A line whose exact text (whitespace collapsed) is in an edge zone on
  two or more pages.
* **Page number.** After those are gone, the outermost remaining line at the top and at the bottom of
  each page. For each number in it, that number is masked and its offset from the page's position in
  the file is taken (`Page 2 of 3` on page 2 gives `Page # of 3`, offset 0; `102` on page 2 gives
  `#`, offset 100). The same masked text at the same offset, at the same edge, on two or more pages is
  a page number. That catches `Page N of M`, a bare `102`, and `Smith et al. | 102`.
* **Everything else stays, however short.** A line that appears once is body text. A one-page
  document has nothing to repeat, so nothing is removed from it, a lone page number included; that is
  the rule's stated limit.
* **Every removed line is recorded** in `ExtractedContent` with its page, its edge, the reason and its
  text, so the removal is visible to a reviewer.
* **Fixture counts:** 8 lines removed, 2 on page 1 and 3 each on pages 2 and 3: 2 running headers, 3
  running footers, 3 page numbers. Five short lines inside an edge zone stay because each appears
  once: page 1's masthead, `2. Methods`, `ronmental conditions that caused its loss.`, `4. Conclusion`,
  and `Received 3 March 2026; accepted 9 June 2026.`. The last is the outermost line left on page 3
  and holds a `3` on page 3 (offset 0), but no other page has its masked text, so it stays.
* **Known risk:** captions `Table 2` and `Table 3` as the outermost lines of pages 2 and 3 would read
  as page numbers. The record makes that visible if it happens.

### Paragraphs in a PDF

A new paragraph starts at an indented first line, a vertical gap larger than the page's usual line
spacing, or a change of font size. At a page break the last paragraph continues onto the next page
when it does not end in sentence-final punctuation and the next page's first body line is not
indented: that is how `envi-|ronmental` is joined across pages 2 and 3, with page 2's footer and page
3's header removed between them. Paragraph boundaries move only whitespace, never a word.

### Dependencies and their licences, as locked

Locked by the operator's `uv lock` (2026-10-25). Every licence below was read from the installed
package's own metadata (`importlib.metadata`: `License-Expression`, else `License`, else its licence
classifiers), at the version the lock holds.

| Package | Locked version | Licence (as declared) | Brought in by |
|---|---|---|---|
| `trafilatura` | 2.3.1 | Apache-2.0 | `extraction` extra |
| `readability-lxml` | 0.9 | Apache-2.0 | `extraction` extra |
| `pypdf` | 6.21.2 | BSD-3-Clause | `extraction` extra |
| `babel` | 2.18.0 | BSD-3-Clause | courlan |
| `chardet` | 5.2.0 | **LGPL** (classifier: LGPLv2 or later) | readability-lxml |
| `charset-normalizer` | 3.5.2 (was 3.5.1) | MIT | trafilatura and htmldate (both need `>=3.5.2`, hence the bump) |
| `courlan` | 1.4.0 | Apache-2.0 | trafilatura |
| `cssselect` | 1.3.0 | BSD | readability-lxml |
| `dateparser` | 1.4.3 | BSD-3-Clause | htmldate |
| `htmldate` | 1.11.0 | Apache-2.0 | trafilatura |
| `justext` | 3.0.2 | BSD-2-Clause | trafilatura |
| `lxml-html-clean` | 0.4.5 | BSD-3-Clause | readability-lxml, justext |
| `pytz` | 2026.5 | MIT | dateparser |
| `regex` | 2026.9.29 | Apache-2.0 AND CNRI-Python | dateparser |
| `tld` | 0.13.2 | **MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later** | courlan |
| `tzlocal` | 5.4.5 | MIT | dateparser |
| `tzdata` | 2026.5 | (not installed: locked only for `sys_platform == 'win32'`) | tzlocal |
| `lxml` | 6.1.3 (already locked) | BSD-3-Clause | trafilatura, readability-lxml |

Nothing is GPL-only or AGPL. Two need the PM's ruling. `chardet` 5.2.0 is LGPL-2.0-or-later, a
weak copyleft that is not GPL. `tld` 0.13.2 is offered under a choice of three licences, of which
the project would take MPL-1.1. Both are used unmodified, as installed libraries.

`pypdf` was chosen over `pdfminer.six` because it has no dependencies of its own, and because it
holds its own resource limits. Version 6.21.2 has `pypdf.Configuration`, with a 75 MB default
ceiling on each stream's decompressed output (FlateDecode, LZW, run-length, JBIG2) and caps on array
and dictionary sizes; the adapter can lower them alongside its own byte and page limits. The line
positions the rules need come from pypdf's text visitor.

### Smaller choices

* **The fallback minimum and the PDF limits are constructor parameters with defaults**, not settings:
  settings live in `debate_core.application`, outside this task's packages. ArticleService (t05) can
  pass them from settings.
* **All three HTML samples are synthetic**, the .gov one included, so no fetch is needed.

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

**Lock and install the extraction dependencies** (network; expected runtime about 1 minute). None of
`trafilatura`, `readability-lxml` or `pypdf` is in uv's cache, so the lock cannot be made offline.
Where: your Mac.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e04-t04-content-extraction
uv lock
uv sync --all-packages
git status --short
```

Success looks like: `uv lock` reports `Added pypdf`, `Added readability-lxml` and `Added trafilatura`
with their versions (and their dependencies), `uv sync` finishes without an error, and `git status`
prints only ` M uv.lock`. Paste the output back into the session; the session commits `uv.lock`.

Done 2026-10-25: 17 packages added (`trafilatura` 2.3.1, `readability-lxml` 0.9, `pypdf` 6.21.2 and
14 they need), `charset-normalizer` 3.5.1 to 3.5.2, `git status` showed only ` M uv.lock`.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

* **How often the de-hyphenation rule cannot tell, on real papers.** The fixture counts show the
  rule's behaviour, not its rates. Run in place over a sample of open-access PDFs, never committed:
  share of line-end hyphens per decision, and a hand check of the `UNDETERMINED` ones. Belongs with
  E04's real-corpus checks after t05 (the PM decides where).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

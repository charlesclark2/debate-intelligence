# Parser evaluation labels: labeling guide

This labeling guide says how to label a debate file for the parser evaluation
(`v1-e31-t05-parser-eval`), and how to settle the cases where two careful people could disagree.
The coach signs it off before it is used (the `labeling` node's manual criterion).

Each file here is `<digest>.jsonl` and labels one file listed in [`../manifest.json`](../manifest.json).
It holds **no text**: a unit and a card for each labeled paragraph, keyed by paragraph index and a
**keyed digest** of the paragraph's text — an HMAC under the operator's key, never a plain
SHA-256, which over a public corpus in a public repository would join straight back to the file.
The format is documented in
[`tests/evals/parser/labels_schema.py`](../../../../evals/parser/labels_schema.py).

## What you label: the sampling plan

You do not label every paragraph of every file. [`../sampling-plan.json`](../sampling-plan.json)
says which ones, and the tooling only ever shows you those:

* the **six PR-subset files in full** (435 rows) — they gate every pull request, so they cannot be
  partial;
* about **a quarter of every other file** (1,441 of 5,353 rows), in contiguous blocks of at least
  20 paragraphs.

That is 1,876 rows rather than 5,788. Blocks are contiguous because card-boundary accuracy needs
unbroken runs: a card split by a sampling gap cannot be scored at all. Which blocks were chosen is
fixed and recorded; it is not yours to change, and the worksheet simply starts and stops where the
plan does. **Row indices therefore jump** — a worksheet may run 0-19 and then 100-128. That is the
plan working, not a missing row.

If the plan is ever regenerated, every label made under the old one stops matching it, and the
baseline has to be re-measured. That is why it is generated once, before labeling starts.

## The one rule

**Label what the file is, not what the parser said.** The worksheet starts from the parser's
pre-labels only to save typing. A pre-label that goes in uncorrected is the parser grading its own
homework, so:

* every row gets looked at and marked `checked`. Import refuses a worksheet with a blank `checked`
  cell;
* the evaluation refuses a label file still marked `PRELABELED`;
* **the `text` column is never edited**, and neither is the text under the span markup. If a
  label only fits after changing the text, the label is wrong or the parser is. Import refuses an
  edited text.

When the parser is wrong, the label says what is right and the evaluation counts the miss. The
bug is filed against `v1-e31-t03`'s parser. Nobody patches the parser inside this task.

## Workflow

```bash
# 1. Seed pre-labels over the plan's rows (no text; kept in the repository while being corrected)
uv run python scripts/prelabel_docx.py prelabel --all

# 2. Write one file's worksheet OUTSIDE the repository; it holds paragraph text
uv run python scripts/prelabel_docx.py worksheet 9d0a74b9 --out-dir ~/parser-eval-worksheets

# 3. Correct it in Numbers or LibreOffice, save as CSV, then import it
uv run python scripts/prelabel_docx.py import 9d0a74b9 \
    --worksheet ~/parser-eval-worksheets/9d0a74b95ccf9269.csv --corrected-by coach

# 4. After the coach's end-to-end spot-check of a corrected file
uv run python scripts/prelabel_docx.py mark-reviewed 9d0a74b9 --reviewer coach
```

A file is named by any unambiguous prefix of its keyed digest — the first column of the table in
[`../MANIFEST.md`](../MANIFEST.md). Everything needs the digest key at
`~/.debate-intelligence/parser-eval-digest.key`; without it the tooling stops rather than falling
back to a plain digest.

Open the `.docx` beside the worksheet: the worksheet shows text, but a paragraph's *style*, its
underlining and highlighting are only visible in Word.

**Worksheets hold other programs' cards and sometimes names.** Keep them in one folder outside the
repository, never attach or upload them, and delete each one once its import succeeds. Only the
`.jsonl` it produces is committed. Excel rewrites some text when it opens a CSV (leading `=` or
`+`, long numbers, dates), which import will then refuse. Numbers and LibreOffice do not.

## Units

A paragraph gets exactly one unit.

| Unit | What it is | Usually looks like |
|---|---|---|
| `POCKET` | The outermost heading: an argument file inside a larger document | `Heading 1` |
| `HAT` | A section of a pocket | `Heading 2` |
| `BLOCK` | A block of cards read together, usually one argument or answer | `Heading 3` |
| `TAG` | The claim a card is read for, written above its cite | `Heading 4` |
| `CITE` | The citation paragraph under a tag: author, year, qualifications, source | Bold short cite ("Okonkwo 26") then the full cite |
| `EVIDENCE` | The card's quoted body | Underlined and highlighted runs, often shrunk text between |
| `ANALYTIC` | The debater's own analysis, not quoted from a source | `Analytic` style, or a `Heading 4` with no cite or body under it |
| `UNDERTAG` | A subordinate line under a tag that belongs to the same card | `Undertag` style, smaller than the tag |
| `OTHER` | Everything else: blank paragraphs, title pages, tables of contents, headers, page furniture, table cells, text boxes | |

Decide by **what the paragraph does**, not what style it carries. A non-Verbatim file has no
`Heading 4`, but its bold 13-point line above a cite is still a `TAG`. A Verbatim file's
`Heading 4` with nothing under it before the next heading is an `ANALYTIC`.

## Cards

A card is one tag, its undertags, its cite and its body. Give every paragraph of one card the same
number in the `card` column and leave it blank everywhere else. Numbers only need to be distinct
within a file; they need not be consecutive.

* **Where a card starts**: at its `TAG`. A card with no tag (common in wiki-converted disclosures)
  starts at its `CITE`.
* **Where a card ends**: at its last `EVIDENCE` paragraph. For a cite-only card, at its `CITE`.
* **A card cut by the end of a block is left unnumbered.** Label each paragraph's unit as usual,
  but leave `card` blank unless the whole card — tag, cite and body — lies inside the block you
  are labeling. A half-card cannot be scored, and numbering it would count as a miss something
  nobody can see. Import refuses a card that crosses a block edge.
* **Blank paragraphs** inside a card are `OTHER` with a blank `card`. The card's boundary is still
  its first and last numbered paragraph, so a blank line in the middle does not split it.
* **Headings and analytics are never inside a card.** An `ANALYTIC` between two cards ends the
  first card, and so does any heading.
* A card must have a `CITE` paragraph. A body with no cite and no tag above it is `EVIDENCE` with
  a blank `card`. It is a stray body, not a card.

`completeness`, on the first row of each card only:

| Value | When |
|---|---|
| `FULL` | Tag, cite and a body that runs from start to finish |
| `ABBREVIATED` | The body gives only its first and last words, with an ellipsis or "AND" marker between them. This is what open-source disclosure usually looks like |
| `CITE_ONLY` | A tag and cite with no body at all |

## Ambiguous conventions

**Undertags.** A line directly under a tag that qualifies it ("Impact: extinction", "Solves the
aff's internal link") is an `UNDERTAG` in the same card, whatever style it carries, provided the
card's cite comes after it. A line of the same kind *after* the body is an `ANALYTIC`, outside the
card.

**Analytics between cards.** A one-line argument between two cards with no cite of its own is an
`ANALYTIC`, even in `Heading 4`. If a `Heading 4` line is followed by a cite, it is a `TAG`, even
when it reads like analysis.

**Cite-only disclosures.** A caselist upload that lists `tag / cite / tag / cite` with no bodies
is a run of `CITE_ONLY` cards: each tag and the cite under it share a card number.

**Wiki-converted entries.** Converted disclosures often put the cite and the first-and-last words
in consecutive plain paragraphs: `CITE` then `EVIDENCE`, one card, `ABBREVIATED`. A line reading
only `AND` or `…` between the first and last words is part of the `EVIDENCE`.

**A cite split over two paragraphs** (short cite on one line, full cite on the next) is two `CITE`
paragraphs in one card.

**Card text in a table or text box** is `OTHER`, with a blank `card`. The parser does not read
cards out of tables, and the labels say where the text is, not where it should have been.

**Tracked changes.** Label the file as it reads with insertions accepted and deletions dropped,
which is what the worksheet's `text` shows.

**When unsure**, pick the reading a debater preparing against the file would take, and write the
case down here, so the next file is labeled the same way.

## Spans

About one labeled paragraph in five carries `underline` and `highlight` columns. Which ones is
decided by a hash of the file's digest and the paragraph index, not by anyone's choice. Each column shows the paragraph text
with `⟦` and `⟧` around every underlined or highlighted stretch. Move the marks until they match
the file. Do not change any other character.

* **Underline** means text a reader sees as underlined, however it is encoded: Verbatim's
  `Underline` style, a direct underline, or Verbatim's `Emphasis` style, which is underlined as
  well as bold. CardMirror files encode one underline two ways at once, and it still counts once.
* **Highlight** is any highlight colour. The colour is not labeled.
* Mark exactly the characters. Whether a space at the edge of a stretch is underlined is visible in
  Word with the cursor on it. Where it genuinely is not visible, leave the space out.
* The one-in-five sample is taken from the rows you are labeling, not from the whole file.
* A sampled row with no underline or highlight keeps its text with no marks. That is a label too:
  "nothing here".

## Coach review

The coach spot-checks at least three corrected files end to end (one team, one caselist, one
camp), against the `.docx`, and signs off on this guide. Each spot-checked file is then marked
`COACH_REVIEWED` with `mark-reviewed`. A disagreement found in review is fixed in the labels and,
if it was a convention question, written into this guide.

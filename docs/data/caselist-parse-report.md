<!-- docs-index: Counts from the operator-run full-corpus caselist parse, per caselist and environment -->
# Caselist parse report

The first full-corpus run of `debate-research caselist parse` over the caselist and camp sources the
2026-27 backfill imported (`v1-e31-t06-parse-pipeline`, criterion ac5). Counts only: no school, team
code, path, filename or card text appears here (`docs/policies/caselist-data-use.md`). The store
these runs write is described in [parsed-card-store.md](parsed-card-store.md).

**Status: run in dev and prod on 2026-10-10.** The operator ran the parse from the dev data
directory with the merged pipeline (#207), publishing to dev and then to prod. Each table below is
from that run's `--json` summary. The steps are in the task's session report under "Operator
follow-ups, revised". The PM recorded the figures at close-out.

**Re-parsed on 2026-10-11 under `2026.10.10-docx-2` and `card-fingerprint-v2`**, in dev and prod,
for `v1-e31-t09` (the parser's fixes) and `v1-e31-t08` (short-card matching). The sections down to
[What the refusals and the empty tags were](#what-the-refusals-and-the-empty-tags-were-v1-e31-t09)
describe the first parse and are kept as its record. The current figures are in
[The re-parse, 2026-10-11](#the-re-parse-2026-10-11).

**Re-parsed on 2026-10-16 under `2026.10.12-docx-3` and `card-fingerprint-v3`**, in dev and prod,
for `v1-e31-t12` (cites) and `v1-e31-t11` (card matching).
[Cites the parser missed or misread](#cites-the-parser-missed-or-misread-v1-e31-t12) says what that
parser reads differently, from a read-only run before the re-parse. The current figures are in
[The re-parse, 2026-10-16](#the-re-parse-2026-10-16).

## Versions

| | |
|---|---|
| Parser | `2026.09.20-docx-1` |
| Style profile | `2026.09.20-verbatim-1` |
| Fingerprints | `card-fingerprint-v1` |
| Version directory | `2026.09.20-docx-1` (first generation) |

## The corpus before the run

Distinct stored sources in each caselist's weekly manifests (the OpenEv release's for `openev`), by
format, counted read-only from the dev data directory's manifests on 2026-10-09. The full-archive
namespace is not part of the parse and is not counted.

| Caselist | Manifests | Sources | DOCX | PDF | Legacy DOC | Other | DOCX size |
|---|---|---|---|---|---|---|---|
| hsld26 | 14 | 4,461 | 4,360 | 62 | 0 | 39 | 525.6 MiB |
| hspf26 | 13 | 3,906 | 2,650 | 1,240 | 0 | 16 | 992.2 MiB |
| hspolicy26 | 13 | 2,657 | 2,629 | 18 | 0 | 10 | 687.8 MiB |
| openev | 1 | 102 | 102 | 0 | 0 | 0 | 53.8 MiB |
| **Total** | 41 | 11,126 | 9,741 | 1,320 | 0 | 65 | 2,259.4 MiB |

PDFs, legacy `.doc` files and other formats are recorded as `UNSUPPORTED`: an outcome, not a
failure, and counted on neither side of the failure rate.

## Dev

Run on 2026-10-10 from the dev data directory with `DEBATE_ENV=dev`, publishing to the dev evidence
bucket. Every run exited 0. The failure rate is failed over the sources tried that are not
unsupported, against the 5% default threshold. Wall-clock is the first run's `elapsed_seconds`:
parse, rebuild and publish.

| Caselist | Sources | Parsed | Unsupported | Failed | Failure rate | Cards | Clusters | Occurrences | Wall-clock |
|---|---|---|---|---|---|---|---|---|---|
| hsld26 | 4,461 | 4,354 | 101 | 6 | 0.14% | 67,914 | 12,102 | 77,537 | 518 s |
| hspf26 | 3,906 | 2,649 | 1,256 | 1 | 0.04% | 44,298 | 9,828 | 53,916 | 352 s |
| hspolicy26 | 2,657 | 2,610 | 28 | 19 | 0.72% | 87,556 | 18,366 | 100,314 | 747 s |
| openev | 102 | 98 | 0 | 4 | 3.92% | 7,288 | 5,467 | 7,288 | 106 s |
| **Total** | 11,126 | 9,711 | 1,385 | 30 | | 207,056 | | 239,055 | 1,723 s |

Unsupported by format, and failures by typed reason, per caselist:

| Caselist | PDF | Legacy DOC | Other | `MALFORMED_XML` | `NOT_A_ZIP` | `FORBIDDEN_XML_CONSTRUCT` | `COMPRESSION_RATIO_EXCEEDED` | Macro-enabled, timeout, worker crash, parser error |
|---|---|---|---|---|---|---|---|---|
| hsld26 | 62 | 0 | 39 | 5 | 1 | 0 | 0 | 0 |
| hspf26 | 1,240 | 0 | 16 | 0 | 0 | 1 | 0 | 0 |
| hspolicy26 | 18 | 0 | 10 | 0 | 0 | 19 | 0 | 0 |
| openev | 0 | 0 | 0 | 0 | 0 | 3 | 1 | 0 |

**Occurrences per card**, the check that the occurrence table holds one row per disclosure:
hsld26 1.14, hspf26 1.22, hspolicy26 1.15, openev 1.00. These are close to the disclosures per
DOCX source measured from the manifests before the run (1.15, 1.26, 1.19, 1.00), and under the 1.5
stop line. Cards per parsed DOCX: hsld26 15.6, hspf26 16.7, hspolicy26 33.5, openev 74.4.

The publish to dev, per caselist. Uploaded is one per-source file for every source, unsupported and
failed ones included, plus the three aggregates.

| Caselist | Uploaded | Skipped | Failed | Aggregates |
|---|---|---|---|---|
| hsld26 | 4,464 | 0 | 0 | 3 |
| hspf26 | 3,909 | 0 | 0 | 3 |
| hspolicy26 | 2,660 | 0 | 0 | 3 |
| openev | 105 | 0 | 0 | 3 |

The second run over the unchanged store, which must parse nothing and upload nothing. Its
`elapsed_seconds` is the rebuild and the publish's checksum checks alone. The PM's limit for filing
an incremental rebuild was 900 s per caselist, and none came close.

| Caselist | Attempted | Skipped | Uploaded | Elapsed |
|---|---|---|---|---|
| hsld26 | 0 | 4,461 | 0 | 348 s |
| hspf26 | 0 | 3,906 | 0 | 214 s |
| hspolicy26 | 0 | 2,657 | 0 | 460 s |
| openev | 0 | 102 | 0 | 60 s |

Sizes after the run: `occurrences.jsonl` is 50 MB (hsld26), 35 MB (hspf26), 66 MB (hspolicy26) and
4.4 MB (openev). The local `parsed/` directory is 5.8 GB. No run was stopped at the 8 GB memory line.

**Sample check, by eye.** Five randomly drawn parsed hsld26 sources were opened beside the first
five cards the store holds for each. Four looked right. In one, the second and third stored cards
were wrong: two cards with an empty tag, one `ABBREVIATED` and one `CITE_ONLY`, where the document
has none. This is a parser accuracy finding, followed up in `v1-e31-t09`. The tallies are recorded
here; the files and tags are not.

## Prod

Published on 2026-10-10 to the prod evidence bucket from the same dev data directory
(`DEBATE_ENV=prod`, `DEBATE_STORAGE__DATA_DIR` set to the dev directory, `--confirm-prod`). The dry
run showed 4,461 hsld26 sources skipped and 0 to parse. Nothing was parsed again. Every aggregate
was rebuilt to the same counts as dev, and every publish exited 0. The shell's variables were unset
afterwards.

| Caselist | Parsed this run | Store sources | Store cards | Store occurrences | Store clusters | Uploaded | Failed | Elapsed |
|---|---|---|---|---|---|---|---|---|
| hsld26 | 0 | 4,461 | 67,914 | 77,537 | 12,102 | 4,464 | 0 | 279 s |
| hspf26 | 0 | 3,906 | 44,298 | 53,916 | 9,828 | 3,909 | 0 | 202 s |
| hspolicy26 | 0 | 2,657 | 87,556 | 100,314 | 18,366 | 2,660 | 0 | 370 s |
| openev | 0 | 102 | 7,288 | 7,288 | 5,467 | 105 | 0 | 55 s |

`store ls parsed/hsld26/2026.09.20-docx-1/index.jsonl` against prod lists the object (1.6 MB).

## After `card-fingerprint-v2`

Every cluster count above is under `card-fingerprint-v1`. `v1-e31-t08-short-card-recall` changed
which cards share a cluster (`card-fingerprint-v2`; the exact fingerprints are the same), so the
`Clusters` columns change when the aggregates are next rebuilt. Sources, parsed counts, cards and
occurrence rows do not: nothing is parsed again.

**Status: rebuilt on 2026-10-11** by `v1-e31-t09`'s re-parse. The counts and the by-eye samples
(that task's criterion ac5) are in [After `card-fingerprint-v2`, measured](#after-card-fingerprint-v2-measured).
The preview below is kept as the record of what the old store suggested.

**A provisional preview, 2026-10-10.** Read-only: the stored cards of this report's
`2026.09.20-docx-1` store placed in memory under the new rules, and compared with the occurrence
table. Provisional because `v1-e31-t09` found that most cards this parse marked `ABBREVIATED` are
whole cards, which the re-parse will reclassify and cluster.

| Caselist | Cards | Clusters, `v1` | Clusters, `v2` | Clusters merged into another | Clusters divided | Largest cluster, `v1` | Largest cluster, `v2` | Exact fingerprints changed |
|---|---|---|---|---|---|---|---|---|
| hsld26 | 67,914 | 12,102 | 12,107 | 37 | 17 | 620 | 620 | 0 |
| hspf26 | 44,298 | 9,828 | 9,835 | 18 | 20 | 541 | 541 | 0 |
| hspolicy26 | 87,556 | 18,366 | 18,326 | 49 | 9 | 1,165 | 1,164 | 0 |
| openev | 7,288 | 5,467 | 5,466 | 1 | 0 | 21 | 21 | 0 |

No new cluster is made of more than four earlier ones. What each column means, and what the
figures do and do not show, is in that task's session report under "Corpus-scale check".

## What the run settled, and what it raised

* **No incremental rebuild yet.** The slowest rebuild was 460 s (hspolicy26). `v1-e34-t17` put
  the parse inside the weekly run, so every scheduled run now pays it; `v1-e31-t10` makes it
  incremental.
* **The failure-rate threshold and small caselists.** openev's four failures out of 102 are just under 4%.
  Two more bad files in a release that size cross 5% (six of 102 is 5.9%; five is 4.9%). An
  earlier version of this line said one more, which was the PM's arithmetic error. `v1-e34-t17`
  judges the rate only once a run has tried at least 100 sources.
* **23 files refused as `FORBIDDEN_XML_CONSTRUCT`**, mostly in policy, and 5 as `MALFORMED_XML`.
  Which construct, and whether it is safe to accept, is `v1-e31-t09`'s to find out.
* **A third of PF is PDF** (1,240 of 3,906 sources), so PF's parsed store covers two thirds of its
  disclosures. PDF parsing is filed as a post-V1 task.
* **Each parser version is a full copy.** A version bump writes a new 5.8 GB directory beside the
  old one, locally and in both buckets. Retention of superseded version directories is noted for a
  later task.

## What the refusals and the empty tags were (`v1-e31-t09`)

Diagnosed on 2026-10-10 by reading the dev data directory's blobs and parsed store in place,
read-only, with scratch scripts that wrote nothing there. Counts and construct names only. The fixes
are in parser version `2026.10.10-docx-2`; the store this report describes is unchanged until the
operator re-parses, and the "after" columns below are what that parser produced over the same
sources in a read-only run, not what a store holds yet.

### The 30 failures, by reason

| Reason | Caselist | Files | The construct or defect | Part | Verdict |
|---|---|---|---|---|---|
| `FORBIDDEN_XML_CONSTRUCT` | hspolicy26 | 19 | The words `system "` (16 files) or `system '` (3) in a paragraph's text. No `DOCTYPE`, no entity declaration, no external reference | `word/document.xml`, inside `w:t` | Parser defect. Read from `2026.10.10-docx-2` |
| `FORBIDDEN_XML_CONSTRUCT` | openev | 3 | The words `public '` (2 files), or `system '` and `system "` (1), in a paragraph's text | `word/document.xml`, inside `w:t` | Parser defect. Read from `2026.10.10-docx-2` |
| `FORBIDDEN_XML_CONSTRUCT` | hspf26 | 1 | The words `public '` in a paragraph's text | `word/document.xml`, inside `w:t` | Parser defect. Read from `2026.10.10-docx-2` |
| `MALFORMED_XML` | hsld26 | 3 | Four U+0001 control characters written raw into the text. XML 1.0 forbids them, so the part is not well-formed | `word/document.xml`, inside `w:t` | Genuinely broken. Still refused |
| `MALFORMED_XML` | hsld26 | 2 | One U+0002 control character and 26 U+FFFE noncharacters written raw into the text | `word/document.xml`, inside `w:t` | Genuinely broken. Still refused |
| `NOT_A_ZIP` | hsld26 | 1 | A gzip stream holding a JSON document, 44 KB, disclosed as a DOCX. That is the shape of CardMirror's native `.cmir` format, not a Word package | The whole file | Genuinely not a DOCX. Still refused |
| `COMPRESSION_RATIO_EXCEEDED` | openev | 1 | One entry expands 278-fold against a limit of 200: a 1.9 MB page thumbnail stored as 7 KB | `docProps/thumbnail.emf` | The guard working as set. Still refused; see below |

**The 23.** The refusal's scan looked for a document type or entity declaration, and also for the
words `SYSTEM` or `PUBLIC` followed by a quotation mark anywhere in a part, in any letter case.
Those words are markup only inside a declaration. In a paragraph they are prose, such as a card
that says a system "works". All 23 document parts are well-formed UTF-8, none declares a document
type, and every match is inside the text of a `w:t` element. No other part of the 23 packages
matched. The scan now looks for `<!DOCTYPE` and `<!ENTITY` only, which is the one place XML allows
an external identifier, and a part that carries a document type in any encoding is refused after
parsing. Across the 9,738 distinct DOCX sources that open as a zip, every document part is UTF-8
and none begins with a document type declaration.

**The 5 malformed files** are all exports of one program. Each package has the same eight parts,
with `docProps/custom.xml` and no `docProps/app.xml`, and its custom properties name CardMirror's
document id. 2,703 sources share that shape and 2,691 of them parse. In these five the exporter
wrote a character into the text that XML does not allow, so no conforming XML parser reads the
part. The three files with U+0001 are well-formed once those four characters are taken out, which
shows the characters are the whole defect there. Taking them out would be editing evidence text,
which the parser never does. From 2026.10.18-docx-4 the parser replaces each such character with
U+FFFD, one for one, by decision (v1-e31-t15); nothing is taken out.

**The compression ratio.** Of the 9,738 distinct DOCX sources that open as a zip, 9,732 have no
entry above 50-fold, five have one between 50 and 100, and this file is the only one above 100.
The refused entry is the page thumbnail Word saves beside a document, which the parser never
opens. The file is ordinary, but 278 against 200 is not a small margin, and nothing else in the
corpus comes within half of the limit, so the limit is left where it is.

### Counts before and after, from the same sources

| Caselist | DOCX sources | Parsed before | Parsed after | Failed before | Failed after | Cards before | Cards after |
|---|---|---|---|---|---|---|---|
| hsld26 | 4,360 | 4,354 | 4,354 | 6 | 6 | 67,914 | 64,678 |
| hspf26 | 2,650 | 2,649 | 2,650 | 1 | 0 | 44,298 | 42,906 |
| hspolicy26 | 2,629 | 2,610 | 2,629 | 19 | 0 | 87,556 | 82,565 |
| openev | 102 | 98 | 101 | 4 | 1 | 7,288 | 8,056 |
| **Total** | 9,741 | 9,711 | 9,734 | 30 | 7 | 207,056 | 198,205 |

The 23 newly read files hold 2,212 cards (328 in hspf26, 807 in hspolicy26, 1,077 in openev). The
seven failures left are the five `MALFORMED_XML` and the `NOT_A_ZIP` in hsld26 and the
`COMPRESSION_RATIO_EXCEEDED` in openev.

### Cards with an empty tag

The store holds 15,528 cards with an empty tag, 7.5% of its cards. Every one is the empty string;
none is whitespace.

| Caselist | `FULL` | `ABBREVIATED` | `CITE_ONLY` | Empty tags | Of cards |
|---|---|---|---|---|---|
| hsld26 | 1,554 | 2,227 | 821 | 4,602 | 6.8% |
| hspf26 | 2,688 | 585 | 372 | 3,645 | 8.2% |
| hspolicy26 | 2,995 | 3,192 | 695 | 6,882 | 7.9% |
| openev | 231 | 112 | 56 | 399 | 5.5% |
| **Total** | 7,468 | 6,116 | 1,944 | 15,528 | 7.5% |

5,947 of the 9,711 parsed sources hold at least one. Three rules produced them:

| Rule | Empty-tag cards | What happened |
|---|---|---|
| A cite that arrives after a body starts a new card with no tag | 14,387 | A paragraph inside a card's body was classified as a cite, by `heuristic-cite-line-author-year` (6,826), `heuristic-wiki-cite-entry` (6,182), `verbatim-cite-run-style` (1,243) or a cite paragraph style (136). The card was closed there and the rest stored as another with no tag |
| A cite with no card open above it starts one with no tag | 1,102 | A cite straight after a block, hat or pocket heading, an analytic, or loose text. The file gives it no tag |
| A blank line in `Heading 4` opens a card with an empty tag | 39 | The blank heading also demoted the real tag above it to an analytic, so the card lost a tag the document has |

The first is the operator's sample. Its second and third stored cards were the middle and the end
of the first card's body: two paragraphs of small print that each hold an ellipsis and a name with
a year, which the wiki cite-entry heuristic takes for a cite entry. The document has one card
there, not three.

In `2026.10.10-docx-2` a cite the classifier *guessed*, arriving inside an open body, stays in that
body when it is formatted as body (small print throughout, or highlighted) and does not open with a
bold name. 11,912 paragraphs are re-read that way. A blank line in any heading, tag, cite, analytic
or undertag style is `OTHER`: 7,986 paragraphs. Expected after a re-parse:

| Caselist | `FULL` | `ABBREVIATED` | `CITE_ONLY` | Cards with no tag | Of cards |
|---|---|---|---|---|---|
| hsld26 | 1,086 | 0 | 270 | 1,356 | 2.1% |
| hspf26 | 1,755 | 0 | 152 | 1,907 | 4.4% |
| hspolicy26 | 739 | 0 | 355 | 1,094 | 1.3% |
| openev | 79 | 0 | 19 | 98 | 1.2% |
| **Total** | 3,659 | 0 | 796 | 4,455 | 2.2% |

No card is `ABBREVIATED` in this table because none is anywhere after the re-parse: see
[`ABBREVIATED`, by shape](#abbreviated-by-shape).

Those 4,455 are written as `"tag": null`, never as an empty string. They are cards whose cite came
from a cite style (1,658), from the cite-line heuristic and looked like a cite (2,398), or from the
wiki heuristic outside small print (399). Whether each is a second card under one tag or one more
split is for the labelled evaluation to say; [parsed-card-store.md](parsed-card-store.md#a-card-with-no-tag)
says how a reader should treat them.

What the change did not touch: of the cards stored now, 186,634 have the same paragraph range under
the new parser, and every one of those has the same tag. 183,417 also have the same evidence text
and the same cite. The other 3,217 are cards that
[a later rule](#a-cards-body-filed-as-its-cite) reached: their first body paragraph was stored in
the cite and is in the evidence text now. 1,630 of the 186,634 have a different section path,
because 1,847 stored cards carry an empty string in their path from a blank heading line, and none
does afterwards. Completeness changes on 18,227 of them, in two ways only, each described below:
15,776 from `ABBREVIATED` to `FULL` and 2,451 from `CITE_ONLY` to `FULL`.

### `ABBREVIATED`, by shape

The first parse called a card `ABBREVIATED` when an ellipsis marker (`…`, `...`, `[…]`, `[...]` or
`***`) appeared anywhere in its body or its cite: 22,443 cards. `2026.10.10-docx-2` decides it from
the shape of a disclosure of first and last words, and the rule was taken from these counts. They
are over the 198,205 cards the new parser reads from the same sources, measured read-only on
2026-10-10. Words are whitespace-separated.

The counts were taken twice: before [the rule of the next section](#a-cards-body-filed-as-its-cite),
which moves 3,365 paragraphs out of cites and into bodies, and again with it in place. The figures
below are the second set. The first set had 19,402 bodies with a marker where this has 22,053, and
gave the same answer at every bound.

Under the old rule 23,842 of those cards would be `ABBREVIATED`: 22,053 whose body holds a marker,
and 1,789 whose body holds none and whose cite does.

**Body length, by how many markers the body holds** (22,053 cards):

| Body words | 1 marker | 2 | 3 to 5 | 6 or more | All |
|---|---|---|---|---|---|
| 20 or fewer | 0 | 0 | 0 | 0 | 0 |
| 21 to 30 | 6 | 0 | 1 | 0 | 7 |
| 31 to 60 | 32 | 0 | 0 | 0 | 32 |
| 61 to 100 | 69 | 2 | 7 | 0 | 78 |
| 101 to 200 | 344 | 41 | 16 | 2 | 403 |
| 201 to 500 | 2,471 | 443 | 155 | 36 | 3,105 |
| 501 to 1,000 | 3,872 | 743 | 574 | 106 | 5,295 |
| Over 1,000 | 6,194 | 2,291 | 2,984 | 1,664 | 13,133 |
| **All** | 12,988 | 3,520 | 3,737 | 1,808 | 22,053 |

For comparison, 10,668 of the 173,898 bodies with no marker are 100 words or fewer (6.1%), against
117 of these 22,053 (0.5%). A body with an ellipsis is, if anything, longer than one without.

**Where the marker sits**, in the 12,988 bodies with one marker, as the share of the body's words
before it:

| Before the marker | 0 to 9% | 10s | 20s | 30s | 40s | 50s | 60s | 70s | 80s | 90s |
|---|---|---|---|---|---|---|---|---|---|---|
| Cards | 691 | 1,148 | 1,700 | 1,476 | 1,556 | 1,704 | 1,050 | 1,050 | 1,259 | 1,354 |

It sits anywhere, as an omission in running text does. In 68 the marker opens or closes the body (1
opens, 67 close), so it joins nothing.

**The words either side**, in the 12,920 one-marker bodies with words on both sides, by the longer
of the two sides. Cumulative:

| Longer side, at most | 12 | 15 | 20 | 30 | 40 | 50 | 60 | 80 | 100 | 150 | 200 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Cards | 0 | 0 | 6 | 15 | 39 | 56 | 60 | 128 | 205 | 506 | 874 |

The shortest longer side in the corpus is 17 words. The 38 one-marker bodies of 60 words or fewer
are a handful of texts disclosed several times each, and by their paragraph counts and lengths they
are whole short cards with an omission.

**The distribution does not separate, because there is no second population.** A disclosure of
first and last words would show as a cluster of short bodies with one marker and a few words either
side. There is none: not one body has a single marker with 15 words or fewer on both sides. What
the old rule marked is one population, whole cards, with a thin lower tail of whole short cards.

**The rule, chosen on the conservative side:** a body is `ABBREVIATED` when it holds exactly one
marker, has words on both sides of it, and no more than **twelve** on either side. A marker in the
cite decides nothing.

* **Exactly one** marker: one joins a beginning to an end; two or more leave things out of a
  quotation. 9,065 bodies hold two or more, and all but 13 of those are over 120 words.
* **Words on both sides:** a marker at either end joins nothing.
* **Twelve** is the middle of the only gap there is. Below it are the disclosures we have a model of:
  the convention is a card's first and last few words, and the profile's own examples have three to
  nine a side. Above it is everything the corpus holds, from 17 up. Any bound from 9 to 16 gives the
  same answer on this corpus. Raising it to 20 would call 6 cards abbreviated, to 30 15, to 50 56,
  and nothing tells those from any other short card.

**Before and after, per caselist:**

| Caselist | Stored: `FULL` | `ABBREVIATED` | `CITE_ONLY` | After: `FULL` | `ABBREVIATED` | `CITE_ONLY` |
|---|---|---|---|---|---|---|
| hsld26 | 57,057 | 8,418 | 2,439 | 63,949 | 0 | 729 |
| hspf26 | 40,319 | 2,972 | 1,007 | 42,506 | 0 | 400 |
| hspolicy26 | 74,902 | 10,524 | 2,130 | 81,529 | 0 | 1,036 |
| openev | 6,563 | 529 | 196 | 7,967 | 0 | 89 |
| **Total** | 178,841 | 22,443 | 5,772 | 195,951 | 0 | 2,254 |

The card totals differ between the two halves because the empty-tag fix merged split cards, as
above, and `CITE_ONLY` falls because of the rule in the next section. To see the completeness rule
alone, take the new parser's 198,205 cards and apply each rule to them:

| Caselist | `ABBREVIATED` to `FULL` | `FULL` to `ABBREVIATED` |
|---|---|---|
| hsld26 | 9,086 | 0 |
| hspf26 | 3,473 | 0 |
| hspolicy26 | 10,593 | 0 |
| openev | 690 | 0 |
| **Total** | 23,842 | 0 |

Of the 23,842, 22,053 held a marker in the body and 1,789 only in the cite. This rule does not
touch `CITE_ONLY`: 2,254 either way. Among the 186,634 stored cards whose paragraph range is the
same under the new parser, 15,776 go from `ABBREVIATED` to `FULL`.

**So the corpus as it stands holds no abbreviated disclosure in a card's body**, and
`v1-e31-t08`'s abbreviation linking will find nothing to link by that route after the re-parse.
That is what the files hold: these caselists disclose open-source documents, which are whole cards.

### A card's body filed as its cite

Added to `2026.10.10-docx-2` after the two rules above, and measured the same way. Before it,
2,902 of the 4,731 `CITE_ONLY` cards held a cite paragraph of more than 100 words: whole cards,
2,713 of them with a tag, with their body in the cite field.

**The defect.** The wiki cite-entry heuristic takes any paragraph that holds an ellipsis and a name
with a year for a cite, at any length. The cite-line heuristic takes any paragraph of 400
characters or fewer that opens with a capitalised word and a year. The empty-tag rule above keeps
such a paragraph in its card once a body is open. The *first* body paragraph has no body open
before it, so it was added to the card's cite. A card whose whole body is that one paragraph came
out `CITE_ONLY`: thousands of characters in `full_cite`, and no evidence text for anything to
fingerprint or cluster.

**The rule.** A cite the classifier *guessed*, arriving while a card is open and has no body yet,
is the body's first paragraph when all of these hold:

* **it is formatted as body**, in the same sense as above: highlighted, or small print throughout,
  and not opening with a bold name;
* **no run carries the cite character style.** A cite style never moves, whatever its length;
* **the card already has a cite.** With no cite before it, only length can say where a cite would
  end: the paragraph must be longer than 2,000 characters and must not open with a name and a year;
* **it is not a line in the middle of a cite:** a paragraph of 2,000 characters or fewer with
  another cite directly below it is left where it is.

A guess that arrives with no card open is left alone. Read as body it would belong to no card.

**The bound of 2,000 characters**, from the 772 paragraphs the wiki heuristic makes the first cite
under a tag. A paragraph is marked as a cite by its author when it carries the cite character style
or opens with a name and a year:

| Characters | Paragraphs | Marked as a cite | Formatted as body |
|---|---|---|---|
| 1,000 or fewer | 258 | 194 | 6 |
| 1,001 to 1,517 | 81 | 74 | 10 |
| 1,518 to 2,678 | 35 | 0 | 34 |
| 2,679 or more | 398 | 32 | 323 |

* **Against cite styles.** The classifier calls a paragraph a cite by its character style up to
  1,000 characters, the profile's own bound, so the 139,012 such cites end at 999. The 1,414
  paragraphs in a cite *paragraph* style at the head of a card have no such bound, and the longest
  is 1,427 characters.
* **It separates.** Paragraphs marked as cites run up to 1,517 characters and stop. The next one
  is at 2,679, and from there they are whole cards written as one paragraph behind a name. Between
  the two, all but one of the 35 are formatted as body.
* **2,000 is in the gap, on the conservative side.** Any bound from 1,518 to 2,678 moves no
  paragraph the corpus marks as a cite. 1,518 would move 11 more paragraphs than 2,000 does, and
  they are left alone.
* **In characters,** because the classifier's two cite bounds are.

**What it moved**, over the same 9,734 parsed sources: 3,365 paragraphs.

| Rule id on the paragraph | Guess it overrode | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|---|
| `assembly-cite-guess-after-card-cite` | wiki cite entry | 1,225 | 398 | 783 | 85 | 2,491 |
| `assembly-cite-guess-after-card-cite` | cite line | 62 | 152 | 298 | 25 | 537 |
| `assembly-cite-guess-longer-than-a-cite` | wiki cite entry | 168 | 97 | 65 | 7 | 337 |

3,007 of the 3,365 are highlighted. Of the 2,491, 2,156 are longer than 2,000 characters. With a
body open one paragraph earlier, the empty-tag rule takes 40 more guesses that follow one of these.

**`CITE_ONLY`, per caselist:**

| Caselist | Before | After | Cards that gained evidence text |
|---|---|---|---|
| hsld26 | 1,906 | 729 | 1,178 |
| hspf26 | 849 | 400 | 449 |
| hspolicy26 | 1,807 | 1,036 | 773 |
| openev | 169 | 89 | 80 |
| **Total** | 4,731 | 2,254 | 2,480 |

* **2,480 cards gain evidence text where they had none**, 2,445 of them with a tag. 1,721 gain more
  than 1,000 words and 40 gain 100 or fewer. In 885 more cards, which already had a body, its first
  paragraph comes back from the cite.
* **No card is `ABBREVIATED` afterwards either.**
* **Card totals rise by 9**, to 198,205, and so do cards with no tag, to 4,455. In 9 cards the
  paragraph that now opens the body is followed by a real cite, so the card ends there and the cite
  starts a card with no tag: two cards under one tag. In the seven where the cite follows directly,
  the paragraph is highlighted and between 5,673 and 16,871 characters long.
* **Every card the rule does not reach is unchanged in every field:** 194,831 cards compared field
  by field against the parser without the rule. The other 3,374 are the 3,365 it reached and the 9
  split off them.
* **Of the cards it reached,** the 3,356 that keep their paragraph range keep their tag, undertag,
  section path and provenance, and every line of the old cite and body is still in the new cite or
  body. No card loses a short cite: all 2,324 that had one keep it. The 337 re-read under a tag
  with no cite had none, and their `full_cite` is now empty.

**What it left alone**, among guesses formatted as body and standing before any body:

| Left as a cite | Paragraphs |
|---|---|
| A cite line as the first cite under a tag: too short to be anything else | 342 |
| A wiki entry as the first cite under a tag, 2,000 characters or fewer | 24 |
| Carries the cite character style | 22 |
| A guess over 2,000 characters with no card open | 19 |
| A guess of 2,000 characters or fewer with no card open | 50 |
| Between the card's cite and another cite, and short enough to be a cite entry | 11 |
| A first paragraph over 2,000 characters that opens with a name and a year | 4 |

**What the counts cannot settle.**

* **A small-print line under the cite.** 358 of the 3,365 are small print with no highlighting. 218
  of those are lines of 400 characters or fewer that open with a word and a number, sit directly
  under the card's cite and are followed by more body. They read as the body's first line. A cite's
  second line set in small print, with no bold opening, would look the same, and 9 of the 218 hold
  a URL. The labelled evaluation is what can say.
* **460 `CITE_ONLY` cards still hold a cite paragraph of more than 100 words**, down from 2,902;
  in 388 of them it is a guess, down from 2,828. Across all cards, 764 cite paragraphs from the
  wiki heuristic are over 100 words, down from 3,515, and 295 are over 1,000 words, down from
  2,058. Most of what is left is not formatted as body: it opens with a bold name, or sits at
  reading size with nothing highlighted, which is how a card written as one paragraph behind its
  cite looks. The rest are in the table above.
* **A short wiki entry that really is a first-and-last-words disclosure stays `CITE_ONLY`.** At
  most 84 paragraphs from that heuristic are 40 words or fewer. Splitting an entry into its cite
  and its words is a model question, filed separately.

### What this raised and did not change

* **The classifier lets go of a cite character style past 1,000 characters.** 53 of the 69 first
  wiki cites between 1,001 and 1,500 characters carry that style: real cites, too long for the
  style rule, that the wiki heuristic happens to catch because they hold an ellipsis. One without
  an ellipsis falls through to body text. That is the profile's bound and the classifier's rule,
  not the assembly's, and it is not changed here.
* **The labelled evaluation cannot yet arbitrate.** Two of its 30 files are corrected by a person,
  both team files with no untagged card. On those 60 paragraphs the blank-line rule raised tag
  precision from 0.714 to 1.000, every card boundary stayed where it was, and completeness is
  right on 4 of 4 matched cards before and after each of the three rules.

## The re-parse, 2026-10-11

Run by the operator from the dev data directory on 2026-10-11, after `v1-e31-t08` and `v1-e31-t09`
merged: one re-parse covers both. It wrote a new version directory and published it to dev, then to
prod. Counts only, as everywhere in this report.

| | |
|---|---|
| Parser | `2026.10.10-docx-2` |
| Fingerprints | `card-fingerprint-v2` |
| Parsed-store schema | 2 (a card with no tag is `null`) |
| Version directory | `2026.10.10-docx-2` (first generation) |
| Superseded | `2026.09.20-docx-1`, schema 1, byte for byte unchanged by the run |

**The dry run reads oddly, and is right.** For a new parser version it shows `new_version: false`
and `superseded: null`. Both fields describe a new generation of the same parser version
(`--reparse`, or a profile change), not a new parser version, which starts a directory of its own.
`v1-e31-t16` makes the dry run say a new directory will be started and which it supersedes.

### Dev

Every run exited 0. Wall-clock is the run's `elapsed_seconds`: parse, rebuild and publish.

| Caselist | Sources | Parsed | Unsupported | Failed | Failure rate | Cards | Occurrences | Clusters | Uploaded | Wall-clock |
|---|---|---|---|---|---|---|---|---|---|---|
| hsld26 | 4,461 | 4,354 | 101 | 6 | 0.14% | 64,678 | 73,743 | 10,712 | 4,464 | 492 s |
| hspf26 | 3,906 | 2,650 | 1,256 | 0 | 0% | 42,906 | 52,156 | 9,327 | 3,909 | 277 s |
| hspolicy26 | 2,657 | 2,629 | 28 | 0 | 0% | 82,565 | 94,422 | 16,562 | 2,660 | 611 s |
| openev | 102 | 101 | 0 | 1 | 0.98% | 8,056 | 8,056 | 5,864 | 105 | 86 s |
| **Total** | 11,126 | 9,734 | 1,385 | 7 | | 198,205 | 228,377 | 42,465 | 11,138 | 1,465 s |

* **Failures: 30 before, 7 now.** hsld26's 5 `MALFORMED_XML` and 1 `NOT_A_ZIP`, and openev's 1
  `COMPRESSION_RATIO_EXCEEDED`, which `v1-e31-t09` found genuine. The 23
  `FORBIDDEN_XML_CONSTRUCT` refusals are gone: hspf26 and hspolicy26 parse every DOCX source.
* **Unsupported** is unchanged: 1,320 PDF and 65 other, by format as in the first parse.
* **Cards: 207,056 before, 198,205 now**, with the cards `v1-e31-t09` found were not cards the
  documents hold gone.
* **Every occurrence row** is schema 2 and `card-fingerprint-v2`. No record in the new directory
  holds `"tag":""`.

**Completeness and tags.** No card is `ABBREVIATED`: `v1-e31-t09` decides it from the disclosure's
shape, and no card in the corpus has that shape. Every figure matches the session's read-only
prediction.

| Caselist | `FULL`, tagged | `FULL`, no tag | `CITE_ONLY`, tagged | `CITE_ONLY`, no tag | `ABBREVIATED` |
|---|---|---|---|---|---|
| hsld26 | 62,863 | 1,086 | 459 | 270 | 0 |
| hspf26 | 40,751 | 1,755 | 248 | 152 | 0 |
| hspolicy26 | 80,790 | 739 | 681 | 355 | 0 |
| openev | 7,888 | 79 | 70 | 19 | 0 |
| **Total** | 192,292 | 3,659 | 1,458 | 796 | 0 |

Cards with no tag: 4,455, against 15,528 cards with an empty tag in the first parse.

**The second run**, which must parse and upload nothing, did neither: `attempted` 0, `skipped`
equal to the source count, `uploaded` 0 for each caselist. Its elapsed time is the rebuild alone
under this parser and fingerprint, and it is the figure `v1-e34-t17` sized the weekly parse stage
from.

| Caselist | Elapsed, 2026-10-11 | Elapsed, first parse's second run (2026-10-10) |
|---|---|---|
| hsld26 | 314 s | 348 s |
| hspf26 | 193 s | 214 s |
| hspolicy26 | 473 s | 460 s |
| openev | 71 s | 60 s |
| **Total** | 1,051 s | 1,082 s |

**Sample check, by eye.** The hsld26 file whose second and third stored cards were wrong in the
first parse's check now holds 10 cards, the first five `FULL`. All five tags match the document:
5 of 5 right.

### Prod

Published on 2026-10-11 from the same dev data directory (`DEBATE_ENV=prod`,
`DEBATE_STORAGE__DATA_DIR` set to the dev directory, `--confirm-prod`). The dry run showed nothing
to parse and all 4,461 hsld26 sources skipped. Every publish exited 0 with nothing parsed again, and
the shell's variables were unset afterwards.

| Caselist | Store sources | Store parsed | Store cards | Store occurrences | Store clusters | Uploaded | Failed |
|---|---|---|---|---|---|---|---|
| hsld26 | 4,461 | 4,354 | 64,678 | 73,743 | 10,712 | 4,464 | 0 |
| hspf26 | 3,906 | 2,650 | 42,906 | 52,156 | 9,327 | 3,909 | 0 |
| hspolicy26 | 2,657 | 2,629 | 82,565 | 94,422 | 16,562 | 2,660 | 0 |
| openev | 102 | 101 | 8,056 | 8,056 | 5,864 | 105 | 0 |

Every figure equals dev's.

### After `card-fingerprint-v2`, measured

`scripts/compare_card_clusters.py counts` with `--before-rules` at the commit before
`v1-e31-t08`: the same stored cards placed by the matching rules before and after that task. Run
read-only on the dev data directory on 2026-10-11.

| Caselist | Cards | Clusters before | Clusters after | Merged into another | Divided | Most absorbed by one | Largest before | Largest after | Exact fingerprints changed | Newly linked to a full card |
|---|---|---|---|---|---|---|---|---|---|---|
| hsld26 | 64,678 | 10,676 | 10,712 | 9 | 21 | 3 | 620 | 620 | 0 | 0 |
| hspf26 | 42,906 | 9,310 | 9,327 | 6 | 18 | 2 | 543 | 543 | 0 | 0 |
| hspolicy26 | 82,565 | 16,566 | 16,562 | 16 | 11 | 2 | 1,173 | 1,172 | 0 | 0 |
| openev | 8,056 | 5,865 | 5,864 | 2 | 1 | 2 | 22 | 22 | 0 | 0 |

* **No sign of a false merge.** No cluster absorbed more than three others, no exact fingerprint
  changed, and every card is in both placements. The largest clusters are unchanged except
  hspolicy26's, which shed one card and one distinct text.
* **No abbreviated card newly links, because none exists.** With no card `ABBREVIATED`,
  `v1-e31-t08`'s linking rules have nothing to act on in the real corpus, and their gain is proven
  on the labelled sets alone. Real abbreviations may sit in one-paragraph wiki entries
  (`v1-e31-t13`).
* **More clusters were divided than merged.** Short bodies that the old rules joined through the
  banding now join only when every longer body holding them is in one cluster.

**By-eye samples**, judged by the operator one pair at a time, tallies only:

| Sample | Pairs | Same card | Different card | Unsure |
|---|---|---|---|---|
| Newly in one cluster (ac5) | 20 | 17 | 0 | 3 |
| Divided (`--divided`), of 81 divided pairs | 10 | 9 | 0 | 1 |

* **ac5 is met.** No newly joined pair is two different cards. A first draw of 20 was judged, but
  its tally was not kept; the table is a second draw from the same saved comparison. One of the
  first draw's unsure pairs was a card whose only paragraph is a cite, read as body text and stored
  `FULL` (`v1-e31-t12`).
* **Most divisions were wrong.** In 9 of 10 sampled divided pairs the two cards are the same card,
  so the short-body rule costs recall where the longer copies are themselves split. On the real
  corpus `card-fingerprint-v2` gains a few groupings and loses about as many, all small.
  `v1-e31-t11` diagnoses the 81 divided pairs and the largest clusters.

### The divided pairs and the largest clusters, diagnosed (`v1-e31-t11`)

`scripts/compare_card_clusters.py diagnose`, run by the `v1-e31-t11` session on 2026-10-12,
read-only on the dev data directory, over the `card-fingerprint-v2` occurrence table of
`2026.10.10-docx-2` as stored. Counts only. It reads the table's cluster ids and places nothing, so
it took 8 to 59 s a caselist for the cuts and under 30 s for the largest clusters alone.

**What the diagnosis counts.** A body is a *cut* of another when the other is at least as large,
holds its first and last five-word runs, and holds nine-tenths of its five-word runs (or, for a
body under 64 words, holds it but for one word). The diagnosis lists every body with such a
container *outside its own cluster*, and names the limit that kept it out. Short is under 64 words.

| Bodies with a container outside their cluster | hsld26 | hspf26 | hspolicy26 | openev | All |
|---|---|---|---|---|---|
| Distinct full texts read | 15,203 | 13,504 | 22,527 | 6,372 | 57,606 |
| ... of which short | 593 | 505 | 555 | 117 | 1,770 |
| **Long** cut, containers in one cluster: the banding never paired them | 789 | 712 | 1,370 | 209 | 3,080 |
| **Long** cut, containers in more than one cluster | 115 | 162 | 180 | 26 | 483 |
| **Short** cut, witnesses in more than one cluster | 25 | 31 | 12 | 3 | 71 |
| **Short** cut, under a quarter of the smallest body that holds it (`MIN_CUT_SHARE`) | 77 | 74 | 113 | 8 | 272 |
| **Short** cut, one witness cluster, within the share, and still apart | 16 | 10 | 14 | 0 | 40 |
| ... because its containers are nested copies in several clusters | 12 | 9 | 9 | 0 | 30 |
| ... because the container first by fingerprint is over the share | 2 | 1 | 5 | 0 | 8 |
| ... because another short body of its cluster points elsewhere | 2 | 0 | 0 | 0 | 2 |
| **Short** body nine-tenths inside a body that lacks one of its ends | 9 | 7 | 9 | 1 | 26 |
| **Short** cut whose ends more than eight clusters hold (`MAX_CONTAINER_CLUSTERS`) | 1 | 1 | 0 | 0 | 2 |
| Total | 1,032 | 997 | 1,698 | 247 | 3,974 |
| Set aside: bodies in a cluster with a copy that every outside container also holds | 478 | 601 | 565 | 34 | 1,678 |

*Witnesses* are containers counted once when they hold one another: a cut inside a copy and
inside the card that copy was cut from has one witness, the copy.

**The 81 divided pairs.** The rules before `v1-e31-t08` merged a short body with a container
whenever the banding paired the two. The diagnosis finds exactly 81 short cuts that the banding
pairs with a container outside their cluster: 45, 23, 12 and 1. That is the count of divided pairs
above, and for openev, the one caselist where the session could compute the earlier placement, the
one divided pair is the one such cut. Why each is still apart under `v2`:

| Short cuts the banding pairs with an outside container | hsld26 | hspf26 | hspolicy26 | openev | All |
|---|---|---|---|---|---|
| Witnesses in more than one cluster | 17 | 12 | 5 | 0 | 34 |
| One witness cluster, within the share, and still apart | 19 | 6 | 5 | 0 | 30 |
| Under a quarter of the smallest body that holds it | 3 | 2 | 2 | 0 | 7 |
| Ends held by more than eight clusters | 4 | 1 | 0 | 0 | 5 |
| Nine-tenths inside a body that lacks one of its ends | 2 | 2 | 0 | 1 | 5 |
| Total | 45 | 23 | 12 | 1 | 81 |

24 of the 81 (19 in hsld26, 5 in hspf26) are in a cluster with a copy that the outside body also
holds, and are counted here by what would keep them out were that copy not there.

* **The hypothesis holds for about seven in ten.** Of the 57 not set aside, 44 have containers in
  more than one cluster, and in all 44 those clusters read as one card that was split: some
  container of each shares at least half of the smaller body's text with one of the other. None
  reads as two different cards. 21 of the 44 are nested, 23 are not.
* **What split the longer copies**, for those 44 (a cut can count under more than one): the two
  copies pass the Jaccard or containment threshold and the banding never paired them, 19; they
  share at least half and are under both thresholds, 25; the smaller copy is itself a short body
  the short-body step left out, 13.
* **`MIN_CUT_SHARE` is not what divided most pairs:** 7 of 81.
* **Long copies split far more often than short ones.** 3,563 long texts are a cut of a body in
  another cluster, against 411 short ones. The banding pairs a cut with its container about nine
  times in ten when the cut is half of it, and about one time in eight when it is a quarter. Of
  the 3,080 with one container cluster, 41 are half or more of their smallest container, 1,065
  a quarter to a half, 1,332 a tenth to a quarter and 642 under a tenth.

**The largest clusters, from the inside.** Three per caselist, largest first.

| | hsld26 1 | hsld26 2 | hsld26 3 | hspf26 1 | hspf26 2 | hspf26 3 | hspolicy26 1 | hspolicy26 2 | hspolicy26 3 | openev 1 | openev 2 | openev 3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Cards | 620 | 365 | 354 | 543 | 296 | 281 | 1,172 | 581 | 560 | 22 | 21 | 18 |
| Distinct texts | 48 | 40 | 15 | 74 | 40 | 75 | 166 | 50 | 20 | 14 | 14 | 14 |
| Words, smallest text | 66 | 343 | 81 | 1,441 | 132 | 193 | 72 | 70 | 302 | 1,251 | 146 | 93 |
| Words, median | 560 | 1,126 | 102 | 6,147 | 477 | 1,032 | 650 | 561 | 790 | 2,114 | 329 | 666 |
| Words, largest | 1,467 | 5,294 | 254 | 7,697 | 2,846 | 2,484 | 3,843 | 1,161 | 2,964 | 4,016 | 1,448 | 1,161 |
| Pairs of texts | 1,128 | 780 | 105 | 2,701 | 780 | 2,775 | 13,695 | 1,225 | 190 | 91 | 91 | 91 |
| ... sharing nothing | 169 | 177 | 0 | 0 | 38 | 288 | 6,409 | 91 | 0 | 0 | 37 | 0 |
| ... sharing under half of the smaller | 234 | 161 | 0 | 27 | 55 | 170 | 448 | 66 | 6 | 18 | 2 | 3 |
| ... sharing half or more | 725 | 442 | 105 | 2,674 | 687 | 2,317 | 6,838 | 1,068 | 184 | 73 | 52 | 88 |
| Texts sharing nothing with the most-read text | 11 | 26 | 0 | 0 | 1 | 1 | 127 | 0 | 0 | 0 | 5 | 0 |
| Cards those texts carry | 54 | 214 | 0 | 0 | 1 | 2 | 755 | 0 | 0 | 0 | 9 | 0 |
| Texts holding two smaller texts that share nothing | 31 | 1 | 0 | 0 | 1 | 51 | 92 | 38 | 0 | 0 | 7 | 0 |
| Texts inside two larger texts that share under half | 20 | 0 | 0 | 0 | 10 | 5 | 41 | 8 | 0 | 0 | 0 | 1 |

* **hspolicy26's largest cluster is not one passage.** 6,409 of its 13,695 pairs of texts have no
  five-word run in common, and 127 of its 166 texts, carrying 755 of its 1,172 cards, share
  nothing with its most-read text. Yet it is one connected group when only texts sharing half or
  more are joined. It is a chain: 92 texts each hold two smaller texts that share nothing with
  each other, and 41 are inside two larger texts that share under half.
* **The merges run through bodies that hold several parts more than through shared fragments.**
  Whether such a cluster is one long source cut at many extents, which a person might call one
  card, or several cards merged, counts cannot say. `sample --largest` and `--least-alike` are for
  that (`v1-e31-t11`, criterion ac2, the operator's).
* **Five of the twelve have no pair of texts that shares nothing**, among them hspf26's largest,
  whose texts are 1,441 to 7,697 words: bodies the length of a whole file, parsed as one card and
  near-identical to each other.

**What `v1-e31-t11` changed: `card-fingerprint-v3`.** Two corrections to the short-body step. A
short cut inside nested copies joins the smallest of them, and its size is compared with the
smallest body that holds it, not the one first by fingerprint. The session's estimate of the
effect, made by applying the corrected step to the stored `v2` clusters without recomputing the
banding (5 to 33 s a caselist), and its one full preview, openev (66 s):

| | hsld26 | hspf26 | hspolicy26 | openev |
|---|---|---|---|---|
| Clusters that merge into another, estimated | 18 | 10 | 17 | 0 |
| New clusters made of several, estimated | 17 | 10 | 13 | 0 |
| Most earlier clusters in one new cluster, estimated | 3 | 2 | 3 | 1 |
| Earlier clusters divided, estimated | 0 | 0 | 0 | 0 |
| Largest cluster, cards, before and estimated after | 620, 620 | 543, 543 | 1,172, 1,179 | 22, 22 |
| Full preview: merged, divided, exact fingerprints changed | not run | not run | not run | 0, 0, 0 |

* **It joins the cut to a copy of its card, not to the body the earlier rules joined it to.** The
  two longer copies are still two clusters, so a comparison against the rules before `v1-e31-t08`
  will still count most of these earlier clusters as divided, into one part fewer.
* **Long bodies are matched as before.** Joining long cuts the way short ones are joined would
  take 1,232 of the long cuts above, those with one witness and within the share. 944 of them
  share text with every text of the cluster they would join, and for 481 that cluster is a single
  text; 288 would be put in a cluster with at least one text they share nothing with. That feeds
  the same chains as the largest clusters, so it waits for the by-eye sample.

**After the rebuild under `card-fingerprint-v3`:** measured on `2026.10.12-docx-3`, in
[Card matching under `card-fingerprint-v3`, measured](#card-matching-under-card-fingerprint-v3-measured-v1-e31-t11).
Everything above is from `2026.10.10-docx-2`.

## Cites the parser missed or misread (`v1-e31-t12`)

`v1-e31-t09` and the operator's sample of the 2026-10-11 re-parse left five questions about cites.
Each was counted on 2026-10-12 by reading the dev data directory's blobs and its
`2026.10.10-docx-2` store in place, read-only, with scratch scripts that wrote nothing there:
the stored cards for the "before" figures, and the old and the new parser run side by side in one
process over the same bytes for everything else. Counts, lengths, formatting flags and rule ids
only. The stored directory's own counts and the old parser's agree on every figure both give.

**Status: the rules are in parser `2026.10.12-docx-3`, and the store was re-parsed with it on
2026-10-16** ([The re-parse, 2026-10-16](#the-re-parse-2026-10-16)). Every "after" figure below is
what that parser produced over the 9,741 DOCX sources in the read-only run before it. Over those
sources the stored figures equal it exactly.

### The five shapes

| | Shape | In the corpus | Verdict |
|---|---|---|---|
| 1 | A sentence the two cite guesses take for a cite | 686 cite lines open with a word no author is called, such as *In 2019*; 460 guessed cite entries are longer than 2,000 characters | Defect. Fixed for 457 lines that do not open in bold and for 335 long entries |
| 2 | A cite in the cite character style past 1,000 characters | 1,221 paragraphs with the style on a name and a year at their head: 811 read as nothing, 329 as body text, 81 as cites only because they hold an ellipsis | Defect. Fixed |
| 3 | A card with no cite | 33,624 tagged cards, not 337. 21,585 have a line under the tag that was read as nothing | Defect in part: the cite is in the file and was not read. Fixed for 9,193 cards. A cite on the tag line, or missing from the file, is correct output |
| 4 | A bracketed cite that ends in the cutter's initials | 85,173 paragraphs write a name and year and then one bracket to the end; 8,131 were not read as cites. 866 more open with the bracket; 304 of those stand where a cite stands and were not read | Defect. Fixed, except in a highlighted paragraph or one in a paragraph style |
| 5 | A short small-print line directly under a cite | 218 | Correct output for at least 193. At most 25 may be a second line of the cite. Left |

### 1. A sentence taken for a cite

**The cite-line guess** reads a capitalised word followed by two or four digits as an author and a
year, in a line of 400 characters or fewer. About 5,400 lines in the corpus open instead with a
word that opens a sentence: *In*, *The*, *A*, *Since*, *From*, *By*, *Between* and *About* are the
most frequent, in that order. `v1-e31-t09`'s assembly rules already re-read about 4,950 of them as
body, because they are small print or highlighted. 686 were still cites: 526 that do not open in
bold and 160 that do.

`2026.10.12-docx-3` holds a written-out list of such words. A line that opens with one, and not in
bold, is not a cite line.

| | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|
| Lines no longer cites | 51 | 121 | 257 | 28 | 457 |

* **What they become:** 236 are underlined or highlighted and are body by that; 95 are prose; 18
  are small print; 108 are short, plain and unformatted, which the classifier reads as nothing.
* **Left: 232 lines.** 160 open in bold, which is how a cite is written, and what they are cannot
  be told by formatting. 72 are written in capitals: the list keeps case, so that an acronym such
  as *WHO 24* stays an author, and a sentence set in capitals is the price.
* **Not on the list:** months, seasons and the short words that are also surnames (*May*, *March*,
  *Winter*, *An*, *So*, *To*, *Page*, *Law*). 29 lines that open with a month and do not open in
  bold stay cites. Taking one of those from a real cite would cost a card its cite.

**The wiki cite-entry guess** takes any paragraph that holds an ellipsis and a name with a year, at
any length. Of its 1,080 cites, 460 are longer than 2,000 characters, the bound `v1-e31-t09`
measured for a cite entry. `v1-e31-t09` re-reads such a paragraph as body only when it is
formatted as body, and a body's first words are often bold.

| Guessed cite entries over 2,000 characters | Before | After |
|---|---|---|
| No cite style, no name and year in the first 300 characters | 336 | 16 |
| No cite style, a name and year within the first 300 characters, not at the front | 67 | 63 |
| Opens with a name and a year | 41 | 22 |
| Carries a cite character style | 16 | 21 |
| **All** | 460 | 122 |

Past 2,000 characters, a guess with no cite style and no name and year in its first 300
characters is now body wherever a card is open, whatever its formatting: 335 paragraphs (254 after
the card's cite, 56 inside a body, 25 under a tag with no cite). 220 cards that were `CITE_ONLY`
with their body in the cite are `FULL`.

* **Why 300.** Of the 403 long guesses that neither carry a cite style nor open with a name and a
  year, 336 have their first name and year further in than 300 characters: prose that mentions a
  source somewhere. 18 have it within 80 and 49 between 81 and 300. Those 67 are left, because a
  card written as one paragraph behind a full name looks the same.
* **Left: 122.** The 16 with no card open would belong to no card if re-read. The rest are cards
  written as one paragraph behind their cite, which is a model question (`v1-e31-t13`).
* **Five of the 21 that carry a cite style were body text before.** `v1-e31-t09` holds a guess
  that carries a cite-style run where it is, at any length. In five cards the paragraph above such
  a guess was a long styled cite read as body, which opened the body, so the guess stayed in it.
  That cite is read as a cite now, the guess stands first, and it is held as cite text: the five
  cards go from `FULL` to `CITE_ONLY` with their body in the cite. It is the earlier rule in a
  place it did not reach before, and it is left as that task had it accepted.

**Cards with no tag that start at one of the two guesses** were 2,797 (2,398 at a cite line and 399
at a wiki entry) and are 2,341 (2,046 and 295).

### 2. A cite in the cite character style, past the profile's bound

The classifier reads a paragraph as a cite from a run in the cite character style up to the
profile's 1,000 characters, so that body text carrying the style for emphasis is not a cite. Past
that it let go. `v1-e31-t09` saw this through the 53 styled cites the wiki guess happened to catch.
Counted directly, at least 1,639 paragraphs past 1,000 characters carry the style:

| Read as | Before | After |
|---|---|---|
| Nothing | 865 | 109 |
| Body text | 664 | 348 |
| A cite | 101 | 1,173 |
| An analytic | 9 | 9 |

(Paragraphs whose styled share rounds to nothing are not in this table; the rule's own count below
is exact.)

Past the bound, a paragraph is now a cite when the style marks a name and a year that start within
its first 40 characters, nothing in it is highlighted, and it is 4,000 characters or shorter.

| | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|
| Paragraphs read by the rule | 407 | 118 | 611 | 85 | 1,221 |

* **They are cites by what they hold.** 1,219 of the 1,221 name a credential. 1,203 sit under a
  tag with a card's body below them. 811 had been read as nothing, 329 as the body's first
  paragraph, and 81 as cites by the wiki guess.
* **Why the head, and 40.** Of the 1,279 unhighlighted paragraphs past the bound that carry the
  style and sit directly under a tag, 1,143 have a name and a year starting within their first 40
  characters. Of the 84 that open in the style inside a body, none has.
* **Why 4,000.** The longest such paragraph is 3,283 characters and none is longer, so 4,000 is
  above every one the corpus holds.
* **Left:** 26 paragraphs with a styled name and year at the head and highlighting. 12 sit under a
  tag with a body below, which is a cite whose credentials a debater highlighted to read; 8 sit
  under a tag with nothing below, which is a card written as one paragraph; 6 are elsewhere.
  Formatting does not tell the first two apart. And 109 paragraphs that carry the style are still
  read as nothing.

### 3. A card with no cite

`v1-e31-t09` counted 337 cards that have a tag and no cite: the ones its own rule re-read from a
guess. That is one corner of the shape. **33,624 tagged cards in the store have no cite**, 17% of
all cards:

| | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|
| Tagged cards with no cite, stored | 7,269 | 17,663 | 7,612 | 1,080 | 33,624 |
| After | 5,294 | 12,318 | 6,053 | 766 | 24,431 |

What sits directly under the tag of such a card:

| Under the tag | Before | After |
|---|---|---|
| A line read as nothing, opening with a name and a year | 6,738 | 122 |
| A line read as nothing, a name and year within its first 40 characters | 5,611 | 5,396 |
| A line read as nothing, opening with a bracket | 2,558 | 2,570 |
| A line read as nothing, no name and year at its head | 6,561 | 6,448 |
| A line in a paragraph style that resolves to nothing | 117 | 116 |
| The body, opening with a name and a year | 2,996 | 814 |
| The body, a name and year within its first 40 characters | 1,887 | 1,804 |
| The body, no name and year at its head | 7,156 | 7,161 |

* **Where the cite was.** In 21,585 cards a line under the tag was read as nothing, and in at
  least 4,883 more the cite was read as the body's first paragraph. The cite-line guess stops at
  400 characters, and a cite that gives its author's credentials runs past that.
* **The tag line** holds a name and a year in 2,343 of the 33,624. The file gives those cards no
  cite paragraph. The parser leaves the tag as it is, and that is correct output: splitting a tag
  is a model question.
* **Of the 337,** 300 had a line under the tag read as nothing and 17 had a name and a year on the
  tag line and nothing else. 113 have a cite after the change.

`2026.10.12-docx-3` reads a line of 401 to 2,000 characters as a cite line when it **opens in bold
with a name and a year** and nothing in it is highlighted.

| | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|
| Paragraphs read by the rule | 1,637 | 5,570 | 1,017 | 202 | 8,426 |

* **They are cites by what they hold and where they are.** 7,873 sit under a tag and 7,821 of
  those have a card's body below. 8,394 name a credential or hold a link. 6,299 had been read as
  nothing and 2,127 as body text.
* **The bound.** 8,023 such paragraphs sit directly under a tag: 5,916 run to 600 characters, 1,266
  to 800, 458 to 1,000, 293 to 1,517, 47 to 2,000 and 43 past it. They thin out with no gap, so
  the bound is the 2,000 `v1-e31-t09` measured for a guessed cite entry.
* **333 follow a body and 211 have no card open.** Those start a card with no tag, as any cite
  does: a second card under one tag, whose body had been joined to the card above, or a card in a
  file that writes no tags. The other 9 are a second line under the card's cite.
* **Left:** 593 that open in bold with a name and a year and are highlighted, 60 past 2,000
  characters, and the 7,200 cards above with a name and a year a few words in, behind a first name
  or a title. The last is the largest thing this task leaves, and it is a formatting question.

### 4. A bracketed cite that ends in the cutter's initials

The operator's sample held a card whose only paragraph was such a cite, stored `FULL` with the
cite as its evidence text. It is the commonest way the corpus writes a cite: a name and a year,
then everything else in one bracket, then what the cutter signs.

| A name and year, then one bracket to the end, 2,000 characters or fewer | Before | After |
|---|---|---|
| Read as a cite | 77,042 | 83,843 |
| Read as nothing | 5,216 | 6 |
| Read as body text | 1,622 | 31 |
| Read as body text, highlighted | 344 | 344 |
| In a paragraph style that resolves to nothing, or to a heading | 832 | 832 |
| Read as an analytic | 117 | 117 |

It was read whenever it carried a cite style or was 400 characters or shorter, and otherwise as
nothing, or as body when a pasted link left an underline in it. Two rules take it now: the bold
rule above, and for a line that does not open in bold, **a name and a year followed by one bracket
that runs to the end but for a signature of 30 characters or fewer** (223 paragraphs).

* **The signature.** Of the 82,928 such paragraphs the parser already read as cites, 72,064 have 10
  characters or fewer after the closing bracket and 77,042 have 30 or fewer. What follows is
  initials in either case, a name, two of either, behind slashes, a dash or a bar. Past 30
  characters it is the rest of the cite.
* **Square or round,** counted so that a bracket inside the bracket closes only itself.

**A cite written wholly inside a bracket** opens with the bracket, so nothing that reads the front
of a line sees its name and year. 866 paragraphs of 2,000 characters or fewer are one bracket to
the end with a name and a year in their first 40 characters. A reference in brackets inside a
source's own text has the same shape, so where it stands decides:

| Where | Read as a cite before | After |
|---|---|---|
| Under a tag or under the card's cite, before any body | 136 of 440 | 420 of 451 |
| Inside a body | 4 of 395 | 4 of 395 |
| With no card open | 1 of 31 | 1 of 20 |

284 paragraphs are re-read as cites: 151 as a second line under the card's cite and 133 under a
tag.

**Cards that are only a cite:** 14 stored `FULL` with the cite as their evidence text are
`CITE_ONLY`, and 48 more had lost their tag to an analytic because nothing under it was read as a
cite or a body. They are tagged `CITE_ONLY` cards now.

### 5. A short small-print line directly under a cite

`v1-e31-t09` re-reads a guessed cite line as the body's first line when it is small print, sits
under the card's cite and is followed by more body: 218 lines.

| The line opens with | Lines | Ends a sentence |
|---|---|---|
| A word that opens a sentence, then a year | 178 | 174 |
| An acronym and a number | 26 | 14 |
| A name, and holds a link and a quoted title | 8 | 0 |
| Another capitalised word | 5 | 0 |
| A month | 1 | 1 |

At least 193 are sentences of the body (the 178, the month, and the 14 that open with an acronym
and end a sentence), and reading them as body is correct. At most 25 could be a second line of the
cite. In small print with no bold opening such a line has a body's formatting,
and only its words say otherwise, so nothing is changed for them. The 178 are no longer guessed to
be cites at all, and 44 lines are still re-read by the assembly.

### Before and after, over the same sources

| Caselist | Cards before | After | `FULL` before | After | `CITE_ONLY` before | After | No tag before | After |
|---|---|---|---|---|---|---|---|---|
| hsld26 | 64,678 | 64,693 | 63,949 | 64,091 | 729 | 602 | 1,356 | 1,347 |
| hspf26 | 42,906 | 43,264 | 42,506 | 42,917 | 400 | 347 | 1,907 | 2,250 |
| hspolicy26 | 82,565 | 82,380 | 81,529 | 81,382 | 1,036 | 998 | 1,094 | 902 |
| openev | 8,056 | 8,033 | 7,967 | 7,955 | 89 | 78 | 98 | 73 |
| **Total** | 198,205 | 198,370 | 195,951 | 196,345 | 2,254 | 2,025 | 4,455 | 4,572 |

No card is `ABBREVIATED`, before or after.

| Caselist | Cards with a cite before | After | With a short cite before | After |
|---|---|---|---|---|
| hsld26 | 57,409 | 59,399 | 39,795 | 41,773 |
| hspf26 | 25,243 | 30,946 | 21,649 | 27,380 |
| hspolicy26 | 74,953 | 76,327 | 45,100 | 46,336 |
| openev | 6,976 | 7,267 | 3,960 | 4,203 |
| **Total** | 164,581 | 173,939 | 110,504 | 119,692 |

* **183,575 stored cards are identical in every field** but the parser version: the same paragraph
  range, tag, cite, evidence text, completeness, spans, rule ids and confidence.
* **13,521 keep their paragraph range and differ.** 6,743 differ in cite and short cite, 2,148 in
  cite, short cite and evidence text, 380 in the cite alone, 192 in cite, evidence and
  completeness, 128 in cite and evidence, and 47 in all four. 3,883 differ only in rule ids or
  confidence, because a sentence that opens *In 2019* is body by its own formatting now and not by
  a guess overruled.
* **9,181 of them gain a cite:** 6,954 where it had been read as nothing, and 2,227 where it had
  been the first paragraph of the evidence text, which is shorter by it.
* **Completeness, among cards that keep their range:** 220 go from `CITE_ONLY` to `FULL` and 19
  from `FULL` to `CITE_ONLY`. Of the 19, 14 are cards whose only paragraph is a cite. The other
  five are the cards under 1 above whose body is held as cite text.
* **61 cards lose a cite.** Their only cite was a line that opens with a word such as *In* and a
  year. They are tagged cards with a body and no cite.
* **1,109 stored ranges are gone and 1,274 are new.** Most are one card for another: a card that a
  sentence had split is whole again, and two cards under one tag that had been joined are two. 307
  cards are where none was stored: 247 `FULL` cards with no tag, 48 tagged `CITE_ONLY` cards and 12
  `CITE_ONLY` cards with no tag, each behind a cite that had been read as nothing. 23 are gone with
  nothing in their place, below.
* **Card totals:** hspf26 gains 358, mostly cards in files that write no tags, whose cites are read
  now. hspolicy26 loses 185, mostly cards that a sentence had split.

**What leaves the store.** 586 paragraphs, 195,408 characters, were in a card's cite or body and
are in none:

* **440 are the whole of 23 cards with no tag** (21 `FULL`, 2 `CITE_ONLY`), which are gone with
  nothing in their place. Each began at a sentence such as *In 2019 …* with no tag and no cite
  above it, and the 21 ran on for about twenty paragraphs each. A body with no tag and no cite is
  not a card ([parsed-card-store.md](parsed-card-store.md#a-card-with-no-tag)), and these were
  cards only because their first sentence had been read as a cite.
* **140 are from 100 other cards with no tag, and 6 from 6 tagged cards,** whose paragraphs are
  otherwise in a card still. 108 of these are short lines that had been read as cite text and are
  read as nothing: a sentence that opens with such a word, at reading size, with no underline,
  highlight or full stop the classifier takes for prose. The classifier reads every short plain
  line that way.
* **By what they are:** 456 body paragraphs, the 108 lines, and 22 more lines that had been cite
  text and are body text with no card.

**What joins it.** 9,998 paragraphs, 6,473,442 characters: 7,527 cites that had been read as
nothing, 2,368 body paragraphs of cards that were not stored because their cite was not read, and
103 cites that had been stray body text.

### The two corrected evaluation files, and the labelled shapes

Two of the evaluation's thirty files are corrected by a person. On their 60 paragraphs every score
is the same under both parsers: tag precision 1.000 and recall 0.833 (5 of 6), cite precision
0.500 and recall 0.167 (1 of 6), 4 of 5 card boundaries, and completeness right on 4 of 4. Neither
file holds a paragraph the new rules reach.

They do hold five cites the parser misses, read as body text: four of 177 to 395 characters
with no name and year at their front, one of them highlighted throughout, and one of 1,737
characters with a styled name and year at its head and highlighting, which a person labelled a
cite. That last is the highlighted shape left under 2 above.

Because the corrected files hold none of the five shapes, each was rebuilt as invented, labelled
cards: 62 examples, at least ten a shape, in `tests/evals/parser/cite_shapes.py`, scored by the
evaluation's own scoring on every pull request.

| Synthetic set, 263 paragraphs | Tag precision | Tag recall | Cite precision | Cite recall | Card boundaries | Completeness |
|---|---|---|---|---|---|---|
| `2026.10.10-docx-2` | 1.000 | 0.967 | 0.805 | 0.524 | 55 of 63 | 44 of 55 |
| `2026.10.12-docx-3` | 1.000 | 1.000 | 1.000 | 0.984 | 63 of 63 | 63 of 63 |

The one cite line still missed is the second line of a cite in small print, under 5 above.

### What this raised and did not change

* **7,200 tagged cards with no cite have a name and a year a few words into the line under the
  tag,** behind a first name or a title: 5,396 read as nothing and 1,804 as the body's first
  paragraph. The rule for a cite line asks that the name and year open it.
* **957 lines shaped like a cite sit in a paragraph style the profile resolves to nothing,** such
  as a list or web style a converted file carries. A paragraph style is read before anything
  else, so no cite rule sees them.
* **Highlighted cites.** 593 lines open in bold with a name and a year and hold highlighting, as
  do 344 written as a name and year and one bracket. One corrected evaluation file holds such a
  paragraph labelled a cite. A card written as one paragraph is highlighted too.
* **24,431 tagged cards still have no cite.** For 13,609 nothing under the tag has a name and a
  year near its front.
* **The 108 short lines above** are in no card. They were in the wrong field before.
* **A cite-style run holds a long guess as a cite.** 19 guessed cites over 2,000 characters are
  formatted as body, carry a cite-style run and stand under the card's cite, where `v1-e31-t09`
  leaves them as cite text: 14 before this task and the five above. A style that marks no name and
  year at the head is emphasis, by the measure under 2, and that is a change to the earlier rule
  and to one of its fixtures.

## The re-parse, 2026-10-16

Run by the operator from the dev data directory on 2026-10-16, after `v1-e31-t12` (cites) and
`v1-e31-t11` (card matching) merged: one re-parse covers both, and the weekly agent was reinstalled
on a build carrying them only after it. It wrote a new version directory, published it to dev, and,
after the by-eye checks below, to prod. Counts only, as everywhere in this report.

| | |
|---|---|
| Parser | `2026.10.12-docx-3` |
| Fingerprints | `card-fingerprint-v3` |
| Parsed-store schema | 2 |
| Version directory | `2026.10.12-docx-3` (first generation) |
| Superseded | `2026.10.10-docx-2`, locally and in both buckets, byte for byte unchanged by the run. `2026.09.20-docx-1` is still in both buckets; removing superseded directories is `v1-e31-t16` |

**There are 1,575 more sources than on 2026-10-12.** The weekly run of 2026-10-14 imported them,
and the build it ran (`v0.1.0-dev.122`) did not parse them into `2026.10.10-docx-2`: the count of
cites in that directory before the run was exactly the 2026-10-12 table above.

### Dev

Every run exited 0. Wall-clock is the run's `elapsed_seconds`: parse, rebuild and publish.

| Caselist | Sources | Parsed | Unsupported | Failed | Cards | Clusters | Uploaded | Wall-clock |
|---|---|---|---|---|---|---|---|---|
| hsld26 | 4,970 | 4,855 | 109 | 6 | 74,725 | 11,552 | 4,973 | 544 s |
| hspf26 | 4,437 | 3,033 | 1,404 | 0 | 49,204 | 9,930 | 4,440 | 399 s |
| hspolicy26 | 3,190 | 3,159 | 31 | 0 | 101,681 | 18,746 | 3,193 | 940 s |
| openev | 104 | 101 | 2 | 1 | 8,033 | 5,841 | 107 | 87 s |
| **Total** | 12,701 | 11,148 | 1,546 | 7 | 233,643 | 46,069 | 12,713 | 1,970 s |

* **The same 7 failures as on 2026-10-11:** hsld26's 5 `MALFORMED_XML` and 1 `NOT_A_ZIP`, and
  openev's 1 `COMPRESSION_RATIO_EXCEEDED`. None of the new sources failed.
* **Unsupported** is by format as before: hsld26 66 PDF and 43 other, hspf26 1,387 PDF.
* **Every occurrence row** is `card-fingerprint-v3`.

**Over the same sources, every figure is the prediction.** Restricted to the sources the
2026-10-12 read-only run covered, the stored cards' completeness, tag and cite counts equal the
"after" columns of [Before and after, over the same sources](#before-and-after-over-the-same-sources)
exactly, and so do the counts by cite rule. Over every source:

| Caselist | Cards | `FULL` | `CITE_ONLY` | No tag | With a cite | Tagged, no cite |
|---|---|---|---|---|---|---|
| hsld26 | 74,725 | 74,018 | 707 | 1,495 | 68,921 | 5,804 |
| hspf26 | 49,204 | 48,796 | 408 | 2,682 | 35,092 | 14,112 |
| hspolicy26 | 101,681 | 100,430 | 1,251 | 1,072 | 94,309 | 7,372 |
| openev | 8,033 | 7,955 | 78 | 73 | 7,267 | 766 |
| **Total** | 233,643 | 231,199 | 2,444 | 5,322 | 205,589 | 28,054 |

No card is `ABBREVIATED`.

**The second run** parsed and uploaded nothing: `attempted` 0, `skipped` equal to the source
count, `uploaded` 0 for each caselist. Its elapsed time is the rebuild alone, now under
`card-fingerprint-v3` and with 14% more sources: 345 s, 219 s, 482 s and 68 s (1,114 s in all,
against 1,051 s on 2026-10-11).

**Five files by eye** (`v1-e31-t12`, step 6), five cards each, tag, cite and evidence text against
the document: 73 of 75 answers right. In one file two cards have no tag where the document may
hold one; the operator is to confirm in Word. In two other files four cards have the right tag,
cite and evidence text and no short cite: an author and a two-digit year with a curly apostrophe
on its own line above a long bracketed cite. No cite was read as a sentence, and no evidence text
began with a cite, so the check passed. Both shapes are `v1-e31-t19`'s.

### Prod

Published on 2026-10-16 from the same dev data directory (`DEBATE_ENV=prod`,
`DEBATE_STORAGE__DATA_DIR` set to the dev directory, `--confirm-prod`), after the checks above. The
dry run showed `2026.10.12-docx-3`, `card-fingerprint-v3`, nothing to parse and every source
skipped. Every publish exited 0, parsing and failing nothing, and uploaded 4,973, 4,440, 3,193 and
107 objects, dev's figures. Each store's listing holds its one index.

Prod went ahead though the join sample below holds one pair of different cards. Nothing reads
prod's parsed store yet, and the fix (`v1-e31-t20`) rewrites only the occurrence table, which the
next publish replaces.

### Card matching under `card-fingerprint-v3`, measured (`v1-e31-t11`)

`scripts/compare_card_clusters.py`, read-only on the dev data directory, over
`2026.10.12-docx-3`'s stored cards.

**Against the rules before `v1-e31-t11`** (`--before-rules` at the commit before it): the same
stored cards placed by `v2` and by `v3`.

| Caselist | Clusters before | After | Merged into another | New clusters made of several | Divided | Most absorbed by one | Largest before and after | Exact fingerprints changed |
|---|---|---|---|---|---|---|---|---|
| hsld26 | 11,570 | 11,552 | 18 | 17 | 0 | 3 | 710, 710 | 0 |
| hspf26 | 9,944 | 9,930 | 14 | 14 | 0 | 2 | 682, 682 | 0 |
| hspolicy26 | 18,765 | 18,746 | 19 | 16 | 0 | 3 | 1,602, 1,609 | 0 |
| openev | 5,841 | 5,841 | 0 | 0 | 0 | 1 | 22, 22 | 0 |

The session estimated 18, 10, 17 and 0 merges and no division. No card is in only one placement.
Of the short cuts the diagnosis finds within the rule and still apart, 2 are left, both in
hsld26, as the session predicted.

**Against the rules before `v1-e31-t08`** (`card-fingerprint-v1` to `v3`):

| Caselist | Clusters before | After | Merged into another | Divided | Largest before and after |
|---|---|---|---|---|---|
| hsld26 | 11,536 | 11,552 | 15 | 13 | 710, 710 |
| hspf26 | 9,924 | 9,930 | 12 | 16 | 682, 682 |
| hspolicy26 | 18,773 | 18,746 | 33 | 5 | 1,603, 1,609 |
| openev | 5,841 | 5,841 | 1 | 1 | 22, 22 |

Against 21, 18, 11 and 1 divided under `v2` on 2026-10-11. Each of the 56 pairs still divided is
one the diagnosis explains by a short cut: one left out in this part, or a part joined only
through a short cut elsewhere. None is a part no short cut links to the rest.

**By-eye samples**, tallies only:

| Sample | Pairs | Same card | Different card | Unsure |
|---|---|---|---|---|
| Newly in one cluster, of 51 | 20 | 17 | 1 | 2 |
| Divided, of 0 | 0 | | | |
| Three largest clusters, hsld26 (10 pairs each) | 30 | 23 | 7 | 0 |
| Three largest clusters, hspf26 (10 pairs each) | 30 | 19 | 10 | 1 |

* **The newly joined pair of different cards** is in hspolicy26: two bodies of 59 and 87 words that
  share no text, joined because a third body of 150 words holds all of both. That body is two
  cards stored as one, or a card and its neighbour, and `v3` lets a body that contains a cut stand
  witness for it whatever else the body holds.
* **The largest clusters lump different cards.** hsld26's second-largest and hspf26's largest each
  gave 6 of 10 pairs as different cards. The operator stopped the largest-cluster sample after two
  caselists: telling one long cut from another of the same article by eye is slow and often
  uncertain, so the rest was measured.

**Measured instead: the share of pairs of distinct texts in a cluster that share no text at all**
(five-word runs, counts only, read-only):

| Cluster | Cards | Distinct texts | Pairs | Sharing no text |
|---|---|---|---|---|
| hspf26, largest | 682 | 89 | 3,916 | 62% |
| hspolicy26, largest | 1,609 | 194 | 18,721 | 51% |
| hsld26, second | 441 | 49 | 1,176 | 25% |
| hspf26, third | 377 | 87 | 3,741 | 19% |
| hsld26, largest | 710 | 53 | 1,378 | 15% |
| hspolicy26, second | 692 | 54 | 1,431 | 8% |
| hsld26, third; hspf26, second; hspolicy26, third | 396; 592; 671 | 14; 75; 20 | 91; 2,775; 190 | 0% |

It agrees with the by-eye samples: the two clusters the operator found worst are the two with a
quarter or more of their pairs sharing nothing. Each large cluster holds few distinct short cites:
one article's many passages, chained together through long bodies that hold several of them.
hspf26's second-largest shares text throughout, but its texts run from 1,414 to 7,485 words, which
no card is: they are bodies the parser did not divide.

**What one card is (the PM's ruling, 2026-10-16, for `v1-e31-t20`).** A card is a passage. Two
bodies are one card when one holds the other or they overlap; two passages of one article are two
cards. Two bodies join only on text they share directly, never through a third body that holds
both. `v1-e31-t20` is measured by the share of pairs sharing no text, as above, and by a join
sample with no pair of different cards; a person looks only at pairs whose overlap a rule cannot
decide.

**The same measures, built into the tools (`v1-e31-t21`, 2026-10-17).**
`compare_card_clusters.py shapes` gives every figure in the table above exactly. It reads the same
texts as `diagnose`. openev's three largest clusters, not in the table, hold 0%, 41% and 0% of
pairs sharing no text, in clusters of 22, 21 and 18 cards and 14 texts each.

The sampler now decides by rule:
* a pair of two full cards that is identical or contained is the same card;
* a pair sharing no text is two different cards.

It asks a person about the rest. Run again on the join sample above (the same seed, so the same
20 pairs):

| Join sample of 20 | Same card | Different card | Unsure | Judged by a person |
|---|---|---|---|---|
| By eye, 2026-10-16 | 17 | 1 | 2 | 20 |
| With the rule, 2026-10-17 | 19 (18 by rule, 1 by eye) | 1 (by rule) | 0 | 1, in 29 seconds |

The rule agrees with every verdict given by eye. The pair called different shares no text, and the
two called unsure are each wholly inside the other body.

## The remaining cite shapes (`v1-e31-t19`)

`v1-e31-t12` left five cite shapes counted and unsettled, and the operator's check by eye on
2026-10-16 added two. Each was counted on 2026-10-18 in the dev data directory, read-only, as t12
counted: the 11,148 parsed DOCX sources of `2026.10.12-docx-3` (233,643 cards) re-parsed in place
from their blobs by scratch scripts outside the repository and the data directory. Counts,
lengths, formatting flags and rule ids only. Every total below over all cards equals the stored
directory's figures of [The re-parse, 2026-10-16](#the-re-parse-2026-10-16).

**Status: the rules are in parser `2026.10.18-docx-5`; the store has not been re-parsed with it.**
`2026.10.18-docx-4` is `v1-e31-t15`'s, which merged first; `2026.10.18-docx-5` carries both. The
"after" figures are what that parser produces over the same sources, measured side by side with
the stored cards on the branch synced onto `dev` with t15. The start commit's parser reproduces the stored cards exactly (openev,
8,033 of 8,033 identical in every field), so the stored directory is the "before".

### The counts, and what was done

| | Shape | In the corpus | Ruling and result |
|---|---|---|---|
| 1 | A cite behind a first name or a title | 8,250 tagged cards with no cite have a name and a year starting within the first 40 characters of the line under the tag, not at its front: 6,204 read as nothing, 2,046 as the body's first paragraph | Built: where a cite stands, behind one to three capitalised words or a title, the name and year (or the line's opening) in bold, or everything after the year in one bracket |
| 2 | A paragraph style that maps to no unit | 1,355 paragraphs a cite rule would read but for their style (1,255 by an alias, 48 by Word's de-duplication, 46 by `basedOn`, 6 in `Normal` by name) | Built, broad (PM, 2026-10-18): the cite and body rules see through such a style; the heading rules never do |
| 3 | A highlighted cite | 645 highlighted paragraphs over 400 characters with a cite's shape: 599 open in bold with a name and a year, 38 carry the cite style on a name and year at the head past 1,000 characters, 8 hold everything after the year in one bracket | Built: where a cite stands and a body follows |
| 4 | `v1-e31-t09`'s cite-style hold | 33 guessed cites carry a cite-style run; 26 of them, all over 2,000 characters, have no styled name and year at the head | Built as ruled in t12's review: the style holds a guess only when it marks a name and a year at its head |
| 5 | Short plain lines inside a body read as nothing | 91,345 short unformatted lines read as nothing; 43,488 stand between two body paragraphs of one card | Measured only (PM: left here, for the task merged with `v1-e31-t23`). Below |
| 6 | A short cite written `Okonkwo ‘26` | 296 short author-and-year lines hold U+2018, the left quote Word types before a two-digit year; the profile's patterns accept `'` and `’` only | Built: a left quote before a digit is read as `’` for matching only. Text, offsets and the profile are unchanged |
| 7 | Two cards with no tag in one checked file | Cards 2 and 3 of the file t12's step 6 opened for the bracketed cite line: above each cite, a short underlined line at reading size, read as body | Waiting on the operator's check in Word; not counted |

### 1. A cite behind a first name or a title

What sits directly under the tag of a tagged card with no cite (28,054 cards):

| Under the tag | Read as nothing | Read as body |
|---|---|---|
| No name and year | 8,178 | 6,392 |
| A name and year within 40 characters, not at the front | 6,204 | 2,046 |
| A name and year past 40 characters | 2,221 | 1,872 |
| A name and year at the front | 143 | 860 |
| A line in a paragraph style that maps to no unit | 129 | |

Of the 8,250 with a name and a year a few words in, 5,817 have one to three capitalised words or
initials before it, 308 a title, and the rest a phrase. The rule takes 4,864 of them in the counts:
3,949 read as nothing (64%) and 915 read as body (45%); 4,811 of the 4,864 name a credential or
hold a link. The same shape fits 437 paragraphs that do not stand where a cite stands, and the rule
leaves them. Over every place a cite stands, the shipped rule reads 5,189 paragraphs.

### 2. A paragraph style that maps to no unit

16,372 paragraphs carry a paragraph style the profile maps to `OTHER`. In 955 of the 1,355 that a
cite rule would read, the tag above had lost its card and the body below, in the same style, was
nothing too; 711 sit in files where half or more of the paragraphs carry such a style. Side by
side over the 492 files that hold one:

| Over the 492 files | Cards | With a cite | Tagged, with a cite and a body | `CITE_ONLY` | Tagged, no cite | No tag | Paragraphs to a cite / to body |
|---|---|---|---|---|---|---|---|
| Before | 8,113 | 6,929 | 6,527 | 196 | 1,184 | 246 | |
| The cite rules alone | 9,171 | 8,061 | 6,666 | 1,185 | 1,110 | 291 | 1,274 / 81 |
| The cite and body rules (built) | 9,598 | 8,149 | 7,687 | 111 | 1,449 | 398 | 1,268 / 12,744 |

The cite rules alone would have left 989 more cards `CITE_ONLY` whose body is in the file. In the
shipped parser, 1,339 cites and 12,852 body paragraphs are read through such a style.

### 3. A highlighted cite

| The 645 | Where a cite stands, a body below | Elsewhere |
|---|---|---|
| Bold opening | 466 | 133 |
| Styled name and year at the head | 14 | 24 |
| One bracket | 8 | 0 |

In 388 of the 488 the rule takes, under a tenth of the characters are highlighted, most often the
name at the head. The shipped rule reads 493.

### 4. The cite-style hold

Over the 15 files that hold such a guess, the change re-reads 25 paragraphs of over 2,000
characters as body: 23 cards go from `CITE_ONLY` to `FULL` (22 of them tagged), one more card
changes and one range becomes two. No paragraph of 2,000 characters or fewer moves. Seven guesses
are still held, six with the style on a name and year at the head. `v1-e31-t09`'s 300-word
fixture, whose style marks a name in its middle, is body now.

### 5. Short plain lines read as nothing, measured for a later task

The PM's ruling of 2026-10-18 leaves these as they are: the lines between two body paragraphs are
the population the task merged with `v1-e31-t23` (in-round markers) rules on. This is the
measurement it starts from. 91,345 lines that the classifier reads as nothing, not table cells or
text boxes:

| Where | Lines |
|---|---|
| Between two body paragraphs of one card | 43,488, in 15,796 cards |
| Before a body (under a tag or a cite) | 30,429 |
| After a body, before something else | 6,467 |
| Elsewhere | 10,961 |

The 43,488 between two body paragraphs:

| Length | No sentence end | Ends a sentence | In capitals |
|---|---|---|---|
| 40 characters or fewer | 24,207 | 1,192 | 11,799 |
| 41 to 100 | 4,909 | 3,421 | 154 |
| 101 to 200 | 1,300 | 5,482 | 4 |
| 201 to 400 | 1,162 | 0 | 0 |
| 401 to 1,000 | 1,457 | 0 | 0 |
| 1,001 to 4,000 | 353 | 0 | 0 |
| Over 4,000 | 5 | 0 | 0 |
| **All** | 33,393 | 10,095 | 11,957 |

A line of 200 characters or more that ends a sentence is prose to the classifier, so none of those
is here; the longer lines are ones that do not end a sentence.

### 6. A short cite written with a left quote

`Okonkwo ‘26`: Word turns an apostrophe typed after a space into U+2018, the left quote. The lines
written with `’` were read already. From `2026.10.18-docx-5` a left quote directly before a digit
is read as `’` wherever the profile's cite patterns are matched, and the short cite is taken from
the cite as written. Over the same sources **9,602 cards hold a short cite written with a left
quote, none before.** The estimate before the build, 415 more short cites, covered only the 131
files with such a line alone on its line; most of the 9,602 are cites that open `Okonkwo ‘26 [...]`.
It also reads 106 such lines that a bold-heading guess had taken for tags, and the tags above them
come back from analytics.

### The coach's sample

`scripts/sample_cite_shapes.py`, run by the operator on 2026-10-18 with seed 20261018: 70 items
from the 11,148 sources, drawn blind across the rules and sides, one key each, 710 seconds
answering. The parser was this task's, with the three new rules behind a flag only the sampler
switched on.

| Rule | Side | In the corpus | Asked | Yes | No | Unsure | Question |
|---|---|---|---|---|---|---|---|
| Behind a first name or a title | Taken, read as nothing before | 4,176 | 8 | 8 | 0 | 0 | The card's cite? |
| | Taken, read as body before | 1,013 | 2 | 2 | 0 | 0 | The card's cite? |
| | Left, read as nothing | 2,186 | 7 | 4 | 0 | 3 | The card's cite? |
| | Left, read as body | 1,110 | 3 | 3 | 0 | 0 | The card's cite? |
| A style that maps to no unit | Taken as a cite | 1,339 | 6 | 6 | 0 | 0 | The card's cite? |
| | Taken as body | 12,852 | 8 | 8 | 0 | 0 | The card's text? |
| | Left as nothing | 2,162 | 6 | 2 | 3 | 1 | A cite or text? |
| A highlighted cite | Taken | 493 | 10 | 10 | 0 | 0 | The card's cite? |
| | Left | 221 | 10 | 10 | 0 | 0 | The card's cite? |
| The cite-style hold | Re-read as body | 25 | 7 | 0 | 7 | 0 | The card's cite? |
| | Still held as a cite | 7 | 3 | 3 | 0 | 0 | The card's cite? |

**No rule took a paragraph wrongly:** 0 of 10, 0 of 14, 0 of 10 and 0 of 7. With ten a side, that
tells "mostly right" from "often wrong" and no finer. The left sides of the first and third rules
are cites too (7 of 10 and 10 of 10): those rules are cautious, and what they leave is a follow-up.

**The left quote, sampled after the PM's review.** (6) had shipped on a count of a few hundred lines
and reaches 9,602 cards, and it is the one change here that can take evidence text away from a
card. On 2026-10-18, seed 20261019, 28 items, 148 seconds answering, `--plan left-quote`:

| Side | In the corpus | Asked | Yes | No | Unsure | Question |
|---|---|---|---|---|---|---|
| A cite line that leaves its card no body | 18 | 18 | 18 | 0 | 0 | The card's cite? |
| A card gaining a short cite written with a left quote | 9,584 | 10 | 10 | 0 | 0 | The right short cite? |

Each of the 18 is a card stored `FULL` that is `CITE_ONLY` now with no other new rule to explain it,
and every one holds a line read as a cite only through the left quote. All 18 of those lines are
the card's cite, and all 10 short cites are right. (6) stands as built.

### Before and after, over the same sources

| Caselist | Cards before | After | `CITE_ONLY` before | After | No tag before | After | With a cite before | After | Tagged, no cite before | After | With a short cite before | After |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hsld26 | 74,725 | 75,336 | 707 | 676 | 1,495 | 1,563 | 68,921 | 70,914 | 5,804 | 4,422 | 48,313 | 50,458 |
| hspf26 | 49,204 | 50,246 | 408 | 390 | 2,682 | 3,038 | 35,092 | 41,696 | 14,112 | 8,550 | 31,193 | 35,638 |
| hspolicy26 | 101,681 | 101,826 | 1,251 | 1,265 | 1,072 | 1,093 | 94,309 | 95,713 | 7,372 | 6,113 | 56,818 | 61,162 |
| openev | 8,033 | 8,049 | 78 | 78 | 73 | 75 | 7,267 | 7,590 | 766 | 459 | 4,203 | 4,468 |
| **Total** | 233,643 | 235,457 | 2,444 | 2,409 | 5,322 | 5,769 | 205,589 | 215,913 | 28,054 | 19,544 | 140,527 | 151,726 |

The table covers the 11,148 sources parsed before. `v1-e31-t15`'s part of `2026.10.18-docx-5` reads
six of the seven sources refused before (five in hsld26, one in openev), with 95 cards, and names
the seventh an unsupported format; with them the totals are 235,552 cards, 2,411 `CITE_ONLY`, 5,772
with no tag, 216,005 with a cite, 19,547 tagged with no cite and 151,802 with a short cite. Over the
11,148 sources, t15 changes no card: every figure above is the same on the synced parser.

* **No card is `ABBREVIATED`,** before or after.
* **218,218 stored cards are identical in every field** but provenance's versions.
* **Among cards that keep their range,** 8,594 gain a cite and one loses its cite (a held guess the
  hold now reads as the card's text); 9,547 gain a short cite; 16 have a different tag (a short
  cite with a left quote no longer taken for the tag); 27 differ only in their section path.
* **Completeness, among cards that keep their range:** 25 go from `CITE_ONLY` to `FULL` (23 by the
  hold) and 28 from `FULL` to `CITE_ONLY`. Of the 28, 10 are a cite behind a first name that had
  been the card's only "body" paragraph. The other 18 carry no new rule id; by their rule ids they
  are lines read by the existing cite-line rule, which fits a line opening with a short cite
  written with a left quote that had been read as body. That is a reading of rule ids, not a check
  of each card.
* **548 stored ranges are gone and 2,362 are new:** mostly tags restored with their cards in files
  that write their cites and bodies in an unmapped style, and cards behind cites that are read now.
  500 of the new have no tag.

### The labelled evaluation

The six person-corrected files of the PR subset, `run_parser_eval.py --tier pr-subset`, every
parser over the same files and the labels as they stand on `dev` after `labels/2026 10 19`. The
full tier's labels are not corrected yet.

| Parser | Cite precision | Cite recall | Tag precision | Tag recall | Evidence precision | Evidence recall | Card boundaries |
|---|---|---|---|---|---|---|---|
| `2026.10.12-docx-3` | 0.957 (22 right, 1 wrong) | 0.500 (22 of 44) | 0.949 | 0.860 | 0.943 | 0.968 | 36 of 38 |
| `2026.10.18-docx-4` (`v1-e31-t15`) | 0.957 | 0.500 | 0.949 | 0.860 | 0.943 | 0.968 | 36 of 38 |
| `2026.10.18-docx-5` | 0.969 (31 right, 1 wrong) | 0.705 (31 of 44) | 0.949 | 0.860 | 0.943 | 0.968 | 36 of 38 |

Before the labels moved, on 2026-10-18, the same comparison gave the same cite figures, tag recall
0.771 and 22 of 23 card boundaries for both parsers.

### What this raised and did not change

* **What the cautious rules leave.** 2,186 lines behind a first name read as nothing and 221
  highlighted cite shapes elsewhere than under a tag with a body below are left; the sample found
  cites among both. Widening either needs its own counts and its own sample.
* **19,544 tagged cards still have no cite.**
* **The short plain lines** are the later task's, with the figures above.

## The re-cluster under `card-fingerprint-v4` (`v1-e31-t20`)

**Status: the first preview is measured and ruled on; the re-preview under the PM's rulings is not
run.** The first preview (the counts, shapes, samples and diagnosis below, all 2026-10-18) was of
the rules before the PM's rulings on it the same day; the re-preview is of the rules as ruled. The
steps are in
[the task's session report](../session-reports/v1-e31-t20-long-cuts-and-limits.md#operator-follow-ups):
a preview from the task worktree before the merge, which writes nothing to the store, and the
rebuild in dev after it. This is a re-cluster, not a re-parse: the parser and `2026.10.12-docx-3`
are unchanged, `caselist parse` rebuilds each caselist's `occurrences.jsonl` under the new rules,
and `--publish` uploads that file alone.

**What changed** (the PM's ruling of 2026-10-16, and the PM's rulings on the first preview of
2026-10-18, in [`near_duplicates.py`](../../packages/debate_core/src/debate_core/evidence/near_duplicates.py)):

* A long cut joins the one cluster that holds it by the step short cuts use, where `v3` joined it
  only when the banding happened to pair the two. `MIN_CUT_SHARE` applies to both.
* **Two bodies overlap when they share at least three-tenths of the smaller's five-word runs**
  (`MIN_OVERLAP_SHARE`, `v1-e31-t21`'s line between overlapping and sharing a little; the PM,
  2026-10-18). Every two bodies in a cluster overlap or one holds the other. This supersedes the
  first preview's reading, one shared run, which the PM had accepted: the preview's sample found a
  newly joined pair sharing a little that a person judged a different card.
* A body that holds a cut and another passage the cut does not overlap is no witness for the cut.
  `v1-e31-t11`'s false join is the case: two bodies sharing no text, joined because a third held
  both.
* A cut's own cluster counts among its witnesses, so a cut already with a body that holds it is not
  taken into a second cluster.
* No join puts two bodies that do not overlap in one cluster. So, by construction, every pair of
  full texts in a cluster overlaps or is contained, ac5's measure, the share of pairs sharing
  nothing, is 0 in every cluster, and so is the share sharing a little, but for texts of six runs
  or fewer, where one or two runs is three-tenths.
* **`MIN_CUT_SHARE` is a tenth** (a quarter before; the PM, 2026-10-18, from the first preview's
  sample: 20 of 20 cuts the share kept out were the same card, 8 of them under a tenth). It is also
  the size of a passage, so a body holding a passage a tenth to a quarter of it that a cut does not
  overlap is now no witness for that cut; the diagnosis counts those refusals.
* **A short body is found from either end**, as a long one is: one nine-tenths inside a body lacking
  one of its ends is compared (item 4, decided by the first preview's sample: 20 of 20 the same
  card). `MAX_CONTAINER_CLUSTERS` stays 8 and still counts clusters holding both ends.
* `MAX_CONTAINER_CLUSTERS` is counted against the clusters as they stand when a cut is considered,
  after long copies have joined one another.
* A long body nine-tenths inside a body that lacks one of its ends joins it, as `v3`'s banding did
  when it paired the two. The container rule applies to that join as to every other: a body that
  also holds a passage sharing no text with the long body is no witness for it (the PM's
  condition, 2026-10-18).

**What it costs on the labelled sets, and what recovering it would need.** Precision stays 1.000.
Two labelled cards have a trimmed-start and a trimmed-end copy that share no five-word run:
Brannock's ferry fares and Kessler's night buses, both invented. The labels call each one card. Under
the ruling they are two passages, and the bodies holding both are no witness for either, so their
pairs are lost: 19 of 24 full-short-card pairs found on the short-card set (was 24) and 23 of 37 on
the extended set (was 35). The PM held the ruling against the labels on 2026-10-18, kept the labels
as the coach wrote them, and amended `v1-e31-t08`'s two full-short-card targets to these figures. A
test pins the lost pairs to these two cards by row id and holds every other card's recall where
`v1-e31-t08` left it. **Recovering these pairs needs evidence beyond the bodies**: on the bodies
alone, two trims of one card that share no text have the same shape as `v1-e31-t11`'s false join of
two cards. A cite, a tag or the files the copies came from might tell the two apart; that is outside
this task, and the PM will consider it as a separate one.

**Stock phrases.** Under the first preview's reading one shared five-word run was enough to pass the
guard, and a stock phrase is one run. `shapes` counts the pairs in one cluster sharing only one or
two runs, for each cluster it describes and, with `--every-cluster`, over every cluster of a
caselist, and since the PM's rulings also how many of them do not overlap, which must be none. On
the labelled sets, all invented text, there are none under either reading: 0 of 59 pairs of
distinct full texts in one cluster on the variant set, 0 of 15 on the short-card set and 0 of 18 on
the extended set. Under the overlap reading the labelled sets' figures are unchanged row for row,
and the guardrail (t08's misses and the 18 pinned pairs, every other card's recall as t08 left it)
holds exactly, by test.

**To be recorded here**, from the operator's runs:

| Measure | First preview (superseded rules) | Re-preview, before the merge | After the dev rebuild |
|---|---|---|---|
| Counts against `card-fingerprint-v3`: clusters, merged, divided, largest | below, 2026-10-18 | below, 2026-10-18 | not run |
| ac5: share of pairs sharing nothing, three largest clusters per caselist | 0 in all twelve, below | 0 in all twelve, below | not run |
| ac1: join sample of 20 newly joined pairs, contained shapes asked | all 20 decided by rule, below | 20 of 20 same card by eye, below | not run, same seed |
| Newly joined cuts a tenth to a quarter of their witness, at least 20 (the PM's check on the share) | | 20 of 20 same card, below | |
| Witness refusals the lower share added | | not run | |
| `MIN_CUT_SHARE`: contained pairs under a third, joined and kept apart, by share band | below | not run | |
| Lacking an end: short bodies nine-tenths inside a body lacking one of their ends | below | (joined) | |
| Bodies nine-tenths inside one holding neither of their ends | 9 unexplained divided pairs | not run | |
| `MAX_CONTAINER_CLUSTERS`: cuts whose ends too many clusters hold, re-measured | below | not run | |
| Divided pairs against `v3`, by reason | below | not run | |
| Pairs in one cluster sharing only one or two five-word runs, every cluster, and of them not overlapping | below, 2026-10-18 | 4, none not overlapping, below | not run |

### The first preview's counts against `card-fingerprint-v3` (operator-run, 2026-10-18)

`compare_card_clusters.py counts --save-after`, from the task worktree at `ecf3e11`, each
caselist's cards in `2026.10.12-docx-3` placed in memory by `v4` and compared with the store's `v3`
table. Nothing was written to the store. In every caselist, `exact_fingerprints_changed`,
`cards_only_before` and `cards_only_after` are 0, and no cluster absorbed more than 5 others.

| | hsld26 | hspf26 | hspolicy26 | openev |
|---|---|---|---|---|
| Clusters, `v3` → `v4` | 11,552 → 11,656 | 9,930 → 10,325 | 18,746 → 18,821 | 5,841 → 5,816 |
| Clusters merged into another | 314 | 267 | 492 | 66 |
| Clusters made of several | 296 | 257 | 460 | 61 |
| Clusters divided | 230 | 336 | 320 | 28 |
| Absorbing 2 / 3 to 5 / 6 or more | 278 / 18 / 0 | 247 / 10 / 0 | 428 / 32 / 0 | 58 / 3 / 0 |
| Largest cluster, cards, `v3` → `v4` | 710 → 385 | 682 → 589 | 1,609 → 649 | 22 → 33 |
| Distinct texts in the largest, `v4` | 22 | 74 | 36 | 21 |
| Seconds to place | 330 | 229 | 414 | 51 |

The divided clusters are the chains `v3` built through bodies holding several passages coming apart;
the merges are mostly long copies joining one another, which `v3` left to the banding. hspf26's
largest cluster falls least and holds the most distinct texts, and openev's grows: both are read by
the shapes step, whose share of pairs sharing nothing is the check that no cluster joins texts with
nothing in common.

### The first preview's shapes (operator-run, 2026-10-18)

`compare_card_clusters.py shapes --largest-clusters 3 --every-cluster --after`, reading the
placement step 2 saved. **ac5 on the preview: no pair sharing nothing in any of the twelve
clusters** (target under 5%; `v3`'s were 62, 51, 41 and 25% in the largest clusters).

| Caselist | Rank | Cards | Distinct texts | Pairs | Sharing nothing | Sharing 1 / 2 runs | Words, smallest / median / largest |
|---|---|---|---|---|---|---|---|
| hsld26 | 1 | 385 | 22 | 231 | 0 | 0 / 0 | 676 / 1,120 / 1,125 |
| hsld26 | 2 | 331 | 29 | 406 | 0 | 0 / 0 | 238 / 1,479 / 1,539 |
| hsld26 | 3 | 312 | 8 | 28 | 0 | 0 / 0 | 81 / 88 / 102 |
| hspf26 | 1 | 589 | 74 | 2,701 | 0 | 0 / 0 | 2,672 / 6,143 / 7,040 |
| hspf26 | 2 | 225 | 47 | 1,081 | 0 | 0 / 0 | 400 / 1,193 / 1,512 |
| hspf26 | 3 | 191 | 19 | 171 | 0 | 0 / 0 | 500 / 829 / 882 |
| hspolicy26 | 1 | 649 | 36 | 630 | 0 | 0 / 0 | 404 / 694 / 1,161 |
| hspolicy26 | 2 | 634 | 74 | 2,701 | 0 | 11 / 0 | 296 / 2,499 / 3,843 |
| hspolicy26 | 3 | 622 | 14 | 91 | 0 | 0 / 0 | 443 / 796 / 880 |
| openev | 1 | 33 | 21 | 210 | 0 | 24 / 1 | 163 / 2,075 / 4,016 |
| openev | 2 | 12 | 4 | 6 | 0 | 0 / 0 | 113 / 174 / 218 |
| openev | 3 | 11 | 6 | 15 | 0 | 0 / 0 | 769 / 1,044 / 1,211 |

Every card in these clusters is full. hspf26's largest is the long-bodied cluster the PM said to
leave alone; nothing special-cases it.

**Stock phrases, over every cluster**: pairs of distinct full texts in one cluster that share only
one or two five-word runs.

| Caselist | Pairs in one cluster | Sharing 1 run | Sharing 2 runs | Share | Clusters with such a pair |
|---|---|---|---|---|---|
| hsld26 | 16,589 | 23 | 169 | 1.2% | 21 of 2,505 |
| hspf26 | 15,361 | 21 | 22 | 0.3% | 17 of 2,054 |
| hspolicy26 | 24,181 | 83 | 47 | 0.5% | 42 of 3,518 |
| openev | 1,151 | 33 | 3 | 3.1% | 9 of 407 |

They are concentrated: openev's largest cluster holds 25 of its caselist's 36. Such a pair is in one
cluster because each text shares more with some third body, so the count cannot say whether it is
two passages of one article overlapping by a few words or a stock phrase bridging two cards; a
person can, with `sample --largest 1 --least-alike`. The PM decides any follow-up from these figures.

### The first preview's samples (operator-run, 2026-10-18)

`compare_card_clusters.py sample --after`, against the placement step 2 saved, over all four
caselists, judged by eye on the operator's terminal. Tallies only.

| Sample | Drawn | Decided by rule | Asked | Same card | Different card | Unsure |
|---|---|---|---|---|---|---|
| Step 4, ac1: newly joined pairs (seed 718710206) | 20 of 1,139 | 20 (contained: 13 under a third, 7 a third or more) | 0 | | | |
| Step 5: newly joined pairs, contained under a third asked (seed 306444940) | 40 of 1,139 | 18 (contained, a third or more) | 22 | 21: 17 contained under a third, 4 overlapping | **1: sharing a little** | 0 |
| Step 5: cuts kept apart by the minimum share (seed 563320648) | 20 of 2,226 | 0 | 20 | 20: long 11 a tenth to a quarter, 7 under a tenth; short 1 and 1 | 0 | 0 |
| Step 6: short bodies lacking an end (seed 737351069) | 20 of 31 | 0 | 20 | 20: 2 half or more, 4 a quarter to a half, 4 a tenth to a quarter, 10 under a tenth | 0 | 0 |
| Step 7: cuts whose ends too many clusters hold (seed 281425182) | 6 of 6 | 0 | 6 | 6: 4 half or more, 1 a quarter to a half, 1 a tenth to a quarter | 0 | 0 |

* **A newly joined pair called different.** One of the 40 newly joined pairs in step 5 shares a
  little text (some five-word run, under three tenths of the smaller's) and was judged a different
  card. `v4` refuses a join only when two texts share nothing, so two texts sharing a run can end up
  in one cluster through a third body that shares more with each, although under the ruling they
  are neither one inside the other nor overlapping. This is with the PM before any merge.
* **ac1's 20 pairs were all decided by rule**, so no person judged them; the sample is to be run
  again on whatever placement the PM's answer leads to, with the contained shapes asked.
* **The limits.** Every cut each limit keeps out that a person saw was judged the same card:
  20 of 20 under the minimum share, including 8 under a tenth of the body; 20 of 20 short bodies
  lacking an end (item 4: the sample says compare them); 6 of 6 whose ends too many clusters hold,
  which is every such cut on the four caselists. The contained pairs under a third that `v4`
  newly joins were the same card 17 times in 17, confirming the rule's "contained is the same card"
  on this sample (ac6).

### The first preview's diagnosis (operator-run, 2026-10-18)

`compare_card_clusters.py diagnose --after`, and `shapes`' pair counts for the twelve largest
clusters. Bodies with a container outside their cluster, by what keeps them out:

| Outcome | Short cuts | Long cuts |
|---|---|---|
| Every body outside that holds it also holds a passage sharing nothing with it | 126 | 1,366 |
| Under the minimum share of the smallest witness | 235 | 1,991 |
| … of which a tenth to a quarter / under a tenth | 81 / 154 | 1,327 / 664 |
| Its witnesses are in more than one cluster | 50 | 625 |
| A body in its own cluster holds it, and so does one in another | 12 | 303 |
| Joining it would put two texts that share nothing in one cluster | 2 | 53 |
| One cluster is its witness, within the share, and it is still apart | 0 | 132 |
| Nine-tenths inside a body lacking one of its ends | 31 | (joined) |
| Its ends are held by too many clusters | 6 | (not counted for long cuts) |

(Summed over hsld26, hspf26, hspolicy26 and openev; t11 counted the too-many-clusters limit at
5 of 81.)

**The 132 long cuts within the rule and still apart**: 82 because another body of their cluster
points elsewhere (a witness of its own in a third cluster, or too common), so the cluster joins
nothing, which is the rule; 22 with nested copies as containers in several clusters; 9 whose
container first by fingerprint is over the share; 19 of none of these, refused beside another join
(the symmetric refusal) or placed by other rules.

**Divided pairs against `v3`**: 418, 662, 567 and 41, 1,688 in all, each explained by a cut left out
or a part joined only through a cut, except **9** (1, 6, 1 and 1) that the diagnosis reports as "no
cut or copy links this part to the rest". On invented text, one shape gives exactly that: a long
body nine-tenths inside another but with a word changed at both ends. `v4` finds a long cut's
containers from either end, so such a body has none; `v3` joined the pair whenever its banding
happened to pair the two. This is likely, not shown on the store, and is a recall loss, not a
false join.

**Pairs sharing a little in the largest clusters** (some five-word run, under three tenths of the
smaller's): hspf26 1 and 19 of 2,701 and 1,081 pairs in its first two; hspolicy26 19 of 2,701 in
its second; openev 50 of 210 in its largest; none in the other eight. These are the pairs a
reading of "shares text" as "overlaps" would keep out of one cluster.

### The PM's rulings on the first preview (2026-10-18)

* **"Shares text" means overlaps**, at three-tenths of the smaller text's five-word runs, in the
  passage refusal and the join guard. This supersedes the one-run reading the PM accepted earlier
  the same day; the count of pairs sharing one or two runs was asked for to test that reading, and
  the sample answered it.
* **`MIN_CUT_SHARE` is a tenth.** The re-preview samples at least 20 newly joined cuts from the
  tenth-to-a-quarter band; any judged a different card stops the merge until the PM has seen it.
  The diagnosis reports the witness refusals the lower share added.
* **Short bodies lacking an end are compared**, as the sample supports. **`MAX_CONTAINER_CLUSTERS`
  stays 8.**
* **The 9 divided pairs the diagnosis could not explain** are named by a new outcome, a body
  nine-tenths inside one holding neither of its ends; recovering them is a later rule change, which
  the PM is filing at p3.
* **The 132 long cuts within the rule and apart**: accepted, no defect.

### The re-preview's counts and shapes (operator-run, 2026-10-18)

The rules as ruled, from the task worktree at `8065605`, placed in memory and saved (step R2), then
described (step R3). Nothing was written to the store. In every caselist
`exact_fingerprints_changed`, `cards_only_before` and `cards_only_after` are 0, and no cluster
absorbed more than 4 others.

| | hsld26 | hspf26 | hspolicy26 | openev |
|---|---|---|---|---|
| Clusters, `v3` → as ruled | 11,552 → 11,595 | 9,930 → 10,234 | 18,746 → 18,741 | 5,841 → 5,806 |
| Clusters merged into another | 501 | 438 | 779 | 109 |
| Clusters divided | 292 | 390 | 420 | 46 |
| Absorbing 2 / 3 to 5 / 6 or more | 443 / 29 / 0 | 404 / 17 / 0 | 696 / 40 / 0 | 104 / 2 / 0 |
| Largest cluster, cards (first preview) | 385 (385) | 586 (589) | 665 (649) | 13 (33) |
| Distinct texts in the largest | 22 | 72 | 75 | 9 |
| Seconds to place | 343 | 247 | 496 | 52 |

**ac5 on the re-preview: no pair sharing nothing in any of the twelve largest clusters, and no pair
sharing a little** (the first preview had 89 of those, 50 in openev's largest). Sizes of the three
largest clusters, in cards: hsld26 385, 331, 312; hspf26 586, 217, 191; hspolicy26 665, 648, 602;
openev 13, 12, 12.

**Pairs sharing only one or two runs, over every cluster: 4** (hsld26 2 of 15,350 pairs in one
cluster, hspf26 1 of 14,804, hspolicy26 1 of 22,864, openev 0 of 974), against 401 in the first
preview, and **none of them fails to overlap**. How they got there: two texts sharing one run
overlap only when the smaller has three runs or fewer, so each of the four is a text of a few words
in its cluster directly, one of its runs being three-tenths of it or more; none is there through a
third body.

### The re-preview's join sample, ac1 (operator-run, 2026-10-18)

`sample --count 20 --ask-shape contained-under-a-third --ask-shape contained-a-third-or-more
--after`, over all four caselists: `Drew 20 of 1827 newly joined pairs, seed 963278315`. Every pair
was shown and judged by eye; **20 of 20 the same card, none different, none unsure** (ac1). By
shape: 16 contained under a third of the larger, 2 contained a third or more, 2 overlapping. The
rule would have called the 18 contained ones the same card; the person agreed with it every time.

### The re-preview's band sample, the PM's check on the share (operator-run, 2026-10-18)

`sample --joined-in-band a-tenth-to-a-quarter --count 20` with the three decided shapes asked,
over all four caselists: `Drew 20 of 933 cuts newly joined a tenth to a quarter of their smallest
witness, seed 902519467`. Each was shown beside the smallest body holding it and judged by eye:
**20 of 20 the same card** (17 long cuts, 3 short; every one contained, under a third of the
larger), none different, none unsure. These are the joins lowering `MIN_CUT_SHARE` from a quarter
to a tenth let in; the PM's condition, no different-card pair among at least 20, is met.

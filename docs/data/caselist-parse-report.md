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

**Status: not rebuilt yet.** The by-eye sample of 20 newly joined pairs is that task's operator
follow-up (its criterion ac5), and it waits for `v1-e31-t09`'s re-parse under `2026.10.10-docx-2`,
which rebuilds the aggregates under `card-fingerprint-v2` in the same run. The figures are recorded
here when it has run.

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

* **No incremental rebuild yet.** The slowest rebuild was 460 s (hspolicy26). This will be
  revisited when `v1-e34-t17` puts the parse inside the weekly run.
* **The failure-rate threshold and small caselists.** openev's four failures out of 102 are just under 4%.
  One more bad file in a release that size crosses 5%. `v1-e34-t17` takes a minimum number of
  sources tried before the rate is judged.
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
which the parser never does.

**The compression ratio.** Of the 9,738 distinct DOCX sources that open as a zip, 9,732 have no
entry above 50-fold, five have one between 50 and 100, and this file is the only one above 100.
The refused entry is the page thumbnail Word saves beside a document, which the parser never
opens. The file is ordinary, but 278 against 200 is not a small margin, and nothing else in the
corpus comes within half of the limit, so the limit is left where it is.

### Counts before and after, from the same sources

| Caselist | DOCX sources | Parsed before | Parsed after | Failed before | Failed after | Cards before | Cards after |
|---|---|---|---|---|---|---|---|
| hsld26 | 4,360 | 4,354 | 4,354 | 6 | 6 | 67,914 | 64,675 |
| hspf26 | 2,650 | 2,649 | 2,650 | 1 | 0 | 44,298 | 42,902 |
| hspolicy26 | 2,629 | 2,610 | 2,629 | 19 | 0 | 87,556 | 82,563 |
| openev | 102 | 98 | 101 | 4 | 1 | 7,288 | 8,056 |
| **Total** | 9,741 | 9,711 | 9,734 | 30 | 7 | 207,056 | 198,196 |

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
bold name. 11,872 paragraphs are re-read that way. A blank line in any heading, tag, cite, analytic
or undertag style is `OTHER`: 7,986 paragraphs. Expected after a re-parse:

| Caselist | `FULL` | `ABBREVIATED` | `CITE_ONLY` | Cards with no tag | Of cards |
|---|---|---|---|---|---|
| hsld26 | 1,067 | 0 | 286 | 1,353 | 2.1% |
| hspf26 | 1,736 | 0 | 167 | 1,903 | 4.4% |
| hspolicy26 | 736 | 0 | 356 | 1,092 | 1.3% |
| openev | 79 | 0 | 19 | 98 | 1.2% |
| **Total** | 3,618 | 0 | 828 | 4,446 | 2.2% |

No card is `ABBREVIATED` in this table because none is anywhere after the re-parse: see
[`ABBREVIATED`, by shape](#abbreviated-by-shape).

Those 4,446 are written as `"tag": null`, never as an empty string. They are cards whose cite came
from a cite style (1,653), from the cite-line heuristic and looked like a cite (2,394), or from the
wiki heuristic outside small print (399). Whether each is a second card under one tag or one more
split is for the labelled evaluation to say; [parsed-card-store.md](parsed-card-store.md#a-card-with-no-tag)
says how a reader should treat them.

What the change did not touch: of the cards stored now, 186,642 have the same paragraph range under
the new parser, and every one of those has the same evidence text, the same cite, the same tag and
the same completeness. 1,630 of them have a different section path, because 1,847 stored cards
carry an empty string in their path from a blank heading line, and none does afterwards.

### `ABBREVIATED`, by shape

The first parse called a card `ABBREVIATED` when an ellipsis marker (`…`, `...`, `[…]`, `[...]` or
`***`) appeared anywhere in its body or its cite: 22,443 cards. `2026.10.10-docx-2` decides it from
the shape of a disclosure of first and last words, and the rule was taken from these counts. They
are over the 198,196 cards the new parser reads from the same sources, measured read-only on
2026-10-10. Words are whitespace-separated.

Under the old rule 21,382 of those cards would be `ABBREVIATED`: 19,402 whose body holds a marker,
and 1,980 whose body holds none and whose cite does.

**Body length, by how many markers the body holds** (19,402 cards):

| Body words | 1 marker | 2 | 3 to 5 | 6 or more | All |
|---|---|---|---|---|---|
| 20 or fewer | 0 | 0 | 0 | 0 | 0 |
| 21 to 30 | 6 | 0 | 1 | 0 | 7 |
| 31 to 60 | 31 | 0 | 0 | 0 | 31 |
| 61 to 100 | 51 | 2 | 7 | 0 | 60 |
| 101 to 200 | 305 | 39 | 15 | 1 | 360 |
| 201 to 500 | 2,360 | 416 | 135 | 28 | 2,939 |
| 501 to 1,000 | 3,565 | 643 | 459 | 69 | 4,736 |
| Over 1,000 | 5,432 | 1,915 | 2,513 | 1,409 | 11,269 |
| **All** | 11,750 | 3,015 | 3,130 | 1,507 | 19,402 |

For comparison, 10,682 of the 174,063 bodies with no marker are 100 words or fewer (6.1%), against
98 of these 19,402 (0.5%). A body with an ellipsis is, if anything, longer than one without.

**Where the marker sits**, in the 11,750 bodies with one marker, as the share of the body's words
before it:

| Before the marker | 0 to 9% | 10s | 20s | 30s | 40s | 50s | 60s | 70s | 80s | 90s |
|---|---|---|---|---|---|---|---|---|---|---|
| Cards | 554 | 970 | 1,600 | 1,389 | 1,414 | 1,572 | 928 | 977 | 1,147 | 1,199 |

It sits anywhere, as an omission in running text does. In 57 the marker opens or closes the body (1
opens, 56 close), so it joins nothing.

**The words either side**, in the 11,693 one-marker bodies with words on both sides, by the longer
of the two sides. Cumulative:

| Longer side, at most | 12 | 15 | 20 | 30 | 40 | 50 | 60 | 80 | 100 | 150 | 200 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Cards | 0 | 0 | 6 | 14 | 38 | 55 | 59 | 109 | 185 | 454 | 806 |

The shortest longer side in the corpus is 17 words. The 37 one-marker bodies of 60 words or fewer
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
  quotation. 7,652 bodies hold two or more, and all but 13 of those are over 120 words.
* **Words on both sides:** a marker at either end joins nothing.
* **Twelve** is the middle of the only gap there is. Below it are the disclosures we have a model of:
  the convention is a card's first and last few words, and the profile's own examples have three to
  nine a side. Above it is everything the corpus holds, from 17 up. Any bound from 9 to 16 gives the
  same answer on this corpus. Raising it to 20 would call 6 cards abbreviated, to 30 14, to 50 55,
  and nothing tells those from any other short card.

**Before and after, per caselist:**

| Caselist | Stored: `FULL` | `ABBREVIATED` | `CITE_ONLY` | After: `FULL` | `ABBREVIATED` | `CITE_ONLY` |
|---|---|---|---|---|---|---|
| hsld26 | 57,057 | 8,418 | 2,439 | 62,769 | 0 | 1,906 |
| hspf26 | 40,319 | 2,972 | 1,007 | 42,053 | 0 | 849 |
| hspolicy26 | 74,902 | 10,524 | 2,130 | 80,756 | 0 | 1,807 |
| openev | 6,563 | 529 | 196 | 7,887 | 0 | 169 |
| **Total** | 178,841 | 22,443 | 5,772 | 193,465 | 0 | 4,731 |

The card totals differ between the two halves because the empty-tag fix merged split cards, as
above. To see the completeness rule alone, take the new parser's 198,196 cards and apply each rule
to them:

| Caselist | `ABBREVIATED` to `FULL` | `FULL` to `ABBREVIATED` |
|---|---|---|
| hsld26 | 7,908 | 0 |
| hspf26 | 3,026 | 0 |
| hspolicy26 | 9,837 | 0 |
| openev | 611 | 0 |
| **Total** | 21,382 | 0 |

Of the 21,382, 19,402 held a marker in the body and 1,980 only in the cite. `CITE_ONLY` is
untouched: 4,731 either way. Among the 186,642 stored cards whose paragraph range is the same under
the new parser, 15,781 go from `ABBREVIATED` to `FULL` and none goes any other way.

**So the corpus as it stands holds no abbreviated disclosure in a card's body**, and
`v1-e31-t08`'s abbreviation linking will find nothing to link by that route after the re-parse.
That is what the files hold: these caselists disclose open-source documents, which are whole cards.

### What this raised and did not change

* **A body paragraph can be stored as the card's cite.** The wiki cite-entry heuristic takes any
  paragraph holding an ellipsis and a name with a year for a cite. `2026.10.10-docx-2` keeps such a
  paragraph in its card when a body is already open. When it is the *first* body paragraph, no body
  is open yet, and it is still filed as cite text. Under the new parser 3,515 cite paragraphs from
  that heuristic are longer than 100 words (2,058 of them longer than 1,000), where a cite read
  from a cite style is longer than 200 words in 35 cases out of about 140,000. 2,902 of the 4,731
  `CITE_ONLY` cards hold a cite paragraph of more than 100 words: they are whole cards with their
  body in the cite field and no evidence text. This is the same defect family as the empty tags,
  it is not fixed in `2026.10.10-docx-2`, and it is where a real first-and-last-words entry would
  also be found: at most 84 cite paragraphs from that heuristic are 40 words or fewer.
* **The labelled evaluation cannot yet arbitrate.** Two of its 30 files are corrected by a person,
  both team files with no untagged card. On those 60 paragraphs the blank-line rule raised tag
  precision from 0.714 to 1.000, every card boundary stayed where it was, and completeness is
  right on 4 of 4 matched cards before and after.

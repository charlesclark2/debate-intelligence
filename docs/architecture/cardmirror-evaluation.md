# CardMirror evaluation

Evidence for [ADR-0014](../adr/0014-debate-file-editor.md): what CardMirror is, how its document
model lines up with ours, what a CardMirror round-trip does to a Verbatim file, what its license
allows us to do, and what a Debate Decoded subscription is actually for.

| | |
|---|---|
| Project | [CardMirror](https://github.com/ant981228/cardmirror), by Anthony Trufanov |
| Reviewed at | `bc92e6bd99cb9b3ce97ddacfa2362100db96360e` (version 1.11.0, pushed 2026-09-19) |
| License | PolyForm Noncommercial License 1.0.0 |
| Editions | Electron desktop (macOS, Windows, Linux) and a web edition at `cardmirror.app` |
| Reviewed | 2026-09-19 / 2026-09-20 |
| Task | [`v1-e31-t01-cardmirror-evaluation`](../../plan_specs/v1/e31-debate-file-parsing/t01-cardmirror-evaluation.yaml) |

CardMirror is a standalone replacement for the editor half of
[Verbatim](https://github.com/ashtarcommunications/verbatim), the Word add-in most US debate teams
use. It keeps Verbatim's Pocket / Hat / Block / Tag structure, its F-key shortcuts and its
send-to-speech workflow, and it reads and writes the same `.docx` files — with no Word, no macros
and no add-in. It does not cut cards and has no research pipeline; nothing about it touches this
platform's evidence-integrity rules.

Everything below was read from the source at the pinned commit or produced by running that commit's
`fromDocx` / `toDocx` through
[`scripts/cardmirror-roundtrip/`](../../scripts/cardmirror-roundtrip/README.md). Where a claim comes
from CardMirror's own documentation rather than from code we read or a round-trip we ran, it says so.

## Schema mapping

CardMirror models a debate file as a ProseMirror typed tree — a card is a real node with a real tag
child, not a run of paragraph styles that happens to look like a card. The top level is a *flat*
sequence: headings are peers in document order and the hierarchy is derived from their outline
level, because real files routinely pack several documents into one, separated by empty Heading 1
paragraphs.

```
doc:           flat sequence of block-level kinds
card:          tag (card_body | undertag | cite_paragraph | table)*
analytic_unit: analytic (card_body | undertag | cite_paragraph | table)*
```

### Nodes

Our column is the `StructuralUnit` enum [`v1-e31-t02-verbatim-style-profile`](../../plan_specs/v1/e31-debate-file-parsing/t02-verbatim-style-profile.yaml)
defines (POCKET, HAT, BLOCK, TAG, CITE, EVIDENCE, ANALYTIC, UNDERTAG, OTHER) and the `FileSection` /
`ParsedCard` models [`v1-e31-t03-debate-docx-parser`](../../plan_specs/v1/e31-debate-file-parsing/t03-debate-docx-parser.yaml)
emits. Style ids are from CardMirror's `NODE_TO_PSTYLE` / `PSTYLE_TO_NODE` in `src/ooxml/styles.ts`.

| CardMirror node | docx paragraph style | Our structural unit | Notes |
|---|---|---|---|
| `doc` | — | `ParsedDocument` | Flat sequence, not a single root. |
| `pocket` | `Heading1` | `POCKET` | Stable UUID `id`; `<w:pageBreakBefore/>` lives in the style, not the node. |
| `hat` | `Heading2` | `HAT` | Stable UUID `id`. |
| `block` | `Heading3` | `BLOCK` | Stable UUID `id`; `numRestart` attr for card numbering. |
| `card` | — (a container) | `ParsedCard` | No docx counterpart: on export it is just its children. This is the one structure we would gain. |
| `tag` | `Heading4` | `TAG` | Card-only; stable UUID `id`. |
| `cite_paragraph` | none (Normal) | `CITE` | Identified by position and the `cite_mark` runs it carries, not by a paragraph style. |
| `card_body` | none (Normal) | `EVIDENCE` | The card's evidence text. |
| `analytic` | `Analytic` | `ANALYTIC` | Outline level 4, colour `#1F3864`; first child of an `analytic_unit`, or a card's cite slot. |
| `analytic_unit` | — (a container) | *(no counterpart)* | Peer of `card` for analysis with no evidence behind it. We keep analytics as sections, not units. |
| `undertag` | `Undertag` | `UNDERTAG` | Belongs to the tag above it; does not start a new card. |
| `paragraph` | none (Normal) | `OTHER` | First-class unstyled text at any position. |
| `table`, `table_row`, `table_cell`, `table_header` | `<w:tbl>` / `<w:tr>` / `<w:tc>` | `OTHER` | Cells hold plain paragraphs only. `rawTblPr` / `rawTcPr` carry borders and shading opaquely. |
| `image` | `<w:drawing>` | *(no counterpart)* | Inline atom: base64 bytes + EMU dimensions + alt text. |
| `footnote` | `word/footnotes.xml`, `word/endnotes.xml` | *(no counterpart)* | Inline atom carrying its own content. (`ARCHITECTURE.md` §19 still lists footnotes as out of scope; the code models them.) |
| `transclusion_ref`, `self_ref` | — | *(no counterpart)* | Linked copies and live views of another section. Both freeze to a plain snapshot on export, so they never reach a `.docx`. |
| `text` | `<w:t>` | — | Marks hang off text nodes. |

Every paragraph-like node also carries two round-trip-only attrs: `indent` (left indent in OOXML
dxa) and `spacing` (the `<w:spacing>` map, captured opaquely and re-emitted verbatim).

### Marks

Named-style marks map to docx character styles through `MARK_TO_RSTYLE`; the rest are direct run
formatting. Our `FormattingSpan` (t03) records these as character offsets over the paragraph text.

| CardMirror mark | docx | Ours |
|---|---|---|
| `cite_mark` | `rStyle Style13ptBold` | Cite styling inside a `CITE` section; the short-cite split is ours, not CardMirror's. |
| `underline_mark` | `rStyle StyleUnderline` | `FormattingSpan` underline. Used in **body** slots. |
| `underline_direct` | `<w:u>` with no `rStyle` | `FormattingSpan` underline. Used in **structural** slots (tag, analytic, pocket, hat, block, undertag). |
| `emphasis_mark` | `rStyle Emphasis` | `FormattingSpan` emphasis. |
| `undertag_mark` | `rStyle UndertagChar` | Undertag run styling. |
| `analytic_mark` | `rStyle AnalyticChar` | Analytic run styling. |
| `highlight(color)` | `<w:highlight>` | `FormattingSpan` highlight. |
| `bold` / `bold_off` | `<w:b/>` / `<w:b w:val="0"/>` | `FormattingSpan` bold. `bold_off` exists because tags and headings are bold by CSS default. |
| `italic`, `strikethrough`, `superscript`, `subscript` | the matching `rPr` elements | Carried as formatting metadata. |
| `shading(color)`, `font_color`, `font_size`, `font_family` | `<w:shd>`, `<w:color>`, `<w:sz>`, `<w:rFonts>` | Carried as formatting metadata. |
| `link(href)` | `<w:hyperlink>` | Cite URL when it sits on a cite paragraph. |
| `comment_range(threadId)` | `<w:commentRangeStart/End>` + `comments.xml` | Not modelled; our parser drops comments. |
| `pilcrow_marker` | — | CardMirror-only: marks where an original paragraph break was when a card is condensed. |

**Underline is dual-encoded, and this matters to us.** `underline_mark` and `underline_direct` look
identical on screen but are different OOXML, and Verbatim's macros key on the difference. CardMirror
normalizes: the named style never lands in a structural slot, the direct one never in a body slot.
On export it writes **both** on body runs — `rStyle StyleUnderline` *and* `<w:u w:val="single"/>`.
Our parser (t03) must treat the two encodings as one underline and must not double-count a run that
carries both; the style profile (t02) is where that rule belongs.

**What CardMirror models that we do not:** the `card` container itself (we rebuild it by grouping),
`analytic_unit`, images, footnotes, transclusion, comments and card numbering. **What we model that
it does not:** provenance (source sha256, element index, caselist and snapshot), the short-cite
split, card fingerprints, and verification status. The two models are complementary, not competing:
CardMirror is an editing model, ours is an analysis and provenance model.

### Out of scope for CardMirror

The importer drops and the exporter never emits: section properties (`<w:sectPr>` — margins, page
size, columns), revision ids (`<w:rsid*>`), and non-heading bookmarks. Numbered and bulleted lists
are on its roadmap, not shipped. Tracked changes are *resolved*, not preserved: `<w:ins>` and
`<w:moveTo>` runs are kept, `<w:del>` and `<w:moveFrom>` dropped, and no revision markup is written
back. That is the same rule our parser and the lossless writer already specify, which is convenient
— but it means a file that goes through CardMirror loses its tracked-change history permanently.

## Public TypeScript API

Exported from `src/index.ts`. The six the task spec names are all there, plus the native-format and
comment functions. CardMirror is not published to npm (`"private": true`), so the reference is a git
URL at a commit; there is no built package entry point, so a consumer imports the TypeScript sources
(our harness runs them through `tsx`).

| Export | What it does |
|---|---|
| `schema` | The ProseMirror `Schema` built from `nodes` + `marks`. Also exported individually. |
| `fromDocx(bytes, provenanceOut?)` | `.docx` bytes → ProseMirror doc. Reads `document.xml`, styles, media, footnotes and endnotes; repairs ragged tables; de-duplicates heading ids; throws if the result fails `doc.check()`. The optional `provenanceOut` map is filled with `headingId → source paragraph index` — the closest thing it has to our provenance. |
| `fromDocxFull(bytes)` | Same, and also returns comment threads and the stored doc id. |
| `importDoc(documentXml, relsXml, media, stylesXml, notes, provenanceOut?)` | The importer without the container: takes XML strings rather than a `.docx`. |
| `toDocx(doc, opts)` | ProseMirror doc → `.docx` bytes. Writes `document.xml`, rels, media parts, and — when asked — `numbering.xml`, `footnotes.xml`, `endnotes.xml`, `comments.xml`. |
| `exportDoc(doc, opts)` | The export without the container: returns `{ documentXml, relsXml, mediaParts, … }`. |
| `newHeadingId()` | A fresh heading UUID. With `bookmarkNameForId` / `idFromBookmarkName` / `HEADING_BOOKMARK_PREFIX`, this is the `pmd-heading-<uuid>` bookmark convention heading ids round-trip through. |
| `serializeNative`, `parseNative`, `parseNativeSalvage`, `looksLikeNative`, `NATIVE_FILE_EXTENSION` | The `.cmir` native format: a gzip-compressed JSON envelope around the PM doc. Lossless for CardMirror, meaningless to Verbatim. |
| `Docx` | The OOXML container helper (read/write parts, content-type overrides, doc id). |
| `readDocIdFromBytes`, `stampDocId` | Stable per-document identity stamped into the `.docx`. |
| `importComments` | `comments.xml` + `commentsExtended.xml` → threads. |

Types (`ExportResult`, `ExportOptions`, `MediaPart`, `NativeFile`, …) are exported alongside.

The round-trip contract the project commits to is **semantic**, not byte, equivalence: aggressive
cleanup on import is explicitly fine (stylepox, abandoned custom styles, stray hyperlinks, font and
spacing overrides), Verbatim semantics are preserved, and exports use Verbatim's own style ids and
direct-formatting conventions. Its own test suite runs universal preservation checks (text length,
heading ids, mark counts, indent and spacing multisets) over a folder of `.docx` fixtures given by
`CARDMIRROR_DOCS_DIR`.

## Plugin bridge

Two surfaces, with different stability promises (from `reference-docs/cardmirror-plugin-api.md`):

* **The renderer plugin API is a DRAFT.** A plugin is one GitHub repo publishing a manifest and a
  built bundle as release assets. It registers commands that appear in the command palette and
  keybindings editor, and gets `extractSelection()`, `jumpToSource(token)`, `docInfo()`,
  `showToast()`, per-plugin `storage`, declared `settings`, and `flowApps()` / `flowPost()`.
  **Plugins are full-trust code** — they run with the editor's own access — so installs are limited
  to a curated allowlist served by the relay, with "Load plugin from file…" for development. A
  sandboxed v2 may change this surface.
* **The `cardmirror-bridge` handshake and its HTTP routes are FROZEN.** Each debate app writes an
  identity file and a session file into a shared per-user directory
  (`~/Library/Application Support/cardmirror-bridge/` on macOS); the routes are `GET /ping`,
  `GET /docs`, `POST /insert`, `POST /jump`, over loopback only, never the network. This is how
  flowing apps talk to the editor.

Extraction has rules worth knowing if we ever write a plugin: pocket, hat, block, tag and analytic
emit their full text; cite paragraphs emit the **short cite only**; undertags always emit; **card
bodies and loose paragraphs never emit, with no override**. Each item carries a heading UUID and an
opaque `cmsrc1…` source token that only CardMirror mints and parses. So the plugin API deliberately
cannot be used to pull evidence text out of a document — which is a point in its favour for us, and
also means a plugin is not a route to importing a debater's cards.

## Debate Decoded subscription

The editor is free. A linked paid Debate Decoded membership is required for exactly two things,
both of which go through CardMirror's relay server:

| Feature | Needs a subscription | Notes |
|---|---|---|
| Card sharing (send/receive cards between machines) | Yes | Desktop, and web once an account is linked in that browser profile. |
| Collaboration sessions (real-time co-editing) | Yes, for *starting* a session on the official relay | Shipped and default-on on desktop, surfaced as experimental. End-to-end encrypted; the relay only forwards ciphertext. Up to 10 participants. A guest can join a session from a link without an account. |
| Everything else — editing, import/export, read mode, send-to-speech, search, read-aloud, plugins, the `.cmir` format | No | Fully offline. |

A membership covers two machines; linking a third asks which to unlink. Server-side entitlement
gating (`RELAY_GATING`) is an env flag on the relay, with a 3-day grace for live sessions, and
self-hosting the relay is possible (`RELAY_PLUGIN_ALLOWLIST` is a self-hosted operator's own list).

The web edition is **deliberately capability-limited**: card sharing's crypto is Electron-main-only
and co-editing is hard-closed on a browser host by construction, so a browser tab never opens a
network session. Desktop is the tournament-day tool; the web edition is explicitly not for
tournament use. Desktop builds are unsigned, so Windows and macOS warn on first launch.

Nothing in the evaluation required a subscription, and none was bought. No real team, caselist or
camp file was loaded into a hosted CardMirror or Debate Decoded instance.

## License review: PolyForm Noncommercial 1.0.0

The full text is in the repository's `LICENSE` at the pinned commit, with a `Required Notice:` line
(copyright Anthony Trufanov, with ProseMirror and Untitled UI attributions) that must travel with
any copy we pass on. The terms that matter here:

* **Any noncommercial purpose is a permitted purpose.** Personal study, hobby projects and amateur
  pursuits are called out by name.
* **Noncommercial organizations** — charitable, educational, public research, government — are
  permitted "regardless of the source of funding".
* The copyright license covers everything that would otherwise infringe, for a permitted purpose;
  distribution and modification get their own explicit grants.
* **No sublicensing or transfer**, and no other implied licenses.
* A written patent-infringement claim ends the patent license immediately.
* A first violation can be cured within 32 days of written notice.
* The software comes as is, with no warranty and no liability.

### Per-use verdicts

| Use | Verdict | Reasoning |
|---|---|---|
| Debaters on the team install and use the desktop or web app for their own work | **Permitted** | Squarely "personal study" and "educational institution" use. This is the use the license was written for. |
| We run `fromDocx` / `toDocx` in operator tooling (this harness) to evaluate compatibility | **Permitted** | Research, experiment and testing, with no anticipated commercial application. Covered by both the personal-use and noncommercial-organization clauses. |
| We keep the harness in this repository and it stays operator-run | **Permitted** | No CardMirror code is vendored — `package.json` references the upstream git URL and npm fetches it. Nothing is redistributed. |
| We fork CardMirror and modify it for the team's own use | **Permitted** | The Changes and New Works License covers this for a permitted purpose. Distributing the fork requires passing on the terms and the `Required Notice:` lines. |
| The V2 web app **links to** CardMirror (a "download this file, open it in CardMirror" hint, or a deep link) | **Permitted** | Linking is not a use of the software under copyright. It carries no license obligation at all. |
| The V2 web app **embeds** the CardMirror editor (bundling its code into our app) | **Needs a decision about what the platform is** | Permitted if and only if the platform itself is noncommercial at the time. The license looks at *our* purpose, not at the code's placement. If this platform ever charges for access, sells subscriptions, or is operated by a company, an embedded CardMirror would need a separate commercial license from the author. |
| Any paid or commercial version of this platform, embedding or distributing CardMirror code | **Not permitted** without a separate license | Commercial use is explicitly outside the grant. |

### Open questions for the author

Neither blocks the decision, because the recommended option does not embed CardMirror.

1. **Where does the author draw the commercial line for a school-team tool?** A tool built for one
   high-school team, hosted at the coach's expense, is plainly noncommercial. The license's own
   "educational institution … regardless of the source of funding" clause covers it. Worth
   confirming in writing before any embedding, not before adopting it as an editor.
2. **Would the author grant a commercial license, and on what terms,** if this platform ever became
   a paid product that wanted to embed the editor? Cheap to ask now, expensive to discover later.
3. **Is the `provenanceOut` map on `fromDocx` a supported part of the API** or an internal
   convenience? It is the one export that would matter most to us if we ever did run CardMirror's
   importer in our pipeline.

**Signed off by:** _(Charlie — confirm the team's use is noncommercial and say whether any "needs a
decision" row must be resolved before ADR-0014 is accepted.)_

**Date:** _(pending)_

## Round-trip results

The harness is [`scripts/cardmirror-roundtrip/`](../../scripts/cardmirror-roundtrip/README.md):
`roundtrip.mjs` calls `fromDocx` then `toDocx` on each input file at the pinned commit, and
[`scripts/compare_docx_roundtrip.py`](../../scripts/compare_docx_roundtrip.py) compares each
original with its round-trip on paragraph text, structural unit, and underline / highlight / bold /
cite / font-size spans, writing an aggregate JSON summary keyed by a short sha256 prefix. Spans are
character ranges over paragraph text, not runs, so re-splitting runs is not counted as a change.

### Synthetic probes (run in this session)

These are small hand-built `.docx` files, not real debate files. They exist to prove the harness
works end to end and to isolate specific behaviours; they are **not** the sample the acceptance
criteria ask for. Run against CardMirror 1.11.0 at `bc92e6b`.

| Probe | Result |
|---|---|
| A conventional Verbatim card (Heading 1–4, `Style13ptBold` cite, `StyleUnderline` + yellow highlight body) | **Clean.** Paragraph text, heading levels, cite styling, underline, highlight and bold all unchanged. |
| The same card's export, inspected | `styles.xml` regenerated with canonical Verbatim ids (`Heading1`–`Heading4`, `Analytic`, `Undertag`, `Style13ptBold`, `StyleUnderline`, `Emphasis` and their `Char` variants); one `pmd-heading-<uuid>` bookmark pair per heading; body underline written as `StyleUnderline` **and** a direct `<w:u>`. |
| Heading carrying only `<w:outlineLvl w:val="0"/>`, no Verbatim heading formatting | **Structure lost** — imported as a plain paragraph. |
| `<w:outlineLvl w:val="0"/>` + bold + 26 pt | **Recognised** as a pocket. |
| `<w:outlineLvl w:val="3"/>` + bold | **Recognised** as a card with a tag and a body. |
| No styles, no outline levels, direct bold/underline only (a wiki or Google Docs export) | **Structure lost** — two plain paragraphs. |
| `<w:br w:type="page"/>` mid-paragraph | Survives as a break but **loses its page type**: re-exported as a plain `<w:br/>` line break. |
| `<w:sectPr>` | Replaced with CardMirror's default Letter / 1-inch section. |
| Tracked changes (`<w:ins>` + `<w:del>`) | Insertion kept, deletion dropped, **no revision markup re-emitted**. Matches the documented rule. |
| A two-cell table | Survives as `table` / `table_row` / `table_cell`. |

The two "structure lost" rows are the finding that matters. CardMirror promotes an outline-level
paragraph to a heading only when it also carries the Verbatim formatting signature — level 0 with
bold + 26 pt, level 1 with bold + 22 pt, level 2 with bold + underline + 16 pt, level 3 with
effective bold (`outlineHeadingNode` in `src/import/importer.ts`, mirroring its style cleaner). A
file with no styles *and* no outline levels has nothing to key on and stays flat. This is the same
wall our own parser will hit on non-Verbatim caselist uploads, and CardMirror's guard thresholds are
a good starting point for t02's heuristic classifier — including the guardrails, which exist to stop
an ordinary Word document that merely uses outline levels from being mis-structured.

### The 25-file sample (operator-run — NOT RUN)

The acceptance criterion asks for at least 25 real files (8+ team files across Policy/LD/PF, 12
caselist files from the hsld26 snapshots including 3+ non-Verbatim and 2+ wiki-converted, and 5 camp
files), round-tripped, with per-category results and each failure categorized. Those files live only
on Charlie's machine and must never enter this repository, so this section is filled in from the
operator run. The command block is in the session report under **Operator follow-ups**.

| File category | Files | Clean | With differences | Failed to import | Difference categories |
|---|---|---|---|---|---|
| Team (Policy / LD / PF) | | | | | |
| Caselist (Verbatim styles) | | | | | |
| Caselist (non-Verbatim) | | | | | |
| Caselist (wiki-converted) | | | | | |
| Camp / OpenEv | | | | | |

Per-file rows from `summary.json`, keyed by sha256 prefix, go below the table. Three of the results
also get opened in the CardMirror desktop app and in Word with Verbatim, edited and re-saved, to
confirm a CardMirror-exported file is still a full participant in a Verbatim team's file ecosystem.

## What this means for the rest of the epic

* **[t02, the style profile](../../plan_specs/v1/e31-debate-file-parsing/t02-verbatim-style-profile.yaml):**
  CardMirror's `PSTYLE_TO_NODE` and `MARK_TO_RSTYLE` are a second independent reading of Verbatim's
  style ids, and its `outlineHeadingNode` thresholds are a ready-made heuristic for files with no
  Verbatim styles. The dual underline encoding — and the fact that CardMirror writes *both*
  encodings on body runs — is a rule the profile has to state explicitly.
* **[t03, the parser](../../plan_specs/v1/e31-debate-file-parsing/t03-debate-docx-parser.yaml):** the
  card grouping we have to do by hand (tag, then cite and body paragraphs until the next tag) is what
  CardMirror's `card` content expression encodes; its "loose on purpose" ordering is a warning that
  real files do not follow a strict tag → cite → body sequence.
* **[v1-e33-t02, the lossless writer](../../plan_specs/v1/e33-file-builder/t02-lossless-card-writer.yaml):**
  its CardMirror checks are conditional on this ADR. If CardMirror is a compatibility target, a
  built file should survive a `fromDocx`/`toDocx` round-trip with no structural differences — this
  harness is exactly the check, and it is cheap to run on a generated file.
* **[v2-e35-t04, the debate tub](../../plan_specs/v2/e35-debate-tub/t04-tub-ui.yaml):** "Open in
  CardMirror" is a download plus a hand-off hint or a deep link. Both are outside the license's
  reach entirely, so neither needs the author's permission.
* **The V2 card editor and [v3-e20 file upload](../../plan_specs/v3/e20-file-intelligence/epic.yaml):**
  embedding CardMirror is the one use that turns on what this platform becomes commercially. The
  cost of keeping our own editor surface is real, but so is the cost of a license renegotiation in
  the middle of V2.

## References

* CardMirror at `bc92e6bd99cb9b3ce97ddacfa2362100db96360e`: `README.md`, `ARCHITECTURE.md` (§3 the
  round-trip contract, §4 the schema, §6 editions, §18 collaboration, §19 roadmap and non-goals),
  `MANUAL.md`, `reference-docs/cardmirror-plugin-api.md`, `LICENSE`, `src/schema/`, `src/import/`,
  `src/export/`, `src/ooxml/styles.ts`.
* [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/)
* [Verbatim](https://github.com/ashtarcommunications/verbatim)
* [ADR-0014](../adr/0014-debate-file-editor.md), [ADR-0006](../adr/0006-exact-source-evidence-verification.md)
* [§6 Repository and service boundaries](architecture_proposal.md#6-repository-and-service-boundaries),
  [§13 V3 detailed architecture](architecture_proposal.md#13-v3-detailed-architecture),
  [§16 Testing and evaluation strategy](architecture_proposal.md#16-testing-and-evaluation-strategy),
  [§18 Key architecture decisions](architecture_proposal.md#18-key-architecture-decisions-adrs)

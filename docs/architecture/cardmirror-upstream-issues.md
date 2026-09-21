# CardMirror upstream issues (drafted, not filed)

Defects found during the CardMirror evaluation
([`v1-e31-t01-cardmirror-evaluation`](../../plan_specs/v1/e31-debate-file-parsing/t01-cardmirror-evaluation.yaml))
that belong upstream rather than in our code. Each is written so it can be pasted into
[the CardMirror issue tracker](https://github.com/ant981228/cardmirror/issues) as is.

**Nothing here has been filed.** Charlie decides whether and when to file. Every reproduction is
synthetic: no file name, no path, no sentence from any real team, caselist or camp file appears
below, and none should be added when filing. If a maintainer asks for a failing file, build a fresh
synthetic one — do not send a debate file.

Status is tracked here. Update it when something is filed or fixed.

| # | Title | Severity | Status |
|---|---|---|---|
| 1 | Image alt text is not escaped for an XML attribute, producing an unreadable `.docx` | Data loss on save | Drafted, not filed |
| 2 | Soft hyphens (U+00AD) are dropped on import | Minor, by design? | Not drafted — see below |

---

## Issue 1 — Image alt text containing a quotation mark corrupts the exported `.docx`

**Title:** `toDocx` writes image alt text unescaped into an XML attribute, producing an unreadable
document

**Version:** 1.11.0 (`bc92e6bd99cb9b3ce97ddacfa2362100db96360e`)

### What happens

An inline image whose alt text contains a double quotation mark round-trips into a `.docx` whose
`word/document.xml` is not well-formed XML. Word reports unreadable content; any XML parser refuses
the file. The import side is fine — the problem is entirely in the export.

This is silent: `toDocx` returns successfully and the bytes are written. The damage is only visible
when something tries to read the result back.

### Cause

`buildDrawingXml` in `src/export/exporter.ts` escapes the alt text with `escText`, then interpolates
it into a double-quoted attribute value:

```ts
const altEsc = escText(alt);
...
`<wp:docPr id="${docPrId}" name="${escText(name)}" descr="${altEsc}"/>` +
...
`<pic:cNvPr id="${docPrId}" name="${escText(name)}" descr="${altEsc}"/>` +
```

`escText` (`src/ooxml/xml.ts`) escapes `&`, `<` and `>` — correct for element content. Attribute
values also need `"` escaped, which is what the neighbouring `escAttr` does. A `"` in the alt text
therefore closes the attribute early.

### Reproduction

1. Build a `.docx` containing one inline image whose `<wp:docPr>`/`<pic:cNvPr>` carry
   `descr="Emissions chart, &quot;Figure 3&quot;"`. (Word writes exactly this when a user types a
   quotation mark into an image's alt text.)
2. Round-trip it: `const out = await toDocx(await fromDocx(bytes))`.
3. Parse `word/document.xml` out of `out` with any XML parser.

Observed, with the escaped input parsing cleanly and the output not:

```
input  descr="Emissions chart, &quot;Figure 3&quot;"   → well-formed
output descr="Emissions chart, "Figure 3""             → not well-formed (invalid token)
```

A control file whose alt text has no quotation mark round-trips to well-formed XML, so the
quotation mark is the trigger.

### Suggested fix

Use `escAttr` for the `descr` attribute in both places in `buildDrawingXml`. `name` is generated
(`Picture N`) so it is safe today, but `escAttr` is the correct function for it too.

A regression test would round-trip an image whose alt text contains `"`, `&` and `<` together and
assert the exported `document.xml` parses. It may be worth asserting that every exported part
parses, since this class of bug is invisible until something reads the file.

### Why it matters to us

Debate files pick up images from pasted charts and screenshots, and Word's own alt text frequently
contains quoted figure captions. One file in our evaluation sample hit this. Until it is fixed,
anyone using CardMirror should avoid re-saving files that contain images — which is what
[ADR-0014](../adr/0014-debate-file-editor.md) tells the team.

---

## Issue 2 — Soft hyphens (U+00AD) are dropped on import

Not drafted as an issue, because it may well be deliberate: CardMirror's round-trip contract
(`ARCHITECTURE.md` §3) is semantic equivalence with aggressive cleanup on import, and a
discretionary hyphen is invisible presentation. It affected four files in our sample and changed no
visible text.

If it is ever worth raising, the question to ask is whether it is intentional, not to report it as
a bug. Either way it is a documented normalization on our side: the round-trip comparison counts
soft-hyphen drops separately from real differences
([`scripts/compare_docx_roundtrip.py`](../../scripts/compare_docx_roundtrip.py)), and our own parser
records U+00AD positions rather than discarding them.

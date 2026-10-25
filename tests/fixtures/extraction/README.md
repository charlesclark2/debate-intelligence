# Extraction fixtures (`v1-e04-t04-content-extraction`)

Samples for the HTML and PDF content extractors, and the paragraphs each must produce.

Every sample here is **synthetic**. The pages are built to look like the layouts the extractors
meet (a news article, a think-tank report, a federal agency page, an open-access journal article),
with navigation, ads, comment sections, bylines and JSON-LD where those layouts have them, but the
publications, people and text are invented for these tests. No saved real article is committed.

| Sample | What it is | Where it came from |
|---|---|---|
| `journal-article.pdf` | Three-page open-access journal article: running header and footer, page numbers, thirteen line-end hyphens | Written by `build_pdf_fixtures.py`, with no PDF library; its docstring lists every line and every break |

## Expected output is written by hand

Each sample's `<name>.expected.json` is written by hand from the sample (working agreement 6), never
saved from an extractor run. Each was committed failing before the extractor was built.

## Rebuilding the PDF

`test_pdf_extractor.py` checks that `journal-article.pdf` is byte for byte what the builder
produces. After changing the builder, rewrite it:

```bash
uv run python tests/fixtures/extraction/build_pdf_fixtures.py
```

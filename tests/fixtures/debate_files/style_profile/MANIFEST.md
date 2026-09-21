# Style profile fixtures

Every `.docx` in this directory, what it is for, where it came from, and — for anything taken from
a real file — when it was scrubbed and who confirmed it. Nothing lands here without a row.

The fixtures are read by
[`test_style_classifier.py`](../../../../packages/debate_core/tests/evidence/test_style_classifier.py)
and will be read by the parser (`v1-e31-t03`) and the accuracy evaluation (`v1-e31-t05`).

Beside each `.docx` is a `<name>.expected.json`: for every paragraph, the structural unit, the
rule id and the match source the classifier should produce. Those expectations are written by hand
in [`scripts/generate_style_fixtures.py`](../../../../scripts/generate_style_fixtures.py) — never
produced by running the classifier, because a fixture whose answers came from the code under test
proves nothing.

## Synthetic fixtures

Generated from the style profile's own writer style definitions, so a change to the profile shows
up here rather than leaving the fixtures quietly stale:

```bash
uv run python scripts/generate_style_fixtures.py
```

A test fails if the committed expectations name an older `profile_version` than the profile does.

The text in these files is invented. There is no real evidence, no real citation and no real team
in any of them, so none of them has been scrubbed and none needs to be.

| File | Shape it represents | Paragraphs | What it holds down |
|---|---|---|---|
| `verbatim-cut-card.docx` | A card cut the ordinary way in Verbatim | 8 | Every unit resolves from its own style. The evidence run carries `StyleUnderline` *and* a direct `<w:u>` at once, which is what CardMirror writes on export. |
| `drifted-style-names.docx` | The same styles after three seasons of copying | 4 | `Heading411` — a Heading 4 that inherits from `Heading1`, in 197 files of the survey — resolves to a tag, not a pocket. `HeadingFake` resolves through `basedOn`; `Analytics` through the alias list. |
| `outline-levels-only.docx` | A Google Docs export | 6 | No Verbatim style is defined or referenced. Structure survives only as `w:outlineLvl` plus the bold and sizes that go with each level. |
| `direct-formatting-only.docx` | A hand-formatted file | 5 | Neither styles nor outline levels — the shape CardMirror imports as loose paragraphs. Headings come from bold plus size, at a lower confidence, and shrunk body text is still evidence. |
| `wiki-converted-cite-entries.docx` | An opencaselist wiki conversion | 4 | The signature the survey found in 58 files: the whole Verbatim style set defined, not one paragraph referencing it. Cites carry an ellipsis between a card's first and last words. |
| `ordinary-document-with-outline-levels.docx` | A document that is not a debate file | 3 | The negative fixture. A syllabus that uses outline levels must not be promoted to pockets, hats, blocks or tags — this is why the heuristics have size and weight guards. |

## Scrubbed excerpts from real files

Four to six short excerpts of real team, caselist and camp files, so the fixtures above are
checked against formatting habits nobody invented. **None are committed yet**; the rows below are
the slots, and each one is filled in when its file lands.

Every excerpt goes through
[`scripts/scrub_docx_fixture.py`](../../../../scripts/scrub_docx_fixture.py) first, which removes
comments, `people.xml`, custom XML, `docProps` authorship and tracked-change authors, and replaces
names and team codes from a list the coach keeps outside this repository. The script refuses to
write a file in which any listed string survives. Then Charlie opens each one in Word and confirms
by eye that no name, team code or authorship metadata remains and that the formatting is what a
real file looks like. Both steps, in that order, before a file is committed.

| File | Category | Season | Scrubbed on | Coach confirmed | Why this excerpt |
|---|---|---|---|---|---|
| _(pending)_ | team, Verbatim | 2026-27 | — | — | A team file cut in Verbatim: the alias list checked against a template nobody designed for a test. |
| _(pending)_ | caselist, Verbatim | hsld26 | — | — | A disclosed file that has been through CardMirror, which is 78% of the caselist corpus. |
| _(pending)_ | caselist, non-Verbatim | hsld26 | — | — | A disclosure with no Verbatim style references, for the outline-level and direct-formatting rules. |
| _(pending)_ | caselist, wiki-converted | hsld26 | — | — | A wiki conversion with abbreviated cite entries. |
| _(pending)_ | camp | 2026 | — | — | A camp file, which is where a team's template habits spread from. |

### Adding one

```bash
uv run python scripts/scrub_docx_fixture.py <source>.docx \
    --output tests/fixtures/debate_files/style_profile/<descriptive-name>.docx \
    --replacements ~/.debate-intelligence/fixture-replacements.yaml
```

Keep the excerpt short — a few cards, not a whole file. Open the result in Word, check it, then
add its row above with the scrub date and your confirmation, and commit the two together.

Real files that have **not** been through both steps do not belong in this repository at all, not
in a branch and not in a stash. The replacement list is not committed either: it names real
students.

# Structural fixtures for the debate `.docx` parser

Every `.docx` in this directory, what it stands for, and where it came from. Nothing lands here
without a row.

They are read by
[`test_structural_fixtures.py`](../../../../packages/debate_core/tests/integrations/docx_parser/test_structural_fixtures.py)
and will be read by the accuracy evaluation ([`v1-e31-t05`](../../../../plan_specs/v1/e31-debate-file-parsing/t05-parser-eval.yaml))
and the parse pipeline ([`v1-e31-t06`](../../../../plan_specs/v1/e31-debate-file-parsing/t06-parse-pipeline.yaml)).

Beside each `.docx` is a `<name>.expected.json`: for every paragraph, the structural unit, the
rule id, the match source and the section path the parser should produce; for every card, its tag,
short cite, full cite, undertag, completeness, element range and the exact characters each
underline span must select. **Those answers are written by hand** in
[`scripts/generate_structural_fixtures.py`](../../../../scripts/generate_structural_fixtures.py)
and are never produced by running the parser, because a fixture whose answers came from the code
under test proves nothing. Writing them by hand is not ceremony: it is what caught the section-path
bug where a second tag under a block came out as a child of the first tag rather than its sibling.

## Regenerating

```bash
uv run python scripts/generate_structural_fixtures.py
```

A test fails if the committed answers name an older `parser_version` than the parser does, so a
change to the output has to come with a re-reading of these answers rather than a silent refresh.

## The fixtures

Families are the ones [the style survey](../../../../docs/data/debate-file-style-survey.md#template-families)
measured: `verbatim` (23% of the corpus), `cardmirror` (63%), `wiki-converted` (3%) and
`other-heuristic` (11%). The corpus column says which kind of import a file of this shape arrives
from, not who cut the cards in it.

| File | Family | Corpus | What it holds down |
|---|---|---|---|
| `team-verbatim-file.docx` | verbatim | team | Pocket, hat, block, tag, cite and body, each resolving from its own style. The shape 276 of 374 team files in the survey have. |
| `cardmirror-caselist-upload.docx` | cardmirror | caselist | The most common shape in the whole corpus: `pmd-heading-` bookmarks, and **both** underline encodings on every body run. A reader that counts them separately doubles the underlining of 63% of the corpus. |
| `cardmirror-camp-file.docx` | cardmirror | camp | Two cards stacked under one block, as 75 of 110 camp files are. A second tag closes the first card and is its sibling, not its child. |
| `wiki-converted-cite-entries.docx` | wiki-converted | caselist | The whole Verbatim style set defined and not one paragraph referencing it. One card is first-and-last-words with an ellipsis (`ABBREVIATED`), one is a cite with no body (`CITE_ONLY`). Neither is padded and neither is dropped. |
| `non-verbatim-caselist-upload.docx` | other-heuristic | caselist | A Google Docs export: structure survives only as `w:outlineLvl` plus the bold and sizes that go with each level. |
| `pre-2026-direct-formatting.docx` | other-heuristic | team | `Heading411` — a Heading 4 that Word de-duplicated twice, in 197 survey files — resolves to a tag, not to the pocket its id starts with. The block above it is bold underlined text and nothing else. |
| `analytics-and-undertags.docx` | verbatim | team | The two units that are not cards, plus the one case only the assembly can decide: a `Heading4` with no cite and no body under it is a line of analysis, and it still sits at tag level. |
| `tables-and-text-boxes.docx` | verbatim | team | A table cell carrying `Heading4` is `OTHER` anyway, and a text box Word wrote twice is read once. |
| `tracked-changes-and-comments.docx` | verbatim | team | The insertion is in the card and the deletion is not. The package's `docProps` authorship and `word/comments.xml` all say `NEVER READ`, and a test asserts that string reaches no output. |
| `not-a-debate-file.docx` | not-a-debate-file | negative | A syllabus that uses outline levels must not become a stack of pockets and must produce no cards. This is what the profile's size and weight guards are for. |

The 300-page timing file goal criterion ac6 asks for is **not** in this directory. It is built in
memory by the `slow` test, because a multi-megabyte binary that changes whenever the generator
does is not a fixture worth committing or reviewing.

## Why there are no real files or excerpts here

There are none, and there should not be. This is the ruling the PM merged with
[`v1-e31-t02`](../../../../plan_specs/v1/e31-debate-file-parsing/t02-verbatim-style-profile.yaml),
and it holds whether or not a file has been scrubbed.

**Redistribution.** [`docs/policies/caselist-data-use.md`](../../../../docs/policies/caselist-data-use.md)
prohibition 1 forbids publishing the archives, the sources, the parsed cards **or any file built
from them** to a git repository, and prohibition 9 forbids committing real caselist or camp files
or excerpts at all. This repository is public.

**There is no such thing as a file that is only one team's work.** Teams read cards other teams
cut and disclosed — that is what open-source debate is. So "our own files" is not a category that
can be separated out and committed, and scrubbing does not rescue it: replacing a debater's
initials protects that debater, but the card is still another school's disclosed evidence,
republished outside the login it sits behind.

**What does the job instead.** The synthetic fixtures above cover every template family the survey
measured, which is what CI needs, and they are stronger than real files for this purpose because
their answers can be written down in advance. Real-file accuracy is measured where the policy
already puts it: [`v1-e31-t05-parser-eval`](../../../../plan_specs/v1/e31-debate-file-parsing/t05-parser-eval.yaml)
runs against the corpus **in place** on the operator's machine.

[`scripts/scrub_docx_fixture.py`](../../../../scripts/scrub_docx_fixture.py) remains the gate if a
real file is ever proposed for committing — which needs the policy changed first, not a scrub.
**Nothing derived from a real debate file is committed here without that question being settled.**
Not in a branch, not in a stash, not "temporarily".

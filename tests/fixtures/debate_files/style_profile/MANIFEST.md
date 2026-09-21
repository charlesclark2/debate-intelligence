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

## Why there are no excerpts of real files here

The task spec asked for four to six scrubbed excerpts of real team, caselist and camp files. There
are none, and there should not be. Two things rule them out, and the second one has no workaround.

**Redistribution.** [`docs/policies/caselist-data-use.md`](../../../../docs/policies/caselist-data-use.md)
prohibition 1 forbids publishing "the archives, the sources, the parsed cards **or any file built
from them**" to a git repository, and prohibition 9 forbids committing real caselist or camp files
or excerpts at all. This repository is public.

**There is no such thing as a file that is only one team's work.** Teams routinely read cards other
teams cut and disclosed — that is what open-source debate is, and a team that refused to would just
be re-cutting evidence somebody already found. It shows up plainly in the corpus: of fourteen of
this team's own files, eight carry cite-tail cutter marks belonging to other programs' debaters or
strings shaped like other schools' team codes, and the remaining six carry no marks at all, which
proves nothing either way. So "our own files" is not a category that can be separated out and
committed. Scrubbing does not rescue it: replacing a debater's initials protects that debater, but
the card is still another school's disclosed evidence, republished outside the login it sits behind.

**What does the job instead.** The synthetic fixtures above cover all four template families, which
is what CI needs. Real-file coverage is measured where the policy already puts it —
[`v1-e31-t05-parser-eval`](../../../../plan_specs/v1/e31-debate-file-parsing/t05-parser-eval.yaml)
runs against the whole corpus **in place** on the operator's machine, which is both permitted
(permitted use 5) and stronger evidence than six hand-picked files would have been.

## The scrub script still matters

[`scripts/scrub_docx_fixture.py`](../../../../scripts/scrub_docx_fixture.py) is not obsolete. It
strips authorship metadata, comments, `people.xml`, custom XML and tracked-change authors, and
replaces names and team codes from a list kept outside this repository. Use it for any scrubbed
copy that stays on the operator's machine, and it remains the gate if a file ever is proposed for
committing — which needs the policy changed first, not a scrub.

**Nothing derived from a real debate file is committed here without that policy question being
settled first.** Not in a branch, not in a stash, not "temporarily".

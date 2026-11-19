# Golden card corpus: what is kept here, and what is not

This folder holds E09's golden cases (`v1-e09-t01-golden-card-fixtures`), on the terms of the PM's
rulings of 2026-11-14. `INDEX.md` lists the cases; `scripts/import_golden_card.py` writes them.

## The team's cards are here

* Each case holds **one card**, copied out of a team file and scrubbed, never a whole file. The rule
  of 2026-10-26 (no team file is copied into the repository in any form) still stands; one scrubbed
  excerpt of a card the coach vouches for is outside it.
* Only cards **the coach cut or re-cut**, and **reviewed for names** by the coach (the product
  owner's ruling of 2026-11-14). A debater's own cut is not picked, nor is a card copied from
  another program, the caselist or a camp file, and the listing leaves out the `Opencaselist` and
  `Camp Files` folders entirely. The import asks the coach about each pick and refuses a card the
  coach does not confirm, and `case.json` records the answer (`coach_cut_and_reviewed_for_names`).
  That attestation is the control on names. A roster denylist is optional and off by default.
* Every import strips the document metadata, comments and tracked-change authors and the cutter
  mark at the end of the cite, and `import_golden_card.py check` fails on any metadata it finds.
* One allowance, in `expected.docx` only (PM ruling of 2026-11-16): the renderer's own name,
  `debate-research`, as author and last editor, and its three card-manifest custom XML parts
  (`customXml/item1.xml`, `customXml/itemProps1.xml`, `customXml/_rels/item1.xml.rels`). Any
  person's name, any other metadata, and the same name or parts in `team-card.docx` still fail.
  `tests/golden/test_label_golden_card.py` pins both halves.

## The source pages are not

The repository is public, so **no source page or snapshot enters it**, in this folder or anywhere
else. Each case's `case.json` records what identifies the page instead: the snapshot's SHA-256, raw
and normalized, its URL, the fetch date and access status, and the card's offsets into it.

The snapshots themselves live in a local fixtures folder outside the repository, on the operator's
machine. The operator's `import_golden_card.py check`, given that folder, verifies each digest and
reproduces the card's evidence from the offsets. CI never sees a snapshot. A source that is
paywalled, private (behind a login) or disallowed by robots is dropped from the corpus, not kept
as a case with a local snapshot.

## What each case holds

| File | What it is | Written by |
|---|---|---|
| `team-card.docx` | The coach's card, scrubbed | `import_golden_card.py import` |
| `case.json` | Event, season, source type, length, cut, research need, the coach's attestation, and `snapshot`: the digests, URL, fetch date and access status | `import`, then `import_golden_card.py record` |
| `expected.json` | The card: its segments and its underline and highlight spans as offsets into the snapshot, and the team's tag, cite and research need. Never evidence text | `label_golden_card.py` |
| `expected.docx` | The card rendered in `team-default` from `expected.json` and the snapshot, with the verifier's verdict | `label_golden_card.py --render-expected` |

The span labels are the coach's own: every card is one the coach cut or re-cut, so its underlining
and highlighting are carried over as they are, onto the snapshot's characters. A span's purpose
is recorded only where the team's format profile defines what a markup kind means, and is never
invented (PM ruling of 2026-11-16). Today every purpose is null: `team-default` sets sizes and a
highlight colour that its style profile counts as a reading colour, but a span's purpose can only
be claim, warrant, internal link or impact, and no profile maps a markup kind to one of those.

`expected.docx` carries the verifier's real verdict. The cite is the team's, typed by hand, so no
citation field is verified and every render is UNVERIFIED (`CITATION_UNVERIFIED`) with its banner.
Nothing sets VERIFIED by hand. If citations are later harvested from the snapshots, the renders are
regenerated with `label_golden_card.py --render-expected`, never edited. CI checks the
structure (`tests/golden/test_corpus_structure.py`) and the scrub
(`tests/golden/test_fixture_scrubbed.py`); only the operator's `import_golden_card.py check
--snapshots` can check the offsets against the snapshots.

`v1-e04-t06`'s rule that every fixture is synthetic, and `v1-e04-t07`'s prohibition on committing
a real page, hold here as everywhere.

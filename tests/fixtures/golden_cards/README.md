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

## The source pages are not

The repository is public, so **no source page or snapshot enters it**, in this folder or anywhere
else. Each case's `case.json` records what identifies the page instead: the snapshot's SHA-256, raw
and normalized, its URL, the fetch date and access status, and the card's offsets into it.

The snapshots themselves live in a local fixtures folder outside the repository, on the operator's
machine. The operator's `import_golden_card.py check`, given that folder, verifies each digest and
reproduces the card's evidence from the offsets. CI never sees a snapshot. A source that is
paywalled, private (behind a login) or disallowed by robots is dropped from the corpus, not kept
as a case with a local snapshot.

`v1-e04-t06`'s rule that every fixture is synthetic, and `v1-e04-t07`'s prohibition on committing
a real page, hold here as everywhere.

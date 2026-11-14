# Golden card corpus

The cases E09's tests and evaluations are measured on (`v1-e09-t01-golden-card-fixtures`). Each
folder holds one card the coach cut or re-cut and reviewed for names: `team-card.docx`, the card's
own paragraphs copied out of the team file and scrubbed (document metadata, comments,
tracked-change authors and cutter marks), and `case.json`, what the table below says about it.
Later steps add the source snapshot's digests and the card's offsets to `case.json` (the snapshot
itself stays outside the repository), `expected.json` and the expected render. What the corpus
keeps, and what it never does, is in `README.md`.

Written by `scripts/import_golden_card.py`, which rewrites this file after every import; do not
edit it by hand. The research need is the card's tag, which says what the card is for.

| Case | Event | Season | Source type | Length | Omission cut | Research need |
|---|---|---|---|---|---|---|

0 cases.

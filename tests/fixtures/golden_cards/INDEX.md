# Golden card corpus

The cases E09's tests and evaluations are measured on (`v1-e09-t01-golden-card-fixtures`). Each
folder holds one card the coach cut or re-cut and reviewed for names: `team-card.docx`, the card's
own paragraphs copied out of the team file and scrubbed (document metadata, comments,
tracked-change authors and cutter marks), and `case.json`, what the table below says about it and
the source snapshot's digests, URL, fetch date and access status (the snapshot itself stays outside
the repository). Once labelled, a case also holds `expected.json`, the card's segments and spans as
offsets into that snapshot, and `expected.docx`, the card as the renderer draws it. What the corpus
keeps, and what it never does, is in `README.md`.

Written by `scripts/import_golden_card.py`, which rewrites this file after every import; do not
edit it by hand. The research need is the card's tag, which says what the card is for.

| Case | Event | Season | Source type | Length | Omission cut | Research need |
|---|---|---|---|---|---|---|

0 cases.
By event: Policy 0, LD 0, PF 0.
By source type: news 0, think tank 0, government 0, journal 0, unknown 0.

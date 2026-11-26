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
| `ld-003` | LD | 2024-25 | think tank | multi-paragraph | yes | Expanding the EITC is a disaster for the already cash strapped IRS---turns case---harker in yellow |
| `ld-006` | LD | 2024-25 | news | short | no | Independently, deep sea mining obliterates tuna populations |
| `ld-007` | LD | 2026-27 | think tank | short | no | Colonization risks causing suffering for extraterrestrial sentient life. |
| `ld-009` | LD | 2024-25 | government | multi-paragraph | yes | ‘Living wage’ applies to everyone. The aff doesn’t. |
| `ld-011` | LD | 2025-26 | government | multi-paragraph | no | Judicial independence high now. |
| `ld-013` | LD | 2026-27 | unknown | short | no | Helium 3 provides key REEs and renewable energy back on earth. |
| `ld-015` | LD | 2025-26 | news | short | yes | Single payer lowers pharma prices |
| `ld-016` | LD | 2024-25 | news | multi-paragraph | yes | Rapidly increases coal production. |
| `ld-017` | LD | 2024-25 | think tank | multi-paragraph | yes | Successful invasion causes extinction from a litany of crises. |
| `pf-001` | PF | 2024-25 | news | short | yes | 3. T: Without commitments to Taiwan, the US can strengthen allied commitments |
| `pf-003` | PF | 2024-25 | think tank | short | yes | Piracy in the Strait of Hormuz risks reducing SLOCS |
| `pf-004` | PF | 2025-26 | think tank | multi-paragraph | yes | China’s investment of Africa consistently traps countries in debt, causing financial troubles and widespread instability. |
| `pf-008` | PF | 2024-25 | unknown | short | yes | Unfortunately, perception of US support kills Taiwanesne self-defense - politicians use US presence to justify other spending |
| `pf-010` | PF | 2025-26 | think tank | short | no | People don’t trust the government to use data |
| `pf-011` | PF | 2024-25 | think tank | multi-paragraph | no | Selloffs cause Middle East war. |
| `pf-014` | PF | 2024-25 | think tank | short | yes | China needs absolute certainty and will indefinitely delay invasion |
| `pf-021` | PF | 2024-25 | journal | short | no | Xi has to respond --- Lai’s rhetoric decks legitimacy and causes secessionist chaos while harming perceptions of China in Taiwan. |
| `pf-022` | PF | 2024-25 | unknown | short | no | No country dares recklessly start conflict now |
| `pf-024` | PF | 2025-26 | news | multi-paragraph | no | People of color will be targeted. Professor Friedman of the University of Southern California notes that |
| `pf-026` | PF | 2025-26 | think tank | multi-paragraph | no | 4. Cartels aren’t dependent on the US |
| `pf-027` | PF | 2024-25 | journal | short | no | Alliances are strong even after Trump’s victory. |
| `pf-033` | PF | 2024-25 | think tank | multi-paragraph | no | Extinction. |
| `pf-035` | PF | 2025-26 | unknown | multi-paragraph | no | Circumventing encryption threatens democracy through bulk surveillance |
| `policy-002` | Policy | 2026-27 | think tank | short | yes | Isolationism increases the risk of global nuclear conflict |
| `policy-003` | Policy | 2026-27 | think tank | multi-paragraph | yes | No existential risk from engineered pathogens – too many barriers and no data supports it |
| `policy-005` | Policy | 2026-27 | unknown | short | no | Power vacuums cause nuke wars. |
| `policy-006` | Policy | 2026-27 | unknown | multi-paragraph | yes | Claims of a Mortality gap from lack of insurance are based on a small study, a larger study over a longer time period disprove it. |
| `policy-011` | Policy | 2026-27 | news | multi-paragraph | no | Fundamentals check and their causality is empirically wrong. |
| `policy-014` | Policy | 2026-27 | unknown | multi-paragraph | no | Tens of thousands of people die every year due to coverage gaps in healthcare |
| `policy-015` | Policy | 2026-27 | think tank | multi-paragraph | no | Safeguards are empirically ineffective |
| `policy-016` | Policy | 2026-27 | think tank | short | yes | Isolationism increases the risk of global nuclear conflict |

31 cases.
By event: Policy 8, LD 9, PF 14.
By source type: news 6, think tank 14, government 2, journal 2, unknown 7.
Retired: ld-001, ld-002, ld-004, ld-005, ld-008, ld-010, ld-012, ld-014, ld-018, pf-002, pf-005, pf-006, pf-007, pf-009, pf-012, pf-013, pf-015, pf-016, pf-017, pf-018, pf-019, pf-020, pf-023, pf-025, pf-028, pf-029, pf-030, pf-031, pf-032, pf-034, pf-036, policy-001, policy-004, policy-007, policy-008, policy-009, policy-010, policy-012, policy-013, policy-017.

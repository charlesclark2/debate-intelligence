# Argument landscape: synthpolicy26 through 2026-09-15

Every count comes from files teams disclosed to the caselist (FILE_IMPORT), not from evidence the platform has verified. No school, team or debater is named.

## About this report

| | |
|---|---|
| Caselist | synthpolicy26 |
| Snapshot | 2026-09-15 (previous: 2026-09-08) |
| Topic | synthetic-policy-topic |
| Taxonomy version | 1.2.0 |
| Coach's overrides | 1789afec01f8e1417460965e050263e11df2d4128ca0ed9604d1643f430639a0 |
| Parser version | 2026.10.20-docx-6 |
| Prompt version | none (deterministic classification, no model) |
| Classification coverage | 33 of 44 cards (75.0%); 15 of 16 rounds (93.8%) |
| Review threshold | 0.6 |
| Disclosures counted | 16 rounds by 8 teams: 7 aff rounds by 6 teams, 8 neg rounds by 6 teams |
| Data freshness | Current: the newest snapshot is 2026-09-15, 2 day(s) old |

How to read the numbers:

* **Rounds** are disclosed rounds: one team, one side, one tournament round. A round reads a position when one of its cards is placed under it at or above the review threshold.
* **Teams** are distinct teams, on any side.
* **Share of teams** is the teams that read a position on its own side, over the teams that disclosed on that side through 2026-09-15: 6 on the affirmative, 6 on the negative, and all 8 for a position either side reads.
* **New** means first disclosed after the previous snapshot.
* A card under an `AT:` heading answers a position and never counts as reading it, and so does a card placed under a position in a round on the other side: a `Midterms DA` block in an affirmative file is the 2AC answering it.
* Each position's 5 most-read cards are in `top_cards.csv`, where near-duplicate copies of a card count as one card.

## Affirmative positions

### Affs

| Position | Rounds | Teams | Aff rounds | Neg rounds | Share of teams | First seen | New |
|---|---|---|---|---|---|---|---|
| Single payer (`single-payer-aff`) | 3 | 2 | 3 | 0 | 33.3% | 2026-09-08 |  |
| Public option (`public-option-aff`) | 1 | 1 | 1 | 0 | 16.7% | 2026-09-08 |  |

### Advantages

| Position | Rounds | Teams | Aff rounds | Neg rounds | Share of teams | First seen | New |
|---|---|---|---|---|---|---|---|
| Costs advantage (`costs-advantage`) | 6 | 5 | 6 | 0 | 83.3% | 2026-09-08 |  |
| Innovation advantage (`innovation-advantage`) | 3 | 3 | 3 | 0 | 50.0% | 2026-09-08 |  |

### Theory

| Position | Rounds | Teams | Aff rounds | Neg rounds | Share of teams | First seen | New |
|---|---|---|---|---|---|---|---|
| Condo bad (`condo-bad`) | 1 | 1 | 1 | 0 | 16.7% | 2026-09-15 | yes |

## Negative positions

### Disadvantages

| Position | Rounds | Teams | Aff rounds | Neg rounds | Share of teams | First seen | New |
|---|---|---|---|---|---|---|---|
| Spending DA (`spending-da`) | 4 | 4 | 0 | 4 | 66.7% | 2026-09-08 |  |
| Midterms DA (`election-da`) | 2 | 2 | 0 | 2 | 33.3% | 2026-09-08 |  |
| Hospital closures DA (`hospital-closures-da`) | 1 | 1 | 0 | 1 | 16.7% | 2026-09-15 | yes |
| Provider strikes DA (`provider-strikes-da`) | 1 | 1 | 0 | 1 | 16.7% | 2026-09-15 | yes |

### Counterplans

| Position | Rounds | Teams | Aff rounds | Neg rounds | Share of teams | First seen | New |
|---|---|---|---|---|---|---|---|
| States CP (`states-cp`) | 3 | 3 | 0 | 3 | 50.0% | 2026-09-08 |  |

### Kritiks

| Position | Rounds | Teams | Aff rounds | Neg rounds | Share of teams | First seen | New |
|---|---|---|---|---|---|---|---|
| Capitalism K (`cap-k`) | 3 | 3 | 0 | 2 | 33.3% | 2026-09-08 |  |

### Topicality

| Position | Rounds | Teams | Aff rounds | Neg rounds | Share of teams | First seen | New |
|---|---|---|---|---|---|---|---|
| T: national health insurance (`nhi-t`) | 2 | 1 | 0 | 2 | 16.7% | 2026-09-08 |  |

## New this week

Positions first disclosed after 2026-09-08:

* Condo bad (`condo-bad`, theory): 1 round, 1 team
* Hospital closures DA (`hospital-closures-da`, da): 1 round, 1 team
* Provider strikes DA (`provider-strikes-da`, da): 1 round, 1 team

## Unclassified

What this report could not count:

* **Cards:** 10 of 44 (22.7%): 8 waiting in the review queue, 2 placed below the review threshold (0.6).
* **Aff rounds with no identified aff:** 3 of 7 (42.9%).
* **Neg rounds with no placed negative position:** 1 of 8 (12.5%).
* Counted as answers, not reads: 1 round that placed a card under a position of the other side, counted once per position.
* Not counted and not queued: 1 card under headings the coach ruled name no position.

How affirmative rounds were identified:

| Method | Aff rounds |
|---|---|
| A card in the round placed under the aff (`PLACED_CARD`) | 4 |
| Not identified | 3 |

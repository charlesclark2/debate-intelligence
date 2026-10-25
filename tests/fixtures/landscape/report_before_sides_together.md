# Argument landscape: synthpolicy26 through 2026-09-15

Every count comes from files teams disclosed to the caselist (FILE_IMPORT), not from evidence the platform has verified. No school, team or debater is named.

**Short history.** The data covers 2 weekly windows on this topic, 2026-09-02 to 2026-09-15, and the topic's dates are not known here, so it may cover less than a full topic cycle. A trend here is one week's change against the week before, not a season's.

## About this report

| | |
|---|---|
| Caselist | synthpolicy26 |
| Snapshot | 2026-09-15 (previous: 2026-09-08) |
| Weekly windows | 2 on this topic, the first 2026-09-02 to 2026-09-08; this week's 2026-09-09 to 2026-09-15, compared with 2026-09-02 to 2026-09-08 |
| Topic | synthetic-policy-topic |
| Taxonomy version | 1.2.0 |
| Coach's overrides | 1789afec01f8e1417460965e050263e11df2d4128ca0ed9604d1643f430639a0 |
| Parser version | 2026.10.20-docx-6 |
| Prompt version | none (deterministic classification, no model) |
| Classification coverage | 45 of 56 cards (80.4%); 15 of 16 rounds (93.8%) |
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
* **Impact cards**, under each advantage and DA, are up to 3 of its cards labelled as an impact, ranked by the teams reading them: a heading over the card says `impact` or `impacts` (not `no impact`, `impact defense` or `impact turn`) or `turns case`, or its tag opens with an impact word such as `extinction`, `existential` or `the impact`. Only the labelled copies of a card count. An impact nobody labelled is not found, so each kind says how many of its documents carry no labelled impact. They are also in `impact_cards.csv`.
* **What each impact runs through**, under its impact cards: a row's **scenario** is heading words two or more teams use under the position (a `Scenario 1` heading's name, a named heading, or the words beside an impact or internal-link label, such as `Dome impact`), and its **internal link** is the nearest card above it under the same position heading that a heading or its tag labels an internal link. Neither is guessed. With no labelled internal link, the card directly above the impact card in its block is shown as the card above it in the file when it is not an impact card itself: where it sits, not what it does. A scenario name holding a word of a caselist school, team code or tournament is withheld.
* **The link chain** of each advantage and DA is its most-read card for each role a team labelled, by a heading under the position or the tag's first words: uniqueness (`U`, `UQ`), link, internal link (`IL`) and impact, and for an advantage harms, inherency and solvency. An `AT:` heading, a heading naming two roles, and a card that answers the position or is read on the other side fill no role. A role no team labelled says so.
* **Trends** compare this week's window with the previous one. A round counts in the week its file was first disclosed, whatever path it was later filed under, and a position's share is the teams that read it that week on its own side over the week's teams disclosing on that side: this week 4 on the affirmative and 4 on the negative, the previous 3 and 4. **NEW** is read for the first time on this topic; **RISING** and **FALLING** moved by at least 5 points with at least 3 teams reading it in one of the two weeks; everything else is **STEADY**. Every position's row is in `trends.csv`.

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

#### Advantages: impact cards

Advantage documents with no labelled impact: 3 of 6 (50.0%).

Advantage documents with no scenario heading and no role label: 1 of 6 (16.7%).

* Impact rows: 3; with a scenario two or more teams name: 1.
* With a labelled internal link: 0 of 3 rows; with none: 3, of which 1 shows the card above it in the file.
* Scenario names withheld for holding a word of a caselist school, team code or tournament: 0.
* Positions with no labelled card, by role: uniqueness 2 of 2, link 2 of 2, internal link 1 of 2, impact 1 of 2, harms 2 of 2, inherency 2 of 2, solvency 1 of 2.

**Costs advantage** (`costs-advantage`)

| Rank | Teams | Tag | Cite | Scenario |
|---|---|---|---|---|
| 1 | 1 | 2. Extinction from economic collapse | Okafor 25 | economic collapse |
| 2 | 1 | Bulk purchasing lowers drug prices | Haddad 23 |  |
| 3 | 1 | Extinction from a debt crisis | Okafor 26 |  |

What each impact runs through:

* Rank 1: no labelled internal link. Card above it in the file: Single payer cuts administrative costs
* Rank 2: no labelled internal link.
* Rank 3: no labelled internal link.

Link chain:

| Role | Teams | Tag | Cite |
|---|---|---|---|
| Uniqueness |  | no labelled card |  |
| Link |  | no labelled card |  |
| Internal link |  | no labelled card |  |
| Impact | 1 | 2. Extinction from economic collapse | Okafor 25 |
| Harms |  | no labelled card |  |
| Inherency |  | no labelled card |  |
| Solvency | 1 | Single payer solves within a year | Reyes 25 |

**Innovation advantage** (`innovation-advantage`): no labelled impact card.

Link chain:

| Role | Teams | Tag | Cite |
|---|---|---|---|
| Uniqueness |  | no labelled card |  |
| Link |  | no labelled card |  |
| Internal link | 1 | Single payer frees capital for research | Moreau 25 |
| Impact |  | no labelled card |  |
| Harms |  | no labelled card |  |
| Inherency |  | no labelled card |  |
| Solvency |  | no labelled card |  |

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

#### Disadvantages: impact cards

DA documents with no labelled impact: 2 of 6 (33.3%).

DA documents with no scenario heading and no role label: 2 of 6 (33.3%).

* Impact rows: 4; with a scenario two or more teams name: 1.
* With a labelled internal link: 1 of 4 rows; with none: 3, of which 0 show the card above it in the file.
* Scenario names withheld for holding a word of a caselist school, team code or tournament: 1.
* Positions with no labelled card, by role: uniqueness 3 of 4, link 2 of 4, internal link 3 of 4, impact 2 of 4.

**Spending DA** (`spending-da`)

| Rank | Teams | Tag | Cite | Scenario |
|---|---|---|---|---|
| 1 | 2 | Debt ceiling fights are near | Ruiz 26 |  |
| 2 | 1 | Spending triggers a debt spiral | Ito 26 |  |
| 3 | 1 | Rate spikes cause a recession | Park 26 | recession |

What each impact runs through:

* Rank 1: no labelled internal link.
* Rank 2: no labelled internal link.
* Rank 3: Internal link: Deficits spike interest rates

Link chain:

| Role | Teams | Tag | Cite |
|---|---|---|---|
| Uniqueness | 1 | Spending is at a record high now | Ito 25 |
| Link | 2 | Spending triggers a debt spiral | Ito 26 |
| Internal link | 1 | Deficits spike interest rates | Lee 26 |
| Impact | 2 | Debt ceiling fights are near | Ruiz 26 |

**Midterms DA** (`election-da`): no labelled impact card.

Link chain:

| Role | Teams | Tag | Cite |
|---|---|---|---|
| Uniqueness |  | no labelled card |  |
| Link | 1 | The link: reform polls badly | Ward 26 |
| Internal link |  | no labelled card |  |
| Impact |  | no labelled card |  |

**Hospital closures DA** (`hospital-closures-da`)

| Rank | Teams | Tag | Cite | Scenario |
|---|---|---|---|---|
| 1 | 1 | Rural hospitals close under single payer | Duarte 26 |  |

What each impact runs through:

* Rank 1: no labelled internal link.

Link chain:

| Role | Teams | Tag | Cite |
|---|---|---|---|
| Uniqueness |  | no labelled card |  |
| Link |  | no labelled card |  |
| Internal link |  | no labelled card |  |
| Impact | 1 | Rural hospitals close under single payer | Duarte 26 |

**Provider strikes DA** (`provider-strikes-da`): no labelled impact card.

Link chain:

| Role | Teams | Tag | Cite |
|---|---|---|---|
| Uniqueness |  | no labelled card |  |
| Link |  | no labelled card |  |
| Internal link |  | no labelled card |  |
| Impact |  | no labelled card |  |

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

## Advantages by affirmative

Under each aff, the advantages read in the affirmative rounds assigned to it (by the round's plan text or the team's other rounds), ranked by the teams reading them; the 5 the most teams read are shown. A round assigned to a mechanism counts under the mechanism and once under its aff. An advantage read in a round assigned to another aff is never counted under this one, and nothing is taken from an advantage's name.

No affirmative round assigned an aff reads an advantage.

9 advantage reads in 7 affirmative rounds, by 6 teams, have no assigned aff.
A placed card identifies the aff of 4 of those rounds, and their advantages are not counted under it.

## Counterplan texts, alternatives and roles of the ballot

The teams' own words, quoted as their files hold them (data-use policy 1.13), never beside a school or team code. A text belongs to the position its section is placed under: the nearest placed heading over its label, as a card is placed. A label under no placed heading is counted here and never placed by a guess. Texts worded alike are one text. Each CP and K shows the 3 texts the most teams read, and how many more there are. A text naming a school of the caselist is withheld.

### Counterplan texts

Found by a CP-text label (`Text:`, `CP Text`) or as the first `should` analytic of a block placed under a CP: 15 in 8 files.

* Placed under a CP the team reads, and counted: 11.
* Not placed: 2 (1 under headings that place nothing, such as `1NC` or `OFF`; 1 under no heading).
* Placed under another kind of position, as an answer, or in a round on the other side: 2.
* Left out by the actor guard (no actor in the 12 words before `should`): 2.
* Withheld for naming a school: 1 text.
* Could not be read again as they were read: 1.

**States CP** (`states-cp`)

| Rank | Teams | Text |
|---|---|---|
| 1 | 4 | The fifty states should establish a sample single payer system. |
| 2 | 3 | Congress should give the fifty states sample block grants. |
| 3 | 2 | The fifty states should adopt a sample payment cap. |

And 1 more text, read by 1 team.

**Courts CP** (`courts-cp`)

| Rank | Teams | Text |
|---|---|---|
| 1 | 1 | The federal courts should strike down a sample mandate. |

### Kritik alternatives

Found by an alternative label (`Alt`, `The alternative is`): 9 in 8 files.

* Placed under a K the team reads, and counted: 5.
* Not placed: 3 (1 under headings that place nothing, such as `1NC` or `OFF`; 2 under no heading).
* Placed under another kind of position, as an answer, or in a round on the other side: 1.

**Capitalism K** (`cap-k`)

| Rank | Teams | Text |
|---|---|---|
| 1 | 3 | The alternative is to reject sample markets in care. |
| 2 | 2 | Our alternative is sample democratic planning. |
| 3 | 1 | refuse the sample market. |

### Roles of the ballot

Found by a role-of-the-ballot label (`Role of the ballot`, `ROB`, `The role of the ballot is`): 2 in 2 files.

* Placed under a K the team reads, and counted: 1.
* Not placed: 1 (1 under headings that place nothing, such as `1NC` or `OFF`; 0 under no heading).
* Placed under another kind of position, as an answer, or in a round on the other side: 0.

**Capitalism K** (`cap-k`)

| Rank | Teams | Text |
|---|---|---|
| 1 | 1 | The role of the ballot is to vote for the best sample method. |

## Overviews

Counted, never quoted: data-use policy 1.13 does not list overviews, and the coach keeps it so (2026-10-24). Per position, the teams whose files hold an overview label (`Overview`, `O/V`, `OV`) under it, on each side.

Found: 8 in 8 files.

* Placed under a position the team reads, and counted: 5.
* Not placed: 2 (1 under headings that place nothing, such as `1NC` or `OFF`; 1 under no heading).
* Placed under an answer to a position: 1.

| Position | Kind | Teams | Aff teams | Neg teams |
|---|---|---|---|---|
| Midterms DA (`election-da`) | da | 2 | 1 | 2 |
| Costs advantage (`costs-advantage`) | advantage | 1 | 1 | 0 |
| States CP (`states-cp`) | cp | 1 | 0 | 1 |

## New this week

Positions first read on this topic in this week's window, 2026-09-09 to 2026-09-15:

* Condo bad (`condo-bad`, theory): 1 team, 25.0% of the week's affirmative teams
* Hospital closures DA (`hospital-closures-da`, da): 1 team, 25.0% of the week's negative teams
* Provider strikes DA (`provider-strikes-da`, da): 1 team, 25.0% of the week's negative teams

## Rising

No position rose by at least 5 points of the week's teams on its side, with at least 3 teams reading it in one of the two weeks.

## Falling

Positions that fell by at least 5 points of the week's teams on its side, with at least 3 teams reading it in one of the two weeks:

* Spending DA (`spending-da`, da): 75.0% to 25.0% of the week's negative teams (-50.0 points), 3 teams to 1
* Costs advantage (`costs-advantage`, advantage): 100.0% to 75.0% of the week's affirmative teams (-25.0 points), 3 teams to 3

Held back by the team floor: 4 positions moved by 5 points or more, but fewer than 3 teams read them in either week, so they are STEADY. Every position's row is in `trends.csv`.

## Unclassified

What this report could not count:

* **Cards:** 10 of 56 (17.9%): 8 waiting in the review queue, 2 placed below the review threshold (0.6).
* **Aff rounds with no identified aff:** 3 of 7 (42.9%).
* **Neg rounds with no placed negative position:** 1 of 8 (12.5%).
* Counted as answers, not reads: 2 rounds that placed a card under a position of the other side, counted once per position.
* Not counted and not queued: 1 card under headings the coach ruled name no position.

How affirmative rounds were identified:

| Method | Aff rounds |
|---|---|
| A card in the round placed under the aff (`PLACED_CARD`) | 4 |
| Not identified | 3 |

The caselist's own round titles and cite entries are not read this season.

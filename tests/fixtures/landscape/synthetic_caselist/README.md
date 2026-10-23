# The synthetic two-snapshot caselist

The inputs `v1-e32-t03-landscape-report` is tested against: one invented Policy caselist,
`synthpolicy26`, written by `scripts/make_landscape_fixture.py`. Every school, team code,
tournament, tag and cite here is synthetic. Team codes are doubled letters (`XX`, `YY`, `ZZ`,
`QQ`, `VV`, `WW`, `JJ`, `KK`) at four fictional schools, so a scan of a report for them means
something (ac4).

What the report should say about these inputs is in `../golden/`, written by hand from the table
in the generator (working agreement 6), never by running the report.

## Files

| File | What it holds |
|---|---|
| `taxonomy.yaml` | 14 positions: 2 affs, 2 advantages, 4 DAs, 2 CPs, a K, a T and 2 theory positions read by the aff |
| `overrides.yaml` | One coach decision: the heading `extra` names no position |
| `disclosures.jsonl` | 18 E30 disclosure rows over three weekly snapshots, 2026-09-08, 2026-09-15 and 2026-09-22 |
| `cards.jsonl` | 44 cards of 15 sources, each with its exact fingerprint and E31 cluster |
| `classifications.jsonl` | The `v1-e32-t02` classification of each card |

Source digests read at a glance: `a1a1…` is an affirmative file, `b1b1…` a negative one. Cluster
`n` is `nn` repeated; copy `a` of cluster 2 is `0202…020a`.

## What each part exercises

The report is built through 2026-09-15, with 2026-09-08 as the previous snapshot.

* **Rounds.** 16 in range by 8 teams: 7 affirmative, 8 negative and 1 on no readable side (`b7`,
  whose filename gave no side, tournament or round).
* **One round listed twice.** `a1`'s first-tournament round is in both weekly windows, carried
  from one to the next. It is one round, first seen on 2026-09-08.
* **One file, two rounds.** `b1` was disclosed by two teams, so its cards count in two rounds.
* **A team with two rounds on one file.** `a1` was read by one team at both tournaments.
* **Out of range.** `b9` is disclosed on 2026-09-22, after the report's date; its cards (a
  `cap-k` read and a `spending-da` read) must change nothing.
* **ANSWERS are not reads.** `a1`'s answer to `spending-da`, `b1`'s answer to `costs-advantage`
  and `b8`'s answer to `pics-bad`, which nobody reads, so `pics-bad` has no row.
* **Below the threshold.** `a2`'s `public-option-aff` and `b3`'s `courts-cp`, placed by tag keyword
  at 0.5; `courts-cp` has no row. With 8 unplaced cards they make the 10 Unclassified cards.
* **The coach's decision.** `a5`'s third card is under a heading ruled to name no position: neither
  counted nor Unclassified.
* **Near-duplicates.** Cluster 2 has four exact fingerprints; one team (`a1`) reads two copies of
  it, and it counts once for that team.
* **New this week.** `condo-bad`, `hospital-closures-da` and `provider-strikes-da` are first seen
  on 2026-09-15.
* **Ties.** `hospital-closures-da` and `provider-strikes-da` have equal teams and rounds, so the
  position id orders them. `nhi-t`'s two clusters have one team each, so the cluster id orders them.
* **Unidentified affs.** 3 of the 7 affirmative rounds have no card placed under an aff.
* **A position read on no readable side.** `cap-k` is read in `b7`'s round, which counts in its
  rounds and teams but not in its neg split or its share of negative teams.

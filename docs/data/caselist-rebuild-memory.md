<!-- docs-index: The aggregate rebuild's main-process memory before and after it read cards source by source, and what its peak grows with -->
# Caselist rebuild memory

Measured for `v1-e40-t36` on 2026-11-01, with `v1-e40-t31`'s method, before and after the aggregate
rebuild stopped holding every card of a caselist at once. It belongs beside t31's record,
[caselist-parse-memory.md](caselist-parse-memory.md), and corrects one reading in it (below). Counts,
sizes, seconds and memory only: no school, team, file name, path, digest or card text
(`docs/policies/caselist-data-use.md`).

**What it found: the rebuild no longer holds the cards, but that was not what made it large.** Reading
the cards source by source took about 85 MiB off the peak at 250 `hspolicy26` sources and about 0.2 GB
at 500. The peak is set by the near-duplicate clusterer's index of the distinct full card bodies
(`CutIndex` in `debate_core/evidence/near_duplicates.py`), about 180 bytes per word of distinct body
text: 930 MiB of the 1.24 GB peak at 250 sources. It grows with the caselist's distinct full bodies,
not with every card, and it is outside this task's packages. The aggregates are byte for byte what
the rebuild wrote before.

## How it was measured

| | |
|---|---|
| Store | The Mac's dev store, `hspolicy26`, parser `2026.10.27-docx-7`: 3,869 sources, 126,681 cards, 144,841 occurrence rows, 29,866 distinct full-card fingerprints, 21,595 clusters. Its stored sources are 1,101,209,192 bytes. |
| Subsets | The first 250 and 500 per-source files by name, each with the caselist's manifests and suppression list, in a copy-on-write clone in the session's scratch folder: 281,249,032 and 535,753,890 bytes of per-source files, the same subsets as t31's |
| Runs | The cloud run's image `v1.1.0-dev.289` (arm64), `docker run --network none -m 7g`, with the code under test mounted read-only first on `PYTHONPATH`: the start commit's (`61d3191`, one list) or this branch's (source by source). Both through the CLI container's parse service, `plan()` then its rebuild, as t31's script did |
| Memory | `VmRSS` sampled twice a second, and `VmHWM` (the most the process was resident), from `/proc/self/status` |
| Mac | Load average 6 to 14, with 20 of 21.5 GB of swap in use by other work |

## Before and after

| Sources | Cards | Code | Seconds | Reading ended | Main-process peak (`VmHWM`) | Container peak (cgroup) | Aggregates |
|---|---|---|---|---|---|---|---|
| 250 | 8,583 | one list | 108.4 | about 290 MB | 1,333,706,752 | 1,611,104,256 | |
| 250 | 8,583 | source by source | 86.7 | about 200 MB | 1,239,453,696 | 1,517,043,712 | the same SHA-256 for `index.jsonl`, `failures.jsonl` and `occurrences.jsonl` |
| 500 | not reached | one list | over 112, stopped (t31) | | over 2.15 GB | | |
| 500 | not reached | source by source | over 115, stopped | about 263 MB | over 1.98 GB, 1.88 GB by 31 s | | |
| 3,869 | 126,681 | source by source | | | not measured: the operator follow-up in the session report | | |

The one-list peak at 250 is t31's figure to the megabyte, measured again here.

## Where the peak is

The source-by-source run over 250 sources, each step of the clusterer wrapped to print the resident
size and the high-water mark since the step before:

| Step | Ends at | Resident after it |
|---|---|---|
| Plan | 0.4 s | 83 MiB |
| Read 246 parsed sources, give each card to the placer | 13.3 s | 201 MiB |
| Build `CutIndex` over 5,470 distinct full bodies: 5,064,524 words, 32,182,048 characters | 22.4 s | 1,131 MiB |
| MinHash bands, candidate pairs and the joins of copies | 77.3 s | 1,181 MiB |
| The cut step | 77.9 s | 1,182 MiB |
| The clusterer returns | 78.2 s | 336 MiB |
| Link abbreviated cards, place, order and write the rows | 82.0 s | 338 MiB, with a high-water mark of 463 MiB while placing |

`CutIndex` keeps, for every distinct full body, its words as a list of strings and its 5-word shingles
as a set of strings: about 180 bytes per word, 30 bytes per character of body text.

**A correction to t31's record.** t31 read its 250-source run's 1.28 GB at 23 seconds as the end of
reading, and drew a straight line from it to "about 13 GB" for the whole store. Reading had ended by
then in both versions: the one-list run was at about 290 MB at 23 seconds and reached 1.28 GB at 38,
inside the clusterer. The cards held in one list cost about 85 MiB per 250 sources.

## What the peak grows with now

* **The distinct full bodies' text**, through `CutIndex`: about 30 bytes per character. Distinct bodies
  grow more slowly than sources, because later sources repeat earlier cards: 5,470 for the first 250
  sources, 29,866 for all 3,869.
* **Each card, a little**: its fingerprint, its source, paragraph range and completeness, and each of
  its rows' place in the table, a few hundred bytes. 126,681 cards and 144,841 rows are about 0.1 GB.
* **The largest source**, while it is read: one document at a time.

**Estimates, not measurements.** The whole `hspolicy26` store: 29,866 bodies at 250's 5,883 characters
each is about 176 million characters, about 5.1 GB of `CutIndex`, so a peak of about 5.5 GB, against
about 6.8 GB for the one list (its cards add about 1.3 GB). `hspolicy25`'s archive is 3,958,272,657
bytes, 3.6 times `hspolicy26`'s stored sources. If its distinct body text grew as fast as its bytes,
its `CutIndex` alone would be about 18 GB; it grows more slowly than that, by how much is not known
until a season is measured. The operator follow-up measures the whole `hspolicy26` store, which
replaces the first estimate.

## What follows from it

* A full season's rebuild in 32 GB depends on the clusterer's index, not on how the cards are read.
  Holding shingles as fixed-size hashes rather than strings, and not keeping each body's word list
  once its shingles are made, would shrink the largest term by several times. That is a change in
  `debate_core.evidence`, where clustering is decided, and needs its own byte-identity proof; the
  session report asks the PM about it.

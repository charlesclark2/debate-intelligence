<!-- docs-index: How much memory a caselist parse uses: each worker against its source's size, and the main process over the aggregate rebuild -->
# Caselist parse memory

Measured for `v1-e40-t31` on 2026-11-01, before any memory rule was written, after the
`hspolicy25` cloud import of 2026-10-31 was killed for memory (8 vCPU, 16 GB, 8 parse workers,
exit 137). The task asked two questions: how much memory one worker uses on the largest sources, and
how much the main process grows over a parse of a few thousand. Counts and sizes only: no school,
team, file name, path, digest or card text appears here (`docs/policies/caselist-data-use.md`).

**What it found: the main process is what grows.** A worker's peak depends on its source's main
document part and is at most about 0.63 GB on the Mac's whole corpus. The workers are stopped before
the aggregate rebuild starts. The rebuild then holds every card of the caselist in the main process
at once, about 0.8 GB more per 250 sources of `hspolicy26`, so the main process alone needs about
13 GB for the full `hspolicy26` store (a straight line through two measured subsets, not measured
whole). A whole season's backfile is larger. A memory ceiling on each worker would not have
prevented the kill of 2026-10-31. The task stopped here, as its PM context asked, and the PM's ruling
of 2026-11-01 dropped the ceiling: a rebuild that streams the cards is `v1-e40-t36`, and the weekly run
now records each stage's memory high-water marks
([caselist-cloud-run.md](../runbooks/caselist-cloud-run.md#the-runs-memory-figures)).

## Where it was measured

| | |
|---|---|
| Sources | The Mac's dev data directory: 15,327 raw sources, of which 13,528 are zip packages (`.docx`) |
| Stored size of a source | median 92,268 bytes, 90th percentile 597,951, 99th 3,473,704, largest 7,823,779 |
| Largest main document part (uncompressed XML) | 10,576,664 bytes |
| Linux runs | The cloud run's image, `v1.1.0-dev.289` (arm64, as the Fargate task), under Docker Desktop (kernel 6.6, cgroup v2), with no network, the sources mounted read-only |
| Mac runs | Apple silicon, 11 cores, 18 GiB; load average 7 to 20 and 21.9 of 23.5 GB of swap in use by other work while these ran |
| Store | Every run that writes did so in a copy-on-write clone of the data directory in a scratch folder, never the operator's store |

## One worker, one source

Each source was parsed in a fresh child process forked from a parent that had imported the parser,
so each figure is one parse's own. The figures are the child's `VmHWM` (the most it was resident)
and `VmPeak` (the most address space it held), from `/proc/self/status`, in MiB. A child that parses
nothing: `VmHWM` 39, `VmPeak` 66.

**The 300 largest by stored size** (1.49 to 7.82 MB stored): 299 parsed and 1 refused as
`MALFORMED_PACKAGE`, in 136.6 seconds together, the slowest 15.8 seconds.

| | Median | 90th percentile | 99th percentile | Largest |
|---|---|---|---|---|
| Resident (`VmHWM`), MiB | 69 | 104 | 457 | 604 |
| Address space (`VmPeak`), MiB | 91 | 127 | 485 | 632 |

28 of the 300 held more than 128 MiB of address space, 6 more than 256 and 1 more than 512. Stored
size says almost nothing about the peak (correlation −0.13), and nor does the package's whole
uncompressed size (0.08): the largest stored files are mostly images, which the parser never opens.

**The 12 largest by main document part** (4.3 to 10.6 MB of XML) peaked at 188 to 632 MiB of address
space. The source with the largest part in the corpus is also the one with the largest peak of all,
632 MiB resident 604, with 603 cards and a 17 MB result. That is the most one worker needs on the
Mac's corpus. The cloud's backfile seasons are not on the Mac and were not measured.

## A worker under an address-space limit

The source with the largest peak was parsed again under `RLIMIT_AS` set in the child before it
parsed, on Linux:

| Limit, MiB | Outcome |
|---|---|
| 120 | `MALFORMED_XML`: libxml2 failed to allocate, and lxml reported it as a syntax error |
| 200, 300, 450, 600 | `MemoryError` raised out of the parser, `VmPeak` at the limit |
| none | parsed, `VmPeak` 632 |

Parsing that main part alone under the limit gave lxml's `XMLSyntaxError` with code 2,
`ERR_NO_MEMORY`, at 90, 120 and 160 MiB, and parsed at 200 and above. A ceiling therefore needs the
parser to treat that code as a memory failure, or some sources over it are recorded as malformed
files.

On macOS `RLIMIT_AS` is the same limit as `RLIMIT_RSS` (both 5), `setrlimit` refuses to set it
(`ValueError: current limit exceeds maximum limit`), and an 800 MB allocation under an attempted
200 MB limit succeeds. Nothing is enforced.

## The main process

**The parse loop** (`caselist parse --reparse --caselist openev`, on the Mac clone, 4 workers,
`ps` once a second): 104 sources, 102 parsed, 8,081 cards, 91 seconds. The main process reached
826 MB while workers were running, the largest worker 760 MB and the workers together 1.72 GB. The
workers stopped at 31 seconds, and the main process then reached 1.37 GB in the rebuild, alone.

**The aggregate rebuild** (the parse service's rebuild over `hspolicy26`, parser
`2026.10.27-docx-7`, in the Linux image under a 7 GB cap, with no source left to parse). The rebuild
reads every parsed source's cards into one list, then fingerprints and clusters them. Run over the
first K of the store's per-source files:

| K sources | Bytes on disk | Cards | Main process, end of reading | Main process peak | Container peak (cgroup) | Seconds |
|---|---|---|---|---|---|---|
| 250 | 281,249,032 | 8,583 | 1.28 GB at 23 s | 1.33 GB | 1.60 GB | 67 |
| 500 | 535,753,890 | not reached | 2.06 GB at 38 s | over 2.15 GB, still placing at 112 s, stopped | not reached | over 112 |
| 3,869 (whole) | 4,267,638,401 | 126,681 | about 12.6 GB by a straight line through the two above; not measured | | | |

The whole store's rebuild was started on the Mac clone too, and was at 1.32 GB and still reading when
it was stopped at 98 seconds. It was not run to the end on either machine: Docker Desktop's VM has
8 GB, and the Mac was already deep in swap.

## What follows from it

* On 32 GB with 8 workers, the parse loop's workers need at most about 8 × 0.63 = 5 GB together,
  next to a main process near 1 GB. The rebuild needs the main process alone to hold the whole
  caselist's cards, and that grows with the caselist, about 0.8 GB per 250 `hspolicy26` sources. The
  task size that fits a parse is set by the largest caselist's rebuild, not by the workers.
* `hspolicy25` is a whole season: its archive is 3.96 GB, and its source and card counts are not
  known on the Mac. The import was killed at 71 minutes, and nothing logged which step it was in
  (`v1-e40-t32` now logs each step and its memory).
* A per-worker ceiling at the container's limit, less a main-process reserve, divided by the
  workers, would be about (32,768 − a reserve of several GB) / 8, far above any worker's 632 MiB.
  It would refuse nothing this corpus holds, and it would not have stopped the kill.

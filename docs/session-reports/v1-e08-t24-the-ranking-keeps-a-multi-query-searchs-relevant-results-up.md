# Session report: v1-e08-t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up

| | |
|---|---|
| Task | `v1-e08-t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up` — On a search of many queries, the ranking keeps the results the coach marks relevant above the providers' own order |
| Spec | [`plan_specs/v1/e08-research-workflows/t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up.yaml`](../../plan_specs/v1/e08-research-workflows/t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up` |
| Session status | COMPLETE: the Goal is `Succeeded` <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

This task is proposal first. **Where it stands:** the PM ruled on 2026-11-11 and the ruled change
is built ([The PM's ruling and the build](#the-pms-ruling-2026-11-11-and-the-build)). Recency is
unknown when every query's window is longer than 365 days, or any age, with no `--since`. The tests
were shown failing first, and nine mutants were caught. Both replayed scores are recorded in
`docs/data`. The operator's run of the built code reproduced the replay on both searches:
* t05 rises from 0.746 to 0.767, and t14 from 0.438 to 0.459, each a lower bound.
* t14 is still below its provider order (0.746). The PM files that follow-up, and t14's top-ten
  figures for it are under [Figures for the follow-up](#figures-for-the-follow-up-t14s-top-ten).

The Goal is `Succeeded`. **Look first at** Deviations 3: four CLI auto-cut tests outside the task's
packages changed with the ruled ranking.

The background from before the ruling follows.
* **The positions block reproduced both records:** t05 0.746 against 0.000, t14 0.438 against
  0.746.
* **On t14, recency's 90-day half-life lifted recent Crossref-only rows above relevant ones**,
  inside the five-year window the coach set for links. Loose matching of many queries did not
  separate relevant rows from the rest ([What the positions show](#what-the-positions-show)).
* **My first proposal fails the replay.** Recency as a position in that window lowered t05 to 0.605,
  which is forbidden, and t14 to 0.268. I withdraw it.
* **The revised recommendation:** recency does not count when every query's window is longer than
  a year. It replays at t05 0.767 and t14 0.459 ([Replayed figures](#replayed-figures-2026-11-11)).
* **It does not reach the Goal on t14**, whose provider order scores 0.746. The questions for the PM
  are under [Questions for the PM](#questions-for-the-pm).

The rest of this summary is from before the positions came back. The block prints, for every row of the two labelled Policy sheets
(v1-e08-t05's ac6 and v1-e08-t14's ac3), the row's ranked and provider positions, the query that
found it, every ranking feature and the coach's mark, and then nDCG@10 both ways. Only the operator
reads the sheets, so the block is his to run. No code has changed, and none will before the PM
rules (ac1). Once the output is back I will say which features moved t14's relevant results down,
propose a change, and give a replay block that scores the change on both searches. Then I stop for
the ruling.

**Look first at** the three facts under [Before the positions](#before-the-positions). Each of them
could explain the drop from 0.746 to 0.438 without the "many loose query matches" the spec suspects.

## Before the positions

What I read: the spec; the epic; v1-e08-t05's report (ac6 and its operator blocks); v1-e08-t14's
report (ac3 and the PM's record of 2026-11-09); v1-e08-t10's report (the joined request);
v1-e08-t16's spec; `federated_ranking.py`, `federated_ranking_features.py`,
`config/federated_ranking.yaml`; the fan-out, dedupe and search storage; and the search presenter's
JSON.

1. **The two searches may not have asked the same providers.** On 2026-11-05 v1-e07-t13 enabled
   `crossref`, `federal_register` and `govinfo` in `config/profiles/dev.toml`. Before that only
   `openalex` and `rss` were enabled. t05's search ran on 2026-11-02 and t14's on 2026-11-08, so
   t14's probably asked five providers where t05's asked two. Three features change with the
   provider set:
   * `provider_agreement` is the share of the other answering providers that found the result;
   * `source_type` scores a government source 1.0 and news 0.8;
   * `citations` now has Crossref's counts as well.

   The block prints each search's providers with their outcomes and counts.
2. **The build named in t14's ac3 record looks wrong.** The record says `v1.1.0-dev.342`, the same
   tag as t05's run of 2026-11-02. But t14 and t10 both merged on 2026-11-04, after that tag (t10
   is first in `v1.1.0-dev.361`). The block prints each saved search's taxonomy version, its query
   count and every query's template id, which shows which expansion actually ran.
3. **Since t10, OpenAlex credits almost every work to every query.** t10 found that on the saved
   ac6 results no title holds a whole templated query, so all 200 works fall back to "every query".
   "The query that found it" therefore has two readings, and the block prints both:
   * `first` is the query and provider of the call where the result first appears in fan-out
     order. That is the call its `provider_order` counts.
   * `attrib` is how many of the search's queries were credited with it. When there are three or
     fewer, the column names them.

How the ranking treats many queries today: `rank_merged_candidates` gets every query asked, and
BM25 scores each result against the **union of the distinct words of all of them**
(`query_terms`), scaled so the best result is 1. So a result that matches many different queries'
words loosely can outscore one that matches a single link query completely. That is the effect the
spec suspects, and four columns test it on each row:
* `terms`: union words present;
* `fullq`: queries whose every word is present;
* `bestq`: the single query the row scores best against;
* `bestbm25`: that query's BM25, scaled over the same results.

The block computes them from each result's title and snippet, with the ranking's own tokenizer.

**Why the block reads the store as well as the saved file.** The saved JSON never holds a snippet
(t05's rule), so BM25 cannot be recomputed from it. The store keeps every provider's whole answer,
snippets included, in `search_provider_statuses` (`~/.debate-research/dev/debate.sqlite3`). The block
rebuilds the search from that: `merge_candidates`, then `rank_merged_candidates` under the search's
own filters and creation time. It then checks that the rebuild reproduces the saved ranks and
features (the `replay with today's code and table` line) before any column is trusted. The later
replay block uses the same path. Since t05's search, `federated_dedupe.py` has changed once (the
Crossref and government adapters, 2026-11-02 evening), so t05's rebuild may differ slightly. The
line says by how much.

**The t05 sheet's file names are not certain.** The committed t05 report still shows the operator
command 4 from before the ruling: one `labels-policy-nhi.csv` with a `rank` column. The PM's ruling
on t05's Q4 changed it to an item-numbered sheet with a separate key, but the command in the report
was never updated. The block therefore reads either form:
* an item sheet joined to its `key-….csv`;
* a sheet with a `rank` column and no key.

If a file is missing, it lists the `search-`, `labels-` and `key-policy-nhi*` names on the Desktop
(file names only) and stops. Rerun it with the right names in place of the defaults.

**The first run (2026-11-11) found no t05 sheet.** The block stopped:
`STOP: missing ['labels-policy-nhi.csv']`. The Desktop holds `search-policy-nhi.json` and t14's
three files, but neither a t05 sheet nor a t05 key. The labels do not need the sheet, though. The
PM's ac6 record in t05's report fixes every one of them:
* the sheet was the top 10 by rank plus the top 10 by provider order of that saved search, 20 rows;
* 3 of the 20 were relevant: ranks 1, 9 and 10, at provider positions 117, 441 and 257;
* the other 17 were not.

So when t05's sheet is missing, the revised block rebuilds those rows from the saved search the way
t05's command 4 chose them, and marks ranks 1, 9 and 10 relevant. It first checks that those three
ranks sit at provider positions 117, 441 and 257 in the file, and stops if they do not, so it cannot
score a different search. t14's labels are still read from its sheet and key. If t05's filled sheet
turns up, putting it on the Desktop as `labels-policy-nhi.csv` makes the block read it instead.

**The second run (2026-11-11) found no t05 search in the dev store.** It stopped with `STOP: the
store does not hold search-policy-nhi.json's search or its provider record`. It had already passed
the record check, so ranks 1, 9 and 10 of the Desktop file sit at provider positions 117, 441 and
257: the file is ac6's search. But that file's search id is not in `~/.debate-research/dev/debate.sqlite3`.
Before guessing why, the operator runs a read-only check, [Where the two searches are
stored](#where-the-two-searches-are-stored). It looks in every SQLite file under `~/.debate-research`
for both searches' ids and lists every stored politics DA search, with only ids, dates, provider
sets, taxonomy versions and counts. If t05's provider record is in no store, its snippets are gone.
Then t05's positions can still come from the saved file alone, but its BM25 cannot be recomputed,
which limits which changes the replay can score on t05. I will put that to the PM rather than decide
it.

**What the store check found (2026-11-11).** `~/.debate-research/dev/debate.sqlite3` (modified
2026-11-08 00:16) holds **one search**: t14's `01M6WWSETYS7GRSQCPJH413CTG`, created
2026-11-08T06:16. It is `COMPLETE`, asked providers `openalex`, `crossref`, `rss`,
`federal_register` and `govinfo`, ran taxonomy 1.5.0 with topic `policy-2026-27-nhi` and 12 queries,
and stored 60 calls and 200 results. No other store under `~/.debate-research` has a searches table
(the four `tub-index` files are evidence-search indexes). So:
* **t05's search `01M6FK1EQGZXEX494EZYC29W4M` is in no store.** The dev store was replaced between
  2026-11-02 and 2026-11-08, so the providers' answers to t05's search, and their snippets, are gone.
  t10's live-check search is gone too.
* **Fact 1 holds:** t14's search asked five providers, and t05's file shows two.
* **Fact 2 is settled:** t14's search ran taxonomy 1.5.0 with 12 queries, so it carried t14's and
  t10's changes. The `v1.1.0-dev.342` in its ac3 record is a slip in the record. The search itself
  is the one the record describes.

**The positions block now reads each search as far as its record goes.**
* **t05, from the saved file alone.** That gives every position, every saved feature value and
  `first` (from the file's `provider_calls`, in fan-out order). It gives no stored attribution,
  title-and-snippet word columns or replay check. It says so on its `replay:` line.
* **t14, from the store as before.**
* **Both searches also get title-only word columns** (`title:` terms, fullq, bestq, best), scored
  over the 200 saved results, so the two can be compared on the same footing.

**How nDCG@10 is computed.** A row the coach marked relevant gains 1, and any other row gains 0. The
ideal ordering puts the sheet's relevant rows first. This reproduces t05's 0.746 from ranks 1, 9 and
10, and its 0.000 from provider positions 117, 441 and 257. "Provider order" can mean the raw
`provider_order` (a position among every provider record, duplicates included) or a place among
the saved results sorted by it. The block prints both, and the recorded figures show which one the
PM used.

## What the positions show

The positions block ran on 2026-11-11, and both searches reproduce their records:
* **t05:** 3 relevant of 20 rows, nDCG@10 **0.746** ranked against **0.000** in provider order.
* **t14:** 6 relevant of 19 rows, **0.438** against **0.746**.

t14's rebuild from the store puts all 200 saved results at their saved ranks. "Provider order" in
the records is a result's place among the saved results sorted by `provider_order`: t14's 0.746
comes from that reading, and the raw `provider_order` gives 0.624.

### The two searches

| | t05 (2026-11-02) | t14 (2026-11-08) |
|---|---|---|
| Taxonomy, queries | 1.2.0, 7 link templates | 1.5.0, the 7 plus 5 mechanism queries |
| Providers that answered | OpenAlex (700 results), rss (0, one feed unreadable) | OpenAlex 2,400, Crossref 2,400, Federal Register 961, GovInfo 2,075, rss 0 |
| How OpenAlex was asked | once per query, so provider order is query 1's 100 results, then query 2's, and so on | one joined request (t10), so every query's call holds OpenAlex's one relevance order |
| Distinct query words | 14 | 26 |
| Merged results | 200 saved (no stored record) | 2,758 |

### Where the relevant rows sat

* **t05.**
  * The ranking put the three relevant rows at 1, 9 and 10.
  * In provider order they were at 117, 441 and 257. Those are positions 17, 41 and 57 in the
    answers to queries 2, 5 and 3.
  * Provider order's top ten were query 1's first 16 OpenAlex results, and none of them is
    relevant. Provider order scored 0 because fan-out order puts query 1's whole answer first.
* **t14.**
  * Four of the six relevant rows are OpenAlex's own positions 1, 2, 4 and 12 in its joined answer
    (raw provider order 1, 2, 4, 12; places among the saved results 1, 2, 3, 7). The ranking put
    them at 2, 137, 39 and 25. The other two relevant rows are rank 3 (OpenAlex position 114) and
    rank 8 (a Crossref result).
  * The ranking's top ten had seven rows that are not relevant: ranks 1, 4, 5, 6, 7, 9 and 10. Six
    of the seven are **Crossref-only** results (ranks 1, 4, 5, 6, 7 and 9).
  * Ranks 4, 5 and 7 each came from one new mechanism query (`public-option-aff`,
    `medicare-for-all-aff` and `single-payer-aff`), which is the only query they are credited to.

### Which features moved the relevant results down on t14 and not on t05

Score = 0.45 bm25 + 0.15 recency + 0.10 source type + 0.10 peer review + 0.05 open access + 0.10
citations + 0.05 provider agreement.

1. **Recency.**
   * **On t14:** ranks 6, 7 and 9, all Crossref-only and not relevant, have recency 0.960, 0.968
     and 1.000. That contributes 0.144 to 0.150 each. Without it they would score 0.335, 0.334 and
     0.319, below relevant ranks 25 (0.423) and 39 (0.357). Rank 4 adds 0.056 for recency 0.370.
     No relevant row has recency above 0.314.
   * **On t05:** recency is about 0 on every labelled row except rank 4 (0.962, not relevant).
   * **Why recency acts like this:** the rank stage measures recency from the request's filters. A
     templated search's request carries no `since`, so recency falls back to the 90-day half-life:
     a paper two years old scores 0.004, and one published last week about 0.95. The providers,
     though, were asked for five years: the coach's window for a link, `recency_days: 1826`, is set
     on each expanded query. So the ranking rewards being weeks old, inside a window the coach set
     to accept any year of the last five.
2. **The providers' own order is not a feature.** Since t10, OpenAlex answers every query of a
   search in one relevance order. On t14 that order held four of the six relevant rows in its top 12
   (the reason provider order went from 0.000 to 0.746), and the ranking ignores it. On t05 the same
   order ran against relevance: OpenAlex's first positions for query 1 are all not relevant, and
   the relevant rows were 17th, 41st and 57th in their own queries' answers.
3. **Open access, once:** relevant rank 137 (OpenAlex's 2nd) is the one row the provider calls
   closed (0.000), which costs it 0.05 against its neighbours.

**Features the positions clear:**
* **"Credit for matching many queries loosely" (BM25 over every query's words).**
  * No labelled row in either search holds every word of any one query (`fullq` 0 everywhere,
    titles alone or titles with snippets).
  * In t14, the share of the 26 words a row holds does not separate the relevant rows (12, 9, 9, 9,
    10 and 7) from the top ten's rows that are not relevant (11, 9, 13, 9, 4, 5 and 12).
  * Nor does the best single-query BM25: 0.669, 0.891, 0.547, 0.755, 0.449 and 0.442 for the
    relevant rows; 0.900, 0.560, 0.912, 0.775, 0.646, 0.695 and 0.510 for those that are not.
  * So scoring each query apart would rank these rows much as the union does. It also could not be
    replayed on t05, whose snippets are gone.
* **Source type.** Every labelled row is scholarly except one row that is not relevant. The
  government providers returned 3,036 results, and none is among the labelled rows.
* **Provider agreement.** 0.25 (0.0125 of score) on four OpenAlex-and-Crossref rows in t14, two of
  them relevant. It is 0 in t05.
* **Citations.** The relevant rows in t14 have 0 to 0.497, and the Crossref-only rows that are not
  relevant have 0, except rank 1 (0.201). If anything, citations help.

## The proposal

**Recency is measured inside the window the search asked its providers for.** When a search's
request sets no `since` but its expanded queries were each asked with one (the taxonomy's window
for the need or the template), recency is the result's position in the widest of those windows:
0 at the window's start, 1 at its end, as recency already works for a typed `--since`. A search
with no window keeps the 90-day half-life, and so does one whose need accepts any age. Nothing
new goes into `config/federated_ranking.yaml`: the windows are the taxonomy's, already reviewed by
the coach. The weights and the other six features do not change.

Why this and not another change:
* It removes a contradiction rather than tuning a number: the ranking would stop scoring age
  against a window nobody chose.
* It touches only the feature the positions blame.
* It can be replayed exactly on both searches, because every saved result keeps its date and each
  expanded query keeps its `since` and `recency_days`.

**Measured alongside it, not proposed:**
* **No recency** (weight 0). It is the bound on what recency costs. It throws away the coach's
  "newer is better inside the window" for every need, uniqueness included.
* **The providers' own position as an eighth feature:** 1 / log2(1 + the result's position in
  the answer of the call that first returned it), at weights 0.02, 0.05, 0.10 and 0.20, alone and
  with window recency. It is the change t14's provider-order figure points at. t05's per-query
  order suggests it lowers t05, which the spec forbids, and the replay says at what weight.

Each is scored as nDCG@10 against the sheets, with the relevant count in the top ten. Rows the
coach never saw count as not relevant, so a change that brings unlabelled results into the top ten
scores lower than it may deserve. The replay prints how many it brings in.

**What the replay covers:**
* **t05:** over its 200 saved results, from their saved features, exactly. A result outside the
  saved 200 cannot be scored, because its record is gone.
* **t14:** over all 2,758 merged results, rebuilt from the store.
* **The provider position:** on both searches, the position in the call that first returned the
  result. A later call may hold it higher, and the replay does not look.

## Replayed figures (2026-11-11)

The operator's replay block ran with no provider call. Both searches rebuild today's order in full
(200 of 200 saved ranks in place) and use a five-year window (1,826 days, one start for every
query).
* **t05** is replayed over its 200 saved results.
* **t14** is replayed over all 2,758 merged results.

nDCG@10 against the coach's labels. "Top ten" is the relevant count in the top ten; "new" is how
many rows the coach never saw enter the top ten. Those count as not relevant, so a score with new
rows is a lower bound.

| Variant | t05 nDCG@10 | t05 top ten | t05 new | t14 nDCG@10 | t14 top ten | t14 new |
|---|---|---|---|---|---|---|
| Today | **0.746** | 3 | 0 | **0.438** | 3 | 0 |
| Window recency (the proposal) | 0.605 | 2 | 1 | 0.268 | 2 | 5 |
| No recency | **0.767** | 3 | 1 | **0.459** | 3 | 3 |
| Provider position 0.02 | 0.746 | 3 | 0 | 0.438 | 3 | 0 |
| Provider position 0.05 | 0.746 | 3 | 0 | 0.438 | 3 | 0 |
| Provider position 0.10 | 0.437 | 2 | 1 | 0.430 | 3 | 2 |
| Provider position 0.20 | 0.296 | 1 | 1 | 0.420 | 2 | 4 |
| Window recency + provider position 0.02 | 0.605 | 2 | 1 | 0.268 | 2 | 5 |
| Window recency + provider position 0.05 | 0.605 | 2 | 1 | 0.282 | 2 | 5 |
| Window recency + provider position 0.10 | 0.432 | 2 | 1 | 0.321 | 2 | 5 |
| Window recency + provider position 0.20 | 0.296 | 1 | 1 | 0.410 | 2 | 5 |
| Provider order (recorded baseline) | 0.000 | 0 | | 0.746 | 4 | |

Where the relevant rows land:
* t05 today: 1, 9 and 10. With no recency: 1, 7 and 9.
* t14 today: 2, 3, 8, 25, 39 and 137. With no recency: 2, 3, 5, 12, 52 and 76.

**What the figures say:**
1. **The proposal fails.**
   * Window recency lowers t05 (0.746 to 0.605, its rank-9 row falling to 31st), which the spec
     forbids. It lowers t14 further still (0.438 to 0.268).
   * Spreading recency over five years lifts many results the coach never saw: five of them enter
     t14's top ten. The relevant rows do not rise with them.
   * I withdraw it.
2. **No recency is the only variant that raises both searches:** t05 0.767, t14 0.459.
   * It is a lower bound on both, because rows the coach never saw enter both top tens (1 on t05,
     3 on t14).
   * On t14 it is still far below provider order's 0.746. No measured change gets t14's ranking
     above the providers' own order, which is this task's Goal.
3. **The providers' own position does not help.**
   * At 0.02 and 0.05 it changes neither top ten.
   * At 0.10 and above it lowers t05 (forbidden) and does not raise t14.
   * OpenAlex's joined order does not carry over into the score this way.

## Revised recommendation

**Recency does not count when the search's window is long.** The rule: when a search's request sets
no `since` and every one of its expanded queries was asked with a window longer than
`recency.counts_within_days` (365, in `config/federated_ranking.yaml`) or with no window at all,
recency is unknown for every result. It then contributes nothing and is not mentioned in the
explanation. "Unknown is not 0", as for every other feature.

What the rule touches, and what it leaves alone:
* **Affected:** link, internal link, answers (five years) and impact (any age), as asked through
  `--argument` and `--need`.
* **Unchanged:**
  * uniqueness (one year) and the politics DA's 30-day templates keep today's recency;
  * a search with its own `--since`, and `daily` (which sets `since` and `until`), keep window
    recency;
  * a typed search with no expansion keeps the 90-day half-life.

On these two searches it is exactly the replayed "no recency": both windows are 1,826 days. So:
* t05 rises from 0.746 to **0.767** and t14 from 0.438 to **0.459**;
* neither score is lowered.

**The rule does not reach the Goal on t14.** It removes the one feature the positions blame and
that a replay could test. The rest of t14's gap is outside what this round measured. The plain
fact: six of the seven rows in t14's top ten that the coach marked not relevant are Crossref-only
results. Rank 1 has BM25 1.000 from its abstract. Closing the gap needs its own proposal and replay
on t14's stored record, which is the one labelled record left. I propose that as a follow-up rather
than widening this task.

### Questions for the PM

````text
PM questions from v1-e08-t24 (multi-query ranking), session of 2026-11-11. Four. Details:
docs/session-reports/v1-e08-t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up.md,
"What the positions show", "Replayed figures" and "Revised recommendation".

Background. Positions reproduced both records (t05 0.746 vs 0.000; t14 0.438 vs 0.746). t05's
search is gone from the dev store (store replaced between 11-02 and 11-08), so t05 was scored from
its saved file and the PM's ac6 labels; t14 from its full stored record. On t14, recency's 90-day
half-life lifted three recent Crossref-only rows above relevant ones, inside the five-year window
the coach set for links; "many loose query matches" did not separate relevant rows from the rest.
My first proposal (recency as a position in that window) replayed at t05 0.605 (forbidden) and
t14 0.268, and is withdrawn.

1. Which change to build?
   (a) Recency is unknown when every expanded query's window is longer than 365 days or any age,
       and the request has no --since (new key recency.counts_within_days: 365). Replayed: t05
       0.746 -> 0.767, t14 0.438 -> 0.459 (both lower bounds: 1 and 3 unseen rows enter the top ten).
       Uniqueness, the politics 30-day templates, --since, daily and plain typed searches unchanged.
   (b) Recency weight 0 everywhere. Same two figures, but it also drops recency from uniqueness,
       --since and daily searches, which nobody measured.
   (c) Build nothing now; a second proposal round on t14's remaining gap first.
   Recommendation: (a). It is the only measured change that raises both searches, it is scoped to
   the windows where the coach said age does not matter, and it leaves every unmeasured search alone.

2. The Goal is not reached on t14 (0.459 vs provider order 0.746). How should the task close?
   (a) Build 1(a), record both replayed scores, and file a follow-up for t14's gap: six of the
       seven not-relevant rows in its top ten are Crossref-only (rank 1 has BM25 1.000 from its
       abstract), proposal first, replayed on t14's stored record.
   (b) Keep this task open for that second round.
   Recommendation: (a). The rule stands on its own figures, and the next question is a different
   feature (how a provider's abstracts score) with only one labelled record to test it on.

3. Unseen rows. The chosen change brings 3 rows the coach never saw into t14's top ten and 1 into
   t05's. Should he label those 4 blind before the figures are recorded?
   (a) Yes, by an operator block like t14's sheet (4 rows, item numbers only).
   (b) No; record the figures as lower bounds, and let v1-e08-t16's repeat search measure afresh.
   Recommendation: (b). Both figures already rise without them; the labels would only raise them.

4. Deviations, for acceptance: t05's labels taken from the PM's ac6 record (its sheet is not on the
   Mac; the block checks ranks 1, 9, 10 sit at provider positions 117, 441, 257); t05 replayed over
   its 200 saved results only; the provider-position feature measured from the first call that
   returned a result.
   Recommendation: accept all three. A follow-up I'd file: a labelled search's hand-off should keep
   its stored record (the dev store reset is what lost t05's).
````

## The PM's ruling (2026-11-11) and the build

The PM ruled:
1. **Build 1(a).** Recency counts as unknown when every expanded query's window is longer than
   `recency.counts_within_days`, or has no limit, and the request has no `--since`.
   * The key is new in `config/federated_ranking.yaml`, at 365, with its reason in a comment.
   * Uniqueness, the politics DA's 30-day templates, `--since`, `daily` and plain typed searches
     are unchanged, each pinned by a test.
   * Not 1(b), because that changes searches nobody measured.
2. **Close the task on the ruled change.**
   * Record both replayed scores in `docs/data` as lower bounds, with their unseen-row counts.
   * Set the Goal `Succeeded`.
   * Put t14's top-ten figures in this report for the follow-up the PM files (Crossref-only rows
     ranked on their abstracts' BM25, p2, proposal first).
3. **No extra labelling sheet.**
4. **All three deviations accepted.** The PM files the follow-up: a labelled search's hand-off keeps
   its stored record, labels and key together outside the dev store.

**What was built:**
* `recency_counts(expansion, filters, *, counts_within_days)` in
  `debate_core.application.federated_ranking`. It answers yes:
  * when the request has a `since`;
  * when the search was not expanded;
  * when any expanded query's `recency_days` is at most the limit.

  Otherwise it answers no. A query with no `recency_days` (any age) never counts as short.
* `rank_merged_candidates` takes an optional `expansion`, None for a typed search. When
  `recency_counts` says no, recency is None for every result: it contributes nothing and is left
  out of the explanation.
* `FederatedRankStage` hands it `state.expansion`.
* `RecencyParameters` has `counts_within_days` (an integer, at least 1). The table refuses a
  missing or zero value, as it does every other key.

**Tests on synthetic fixtures**, in `packages/debate_core/tests/application/test_federated_ranking.py`.
Each expected value is worked out by hand from the half-life (0.5 per 90 days) or the window
position.
* The rule:
  * a five-year window reorders two results and drops recency from their totals and explanations;
  * any age;
  * a long window mixed with any age;
  * 366 days;
  * the limit read from the table;
  * the stage hands over the expansion.
* The unchanged searches, one pin each:
  * uniqueness at exactly 365 days;
  * the politics 30-day templates beside a year and beside five years;
  * `--since` (50 of 140 days);
  * `daily`'s `since` and `until` (0.2);
  * a typed search with no expansion (0.5).
* A seven-case table of `recency_counts`, two refusals of the table, and the committed 365.

**Red, against a skeleton that refuses nothing** (`5d03bc1`). The skeleton has the key, the
parameter and the argument, and a `recency_counts` that always answers yes. The run was
`hard_stop.py 115 … pytest test_federated_ranking.py -n 0`, with two results:
* **8 failed, 141 passed, all 8 at their assertions.** The eight are the five rule tests, the
  three "unknown" cases of the table (five-years, any-age, just-over-and-any), and the stage test.
* **Passing at red, by design:** the five pins of unchanged searches and the four "counts" cases of
  the table (the skeleton keeps today's recency), plus the refusals and the committed-table test
  (the skeleton has the key).

A first red run also failed `test_score_recency_reads_the_half_life_from_the_table`, because that
existing test replaces the whole `recency` section and so lacked the new key. That was a crash, not
a catch. I gave the test the key and reran.

**Green** (`87259cf`): 160 passed over the ranking and article-matching test files.

**Mutants** (nine, `hard_stop.py 115` over a scratch script that edits the module, runs the ranking
test file and restores it). All nine were caught at assertions; none crashed. No Hypothesis
property is involved, so agreement 8's database rule does not apply.

| Mutant | Caught by |
|---|---|
| Threshold `<=` made `<` | 2 (uniqueness at 365; the table's a-year case) |
| Threshold hard-coded to 365 | 1 (the limit read from the table) |
| Threshold reversed (`>=`) | 7 |
| `--since` exemption removed | 4 (`--since`, `daily`, the table's two `since` cases) |
| `until` checked in place of `since` | 3 |
| Any age counted as short | 4 (any age, mixed, the table's two) |
| "Any query short" made "every query short" | 2 (the politics 30-day pins) |
| A typed search loses recency | 22 |
| The stage drops the expansion | 1 |

**One more test file changed:** the CLI's `search --auto-cut` budget tests (Deviations 3).

## The built ranking, run by the operator (2026-11-11)

The built code reproduces the replay on both searches:
* **t05**, over its 200 saved results: `recency_counts` says no, and nDCG@10 goes from 0.746 to
  **0.767**. The relevant rows move from 1, 9 and 10 to 1, 7 and 9, with 1 unseen row in the top
  ten.
* **t14**, over its stored record: today's ranking rebuilds 200 of 200, and nDCG@10 goes from 0.438
  to **0.459**. The relevant rows move from 2, 3, 8, 25, 39 and 137 to 2, 3, 5, 12, 52 and 76, with
  3 unseen rows in the top ten.

### Figures for the follow-up: t14's top ten

These are for the follow-up the PM files: Crossref-only rows ranked on their abstracts' BM25. They
are counts, positions and provider names only.
* **"BM25 raw"** is the ranking's own score over title and snippet.
* **"title" and "snippet"** are BM25 of that field alone, each scored over the same 2,758 results'
  titles or snippets.
* **"words"** is a field's length.
* **"query words"** is how many of the search's 26 distinct query words the field holds.

**Snippets across t14's 2,758 merged results:**

| Results | With a snippet | From Crossref | From the Federal Register | From OpenAlex | No snippet |
|---|---|---|---|---|---|
| 2,758 | 974 | 348 | 438 | 188 | 1,784 |

**Today's top ten** (the ranking that was labelled):

| Rank | Providers | Title from | Snippet from | BM25 (scaled) | BM25 raw | Title BM25 | Snippet BM25 | Title words | Snippet words | Query words in title | in snippet | Recency | Score | Coach |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | crossref | crossref | crossref | 1.000 | 31.658 | 16.854 | 34.570 | 7 | 189 | 4 | 11 | 0.000 | 0.620 | n |
| 2 | openalex+crossref | crossref | openalex | 0.800 | 25.318 | 11.444 | 27.542 | 13 | 180 | 5 | 12 | 0.000 | 0.532 | y |
| 3 | openalex | openalex | openalex | 0.757 | 23.967 | 10.368 | 22.512 | 12 | 178 | 3 | 8 | 0.001 | 0.524 | y |
| 4 | crossref | crossref | crossref | 0.645 | 20.405 | 11.055 | 19.824 | 16 | 149 | 5 | 9 | 0.370 | 0.495 | n |
| 5 | crossref | crossref | crossref | 0.848 | 26.846 | 10.422 | 27.731 | 9 | 180 | 3 | 13 | 0.091 | 0.495 | n |
| 6 | crossref | crossref | crossref | 0.522 | 16.531 | 4.333 | 18.687 | 10 | 188 | 2 | 9 | 0.960 | 0.479 | n |
| 7 | crossref | crossref | none | 0.408 | 12.931 | 7.658 | 0.000 | 23 | 0 | 4 | 0 | 0.968 | 0.479 | n |
| 8 | crossref | crossref | crossref | 0.600 | 19.001 | 7.053 | 19.710 | 11 | 171 | 3 | 9 | 0.000 | 0.470 | y |
| 9 | crossref | crossref | none | 0.375 | 11.873 | 9.667 | 0.000 | 14 | 0 | 5 | 0 | 1.000 | 0.469 | n |
| 10 | openalex | openalex | openalex | 0.676 | 21.411 | 3.017 | 23.004 | 19 | 154 | 1 | 12 | 0.000 | 0.464 | n |

**The built top ten** (recency unknown):

| Rank | Providers | Title from | Snippet from | BM25 (scaled) | BM25 raw | Title BM25 | Snippet BM25 | Title words | Snippet words | Query words in title | in snippet | Score | Coach |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | crossref | crossref | crossref | 1.000 | 31.658 | 16.854 | 34.570 | 7 | 189 | 4 | 11 | 0.620 | n |
| 2 | openalex+crossref | crossref | openalex | 0.800 | 25.318 | 11.444 | 27.542 | 13 | 180 | 5 | 12 | 0.532 | y |
| 3 | openalex | openalex | openalex | 0.757 | 23.967 | 10.368 | 22.512 | 12 | 178 | 3 | 8 | 0.524 | y |
| 4 | crossref | crossref | crossref | 0.848 | 26.846 | 10.422 | 27.731 | 9 | 180 | 3 | 13 | 0.482 | n |
| 5 | crossref | crossref | crossref | 0.600 | 19.001 | 7.053 | 19.710 | 11 | 171 | 3 | 9 | 0.470 | y |
| 6 | openalex | openalex | openalex | 0.676 | 21.411 | 3.017 | 23.004 | 19 | 154 | 1 | 12 | 0.464 | n |
| 7 | openalex | openalex | openalex | 0.608 | 19.247 | 4.901 | 21.933 | 7 | 187 | 2 | 10 | 0.452 | unseen |
| 8 | crossref | crossref | crossref | 0.587 | 18.588 | 7.214 | 21.874 | 12 | 289 | 4 | 10 | 0.446 | unseen |
| 9 | openalex | openalex | openalex | 0.587 | 18.596 | 5.128 | 20.598 | 4 | 182 | 1 | 6 | 0.443 | unseen |
| 10 | crossref | crossref | crossref | 0.645 | 20.405 | 11.055 | 19.824 | 16 | 149 | 5 | 9 | 0.440 | n |

**What the figures show,** stated as facts without a proposal:
* **The snippet carries the score.** Every row of either top ten that has a snippet has a snippet
  BM25 above its title BM25, and a snippet that holds more of the query words than its title (6 to
  13 against 1 to 5). A snippet runs 149 to 289 words against a title's 4 to 23.
* **Most results have no snippet.** Only 974 of the 2,758 results have one. The 1,784 without one
  are scored on a title of a few words. Only 188 of OpenAlex's results carry a snippet, against 348
  of Crossref's.
* **The recency rule removed exactly the snippetless rows.** The two rows with no snippet in
  today's top ten, ranks 7 and 9, both Crossref-only, are the two that recency lifted (0.968 and
  1.000). The rule removed both from the top ten.
* **Crossref-only rows that are not relevant stay at the top.** Ranks 1 and 4 of the built top ten
  are Crossref-only, not relevant, and score highest on BM25 (1.000 and 0.848) on a snippet that
  Crossref supplied.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `the-ranking-keeps-a-multi-query-searchs`: Multi-query ranking | Done | Red `5d03bc1`, rule `87259cf`, `docs/data` record `ef71faa`, auto-cut tests `e5c7b11`; nine mutants caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the operator's positions block has run and the PM has ruled on the proposal before any code | PASS | Positions block ran 2026-11-11 and reproduced both records ([What the positions show](#what-the-positions-show)). Replay the same day ([Replayed figures](#replayed-figures-2026-11-11)). The PM's ruling of 2026-11-11 ([above](#the-pms-ruling-2026-11-11-and-the-build)). The first code commit, `5d03bc1`, comes after it. |
| ac2: the ruled change holds by tests on fixtures shown failing first, and both searches' replayed nDCG@10 are recorded beside today's (operator) | PASS | Tests shown failing first (8 of 149 at red, at assertions), green 160, nine mutants caught. [`docs/data/federated-ranking-labelled-searches.md`](../data/federated-ranking-labelled-searches.md) records the operator's replay: t05 0.746 → 0.767 (lower bound, 1 unseen row in the top ten) and t14 0.438 → 0.459 (lower bound, 3), beside provider order. The operator's run of the built code, 2026-11-11, gives the same figures ([The built ranking](#the-built-ranking-run-by-the-operator-2026-11-11)). |
| Node: `uv run pytest packages/debate_core/tests -k ranking` | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k ranking -n 4` → `175 passed in 41.48s` |

### Closing checks

* **The affected set** (`uv run scripts/affected_tests.py`) is **283 test files**, well over two
  minutes: a 47-file set once ran 269 s. Under agreement 10 it is left to the pull request's `ci`.
  Within the limit I ran:
  * the always-run list (`tests/architecture`, `tests/specs` and the CLI's three wiring files):
    `379 passed in 23.44s`;
  * the 18 affected files that reach the ranking, search, daily, digest, auto-cut, stamp,
    installation or config, plus the search, cut and daily smoke checks: `820 passed in 29.33s`.
    Before the auto-cut fix this run gave `4 failed, 802 passed`: the four budget tests of
    Deviations 3.
  * `packages/debate_core/tests/application`, the changed module's whole test directory. It hit the
    115-second limit twice, at 98 % and 99 % (load 12 on the second). I have no verdict for it, and
    it is `ci`'s.
* **Repo-wide checks**, all clean:
  * `uv run --frozen ruff format --check .`: 2054 files formatted;
  * `ruff check .`: all checks passed;
  * `pyright`: 0 errors;
  * `lint-imports`: 20 contracts kept;
  * `check_thin_handlers.py`: 74 handlers within 25 statements;
  * `uv run scripts/validate_specs.py`: OK;
  * `docs_index.py --check-descriptions`: 70 documents;
  * `check_links.py`: 3756 links;
  * `check_command_blocks.py --base origin/dev`: 700 blocks.

## Files changed

* `config/federated_ranking.yaml`: `recency.counts_within_days: 365`, with its reason in a
  comment.
* `packages/debate_core/src/debate_core/application/federated_ranking.py`: `recency_counts`, the
  `expansion` argument to `rank_merged_candidates`, the stage handing it over, the new parameter
  and the module docstring. `federated_ranking_features.py`: the recency docstring.
* `packages/debate_core/tests/application/test_federated_ranking.py`: the rule's tests, the pins
  of the unchanged searches, the table cases.
* `packages/debate_cli/tests/test_search_command.py`: the four auto-cut budget tests (Deviations 3).
* `docs/data/federated-ranking-labelled-searches.md`: new. The labelled searches and their scores,
  counts only.
* `docs/session-reports/v1-e08-t24-…md`: this report.

## Deviations from the spec

1. **t05's labels come from the PM's ac6 record, not from the coach's sheet.** The spec asks for
   positions from the labelled sheets, and t05's filled sheet is not on the operator's Desktop. The
   record gives the same labels: 3 relevant of 20 rows, at ranks 1, 9 and 10 (provider positions
   117, 441 and 257), and the rest not relevant. The block checks those positions against the saved
   search before it uses them. If the sheet is found, the block reads it instead.
2. **t05's positions come from its saved file alone.** Its provider record is in no store (the dev
   store was replaced between 2026-11-02 and 2026-11-08), so its BM25 cannot be recomputed from
   titles and snippets. Its saved feature values are exact. Its word-match columns use titles only.
3. **Four CLI tests outside the task's packages changed with the ruled behaviour.**
   `packages/debate_cli/tests` is not in `constraints.packages`.
   * **What changed:** the CLI's fixture search (`health insurance --argument politics-da --need
     link`) asks five years, so the rule drops its recency. Its government grant notice, whose
     citation the fixture does not verify, now ranks above a newer magazine story. `--auto-cut 3`
     therefore cuts four results for three verified cards, where it cut three.
   * **What broke:** v1-e08-t17's four budget tests pinned "three cuts, two calls each". On the
     skeleton's ranking all 23 auto-cut tests pass, so the rule is the cause.
   * **The fix:** their expected calls are worked out again by hand from the new order:
     * eight calls with no limit;
     * under `--expand-llm`, the fourth cut's markup refused, with two cards verified;
     * the verified entries costing calls 1 and 2, 3 and 4, and 7 and 8;
     * a cent short, seven calls spent and the eighth refused.

     The budget rule itself is unchanged.
   * **For the PM:** the PM may want the packages list to name the CLI tests.

## Decisions and assumptions

* **The positions block runs the worktree's own code, read-only.** It uses
  `.venv/bin/python -I -B` from the task worktree, so it imports this branch's ranking (which is dev
  at the task's start) and writes no bytecode. It opens the store with SQLite's `immutable=1`, which
  creates no `-wal` or `-shm` sidecar. It stops if the store has an unmerged write-ahead log, which
  `immutable` would not see, and if a `debate-research` command is running.
* **Nothing it prints can carry a title.** No title, URL, snippet, publisher or query word is
  printed. A query is named by its template id. The sheet's URLs are compared with the saved
  results' URLs only to count disagreements. If anything fails, the block prints the exception's
  type and line, never its message, because a pydantic error quotes the value it refused, and that
  value can be a title.
* **Tested on invented data only.** I built a synthetic store and Desktop in the session scratchpad
  with invented words: two searches, of 4 and 12 queries, saved through the real
  `SqliteSearchRepository` and the presenter's `search_payload`, plus item sheets with key files.
  The block ran under zsh with `HOME` pointed at that folder.
  * It reproduced the synthetic ranking (30 of 30 ranks and features).
  * Its nDCG matched my hand calculation: 0.643 ranked from relevant ranks 3, 5, 7, 8, 9 and 10;
    0.091 in provider order from provider positions 11, 9, 22, 31, 12 and 45.
  * It read a sheet with a `rank` column and no key the same way.
  * It stopped with a named reason on each of these: a missing key, a missing saved search, a
    non-empty `-wal` file, a set `DEBATE_` variable.
  * On a stored record I corrupted on purpose, it printed `FAILED: ValidationError at block line
    143 in report` and no data.
  * Nothing under the synthetic `HOME` changed (file sizes and modification times compared), and
    the worktree stayed clean.
  * It took 0.4 s.
  * With no t05 sheet, on a synthetic search patched so ranks 1, 9 and 10 sit at provider positions
    117, 441 and 257, it marked those three relevant and printed nDCG@10 0.746 ranked against 0.000.
    Unpatched, it stopped with `the saved t05 search is not the one recorded: rank 1 is not at
    provider position 117`.

  The block holds no `#` and no `!` (zsh history expansion), and only ASCII.

## Operator follow-ups

None open. Every operator command this task needed ran on 2026-11-11, and each one's output is
recorded in the sections above. The four commands are kept word for word under [Operator commands
that ran](#operator-commands-that-ran-2026-11-11), outside this section. `scripts/task pr` copies
this section into the pull request body, and with them inside it the body was 67,439 characters,
over GitHub's limit of 65,536.

## Operator commands that ran (2026-11-11)

They are listed in the order they were written: the store check, the positions block (its third
version), the built-ranking block and the replay.

### Where the two searches are stored

**Operator command: find both searches' stored records** (seconds; no network, no model, writes
nothing)

Where: your Mac, any terminal. It needs no worktree code and opens each store with `immutable=1`.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else python3 -I -B - "$HOME/.debate-research" "$HOME/Desktop/search-policy-nhi.json" "$HOME/Desktop/search-policy-nhi-mechanisms.json" <<'EOF'
import json
import sqlite3
import sys
import traceback
from datetime import datetime
from pathlib import Path


def saved_id(path):
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    if "results" not in document:
        document = document.get("data") or (document.get("error") or {}).get("details") or {}
    return document.get("search_id")


def main():
    root = Path(sys.argv[1])
    wanted = {}
    for label, name in (("t05", sys.argv[2]), ("t14", sys.argv[3])):
        search_id = saved_id(Path(name))
        wanted[search_id] = label
        print(f"{label}: {Path(name).name} names search {search_id}")
    stores = sorted(p for p in root.rglob("*") if p.is_file() and p.name.endswith((".sqlite3", ".sqlite", ".db")))
    print(f"stores under {root.name}: {len(stores)}")
    for store in stores:
        stat = store.stat()
        wal = store.with_name(store.name + "-wal")
        print(
            f"--- {store.relative_to(root)}: {stat.st_size} bytes, modified {datetime.fromtimestamp(stat.st_mtime):%Y-%m-%d %H:%M},"
            f" wal {wal.stat().st_size if wal.is_file() else 'none'}"
        )
        connection = sqlite3.connect(store.as_uri() + "?mode=ro&immutable=1", uri=True)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if "searches" not in tables:
                print("    no searches table")
                continue
            rows = connection.execute("SELECT search_id, created_at, document FROM searches ORDER BY created_at").fetchall()
            print(f"    searches {len(rows)}, first {rows[0][1][:10] if rows else '-'}, last {rows[-1][1][:10] if rows else '-'}")
            for search_id, created_at, document in rows:
                body = json.loads(document)
                expansion = body.get("expansion") or {}
                statuses = connection.execute(
                    "SELECT count(*) FROM search_provider_statuses WHERE search_id = ?", (search_id,)
                ).fetchone()[0] if "search_provider_statuses" in tables else "no table"
                results = connection.execute(
                    "SELECT count(*) FROM search_results WHERE search_id = ?", (search_id,)
                ).fetchone()[0]
                if search_id in wanted or expansion.get("argument") == "politics-da":
                    print(
                        f"    {wanted.get(search_id, '   ')} {search_id} {created_at[:16]} {body.get('status')}"
                        f" providers {body.get('provider_set')} taxonomy {expansion.get('taxonomy_version')}"
                        f" topic {expansion.get('topic_id')} queries {len(expansion.get('queries') or [])}"
                        f" calls {statuses} results {results}"
                    )
        finally:
            connection.close()


try:
    main()
except Exception as failure:
    frames = traceback.extract_tb(failure.__traceback__)
    own = [frame for frame in frames if frame.filename == "<stdin>"]
    where = own[-1] if own else frames[-1]
    print("FAILED:", type(failure).__name__, "at block line", where.lineno, "in", where.name)
    sys.exit(2)
EOF
fi
```

Success looks like:
* two lines naming each Desktop file's search id;
* the number of stores found;
* for each store, its size, its modification time, its search count, and a line per politics DA
  search. A line for t05's or t14's search starts with `t05` or `t14`.

Paste back everything it prints. It holds no query text, title or URL.

### Positions of the labelled rows

**Operator command: positions of the labelled rows** (seconds; no network, no model, writes nothing)

Where: your Mac, any terminal. The block changes into the task worktree itself. It reads:
* the two saved searches on your Desktop, `search-policy-nhi.json` (t05) and
  `search-policy-nhi-mechanisms.json` (t14);
* t14's filled sheet and key (`labels-policy-nhi-mechanisms.csv`, `key-policy-nhi-mechanisms.csv`),
  and t05's sheet only if one is on the Desktop. Otherwise t05's labels come from the PM's record,
  as described above;
* the dev store `~/.debate-research/dev/debate.sqlite3`.

If any of those Desktop files has another name, the block stops and lists what it found. Change the
name in the command and paste it again.
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e08-t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -f 'debate-research ' > /dev/null; then echo "STOP: a debate-research command is running; let it finish first"; else .venv/bin/python -I -B - "$HOME/.debate-research/dev" "$HOME/Desktop/search-policy-nhi.json" "$HOME/Desktop/labels-policy-nhi.csv" "$HOME/Desktop/key-policy-nhi.csv" "$HOME/Desktop/search-policy-nhi-mechanisms.json" "$HOME/Desktop/labels-policy-nhi-mechanisms.csv" "$HOME/Desktop/key-policy-nhi-mechanisms.csv" <<'EOF'
import csv
import json
import math
import sqlite3
import sys
import traceback
from pathlib import Path

RECORDED = {
    "t05": {"relevant": 3, "rows": 20, "ranked": 0.746, "provider": 0.000, "marked": {1: 117, 9: 441, 10: 257}},
    "t14": {"relevant": 6, "rows": 19, "ranked": 0.438, "provider": 0.746},
}
FEATURES = ("bm25", "recency", "source_type", "peer_reviewed", "open_access", "citations", "provider_agreement")
SHORT = ("bm25", "rec", "src", "peer", "oa", "cite", "agree")


class Stop(Exception):
    pass


def num(value, places=3):
    return "-" if value is None else f"{value:.{places}f}"


def ndcg_at_10(positions, relevant_count):
    if relevant_count == 0:
        return None
    dcg = sum(1 / math.log2(p + 1) for p in positions if p is not None and p <= 10)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(relevant_count, 10)))
    return dcg / ideal


def saved_search(path):
    document = json.loads(path.read_text(encoding="utf-8"))
    if "results" not in document:
        document = document.get("data") or (document.get("error") or {}).get("details") or {}
    if not document.get("results") or not document.get("search_id"):
        raise Stop(f"{path.name} holds no saved search with results")
    return document


def header_of(reader):
    return [(name or "").strip().lstrip(chr(0xFEFF)).strip().lower() for name in reader.fieldnames or []]


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        names = header_of(reader)
        reader.fieldnames = names
        return names, list(reader)


def relevance(text):
    word = (text or "").strip().lower()
    if word in ("y", "yes", "1", "true", "x"):
        return True
    if word in ("n", "no", "0", "false"):
        return False
    return None


def labelled_rows(labels_path, key_path, results_by_rank):
    names, rows = read_rows(labels_path)
    if "relevant" not in names:
        raise Stop(f"{labels_path.name} has no relevant column")
    if "rank" in names:
        keyed = {index: (int(row["rank"]), None) for index, row in enumerate(rows)}
        key_note = "rank column in the sheet"
    elif "item" in names:
        if key_path is None or not key_path.is_file():
            raise Stop(f"{labels_path.name} numbers its rows by item and its key file is missing")
        key_names, key_rows = read_rows(key_path)
        if not {"item", "rank", "provider_order"} <= set(key_names):
            raise Stop(f"{key_path.name} lacks item, rank or provider_order")
        by_item = {row["item"].strip(): (int(row["rank"]), int(row["provider_order"])) for row in key_rows}
        keyed = {}
        for index, row in enumerate(rows):
            item = (row.get("item") or "").strip()
            if item not in by_item:
                raise Stop(f"{labels_path.name}: an item the key does not hold (row {index + 1})")
            keyed[index] = by_item[item]
        key_note = f"items joined to {key_path.name}"
    else:
        raise Stop(f"{labels_path.name} has neither an item nor a rank column")
    out = []
    url_mismatch = 0
    order_mismatch = 0
    for index, row in enumerate(rows):
        rank, key_order = keyed[index]
        result = results_by_rank.get(rank)
        if result is None:
            raise Stop(f"{labels_path.name}: a row names rank {rank}, which the saved search lacks")
        sheet_url = (row.get("url") or "").strip()
        if sheet_url and sheet_url not in (result.get("url"), result.get("canonical_url")):
            url_mismatch += 1
        if key_order is not None and not key_order == result.get("provider_order"):
            order_mismatch += 1
        out.append((rank, relevance(row.get("relevant"))))
    return out, key_note, url_mismatch, order_mismatch


def recorded_rows(name, results):
    marked = RECORDED[name].get("marked")
    if not marked:
        raise Stop(f"{name}'s sheet is missing and no record gives its labels")
    by_rank = {result["rank"]: result for result in results}
    for rank, order in marked.items():
        if by_rank.get(rank, {}).get("provider_order") is None or not by_rank[rank]["provider_order"] == order:
            raise Stop(f"the saved {name} search is not the one recorded: rank {rank} is not at provider position {order}")
    top = {x["rank"] for x in sorted(results, key=lambda x: x["rank"])[:10]} | {
        x["rank"] for x in sorted(results, key=lambda x: x["provider_order"])[:10]
    }
    rows = [(rank, rank in marked) for rank in sorted(top)]
    note = "no sheet: rows rebuilt from the saved search, labels from the PM's record (ranks " + ", ".join(
        f"{rank} at provider position {order}" for rank, order in marked.items()
    ) + " relevant, provider positions checked)"
    return rows, note, 0, 0


def candidate_key(candidate):
    return (candidate.provider, candidate.provider_record_id, str(candidate.url), candidate.title)


def per_query_scaled(documents, query_texts, config, bm25_scores, query_terms):
    out = []
    for text in query_texts:
        terms = query_terms([text])
        raw = bm25_scores(documents, terms, k1=config.bm25.k1, b=config.bm25.b)
        best = max(raw, default=0.0)
        out.append((set(terms), [value / best if best > 0 else 0.0 for value in raw]))
    return out


def lexical(tokens, union, per_query, position):
    terms_hit = sum(1 for t in union if t in tokens)
    full = sum(1 for terms, _ in per_query if terms and terms <= tokens)
    best_index = max(range(len(per_query)), key=lambda i: per_query[i][1][position])
    return f"{terms_hit:>3}/{len(union):<3} {full:>3}  q{best_index + 1:<4} {per_query[best_index][1][position]:6.3f}"


def report(name, data_dir, search_path, labels_path, key_path):
    from debate_core.application.federated_dedupe import merge_candidates
    from debate_core.application.federated_ranking import (
        FEDERATED_RANKING_CONFIG_PATH,
        load_federated_ranking_config,
        rank_merged_candidates,
    )
    from debate_core.application.federated_ranking_features import (
        bm25_scores,
        document_tokens,
        query_terms,
        ranking_tokens,
    )
    from debate_core.domain import Search
    from debate_core.domain.discovery import ProviderOutcome, ProviderStatus

    saved = saved_search(search_path)
    results = saved["results"]
    results_by_rank = {result["rank"]: result for result in results}
    if labels_path.is_file():
        rows, key_note, url_mismatch, order_mismatch = labelled_rows(labels_path, key_path, results_by_rank)
    else:
        rows, key_note, url_mismatch, order_mismatch = recorded_rows(name, results)
    config = load_federated_ranking_config(FEDERATED_RANKING_CONFIG_PATH)

    database = data_dir / "debate.sqlite3"
    wal = data_dir / "debate.sqlite3-wal"
    if not database.is_file():
        raise Stop(f"no store at {data_dir.name}/debate.sqlite3")
    if wal.is_file() and wal.stat().st_size > 0:
        raise Stop("the store has an unmerged write-ahead log; close every debate-research and rerun")
    connection = sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        search_row = connection.execute(
            "SELECT document FROM searches WHERE search_id = ?", (saved["search_id"],)
        ).fetchone()
        status_rows = connection.execute(
            "SELECT document FROM search_provider_statuses WHERE search_id = ? ORDER BY position",
            (saved["search_id"],),
        ).fetchall()
    finally:
        connection.close()
    stored = search_row is not None and bool(status_rows)

    calls = saved.get("provider_calls") or []
    query_texts = list(dict.fromkeys(call["query"] for call in calls))
    expansion = saved.get("expansion") or {}
    expanded = expansion.get("queries") or []
    labels_of = {}
    for index, text in enumerate(query_texts):
        match = next((q for q in expanded if q.get("query") == text), None)
        if match is None:
            labels_of[index] = "typed query" if text == saved.get("query") else "not in the expansion"
        else:
            labels_of[index] = match.get("template_id") or f"model suggestion {expanded.index(match) + 1}"
    first_call = []
    for call in calls:
        first_call.extend([(query_texts.index(call["query"]), call["provider"])] * int(call.get("results") or 0))

    union = query_terms(query_texts)
    title_docs = [ranking_tokens(result.get("title") or "") for result in results]
    title_per_query = per_query_scaled(title_docs, query_texts, config, bm25_scores, query_terms)
    title_position = {result["rank"]: i for i, result in enumerate(results)}

    def url_key(item):
        return item.get("canonical_url") or item.get("url")

    store_columns = {}
    replay_line = "replay: not possible, the store holds no record of this search"
    created = "not in the store"
    counts_line = f"saved results {len(results)}, provider calls {len(calls)}, distinct query terms {len(union)}"
    if stored:
        search = Search.model_validate_json(search_row[0])
        statuses = [ProviderStatus.model_validate_json(row[0]) for row in status_rows]
        created = f"{search.created_at:%Y-%m-%d}"
        stored_texts = list(dict.fromkeys(status.query.query for status in statuses))
        if not stored_texts == query_texts:
            raise Stop(f"{search_path.name}'s provider calls and the store's disagree on the queries")
        candidates = []
        calls_of = {}
        for status in statuses:
            if status.response is None:
                continue
            query_index = query_texts.index(status.query.query)
            for candidate in status.response.results:
                candidates.append(candidate)
                calls_of.setdefault(candidate_key(candidate), set()).add(query_index)
        merged = merge_candidates(candidates)
        answered = len({status.provider for status in statuses if status.outcome is ProviderOutcome.OK})
        ranked = rank_merged_candidates(
            merged,
            queries=query_texts,
            filters=search.filters,
            answered_providers=answered,
            now=search.created_at,
            config=config,
        )
        replay_by_key = {}
        for entry in ranked:
            replay_by_key.setdefault(entry.candidate.canonical_url or entry.candidate.url, entry)
        same_rank = 0
        same_features = 0
        for result in results:
            entry = replay_by_key.get(url_key(result))
            if entry is None:
                continue
            same_rank += entry.rank == result["rank"]
            same_features += all(
                (entry.features[f] is None and result["features"].get(f) is None)
                or (
                    entry.features[f] is not None
                    and result["features"].get(f) is not None
                    and abs(entry.features[f] - result["features"][f]) < 1e-9
                )
                for f in FEATURES
            )
        replay_line = (
            f"replay with today's code and table: same rank for {same_rank} of {len(results)} saved results,"
            f" same features for {same_features}"
        )
        counts_line = (
            f"stored calls {len(statuses)}, candidates {len(candidates)}, merged {len(merged)}, saved results"
            f" {len(results)}, answered providers {answered}, distinct query terms {len(union)}"
        )
        kept = [
            c for c in merged if not search.filters.source_types or c.source_type in search.filters.source_types
        ]
        documents = [document_tokens(c) for c in kept]
        per_query = per_query_scaled(documents, query_texts, config, bm25_scores, query_terms)
        kept_by_key = {}
        for position, c in enumerate(kept):
            kept_by_key.setdefault(c.canonical_url or c.url, (position, c))
        for result in results:
            found = kept_by_key.get(url_key(result))
            if found is None:
                continue
            position, candidate = found
            members = [calls_of.get(candidate_key(m), set()) for m in candidate.members]
            hit = sorted(set().union(*members)) if members else []
            attrib = f"{len(hit)}/{len(query_texts)}"
            if 0 < len(hit) <= 3:
                attrib += ":" + ",".join(str(i + 1) for i in hit)
            store_columns[result["rank"]] = (attrib, lexical(set(documents[position]), union, per_query, position))

    dense = {
        result["rank"]: position
        for position, result in enumerate(
            sorted(results, key=lambda r: (r["provider_order"] is None, r["provider_order"] or 0)), start=1
        )
    }

    print(f"=== {name}: {search_path.name} ===")
    print(f"search {saved['search_id']} created {created} status {saved.get('status')}")
    if expansion:
        print(
            f"expansion taxonomy {expansion.get('taxonomy_version')} argument {expansion.get('argument')}"
            f" need {expansion.get('need')} topic {expansion.get('topic_id')} queries {len(expanded)}"
        )
    for index, _ in enumerate(query_texts):
        print(f"  query {index + 1}: {labels_of[index]} ({len(title_per_query[index][0])} terms)")
    print(
        "providers",
        [(p.get("provider"), p.get("outcome"), p.get("queries"), p.get("results")) for p in saved.get("providers") or []],
    )
    print(counts_line)
    print(replay_line)
    print(
        f"sheet: {len(rows)} rows ({key_note}); urls differing from the saved result {url_mismatch};"
        f" provider_order differing from the key {order_mismatch}"
    )
    print(
        "rank porder pdense provider          first        "
        + " ".join(f"{s:>6}" for s in SHORT)
        + "  type        score | title: terms  fullq bestq  best | stored: attrib  terms  fullq bestq  best | rel"
    )
    for rank, relevant in sorted(rows):
        result = results_by_rank[rank]
        porder = result.get("provider_order")
        first = "-"
        if porder is not None and 0 < porder <= len(first_call):
            q, provider = first_call[porder - 1]
            first = f"q{q + 1}/{provider}"
        features = result.get("features") or {}
        position = title_position[rank]
        title_part = lexical(set(title_docs[position]), union, title_per_query, position)
        attrib, stored_part = store_columns.get(rank, ("-", "-"))
        print(
            f"{rank:>4} {porder if porder is not None else '-':>6} {dense.get(rank, '-'):>6} "
            f"{'+'.join(result.get('providers') or []):<17} {first:<12} "
            + " ".join(f"{num(features.get(f)):>6}" for f in FEATURES)
            + f"  {result.get('source_type', '-'):<10} {result.get('score', 0):6.3f} | {title_part} |"
            + f" {attrib:<8} {stored_part} | {'y' if relevant else ('n' if relevant is False else '?')}"
        )
    relevant_ranks = [rank for rank, relevant in rows if relevant]
    unanswered = sum(1 for _, relevant in rows if relevant is None)
    count = len(relevant_ranks)
    ranked_score = ndcg_at_10(relevant_ranks, count)
    raw_score = ndcg_at_10([results_by_rank[r].get("provider_order") for r in relevant_ranks], count)
    dense_score = ndcg_at_10([dense.get(r) for r in relevant_ranks], count)
    top_ranked = sum(1 for r in relevant_ranks if r <= 10)
    top_raw = sum(1 for r in relevant_ranks if (results_by_rank[r].get("provider_order") or 99999) <= 10)
    top_dense = sum(1 for r in relevant_ranks if (dense.get(r) or 99999) <= 10)
    print(f"relevant {count} of {len(rows)} rows, unanswered {unanswered}")
    print(
        f"nDCG@10 ranked {num(ranked_score)} (top ten {top_ranked}); provider order by provider_order"
        f" {num(raw_score)} (top ten {top_raw}); provider order by place among saved results"
        f" {num(dense_score)} (top ten {top_dense})"
    )
    record = RECORDED[name]
    agrees = (
        count == record["relevant"]
        and len(rows) == record["rows"]
        and ranked_score is not None
        and abs(ranked_score - record["ranked"]) < 0.0005
        and any(s is not None and abs(s - record["provider"]) < 0.0005 for s in (raw_score, dense_score))
    )
    print(
        f"recorded {record['relevant']} of {record['rows']}, {record['ranked']:.3f} ranked against"
        f" {record['provider']:.3f}: {'REPRODUCED' if agrees else 'DIFFERS'}"
    )
    print()


def main():
    data_dir = Path(sys.argv[1]).expanduser()
    names = ("t05", "t14")
    paths = sys.argv[2:]
    if not len(paths) == 6:
        raise Stop("expected three paths per search")
    desktop = Path(paths[0]).parent
    missing = [Path(p).name for i, p in enumerate(paths) if not Path(p).is_file() and (i % 3 == 0 or i == 4)]
    if missing:
        found = sorted(
            entry.name
            for entry in desktop.iterdir()
            if entry.name.startswith(("search-policy-nhi", "labels-policy-nhi", "key-policy-nhi"))
        )
        raise Stop(f"missing {missing}; on that folder: {found}")
    for index, name in enumerate(names):
        search_path, labels_path, key_path = (Path(p) for p in paths[index * 3 : index * 3 + 3])
        report(name, data_dir, search_path, labels_path, key_path if key_path.is_file() else None)


try:
    main()
except Stop as stop:
    print("STOP:", stop)
    sys.exit(1)
except Exception as failure:
    frames = traceback.extract_tb(failure.__traceback__)
    own = [frame for frame in frames if frame.filename == "<stdin>"]
    where = own[-1] if own else frames[-1]
    print("FAILED:", type(failure).__name__, "at block line", where.lineno, "in", where.name)
    sys.exit(2)
EOF
fi
```

**What success looks like:** two sections, `=== t05: …` and `=== t14: …`. In each section:
* `replay with today's code and table: same rank for N of N saved results, same features for N`,
  ideally with N the same throughout;
* `sheet: 20 rows (no sheet: rows rebuilt …)` for t05, and `sheet: 19 rows (items joined to …)` for
  t14 with `urls differing from the saved result 0`;
* t05's `replay: not possible, the store holds no record of this search`, which is expected. t14's
  `replay with today's code and table` line should show the same N throughout;
* then one line per labelled row, the relevant count, the nDCG@10 line, and `REPRODUCED` on the last
  line.

A `DIFFERS` line, a replay short of N, or a `STOP:` or `FAILED:` line is still worth pasting back
exactly as printed. **Paste back everything the block prints.** It holds positions, counts, feature
values, template ids and search ids, and no title, URL, snippet or publisher.

### The built ranking on both searches, and t14's top-ten figures

**Operator command: the built ranking** (seconds; no network, no model, no provider call, writes
nothing)

Where: your Mac, any terminal; the block changes into the task worktree itself, whose code now
carries the ruled change. It reads the same files as the earlier blocks. It does three things:
* **Checks the built code against the replay.** It ranks t05's 200 saved results with the built
  `recency_counts`, and t14's stored record with the built `rank_merged_candidates`. It prints
  nDCG@10 today and built for each.
* **Counts snippets.** It prints how many of t14's results have a snippet, by the provider that
  supplied it.
* **Prints, for each row of t14's top ten today and built:**
  * its rank and providers;
  * which provider its title and its snippet came from;
  * its BM25, scaled and raw;
  * BM25 of its title alone and of its snippet alone, each over the same 2,758 results' titles or
    snippets;
  * its title and snippet word counts;
  * how many of the 26 query words each field holds;
  * its recency and score;
  * the coach's mark, or `unseen`.

It prints no title, URL, snippet or publisher.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e08-t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -f 'debate-research ' > /dev/null; then echo "STOP: a debate-research command is running; let it finish first"; else .venv/bin/python -I -B - "$HOME/.debate-research/dev" "$HOME/Desktop/search-policy-nhi.json" "$HOME/Desktop/labels-policy-nhi.csv" "$HOME/Desktop/key-policy-nhi.csv" "$HOME/Desktop/search-policy-nhi-mechanisms.json" "$HOME/Desktop/labels-policy-nhi-mechanisms.csv" "$HOME/Desktop/key-policy-nhi-mechanisms.csv" <<'EOF'
import csv
import json
import math
import sqlite3
import sys
import traceback
from pathlib import Path

RECORDED = {
    "t05": {"relevant": 3, "rows": 20, "ranked": 0.746, "provider": 0.000, "marked": {1: 117, 9: 441, 10: 257}},
    "t14": {"relevant": 6, "rows": 19, "ranked": 0.438, "provider": 0.746},
}
FEATURES = ("bm25", "recency", "source_type", "peer_reviewed", "open_access", "citations", "provider_agreement")
SHORT = ("bm25", "rec", "src", "peer", "oa", "cite", "agree")


class Stop(Exception):
    pass


def num(value, places=3):
    return "-" if value is None else f"{value:.{places}f}"


def ndcg_at_10(positions, relevant_count):
    if relevant_count == 0:
        return None
    dcg = sum(1 / math.log2(p + 1) for p in positions if p is not None and p <= 10)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(relevant_count, 10)))
    return dcg / ideal


def saved_search(path):
    document = json.loads(path.read_text(encoding="utf-8"))
    if "results" not in document:
        document = document.get("data") or (document.get("error") or {}).get("details") or {}
    if not document.get("results") or not document.get("search_id"):
        raise Stop(f"{path.name} holds no saved search with results")
    return document


def header_of(reader):
    return [(name or "").strip().lstrip(chr(0xFEFF)).strip().lower() for name in reader.fieldnames or []]


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        names = header_of(reader)
        reader.fieldnames = names
        return names, list(reader)


def relevance(text):
    word = (text or "").strip().lower()
    if word in ("y", "yes", "1", "true", "x"):
        return True
    if word in ("n", "no", "0", "false"):
        return False
    return None


def labelled_rows(labels_path, key_path, results_by_rank):
    names, rows = read_rows(labels_path)
    if "relevant" not in names:
        raise Stop(f"{labels_path.name} has no relevant column")
    if "rank" in names:
        keyed = {index: (int(row["rank"]), None) for index, row in enumerate(rows)}
        key_note = "rank column in the sheet"
    elif "item" in names:
        if key_path is None or not key_path.is_file():
            raise Stop(f"{labels_path.name} numbers its rows by item and its key file is missing")
        key_names, key_rows = read_rows(key_path)
        if not {"item", "rank", "provider_order"} <= set(key_names):
            raise Stop(f"{key_path.name} lacks item, rank or provider_order")
        by_item = {row["item"].strip(): (int(row["rank"]), int(row["provider_order"])) for row in key_rows}
        keyed = {}
        for index, row in enumerate(rows):
            item = (row.get("item") or "").strip()
            if item not in by_item:
                raise Stop(f"{labels_path.name}: an item the key does not hold (row {index + 1})")
            keyed[index] = by_item[item]
        key_note = f"items joined to {key_path.name}"
    else:
        raise Stop(f"{labels_path.name} has neither an item nor a rank column")
    out = []
    url_mismatch = 0
    order_mismatch = 0
    for index, row in enumerate(rows):
        rank, key_order = keyed[index]
        result = results_by_rank.get(rank)
        if result is None:
            raise Stop(f"{labels_path.name}: a row names rank {rank}, which the saved search lacks")
        sheet_url = (row.get("url") or "").strip()
        if sheet_url and sheet_url not in (result.get("url"), result.get("canonical_url")):
            url_mismatch += 1
        if key_order is not None and not key_order == result.get("provider_order"):
            order_mismatch += 1
        out.append((rank, relevance(row.get("relevant"))))
    return out, key_note, url_mismatch, order_mismatch


def recorded_rows(name, results):
    marked = RECORDED[name].get("marked")
    if not marked:
        raise Stop(f"{name}'s sheet is missing and no record gives its labels")
    by_rank = {result["rank"]: result for result in results}
    for rank, order in marked.items():
        if by_rank.get(rank, {}).get("provider_order") is None or not by_rank[rank]["provider_order"] == order:
            raise Stop(f"the saved {name} search is not the one recorded: rank {rank} is not at provider position {order}")
    top = {x["rank"] for x in sorted(results, key=lambda x: x["rank"])[:10]} | {
        x["rank"] for x in sorted(results, key=lambda x: x["provider_order"])[:10]
    }
    rows = [(rank, rank in marked) for rank in sorted(top)]
    note = "no sheet: rows rebuilt from the saved search, labels from the PM's record (ranks " + ", ".join(
        f"{rank} at provider position {order}" for rank, order in marked.items()
    ) + " relevant, provider positions checked)"
    return rows, note, 0, 0


def candidate_key(candidate):
    return (candidate.provider, candidate.provider_record_id, str(candidate.url), candidate.title)


def load_store(data_dir, search_id):
    database = data_dir / "debate.sqlite3"
    wal = data_dir / "debate.sqlite3-wal"
    if not database.is_file():
        raise Stop(f"no store at {data_dir.name}/debate.sqlite3")
    if wal.is_file() and wal.stat().st_size > 0:
        raise Stop("the store has an unmerged write-ahead log; close every debate-research and rerun")
    connection = sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        search_row = connection.execute("SELECT document FROM searches WHERE search_id = ?", (search_id,)).fetchone()
        status_rows = connection.execute(
            "SELECT document FROM search_provider_statuses WHERE search_id = ? ORDER BY position", (search_id,)
        ).fetchall()
    finally:
        connection.close()
    return search_row, status_rows


def labels_for(name, saved, labels_path, key_path):
    results = saved["results"]
    results_by_rank = {result["rank"]: result for result in results}
    if labels_path.is_file():
        rows, _, _, _ = labelled_rows(labels_path, key_path, results_by_rank)
    else:
        rows, _, _, _ = recorded_rows(name, results)
    labels = {}
    for rank, relevant in rows:
        result = results_by_rank[rank]
        labels[result.get("canonical_url") or result.get("url")] = relevant
    return labels, sum(1 for _, relevant in rows if relevant)


def score_line(label, keys, labels, relevant_count):
    positions = [i for i, key in enumerate(keys, start=1) if labels.get(key)]
    unseen = sum(1 for key in keys[:10] if key not in labels)
    print(
        f"  {label}: nDCG@10 {num(ndcg_at_10(positions, relevant_count))}, relevant in top ten"
        f" {sum(1 for p in positions if p <= 10)}, unseen rows in top ten {unseen}, relevant at"
        f" {','.join(str(p) for p in positions)}"
    )


def built_t05(saved, labels, relevant_count):
    from debate_core.application.federated_ranking import (
        FEDERATED_RANKING_CONFIG_PATH,
        load_federated_ranking_config,
        recency_counts,
    )
    from debate_core.domain import SearchFilters
    from datetime import datetime

    from debate_core.domain.search import SearchExpansion

    config = load_federated_ranking_config(FEDERATED_RANKING_CONFIG_PATH)
    expansion = SearchExpansion.model_validate(saved["expansion"])
    filters = SearchFilters.model_validate(saved["filters"])
    counts = recency_counts(expansion, filters, counts_within_days=config.recency.counts_within_days)
    weights = {f: config.weights.weight_of(f) for f in FEATURES}

    def total(result):
        features = result.get("features") or {}
        return sum(
            weights[f] * features[f]
            for f in FEATURES
            if features.get(f) is not None and (counts or not f == "recency")
        )

    def key_of(result):
        published = result.get("published_at")
        stamp = datetime.fromisoformat(published).timestamp() if published else 0.0
        return (-total(result), published is None, -stamp, result.get("canonical_url") or result.get("url") or "")

    order = sorted(saved["results"], key=key_of)
    print("=== t05: built ranking over its 200 saved results (no stored record) ===")
    print(f"recency counts under the committed table: {counts}")
    score_line("today (saved ranks)", [r.get("canonical_url") or r.get("url") for r in sorted(saved["results"], key=lambda r: r["rank"])], labels, relevant_count)
    score_line("built", [r.get("canonical_url") or r.get("url") for r in order], labels, relevant_count)
    print()


def built_t14(saved, labels, relevant_count, search_row, status_rows):
    from debate_core.application.federated_dedupe import merge_candidates
    from debate_core.application.federated_ranking import (
        FEDERATED_RANKING_CONFIG_PATH,
        load_federated_ranking_config,
        rank_merged_candidates,
        recency_counts,
    )
    from debate_core.application.federated_ranking_features import bm25_scores, query_terms, ranking_tokens
    from debate_core.domain import Search
    from debate_core.domain.discovery import ProviderOutcome, ProviderStatus

    config = load_federated_ranking_config(FEDERATED_RANKING_CONFIG_PATH)
    search = Search.model_validate_json(search_row[0])
    statuses = [ProviderStatus.model_validate_json(row[0]) for row in status_rows]
    candidates = [c for s in statuses if s.response is not None for c in s.response.results]
    merged = merge_candidates(candidates)
    answered = len({s.provider for s in statuses if s.outcome is ProviderOutcome.OK})
    query_texts = list(dict.fromkeys(s.query.query for s in statuses))
    common = dict(queries=query_texts, filters=search.filters, answered_providers=answered, now=search.created_at, config=config)
    today = rank_merged_candidates(merged, **common)
    built = rank_merged_candidates(merged, expansion=search.expansion, **common)
    counts = recency_counts(search.expansion, search.filters, counts_within_days=config.recency.counts_within_days)

    kept = [c for c in merged if not search.filters.source_types or c.source_type in search.filters.source_types]
    union = query_terms(query_texts)
    titles = [ranking_tokens(c.title) for c in kept]
    snippets = [ranking_tokens(c.snippet or "") for c in kept]
    title_bm25 = bm25_scores(titles, union, k1=config.bm25.k1, b=config.bm25.b)
    snippet_bm25 = bm25_scores(snippets, union, k1=config.bm25.k1, b=config.bm25.b)
    index_of = {id(c): i for i, c in enumerate(kept)}

    def key(entry):
        return entry.candidate.canonical_url or entry.candidate.url

    print("=== t14: built ranking over its stored record ===")
    print(f"recency counts under the committed table: {counts}; merged {len(merged)}; distinct query words {len(union)}")
    saved_keys = [r.get("canonical_url") or r.get("url") for r in sorted(saved["results"], key=lambda r: r["rank"])]
    print(f"today's ranking rebuilt: {sum(1 for a, b in zip(today, saved_keys) if key(a) == b)} of {len(saved_keys)} saved ranks in place")
    score_line("today", [key(e) for e in today], labels, relevant_count)
    score_line("built", [key(e) for e in built], labels, relevant_count)
    have_snippet = sum(1 for s in snippets if s)
    print(f"results with a snippet: {have_snippet} of {len(kept)}; by provider:")
    by_provider = {}
    for c in kept:
        source = c.field_sources.get("snippet") if c.snippet else None
        by_provider.setdefault(source or "none", 0)
        by_provider[source or "none"] += 1
    print("   ", sorted(by_provider.items()))
    for label, ranking in (("today", today), ("built", built)):
        print(f"--- {label}'s top ten ---")
        print(
            "rank providers              title-from  snippet-from  bm25   raw     title-bm25 snippet-bm25"
            "  title-words snippet-words  terms-in-title terms-in-snippet  recency  score  label"
        )
        for entry in ranking[:10]:
            c = entry.candidate
            i = index_of[id(c)]
            title_terms = sum(1 for t in union if t in set(titles[i]))
            snippet_terms = sum(1 for t in union if t in set(snippets[i]))
            mark = labels.get(key(entry), "unseen")
            mark = "y" if mark is True else ("n" if mark is False else mark)
            print(
                f"{entry.rank:>4} {'+'.join(c.providers):<22} {c.field_sources.get('title', '-'):<11}"
                f" {(c.field_sources.get('snippet') if c.snippet else '-') or '-':<12}"
                f" {num(entry.features['bm25'])} {entry.lexical_score or 0:7.3f} {title_bm25[i]:10.3f} {snippet_bm25[i]:12.3f}"
                f"  {len(titles[i]):>11} {len(snippets[i]):>13}  {title_terms:>14} {snippet_terms:>16}"
                f"  {num(entry.features['recency']):>7} {entry.total_score:6.3f}  {mark}"
            )
    print()


def main():
    data_dir = Path(sys.argv[1]).expanduser()
    paths = sys.argv[2:]
    if not len(paths) == 6:
        raise Stop("expected three paths per search")
    missing = [Path(p).name for i, p in enumerate(paths) if not Path(p).is_file() and (i % 3 == 0 or i == 4)]
    if missing:
        raise Stop(f"missing {missing}")
    t05_paths = [Path(p) for p in paths[0:3]]
    t14_paths = [Path(p) for p in paths[3:6]]
    t05 = saved_search(t05_paths[0])
    labels, count = labels_for("t05", t05, t05_paths[1], t05_paths[2] if t05_paths[2].is_file() else None)
    built_t05(t05, labels, count)
    t14 = saved_search(t14_paths[0])
    labels, count = labels_for("t14", t14, t14_paths[1], t14_paths[2] if t14_paths[2].is_file() else None)
    search_row, status_rows = load_store(data_dir, t14["search_id"])
    if search_row is None or not status_rows:
        raise Stop("the store does not hold t14's search")
    built_t14(t14, labels, count, search_row, status_rows)


try:
    main()
except Stop as stop:
    print("STOP:", stop)
    sys.exit(1)
except Exception as failure:
    frames = traceback.extract_tb(failure.__traceback__)
    own = [frame for frame in frames if frame.filename == "<stdin>"]
    where = own[-1] if own else frames[-1]
    print("FAILED:", type(failure).__name__, "at block line", where.lineno, "in", where.name)
    sys.exit(2)
EOF
fi
```

Success looks like:
* **t05:** `recency counts under the committed table: False`, then `today` at nDCG@10 0.746 and
  `built` at **0.767** (relevant at 1, 7 and 9).
* **t14:**
  * the same `False`;
  * `today's ranking rebuilt: 200 of 200`;
  * `today` at 0.438 and `built` at **0.459** (relevant at 2, 3, 5, 12, 52 and 76; 3 unseen rows in
    the top ten);
  * the snippet counts;
  * two ten-row tables.

Paste back everything it prints, `STOP:` or `FAILED:` included.

### Replay of the proposal and the alternatives

**Operator command: the replay** (seconds; no network, no model, no provider call, writes nothing)

Where: your Mac, any terminal; the block changes into the task worktree itself. It reads the same
files as the positions block. For each search it prints:
* what it replays over;
* the window its queries were asked under;
* whether today's order rebuilds;
* one line per variant: nDCG@10, the relevant count in the top ten, how many unlabelled rows reach
  the top ten, and where the relevant rows land. A variant that scores below today says
  `lower than today`.

It prints no title, URL, snippet or publisher.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e08-t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -f 'debate-research ' > /dev/null; then echo "STOP: a debate-research command is running; let it finish first"; else .venv/bin/python -I -B - "$HOME/.debate-research/dev" "$HOME/Desktop/search-policy-nhi.json" "$HOME/Desktop/labels-policy-nhi.csv" "$HOME/Desktop/key-policy-nhi.csv" "$HOME/Desktop/search-policy-nhi-mechanisms.json" "$HOME/Desktop/labels-policy-nhi-mechanisms.csv" "$HOME/Desktop/key-policy-nhi-mechanisms.csv" <<'EOF'
import csv
import json
import math
import sqlite3
import sys
import traceback
from pathlib import Path

RECORDED = {
    "t05": {"relevant": 3, "rows": 20, "ranked": 0.746, "provider": 0.000, "marked": {1: 117, 9: 441, 10: 257}},
    "t14": {"relevant": 6, "rows": 19, "ranked": 0.438, "provider": 0.746},
}
FEATURES = ("bm25", "recency", "source_type", "peer_reviewed", "open_access", "citations", "provider_agreement")
SHORT = ("bm25", "rec", "src", "peer", "oa", "cite", "agree")


class Stop(Exception):
    pass


def num(value, places=3):
    return "-" if value is None else f"{value:.{places}f}"


def ndcg_at_10(positions, relevant_count):
    if relevant_count == 0:
        return None
    dcg = sum(1 / math.log2(p + 1) for p in positions if p is not None and p <= 10)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(relevant_count, 10)))
    return dcg / ideal


def saved_search(path):
    document = json.loads(path.read_text(encoding="utf-8"))
    if "results" not in document:
        document = document.get("data") or (document.get("error") or {}).get("details") or {}
    if not document.get("results") or not document.get("search_id"):
        raise Stop(f"{path.name} holds no saved search with results")
    return document


def header_of(reader):
    return [(name or "").strip().lstrip(chr(0xFEFF)).strip().lower() for name in reader.fieldnames or []]


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        names = header_of(reader)
        reader.fieldnames = names
        return names, list(reader)


def relevance(text):
    word = (text or "").strip().lower()
    if word in ("y", "yes", "1", "true", "x"):
        return True
    if word in ("n", "no", "0", "false"):
        return False
    return None


def labelled_rows(labels_path, key_path, results_by_rank):
    names, rows = read_rows(labels_path)
    if "relevant" not in names:
        raise Stop(f"{labels_path.name} has no relevant column")
    if "rank" in names:
        keyed = {index: (int(row["rank"]), None) for index, row in enumerate(rows)}
        key_note = "rank column in the sheet"
    elif "item" in names:
        if key_path is None or not key_path.is_file():
            raise Stop(f"{labels_path.name} numbers its rows by item and its key file is missing")
        key_names, key_rows = read_rows(key_path)
        if not {"item", "rank", "provider_order"} <= set(key_names):
            raise Stop(f"{key_path.name} lacks item, rank or provider_order")
        by_item = {row["item"].strip(): (int(row["rank"]), int(row["provider_order"])) for row in key_rows}
        keyed = {}
        for index, row in enumerate(rows):
            item = (row.get("item") or "").strip()
            if item not in by_item:
                raise Stop(f"{labels_path.name}: an item the key does not hold (row {index + 1})")
            keyed[index] = by_item[item]
        key_note = f"items joined to {key_path.name}"
    else:
        raise Stop(f"{labels_path.name} has neither an item nor a rank column")
    out = []
    url_mismatch = 0
    order_mismatch = 0
    for index, row in enumerate(rows):
        rank, key_order = keyed[index]
        result = results_by_rank.get(rank)
        if result is None:
            raise Stop(f"{labels_path.name}: a row names rank {rank}, which the saved search lacks")
        sheet_url = (row.get("url") or "").strip()
        if sheet_url and sheet_url not in (result.get("url"), result.get("canonical_url")):
            url_mismatch += 1
        if key_order is not None and not key_order == result.get("provider_order"):
            order_mismatch += 1
        out.append((rank, relevance(row.get("relevant"))))
    return out, key_note, url_mismatch, order_mismatch


def recorded_rows(name, results):
    marked = RECORDED[name].get("marked")
    if not marked:
        raise Stop(f"{name}'s sheet is missing and no record gives its labels")
    by_rank = {result["rank"]: result for result in results}
    for rank, order in marked.items():
        if by_rank.get(rank, {}).get("provider_order") is None or not by_rank[rank]["provider_order"] == order:
            raise Stop(f"the saved {name} search is not the one recorded: rank {rank} is not at provider position {order}")
    top = {x["rank"] for x in sorted(results, key=lambda x: x["rank"])[:10]} | {
        x["rank"] for x in sorted(results, key=lambda x: x["provider_order"])[:10]
    }
    rows = [(rank, rank in marked) for rank in sorted(top)]
    note = "no sheet: rows rebuilt from the saved search, labels from the PM's record (ranks " + ", ".join(
        f"{rank} at provider position {order}" for rank, order in marked.items()
    ) + " relevant, provider positions checked)"
    return rows, note, 0, 0


def candidate_key(candidate):
    return (candidate.provider, candidate.provider_record_id, str(candidate.url), candidate.title)


def parse_time(text):
    from datetime import datetime

    return None if text is None else datetime.fromisoformat(text)


class Unbounded:
    def __init__(self, filters):
        self.source_types = filters.source_types
        self.since = filters.since
        self.until = filters.until
        self.max_results = 10**9


def universe_from_saved(saved):
    entries = []
    for result in saved["results"]:
        entries.append(
            {
                "key": result.get("canonical_url") or result.get("url"),
                "rank": result["rank"],
                "features": dict(result.get("features") or {}),
                "published": parse_time(result.get("published_at")),
                "porder": result.get("provider_order"),
                "url": result.get("canonical_url") or result.get("url") or "",
            }
        )
    return entries, "the 200 saved results (the store holds no record of this search)"


def universe_from_store(saved, search_row, status_rows, config):
    from debate_core.application.federated_dedupe import merge_candidates
    from debate_core.application.federated_ranking import rank_merged_candidates
    from debate_core.domain import Search
    from debate_core.domain.discovery import ProviderOutcome, ProviderStatus

    search = Search.model_validate_json(search_row[0])
    statuses = [ProviderStatus.model_validate_json(row[0]) for row in status_rows]
    candidates = [c for s in statuses if s.response is not None for c in s.response.results]
    first_index = {}
    for index, candidate in enumerate(candidates):
        first_index.setdefault(candidate_key(candidate), index + 1)
    merged = merge_candidates(candidates)
    answered = len({s.provider for s in statuses if s.outcome is ProviderOutcome.OK})
    query_texts = list(dict.fromkeys(s.query.query for s in statuses))
    ranked = rank_merged_candidates(
        merged,
        queries=query_texts,
        filters=Unbounded(search.filters),
        answered_providers=answered,
        now=search.created_at,
        config=config,
    )
    entries = []
    for entry in ranked:
        c = entry.candidate
        orders = [first_index[candidate_key(m)] for m in c.members if candidate_key(m) in first_index]
        entries.append(
            {
                "key": c.canonical_url or c.url,
                "rank": entry.rank,
                "features": dict(entry.features),
                "published": c.published_at,
                "porder": min(orders) if orders else None,
                "url": c.canonical_url or c.url,
            }
        )
    return entries, f"every merged result of the stored search ({len(entries)})"


def window_of(saved):
    from datetime import timedelta

    starts = []
    ends = []
    for query in (saved.get("expansion") or {}).get("queries") or []:
        since = parse_time(query.get("since"))
        days = query.get("recency_days")
        if since is not None and days is not None:
            starts.append(since)
            ends.append(since + timedelta(days=days))
    filters = saved.get("filters") or {}
    until = parse_time(filters.get("until"))
    if not starts:
        return None
    return min(starts), (until if until is not None else max(ends)), len(set(starts))


def in_call_positions(saved, entries):
    bounds = []
    total = 0
    for call in saved.get("provider_calls") or []:
        count = int(call.get("results") or 0)
        bounds.append((total, total + count))
        total += count
    for entry in entries:
        order = entry["porder"]
        entry["position"] = None
        if order is None:
            continue
        for start, end in bounds:
            if start < order <= end:
                entry["position"] = order - start
                break


def ordered(entries, total_of):
    scored = [(entry, total_of(entry)) for entry in entries]
    scored.sort(
        key=lambda pair: (
            -pair[1],
            pair[0]["published"] is None,
            -(pair[0]["published"].timestamp()) if pair[0]["published"] is not None else 0.0,
            pair[0]["url"],
        )
    )
    return [entry for entry, _ in scored]


def replay(name, data_dir, search_path, labels_path, key_path):
    from debate_core.application.federated_ranking import (
        FEDERATED_RANKING_CONFIG_PATH,
        load_federated_ranking_config,
    )

    saved = saved_search(search_path)
    results = saved["results"]
    results_by_rank = {result["rank"]: result for result in results}
    if labels_path.is_file():
        rows, key_note, _, _ = labelled_rows(labels_path, key_path, results_by_rank)
    else:
        rows, key_note, _, _ = recorded_rows(name, results)
    label_by_key = {}
    for rank, relevant in rows:
        result = results_by_rank[rank]
        label_by_key[result.get("canonical_url") or result.get("url")] = relevant
    relevant_count = sum(1 for _, relevant in rows if relevant)
    config = load_federated_ranking_config(FEDERATED_RANKING_CONFIG_PATH)
    weights = {f: config.weights.weight_of(f) for f in FEATURES}

    database = data_dir / "debate.sqlite3"
    wal = data_dir / "debate.sqlite3-wal"
    if not database.is_file():
        raise Stop(f"no store at {data_dir.name}/debate.sqlite3")
    if wal.is_file() and wal.stat().st_size > 0:
        raise Stop("the store has an unmerged write-ahead log; close every debate-research and rerun")
    connection = sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        search_row = connection.execute(
            "SELECT document FROM searches WHERE search_id = ?", (saved["search_id"],)
        ).fetchone()
        status_rows = connection.execute(
            "SELECT document FROM search_provider_statuses WHERE search_id = ? ORDER BY position",
            (saved["search_id"],),
        ).fetchall()
    finally:
        connection.close()
    if search_row is not None and status_rows:
        entries, universe = universe_from_store(saved, search_row, status_rows, config)
    else:
        entries, universe = universe_from_saved(saved)
    in_call_positions(saved, entries)
    window = window_of(saved)

    def window_recency(entry):
        if window is None:
            return entry["features"].get("recency")
        start, end, _ = window
        if entry["published"] is None:
            return None
        return min(max((entry["published"] - start) / (end - start), 0.0), 1.0)

    def provider_position(entry):
        position = entry["position"]
        return None if position is None else 1 / math.log2(1 + position)

    def total(entry, recency="today", recency_weight=None, position_weight=0.0):
        values = dict(entry["features"])
        if recency == "window":
            values["recency"] = window_recency(entry)
        score = 0.0
        for f in FEATURES:
            weight = weights[f] if not (f == "recency" and recency_weight is not None) else recency_weight
            if values.get(f) is not None:
                score += weight * values[f]
        if position_weight:
            value = provider_position(entry)
            if value is not None:
                score += position_weight * value
        return score

    today_order = ordered(entries, total)
    saved_keys = [r.get("canonical_url") or r.get("url") for r in sorted(results, key=lambda r: r["rank"])]
    reproduced = sum(1 for a, b in zip(today_order[: len(saved_keys)], saved_keys) if a["key"] == b)

    print(f"=== {name}: {search_path.name} ===")
    print(f"universe: {universe}; labels: {key_note}")
    print(f"relevant {relevant_count} of {len(rows)} labelled rows; unlabelled rows count as not relevant")
    if window is None:
        print("window: none; window recency falls back to today's recency")
    else:
        start, end, distinct = window
        print(f"window: {(end - start).days} days, {distinct} distinct query start(s)")
    print(f"today's order rebuilt: {reproduced} of {len(saved_keys)} saved ranks in place")
    unpositioned = sum(1 for e in entries if e["position"] is None)
    print(f"results with no provider position: {unpositioned} of {len(entries)}")

    variants = [("today", {})]
    variants.append(("window recency", {"recency": "window"}))
    variants.append(("no recency", {"recency_weight": 0.0}))
    for w in (0.02, 0.05, 0.10, 0.20):
        variants.append((f"provider position {w:.2f}", {"position_weight": w}))
    for w in (0.02, 0.05, 0.10, 0.20):
        variants.append((f"window recency + provider position {w:.2f}", {"recency": "window", "position_weight": w}))

    baseline = None
    for label, options in variants:
        order = ordered(entries, lambda e, o=options: total(e, **o))
        positions = [i for i, e in enumerate(order, start=1) if label_by_key.get(e["key"])]
        score = ndcg_at_10(positions, relevant_count)
        top_relevant = sum(1 for p in positions if p <= 10)
        unlabelled = sum(1 for e in order[:10] if e["key"] not in label_by_key)
        if baseline is None:
            baseline = score
        shown = ",".join(str(p) for p in sorted(positions))
        print(
            f"  {label:<42} nDCG@10 {num(score)}  relevant in top ten {top_relevant}  unlabelled in top ten"
            f" {unlabelled}  relevant at {shown}"
            + ("" if label == "today" else ("  lower than today" if score < baseline - 1e-9 else ""))
        )
    print()


def main():
    data_dir = Path(sys.argv[1]).expanduser()
    names = ("t05", "t14")
    paths = sys.argv[2:]
    if not len(paths) == 6:
        raise Stop("expected three paths per search")
    missing = [Path(p).name for i, p in enumerate(paths) if not Path(p).is_file() and (i % 3 == 0 or i == 4)]
    if missing:
        raise Stop(f"missing {missing}")
    for index, name in enumerate(names):
        search_path, labels_path, key_path = (Path(p) for p in paths[index * 3 : index * 3 + 3])
        replay(name, data_dir, search_path, labels_path, key_path if key_path.is_file() else None)


try:
    main()
except Stop as stop:
    print("STOP:", stop)
    sys.exit(1)
except Exception as failure:
    frames = traceback.extract_tb(failure.__traceback__)
    own = [frame for frame in frames if frame.filename == "<stdin>"]
    where = own[-1] if own else frames[-1]
    print("FAILED:", type(failure).__name__, "at block line", where.lineno, "in", where.name)
    sys.exit(2)
EOF
fi
```

Success looks like two sections, `=== t05` and `=== t14`, each with:
* a `window: 1826 days, 1 distinct query start(s)` line;
* `today's order rebuilt: 200 of 200 saved ranks in place`;
* a `today` line reading `nDCG@10 0.746` for t05 and `0.438` for t14;
* eleven more variant lines.

Paste back everything it prints, `STOP:` or `FAILED:` included.

## Follow-up work

* **t14's remaining gap (E08, proposal first).** Six of the seven rows in t14's top ten that the
  coach marked not relevant are Crossref-only. Rank 1 has BM25 1.000 from its abstract. A proposal
  on how a provider's abstracts score, replayed on t14's stored record, the one labelled record
  left. It depends on question 2.
* **A labelled search keeps its stored record (E08).** The dev store was replaced between 2026-11-02
  and 2026-11-08 and took t05's provider record, snippets included, with it. A blind-labelling
  hand-off (v1-e08-t16's repeat) should also save the search's stored record, so that a later
  ranking change can be replayed on it.
* **A pull request body over GitHub's limit (E41, delivery tooling).** `scripts/task pr` copies the
  report's Summary, Acceptance criteria, Operator follow-ups and PM review into the body, and
  GitHub refuses a body over 65,536 characters. This report's four operator blocks made it 67,439
  characters, and `gh pr create` failed after the push. `task_helper.py pr-body` could shorten a
  section past a set length and link to the report instead. For this task, the blocks that ran
  were moved out of the section unchanged.
* **t14's ac3 record names the wrong build.** It says `v1.1.0-dev.342`, but the search ran taxonomy
  1.5.0 with 12 queries and five providers (a build after 2026-11-05). This is for the PM's records.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-11

**Notes:**

1. **ac1 passes.**
   - The positions block reproduced both records exactly.
   - The replay scored every variant before any code, and the first code commit (`5d03bc1`) follows
     the ruling.
   - The session withdrew its own first proposal on the replay's evidence (t05 0.605, which the spec
     forbids), which is the process working as intended.
   - It also took care with the coach's data:
     - every block prints positions and template ids, never a title or URL;
     - exceptions print their type, never their message;
     - the store is opened `immutable=1`;
     - the blocks were rehearsed on an invented store first.
2. **ac2 passes.**
   - **Red:** 8 failed against a skeleton that always counts recency, each at its assertion. The one
     crash in the first red run, an existing test missing the new key, was fixed and the run repeated.
   - **Green:** 160.
   - **Mutants:** all 9 caught, including the 365 boundary, the `--since` exemption and "any query
     short".
   - **The record:** `docs/data/federated-ranking-labelled-searches.md` holds both replayed scores as
     lower bounds, with their unseen-row counts, beside provider order.
   - **The check against real data:** the operator's run of the built code reproduced the replay.
3. **The ruled change is scoped as ruled.**
   - Recency is unknown only when the request has no `--since` and every expanded query's window is over
     365 days or has no limit.
   - Uniqueness, the 30-day templates, `--since`, `daily` and typed searches are each pinned unchanged.
4. **Deviations accepted.**
   - 1, t05's labels from the PM's record, checked against the saved search.
   - 2, t05 from its saved file alone.
   - 3, the four `search --auto-cut` budget tests: the ruled ranking reorders the CLI fixture, so
     `--auto-cut 3` now cuts four results for three verified cards. Their expected calls were worked
     out again by hand, and the budget rule is unchanged. The PM adds `packages/debate_cli/tests` to the
     spec's packages in the next batch.
5. **Follow-ups, which the PM files in the next batch:**
   - **E08, p2, proposal first: t14's remaining gap,** with the ranking still at 0.459 against provider
     order's 0.746. The figures above show that a snippet carries the score. A 149-to-289-word Crossref
     abstract outscores a 4-to-23-word title, while 1,784 of 2,758 results have no snippet at all. So
     the proposal weighs how a provider's abstract counts, for example field-weighted BM25 or a capped
     snippet contribution. It is replayed on t14's stored record, and on v1-e08-t16's ac3 search once
     that search can run again: tonight's attempt lost OpenAlex to an HTTP 400 on the joined request,
     which is filed separately.
   - **E08, p3:** a labelled search's hand-off keeps its stored record, labels and key together outside
     the dev store (t05's was lost with the store).
   - **The record's build tag for t14's ac3 (`v1.1.0-dev.342`) is a slip:** the search ran taxonomy
     1.5.0 with 12 queries. The PM corrects it in the next batch.
6. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.

<!-- docs-index: The coach's labelled federated searches and each ranking change's nDCG@10 on them (counts and scores only) -->
# Federated ranking on the coach's labelled searches

This page records the federated searches the coach has labelled blind, and every ranking change
scored against them. It records counts and scores only: no title, URL, snippet or card text from a
search or a sheet appears here.

A labelled sheet is built from one saved search. It holds the ranking's top ten and the providers'
top ten, merged, in title order, with no rank shown, and the coach marks each row relevant or not.
**nDCG@10** gives a relevant row in the first ten 1 / log2(position + 1), and divides by the score of
the best possible order of the sheet's relevant rows. "Provider order" is a result's place among
the saved results sorted by `provider_order`, its first appearance in fan-out order. A change is
scored by replaying the saved search through it, with no provider call. A row the coach never saw
that enters a replayed top ten counts as not relevant, so such a score is a **lower bound**, and
the table says how many such rows entered.

## The labelled searches

Both are the Policy NHI topic's politics DA link search ("national health insurance",
`--argument politics-da --need link --topic policy-2026-27-nhi --max-results 200`). Every query of
both asked a five-year window (1,826 days, the coach's window for a link).

| Search | Run | Taxonomy | Queries | Providers that answered (results) | Sheet rows | Relevant | What a replay can read |
|---|---|---|---|---|---|---|---|
| v1-e08-t05 ac6 | 2026-11-02 | 1.2.0 | 7 (one OpenAlex request each) | OpenAlex (700), rss (0, one feed unreadable) | 20 | 3 | its 200 saved results only: the dev store was replaced between 2026-11-02 and 2026-11-08, and its stored record went with it |
| v1-e08-t14 ac3 | 2026-11-08 | 1.5.0 | 12 (7 link templates and 5 mechanism queries; one joined OpenAlex request) | OpenAlex (2,400), Crossref (2,400), Federal Register (961), GovInfo (2,075), rss (0) | 19 | 6 | its whole stored record: 2,758 merged results |

t05's sheet is not on the operator's Mac. Its labels are the PM's ac6 record: ranks 1, 9 and 10
relevant, at provider positions 117, 441 and 257, and every other row not relevant. Every replay
checks those three positions against the saved search before it uses them.

## Scores

| Ranking | Measured | t05 nDCG@10 | t05 relevant in top ten | t14 nDCG@10 | t14 relevant in top ten |
|---|---|---|---|---|---|
| Provider order | at labelling | 0.000 | 0 | 0.746 | 4 |
| The ranking as built in v1-e08-t03 (recency on a 90-day half-life) | at labelling | 0.746 | 3 | 0.438 | 3 |
| Recency unknown when every query's window is longer than 365 days or any age, with no `--since` (v1-e08-t24, the PM's ruling of 2026-11-11) | replayed by the operator, 2026-11-11 | **0.767**, a lower bound: 1 unseen row in the top ten | 3 | **0.459**, a lower bound: 3 unseen rows in the top ten | 3 |

After v1-e08-t24, the relevant rows sit:
* on t05 at 1, 7 and 9 (they were at 1, 9 and 10);
* on t14 at 2, 3, 5, 12, 52 and 76 (they were at 2, 3, 8, 25, 39 and 137).

t14's ranking is still below its provider order. The PM has filed the follow-up: rows found only by
Crossref, ranked on their abstracts' BM25.

### Changes measured and not taken (v1-e08-t24, replayed 2026-11-11)

| Change | t05 | t14 | Why not |
|---|---|---|---|
| Recency as the position in the queries' five-year window | 0.605 | 0.268 | It lowers both searches; lowering t05 is forbidden |
| The providers' own position, 1 / log2(1 + position in the first call that returned the result), weight 0.02 or 0.05 | 0.746 | 0.438 | It changes neither top ten |
| The same, weight 0.10 or 0.20 | 0.437 or 0.296 | 0.430 or 0.420 | It lowers both searches |
| The same added to window recency, weights 0.02 to 0.20 | 0.605 to 0.296 | 0.268 to 0.410 | It lowers both searches |

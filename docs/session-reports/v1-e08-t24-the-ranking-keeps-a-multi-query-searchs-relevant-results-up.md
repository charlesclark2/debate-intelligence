# Session report: v1-e08-t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up

| | |
|---|---|
| Task | `v1-e08-t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up` — On a search of many queries, the ranking keeps the results the coach marks relevant above the providers' own order |
| Spec | [`plan_specs/v1/e08-research-workflows/t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up.yaml`](../../plan_specs/v1/e08-research-workflows/t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up` |
| Session status | IN PROGRESS: waiting on the operator's positions block (below), before the proposal <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

This task is proposal first. **Where it stands:** the positions block is written and tested, and
nothing else has been done. The block prints, for every row of the two labelled Policy sheets
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

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `the-ranking-keeps-a-multi-query-searchs`: Multi-query ranking | Not started | Waiting for ac1: the positions, the proposal and the PM's ruling come first. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the operator's positions block has run and the PM has ruled on the proposal before any code | NOT RUN | The block is under [Operator follow-ups](#operator-follow-ups). The proposal follows its output. |
| ac2: the ruled change holds by tests on fixtures shown failing first, and both searches' replayed nDCG@10 are recorded beside today's (operator) | NOT RUN | After the ruling. |
| Node: `uv run pytest packages/debate_core/tests -k ranking` | NOT RUN | After the ruling. |

## Files changed

* `docs/session-reports/v1-e08-t24-…md`: this report. No code has changed.

## Deviations from the spec

1. **t05's labels come from the PM's ac6 record, not from the coach's sheet.** The spec asks for
   positions from the labelled sheets, and t05's filled sheet is not on the operator's Desktop. The
   record gives the same labels: 3 relevant of 20 rows, at ranks 1, 9 and 10 (provider positions
   117, 441 and 257), and the rest not relevant. The block checks those positions against the saved
   search before it uses them. If the sheet is found, the block reads it instead.
2. **t05's positions come from its saved file alone.** Its provider record is in no store (the dev
   store was replaced between 2026-11-02 and 2026-11-08), so its BM25 cannot be recomputed from
   titles and snippets. Its saved feature values are exact. Its word-match columns use titles only.

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

## Follow-up work

None yet.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

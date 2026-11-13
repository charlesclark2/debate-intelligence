# Session report: v1-e08-t15-ld-research-starts-broad-and-narrows-from-the-first-page

| | |
|---|---|
| Task | `v1-e08-t15-ld-research-starts-broad-and-narrows-from-the-first-page` — LD research starts broad and narrows from what the first page turns up |
| Spec | [`plan_specs/v1/e08-research-workflows/t15-ld-research-starts-broad-and-narrows-from-the-first-page.yaml`](../../plan_specs/v1/e08-research-workflows/t15-ld-research-starts-broad-and-narrows-from-the-first-page.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t15-ld-research-starts-broad-and-narrows-from-the-first-page` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Stopped at the proposal (ac1, "the proposal is sent to the PM and ruled on before any code"),
which is below. No code yet. Two facts come before the design. First, no search has ever received
OpenAlex's subject fields: the adapter's `select=` asks for none of them, and no OpenAlex body in
the repo carries them. Second, building any version needs `debate_core.integrations`, which the
spec's packages leave out.

## Proposal for the PM's ruling (ac1)

### What the repo says first

1. **No search has received a subject field yet.** `SELECTED_FIELDS` in
   `packages/debate_core/src/debate_core/integrations/discovery/openalex.py` asks OpenAlex for
   neither `topics`, `keywords` nor `concepts`, and Crossref's `SELECTED_FIELDS` (`crossref.py`)
   does not ask for `subject`. So t05's live de-extinction search got none of them, and neither did
   any other search.
2. **No fixture carries them.** Every OpenAlex body in the repo
   (`packages/debate_core/tests/fixtures/discovery/openalex/`,
   `packages/debate_cli/tests/fixtures/search/`) was written by hand from OpenAlex's documented Work
   object, and none has these fields. t05 committed no de-extinction fixture: that search was live,
   and its saved JSON is on the operator's Desktop, without subjects (point 1). So a test needs a
   new body, written by hand from the documented shape as every existing one was. It is not a
   recording.
3. **Which field carries the coach's directions (ethics, ecology, mourning, the animal subject) is
   not measured.** One live OpenAlex request answers it (operator block below). It waits for
   v1-e39-t18, so it is not for today.
4. **Scope.** Reading a subject means changing the OpenAlex adapter (`select=` and the mapping),
   which is `debate_core.integrations`. `constraints.packages` lists only `debate_core.application`,
   `debate_core.domain`, `debate_cli`, the two packages' tests and `docs/guides`. Agreement 5 also
   asks for a smoke check under `tests/smoke/`, which is not listed either.
5. **Naming.** `CandidateResult` says "nothing else on this model is a provider's field", so a
   subject goes on it as a provider-neutral `subjects` field: a name, its scheme
   (`openalex_keyword`) and the provider's id, as `identifiers` holds ids. On the command line it is
   a "subject", because `--topic` already names the debate topic.

### 1. Where the narrowing directions come from

Only the first page's own provider fields, never a model:

* **OpenAlex `keywords`**, recommended. These are short phrases (a few words), each with an id and
  a score. A short phrase can be added to a query as words.
* **OpenAlex `topics`**: up to three per work, from a fixed taxonomy of about 4,500 labels, with
  subfield, field and domain above each. Left out of the first version. Their names are long
  taxonomy labels, and added to a query as words they demand every word (for a label of the form
  "X and Y", both X and Y). They need a filter to narrow by, which is the second step below.
* **Not `concepts`.** This is OpenAlex's legacy tagging, which topics replaced in 2024, and its top
  levels are whole disciplines ("Biology", "Philosophy").
* **Not Crossref `subject`.** As I understand it, these are the journal's categories, not the
  work's, so every article in an ecology journal says "Ecology". I have not measured it.

What I describe here is OpenAlex's documentation as I know it. I read no documentation live (live
reads go to the operator). The measurement confirms it, or the PM can read the Work object's
`keywords` and `topics` sections at help.openalex.org.

**How the subjects are counted** (a pure function in `debate_core.application`):

* Counted over the results the table shows: the ranked page, which is 20 by default and up to
  `--max-results`. Each distinct result counts a subject once, so a source two providers found
  counts once.
* **Kept:** a subject on 2 or more results.
* **Left out:**
  * a subject on one result only;
  * a subject on every result that carries any keyword, because narrowing by it changes nothing;
  * a subject whose words are all in the query already, such as the keyword "De-extinction" on a
    de-extinction search.
* **Order:** by how many results carry it, then by the best rank among those results, then by name.
* **Shown:** at most 5.
* **Scores:** OpenAlex's keyword scores are not used. Its own threshold already decides which
  keywords a work gets.

### 2. What a student sees and types

The table gets these lines after the provider footer:

```text
Narrow it: subjects OpenAlex gave 2 or more of these 20 results
  animal ethics, on 6:  debate-research search 'de-extinction animal ethics'
  conservation biology, on 5:  debate-research search 'de-extinction conservation biology'
```

These labels are illustrative, not measured. Each command is the student's own search with the
subject's words added to the query, and the student's `--since`, `--until`, `--max-results`,
`--providers` and `--topic` kept. It is quoted with single quotes, which are safe to paste into
zsh. A student can copy the line, or type a word of their own in the same way.

`--json` and `--save` get a `narrowing` list. Each entry has `subject`, `scheme`, `id`, `results`,
`best_rank`, `query` and `command`. The first version shows nothing for:

* an expanded search (`--argument` with `--need`), because its queries are the taxonomy's;
* a search with no rows (exits 1, 3 and 7);
* a page where no subject qualifies (the JSON then has an empty list).

### 3. Searching within a saved search

Not in the first version. When it is built, the recommended meaning is a local filter with no
provider call:

```text
debate-research search --within ~/Desktop/search-ld-de-extinction.json 'mourning'
```

This reads the `--save` file and keeps the saved results whose title has every word, or that carry
a subject with those words. They print in their saved rank.

* **Why the file, not the stored search.** The saved search is named by the `--save` file, which
  the student named themselves. A search stored in SQLite is named by a ULID that only `--json`
  prints and no command lists. No installed build reads a stored search yet (t05's report), so the
  first reader would also own cross-build tolerance.
* **A limit.** The file holds no abstracts (search never prints or saves one), so the words match
  titles and subjects only.
* **When the file is missing,** or is not a search's JSON: exit 2, naming the path.
* **A file saved before this version** has no subjects. Its words match titles only, and a note
  says the search was saved by a build that kept no subjects and should be run again to narrow by
  subject.

The other meaning is to re-ask OpenAlex with the narrowed query, filtered to the saved search's
OpenAlex works (`ids.openalex:W…|W…`). As I understand it, a filter takes up to 100 values. I do
not recommend it: it spends requests (point 4) to answer from fewer works than a fresh narrowed
search, and it cannot re-ask the results that came from Crossref or a feed.

### 4. What each costs in provider requests

Today, an unexpanded LD search under the 15 s deadline sends:

* OpenAlex: one request per 100 results (1 at the default 20, 2 at `--max-results 200`). Without
  a key that comes out of a budget of about 100 searches a day; with one, about 1,000.
* Crossref: one call (`rows` ≤ 200). It is paced at 1 a second, or 3 with the email, but a single
  call never waits.
* The feeds: each configured feed read once with a conditional request (10 feeds today).

| What | Provider requests | Under `MAX_SEARCH_CHARS` (1,500)? |
|---|---|---|
| The suggestions | None: they come from the same answer. The answer is larger, and `select=` grows by `,keywords`, about 10 URL characters against `MAX_URL_CHARS` 3,500 (the search limit binds first, at about 1,860). | Unchanged |
| A narrowed search (recommended) | The same as a fresh search, so one more out of the day's OpenAlex budget | Yes. The query grows by a keyword's few words, and an unexpanded search is one query of tens of characters. A typed query already near 1,500 goes as any typed query does today: asked alone, and OpenAlex refuses one over 1,500 with a `400` that the footer names. |
| Within a saved file (local) | None | Not sent |
| Within, re-asked | OpenAlex only: one request per 100 of the saved search's OpenAlex works (2 for t05's 200). Nothing from Crossref or the feeds. | Yes. The ids go in `filter=`, about 1,200 URL characters per 100 ids. |
| Narrowing by topic filter (second step) | OpenAlex only: one request per page | Yes. `search=` is unchanged. |

### 5. Recommendation and the smallest version

**Build first:**

1. The OpenAlex adapter asks for `keywords` and maps them to `CandidateResult.subjects`. The field
   is additive and defaults to empty.
2. The application counts them as in section 1.
3. The table's "Narrow it" lines, and `narrowing` in `--json`/`--save`.
4. The search guide's paragraph on narrowing.
5. A smoke check.

The tests run on one new body for `/works`, written by hand from the documented shape as every
OpenAlex fixture is, and are shown failing first.

**Second step,** only if the measurement shows that keywords miss the directions: topics, with a
`--subject <topic id>` filter that asks OpenAlex alone. **Third step:** `--within` on a saved file,
locally.

**The open risk:** whether OpenAlex's keywords on the de-extinction first page carry ethics,
ecology, mourning or the animal subject is unmeasured, and humanities words may be the weakest
case. My recommendation is to build now, because the work is cheap and switching the field is one
constant. The operator's measurement runs after t18 and before the merge; if keywords miss, the
second step becomes a follow-up task.

### The measurement (not to be run while v1-e39-t18's restore is going)

This is for the operator, after t18's restore and measurements have finished. It is one live
OpenAlex request with no key, run from the home folder, and it touches nothing on disk. It prints
only subject names and counts, never a title. It takes a few seconds.

```bash
cd "$HOME" && python3 -I -c 'import collections, json, urllib.request
url = "https://api.openalex.org/works?search=de-extinction&per_page=100"
works = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "debate-research-measure"}), timeout=30))["results"]
print("works", len(works))
for size in (20, 100):
    page = works[:size]
    for field in ("keywords", "topics", "concepts"):
        counts = collections.Counter()
        carrying = 0
        for work in page:
            names = {entry.get("display_name") for entry in (work.get(field) or [])}
            carrying += bool(names)
            counts.update(names)
        print("first", size, field, "on", carrying, "works,", len(counts), "distinct,", sum(1 for name in counts if counts[name] >= 2), "on 2 or more")
        for name, count in counts.most_common(15):
            print("   ", count, name)
'
```

Success looks like `works 100`, then six blocks, one for each field over the first 20 and the first
100 works. Paste them all back. A field that OpenAlex no longer serves prints `on 0 works`.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

<!-- Choices the spec left open, with the reasoning. -->

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

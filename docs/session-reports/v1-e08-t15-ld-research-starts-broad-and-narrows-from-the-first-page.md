# Session report: v1-e08-t15-ld-research-starts-broad-and-narrows-from-the-first-page

| | |
|---|---|
| Task | `v1-e08-t15-ld-research-starts-broad-and-narrows-from-the-first-page` — LD research starts broad and narrows from what the first page turns up |
| Spec | [`plan_specs/v1/e08-research-workflows/t15-ld-research-starts-broad-and-narrows-from-the-first-page.yaml`](../../plan_specs/v1/e08-research-workflows/t15-ld-research-starts-broad-and-narrows-from-the-first-page.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t15-ld-research-starts-broad-and-narrows-from-the-first-page` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`debate-research search` now suggests up to five narrower searches from the OpenAlex keywords that
two or more results on the page share. Each suggestion is a command a student can copy and paste:
the same search with the keyword's words added. This is the keyword version the PM ruled on
(2026-11-12), and the proposal it ruled on is kept below.

* **Pieces.** The OpenAlex adapter asks for `keywords` and maps each usable one to a
  provider-neutral `CandidateResult.subjects`. `debate_core.application.search_narrowing` applies
  the PM's counting rules. The CLI prints the lines after the provider footer and adds `narrowing`
  to `--json` and `--save`. The search guide (the `debate-research search` section of
  `packages/debate_cli/README.md`) says how a student narrows a search.
* **Cost.** No extra provider request and no model call.
* **Tests.** 45 new test cases, a smoke test and one smoke assertion, on one hand-written `/works`
  body. The new tests were run red first, and 18 mutants were each caught at an assertion.
* **The live measurement** confirmed the keyword shape the fixture and the parser assumed, so
  neither needed correcting. On the de-extinction page, keywords carry three of the coach's four
  directions (ethics, ecology, the animal subject) and miss mourning, which topics miss too
  (below).
* **For the PM first:** the packages amendment (Q2) has not reached dev yet (Deviation 1), and on
  the real page the cap of five may hide "conservation ethics" (Follow-up 2).

## The PM's rulings (2026-11-12)

Quoted from the relay:

> Q1. Yes: build the keyword version as proposed. OpenAlex `keywords` only, into a provider-neutral
> CandidateResult.subjects, counted over the ranked page shown, kept on 2+ results, left out when on
> a single result, on every keyword-carrying result, or all of its words already in the query.
> Ordered by result count, best rank, name; at most 5. The footer wording is accepted. Two additions:
> Quoting: the printed command must paste safely when the query or a keyword contains an apostrophe
> ('\'' escaping, or the quoting zsh needs), shown by a test with an apostrophe in each. Never print
> a command that would break. Defensive parsing: a keyword item without a usable display name is
> skipped, not a failure. A work with no keywords contributes nothing. "Within a saved search" is not
> in v1. Record the local --within design as a follow-up. The topics --subject step is a follow-up
> only if the measurement shows keywords miss.
>
> Q2. Yes, amended by the PM's next batch: add debate_core.integrations.discovery (not all of
> debate_core.integrations) and tests/smoke to constraints.packages.
>
> Q3. Build now. The measurement need not wait for v1-e39-t18 [...] Read the operator's output
> before writing the report, and record it there as the evidence for (or against) keywords.
>
> Q4. Yes: one hand-written /works body. [...] write the fixture in the shape you expect (id,
> display_name, score), and let the live request confirm it. If the live shape differs, correct the
> fixture and the parser before the report, and say so.

## The measurement: what OpenAlex's de-extinction page carries

The operator ran one keyless OpenAlex request on 2026-11-12:
`/works?search=de-extinction&per_page=100&select=id,keywords,topics`. It printed subject names and
counts only, never a title or abstract, and touched nothing on disk. The command was:

```bash
cd "$HOME" && python3 -I -c 'import collections, json, urllib.request
url = "https://api.openalex.org/works?search=de-extinction&per_page=100&select=id,keywords,topics"
works = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "debate-research-measure"}), timeout=30))["results"]
print("works", len(works))
items = [item for work in works for item in (work.get("keywords") or [])]
print("keyword item keys", sorted({key for item in items if isinstance(item, dict) for key in item}))
print("keyword id prefixes", sorted({str(item.get("id", "")).rsplit("/", 1)[0] for item in items if isinstance(item, dict)}))
scores = [item.get("score") for item in items if isinstance(item, dict) and isinstance(item.get("score"), (int, float))]
print("keyword items", len(items), "with a score", len(scores), "lowest", min(scores, default=None), "highest", max(scores, default=None))
print("keywords per work", sorted(collections.Counter(len(work.get("keywords") or []) for work in works).items()))
for size in (20, 100):
    page = works[:size]
    for field in ("keywords", "topics"):
        counts = collections.Counter()
        carrying = 0
        for work in page:
            names = {entry.get("display_name") for entry in (work.get(field) or []) if isinstance(entry, dict)}
            carrying += bool(names)
            counts.update(names)
        print("first", size, field, "on", carrying, "works,", len(counts), "distinct,", sum(1 for name in counts if counts[name] >= 2), "on 2 or more")
        for name, count in counts.most_common(15):
            print("   ", count, name)
'
```


**The shape.**

* OpenAlex accepted `keywords` and `topics` in `select=`.
* Every keyword item had exactly `display_name`, `id` and `score`.
* Every id was under `https://openalex.org/keywords`.
* There were 702 keyword items on the 100 works, all with a score, from 0.302 to 1.0.
* Every work had at least one keyword: 1 to 13 each, 7 on average, and 7 in the middle work. The
  PM's reading of the documentation said "typically five or six".

The fixture and the parser assumed this shape, so neither needed correcting. The score is not kept.
Its lowest value, 0.302, looks like OpenAlex's own threshold.

**Keywords against the coach's directions.** The first 20 works are OpenAlex's relevance order, not
our ranking. Over them, 101 distinct keywords appeared, 16 of them on 2 or more works. The top 15,
by how many works carry each:

* on 20 works: de-extinction;
* on 6: extinction;
* on 4: woolly mammoth, biodiversity conservation, cloning;
* on 3: passenger pigeon, reintroduction, extinct species, genetic engineering, conservation ethics;
* on 2: thylacine, animal welfare, species concept, genetically modified organisms, human-animal
  relations.

Over the first 100 works there were 350 distinct keywords, 87 of them on 2 or more. Conservation
biology (13) and biodiversity loss (7) join the list.

| The coach's direction | Keywords on the first 20 | Topics on the first 20 |
|---|---|---|
| ethics | conservation ethics (3), animal welfare (2) | Philosophical Ethics and Theory (3), Bioethics and Human Rights Issues (3), Posthumanist Ethics and Activism (3). Environmental Philosophy and Ethics is on all 20, so the rule would leave it out. |
| ecology | biodiversity conservation (4), reintroduction (3) | Conservation, Ecology, Wildlife Education (6), Wildlife Ecology and Conservation (5) |
| mourning | none in the top 15 of 20 or of 100 | none in the top 15 of 20 or of 100 |
| the animal subject | human-animal relations (2), animal welfare (2), species concept (2) | Animal Law and Welfare (2), Posthumanist Ethics and Activism (3). Geographies of human-animal interactions is on 1 of 20 (5 of 100). |

**Verdict.** Keywords carry three of the four directions and miss mourning. Topics miss mourning
too, so the topics step would not recover it. Topics do add humanities directions that keywords
lack (posthumanist ethics, ecocriticism), but they reach the same three directions. The ruling
makes topics a follow-up only if keywords miss. This is a partial miss that topics would not
repair, so I have not filed it; the PM decides (Follow-up 3).

**Under the rules as built,** the first 20 would show fewer of these. De-extinction is on all 20 and
extinction's words are all in the query, so both are left out. That leaves woolly mammoth,
biodiversity conservation and cloning (4 each), then two of the five keywords on 3 works, chosen by
best rank, which this measurement does not give. So conservation ethics may or may not be among the
five shown (Follow-up 2).

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

### The measurement (as proposed)

The proposal's block also asked for `concepts`. The PM's Q3 ruling had it run that day, and asked
for keyword (and topic) names and counts only, so the block that ran is the narrower one in the
measurement section above.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `ld-research-starts-broad-and-narrows-fro` (Narrowing) | Done | Proposal and ruling (`e820271`). Adapter, rules and presenter (`735b0ad`). Guide and smoke checks (`583a06b`). Its criterion passes (below). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the proposal is sent to the PM and ruled on before any code | PASS | Proposal committed in `e820271`, before any code. The PM's rulings of 2026-11-12 are quoted above, and code started after them (`735b0ad`). |
| ac2: what the ruling asks for is built with tests on recorded fixtures shown failing first, and the search guide says how a student narrows a search | PASS | Built as ruled: keywords only; the counting rules; apostrophe-safe quoting, tested with an apostrophe in the query and in the keyword; unusable keyword items skipped; no `--within`. **Red first**, against skeletons that suggest nothing: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <the four test files> -n 0 -q --tb=line` gave `76 failed, 277 passed`. The 76 are 30 of the 45 new cases, failing at their assertions (empty suggestions, no subjects, `KeyError: 'narrowing'`, no `Narrow it:` line), and 46 existing OpenAlex tests whose updated recordings expect `select=…,keywords`. The 15 new cases that passed on the skeletons are the ones whose right answer is "nothing" (refusals, skipped items, an empty page); 10 of them were shown failing by mutants (below). **Green:** the same files give `353 passed`. **Guide:** "Narrowing a search" in the `debate-research search` section of `packages/debate_cli/README.md`. **Fixture:** one hand-written `/works` body, in the shape the live request confirmed. |
| Node: Narrowing tests pass (`uv run pytest packages/debate_core/tests/application packages/debate_cli/tests -k search`) | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application packages/debate_cli/tests -k search -n 4 -q` → `761 passed in 33.46s`. |

**Mutants**, each run against the four test files: 18 mutants, every one caught at an assertion. I
checked the failure lines of the three most likely to crash instead, and the last two (`--tb=line`).

* **The CLI command line**
  * `shell_word` refuses nothing: 6 failed.
  * apostrophes are not escaped: 6 failed.
  * no `--` before a query that starts with `-`: 1 failed.
  * the default `--max-results` is printed: 5 failed.
* **The adapter**
  * a keyword a work lists twice is kept twice: 1 failed.
  * an unusable keyword is kept, as "unnamed": 8 failed.
  * `keywords` is not asked for: 46 failed.
  * a `keywords` object is read as one keyword: 1 failed.
* **The domain:** empty `subjects` are dumped: 1 failed.
* **The counting rules**
  * a subject on one result is kept: 4 failed.
  * a subject on every keyword-carrying result is kept: 7 failed.
  * a subject whose words are all in the query is kept: 5 failed.
  * a result without subjects counts as carrying: 7 failed.
  * no best-rank tie-break: 1 failed.
  * six suggestions: 5 failed.
  * only the first member's subjects are read: 1 failed.
  * subjects differing in case are two: 1 failed.
  * an expanded search suggests too: 1 failed.

No mutant showed these five cases failing:

* the three unreadable `keywords` shapes `"de-extinction"`, `7` and `[["de-extinction"]]`. Each is
  turned away by two type checks in a row: removing the list check still leaves the object check,
  and removing the object check crashes rather than misbehaves;
* the empty page;
* the constants pin (`MIN_RESULTS`, `MAX_SUGGESTIONS`).

The two smoke mutants (no `narrowing` key; apostrophes not escaped) each failed
`tests/smoke/test_search_smoke.py` for its reason (`KeyError: 'narrowing'`, and the command list's
assertion).

**Before the report** (agreement 10):

* **The affected set.** `uv run scripts/affected_tests.py` lists 581 test files, because the root
  `conftest.py` imports `debate_core.domain.discovery` through `fake_router` and `ports.providers`. That
  is most of the suite, over two minutes, so it is left to the pull request's `ci`, which runs the same
  selection. I did not run `--run`.
* **The always-run list,** with `tests/docs` and `tests/smoke/test_search_smoke.py`: `632 passed in
  28.43s`.
* **`packages/debate_core/tests/domain` and `packages/debate_core/tests/integrations/discovery`,** with
  the two docs-check script tests: `2492 passed in 10.59s`.
* **`packages/debate_core/tests/application` as a whole** reached its 115-second stop past 82 per
  cent, at a load near 9, with the v1-e39-t18 restore running. Its files that build candidates and
  searches gave `692 passed in 2.86s`: `test_federated_*`, `test_query_expansion.py`, `test_digest_*`,
  `test_daily_presets.py`, `test_batch_cut_service.py`, the two configuration-gap files and
  `test_search_narrowing.py`. The rest is left to `ci`.
* **The CLI's search, daily, output, presenter, installation and doctor test files:** `342 passed in
  12.60s`.
* **Static checks**
  * `uv run ruff format --check .`: 2082 files already formatted. `uv run ruff check .`: all checks
    passed.
  * `.venv/bin/pyright packages/debate_core packages/debate_cli tests/smoke/test_search_smoke.py`: 0
    errors.
  * `uv run lint-imports`: 20 kept, 0 broken.
  * `uv run scripts/check_thin_handlers.py`: 74 handlers within 25 statements.
  * `uv run scripts/check_links.py`: OK.
  * `uv run scripts/check_command_blocks.py --base origin/dev`: OK.
  * `uv run scripts/validate_specs.py`: OK (below).

## Files changed

* **`debate_core.domain.discovery`.** `Subject`, `SubjectScheme` (`openalex_keyword`) and
  `CandidateResult.subjects`, which is left out of a dump when empty, so stored and pinned shapes are
  unchanged.
* **`debate_core.integrations.discovery.openalex`.** `keywords` added to `SELECTED_FIELDS`, and
  `subjects_of`.
* **`debate_core.application.search_narrowing`** (new): `narrowing_suggestions`, `narrowing_for` and
  `words`.
* **`debate_cli.presenters.search_narrowing`** (new): `shell_word`, `SearchCommandLine`, the lines
  and the JSON. `search_presenter` adds both to the table and the payload, and `commands/search.py`
  builds the command line from the student's options. The `--max-results` default is now the
  presenter's `DEFAULT_MAX_RESULTS`, still 20.
* **`packages/debate_cli/README.md`:** the search guide's paragraph on narrowing.
* **Tests**
  * `packages/debate_core/tests/application/test_search_narrowing.py` (new, 12 cases).
  * `packages/debate_cli/tests/test_search_narrowing_presenter.py` (new, 15).
  * 10 adapter cases in `test_openalex.py`, and 8 CLI cases in `test_search_command.py`.
  * `tests/smoke/test_search_smoke.py`: one new test and one new assertion.
* **Fixtures**
  * `works_keywords.body.json` (new, hand-written), and its entry in the OpenAlex fixtures README.
  * The six recorded OpenAlex request URLs, and the test's `SELECT` constant and URL pin, now ask for
    `keywords`.

## Deviations from the spec

1. **The packages amendment has not reached dev yet.** The PM ruled (Q2) that
   `debate_core.integrations.discovery` and `tests/smoke` join `constraints.packages`, in the PM's
   next batch. On `origin/dev` at `938358b` this task's spec still lists only
   `debate_core.application`, `debate_core.domain`, `debate_cli`, the two packages' tests and
   `docs/guides`. This branch changes `debate_core.integrations.discovery.openalex` and
   `tests/smoke/test_search_smoke.py` under that ruling, and leaves the spec's constraints for the PM
   to amend. If the amendment merges first, a `scripts/task sync` brings it in.
2. **The search guide is a package README, not a file under `docs/guides`.** That follows the
   spec's own amendment of 2026-11-05, so `docs/guides` is untouched.

## Decisions and assumptions

* **Within one work,** a keyword is kept once, compared ignoring case. A keyword's `score` is not
  kept, and a non-text `id` is dropped while the keyword stays.
* **Across the page,** subjects that differ only in case are one subject, named as the best-ranked
  result carrying it names it. A source two providers found counts a subject from either record,
  once.
* **"Its words are all in the query"** compares runs of letters and digits, ignoring case, so a
  hyphen or an apostrophe splits a word: `extinction` is in `de-extinction`.
* **What the command keeps:** `--since`, `--until`, `--max-results` (when not 20), `--topic` and
  `--providers`, in `search --help`'s order. `--save`, `--auto-cut`, `--format`/`--json` and the
  global options are the student's to add, as the guide says.
* **How the command is quoted.** The query goes in single quotes, with an apostrophe written `'\''`.
  A query with any character `str.isprintable` refuses (a newline, a tab, a control or zero-width
  character) gets no command: the line names the subject alone and the JSON's `command` is `null`. A
  query starting with `-` follows `--`. An option value outside plain ASCII letters, digits and
  `-_.,:` is quoted the same way.
* **When the lines show.** They come after the footer, on exit 0 and 6, whenever there are rows.
  `narrowing` is in every search payload (`data`, or `error.details`), an empty list when there is
  nothing.
* **The shell test.** The apostrophe test runs the printed command through `sh`, and through zsh
  when it is installed (the operator's shell; Linux runners usually have none), with `printf` in
  place of the program, and checks the words each shell reads.

## Operator follow-ups

None. The measurement the PM asked for (Q3) has run, and its output is recorded above.

## Follow-up work

1. **`search --within <saved file>`, as a local filter** (the PM's ruling, Q1). Recorded from the
   proposal's section 3:
   * It reads a `--save` file and keeps the saved results whose title has every word typed, or that
     carry a subject with those words, in their saved rank, with no provider call.
   * A missing or non-search file exits 2 and names the path.
   * A file saved before this version has no subjects: it matches titles only, with a note to run
     the search again.
   * It needs `subjects` per result in the saved JSON, which this version does not write (it writes
     only `narrowing`).
   * It belongs to E08.
2. **On the real page, the cap of five may hide the coach's directions.** By the measurement, the
   first 20 de-extinction works would show woolly mammoth, biodiversity conservation and cloning,
   then two of the five keywords on 3 works, by best rank. Conservation ethics is one of those five.
   Before any change, compare the five shown with the coach's directions on one real search. Possible
   changes are showing more than five, or another order. This is for the PM, in E08.
3. **Topics.** Keywords miss one of the four directions (mourning), and topics miss it too. On the
   ruling's condition, the topics `--subject` step is not filed. The PM decides whether a partial
   miss that topics would not repair calls for it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-12

**Notes:**

Accepted. ac1, ac2 and the node pass, and the Goal is `Succeeded`.

* **The rulings are built as given.**
  * OpenAlex keywords only, into a provider-neutral `subjects`.
  * The counting rules, the order and the cap of five.
  * Apostrophe-safe commands, run through `sh` (and zsh where installed), with no command printed
    for a query that cannot be quoted safely.
  * Unusable keyword items are skipped. There is no `--within`.
* **The live measurement settles Q4.** The embedded shape is exactly `display_name`, `id` and
  `score`, as the fixture assumed, and the block printed subject names and counts only. On the
  de-extinction page, keywords carry three of the coach's four directions (ethics, ecology, the
  animal subject), and topics miss the fourth (mourning) as well. That is honest evidence for the
  keyword version.
* **The evidence is enough.** The red run against do-nothing skeletons had 30 of 45 new cases
  failing at assertions; the 46 existing OpenAlex failures were URL pins, expected from the new
  `select=`. All 18 mutants were caught. The five cases no mutant shows failing are explained.
  `subjects` is left out of a dump when empty, so stored and pinned shapes are unchanged.
* **Deviation 1 is the PM's.** The packages amendment (Q2) was held out of the 2026-11-12 batch so as
  not to collide with this branch's spec. The next batch adds `debate_core.integrations.discovery`
  and `tests/smoke`. Deviation 2 is as the 2026-11-05 amendment says.
* **The branch is behind dev** (e40-t44 and the PM batch merged since). Neither touches this task's
  files. If `scripts/task pr` asks, `scripts/task sync`.
* **The affected set** (581 files) goes to `ci` under agreement 10.
* **Follow-ups, into the next PM batch:**
  1. `search --within <saved file>`, as a local filter: a new E08 task at p3, as recorded here,
     including that a saved file must carry per-result `subjects`;
  2. whether the cap of five hides the coach's directions: a coach check on one real LD search after
     install, before any change;
  3. topics: not filed. The miss (mourning) is one topics would not repair, so the condition for the
     second step is not met.

`scripts/task pr`

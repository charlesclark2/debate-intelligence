# Session report: v1-e08-t14-da-links-name-the-plans-mechanism-in-the-united-states

| | |
|---|---|
| Task | `v1-e08-t14-da-links-name-the-plans-mechanism-in-the-united-states` — A disadvantage's link queries name the plan's mechanism and the United States |
| Spec | [`plan_specs/v1/e08-research-workflows/t14-da-links-name-the-plans-mechanism-in-the-united-states.yaml`](../../plan_specs/v1/e08-research-workflows/t14-da-links-name-the-plans-mechanism-in-the-united-states.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t14-da-links-name-the-plans-mechanism-in-the-united-states` |
| Session status | BLOCKED: waiting for the PM's ruling on the proposal (ac1) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The spec and the PM's context both ask for a proposal before any code, so this session has only the
proposal so far, [below](#proposal-for-the-pms-ruling). It answers the PM's five questions.

The recommendation, in short:
- **Fan-out at expansion time.** Every reviewed template stays byte-identical.
- **Where the new words go.** The NHI topic preset names four mechanisms and the country, taken from
  the landscape's aff positions and the resolution's own words.
- **Which DAs.** All five DAs (`kind: da`).
- **What a link search adds.** At most five queries, each naming the United States: one per mechanism
  and one on the resolution's words.

The politics DA's link search on NHI goes from 7 queries to 12. I wrote no code, and the Goal stays
`InProgress`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `da-links-name-the-plans-mechanism-in-the`: Mechanism links | Not started | Waiting for the PM's ruling on the proposal (ac1). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the PM rules on the proposal before any code, and the coach reviews the new templates (operator) | NOT RUN | The proposal is below. The PM's ruling comes first. The coach's review follows the build. |
| ac2: a DA's link need expands over the topic's mechanisms and names the United States, with the resolution's words kept, by expansion tests shown failing first | NOT RUN | Waiting for the ruling. |
| ac3: the operator repeats v1-e08-t05's Policy search and the coach labels it blind | NOT RUN | The operator runs it after the merge, on an installed build the PM schedules. |
| Node: `uv run pytest packages/debate_core/tests/application/test_query_expansion.py` | NOT RUN | Waiting for the ruling. |

## Proposal for the PM's ruling

What I measured, all offline, with scripts kept in the session scratchpad:
- `config/argument_taxonomy.yaml` 1.2.1, loaded by the real loader;
- the courier feed fixture, run through the feeds provider's own `query_terms` and `matches_terms`;
- `git diff HEAD origin/dev`, which showed no amendment to this spec.

I quote card text from no file, and every mechanism word below is a landscape label or the coach's
tag keyword.

### 1. Where the mechanisms come from

**Recommendation: the NHI topic preset in `config/argument_taxonomy.yaml` lists them.** Each entry
names the landscape's aff position by `landscape_id`. A test checks every id against
`config/landscape/taxonomies/policy-2026-27-nhi.yaml`: it must be a position there with `side: aff`.
The code never reads the landscape file, which is the rule v1-e08-t04 set.

Why not read the landscape's aff positions directly:
- **Too many positions.** The landscape has 24 aff positions, including `kritikal-aff` (no plan text),
  `nhi-aff` (the resolution itself), `degrowth-aff` and `nanomedicine-coverage-aff`. A fan-out needs a
  short ordered choice of them anyway.
- **Labels search badly.** The labels are heading names, such as "UCC", "Indigenous", "Resolutional
  NHI" and "ACA reform". Each mechanism needs a search phrase, which the coach edits.
- **Separate versions.** The landscape is versioned for counting. A landscape bump would otherwise
  change search queries without anyone reviewing them.

The NHI list I propose follows the spec's own four, in its order:

| Order | Landscape id | Landscape label | Search phrase | Where the phrase comes from |
|---|---|---|---|---|
| 1 | `single-payer-aff` | Single payer | `single payer` | The label |
| 2 | `medicare-for-all-aff` | Medicare for all | `Medicare for All` | The label, and the coach's tag keyword |
| 3 | `public-option-aff` | Public option | `public option` | The label, and the coach's tag keyword |
| 4 | `aca-reform-aff` | ACA reform | `Affordable Care Act` | The coach's tag keyword. The label's "ACA" is an acronym that also names other things. |

**Mechanisms the cap leaves out, for the coach to swap in:**
- single payer's other eight children: `global-budgets-aff`, `single-public-authority-aff`,
  `lower-payment-rates-aff`, `value-based-reimbursement-aff`, `disparate-impact-enforcement-aff`,
  `degrowth-aff`, `prescription-drug-coverage-aff` and `nanomedicine-coverage-aff`
  (`medicare-for-all-aff` is the ninth);
- the other affs, such as `medicaid-expansion-aff`, `ucc-aff` and `tiered-nhi-aff`.

`nhi-aff` is covered by the resolution's own queries. `kritikal-aff` has no plan text to link to.

The phrases follow two rules: no digits, so the coach's `3069` keyword is out, and no card text.

### 2. How the United States is anchored

**Recommendation: a word in the query, on the added queries only. No provider filter.**

The resolution is "The United States federal government should establish national health insurance in
the United States." The preset gains `country: United States` as a variable. The existing test checks
every preset variable word for word against `topics.yaml`'s resolution, so it covers this one too.

Every added query ends with the country, unless it already names it. The reviewed queries are asked
exactly as today, without it.

What each choice does to recall on the recorded fixtures:
- **A word on every query, the reviewed ones included, costs feed recall.** The feeds provider keeps
  an entry only when every query word is in its title or snippet. On `courier_politics.xml`, the
  politics DA's seven link queries for `health insurance` match one item today ("Health insurance
  fight costs the president political capital"). With `United States` appended they match none.
  Anchoring only the added queries keeps that one item, because the reviewed seven are unchanged. The
  added queries match no fixture item with the anchor or without it.
- **A word in an OpenAlex query: the fixtures cannot measure it.** The recorded OpenAlex transport
  answers every `/works` request with the same body, whatever the query. The recall change can only
  be measured live, which is ac3. I have not checked how OpenAlex's `search=` combines words. That
  would be a live documentation read, which goes to the operator, and the coach's labels answer the
  question that matters anyway.
- **An OpenAlex filter: not recommended for this task.** The filter would be by author country,
  something like `authorships.countries:US` (the exact name is unverified, for the same reason).
  - It filters by where the authors work, not by what the work is about. It would drop a Canadian
  scholar on US single payer and keep a US author on South Africa's NHI.
  - It needs a new `SearchFilters` field, which changes the stored `Search` schema.
  - It needs an adapter change in `debate_core.integrations`, outside this task's packages.
  - It does nothing for feeds.
  - The fixtures cannot show what it drops, because the server applies it.

  If ac3 still shows foreign NHI, the filter is a follow-up for E07.

### 3. The fan-out's size

**Recommendation: the preset names at most 4 mechanisms, and the loader refuses more.** A DA's link
search adds, in order:
1. one query on the resolution's words: the DA's first link template that renders on `{query}` and
   `{topic}`, filled with the topic's value, plus the country;
2. one query per mechanism, from the same template with `{query}` and `{topic}` filled with the
   mechanism's phrase, plus the country.

That is at most five added queries. Every DA's first link template renders on `{query}` and `{topic}`
alone today. Each added query uses the need's window (link: 1,826 days).

Queries per search, with `--topic policy-2026-27-nhi`, and OpenAlex searches a day without a key. The
daily figures use v1-e08-t05's estimate of about 100 OpenAlex requests a day, one request per query
until v1-e08-t10 lands.

| DA link search | Today | Recommended (first template) | First two templates | Every link template |
|---|---|---|---|---|
| `politics-da` (7 link templates) | 7, ~14 a day | **12, ~8 a day** | 17, ~5 a day | 42, ~2 a day |
| `midterms-da`, `economy-da`, `spending-da`, `federalism-da` (2 each) | 2, ~50 a day | **7, ~14 a day** | 12, ~8 a day | 12, ~8 a day |

The figures are 100 divided by the query count, rounded down: 100/7, 100/12, 100/17, 100/42, 100/2 and
100/7.

A search without `--topic`, or on a preset with no mechanisms, adds nothing. So does a need other
than link, or an argument that is not a DA (advantages, kritiks). Every search except a DA's link
search on a preset with mechanisms is therefore unchanged.

**What the ac6 search would ask** (`"national health insurance" --argument politics-da --need link
--topic policy-2026-27-nhi`), recommended option:

| Queries | Text |
|---|---|
| The reviewed 7, unchanged | `national health insurance political capital`, `… partisan fight Congress`, `… unpopular with voters`, `… popular with Republicans`, `… unpopular with Republicans`, `… popular with Democrats`, `… unpopular with Democrats` |
| Added 5 | `national health insurance political capital United States`, `single payer political capital United States`, `Medicare for All political capital United States`, `public option political capital United States`, `Affordable Care Act political capital United States` |

The first-template choice puts the politics DA's mechanism links on political capital alone. The
party-popularity links ("unpopular with Republicans") are not crossed with the mechanisms. That is
the price of the cap, and the coach's review is where to change it. Moving another template first
would change a reviewed entry, which puts it back to `awaiting_coach_review`.

### 4. The coach-reviewed guard

**Recommendation: the fan-out runs at expansion time, and no reviewed entry changes.**

The guard is `test_the_committed_taxonomy_keeps_every_coach_reviewed_entry_as_he_reviewed_it`. It
compares each reviewed argument entry whole, and the DA family's needs, with
`coach_reviewed_1_2_1.yaml`. It does not read the topic presets.

The new text lives in the NHI preset: `country` and the `mechanisms` list. The preset gets
`review: awaiting_coach_review` of its own, so the coach's sign-off is recorded in the file as it is
for arguments.

Why not the other route:
- **It would need new templates on the DA entries.** That means a `{mechanism}` variable on politics,
  midterms, economy, spending and federalism.
- **Those five entries would go back to `awaiting_coach_review` whole.** Their reviewed uniqueness,
  internal link, impact and answers templates would lose the guard until he reviews again.
- **He would review five sets of near-duplicate templates.** Here he reviews one list and one rule.

The 17 entries awaiting his review from v1-e08-t08 are untouched. The taxonomy goes from 1.2.1 to
1.3.0, a minor bump, because the preset gains new fields.

The guard's fixture is refreshed only after the coach reviews. The preset is not guarded until then.

### 5. The resolution's words stay a query

Both ways the forbidden entry could be read are met:
- The reviewed queries are asked as today, built on what the debater typed. In ac6 that was the
  resolution's words.
- The added resolution query is built on the topic's value ("national health insurance") whatever was
  typed. A test pins that one query holds the topic's value word for word.

### What the build would change (after the ruling)

- **`domain/argument_taxonomy.py`:** `TopicPreset` gains `mechanisms` (id, label, phrase, at most 4,
  no digits, unique) and `review`, and the taxonomy declares the `country` variable.
- **`application/query_expansion.py`:** the fan-out in `expand_with_templates`. Added queries are
  recorded with template ids such as `politics-da/link/1/medicare-for-all-aff` and
  `politics-da/link/1/resolution`.
- **`domain/search.py`:** an optional `ExpandedQuery.mechanism` (the landscape id), left out of the
  JSON when it is unset, so every other search serializes as before. This changes
  `schemas/search.schema.json`, which is outside the listed packages, as in v1-e08-t04.
  The alternative is to keep the mechanism in the template id alone, with no schema change.
- **`config/argument_taxonomy.yaml`:** the NHI preset's new fields and 1.3.0. The ac2 example test
  pins the taxonomy version, so that pin moves.
- **Tests, shown failing first against a skeleton with the fan-out off:**
  - every DA's link need on the NHI preset, with expected queries written by hand;
  - the reviewed queries unchanged;
  - no fan-out without a preset, for an advantage or a kritik, or for any other need;
  - the cap refusal;
  - the landscape-id check;
  - the stored search's record;
  - a CLI test that OpenAlex is asked the 12 queries.
- **Not touched:** `commands/search.py` (v1-e08-t06's), and the 17 entries still awaiting review.

## Questions for the PM

```text
v1-e08-t14 proposal (session of 2026-11-04). No code yet; the build starts on your ruling.

1. Where the mechanisms come from.
   A. The NHI topic preset in config/argument_taxonomy.yaml lists them, each with the landscape aff
      id it stands for (checked by a test against config/landscape/taxonomies/policy-2026-27-nhi.yaml,
      side aff) and a search phrase (recommended). The code still never reads a landscape file; the
      landscape has 24 aff positions whose labels are headings ("UCC", "Resolutional NHI"), so a short
      ordered list with search phrases is needed either way, and a landscape bump cannot silently move
      search queries.
   B. Read every aff position from the landscape file at expansion time, label as phrase: 24 positions,
      including kritikal-aff and nhi-aff, so it needs a filter and a cap anyway.
   NHI list for A, in the spec's order: single-payer-aff "single payer", medicare-for-all-aff
   "Medicare for All", public-option-aff "public option", aca-reform-aff "Affordable Care Act" (the
   coach's tag keyword; the label's "ACA" also names other things). Single payer's other eight
   children and the other affs are left for the coach to swap in.

2. The United States anchor.
   A. The preset gains country: United States (the resolution's own words, checked by the existing
      word-for-word test), appended to every ADDED query only; the reviewed queries are asked exactly
      as today (recommended). On the recorded courier feed fixture, the politics link queries for
      "health insurance" match 1 item today; with "United States" appended to them they match 0
      (feeds keep an entry only when every word is in it); A keeps the 1. The OpenAlex fixture
      answers every query alike, so its recall change is ac3's to measure.
   B. Append it to every query, the reviewed ones included: costs the feed match above.
   C. An OpenAlex author-country filter as well: filters by where authors work, not what the work is
      about; needs a stored SearchFilters field and an adapter change outside this task's packages;
      nothing for feeds. Recommended as an E07 follow-up only if ac3 still shows foreign NHI.

3. Fan-out size. A preset names at most 4 mechanisms (the loader refuses more). A DA's link search
   on it adds one query per mechanism plus one on the resolution's words, each from the DA's first
   link template that renders on {query}/{topic}, plus the country: at most 5 added.
   politics-da link: 7 queries today -> 12 (A, recommended), 17 (first two templates), 42 (every
   template). The other four DAs: 2 -> 7, 12, 12. On t05's estimate of ~100 keyless OpenAlex requests
   a day, one per query until t10: politics link ~14 searches a day today -> ~8 (A), ~5, ~2.
   The cost of A: the politics mechanism links are political capital only, not the party-popularity
   templates; the coach can say otherwise at his review.

4. The coach-reviewed guard.
   A. Fan-out at expansion time; no reviewed entry changes; the new words (country, mechanisms) live
      in the preset with its own review: awaiting_coach_review; taxonomy 1.2.1 -> 1.3.0; the guard's
      fixture is refreshed only after his review (recommended).
   B. New {mechanism} templates on the five DA entries: all five go back to awaiting_coach_review
      whole, so their reviewed uniqueness, impact and answers templates lose the guard until he
      reviews again.

5. Two smaller choices.
   a. Record a mechanism query's landscape id in an optional ExpandedQuery.mechanism (exclude_if
      unset, so other searches serialize as before; regenerates schemas/search.schema.json, outside
      the listed packages) (recommended), or only in its template id
      (politics-da/link/1/medicare-for-all-aff), with no schema change.
   b. DAs only, as the spec says (recommended), or advantages' link need too (an aff advantage's link
      is the plan's mechanism as well).

Not touched either way: commands/search.py (v1-e08-t06), and the 17 entries awaiting the coach
from v1-e08-t08.
```

## Files changed

- `docs/session-reports/v1-e08-t14-da-links-name-the-plans-mechanism-in-the-united-states.md`: this
  report, with the proposal.

## Deviations from the spec

None so far.

## Decisions and assumptions

- **"Every DA" means `kind: da`.** Those are `politics-da`, `midterms-da`, `economy-da`, `spending-da`
  and `federalism-da`. Advantages are a question for the PM (question 5b).

## Operator follow-ups

None yet. The blocks for ac3 (search, blind sheets, key) are written after the build, in the form
v1-e08-t05's were. They run on an installed build carrying the merge, which the PM schedules, not
before Thursday's v1-e31-t32 copy. Nothing is handed over today, the cloud run's day.

## Follow-up work

- **An OpenAlex author-country filter (E07)**, if ac3 still shows other countries' national health
  insurance (question 2C).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

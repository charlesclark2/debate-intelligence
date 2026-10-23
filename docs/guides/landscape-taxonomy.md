<!-- docs-index: For coaches: editing the position taxonomies a landscape report counts against, and seeding a new one -->
# Landscape taxonomies: a guide for coaches

A **landscape report** says what a caselist's teams are reading: which plans, which DAs, CPs, Ks, T
and theory, by how many teams. It counts against a **position taxonomy**, a list of positions you
keep in YAML. Each position lists the **aliases** it is read under: headings as teams write them,
reduced to one plain form. A report finds each pocket, hat or block heading in a disclosed file,
reduces it the same way, and counts the file under the position that claims it.

Where things are:

| What | Where |
|---|---|
| Which topic each caselist snapshot is on | [`config/landscape/topics.yaml`](../../config/landscape/topics.yaml) |
| A topic's positions | `config/landscape/taxonomies/<topic id>.yaml`, e.g. [`policy-2026-27-nhi.yaml`](../../config/landscape/taxonomies/policy-2026-27-nhi.yaml) |
| Positions every topic of an event shares: generic Ks, framework, theory | [`config/landscape/taxonomies/generic.yaml`](../../config/landscape/taxonomies/generic.yaml) |
| The check every edit must pass | [`tests/config/test_landscape_taxonomies.py`](../../tests/config/test_landscape_taxonomies.py) |
| The models, the source of truth if this page and they disagree | `debate_core.domain.landscape` and `debate_core.integrations.landscape.yaml_taxonomy_repository` |

Matching headings to positions in a report is `v1-e32-t02`; the report itself is `v1-e32-t03`; the
`debate-research landscape` command is `v1-e32-t05`. This page is about the files (`v1-e32-t01`).

## A position

```yaml
  - id: states-cp
    label: States CP
    kind: cp
    side: neg
    aliases: [states cp, cp states, states counterplan]
```

| Field | What it is |
|---|---|
| `id` | Lowercase words joined by hyphens. Permanent: see [Ids are forever](#ids-are-forever) |
| `label` | The name debaters use, as a report prints it. Sentence case: `Court clog DA`, not `Court Clog DA` |
| `kind` | `aff`, `advantage`, `da`, `cp`, `k`, `t`, `theory`; for LD and PF also `value`, `criterion`, `contention`, `response` |
| `side` | `aff`, `neg` or `both`. In PF, pro is `aff` and con is `neg` |
| `parent` | Optional. The id of the position this one belongs to, such as an advantage's aff |
| `aliases` | The headings it is read under, in normalized form ([below](#an-alias-is-a-normalized-heading)) |
| `tag_keywords` | Optional. Words its card tags tend to carry, for the matcher's second look |
| `description` | Optional. A sentence for you; never card text |
| `events` | `generic.yaml` only: the events the position applies to, e.g. `[POLICY]` |
| `deprecated`, `merged_into` | How a position is retired ([below](#retire-or-merge-a-position)) |

A topic file has at least twelve positions that are not retired, and so does `generic.yaml`.

## An alias is a normalized heading

Teams write one position many ways: `1NC — Spending DA Shell`, `2. spending DA`, `OFF---1NC`. Before
a heading is matched it is reduced to lowercase words of letters and digits: numbering, round names
(`1NC`, `2AR`), `Shell`, `Block`, `Off`, versions (`v2.0`), opponents (`vs ...`), tournament and
round labels are taken off, and `AT:`/`A2` is noted as an answer to the position rather than a
reading of it. So `1NC — Spending DA Shell` and `AT: Spending DA` are both `spending da`, and one
alias catches both. An alias is always written in that reduced form. To see what a heading reduces
to, run this in the repository, with your heading in the quotes:

```bash
uv run python -c "from debate_core.arguments.landscape.headings import normalize_heading; print(normalize_heading('1NC — Spending DA Shell'))"
```

It prints `NormalizedHeading(text='spending da', answer=False)`; `spending da` is the alias.

Two positions of one topic never share an alias, retired ones included, because a heading must lead
to one position. `generic.yaml` counts too: an alias it gives a Policy position cannot also be in the
Policy topic's file.

## What an alias may not hold

No team code, school or person's name, anywhere in these files. The check refuses:

* an alias with a two-letter word that is not debate vocabulary (`spending da qx` reads as a team's
  initials). A real two-letter word goes in the check's `SHORT_WORDS` in the same change;
* a label with a team-code shape (`QX`, `RiOs`) or a capitalized word after its first (`Spending DA
  Avery Quinlan` reads as a name);
* `school`, `high`, `academy`, `prep` and similar words in any field.

Aliases come from headings **at least two teams used**, or from you. A heading only one team wrote
can point at that team, so it is never seeded as an alias. Add one yourself only when you know it is
an ordinary name for the position.

## Check your edit

Every edit is checked by one command, which takes a second:

```bash
uv run pytest tests/config/test_landscape_taxonomies.py
```

A mistake fails it with the file and the problem named, for example
`config/landscape/taxonomies/policy-2026-27-nhi.yaml: ... the alias 'courts cp' is claimed by
courts-cp and nhs-cp`. The same checks run on every pull request.

## Worked examples

### Add an alias

Teams start writing `fed cp` for the States CP. Check the reduced form, then add it to the list:

```yaml
  - id: states-cp
    label: States CP
    kind: cp
    side: neg
    aliases: [states cp, cp states, states counterplan, fed cp]
```

Bump `taxonomy_version` (a minor bump, [below](#bump-taxonomy_version)).

### Add a position

A new DA shows up in the review sheet's unplaced headings, say `medicaid da`. Add it with an id
that has never been used in this file:

```yaml
  - id: medicaid-da
    label: Medicaid DA
    kind: da
    side: neg
    aliases: [medicaid da, da medicaid]
```

### Split a DA

`economy-da` turns out to hold two arguments: a recession DA (`econ da`, `da econ`) and a stock
market DA (`economy da stocks`). The old id still names one of them, so keep it for that half and
add a new position for the other, moving its aliases:

```yaml
  - id: economy-da
    label: Economy DA
    kind: da
    side: neg
    aliases: [econ da, da econ, economy da, da economy]

  - id: economy-stocks-da
    label: Economy DA (stocks)
    kind: da
    side: neg
    aliases: [economy da stocks]
```

If neither half is what the old label meant, retire the old position (`deprecated: true`, no
`merged_into`, since it went two ways) and add two new ones. Earlier reports keep the old id; later
ones count the new two.

### Merge two K labels

`cap-k` and `capitalism-k` are one K. Keep `cap-k`, move the other's aliases to it, and retire the
other into it:

```yaml
  - id: cap-k
    label: Cap K
    kind: k
    side: neg
    events: [POLICY]
    aliases: [cap k, k cap, capitalism k, k capitalism]

  - id: capitalism-k
    label: Capitalism K
    kind: k
    side: neg
    events: [POLICY]
    deprecated: true
    merged_into: cap-k
```

An alias may stay on the retired position instead of moving, but never on both.

### Retire or merge a position

* **Retire** a position nobody reads any more: `deprecated: true`. It stays in the file.
* **Rename** one: retire the old id with `merged_into: <new id>` and add the new one. A label alone
  can change without a new id, as long as it still names the same argument.
* **Merge** two: retire one with `merged_into: <the other>`, as above.

`merged_into` and `parent` must name a position in the same file, a merged position must be
`deprecated: true`, and merges may not go round in a circle.

## Ids are forever

A report classified under one version must mean the same thing under the next, so an id is never
deleted and never reused for a different argument, even after it is retired. Retire it instead. A
renamed position gets a new id; the old one points at it with `merged_into`.

## Bump `taxonomy_version`

Every released edit bumps the version, `MAJOR.MINOR.PATCH`, in **two** places: the topic file's
`taxonomy_version` and that topic's `taxonomy_version` in `topics.yaml`. The check refuses the two
when they disagree, so a report always says which version it counted under.

| Change | Bump | Example |
|---|---|---|
| Wording that moves no count: a label, a description, tag keywords | Patch | `1.0.0` → `1.0.1` |
| Anything that can move a count: an alias added or removed, a position added, split, merged or retired | Minor | `1.0.0` → `1.1.0` |
| A rebuild: re-seeding the topic, or a new resolution under the same topic id | Major | `1.1.0` → `2.0.0` |

An edit to `generic.yaml` bumps its own version, and also the version of every topic of the events
the edited positions name, in its file and in `topics.yaml`, since that topic's counts move too.

## The topic map

`topics.yaml` lists each topic with its event, the resolution exactly as you gave it (or nothing,
until you do), its `taxonomy_version` when it has a taxonomy, and the caselist date ranges it covers.
Both ends of a range are included, and two ranges of one caselist may not overlap, so every snapshot
is on one topic or none. LD and PF change topic during a season: a new topic is a new entry with
its own range, and the old one keeps its range so that earlier snapshots still resolve. A topic with
no `taxonomy_version` has no taxonomy file, and a report on it says so.

## Seeding a new taxonomy

A taxonomy is seeded, not invented. For a new topic, the operator runs the seeding script over the
caselist's parsed store, on the Mac that holds it. It reads only, takes under a minute for a whole
Policy season, and writes a CSV of normalized headings with their document and team counts and a
suggested position for each, leaving out every heading fewer than two teams used. The CSV holds real
headings, so it lives outside the repository (the script refuses a path inside it) and is never
committed.

The topic must be in `topics.yaml` first, with its range for the caselist. Then, from the
repository, check that no `DEBATE_` override is set and no caselist pull is running; the first
command prints nothing when both are true:

```bash
env | grep '^DEBATE_'; pgrep -fl 'debate-research( --json)? caselist pull'
```

```bash
uv run python scripts/seed_landscape_taxonomy.py candidates --topic policy-2026-27-nhi --out ~/Documents/debate/landscape-seed/policy-2026-27-nhi-candidates.csv
```

Its last line names how many sources it read and how many candidate rows it wrote, and both must be
above zero. A run that reads no source, or writes no candidate, says `FAILED` and writes nothing.
With a draft taxonomy committed, the review sheet sets each position beside the counts behind its
aliases, then lists the headings most teams use that no position claims:

```bash
uv run python scripts/seed_landscape_taxonomy.py review --topic policy-2026-27-nhi --candidates ~/Documents/debate/landscape-seed/policy-2026-27-nhi-candidates.csv --out ~/Documents/debate/landscape-seed/policy-2026-27-nhi-review.md
```

In the sheet, `aff` and `neg` are the sides the teams disclosed the files on, not the side that reads
the position: an aff file's block answering a DA is titled with the DA and counts as aff.

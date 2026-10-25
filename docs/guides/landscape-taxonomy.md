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
| Your decisions on headings the matcher could not place | `config/landscape/overrides/<topic id>.yaml`, written for you from the review queue ([below](#the-review-queue-and-your-decisions)) |
| When a plan text that names no aff names the resolutional aff | `config/landscape/plan_texts/<topic id>.yaml`, e.g. [`policy-2026-27-nhi.yaml`](../../config/landscape/plan_texts/policy-2026-27-nhi.yaml) ([below](#the-resolutional-plan)) |
| The ids published reports have released, which no edit may delete or change | [`config/landscape/released.yaml`](../../config/landscape/released.yaml), written for you ([below](#released-ids-and-the-lock-file)) |
| The checks every edit must pass | [`tests/config/test_landscape_taxonomies.py`](../../tests/config/test_landscape_taxonomies.py) and [`tests/config/test_landscape_released_ids.py`](../../tests/config/test_landscape_released_ids.py) |
| The models, the source of truth if this page and they disagree | `debate_core.domain.landscape` and `debate_core.integrations.landscape.yaml_taxonomy_repository` |

Matching headings to positions in a report is `v1-e32-t02`; the report itself is `v1-e32-t03`; the
`debate-research landscape` command is `v1-e32-t05`. This page is about the files (`v1-e32-t01`) and
the review queue that matching leaves for you (`v1-e32-t02`).

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

Every edit is checked by one command, which takes a few seconds:

```bash
uv run pytest tests/config
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

## Released ids and the lock file

An id is *released* once a report counted under its version has been published. From then on the
check holds it to the rule above. [`config/landscape/released.yaml`](../../config/landscape/released.yaml)
records, for each topic and each released version, every position id with its kind and side, and a
*digest* of the positions: a sha256 of every field of every position, so any edit shows, but no text.
That covers retired positions, and generic.yaml's positions for the topic's event, since the report
counted those too. It holds nothing else: no labels, no counts. Until the first report is published
it is empty (`releases: []`), and every edit passes.

Against that file, `tests/config/test_landscape_released_ids.py` refuses, naming the file, the id
and the rule:

| Refused | What to do instead |
|---|---|
| A released id is missing from the file | Put it back and retire it: `deprecated: true`, with `merged_into` if it was renamed or merged |
| A released id's `kind` or `side` changed | Put it back as it was, retire it, and add a new id for the different argument |
| The file is at a released version, and anything in its positions differs from that version's: an id, a kind or side, an alias, a label, a tag keyword, in the topic's file or in generic.yaml | Bump `taxonomy_version`, in the file and in `topics.yaml` |
| The file's version is below one already released | Bump it past the released one |
| A `merged_into` names a retired position | Point it at the position the argument is counted under now |

A label may change: a rename that still names the same argument keeps its id. At a released version
it is an edit like any other, so it comes with a patch bump, as [the table below](#bump-taxonomy_version)
says. When the check finds a changed digest it cannot say which position changed, so it names the
topic's file "with generic.yaml merged in": look at `git diff` of both.

### When the operator writes it

The operator writes the lock **when a report under a new `taxonomy_version` is first published**,
that is, right after the first `debate-research landscape report --publish` whose report shows a
version the lock does not have yet. The version is the `Taxonomy version` row at the top of
`report.md`, and `taxonomy_version` in the command's `--json` output. Run it in a worktree up to
date with `dev`, with the topic id and that version:

```bash
uv run python scripts/release_landscape_taxonomy.py --topic policy-2026-27-nhi --version 1.1.0
```

It prints `Released policy-2026-27-nhi 1.1.0: N position ids written to ...`, where N is above
zero. It reads the committed files in `config/landscape/` and nothing else. It refuses, writing
nothing, when the topic's file is not at exactly that version (so a lock written late cannot record
a later edit), when that version is already in the lock, and when the files already break a
released id. Then check the files and look at what changed:

```bash
uv run pytest tests/config
git diff config/landscape/released.yaml
```

The diff adds one release, with the topic's ids. Commit `released.yaml` in the next PM batch or the
next task's pull request. A weekly report under a version that is already released needs nothing.

**The first published report** is `v1-e32-t05`'s first `--publish`, of the Policy topic at 1.1.0.
This check (`v1-e32-t08`) merges into `dev` before that publish (the PM's ruling of 2026-10-24). Right
after the publish, `v1-e32-t05`'s operator runs the command above for 1.1.0, exactly as written, runs
the two checks, and the lock is committed in a PM batch. Do it before any later edit bumps the file
(the mechanism child affs of `v1-e32-t09` come as 1.2.0 or later), because the command refuses a
version the file has moved past. `v1-e32-t05` merges after `v1-e32-t08`, so it adds this step to its
own first-publish instructions.

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

## How a card is placed

Matching uses no model. For each card it reads the headings above it, outermost first, each reduced
the way an alias is written, and:

1. **The nearest heading that names a position places it.** Your decision on a heading (an override)
   is read first, then the aliases. A card under `Spending DA` > `Link` counts under the Spending DA,
   because `link` names nothing and `spending da` is the nearest heading above it that does.
2. **Under an `AT:` or `A2` heading it answers the position** rather than reading it, and a report never
   counts an answer as a read. That holds for everything under an answer heading too: `AT: DAs` >
   `Spending DA` answers the Spending DA. An `AT:` block *below* the position (`Spending DA` >
   `AT: Link Turn`) is the reading team's own block and still reads it.
3. **Tag keywords split a position into its children.** When a position has children with
   `tag_keywords` (an aff split by mechanism, say), a card under the parent goes to the child whose
   keyword its tag holds, and stays with the parent when no child's does, or when two do.
4. **A heading that matches nothing stays unplaced.** It is never guessed into the nearest-looking
   position, and a card under nothing but such headings goes to the review queue.

## How an affirmative round's aff is identified

Headings name the plan in under a fifth of Policy affirmative files, so the report does not rely on
them for the aff. Each affirmative round gets its aff from the first of these that says it, and the
report shows which one did:

1. **Its plan text** (`PLAN_TEXT`). The paragraph directly under a heading or label such as `Plan`,
   `Plan Text` or `PT`, or a `Plan:` line holding the text itself, names an aff when it holds one of
   that aff's aliases or tag keywords. A child named with its parent counts as the child; two affs
   named together, two children of single payer included, count as neither. A paragraph that only
   looks like a plan text, with no label above it, identifies nothing, and neither does a text whose
   `should` has no federal actor before it (`The fifty states ... should`): that is a counterplan
   under a plan label, not the team's plan. A plan text that names no aff can still name the
   resolutional aff ([below](#the-resolutional-plan)).
2. **A card the matcher placed under an aff** in that round (`PLACED_CARD`), as for any position.
3. **The team's other rounds** (`TEAM_CARRY`). When every identified round of a team names one aff,
   its other affirmative rounds count under it too, but only rounds whose files hold no plan text of
   their own. A round whose plan text names something else, or no aff at all, is never carried into,
   and a team whose rounds name two affs carries nothing.

A round none of these identifies is counted as unidentified. The caselist's own round titles and cite
entries are not read: this project does not take them from the site this season.

Reading a plan text means opening the file again, since the parsed card store keeps cards only, so
what is read is kept beside the classification cache, at
`~/.debate-research/dev/landscape/plan_texts/<caselist>.jsonl`: where each plan text is, digests and
the aff ids it names. Never its words. Adding an alias or tag keyword to an aff makes the next run
read every affirmative file again (a few minutes on the Mac that holds the store).

## The plan-text sheet and your mechanisms

The plan-text sheet lists what plans teams read, grouped by the words that tell one plan text from
another. Words nearly every plan text shares (`united states federal government should establish`,
and the like) are left out as the frame. Each group shows its commonest plan text word for word, with
how many of its files hold it exactly, and a group one team reads is listed too (data-use policy 1.13).
No school or team is named beside a text, and a plan text that names a school is not shown. The
operator writes it outside the repository; it will not replace an answers file you have begun:

```bash
uv run python scripts/assign_landscape_affs.py sheet --caselist hspolicy26 --out ~/Documents/debate/landscape-seed
```

That writes `policy-2026-27-nhi-plan-texts.md` and `plan-text-answers.csv` there. For each cluster that
is a mechanism of single payer, fill the CSV's two last columns:

| Column | What to write |
|---|---|
| `mechanism_name` | A short name in sentence case, e.g. `Payroll levy` |
| `tag_keywords` | Words that mark the mechanism in a plan text or a card's tag, separated by `;`, e.g. `payroll levy; payroll tax` |

Leave both blank to keep a cluster under its aff. Each named mechanism becomes a child aff of single
payer in the taxonomy file with your keywords, and the version is bumped (a minor bump: new positions).
The next run reads every affirmative file again and counts rounds under the child their plan text
names. Your keywords also refine cards placed under single payer by their tags, as rule 3 above says.
Commas between keywords work as well as `;`.

**Your answers of 2026-10-24 are in taxonomy 1.2.0** (`v1-e32-t09`):
* nine mechanisms of single payer, as its children;
* thirteen other affs, with the ids you wrote in `aff_named`, such as `public-option-aff`.

A child's id is its mechanism name in kebab case plus `-aff`, such as `global-budgets-aff`. Each
label is your mechanism name in sentence case, because the configuration check reads a capital
after the first word as a person's name. Each position has your keywords and no alias. A cluster
you marked `none` gets no position.

### The resolutional plan

Every plan says "national health insurance", so `nhi-aff` has no keywords. Instead, a plan text with a
federal actor that names no aff names `nhi-aff` when every word of it is either:
* an English joining word (`the`, `of`, `in` and the like);
* one of the topic's **frame words**: those in at least 80% of the sheet's plan texts;
* one of its **resolutional words**: those of the clusters you marked `nhi-aff`.

`nhi-aff` is the least specific aff: when a file's plan texts, a round's files or a team's rounds name
it and exactly one other aff, they count as that other aff, and `nhi-aff` never makes a conflict.

A plan text with one other word stays unnamed. A text that writes `USFG` is an example, because
`usfg` is in neither list. Both lists are in `config/landscape/plan_texts/<topic id>.yaml`, one
lowercase word each. Adding a word is a configuration edit like an alias: `uv run pytest tests/config`
checks it, and the next run reads every affirmative file again. The words come from teams' plan
texts, so the check refuses one shaped like a team code or naming a school, as it does for an alias.

## CP texts, alternatives, roles of the ballot and overviews

The report quotes each CP's and each K's texts word for word, and counts each position's overviews.
They are the teams' own analytic words, read from each file's paragraphs, so the store's cards do not
hold most of them. A text belongs to the position its section is placed under: the nearest heading over
its label that an alias or your decision places, as a card is placed. A label under `1NC` or `OFF`, or
under headings that place nothing, is counted and never placed by a guess, so an alias or a decision you
add for such a heading places its texts too.

* **A CP text** is the paragraph a label holds or opens: `Text:`, `CP Text:`, `Counterplan:`, or a
  `Text` or `CP Text` heading over it. It holds `should`. Most teams write it with no label, so the
  first analytic with `should` in a block placed under a CP is its text too, when an **actor** is among
  the at most 12 words before its `should`: "The fifty states should ..." is a text, and "Our counter
  interpretation is that we should ..." is not.
* **An alternative** is a tag or analytic opening `The alternative is`, `The alt is` or `Our alternative
  is`, or the one under an `Alt` or `Alternative` heading. `Alt causes`, `Alt fails` and `Perm do the
  alt` answer an alternative, and are left out.
* **A role of the ballot** is under a `Role of the ballot`, `ROB`, `Role of the judge` or `ROJ` heading,
  or opens `The role of the ballot is`. A `Ballot` heading on its own is left out: it also heads
  ballot-PIK and presumption blocks.
* **An overview** is a heading `Overview`, `O/V`, `OV` or `OVW`, alone or with other words (`Impact
  overview`). Overviews are counted, never quoted: the data-use policy does not list them, and you
  decided on 2026-10-24 to keep it so.

Each CP and K shows its 3 texts the most teams read, then how many more texts and teams there are.
Texts worded alike are one text. A text naming a school of the caselist is withheld and counted.

The actors are in `config/landscape/analytic_texts/<topic id>.yaml`, one lowercase phrase each and no
`the` (`fifty states`, `usfg`, `congress`). Adding one is a configuration edit like an alias: `uv run
pytest tests/config` checks it, and the next run reads every file of the topic again, once (551
seconds for hspolicy26's first reading, on 2026-10-24). An edit to a position or a decision of yours
reads them again too, because a text's position is kept with it.

So after an edit to the taxonomy, your decisions or the actors, run the fill on its own first,
`uv run python scripts/read_landscape_texts.py --caselist <caselist>`, then the dry run and the
publish. A dry run writes no cache, so without the fill first the dry run and the publish would each
read every file again (the PM's ruling of 2026-10-24 on v1-e32-t11's question 4).

## The review queue and your decisions

Each run writes a review queue: the headings that cards nothing placed sit under, one row each, with
how many documents, teams and cards are under it and up to three candidate positions (positions
whose aliases share a word with it). It holds headings teams wrote, so it is kept on the Mac that
holds the store, at `~/.debate-research/dev/landscape/review/<caselist>/<topic id>-review-queue.csv`,
never in the repository. A heading fewer than two teams used is left out of it.

Your first pass over the Policy queue happens before the first `debate-research landscape report`
run (`v1-e32-t05`), which applies your decisions, so the first report counts with them.

To decide, copy the CSV somewhere outside the repository, open it in a spreadsheet and fill the last
column, `decision`, for the rows you want to settle:

| Write in `decision` | When |
|---|---|
| A position id, e.g. `pharma-da` | The heading names that position. Every card under it counts there next run |
| `none` | The heading names no position: a block label such as `link`, `impact` or `solvency`. It stops coming back to the queue, and cards under it still count under a heading above it |
| Nothing | You have not decided. The row comes back next run |

Then the operator applies the file, which writes `config/landscape/overrides/<topic id>.yaml` and
refuses an id the taxonomy does not have before writing anything:

```bash
uv run python scripts/classify_landscape_positions.py apply-decisions --topic policy-2026-27-nhi --decisions ~/Documents/debate/landscape-review/policy-2026-27-nhi-decisions.csv
```

The overrides file is checked like a taxonomy file (`uv run pytest tests/config`), including for team
codes and school names, since a decision copies a heading teams wrote into the repository. A heading
that names a school or a team, by any form, gets no decision: leave it blank. A decision changes
counts from the next run without a `taxonomy_version` bump.

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

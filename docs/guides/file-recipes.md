<!-- docs-index: For coaches: writing a file recipe, the YAML that names the cards and headings of an evidence file to build -->
# File recipes: a guide for coaches

A **file recipe** is a short YAML file that describes one evidence file: its title and what it is
for, its pockets, hats and blocks, and the cards and analytics under each block, in order. You name
each card by its **fingerprint**; you never paste a card. The file builder copies every card's cite
and evidence from the file it was disclosed in, run for run, so what reaches the built file is
exactly what the source held.

Where things are:

| What | Where |
|---|---|
| Your recipes | The evidence workspace, `<data dir>/files/recipes/<topic>/<name>.yaml`, where `files suggest` writes its drafts. Never in the repository |
| Built files | `<data dir>/files/built/<topic>/<name>.docx`, with its `.provenance.json`, `.quality.json` and `.quality.md`. Never in the repository |
| The published schema, for an editor that checks YAML as you type | [`docs/data/file-recipe.schema.json`](../data/file-recipe.schema.json) |
| The three synthetic examples below | [`tests/fixtures/file_builder/recipes/`](../../tests/fixtures/file_builder/recipes/) |
| The models, the source of truth if this page and they disagree | `debate_core.domain.file_recipe` and `debate_core.application.file_recipes` |

Building a file from a recipe is `debate-research files build <recipe>` (`v1-e33-t03`), which writes
the `.docx`, its provenance sidecar and its quality report, and `files check <file>` checks a built
file again. `files suggest --caselist <slug> --position <id>` writes a draft recipe for you from the
landscape's most-read cards: `status: draft`, which `files build` builds only with `--allow-draft`.
Neither ever writes inside a git working tree. This page is about the recipe itself (`v1-e33-t01`).

## Drafting a counterplan file

When the position is a counterplan in the topic's taxonomy (`kind: cp`), `files suggest` drafts it the
way a CP file is built (`v1-e33-t11`). Its first block opens with a slot for the counterplan's text,
`- analytic: "[the counterplan text: write it here]"`, which you replace with the text your team
reads. The draft never fills it from another team's file or from the landscape report's CP texts.
Nothing checks that you replaced it: `files build` on a `ready` recipe still holding it builds it as
written, so read it over before you build. A block whose heading names another position, such as a
topicality block that sat in the same 1NC, is left out with its cards, and the command's table and
`--json` (`other_positions_left_out`) count the blocks and cards it left out. A block whose heading
names no position stays. A block whose heading names a plank or mechanism of the plan (an
affirmative's alias or tag keyword in the taxonomy, a plank label such as `Plank 2`, or one of your
plan-mechanism words for the topic) stays, with the comment `# Check this block against the
affirmative's plan: its heading names a plank or mechanism of a plan.` above it: its cards may make
sense only against a plan that has that plank. A block whose heading names an affirmative or one of its
advantages is not left out but kept, where its most-read card puts it, with the comment `# Check this
block against the affirmative's plan: its heading names an affirmative or one of its advantages.` above
it, because in a CP file it is often the counterplan's solvency for that advantage; the table and
`--json` (`affirmative_side_kept`) count those blocks and cards, and a block naming any other kind of
position (a DA, another CP, a K, a T) is still left out (`v1-e33-t13`). A block both describe has the
first comment only. Any other position's draft is written as before.

**The plan-mechanism words are yours to edit** (`v1-e33-t14`), in
`config/landscape/plan_mechanisms/<topic id>.yaml`, beside the topic's other landscape files, for
example [`policy-2026-27-nhi.yaml`](../../config/landscape/plan_mechanisms/policy-2026-27-nhi.yaml),
seeded with `preempt`, `preemption`, `waiver` and `waive`. Add a word when you meet a block of a CP
draft that depends on the plan and was not marked. Each word is lowercase letters, with single hyphens
between them (`pre-empt`), 3 to 32 characters, and listed once. A word marks a block whose heading holds
it as a whole word, or its plural with `s` or `es`: `waiver` marks a block headed `Waivers`, but `waive`
does not mark `Waiver`, and `preempt` does not mark `Preemption`, so list each form you mean. A topic
with no file is drafted as before. `uv run pytest tests/config` checks your edit; nothing else reads the
file, so it needs no refill and no taxonomy bump.

## A recipe holds no evidence

There is no field for a card's text or its cite, and there never will be. A card is its
fingerprint. The only words a recipe carries are yours: headings, a tag you write to replace a
card's own, and analytics. Each has a length limit, so a pasted card does not fit:

| Your text | Longest |
|---|---|
| Title, pocket, hat and block headings | 200 characters |
| A tag override | 600 characters |
| An analytic | 2,000 characters |

## The fields

```yaml
schema_version: 1
title: Politics DA answers
topic: nhi
format: POLICY
caselist: hspolicy26
position: politics-da
side: AFF
fingerprint_version: card-fingerprint-v3
status: ready
structure: []
```

| Field | What it is |
|---|---|
| `schema_version` | Always `1`, the recipe shape this page describes |
| `title` | The file's title |
| `topic` | The topic id, kebab-case (`nhi`, `space-colonization`), as the landscape taxonomy names it |
| `format` | `POLICY`, `LD` or `PF` |
| `caselist` | The caselist whose cards an unpinned reference comes from, such as `hspolicy26`, or `openev` for a file of camp cards ([below](#camp-cards-openev)) |
| `position` | The position id, kebab-case (`politics-da`) |
| `side` | `AFF` or `NEG` for Policy and LD, `PRO` or `CON` for PF |
| `fingerprint_version` | The card-matching rules your fingerprints were taken under. `card-fingerprint-v1`, `v2` and `v3` all give the same fingerprints today, so any of them is accepted |
| `status` | `ready`, the default, or `draft`. `files build` will refuse a draft unless asked to build it anyway |
| `structure` | The file's pockets, in order (below). The empty list in the sketch above is refused: a recipe holds at least one pocket |

Every key is checked: a key the recipe does not know, at any level, is an error, so a misspelt
`tag_overide` is reported rather than quietly ignored.

## Pockets, hats, blocks and items

The tree follows Verbatim's heading levels, and no level may be skipped:

```text
pocket          Heading 1
  hat           Heading 2
    block       Heading 3
      items     cards (Heading 4 tags) and analytics
```

* A pocket holds `hats:` or `blocks:`, never both and never neither.
* Hats are optional for the recipe as a whole. If **any** pocket has hats, every pocket does, and
  every block sits inside a hat.
* Items sit only in a block. `items:` straight under a pocket or a hat skips a heading level and is
  refused, and so is a block inside a block.
* No section is empty: every pocket, hat and block holds something.

An item is one of two things.

**A card**, by its fingerprint, with an optional tag of your own and an optional pin:

```yaml
- fingerprint: 2b256ef7bada457c21398f75b771ccc86e582caf37c75935c07c1597c74debb9
  tag_override: The agenda is stalled - no capital is left to spend
```

The fingerprint is the card's E31 exact fingerprint: 64 lowercase hex characters, the same value
the occurrence store and `debate-research caselist cards` give for it. It names the card's
evidence, not its tag or cite, so every team's copy of one card has the same fingerprint. Leave out
`tag_override` to keep the tag the card has in its source file; give one and the built file uses
your tag, recorded as written by you.

**An analytic**, your own words:

```yaml
- analytic: The agenda is stalled now, so the plan cannot be why it fails.
```

A file holds a card once. The same fingerprint twice in one recipe is an error at the second.

## Which copy of a card the file uses

The same card is usually disclosed by many teams. The builder copies it from one **occurrence**: one
place the card appears, in one file disclosed by one team. You can choose it with a pin, or let the
recipe choose.

### Unpinned: chosen for you (AUTO)

Among the card's occurrences in the recipe's `caselist`, the builder takes:

1. an **attributed** occurrence before an unattributed one: one whose disclosure is on record, so
   the built file's sidecar can say which team disclosed the card (for a camp card, one whose
   release is on record, so the sidecar can name the camp file);
2. then the one seen in the **latest snapshot**;
3. then the one in the file with the **lowest source SHA-256**;
4. then the one that starts at the **lowest paragraph** of that file;
5. then the one whose disclosure has the lowest digest, when one file was disclosed at two paths.

An unattributed occurrence is used only when the card has no attributed one, and `files build`
names every card that was resolved to one before it builds the file. Every step reads a field the
occurrence store holds or the record it points to, so the same store always gives the same choice.
The result is recorded as `AUTO`.

AUTO never leaves the recipe's own `caselist`. A camp card reaches a caselist recipe only by a pin;
a recipe whose `caselist` is `openev` chooses among camp cards instead ([below](#camp-cards-openev)).

### Pinned: the copy you name

```yaml
- fingerprint: 656173b74de69289fbb383bcb27136e7479fcb7762b20605e08bc2a1923b977c
  pin:
    caselist: hspolicy26
    source_sha256: 731fac7d649f172c908571e53cc95e035d20b31f878a6b17c209f86cd0132b15
    element_index: 41
    snapshot: 2026-09-22
    school: Maple Grove
    team_code: QX
    round: Round 3
```

A pin needs three fields: the `caselist` whose store holds the card, the `source_sha256` of the file
it is in, and the `element_index` of the card's first paragraph in that file. The rest narrow it to
one disclosure when the same file was disclosed by more than one team:

| Field | Matches when |
|---|---|
| `snapshot` | The disclosure was listed in or between its first and latest snapshots |
| `school`, `team_code` | Exactly as disclosed |
| `side` | The side the disclosing file was read on |
| `tournament`, `round` | Exactly as disclosed, capitals and spaces included (`Round 3`, not `round 3`) |

A pin may name another caselist than the recipe's, such as last season's. The result is recorded as
`PINNED`. A pin is never quietly moved to another copy: one that matches no occurrence, or two
disclosures by different teams or rounds, is an error until you fix it.

### Camp cards (OpenEv)

Camp files from OpenEv are kept in a store of their own, named `openev`, one copy of each card per
**release**: a camp year and an event, written `<year>-<event>` such as `2031-policy`, as
`caselist publish --caselist openev --snapshot` names it. A pin reaches a camp card with
`caselist: openev` and its release as `snapshot`:

```yaml
- fingerprint: 5e0b7d2c41f0a8c3d6e9b1f4a7c2e5d8b0f3a6c9e2d5b8f1a4c7e0d3b6f9a2c5
  pin:
    caselist: openev
    source_sha256: 9c4e1a7f3b6d0c2e5a8f1b4d7c0e3a6f9b2d5c8e1a4f7b0d3c6e9a2f5b8d1c4e
    element_index: 12
    snapshot: 2031-policy
```

* The release is required, because the same camp file released in two years is two copies. The
  event is `policy`, `ld` or `pf`, in lower case.
* A camp file has no disclosure, so a camp pin names no `school`, `team_code`, `side`, `tournament`
  or `round`; giving one is an error.
* A caselist pin's `snapshot` is still a date. A release there is an error that says to use
  `caselist: openev`.

A camp pin can sit in any recipe, beside cards from a caselist. For a file of camp cards alone, set
the recipe's own `caselist` to `openev`, and unpinned cards are chosen among camp releases by the
same five steps, where the latest release is the one of the latest year, then the first by name
(`2031-ld`, `2031-pf`, `2031-policy`). A camp card's provenance line names the camp, year, event and
file title, as the data-use policy sets out:

```text
[OpenEv: Cascade Institute 2026 — Policy, Climate Adv CP]
```

The line is in the file's sidecar, `<file>.docx.provenance.json`, for disclosed and camp cards alike,
and not in the built file: since version 1.11 of the data-use policy a built file carries no
provenance line below its cites. The sidecar keeps every card's provenance, and a removal request is
matched against it.

**A pin names a team.** A school and team code are personal data about students, and the data-use
policy allows them only in a few places, the evidence workspace among them. That is where your
recipes live, so a pin there may name a team. A recipe is never committed to the repository with a
real school or team code in it, and nothing ever logs one.

### Removed files

When a team asks for a file to be taken down, the removal suppression list remembers it. A recipe
never uses a copy the list stops, whether the whole file was removed or only one team's disclosure
of it was withdrawn:

* an unpinned card skips that copy and takes the next by the order above;
* a card with no copy left is reported, `SUPPRESSED_OCCURRENCE`;
* a pin to a removed copy is refused with `SUPPRESSED_OCCURRENCE`. It is not moved to another copy:
  remove the pin to let the recipe choose, or pin another.

A removal also **holds** the path the file was taken from, so a later upload at that path is not
used either. The same three rules apply to a copy at a held path, from the moment the hold reaches
your machine, before the next `caselist parse` takes the copy out of the store.

Camp cards follow the same rules. A camp file removed as a whole is never used. Withdrawing one
team's disclosure of a file does not withdraw a camp's release of the same file; a camp release a
removal takes a file out of drops it at the next `caselist parse --caselist openev`.

## Errors

Checking a recipe reports **every** error at once, each with its line in your file and where it is
in the recipe:

```text
line 28: structure[0].hats[1].blocks[2].items[3].fingerprint: a fingerprint is an E31 exact fingerprint: 64 lowercase hex characters [INVALID]
line 32: structure[0].hats[1].blocks[2].items[3].pin.element_index: Input should be greater than or equal to 0 [INVALID]
```

`structure[0].hats[1].blocks[2].items[3]` counts from zero: the fourth item of the third block of
the second hat of the first pocket.

| Code | Means |
|---|---|
| `YAML_SYNTAX` | The text is not one readable YAML document |
| `DUPLICATE_KEY` | A key given twice in one mapping; YAML would silently keep the last |
| `TOO_LARGE` | Over 1,000,000 bytes, or over 100,000 YAML nodes once aliases are followed |
| `INVALID` | A field or section the recipe does not allow, or a `fingerprint_version` with other fingerprints |
| `UNKNOWN_CARD` | The recipe's caselist (or `openev`) has no occurrence of this fingerprint |
| `PIN_MISMATCH` | The pin matches no occurrence of the card, or two disclosures that differ in who disclosed them |
| `DUPLICATE_REF` | The card is already in the file |
| `SUPPRESSED_OCCURRENCE` | The removal suppression list stops or holds the pinned copy, or every copy of the card |

No message repeats what you wrote in a field, because what you wrote may be a team code.

Two YAML habits worth knowing. `side: no` is read by YAML as *false*, not as text, so it is
refused; write the side in capitals. And a hex value made only of digits is read as a number: the
error says to put it in quotes.

## The recipe hash

Every recipe has a `recipe_hash`, the SHA-256 of a canonical form of what it holds. Reordering keys,
adding comments, quoting, flow or block style, anchors and aliases do not change it; changing a card,
a pin, a tag, an analytic, a heading or the order of anything does. Built and published files carry
it, so two files with the same hash were built from the same recipe.

## Three examples

All three are synthetic: every fingerprint, source hash, school, team code and tag is invented.
They are the files in [`tests/fixtures/file_builder/recipes/`](../../tests/fixtures/file_builder/recipes/),
and a test fails if this page and those files ever differ.

### Policy: answers to the politics disadvantage

An affirmative file with one pocket and three hats (uniqueness, link, impact). Two cards carry your
own tags. The link card is pinned to one team's disclosure in one round, with a snapshot it was
listed in; the other four are chosen for you.

```yaml
# Synthetic example recipe: Policy, affirmative answers to the politics disadvantage.
# Every fingerprint, source hash, school, team code and tag here is invented for the repository.
schema_version: 1
title: Politics DA answers
topic: nhi
format: POLICY
caselist: hspolicy26
position: politics-da
side: AFF
fingerprint_version: card-fingerprint-v3
structure:
  - pocket: Politics DA answers
    hats:
      - hat: Uniqueness
        blocks:
          - block: Non-unique - the agenda is already stalled
            items:
              - analytic: The agenda is stalled now, so the plan cannot be why it fails.
              - fingerprint: 2b256ef7bada457c21398f75b771ccc86e582caf37c75935c07c1597c74debb9
                tag_override: The agenda is stalled - no capital is left to spend
              - fingerprint: 62ad82e7dd7cbacf7bd602445b0abc49228ab21e850fe32be95c4119aa459a4a
      - hat: Link
        blocks:
          - block: No link - the plan is popular
            items:
              - fingerprint: 656173b74de69289fbb383bcb27136e7479fcb7762b20605e08bc2a1923b977c
                pin:
                  caselist: hspolicy26
                  snapshot: 2026-09-22
                  school: Maple Grove
                  team_code: QX
                  round: Round 3
                  source_sha256: 731fac7d649f172c908571e53cc95e035d20b31f878a6b17c209f86cd0132b15
                  element_index: 41
              - analytic: Even if the plan is unpopular, the vote comes after the agenda item.
      - hat: Impact
        blocks:
          - block: Impact turns
            items:
              - fingerprint: d31c01b523147eb739279295b2d0912a26bf607d9e6e2b63c26697b2bb8a1bcb
              - fingerprint: 99703657cd4dd993417fb63f39acb28c52d108f9c746c7a15bfd603fa7305789
                tag_override: Turn - a fight over the agenda item helps the plan
```

### LD: a negative constructive on space colonization

An NC laid out without hats: one pocket of three blocks, framework then two contentions. The pin is
written on one line, in flow style, which reads the same as the block style above.

```yaml
# Synthetic example recipe: LD, a negative constructive on space colonization, without hats.
# Every fingerprint, source hash, school, team code and tag here is invented for the repository.
schema_version: 1
title: Space colonization NC
topic: space-colonization
format: LD
caselist: hsld26
position: nc
side: NEG
fingerprint_version: card-fingerprint-v3
structure:
  - pocket: NC
    blocks:
      - block: Framework - the value is morality
        items:
          - analytic: I value morality, because the resolution asks what we ought to do.
          - fingerprint: 608ac2f3e7b063e55ffab3e7617285fe31e5869cffd4006ea79853bdcb59a9ed
            tag_override: Obligations bind before outcomes are counted
      - block: Contention 1 - extraction off-world
        items:
          - fingerprint: 9d647c1b4b2c2a0605417fe28141bc2163b19c5eda356cb3cc7b19a1686cbf53
            pin: {caselist: hsld26, source_sha256: a0f52e86d35462af8a89ddc539c504b4d3ec15167451320c3047d23a414560d6, element_index: 7, school: Cedar Hollow, team_code: ZaLu}
          - fingerprint: 3a7f105abcb103a8c2b670766de88c4b02e189c2637df65efee388090e8e57a5
      - block: Contention 2 - priorities on Earth
        items:
          - fingerprint: 0a3967fe32002a2335ed08dfb58249da50a2f3a66b98232600d153cf9660872a
          - analytic: Every dollar spent off-world is a dollar not spent here.
```

### PF: con blocks against a data-center moratorium

Two pockets, each with a hat, answering two pro arguments. The pin names the side the disclosing
file was read on as well as the team.

```yaml
# Synthetic example recipe: PF, con blocks against a data-center moratorium, two pockets with hats.
# Every fingerprint, source hash, school, team code and tag here is invented for the repository.
schema_version: 1
title: Data-center moratorium con blocks
topic: data-center-moratorium
format: PF
caselist: hspf26
position: con-blocks
side: CON
fingerprint_version: card-fingerprint-v3
structure:
  - pocket: Answers to energy prices
    hats:
      - hat: Prices
        blocks:
          - block: AT - a moratorium lowers prices
            items:
              - fingerprint: f4fcb12e6aecb70d1638a34c13fd713b2563b5db671dd17a7030e619eb5ee752
                tag_override: Demand moves elsewhere - it does not vanish
              - analytic: Their evidence assumes the demand disappears; it relocates.
  - pocket: Answers to water use
    hats:
      - hat: Water
        blocks:
          - block: AT - data centers drain aquifers
            items:
              - fingerprint: 34a4d50762785d35d8dc5aecc3dbe487bf5f5e99a6375510164ff7da1fc702e6
                pin:
                  caselist: hspf26
                  source_sha256: 86affdf090d9656d2e71cf6064802f3c1add451789b25d13a79e03f19a41dfc5
                  element_index: 3
                  school: Maple Grove
                  team_code: AB
                  side: CON
              - fingerprint: aa1220efca7d04f0511c4359e5d32637f5fd5019c20ebfdb0807fb60fa54dcc1
              - fingerprint: dc2c26bc1e2004dab8eb4d777317a18a68aa10a9a84a2a8cbd30cad457800b88
```

## Checking a recipe against the schema

The schema describes each field and the shape of the tree, and an editor with YAML schema support
(VS Code's YAML extension, for one) can check a recipe against it as you type. Two rules are not in
it and are checked when the recipe is loaded: that `side` is one `format` debates, and that every
pocket has hats when any does.

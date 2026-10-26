<!-- docs-index: Published built files under the evidence bucket's files/ prefix: the key layout, the metadata.json contract the V2 debate tub indexes, and the lookups by source, school or team for takedowns -->
# Published built files: `files/` and `metadata.json`

What `debate-research files publish` puts in an evidence bucket, object by object, and the
`metadata.json` beside each built file. This is the contract the V2 debate tub indexes by
([`v2-e35-t02`](../../plan_specs/v2/e35-debate-tub/t02-tub-index-sync.yaml)) and the takedown flows find files by (`v1-e30-t07`,
`v2-e35-t05`). Spec:
[`v1-e33-t05`](../../plan_specs/v1/e33-file-builder/t05-file-publish.yaml). Schema:
[`built-file-metadata.schema.json`](built-file-metadata.schema.json), generated from
`debate_core.domain.built_file_metadata.BuiltFileMetadata` by
`scripts/export_built_file_metadata_schema.py` and held to the model by a drift test. The objects
beside it have schemas of their own: [the provenance sidecar](file-provenance.schema.json), [the
quality report](file-quality-report.schema.json) and [the recipe](file-recipe.schema.json).

## One published file is five objects

```
files/<topic>/<side>/<position>/<slug>/<recipe hash, first 12>/
    <slug>.docx                     the built file, the bytes the quality check passed
    <slug>.docx.provenance.json     its provenance sidecar, as files build wrote it
    <slug>.docx.quality.json        the quality report for these exact bytes, PASS
    recipe.yaml                     the recipe, no pin naming a side, tournament, round, school or team
    metadata.json                   what the file is; written last
```

* `<topic>` and `<position>` are the recipe's ids (kebab-case, as the landscape taxonomy names
  them), `<side>` is `aff`, `neg`, `pro` or `con`, and `<slug>` is the built file's name without
  `.docx`, which `files build` takes from the recipe's file name. A slug is kebab-case, at most 100
  characters; a file whose name is not is refused (`SLUG_INVALID`). A slug is the coach's choice of
  name, so a coach names a recipe for its argument, never for a team.
* The last segment is the first 12 hex characters of the recipe hash (`v1-e33-t01`) the sidecar
  records. A recipe that changes is a new version beside the old one; nothing is overwritten under a
  version, and nothing here deletes.
* **Keys are deterministic.** The same file publishes to the same five keys every time, with the same
  bytes: `metadata.json` holds the sidecar's `built_at` and no publish time. A publish heads each key
  first and skips an object whose recorded SHA-256 is the one it would write, so republishing an
  unchanged file reports `SKIPPED` and writes nothing, not even a new object version.
* **Order.** The five are written in the order above. Each is checked twice after it is written: the
  digest of the bytes the store wrote, then the digest a `head` reads back. A difference stops the
  publish before `metadata.json`, so a reader that starts from `metadata.json` never finds a file whose
  objects are not the ones it names.

The prefix sits under the bucket's `files/` prefix
([store layout](../architecture/evidence-store-layout.md)), outside every prefix the weekly run
keeps its state in (`reports/sync/run-lock.json`, `reports/sync/state/`, `manifests/_run-state/`).
In bucket mode `files publish` holds the bucket's run lock while it writes, as every command that
writes a bucket does (ADR-0020 (4)); a dry run takes nothing.

## What is published, and what is refused

A file is published only when, in this order:

1. its quality report is beside it and readable (`QUALITY_REPORT_MISSING` otherwise);
2. the report is for the `.docx` as it is now, by SHA-256 (`QUALITY_REPORT_STALE`);
3. its sidecar records that the recipe was `ready`: a file built from a `status: draft` recipe is
   `BUILT_FROM_A_DRAFT` whatever its quality, and a sidecar written before the status was recorded is
   `RECIPE_STATUS_UNRECORDED` until the file is rebuilt (PM amendment 2026-10-24);
4. the report's status is PASS (`QUALITY_FAILED`, naming the failing checks); a WARN never blocks,
   and is recorded in `metadata.json` (PM amendment 2026-10-21);
5. the quality check, run again on the exact bytes to be uploaded, is PASS too (`QUALITY_FAILED`),
   so a source suppressed since the report was written stops the file; the report uploaded is this
   one;
6. the recipe it was built from is found, `<data dir>/files/recipes/<topic>/<slug>.yaml` or
   `--recipes <dir>/<slug>.yaml`, and its hash is the sidecar's (`RECIPE_NOT_FOUND`,
   `RECIPE_CHANGED`).

The published `recipe.yaml` is rendered from the recipe's model with every pin's `side`,
`tournament`, `round`, `school` and `team_code` removed, and without the original's comments (PM
amendment 2026-10-19; data-use policy version 1.15, under which a published recipe "loses every such
field"). A pin keeps its caselist, source SHA-256, element index and snapshot, which name the card's
source and paragraphs; the provenance sidecar beside it carries who disclosed it.

## `metadata.json`

| Field | What it holds |
|---|---|
| `schema_version` | `1` |
| `key_prefix` | `files/<topic>/<side>/<position>/<slug>/<hash12>/`, checked against the fields below |
| `slug`, `title` | The file's name without `.docx`; the recipe's title |
| `topic`, `format`, `caselist`, `position`, `side` | The recipe's topic id, event (`POLICY`, `LD`, `PF`), own caselist, position id and side (`AFF`, `NEG`, `PRO`, `CON`) |
| `card_count` | Cards in the file, as its sidecar lists them |
| `recipe_hash`, `recipe_status` | The sidecar's recipe hash; always `ready` |
| `builder_version` | The writer's version, from the sidecar |
| `parser_version`, `style_profile_version`, `fingerprint_version`, `checker_version` | The versions the publish's quality check ran under |
| `quality_status`, `quality_warnings`, `warned_checks` | Always `PASS`; how many results warned, and which checks warned |
| `built_at` | When the file was built, from the sidecar, UTC with a `Z` |
| `docx_sha256` | SHA-256 of the published `.docx` |
| `objects` | The four objects before this one, each `{name, bytes, sha256}`, in publish order |
| `sources` | Every source the sidecar names, `{caselist, snapshot, source_sha256}`, once each, sorted |
| `caselists`, `source_sha256s` | The caselists and SHA-256s of `sources`, flattened, sorted, once each |
| `provenance_mode` | Always `FILE_IMPORT`: no card in a built file is platform-verified (ADR-0006) |

`snapshot` is the first snapshot the card's occurrence was seen in, as the sidecar records it; for a
camp (OpenEv) card it is the release, `2031-policy`, and `caselist` is `openev`.

The model refuses metadata whose flattened arrays are not exactly what `sources` gives, whose
`key_prefix` is not the one its fields make, whose objects are not the four in order, or whose
`recipe_status` or `quality_status` is anything else.

### No school, no team code

`sources[]` carries no `school` or `team_code`, and there are no `schools` or `team_codes` arrays. The
data-use policy's "Where personal data is allowed to live" names a built file's provenance sidecar
and not a `metadata.json` beside it, and the PM ruled on 2026-10-25 that it stays that way: the
sidecar in the same prefix holds both for every disclosed card, and a lookup by them reads it. The V2
tub indexes school and team code from the sidecars, which it reads anyway to show provenance.

## Finding the files built from a source, a school or a team

A removal request names a source by its SHA-256 (data-use policy, Removal). The takedown lookup,
`FilePublishService.find_by_source(source_sha256)`, lists `files/`, reads every `metadata.json`, and
returns the `key_prefix` of every file whose `source_sha256s` holds it. Every source a file's sidecar
names is in its `sources[]`, which a test checks against the published sidecar, so the lookup misses
none. A `metadata.json` it cannot read is returned beside the matches as unreadable, for a person to
look at, rather than passed over.

By a school, a team code or both (PM ruling 2026-10-25),
`FilePublishService.find_by_disclosure(school=…, team_code=…)` lists `files/`, reads every
`<slug>.docx.provenance.json`, and returns the prefix of every file with a card whose disclosure names
them, both on one card when both are given. It reads the sidecar because the policy names the sidecar
as the record a removal request is matched against (Attribution rule 3). The match is exact, as
disclosed: no case folding, no expansion. A sidecar whose file's `metadata.json` never landed is read
too, since its cards are in the bucket all the same, and a sidecar it cannot read is returned as
unreadable. The result names prefixes and keys only.

Flagging and withdrawing the files found is `v1-e30-t07`'s and `v2-e35-t05`'s; this task makes them
findable.

## In dev and prod

Dev holds synthetic sample files only. Publishing the coach's first real files to prod is an
operator step, after the coach approves them, and its record is `docs/data/file-publish-log.md`
(keys, counts and statuses; no team codes), which the operator writes with the first publish.

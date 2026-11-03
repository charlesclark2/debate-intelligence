# The synthetic topic-change caselist

A second invented caselist, `synthld26` (Lincoln-Douglas), written by
`scripts/make_landscape_fixture.py` for `v1-e32-t04-trend-and-school-views` ac3: a trend never
compares two topics. Its schools (Maple Grove, Larch Point), team codes (`QX`, `RV`), tournaments,
tags and cites are invented.

| File | What it holds |
|---|---|
| `topics.yaml` | Two topics: `synthetic-ld-jul-aug` (July and August, no taxonomy) and `synthetic-ld-sep-oct` (September and October, taxonomy 1.0.0) |
| `taxonomy.yaml` | The new topic's two positions: an aff contention and a K |
| `disclosures.jsonl` | 4 rows: the same two teams on 2026-08-25 (the old topic) and on 2026-09-01 (the new) |
| `cards.jsonl`, `classifications.jsonl` | One card for each new-topic file; the old topic has no taxonomy to classify under |

A report through 2026-09-01 counts the new topic's two disclosures only, as the run reads them. Its
previous snapshot is 2026-08-25, which `topics.yaml` puts on the other topic, so it draws no trend:
both positions are NEW with no previous share and no delta, and the report says the topic changed.
Given the old topic's disclosures as well, the report refuses to build.

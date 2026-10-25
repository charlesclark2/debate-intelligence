# Session report: v1-e05-t06-card-selection-contract

| | |
|---|---|
| Task | `v1-e05-t06-card-selection-contract` — CardSelection / MarkupSpan contract and prompts |
| Spec | [`plan_specs/v1/e05-model-router/t06-card-selection-contract.yaml`](../../plan_specs/v1/e05-model-router/t06-card-selection-contract.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t06-card-selection-contract` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

<!-- 3-6 sentences: what was built, how it fits the epic, anything the PM should look at first. -->

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

The PM asked for the 12-word rule, the offset unit and "overlap inconsistently" to be defined
here before anything was built. These three definitions were written and committed first, and the
code and tests implement them as written.

### The 12-word rule (the anti-authoring guard, ac3)

* **Words.** A word is a maximal run of characters that Python's `re` matches as `\w` (Unicode
  letters, digits, combining marks and `_`). Everything else separates words and is otherwise
  ignored: spaces, line breaks and paragraph breaks, punctuation, straight and curly quotes, dashes,
  emoji. So `Senate’s` is the two words `senate` and `s`, and `52–48` is `52` and `48`, the same
  way on both sides.
* **Normalization before comparing.** The free-text field is put in Unicode NFC (the snapshot's
  normalized text already is, by `evidence-normalizer-v1`), and every word on both sides is
  compared case-folded (`str.casefold`). Case is therefore normalized, punctuation and whitespace
  are not compared at all, and nothing else is folded (no accent stripping, no quote folding).
* **The rule.** A field is refused when 12 consecutive words of it are equal to 12 consecutive
  words of the snapshot's normalized text, anywhere in the snapshot, across paragraph breaks too.
  11 consecutive shared words pass. A run counts whole words only: a field that starts in the
  middle of a snapshot word shares that word only if the whole token matches.
* **Fields checked.** Every string value anywhere in the answer, found by walking the validated
  output, not a list of field names: today that is the tag's `text` and each `rationale`. A string
  field added later is covered without anyone remembering to add it.
* **What the refusal says.** A problem of type `quoted_snapshot_text` at the field's location,
  naming how many consecutive words matched and the snapshot offsets they span. Never the words.

### Offsets

* **What the model gives:** a paragraph number `N`, the one shown as `[PN]` in the prompt (the Nth
  paragraph of the snapshot's paragraph map, counted from 1), and offsets into **that paragraph's
  normalized text**, half-open `[start, end)`, where 0 is the first character after the `[PN] `
  label.
* **The unit is Python `str` indices, which count Unicode code points**, into the snapshot's
  normalized text (`SnapshotText.text`). A paragraph offset becomes an absolute one by adding the
  paragraph's `start`, which is the unit `v1-e03-t03`'s `OffsetRange` and the normalizer's
  `OffsetMap` already use, so nothing converts between the contract and extraction.
* **Why code points.** It is what Python slices, so `text[start:end]` is the evidence with no
  conversion step to get wrong. UTF-8 bytes would make an `é` two units and an emoji four; UTF-16
  units (what JavaScript counts) would make an emoji two. Paragraph-relative rather than absolute
  because the `[PN] ` labels would otherwise shift every offset the model reads, and because a model
  counts more reliably within one paragraph than across a document.
* **The limit of the check.** A model that miscounts (say, an emoji as two) but stays in bounds
  selects different words of the real snapshot, never words it wrote. The guard cannot detect
  that; the selection is still sliced from the snapshot and is what a reviewer sees.

### "Overlap inconsistently", and the other offset refusals

The guard refuses an answer, with a named problem type, in each of these cases. Each one has a
test.

Selection (`CardSelection.passages`):

1. A paragraph number above the snapshot's paragraph count (`paragraph_out_of_bounds`; 0 and
   negatives are refused by the schema).
2. A passage whose `last_paragraph` comes before its `first_paragraph` (`reversed_range`).
3. A `start_offset` at or past the end of its first paragraph, or an `end_offset` past the end of
   its last paragraph: one past the end is refused, the end itself is allowed, since `end` is
   exclusive (`offset_out_of_bounds`).
4. A passage that selects nothing once resolved (`empty_range`).
5. Two passages that share a character (`overlapping_passages`). Passages that only touch are
   allowed: extraction joins them into one segment.

Markup (`MarkupSuggestion.spans`, checked against the selection it marks up):

6. A span in a paragraph the snapshot does not have, or ending past its paragraph's end
   (`paragraph_out_of_bounds`, `offset_out_of_bounds`), or marking nothing (`empty_range`,
   `reversed_range`).
7. A span that is not wholly inside one selected passage, after touching passages are joined:
   a span in a paragraph outside the selection, one that runs partly outside it, or one that crosses
   the gap between two passages (`outside_selection`).
8. Two spans of the same style that share a character (`overlapping_same_style`).
9. A highlighted character that no underline covers (`highlight_not_underlined`).

An underline and a highlight overlapping is the convention (what is read aloud is underlined), not
an inconsistency. Rules 7 to 9 are the ones `v1-e03-t03`'s `CardMarkup` enforces after extraction.
The guard checks them first, on the model's answer, so the model gets its one repair with the
problem named, and `CardMarkup` checks them again on the extracted evidence.

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

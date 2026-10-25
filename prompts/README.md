# Prompts

Every prompt the platform sends to a model is a file in this directory, reviewed in a pull request
like code. No production call sends wording written into a Python module
(`v1-e05-t04-prompt-registry`). `debate_core.integrations.models.prompt_registry.PromptRegistry`
loads the files, and the model router sends what it renders.

Each file is **one version of one prompt**. A YAML front matter block says which prompt and version
it is and what the answer must look like. The Jinja2 template after it is the text.

The worked example is
[`tests/fixtures/prompts/example/select-passage.md`](../tests/fixtures/prompts/example/select-passage.md).
It lives with the test fixtures because only tests load it.

## The file

```markdown
---
prompt_id: card.select
version: 1.0.0
status: released
task_class: complex_reasoning
output_schema: debate_core.evidence.selection_contract.CardSelection
owner: v1-e05-model-router
changelog:
  - version: 1.0.0
    date: 2026-10-17
    summary: First version.
---
<!-- system -->
The instructions the model works under.
<!-- user -->
The request, with the call's values: {{ research_need }}
```

(The real `card.select` is [`card/select.md`](card/select.md), with `card.markup` beside it, from
`v1-e05-t06-card-selection-contract`.)

The first released prompt is [`model/repair.md`](model/repair.md), the structured-output guard's
one repair attempt (`v1-e05-t05-structured-output-validation`). It answers in the schema of the
call it repairs and runs on that call's route, so its `output_schema` names the placeholder
`RepairedSchema` and its `task_class` is not used for routing.

### Front matter

Every key is required, and an unknown key is refused.

| Key | What it holds |
|---|---|
| `prompt_id` | The prompt's name. Letters, digits, `.`, `_` and `-`, starting with a letter or digit. It names the directory the prompt's fixtures and cassettes are filed in (`tests/fixtures/model_outputs/<prompt_id>/`), so anything else is refused. |
| `version` | `MAJOR.MINOR.PATCH`, such as `1.0.0` or `1.10.2`, without leading zeros. Pre-release and build suffixes are refused: a version that is not ready is a `draft`. |
| `status` | `draft` while the text may still change, `released` once it may not. |
| `task_class` | The task class the prompt is written for: `complex_reasoning`, `high_volume` or `deep_audit`. `embeddings` and `rerank` take no prompt. |
| `output_schema` | The dotted path of the Pydantic model the answer must validate as, where the class is defined: `module.ClassName`. A re-exported path is refused and the error names the defining one, because the path is part of every fixture key. |
| `owner` | The epic or area that maintains the prompt, such as `v1-e05-model-router`. Never a person's name. |
| `changelog` | One entry per version, `version`, `date` and `summary`, including an entry for this file's own version. |

### Body

The body is everything after the closing `---`. It is a Jinja2 template, compiled when the registry
loads and rendered for each call.

* **Turns.** With no marker the whole body is the user turn. A prompt with a system prompt starts its
  body with a line holding only `<!-- system -->` and puts a line holding only `<!-- user -->`
  before the user turn. Each marker appears at most once, the system turn comes first, and the user
  turn may not be blank. Each turn is trimmed of the blank space at its ends.
* **Every variable is required, and every one given is used.** A variable the template names but
  the call does not give is a `PromptRenderError`, even under `default(...)`, and so is a variable
  the call gives that the template never names. A call that needs to say "nothing here" passes
  `null` or an empty list.
* **Values are rendered as given.** Nothing is HTML-escaped. A mapping is rendered with its keys
  sorted at every depth, so the same values give the same text in whatever order a caller built
  them, as they already give the same fixture key.
* **One file, no other.** `include`, `extends` and `import` are refused when the file is loaded.
  The `random` filter and the `lipsum` function are not available, and the template runs in Jinja2's
  sandbox.
* **Line endings** are read as `\n` whatever the checkout uses, so a body hashes and renders the
  same on every platform.

## Versions

`PromptRegistry.get(prompt_id, version)` returns an exact version, draft or released.
`PromptRegistry.prompt(prompt_id, variables)` resolves `latest`, the highest **released** version by
number, and returns a `ModelPrompt` pinned to the exact version it found. A call always names an
exact version, because that version is part of the fixture key and of the provenance kept with the
result (`GeneratedArtifactMetadata`). v1-e09-t04 will make `latest` read the versions pinned in
`config/promoted.yaml`.

**A released version is never edited and never deleted.** Its body, `output_schema` and
`task_class` are pinned in [`prompts.lock.json`](prompts.lock.json). To change a released prompt:

1. Copy its file to a new one beside it and give the copy the next version, with `status: draft`.
   File names are not read by the registry. The convention is `<name>.md` for a prompt's first
   version and `<name>@<version>.md` for each later one, such as `card/select@1.1.0.md`.
2. Edit the draft as often as you like. Add its changelog entry.
3. Set `status: released`, then record it in the lock:

   ```bash
   uv run scripts/lock_prompts.py
   ```

   The script only adds entries. It refuses, writing nothing, if a released version already in the
   lock has changed, gone missing or been set back to draft.

`owner` and `changelog` may be corrected on a released version: they are not part of the lock.

`packages/debate_core/tests/integrations/models/test_prompt_lock.py` fails when any released prompt
here does not match the lock, so a released body edited in place fails CI. To check without writing:

```bash
uv run scripts/lock_prompts.py --check
```

## What a prompt may hold

A prompt is the repository's own instructions. **No prompt, example or fixture holds real card text,
a school, a team code or a debater's name** (`CLAUDE.md`, and the
[model provider conditions](../docs/policies/caselist-data-use.md#model-provider-use) of the
caselist data-use policy). Evidence reaches a model only as a call's variables, at call time, and a
rendered prompt holds nothing but the template's text and those variables. Those variables never
carry a school, a team code, a debater's name or initials, a tournament or round label, or a file
path either (condition 4 of that policy).

A prompt asks for paragraph ids, offsets, labels and reasons, never for quoted evidence text: the
quotation is always sliced from the stored snapshot afterwards (`CLAUDE.md`, ADR-0006).

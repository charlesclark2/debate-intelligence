# Malformed model answers

Invented answers that do not fit their schema, served by `FakeModelRouter` with this directory as
its fixture directory. `packages/debate_core/tests/application/test_structured_output.py` runs each
one through the structured-output guard with `fail_closed=True` and expects a `ModelOutputError`
every time (`v1-e05-t05-structured-output-validation`, ac3). Nothing here is real card text.

Every case is the prompt `example.select-passage@1.0.0` (schema `ContractPassage`: three integers)
with the tag `Malformed answer: <case>`, and a `model.repair` fixture that answers the repair call
with the same malformed answer, so the repair fails too.

| Case | Answer |
|---|---|
| missing fields | `{"paragraph_id": 3}` |
| wrong types | a string, a list and an object where integers belong |
| coercible values | `"3"`, `0.0` and `true`: lax validation would turn each into an integer |
| extra keys | a valid answer plus `passage_text` |
| empty tool output | `{}` |
| no tool call | `null`, which the fake reads as an answer that never called the schema's tool |

**Every case has a repair fixture of its own.** A repair request carries the failed call's own
prompt, rendered with its variables, so two calls that fail the same way still ask different repair
questions. "wrong types" and "coercible values" fail with the same three `int_type` problems and
are filed apart, by their tags (the PM's review of v1-e05-t05).

## Rewriting them

A repair fixture's key covers the repair prompt's variables: the failed call's rendered prompt and
pydantic's messages. So a change to `select-passage.md`, a pydantic upgrade that rewords a message,
a change to the repair prompt's variables or a new `model.repair` version needs the repair files
written again. Write them with `FixtureDirectory` as
`tests/fixtures/model_cassettes/README.md` describes, building each repair request with
`repair_prompt`, as the guard does:

```python
from pathlib import Path

from debate_core.application.errors import InvalidModelOutput
from debate_core.application.structured_output import repair_prompt, validate_model_output
from debate_core.domain.model_contracts import ModelPrompt, ModelRequest, TaskClass
from debate_core.integrations.models.fake_router import FixtureDirectory
from debate_core.integrations.models.prompt_registry import load_prompt_file
from debate_core.testing.contracts.model_router import ContractPassage

fixtures = FixtureDirectory(Path("tests/fixtures/model_outputs/malformed"))
example = load_prompt_file(Path("tests/fixtures/prompts/example/select-passage.md"))
prompt = ModelPrompt(
    prompt_id="example.select-passage",
    prompt_version="1.0.0",
    variables={"tag": "Malformed answer: missing fields"},
)
answer = {"paragraph_id": 3}
fixtures.write(ModelRequest.build(TaskClass.HIGH_VOLUME, prompt, ContractPassage), answer)
try:
    validate_model_output(ContractPassage, answer, prompt=prompt, model_id=None)
except InvalidModelOutput as invalid:
    repair = repair_prompt(prompt, example.render(prompt.variables), ContractPassage, invalid.problems)
    fixtures.write(ModelRequest.build(TaskClass.HIGH_VOLUME, repair, ContractPassage), answer)
```

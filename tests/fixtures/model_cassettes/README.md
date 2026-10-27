# Recorded model answers

Tests, golden runs and evals never call a real model (`docs/process/working-agreements.md`). They
get their answers from two directories, written for review and committed like code
(`v1-e05-t03-fake-replay-models`):

| Directory | Read by | Holds |
|---|---|---|
| `tests/fixtures/model_cassettes/` (this one) | `RecordReplayModelRouter` in replay mode | Cassettes: a real router's request and response, one file per call |
| `tests/fixtures/model_outputs/` | `FakeModelRouter` (`models.provider = "fake"`) | Fixtures: a hand-written answer to one prompt, version and set of variables |

Both are keyed the same way: `<prompt_id>/<key>.json`, where the key is the SHA-256 of the prompt
id, its version, the canonical JSON of its variables and the output schema's dotted path
(`debate_core.integrations.models.fixture_key`). Cassettes of `embed` and `rerank` calls go in
`_embed/` and `_rerank/`. The fake computes its embeddings and rerank scores and keeps no files for
them.

## What may be in a file here

**Everything is invented.** No credentials, request signatures, account ids, student names or real
card text, in a cassette or a fixture. The task spec forbids each of them.

* Prompt variables are made-up tags, needs and paragraph-numbered text written for the test, never
  text copied from a caselist file, a student's document or a published card.
* Record mode scrubs authorization headers, AWS keys, SigV4 signatures, bearer tokens and account
  ids before it writes (`debate_core.integrations.models.redaction`). A name or a card's text cannot
  be recognised that way, which is why the inputs have to be invented in the first place.
* `test_no_committed_cassette_or_fixture_holds_anything_redaction_would_remove`, in
  `packages/debate_core/tests/integrations/models/test_record_replay.py`, reads every JSON file in
  both directories on every pull request and fails on anything the scrubber would remove.

Review a new cassette as you would a source file: the request should be one you wrote, and the
response should not hold anything you would not commit.

## Writing a fixture for the fake

Write it through `FixtureDirectory`, which computes the key and files it:

```python
from pathlib import Path

from debate_core.domain.model_contracts import ModelPrompt, ModelRequest, TaskClass
from debate_core.integrations.models.fake_router import FixtureDirectory

prompt = ModelPrompt(prompt_id="card.select-passage", prompt_version="1.0.0", variables={"need": "..."})
request = ModelRequest.build(TaskClass.COMPLEX_REASONING, prompt, CardSelection)
FixtureDirectory(Path("tests/fixtures/model_outputs")).write(request, {"paragraph_id": 3, ...})
```

The fake recomputes the key from the file's own fields when it reads one, so a fixture copied to the
wrong name, or left behind by a prompt version bump, is refused rather than served.

`"output": null`, in a fixture or a cassette, is an answer that never called the schema's tool,
which Bedrock's `toolChoice` `auto` allows. Both routers refuse it as invalid output, and the
structured-output guard repairs it like any other (`v1-e05-t05`, ac5). A repair is a second call,
to `model.repair`, and needs a fixture or cassette of its own; `tests/fixtures/model_outputs/malformed/`
has worked examples. A call with no
fixture fails with `MissingFixtureError`, naming the prompt and the key; it never gets a default.

Record mode writes an invalid answer too (`v1-e05-t10`), so both halves of a repaired call are
recorded live and neither is written by hand. Its response holds the answer as the real router
received it (`"output": null` when the model called no tool) and the router's `problems` and
`usage`; replay raises that same `InvalidModelOutput`, and the guard's repair finds its own
cassette. It holds what the model said, as every cassette does, so the rules above apply to it
unchanged. Nothing is recorded for a provider error, a budget refusal or a call that never reached
the provider.

## Recording cassettes

Recording calls a real model, so it needs credentials and costs money. It is a developer's
deliberate step, never CI's:

* The mode has one control: `--model-mode record|replay|live` where a program has the option, else
  `DEBATE_MODEL_MODE`, else replay. No setting or other variable chooses it.
* Record mode refuses to start when `CI` is `true`, `1` or `yes`.
* A program records only when it builds its router with `build_model_router` from
  `debate_core.integrations.models.factory`, with a real provider in `models.provider`. The Bedrock
  adapter that records against is `v1-e05-t02-bedrock-adapter`; until it lands there is nothing
  real to record.

A recording run goes to the operator as a hand-off (working agreement 2): it needs credentials and
it changes files a pull request will carry.

In replay mode a call with no cassette fails with `MissingFixtureError`. So does a call whose task
class or parameters differ from what the cassette recorded, because the key does not cover them and
replay compares the whole request. Replay never holds the real router, so it cannot fall back to it.

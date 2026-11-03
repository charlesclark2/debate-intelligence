# Fake model router fixtures

Hand-written answers that `FakeModelRouter` serves, one file per prompt, version, set of variables
and output schema, filed as `<prompt_id>/<key>.json`. Every one is invented: no credentials, student
names or real card text.

How the key is computed, how to write a fixture with `FixtureDirectory`, and what may be in one are
in [`../model_cassettes/README.md`](../model_cassettes/README.md), which covers both directories.

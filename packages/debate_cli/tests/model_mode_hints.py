"""The hints a refused model call ends with, written by hand (v1-e06-t09, the PM's amendment of 2026-11-14).

A `debate-research` command whose model call nobody recorded is refused with `MISSING_FIXTURE_ERROR`.
Which sentence ends that refusal depends on who asked for replay:

* nobody, on a real provider: :data:`LIVE_MODE_HINT`, for a coach, who wants the real call;
* a person, with `DEBATE_MODEL_MODE=replay`, or a script or an eval runner that builds its router
  itself: :data:`RECORD_HINT`, the record-and-replay router's own, for whoever records cassettes;
* the `test` profile's fixture fake: :data:`FAKE_HINT`, the fake's own.

The tests of `cut`, `search` and `daily` compare against these, never against the code's constants, so
that a change to the code's wording is a change a test sees.
"""

from __future__ import annotations

from typing import Final

LIVE_MODE_HINT: Final = (
    "Replay is the default, and it answers only from calls recorded on this machine. For a real call, "
    "set DEBATE_MODEL_MODE=live in this shell (export DEBATE_MODEL_MODE=live) and run the command again: "
    "each call is then a model call on this environment's route, which the budget counts. "
    '"Real model calls" in docs/guides/daily-digests.md says more.'
)
RECORD_HINT: Final = (
    "Record it with DEBATE_MODEL_MODE=record and credentials, outside CI "
    "(tests/fixtures/model_cassettes/README.md); replay never calls a real model."
)
FAKE_HINT: Final = (
    "Write the answer with FixtureDirectory.write (tests/fixtures/model_cassettes/README.md); "
    "the fake router never asks a real model."
)


def refused_under_the_default_line(count: int) -> str:
    """The line under an auto-cut table when `count` results were refused under the replay default.

    The PM's wording (ruling of 2026-11-14 on v1-e06-t09), with one result said in the singular.
    """
    refused = "1 result was refused" if count == 1 else f"{count} results were refused"
    return (
        f"{refused} because replay is the default. For real model calls, export DEBATE_MODEL_MODE=live "
        '(see "Real model calls" in docs/guides/daily-digests.md).'
    )


REFUSED_UNDER_THE_DEFAULT_WORDS: Final = "because replay is the default"
"""Words of that line, and of no other output, for a test that the line is absent."""

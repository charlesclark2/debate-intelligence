"""Record the one landscape model call the synthetic archive needs, offline, from a hand-written prompt.

The synthetic archive's card 4 sits under `Off-case one`, which no alias of the taxonomy names, so
`landscape report --model-mode replay` asks `landscape.classify_position` about it, once, and replays
the answer from a cassette. No model is called to make that cassette, here or anywhere:

* the **request** is written by hand below (:data:`VARIABLES`): the taxonomy's two positions, and
  card 4 as the stage shows a model a card, its heading, tag, short cite and excerpt (the whole of its
  evidence, which is under the stage's 120 words and names nobody), each in the words the stage reads:
  lower case, punctuation dropped, a hyphen read as a space. The first hand-written request kept the
  card's own case and punctuation, and the replay refused it with `MissingFixtureError`;
* the **answer** is written by hand (:data:`ANSWER`): card 4 argues `spending-da`;
* the **cassette** is written by the production record path, `RecordReplayModelRouter` in record
  mode behind the `StructuredOutputGuard` the stage uses, with a scripted router standing for the
  model, inside `filed_under("synthcl26")` as the stage files its calls. So the file's key, task class,
  parameters and format are the ones a recording would have.

A replay that sends anything but :data:`VARIABLES` finds no cassette and stops with
`MissingFixtureError`, so the end-to-end test fails if the stage's request is not the one written here.
`tests/fixtures/caselist/test_synthetic_archive.py` fails when the committed cassette is not what this
script writes. Rewrite it with::

    uv run python -m tests.fixtures.caselist.synthetic_archive.record_landscape_cassette
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Final

from pydantic import JsonValue
from tests.fixtures.caselist.synthetic_archive.build_synthetic_archive import CASELIST, DIRECTORY

from debate_core.application.cassette_filing import filed_under
from debate_core.application.landscape_model_stage import (
    CLASSIFICATION_POLICY,
    CLASSIFICATION_TASK_CLASS,
    CLASSIFY_POSITION_PROMPT_ID,
    CLASSIFY_POSITION_VERSION,
)
from debate_core.application.structured_output import StructuredOutputGuard
from debate_core.domain.landscape_classification import ModelPositionAnswers
from debate_core.domain.model_contracts import ModelPrompt
from debate_core.integrations.models.model_mode import ModelMode
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.integrations.models.record_replay import RecordReplayModelRouter
from debate_core.testing.fakes.model_router import ScriptedModelRouter

__all__ = ["ANSWER", "CASSETTES", "VARIABLES", "record"]

CASSETTES: Final = DIRECTORY / "cassettes"
"""Copied to `<data dir>/landscape/model-cassettes/` by the test, where the stage replays from."""

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[4]


def _json(value: object) -> str:
    """The stage's JSON: sorted keys, one-space indent, characters as they are."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=1)


VARIABLES: Final[dict[str, JsonValue]] = {
    "taxonomy_version": "1.0.0",
    "positions": _json(
        [
            {"id": "grid-adv", "kind": "advantage", "label": "Grid reliability advantage", "side": "aff"},
            {"id": "spending-da", "kind": "da", "label": "Spending disadvantage", "side": "neg"},
        ]
    ),
    "items": _json(
        [
            {
                "item": "item-1",
                "headings": ["off case one"],
                "under_an_answer_heading": False,
                "tag": "a breach of the cap triggers automatic cuts to every invented program",
                "cite": "marsh 26",
                "excerpt": (
                    "under the invented statute a breach of the cap starts automatic cuts within thirty days "
                    "to every program on the synthetic schedule popular or not"
                ),
            }
        ]
    ),
}
"""What the stage sends about card 4, written by hand from the archive and the taxonomy."""

ANSWER: Final = {
    "answers": [
        {
            "item": "item-1",
            "position_id": "spending-da",
            "confidence": 0.8,
            "rationale": "Automatic cuts after a breach are the impact of the spending argument.",
        }
    ]
}
"""The answer, written by hand: card 4 is the spending disadvantage's impact."""


async def _record(cassettes: Path) -> None:
    model = ScriptedModelRouter([ANSWER])
    router = RecordReplayModelRouter(model, mode=ModelMode.RECORD, cassette_dir=cassettes, environ={})
    guard = StructuredOutputGuard(router, PromptRegistry.load(REPOSITORY_ROOT / "prompts"))
    prompt = ModelPrompt(
        prompt_id=CLASSIFY_POSITION_PROMPT_ID, prompt_version=CLASSIFY_POSITION_VERSION, variables=VARIABLES
    )
    with filed_under(CASELIST):
        await guard.generate(
            CLASSIFICATION_TASK_CLASS, prompt, ModelPositionAnswers, policy=CLASSIFICATION_POLICY
        )


def record(cassettes: Path = CASSETTES) -> list[Path]:
    """Write the cassette under `cassettes`, replacing what was there; the files written."""
    shutil.rmtree(cassettes, ignore_errors=True)
    asyncio.run(_record(cassettes))
    return sorted(path for path in cassettes.rglob("*.json"))


def main() -> int:
    for path in record():
        print(f"wrote {path.relative_to(DIRECTORY)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

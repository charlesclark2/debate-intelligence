"""The model stage's application half (`v1-e32-t07`): the evidence it reads, and the gate on a live run.

The stage's batches, cap and refusals are tested through the service in `test_position_classification.py`.
Every text here is invented.
"""

from __future__ import annotations

import pytest

from debate_core.application.landscape_model_stage import ParsedStoreCardTexts, model_use_gate
from debate_core.application.ports.parsed_store import DocumentRecord, SourceEntry
from debate_core.testing.fakes.parsed_store import InMemoryParsedStore

SHA = "a" * 64
VERSION = "2026.10.20-docx-6"
COMMON = {
    "caselist": "hspolicy99",
    "snapshot": "2026-10-20",
    "source_sha256": SHA,
    "parser_version": VERSION,
    "profile_version": "2026.09.20-verbatim-1",
    "fingerprint_version": "card-fingerprint-v4",
}


def card(first: int, evidence: str | None) -> dict[str, object]:
    return {
        "tag": "An invented claim",
        "section_path": [],
        **({"evidence_text": evidence} if evidence is not None else {}),
        "provenance": {"first_element_index": first, "last_element_index": first + 2},
    }


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_evidence_is_read_for_the_wanted_cards_only() -> None:
    store = InMemoryParsedStore()
    entry = SourceEntry.model_validate(
        {**COMMON, "source_format": "DOCX", "byte_size": 10, "outcome": "PARSED", "reason": None, "cards": 4}
    )
    document = DocumentRecord.model_validate(
        {
            **COMMON,
            "document": {
                "source_sha256": SHA,
                "parser_version": VERSION,
                "profile_version": "2026.09.20-verbatim-1",
                "cards": [
                    card(0, "first card's words"),
                    card(3, "second card's words"),
                    card(6, "  "),
                    card(9, None),
                ],
                "warnings": [],
            },
        }
    )
    await store.write_source("hspolicy99", VERSION, entry, document)

    found = await ParsedStoreCardTexts(store).evidence_texts(
        "hspolicy99", VERSION, {SHA: {3, 6, 9}, "b" * 64: {0}}
    )

    assert found == {(SHA, 3): "second card's words"}


OPEN = (
    "| 4 | Confirmation that the model provider does not retain inputs | **Open** | Operator | E32 gate |\n"
)
ANSWERED = (
    "| 4 | Confirmation that the model provider does not retain inputs | **Answered** (2026-11-02) "
    "| Operator | E32 gate |\n"
)
OTHER = "| 3 | OpenEv terms | **Open** | x | y |\n"


def test_the_gate_refuses_while_question_four_is_open() -> None:
    refusal = model_use_gate(OTHER + OPEN)
    assert refusal is not None
    assert "open question 4" in refusal


def test_the_gate_opens_once_question_four_is_answered() -> None:
    assert model_use_gate(OTHER + ANSWERED) is None


def test_the_gate_refuses_with_no_policy_no_row_or_no_status() -> None:
    assert model_use_gate(None) is not None
    assert model_use_gate("| 3 | OpenEv terms | **Answered** | x | y |\n") is not None
    assert model_use_gate("| 4 | the question | | x | y |\n") is not None

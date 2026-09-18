"""Smoke test: debate_workers is installed in the workspace, importable and ships type information."""

from importlib import import_module
from importlib.resources import files


def test_debate_workers_is_importable() -> None:
    module = import_module("debate_workers")
    assert module.__name__ == "debate_workers"


def test_debate_workers_is_typed() -> None:
    assert files("debate_workers").joinpath("py.typed").is_file()

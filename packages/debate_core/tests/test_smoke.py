"""Smoke test: debate_core is installed in the workspace, importable and ships type information."""

from importlib import import_module
from importlib.resources import files


def test_debate_core_is_importable() -> None:
    module = import_module("debate_core")
    assert module.__name__ == "debate_core"


def test_debate_core_is_typed() -> None:
    assert files("debate_core").joinpath("py.typed").is_file()

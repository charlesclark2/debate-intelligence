"""Smoke test: debate_cli is installed in the workspace, importable and ships type information."""

from importlib import import_module
from importlib.resources import files


def test_debate_cli_is_importable() -> None:
    module = import_module("debate_cli")
    assert module.__name__ == "debate_cli"


def test_debate_cli_is_typed() -> None:
    assert files("debate_cli").joinpath("py.typed").is_file()

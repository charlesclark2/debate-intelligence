"""Smoke test: debate_api is installed in the workspace, importable and ships type information."""

from importlib import import_module
from importlib.resources import files


def test_debate_api_is_importable() -> None:
    module = import_module("debate_api")
    assert module.__name__ == "debate_api"


def test_debate_api_is_typed() -> None:
    assert files("debate_api").joinpath("py.typed").is_file()

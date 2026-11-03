"""The committed example routing file, for tests that write a settings profile of their own.

The CLI loads and validates the routing file its settings name when it loads them, and refuses a
run whose file is missing or invalid (v1-e05-t03-fake-replay-models ac6). A test profile that only
exercises storage or caselist commands still has to name a routing file that loads, and this is
the one: `config/model_routing.example.yaml`, the default and template file, which every test of
the routing policy already holds to the schema.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["EXAMPLE_ROUTING_FILE"]

EXAMPLE_ROUTING_FILE = Path(__file__).resolve().parents[2] / "config" / "model_routing.example.yaml"
"""Absolute, so a profile naming it means the same file from any working directory."""

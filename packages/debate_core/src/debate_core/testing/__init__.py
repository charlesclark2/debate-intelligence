"""Test doubles that ship with the library.

They live in `debate_core` rather than under a `tests/` directory for two reasons: every package's
tests need them — `debate_cli`, `debate_api` and `debate_workers` each wire a service to fakes —
and the reusable repository contract suite lives here too, so that a V2 DynamoDB adapter is held
to the same contract as the V1 SQLite one.

Import from the submodule that defines a name; this package re-exports nothing:

* :mod:`debate_core.testing.fakes` — an in-memory implementation of every port.
* :mod:`debate_core.testing.builders` — builders that produce complete, valid domain entities
  from a handful of keyword arguments.
* :mod:`debate_core.testing.contracts` — the shared contract suites. They import pytest, so they
  are importable in a test environment and not in a running CLI or API.

This module imports nothing (v1-e01-t29). Importing any `debate_core.testing.*` module runs it,
so an import here would make every caller of every helper reach what that import reaches: `fakes`
alone reaches the caselist suppression code. `tests/architecture/test_package_inits_import_nothing.py`
keeps it that way.

Everything here is deterministic and offline. Nothing reads the clock, the filesystem or the
network.
"""

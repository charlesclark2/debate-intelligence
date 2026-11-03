"""Pure procedures over the arguments debaters read: what a position is called, and where it is read.

A layer beside `debate_core.evidence` and `debate_core.retrieval`: it sees only `debate_core.domain`,
does no I/O and calls no model, so the application layer can compose it and every rule in it can be
tested on invented input. E32's argument landscape is its first user (`debate_core.arguments.landscape`).
This module holds only a docstring; callers import from the submodule that defines a name.
"""

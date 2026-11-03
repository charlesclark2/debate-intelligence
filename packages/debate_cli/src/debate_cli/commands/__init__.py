"""One module per `debate-research` command; :mod:`debate_cli.command_registry` attaches them.

This file holds only this docstring. Importing `debate_cli.commands.verify` runs it first, so
anything it imported, every test of every command would import too (v1-e01-t32,
`tests/architecture/test_fakes_reach_only_their_port.py`).
"""

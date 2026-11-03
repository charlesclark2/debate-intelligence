"""Presenters: a service's result as the CLI shows it, the `--json` payload and the table, and nothing else.

A presenter decides no outcome. It reads a result the service already decided and says how a person and
a program each see it, including which :class:`~debate_cli.output.CommandFailure` an outcome that failed
is reported as.
"""

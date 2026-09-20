"""`debate-research` command-line interface: a thin surface over debate_core.

The package's own version is the one `debate-research --version` reports, read from the installed
distribution's metadata rather than repeated in the source, so `packages/debate_cli/pyproject.toml`
stays the single place it is written down. v1-e01-t09 extends what `--version` reports with the
release channel and commit.
"""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["DISTRIBUTION_NAME", "__version__", "package_version"]

DISTRIBUTION_NAME = "debate-cli"
"""The installed distribution that provides `debate-research`."""

UNKNOWN_VERSION = "0.0.0+unknown"
"""Reported when the code is being run from a source tree that was never installed."""


def package_version(distribution: str = DISTRIBUTION_NAME) -> str:
    """Return the installed version of `distribution`, or :data:`UNKNOWN_VERSION`.

    A missing distribution is not an error worth failing a command over: `doctor` reporting
    `0.0.0+unknown` for a package is itself the diagnosis.
    """
    try:
        return version(distribution)
    except PackageNotFoundError:
        return UNKNOWN_VERSION


__version__ = package_version()

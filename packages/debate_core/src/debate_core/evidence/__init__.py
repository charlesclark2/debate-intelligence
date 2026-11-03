"""Evidence handling: normalization, hashing, verification and debate-file style rules.

The domain layer (`debate_core.domain`) holds the shapes; this package holds the procedures that
read and write them. It may read files that ship inside the package — the style profiles are data
files, not configuration — but it still makes no network calls and touches no cloud SDK.

Import from the submodule that defines a name (`debate_core.evidence.normalization`,
`debate_core.evidence.style_profile_loader`, ...); this package re-exports nothing. It imports
nothing either (v1-e01-t29): importing any `debate_core.evidence.*` module runs it, so an import
here would make every caller of every evidence module reach, say, the style classifier.
`tests/architecture/test_package_inits_import_nothing.py` keeps it that way.
"""

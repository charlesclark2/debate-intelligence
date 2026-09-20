"""Evidence handling: normalization, hashing, verification and debate-file style rules.

The domain layer (`debate_core.domain`) holds the shapes; this package holds the procedures that
read and write them. It may read files that ship inside the package — the style profiles below
are data files, not configuration — but it still makes no network calls and touches no cloud SDK.
"""

from debate_core.evidence.style_classifier import (
    ParagraphDescription,
    RunDescription,
    classify_paragraph,
    classify_run,
)
from debate_core.evidence.style_profile_loader import (
    DEFAULT_STYLE_PROFILE_NAME,
    StyleProfileError,
    available_style_profiles,
    load_style_profile,
    load_style_profile_from_text,
    resolve_based_on_chain,
)

__all__ = [
    "DEFAULT_STYLE_PROFILE_NAME",
    "ParagraphDescription",
    "RunDescription",
    "StyleProfileError",
    "available_style_profiles",
    "classify_paragraph",
    "classify_run",
    "load_style_profile",
    "load_style_profile_from_text",
    "resolve_based_on_chain",
]

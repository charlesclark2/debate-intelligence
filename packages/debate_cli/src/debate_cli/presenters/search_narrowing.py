"""What `search` prints to narrow a search: lines after the footer, and `narrowing` in the JSON (v1-e08-t15).

Rendering only. Which subjects a page suggests, in which order, is `debate_core`'s
(:mod:`debate_core.application.search_narrowing`); this module turns each suggestion into a command a
student can copy from the screen and paste:

```text
Narrow it: subjects OpenAlex gave 2 or more of these 20 results
  conservation ethics, on 5:  debate-research search 'de-extinction conservation ethics'
```

**The command** is the student's own search with the subject's words added to the query, keeping
`--since`, `--until`, `--max-results` (when not the default 20), `--topic` and `--providers`, in the
order `search --help` lists them. Nothing else is carried: an expanded search suggests nothing, and
`--save`, `--auto-cut` and the output options are the student's to add.

**Quoting** (the PM's ruling of 2026-11-12). The query is one word in single quotes, in which zsh, bash
and sh take every character as written, `$`, backquotes and `!` included. An apostrophe ends the
quote, is written `\\'` and opens it again (`'nature'\\''s value'`). A query holding a character that
would not paste as shown (a newline, a tab, a control or invisible character: anything
`str.isprintable` refuses) gets no command, and its line names the subject alone: a command that
would break is never printed. A query starting with `-` follows `--`, so it is not read as an option.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final

from debate_cli.output import JsonValue
from debate_core.application.federated_search_types import SearchOutcome
from debate_core.application.search_narrowing import MIN_RESULTS, NarrowingSuggestion

__all__ = ["DEFAULT_MAX_RESULTS", "SearchCommandLine", "narrowing_json", "narrowing_lines", "shell_word"]

DEFAULT_MAX_RESULTS: Final = 20
"""`search --max-results`'s default, left out of a suggested command."""

PROGRAM: Final = "debate-research"


def shell_word(text: str) -> str | None:
    """`text` as one single-quoted shell word, or None when a character in it would not paste as shown."""
    if not text.isprintable():
        return None
    return "'" + text.replace("'", "'\\''") + "'"


@dataclass(frozen=True, slots=True)
class SearchCommandLine:
    """The options of the student's search that a narrower search keeps."""

    since: date | None = None
    until: date | None = None
    max_results: int = DEFAULT_MAX_RESULTS
    providers: tuple[str, ...] | None = None
    topic: str | None = None

    def options(self) -> list[str]:
        """The kept options as words, in `search --help`'s order; each value is printable plain text."""
        kept: list[str] = []
        if self.since is not None:
            kept += ["--since", self.since.isoformat()]
        if self.until is not None:
            kept += ["--until", self.until.isoformat()]
        if self.max_results != DEFAULT_MAX_RESULTS:
            kept += ["--max-results", str(self.max_results)]
        if self.topic is not None:
            kept += ["--topic", self.topic]
        if self.providers:
            kept += ["--providers", ",".join(self.providers)]
        return kept

    def for_query(self, query: str) -> str | None:
        """The search command for `query` with these options, or None when `query` would not paste."""
        word = shell_word(query)
        if word is None:
            return None
        options: list[str] = []
        for value in self.options():
            option = value if _plain(value) else shell_word(value)
            if option is None:
                return None
            options.append(option)
        if query.startswith("-"):
            return " ".join([PROGRAM, "search", *options, "--", word])
        return " ".join([PROGRAM, "search", word, *options])


def _plain(value: str) -> bool:
    """Whether a word pastes as it is: only the ASCII letters, digits and `-_.,:` an option, a date, a
    number, a topic id or a provider list is written with. Anything else is quoted."""
    return bool(value) and all(
        character.isascii() and (character.isalnum() or character in "-_.,:") for character in value
    )


def narrowing_lines(
    outcome: SearchOutcome, suggestions: Sequence[NarrowingSuggestion], command_line: SearchCommandLine
) -> list[str]:
    """The lines after the footer: a heading, then one per suggestion; none when there is none."""
    if not suggestions:
        return []
    shown = len(outcome.ranked_candidates)
    lines = [f"Narrow it: subjects OpenAlex gave {MIN_RESULTS} or more of these {shown} results"]
    for suggestion in suggestions:
        line = f"  {suggestion.subject.name}, on {suggestion.results}"
        command = command_line.for_query(suggestion.query)
        lines.append(line if command is None else f"{line}:  {command}")
    return lines


def narrowing_json(
    suggestions: Sequence[NarrowingSuggestion], command_line: SearchCommandLine
) -> list[JsonValue]:
    """`narrowing` in the JSON: each suggestion's subject, scheme, id, count, best rank, query and command."""
    return [
        {
            "subject": suggestion.subject.name,
            "scheme": suggestion.subject.scheme.value,
            "id": suggestion.subject.provider_id,
            "results": suggestion.results,
            "best_rank": suggestion.best_rank,
            "query": suggestion.query,
            "command": command_line.for_query(suggestion.query),
        }
        for suggestion in suggestions
    ]

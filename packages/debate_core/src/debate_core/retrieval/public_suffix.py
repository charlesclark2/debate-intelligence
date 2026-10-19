r"""Registrable domains, from a pinned snapshot of the Public Suffix List.

"Same site" for a rel=canonical link (`canonical_url.apply_rel_canonical`) means the same
*registrable domain*: the public suffix plus one label. `www.bbc.co.uk` and `news.bbc.co.uk` are one
site because `co.uk` is a public suffix; `alice.github.io` and `bob.github.io` are two, because
`github.io` is one too. No rule of thumb about the last two labels gets both right, so the answer
comes from the list browsers use (https://publicsuffix.org), ICANN and private sections both.

**The list is a file in this package, never fetched.** `data/public_suffix_list.dat` is the list
exactly as publicsuffix.org published it, and `data/public_suffix_list.dat.sha256` pins its bytes
in `shasum -a 256` format. The list's own header names its version and the commit of
github.com/publicsuffix/list it was built from (`// VERSION:` and `// COMMIT:`), and
`bundled_public_suffix_rules()` reports both. Nothing here downloads, refreshes or caches a newer
copy, on import, on first use or ever, because a different list could make a stored canonical URL
stop agreeing with the rule that produced it. The list is Mozilla Public License 2.0, a file-level
licence: the file keeps its own header and terms, and nothing else in the package is affected.

**Refreshing it** is a deliberate pull request, never an automatic one. The list's maintainers ask
that it be pulled only from https://publicsuffix.org/list/public_suffix_list.dat. From the
repository root, this one command replaces the file and rewrites its hash together:

    cd packages/debate_core/src/debate_core/retrieval/data && \
      curl --fail --silent --show-error --output public_suffix_list.dat \
        https://publicsuffix.org/list/public_suffix_list.dat && \
      shasum -a 256 public_suffix_list.dat > public_suffix_list.dat.sha256

Back at the repository root, run `uv run pytest packages/debate_core/tests/retrieval` and commit both
files in one pull request that names the new `// VERSION:` line. The pin test fails if either file
changes without the other. The project's test vectors in `test_public_suffix.py` were transcribed
at the old commit; if one now fails, the list changed a rule they cover, so read the list's
history before changing the expectation.

The algorithm is the list's own (https://github.com/publicsuffix/list/wiki/Format): an exception
rule (`!www.ck`) beats everything, otherwise the matching rule with the most labels wins, a
wildcard (`*.ck`) matches exactly one label, and a host no rule matches has its last label as its
public suffix. Hosts and rules are compared in ASCII (punycode), lower case.
"""

from __future__ import annotations

import functools
import ipaddress
from dataclasses import dataclass
from importlib import resources

import idna

__all__ = [
    "PUBLIC_SUFFIX_LIST_FILE",
    "PUBLIC_SUFFIX_LIST_HASH_FILE",
    "PublicSuffixRules",
    "ascii_hostname",
    "bundled_public_suffix_rules",
    "parse_public_suffix_list",
    "registrable_domain",
]

PUBLIC_SUFFIX_LIST_FILE = "data/public_suffix_list.dat"
PUBLIC_SUFFIX_LIST_HASH_FILE = "data/public_suffix_list.dat.sha256"
_VERSION_MARKER = "// VERSION:"
_COMMIT_MARKER = "// COMMIT:"


@dataclass(frozen=True, slots=True)
class PublicSuffixRules:
    """The list's rules, in ASCII lower case.

    `wildcards` holds what follows `*.` and `exceptions` what follows `!`, so a lookup is a set
    membership test on a suffix of the host's labels.
    """

    exact: frozenset[str]
    wildcards: frozenset[str]
    exceptions: frozenset[str]
    version: str | None
    commit: str | None


def ascii_hostname(host: str) -> str:
    """A host name in the ASCII form hosts are compared in: lower case, punycode, no trailing dot.

    Mapping is UTS #46 with nontransitional processing, the WHATWG URL Standard's choice, so
    `faß.de` stays `xn--fa-hia.de` rather than becoming `fass.de`. That is idna's only behaviour:
    its `transitional` argument defaults to off and, since UTS #46 dropped transitional processing
    in Unicode 15.1, is ignored. ASCII labels are only lowered,
    which keeps real hosts with an underscore (IDNA 2008 forbids it in a U-label) usable.

    Raises `idna.IDNAError` for a label that cannot be encoded.
    """
    host = host.rstrip(".")
    if host.isascii():
        return host.lower()
    mapped = idna.uts46_remap(host, std3_rules=False)
    return ".".join(
        label if label.isascii() else idna.alabel(label).decode("ascii") for label in mapped.split(".")
    )


def parse_public_suffix_list(text: str) -> PublicSuffixRules:
    """Read the list's published format: one rule per line, `//` comments, blank lines ignored."""
    exact: set[str] = set()
    wildcards: set[str] = set()
    exceptions: set[str] = set()
    version: str | None = None
    commit: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith(_VERSION_MARKER):
            version = line.removeprefix(_VERSION_MARKER).strip()
            continue
        if line.startswith(_COMMIT_MARKER):
            commit = line.removeprefix(_COMMIT_MARKER).strip()
            continue
        if not line or line.startswith("//"):
            continue
        if line.startswith("!"):
            exceptions.add(ascii_hostname(line[1:]))
        elif line.startswith("*."):
            wildcards.add(ascii_hostname(line[2:]))
        else:
            exact.add(ascii_hostname(line))
    return PublicSuffixRules(frozenset(exact), frozenset(wildcards), frozenset(exceptions), version, commit)


@functools.cache
def bundled_public_suffix_rules() -> PublicSuffixRules:
    """The pinned snapshot, read from this package once per process."""
    text = (
        resources.files("debate_core.retrieval").joinpath(PUBLIC_SUFFIX_LIST_FILE).read_text(encoding="utf-8")
    )
    return parse_public_suffix_list(text)


def _is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host.removeprefix("[").removesuffix("]"))
    except ValueError:
        return False
    return True


def _public_suffix_length(labels: list[str], rules: PublicSuffixRules) -> int:
    """How many trailing labels of the host form its public suffix."""
    for start in range(len(labels)):
        if ".".join(labels[start:]) in rules.exceptions:
            return len(labels) - start - 1
    for start in range(len(labels)):
        if ".".join(labels[start:]) in rules.exact:
            return len(labels) - start
        if ".".join(labels[start + 1 :]) in rules.wildcards:
            return len(labels) - start
    return 1


def registrable_domain(host: str, rules: PublicSuffixRules | None = None) -> str | None:
    """The host's public suffix plus one label, in ASCII; None if there is no such domain.

    None for an IP address, for a host that is itself a public suffix (`co.uk`, `github.io`), and
    for a host that is empty, has an empty label or cannot be encoded.
    """
    if not host or _is_ip_address(host):
        return None
    try:
        name = ascii_hostname(host)
    except idna.IDNAError:
        return None
    labels = name.split(".")
    if "" in labels:
        return None
    suffix_length = _public_suffix_length(labels, rules or bundled_public_suffix_rules())
    if len(labels) <= suffix_length:
        return None
    return ".".join(labels[-(suffix_length + 1) :])

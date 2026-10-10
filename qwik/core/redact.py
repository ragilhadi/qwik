"""Secret-shaped command detection for ``qwik suggest``.

Shell history routinely contains credentials: ``mysql -p s3cret``,
``gh auth login --with-token <(...)`` lines, ``export API_KEY=...``,
cloud-CLI tokens, and so on. ``qwik suggest`` must never propose an
alias for (or even display) a command matching one of these shapes.

This module is pure pattern matching: no I/O, no network. The corpus of
shapes lives in :data:`REDACT_PATTERNS` (regexes) plus a couple of
structural checks in :func:`contains_secret`. Unit-tested against a
corpus in ``tests/test_redact.py``.
"""

from __future__ import annotations

import re

__all__ = [
    "REDACT_PATTERNS",
    "contains_secret",
    "redact_command",
]


# Common secret shapes. Each pattern is case-insensitive where flags
# allow; compiled once at import.
REDACT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in [
        # Explicit secret-ish flags and their values (whole token and
        # anything following): --password, --token, --secret, -p <val>
        r"(?:^|\s)--?(?:password|passwd|pwd|token|secret|secret-key|api-key|apikey|access-token|auth-user-pass|with-token)(?:\s|$|=)",
        r"(?:^|\s)-p\s+\S",  # -p followed by anything (password in many CLIs)
        # AWS access key ids and secret keys
        r"AKIA[0-9A-Z]{16}",
        r"secret[_-]?access[_-]?key",
        r"aws[_a-z]*(?:access[_-]?key[_-]?id|secret[_-]?key)[a-z_]*\s*=",
        # env-var assignments carrying secret-looking names
        r"(?:^|\s)(?:export\s+)?[A-Za-z0-9_]*(?:PASSWORD|PASSWD|TOKEN|SECRET|API[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIAL)[A-Za-z0-9_]*\s*=",
        # auth headers and credential-bearing URL/userinfo shapes
        r"authorization\s*:\s*bearer\s+\S+",
        r"://[^/@\s:]+:[^@\s]+@",  # scheme://user:pass@host
        r"(?:^|\s)-u\s+\S+:\S+",  # curl -u user:pass
        # long opaquish tokens passed around
        r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}",  # GitHub tokens
        r"glpat-[A-Za-z0-9_-]{20,}",  # GitLab PATs
        r"xox[bpars]-[A-Za-z0-9-]{10,}",  # Slack tokens
        r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}",  # OpenAI-style keys
        r"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}",  # JWT
        # ssh private keys referenced on the command line
        r"(?:^|\s)===?\s*BEGIN\s+(?:RSA\s+|OPENSSH\s+)?PRIVATE\s+KEY",
        r"(?:^|\s)-i\s+\S*id_rsa",
        r"(?:^|\s)id_rsa(?:\s|$)",
        # sshpass is never anything but a password
        r"(?:^|\s)sshpass(?:\s|$)",
        # .netrc / credentials files
        r"netrc",
    ]
)

# Commands that are inherently secret-handling regardless of arguments.
_SECRET_WORDS: tuple[str, ...] = (
    "gpg --passphrase",
    "security add-generic-password",
    "keytool -storepass",
    "openssl passwd",
    "user-secrets",
    "create secret",
)


def contains_secret(command: str) -> bool:
    """Return ``True`` when *command* looks like it carries a secret.

    Deliberately over-inclusive: a false positive costs one command that
    never gets a suggested alias, while a false negative puts a
    credential into a suggestion list.

    Args:
        command: The raw command line from history.

    Returns:
        ``True`` if any pattern or secret-word heuristic matches.
    """
    lowered = command.lower()
    for pattern in REDACT_PATTERNS:
        if pattern.search(command):
            return True
    return any(word in lowered for word in _SECRET_WORDS)


def redact_command(command: str, *, max_length: int = 32) -> str:
    """Return a printable placeholder for a redacted command.

    Args:
        command: The raw command (never rendered as-is by callers).
        max_length: Cap on the echoed prefix.

    Returns:
        A short, clearly-redacted string such as ``<redacted: mysql …>``.
    """
    first_word = command.split(maxsplit=1)[0] if command.split() else "command"
    if len(first_word) > max_length:
        first_word = first_word[:max_length] + "…"
    return f"<redacted {first_word}>"

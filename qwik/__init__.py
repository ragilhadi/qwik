"""A friendly CLI alias manager."""

import sys
from typing import Any

# On Windows the default stdio encoding is the OEM codepage (cp1252 on
# en-US hosts), which cannot represent the Unicode glyphs Rich emits
# (✓ U+2713, → U+2192, ⚠ U+26A0). When output is piped (no TTY) Rich still
# writes to sys.stdout and crashes with UnicodeEncodeError. Force UTF-8
# so qwik's output is safe to capture from any shell, including the
# pwsh integration test that pipes `qwik run` through a subprocess.
def _force_utf8(stream: Any) -> None:
    enc = getattr(stream, "encoding", None)
    if enc and enc.lower() not in {"utf-8", "utf8"}:
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


_force_utf8(sys.stdout)
_force_utf8(sys.stderr)

__version__ = "0.3.1"

"""
voice-mode - Voice interaction capabilities for Model Context Protocol (MCP) servers

This package provides MCP servers for voice interactions through multiple transports:
- Local microphone recording and playback
- Configurable OpenAI-compatible STT/TTS services
"""

import sys
import warnings

# Third-party pydub ships invalid escape sequences that emit SyntaxWarning at
# compile time; filter before anything imports it.
warnings.filterwarnings("ignore", category=SyntaxWarning)

# Legacy Windows code pages (cp1252) cannot encode the emoji/unicode used in
# output. Reconfigure in place; nothing is written to the streams.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        _reconfigure = getattr(_stream, "reconfigure", None)
        if _reconfigure is not None:
            try:
                _reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

from .version import __version__

__all__ = [
    "__version__",
]
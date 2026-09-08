"""MCP resources for voice discovery.

Exposes two resources:

* ``voice://voices`` — full list of TTS voices the server can produce.
* ``voice://voices/{provider}`` — same envelope, filtered to entries
  whose ``provider`` matches the path segment.

Both return ``application/json``. The body is
``{schema_version, generated_at, voices[]}`` per the locked v1 schema in
the task README.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..server import mcp
from ..voices import enumerate_voices

_SCHEMA_VERSION = 1


def _now_iso() -> str:
    """ISO 8601 UTC timestamp with the ``Z`` suffix."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


async def _build_response() -> dict[str, Any]:
    voices = await enumerate_voices()
    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "voices": voices,
    }


@mcp.resource("voice://voices", mime_type="application/json")
async def list_voices() -> dict[str, Any]:
    """JSON list of TTS voices the server can produce.

    Envelope: ``{schema_version, generated_at, voices[]}``. Each entry
    has ``id`` (``{provider}:{voice}``), ``voice``, ``name``, ``provider``,
    ``language``, ``gender``, ``preview_url``.
    """
    return await _build_response()


@mcp.resource("voice://voices/{provider}", mime_type="application/json")
async def list_voices_for_provider(provider: str) -> dict[str, Any]:
    """Same envelope as ``voice://voices``, filtered to one provider.

    Filters ``voices[]`` to entries with ``provider == {provider}``. An
    unknown provider yields an empty ``voices`` list — the envelope is
    well-formed either way.
    """
    body = await _build_response()
    body["voices"] = [v for v in body["voices"] if v.get("provider") == provider]
    return body

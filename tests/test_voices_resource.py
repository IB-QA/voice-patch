"""Tests for the ``voice://voices`` and ``voice://voices/{provider}`` resources.

Covers the locked v1 envelope, the per-provider filter, and resource
registration. Both handlers are called directly; the over-the-wire
streamable-HTTP path is covered in ``test_voices_resource_http.py``.
"""

import json
from datetime import datetime

import pytest

from voice_mode.resources.voices import (
    list_voices,
    list_voices_for_provider,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_voice(provider, voice):
    return {
        "id": f"{provider}:{voice}",
        "voice": voice,
        "name": voice,
        "provider": provider,
        "language": None,
        "gender": None,
        "preview_url": None,
    }


@pytest.fixture
def patched_enum(monkeypatch):
    """Replace ``enumerate_voices`` with a controllable async fake."""
    voices = [
        _make_voice("openai", "alloy"),
        _make_voice("kokoro", "af_alpha"),
    ]

    async def fake_enum():
        return list(voices)

    monkeypatch.setattr("voice_mode.resources.voices.enumerate_voices", fake_enum)
    return voices


# ---------- voice://voices envelope ---------------------------------------


async def test_list_voices_returns_locked_envelope(patched_enum):
    body = await getattr(list_voices, "fn", list_voices)()

    assert body["schema_version"] == 1
    assert isinstance(body["generated_at"], str)
    # generated_at parses as ISO 8601 (use the same Z→+00:00 swap).
    parsed = datetime.fromisoformat(body["generated_at"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert isinstance(body["voices"], list)
    assert all(
        {"id", "voice", "name", "provider", "language", "gender", "preview_url"}
        <= v.keys()
        for v in body["voices"]
    )


async def test_list_voices_response_carries_no_raw_urls(patched_enum):
    """AC4: no ``http://`` / ``https://`` substrings anywhere in the body."""
    body = await getattr(list_voices, "fn", list_voices)()

    serialized = json.dumps(body)
    assert "http://" not in serialized
    assert "https://" not in serialized


# ---------- voice://voices/{provider} filter ------------------------------


async def test_per_provider_filter_returns_only_matching(patched_enum):
    body = await getattr(list_voices_for_provider, "fn", list_voices_for_provider)(
        provider="openai"
    )

    assert body["schema_version"] == 1
    assert all(v["provider"] == "openai" for v in body["voices"])
    assert len(body["voices"]) == 1


async def test_per_provider_filter_empty_for_unknown_provider(patched_enum):
    body = await getattr(list_voices_for_provider, "fn", list_voices_for_provider)(
        provider="never-heard-of-it"
    )

    assert body["voices"] == []
    assert body["schema_version"] == 1


async def test_per_provider_envelope_matches_unfiltered(patched_enum):
    """Per-provider response carries the same envelope keys as the unfiltered one."""
    full = await getattr(list_voices, "fn", list_voices)()
    one = await getattr(list_voices_for_provider, "fn", list_voices_for_provider)(
        provider="kokoro"
    )

    assert set(full.keys()) == set(one.keys())
    assert full["schema_version"] == one["schema_version"]


# ---------- registration sanity check -------------------------------------


async def test_resources_register_with_expected_uris():
    """Both resources are loaded into the FastMCP instance with mime_type=json."""
    # FastMCP 3.x: @mcp.resource decorator returns the raw function, so we
    # query the server for registered resources rather than introspecting
    # the decorated objects directly. (In 2.x the decorator returned a
    # wrapper exposing .uri / .mime_type / .uri_template.)
    from voice_mode.server import mcp

    static = {str(r.uri): r for r in await mcp.list_resources()}
    assert "voice://voices" in static
    assert static["voice://voices"].mime_type == "application/json"

    templates = {str(t.uri_template): t for t in await mcp.list_resource_templates()}
    assert any("voice://voices/{provider}" in u for u in templates)
    template = next(
        t for u, t in templates.items() if "voice://voices/{provider}" in u
    )
    assert template.mime_type == "application/json"

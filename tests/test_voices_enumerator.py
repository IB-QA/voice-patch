"""Tests for ``voice_mode/voices.py`` — the ``enumerate_voices()`` helper.

Covers AC11 cases: empty / single / multi / no-voices / unhealthy
providers, and cross-provider id collision.

``asyncio_mode = "auto"`` in ``pyproject.toml`` means async test
functions run automatically — no ``@pytest.mark.asyncio`` needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest


@pytest.fixture(autouse=True)
def _reset_voice_cache():
    """Clear the in-process enumerate_voices cache between tests."""
    from voice_mode import voices

    voices._reset_cache()
    yield
    voices._reset_cache()


@pytest.fixture
def voices_mod():
    from voice_mode import voices

    return voices


def _entry_ids(entries):
    return [e["id"] for e in entries]


# ---------- shape & basic enumeration --------------------------------------


async def test_empty_tts_base_urls_no_impressions(voices_mod, monkeypatch):
    monkeypatch.setattr(voices_mod, "TTS_BASE_URLS", [])

    result = await voices_mod.enumerate_voices()

    assert result == []


async def test_single_kokoro_provider(voices_mod, monkeypatch):
    monkeypatch.setattr(voices_mod, "TTS_BASE_URLS", ["http://127.0.0.1:8880/v1"])
    monkeypatch.setattr(
        voices_mod, "_fetch_audio_voices",
        AsyncMock(return_value=["af_beta", "af_alpha"]),
    )

    result = await voices_mod.enumerate_voices()

    assert _entry_ids(result) == ["kokoro:af_alpha", "kokoro:af_beta"]
    for e in result:
        assert e["provider"] == "kokoro"
        assert e["language"] is None
        assert e["gender"] is None
        assert e["preview_url"] is None
        assert e["name"] == e["voice"]


async def test_multiple_providers_in_config_order(voices_mod, monkeypatch):
    """TTS_BASE_URLS order is the outer order; alphabetical within each provider."""
    monkeypatch.setattr(voices_mod, "TTS_BASE_URLS", [
        "http://127.0.0.1:8880/v1",       # kokoro
        "https://api.openai.com/v1",      # openai
    ])
    monkeypatch.setattr(
        voices_mod, "_fetch_audio_voices",
        AsyncMock(return_value=["af_beta", "af_alpha"]),
    )

    result = await voices_mod.enumerate_voices()
    ids = _entry_ids(result)

    assert ids[:2] == ["kokoro:af_alpha", "kokoro:af_beta"]
    openai_part = [i.split(":", 1)[1] for i in ids if i.startswith("openai:")]
    assert openai_part == sorted(voices_mod.OPENAI_TTS_VOICES, key=str.casefold)
    # Together: kokoro entries first, openai entries after.
    assert ids.index("kokoro:af_beta") < ids.index("openai:alloy")


async def test_provider_with_no_voices(voices_mod, monkeypatch):
    """An empty /audio/voices response simply yields no entries for that provider."""
    monkeypatch.setattr(voices_mod, "TTS_BASE_URLS", [
        "http://127.0.0.1:8880/v1",
        "https://api.openai.com/v1",
    ])
    monkeypatch.setattr(
        voices_mod, "_fetch_audio_voices",
        AsyncMock(return_value=[]),
    )

    ids = _entry_ids(await voices_mod.enumerate_voices())

    assert all(not i.startswith("kokoro:") for i in ids)
    assert any(i.startswith("openai:") for i in ids)


async def test_provider_unhealthy_silently_skipped(voices_mod, monkeypatch, caplog):
    """ConnectError on one endpoint must not block the rest (AC6)."""
    monkeypatch.setattr(voices_mod, "TTS_BASE_URLS", [
        "http://127.0.0.1:8880/v1",
        "https://api.openai.com/v1",
    ])
    monkeypatch.setattr(
        voices_mod, "_fetch_audio_voices",
        AsyncMock(side_effect=httpx.ConnectError("refused")),
    )

    with caplog.at_level("WARNING", logger="voicemode"):
        ids = _entry_ids(await voices_mod.enumerate_voices())

    assert all(not i.startswith("kokoro:") for i in ids)
    assert "openai:alloy" in ids   # openai is hardcoded, exempt from probe
    assert any("voice probe failed" in r.message for r in caplog.records)


async def test_id_collision_cross_provider(voices_mod, monkeypatch):
    """Same voice name from openai and kokoro — both appear with distinct ids (AC5)."""
    monkeypatch.setattr(voices_mod, "TTS_BASE_URLS", [
        "https://api.openai.com/v1",
        "http://127.0.0.1:8880/v1",
    ])
    monkeypatch.setattr(
        voices_mod, "_fetch_audio_voices",
        AsyncMock(return_value=["nova"]),
    )

    ids = _entry_ids(await voices_mod.enumerate_voices())

    assert "openai:nova" in ids
    assert "kokoro:nova" in ids
    assert ids.count("openai:nova") == 1
    assert ids.count("kokoro:nova") == 1


# ---------- caching ---------------------------------------------------------


async def test_cache_within_ttl_reuses_result(voices_mod, monkeypatch):
    monkeypatch.setattr(voices_mod, "TTS_BASE_URLS", ["http://127.0.0.1:8880/v1"])
    fetch = AsyncMock(return_value=["af_alpha"])
    monkeypatch.setattr(voices_mod, "_fetch_audio_voices", fetch)

    a = await voices_mod.enumerate_voices()
    b = await voices_mod.enumerate_voices()

    assert _entry_ids(a) == _entry_ids(b)
    assert fetch.await_count == 1


async def test_returned_list_is_isolated_from_cache(voices_mod, monkeypatch):
    """Mutating a returned list must not corrupt the cached one."""
    monkeypatch.setattr(voices_mod, "TTS_BASE_URLS", ["http://127.0.0.1:8880/v1"])
    monkeypatch.setattr(
        voices_mod, "_fetch_audio_voices", AsyncMock(return_value=["af_alpha"]),
    )

    a = await voices_mod.enumerate_voices()
    a.clear()
    b = await voices_mod.enumerate_voices()

    assert _entry_ids(b) == ["kokoro:af_alpha"]


def test_reset_cache_seam(voices_mod):
    voices_mod._cache = (0.0, [{"id": "stale:x"}])
    voices_mod._reset_cache()

    assert voices_mod._cache is None


# ---------- failure modes (design §5) --------------------------------------


async def test_malformed_json_logs_error_and_skips(voices_mod, monkeypatch, caplog):
    monkeypatch.setattr(voices_mod, "TTS_BASE_URLS", ["http://127.0.0.1:8880/v1"])
    monkeypatch.setattr(
        voices_mod, "_fetch_audio_voices",
        AsyncMock(side_effect=ValueError("expected JSON object")),
    )

    with caplog.at_level("ERROR", logger="voicemode"):
        result = await voices_mod.enumerate_voices()

    assert result == []
    assert any("malformed JSON" in r.message for r in caplog.records)


async def test_timeout_skipped_with_warning(voices_mod, monkeypatch, caplog):
    monkeypatch.setattr(voices_mod, "TTS_BASE_URLS", ["http://127.0.0.1:8880/v1"])
    monkeypatch.setattr(
        voices_mod, "_fetch_audio_voices",
        AsyncMock(side_effect=httpx.ReadTimeout("slow")),
    )

    with caplog.at_level("WARNING", logger="voicemode"):
        result = await voices_mod.enumerate_voices()

    assert result == []
    assert any("timeout" in r.message.lower() for r in caplog.records)


async def test_http_status_error_skipped_with_warning(voices_mod, monkeypatch, caplog):
    monkeypatch.setattr(voices_mod, "TTS_BASE_URLS", ["http://127.0.0.1:8880/v1"])
    request = httpx.Request("GET", "http://127.0.0.1:8880/v1/audio/voices")
    response = httpx.Response(503, request=request)
    monkeypatch.setattr(
        voices_mod, "_fetch_audio_voices",
        AsyncMock(side_effect=httpx.HTTPStatusError(
            "503", request=request, response=response,
        )),
    )

    with caplog.at_level("WARNING", logger="voicemode"):
        result = await voices_mod.enumerate_voices()

    assert result == []
    assert any("HTTP 503" in r.message for r in caplog.records)


async def test_whisper_endpoint_skipped_without_probe(voices_mod, monkeypatch):
    """detect_provider_type returns 'whisper' for ':2022' URLs — STT-only, no probe."""
    monkeypatch.setattr(voices_mod, "TTS_BASE_URLS", [
        "http://127.0.0.1:2022/v1",
        "https://api.openai.com/v1",
    ])
    fetch = AsyncMock(side_effect=AssertionError("whisper must not be probed"))
    monkeypatch.setattr(voices_mod, "_fetch_audio_voices", fetch)

    ids = _entry_ids(await voices_mod.enumerate_voices())

    assert all(not i.startswith("whisper:") for i in ids)
    assert "openai:alloy" in ids


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, payload, **_kwargs):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return None

    async def get(self, _url):
        return _FakeResponse(self._payload)


def _patch_async_client(monkeypatch, voices_mod, payload):
    def factory(**kwargs):
        return _FakeAsyncClient(payload, **kwargs)
    monkeypatch.setattr(voices_mod.httpx, "AsyncClient", factory)


async def test_fetch_audio_voices_parses_dict_voices_form(voices_mod, monkeypatch):
    _patch_async_client(monkeypatch, voices_mod, {"voices": ["alpha", {"id": "beta"}]})

    out = await voices_mod._fetch_audio_voices("http://x/v1")

    assert out == ["alpha", "beta"]


async def test_fetch_audio_voices_parses_bare_list_form(voices_mod, monkeypatch):
    _patch_async_client(monkeypatch, voices_mod, ["alpha", "beta"])

    out = await voices_mod._fetch_audio_voices("http://x/v1")

    assert out == ["alpha", "beta"]


async def test_fetch_audio_voices_rejects_unexpected_shape(voices_mod, monkeypatch):
    _patch_async_client(monkeypatch, voices_mod, 42)

    with pytest.raises(ValueError):
        await voices_mod._fetch_audio_voices("http://x/v1")

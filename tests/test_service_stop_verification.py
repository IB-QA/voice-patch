"""Stop must be verified against the port, not the exit code of the stop request.

Observed failure (macOS, hung Kokoro): `launchctl unload` returned 0 and
`stop_service` reported "✅ Kokoro stopped", but the uvicorn process was wedged
in an uninterruptible wait and kept its listening socket. `restart_service`
then called `start_service`, which found the port occupied and answered
"already running" -- so a restart that fixed nothing looked like it worked.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from voice_mode.tools.service import (
    _confirm_port_released,
    restart_service,
    stop_service,
)


def _fake_proc(pid=4242):
    return SimpleNamespace(pid=pid)


class TestConfirmPortReleased:
    @pytest.mark.asyncio
    async def test_returns_none_when_port_free(self):
        with patch("voice_mode.tools.service.find_process_by_port", return_value=None):
            assert await _confirm_port_released("kokoro", 8090) is None

    @pytest.mark.asyncio
    async def test_reports_pid_when_port_still_held(self):
        with patch(
            "voice_mode.tools.service.find_process_by_port",
            return_value=_fake_proc(51221),
        ):
            error = await _confirm_port_released("kokoro", 8090, timeout=0)

        assert error is not None
        assert error.startswith("❌")
        assert "51221" in error
        assert "8090" in error

    @pytest.mark.asyncio
    async def test_tolerates_slow_release(self):
        """A process that exits during the grace window is still a clean stop."""
        calls = {"n": 0}

        def releases_on_third_poll(_port):
            calls["n"] += 1
            return _fake_proc() if calls["n"] < 3 else None

        with patch(
            "voice_mode.tools.service.find_process_by_port",
            side_effect=releases_on_third_poll,
        ):
            assert await _confirm_port_released("kokoro", 8090, timeout=5) is None
        assert calls["n"] == 3


class TestStopServiceVerifies:
    @pytest.mark.asyncio
    async def test_launchctl_success_does_not_imply_stopped(self, tmp_path):
        """The regression: unload returns 0 while the process keeps the port."""
        plist = tmp_path / "Library" / "LaunchAgents" / "com.voicemode.kokoro.plist"
        plist.parent.mkdir(parents=True)
        plist.touch()

        with patch("voice_mode.tools.service.platform.system", return_value="Darwin"), \
             patch("voice_mode.tools.service.Path.home", return_value=tmp_path), \
             patch("voice_mode.tools.service.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="", stderr="")), \
             patch("voice_mode.tools.service.find_process_by_port",
                   return_value=_fake_proc(51221)), \
             patch("voice_mode.tools.service.asyncio.sleep", new=_instant_sleep):
            result = await stop_service("kokoro")

        assert result.startswith("❌"), f"claimed success while port held: {result!r}"
        assert "51221" in result

    @pytest.mark.asyncio
    async def test_launchctl_success_reports_stopped_when_port_freed(self, tmp_path):
        plist = tmp_path / "Library" / "LaunchAgents" / "com.voicemode.kokoro.plist"
        plist.parent.mkdir(parents=True)
        plist.touch()

        with patch("voice_mode.tools.service.platform.system", return_value="Darwin"), \
             patch("voice_mode.tools.service.Path.home", return_value=tmp_path), \
             patch("voice_mode.tools.service.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="", stderr="")), \
             patch("voice_mode.tools.service.find_process_by_port", return_value=None):
            result = await stop_service("kokoro")

        assert result == "✅ Kokoro stopped"


class TestRestartSkipsStartAfterFailedStop:
    @pytest.mark.asyncio
    async def test_start_not_attempted_when_stop_failed(self):
        start = MagicMock()

        async def failed_stop(_name):
            return "❌ Kokoro did not stop: PID 51221 still holds port 8090"

        with patch("voice_mode.tools.service.stop_service", new=failed_stop), \
             patch("voice_mode.tools.service.start_service", new=start):
            result = await restart_service("kokoro")

        start.assert_not_called()
        assert "Start skipped" in result

    @pytest.mark.asyncio
    async def test_start_attempted_after_clean_stop(self):
        async def clean_stop(_name):
            return "✅ Kokoro stopped"

        async def started(_name):
            return "✅ Kokoro started"

        with patch("voice_mode.tools.service.stop_service", new=clean_stop), \
             patch("voice_mode.tools.service.start_service", new=started), \
             patch("voice_mode.tools.service.asyncio.sleep", new=_instant_sleep):
            result = await restart_service("kokoro")

        assert "✅ Kokoro started" in result


async def _instant_sleep(_seconds):
    """Keep the grace-window polling out of the test runtime."""
    return None

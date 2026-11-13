"""The `service install` group must expose per-service options and keep old invocations working."""
from click.testing import CliRunner

from voice_mode.cli import voice_mode_main_cli


def _help(*args):
    result = CliRunner().invoke(voice_mode_main_cli, ["service", "install", *args, "--help"])
    assert result.exit_code == 0, result.output
    return result.output


def test_group_lists_every_service():
    out = _help()
    for name in ("whisper", "kokoro", "voicemode", "mlx-audio", "livekit"):
        assert name in out


def test_whisper_help_lists_models_and_gpu_flags():
    out = _help("whisper")
    for token in ("large-v3-turbo", "--model", "--use-gpu", "--no-gpu", "--no-model", "--scope"):
        assert token in out


def test_kokoro_help_offers_device_choice():
    out = _help("kokoro")
    assert "--device" in out and "gpu" in out


def test_whisper_install_passes_model_and_gpu(monkeypatch):
    seen = {}

    async def fake_install(**kwargs):
        seen.update(kwargs)
        return {"success": True, "model": kwargs["model"]}

    import voice_mode.tools.whisper.install as mod

    monkeypatch.setattr(mod, "whisper_install", fake_install)
    result = CliRunner().invoke(
        voice_mode_main_cli,
        ["service", "install", "whisper", "--model", "large-v3-turbo", "--no-gpu"],
    )
    assert result.exit_code == 0, result.output
    assert seen["model"] == "large-v3-turbo" and seen["use_gpu"] is False


def test_kokoro_install_passes_device(monkeypatch):
    seen = {}

    async def fake_install(**kwargs):
        seen.update(kwargs)
        return {"success": True}

    import voice_mode.tools.kokoro.install as mod

    monkeypatch.setattr(mod, "kokoro_install", fake_install)
    result = CliRunner().invoke(voice_mode_main_cli, ["service", "install", "kokoro", "--device", "cpu"])
    assert result.exit_code == 0, result.output
    assert seen["device"] == "cpu"

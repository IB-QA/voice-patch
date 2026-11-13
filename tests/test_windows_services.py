"""Windows service backend: scope selection, task registration, templates."""

from pathlib import Path

import pytest

from voice_mode.utils.services import windows as win
from voice_mode.utils.services import windows_install as wi


@pytest.fixture(autouse=True)
def _clean_scope_env(monkeypatch):
    monkeypatch.delenv(win.SCOPE_ENV_VAR, raising=False)


def test_auto_scope_follows_elevation(monkeypatch):
    monkeypatch.setattr(win, "is_admin", lambda: True)
    assert win.resolve_scope() == win.ServiceScope.MACHINE
    monkeypatch.setattr(win, "is_admin", lambda: False)
    assert win.resolve_scope("auto") == win.ServiceScope.USER


def test_machine_scope_without_elevation_is_refused_not_downgraded(monkeypatch):
    monkeypatch.setattr(win, "is_admin", lambda: False)
    with pytest.raises(win.ElevationRequired):
        win.resolve_scope("machine")


def test_user_scope_allowed_when_elevated_and_env_override(monkeypatch):
    monkeypatch.setattr(win, "is_admin", lambda: True)
    assert win.resolve_scope("user") == win.ServiceScope.USER
    monkeypatch.setenv(win.SCOPE_ENV_VAR, "user")
    assert win.resolve_scope() == win.ServiceScope.USER


def test_unknown_scope_rejected():
    with pytest.raises(ValueError):
        win.resolve_scope("everyone")


def test_machine_data_lives_in_programdata(monkeypatch):
    monkeypatch.setenv("ProgramData", r"C:\PD")
    assert win.base_dir(win.ServiceScope.MACHINE) == Path(r"C:\PD") / "VoiceMode"
    assert win.service_dir("whisper", win.ServiceScope.MACHINE).name == "whisper"


def test_task_names():
    assert win.task_name("whisper") == "VoiceMode-Whisper"
    assert win.task_name("voicemode") == "VoiceMode-Serve"


def test_user_task_runs_at_logon_unelevated():
    script = win.build_register_script("whisper", win.ServiceScope.USER, Path(r"C:\x\s.ps1"), "d")
    assert "-AtLogOn" in script
    assert "-RunLevel Limited" in script
    assert "SYSTEM" not in script


def test_machine_task_runs_at_boot_as_system():
    script = win.build_register_script("kokoro", win.ServiceScope.MACHINE, Path(r"C:\x\s.ps1"), "d")
    assert "-AtStartup" in script
    assert "-UserId 'SYSTEM'" in script
    assert "-AtLogOn" not in script


def test_register_machine_task_requires_elevation(monkeypatch):
    monkeypatch.setattr(win, "is_admin", lambda: False)
    with pytest.raises(win.ElevationRequired):
        win.register_task("whisper", win.ServiceScope.MACHINE, Path("x.ps1"))


@pytest.mark.parametrize("name", ["start-whisper-server.ps1", "start-kokoro.ps1", "start-voicemode-serve.ps1"])
def test_templates_are_packaged_and_never_evaluate_env_values(name):
    text = wi._read_template(name)
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    assert "Import-VoiceModeEnv" in text
    # voicemode.env is data, never code (GHSA-h97v-r3jw-cf6f)
    assert "Invoke-Expression" not in code
    assert "ExpandString" not in code


def test_whisper_asset_name_by_architecture(monkeypatch):
    monkeypatch.setattr(wi.platform, "machine", lambda: "AMD64")
    assert wi._whisper_asset_name() == "whisper-bin-x64.zip"
    monkeypatch.setattr(wi.platform, "machine", lambda: "ARM64")
    assert wi._whisper_asset_name() != "whisper-bin-x64.zip"


def test_release_lookup_falls_back_when_github_is_unreachable(monkeypatch):
    def boom(url):
        raise OSError("offline")

    monkeypatch.setattr(wi, "_http_json", boom)
    monkeypatch.setattr(wi.platform, "machine", lambda: "AMD64")
    release = wi.find_whisper_release_asset()
    assert release["tag"] == wi.WHISPER_FALLBACK_TAG
    assert release["url"].endswith("whisper-bin-x64.zip")


def test_release_lookup_skips_releases_without_the_windows_asset(monkeypatch):
    releases = [
        {"tag_name": "v9", "assets": []},
        {"tag_name": "b1", "assets": [{"name": "whisper-bin-x64.zip", "browser_download_url": "http://u/z"}]},
    ]
    monkeypatch.setattr(wi, "_http_json", lambda url: releases)
    monkeypatch.setattr(wi.platform, "machine", lambda: "AMD64")
    assert wi.find_whisper_release_asset()["tag"] == "b1"


@pytest.mark.skipif(not win.is_windows(), reason="Windows path layout")
def test_find_whisper_server_checks_windows_layout(tmp_path, monkeypatch):
    from voice_mode.utils.services import whisper_helpers

    exe = tmp_path / "services" / "whisper" / "bin" / "whisper-server.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(tmp_path))
    assert whisper_helpers.find_whisper_server() == str(exe)


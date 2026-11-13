"""Windows GPU/CPU variant selection for the local services."""
import platform

from voice_mode.utils.services import windows_install as wi


def test_whisper_asset_follows_gpu_choice(monkeypatch):
    monkeypatch.setattr(platform, "machine", lambda: "AMD64")
    assert wi._whisper_asset_name(gpu=False) == "whisper-bin-x64.zip"
    assert wi._whisper_asset_name(gpu=True) == wi.WHISPER_CUDA_ASSET


def test_arm_has_no_cuda_asset(monkeypatch):
    monkeypatch.setattr(platform, "machine", lambda: "ARM64")
    assert wi._whisper_asset_name(gpu=True) == "whisper-bin-win-cpu-arm64.zip"


def test_no_nvidia_smi_means_no_gpu(monkeypatch):
    monkeypatch.setattr(wi.shutil, "which", lambda _name: None)
    assert wi.nvidia_gpu_available() is False


def test_cuda_index_order_prefers_newest():
    assert wi.KOKORO_CUDA_INDEXES[0] > wi.KOKORO_CUDA_INDEXES[-1]

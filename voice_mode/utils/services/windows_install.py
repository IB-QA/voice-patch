"""Windows installers for the local speech services.

Linux and macOS compile whisper.cpp and register launchd/systemd units. On
Windows we instead:

* download the official prebuilt whisper.cpp release (no compiler needed),
* create Kokoro-FastAPI's virtualenv with uv and bundle eSpeak NG through the
  ``espeakng-loader`` wheel (no machine-wide installer needed),
* register a Task Scheduler task per service in the chosen scope
  (``user`` or ``machine``, see ``voice_mode.utils.services.windows``).

Every function returns the same ``{"success": bool, ...}`` dict shape the
POSIX installers use, so the CLI and MCP tool layers do not care which OS ran.
"""

from __future__ import annotations

import importlib.resources as resources
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

from voice_mode.utils.services import windows as win

logger = logging.getLogger("voicemode")

WHISPER_RELEASES_API = "https://api.github.com/repos/ggml-org/whisper.cpp/releases?per_page=30"
# Used when the GitHub API is unreachable or rate limited.
WHISPER_FALLBACK_TAG = "b5454"
KOKORO_REPO = "https://github.com/ai-cora/Kokoro-FastAPI.git"
# Newest first: cu128+ wheels carry Blackwell (sm_120) kernels; a driver too old for
# one CUDA generation fails the is_available() probe and the next index is tried.
KOKORO_CUDA_INDEXES = ("cu130", "cu128")
KOKORO_PYTHON = "3.12"  # Kokoro-FastAPI supports 3.10-3.12
FFMPEG_WINGET_ID = "Gyan.FFmpeg"


WHISPER_CUDA_ASSET = "whisper-bin-win-cuda-12.4.0-x64.zip"


def _whisper_asset_name(gpu: bool = False) -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "whisper-bin-win-cpu-arm64.zip"
    return WHISPER_CUDA_ASSET if gpu else "whisper-bin-x64.zip"


def nvidia_gpu_available() -> bool:
    """True when an NVIDIA driver answers nvidia-smi (needed for the CUDA builds)."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return False
    try:
        return subprocess.run([smi, "-L"], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def to_bool(value: Any) -> bool:
    """Coerce MCP-style 'true'/'false' strings to bool."""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _fail(error: str, **extra: Any) -> Dict[str, Any]:
    return {"success": False, "error": error, **extra}


def _read_template(name: str) -> str:
    return resources.files("voice_mode.templates.windows.scripts").joinpath(name).read_text(encoding="utf-8")


def _resolve_scope(scope: Optional[str]):
    """Return (ServiceScope, None) or (None, error_dict)."""
    try:
        return win.resolve_scope(scope), None
    except (win.ElevationRequired, ValueError) as exc:
        return None, _fail(str(exc), needs_elevation=isinstance(exc, win.ElevationRequired))


def _run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def _http_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "voicemode-installer"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def find_whisper_release_asset(gpu: bool = False) -> Dict[str, str]:
    """Locate the newest whisper.cpp release that ships the Windows binary (CPU or CUDA)."""
    asset_name = _whisper_asset_name(gpu)
    try:
        for release in _http_json(WHISPER_RELEASES_API):
            for asset in release.get("assets", []):
                if asset["name"] == asset_name:
                    return {"tag": release["tag_name"], "url": asset["browser_download_url"], "name": asset_name}
    except Exception as exc:  # network, rate limit, schema drift
        logger.warning(f"Could not query whisper.cpp releases ({exc}); using {WHISPER_FALLBACK_TAG}")
    return {
        "tag": WHISPER_FALLBACK_TAG,
        "name": asset_name,
        "url": f"https://github.com/ggml-org/whisper.cpp/releases/download/{WHISPER_FALLBACK_TAG}/{asset_name}",
    }


def _find_ffmpeg() -> Optional[str]:
    found = shutil.which("ffmpeg")
    if found:
        return found
    roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "WinGet" / "Packages",
    ]
    for root in roots:
        if root.is_dir():
            for candidate in root.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"):
                return str(candidate)
    return None


def ensure_ffmpeg(scope: "win.ServiceScope") -> Optional[str]:
    """Make ffmpeg available to the service account and return its path.

    whisper-server needs ffmpeg for ``--convert``. Machine-scope tasks run as
    SYSTEM, which does not see the installing user's PATH, so for that scope the
    binary is copied into ``<base>\\bin`` where the start script looks.
    """
    ffmpeg = _find_ffmpeg()
    if not ffmpeg and shutil.which("winget"):
        logger.info("ffmpeg not found; installing with winget...")
        _run([
            "winget", "install", "--id", FFMPEG_WINGET_ID, "-e", "--silent",
            "--accept-package-agreements", "--accept-source-agreements",
        ])
        ffmpeg = _find_ffmpeg()
    if ffmpeg and scope == win.ServiceScope.MACHINE:
        shared = win.base_dir(scope) / "bin"
        shared.mkdir(parents=True, exist_ok=True)
        target = shared / "ffmpeg.exe"
        shutil.copy2(ffmpeg, target)
        ffmpeg = str(target)
    return ffmpeg


def _register(service: str, scope: "win.ServiceScope", start_script: Path, auto_enable: bool) -> Dict[str, Any]:
    try:
        win.register_task(service, scope, start_script)
    except (win.ElevationRequired, RuntimeError) as exc:
        return {"registered": False, "error": str(exc)}
    if not auto_enable:
        win.disable_task(service)
    return {"registered": True, "task": win.task_name(service), "enabled": auto_enable}


def _default_auto_enable(auto_enable: Optional[bool]) -> bool:
    if auto_enable is not None:
        return bool(auto_enable)
    from voice_mode.config import SERVICE_AUTO_ENABLE

    return SERVICE_AUTO_ENABLE


async def install_whisper_windows(
    model: str = "base",
    scope: Optional[str] = None,
    force_reinstall: bool = False,
    auto_enable: Optional[bool] = None,
    skip_deps: bool = False,
    use_gpu: Optional[bool] = None,
    no_model: bool = False,
) -> Dict[str, Any]:
    """Install whisper.cpp (prebuilt CPU or CUDA) plus a model and register its task.

    use_gpu: None picks CUDA when an NVIDIA GPU is present, True requires it,
    False forces the CPU build.
    """
    from voice_mode.utils.services.whisper_helpers import download_whisper_model

    resolved, error = _resolve_scope(scope)
    if error:
        return error

    svc = win.service_dir("whisper", resolved)
    bin_dir = svc / "bin"
    models_dir = svc / "models"
    server = bin_dir / "whisper-server.exe"

    if not skip_deps and not ensure_ffmpeg(resolved):
        return _fail(
            "ffmpeg is required by whisper-server (--convert) and could not be installed. "
            f"Install it with: winget install {FFMPEG_WINGET_ID}",
            missing=["ffmpeg"],
        )

    want_gpu = nvidia_gpu_available() if use_gpu is None else bool(use_gpu)
    if want_gpu and "arm" in platform.machine().lower():
        want_gpu = False
    variant_file = bin_dir / ".variant"
    installed_variant = (
        variant_file.read_text(encoding="utf-8").strip() if variant_file.exists()
        else ("cpu" if server.exists() else "")  # installs before the marker existed were CPU
    )
    variant = "cuda" if want_gpu else "cpu"

    release = {"tag": "existing"}
    if force_reinstall or not server.exists() or (installed_variant and installed_variant != variant):
        release = find_whisper_release_asset(want_gpu)
        bin_dir.mkdir(parents=True, exist_ok=True)
        archive = svc / release["name"]
        logger.info(f"Downloading whisper.cpp {release['tag']}...")
        from voice_mode.utils.download import download_with_progress_async

        if not await download_with_progress_async(release["url"], archive, f"whisper.cpp {release['tag']}"):
            return _fail(f"Failed to download {release['url']}")
        try:
            with zipfile.ZipFile(archive) as bundle:
                names = [n for n in bundle.namelist() if n.lower().endswith("whisper-server.exe")]
                if not names:
                    return _fail("whisper-server.exe not found in the downloaded release archive")
                prefix = names[0][: -len("whisper-server.exe")]
                for member in bundle.namelist():
                    if member.endswith("/") or not member.startswith(prefix):
                        continue
                    target = bin_dir / member[len(prefix):]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        finally:
            archive.unlink(missing_ok=True)
        if want_gpu and not _server_starts(server):
            logger.warning("The CUDA whisper build cannot load on this machine; falling back to CPU")
            shutil.rmtree(bin_dir, ignore_errors=True)
            return await install_whisper_windows(
                model=model, scope=scope, force_reinstall=True, auto_enable=auto_enable,
                skip_deps=skip_deps, use_gpu=False, no_model=no_model,
            )
        variant_file.write_text(variant + "\n", encoding="utf-8")

    model_result: Dict[str, Any] = {"success": True}
    if not no_model:
        model_result = await download_whisper_model(model, models_dir, force_download=False, skip_core_ml=True)
        if not model_result.get("success"):
            return _fail(f"Failed to download model '{model}': {model_result.get('error', 'unknown error')}")
        from voice_mode.tools.whisper.models import set_active_model

        set_active_model(model)

    start_script = bin_dir / "start-whisper-server.ps1"
    start_script.write_text(_read_template("start-whisper-server.ps1"), encoding="utf-8")

    if resolved == win.ServiceScope.MACHINE:
        win.grant_users_read(svc)

    registration = _register("whisper", resolved, start_script, _default_auto_enable(auto_enable))
    if not registration["registered"]:
        return _fail(f"Installed files but could not register the task: {registration['error']}",
                     install_path=str(svc), scope=resolved.value)

    return {
        "success": True,
        "install_path": str(svc),
        "scope": resolved.value,
        "version": release["tag"],
        "model": None if no_model else model,
        "model_path": model_result.get("path"),
        "gpu_enabled": variant == "cuda",
        "variant": variant,
        "start_script": str(start_script),
        "task": registration["task"],
        "service_url": "http://127.0.0.1:2022",
    }


def _server_starts(server: Path) -> bool:
    """A build whose DLLs or driver do not match fails here instead of at logon."""
    try:
        return subprocess.run([str(server), "--help"], capture_output=True, timeout=30,
                              cwd=str(server.parent)).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _uv_command() -> list:
    found = shutil.which("uv")
    return [found] if found else [sys.executable, "-m", "uv"]


def _uv_env() -> Dict[str, str]:
    # Corporate TLS-inspection proxies break uv's bundled certificate store.
    return {**os.environ, "UV_SYSTEM_CERTS": "1", "PYTHONUTF8": "1"}


def _uv_run(args: list, cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(_uv_command() + args, cwd=cwd, env=_uv_env(), capture_output=True, text=True)
    if result.returncode != 0 and ("UnknownIssuer" in result.stderr or "invalid peer certificate" in result.stderr):
        # Older uv releases only know the previous flag name.
        retry_env = {**_uv_env(), "UV_NATIVE_TLS": "1"}
        result = subprocess.run(_uv_command() + args, cwd=cwd, env=retry_env, capture_output=True, text=True)
    return result


async def install_kokoro_windows(
    scope: Optional[str] = None,
    version: str = "latest",
    force_reinstall: bool = False,
    auto_enable: Optional[bool] = None,
    skip_deps: bool = False,
    device: str = "auto",
) -> Dict[str, Any]:
    """Clone Kokoro-FastAPI, build its venv (torch, bundled eSpeak) and register its task.

    device: "cpu", "gpu" (CUDA torch) or "auto" (gpu when an NVIDIA GPU is present).
    A GPU build that cannot see the GPU falls back to CPU torch.
    """
    import asyncio

    from voice_mode.utils.version_helpers import checkout_version, get_git_tags, get_latest_stable_tag

    resolved, error = _resolve_scope(scope)
    if error:
        return error

    if not skip_deps:
        missing = [tool for tool in ("git",) if not shutil.which(tool)]
        if missing:
            return _fail(
                "Git is required to install Kokoro. Install it with: winget install Git.Git",
                missing=missing,
            )

    device = (device or "auto").lower()
    if device not in {"auto", "cpu", "gpu"}:
        return _fail(f"Unknown device '{device}' (use auto, cpu or gpu)")
    if device == "auto":
        device = "gpu" if nvidia_gpu_available() else "cpu"

    install_dir = win.service_dir("kokoro", resolved)
    python = install_dir / ".venv" / "Scripts" / "python.exe"

    if version == "latest":
        tags = get_git_tags(KOKORO_REPO.removesuffix(".git"))
        version = get_latest_stable_tag(tags) if tags else None
        if not version:
            return _fail("Could not determine the latest stable Kokoro version (check network access to github.com)")

    if force_reinstall and install_dir.exists():
        shutil.rmtree(install_dir, ignore_errors=True)

    if not (install_dir / ".git").exists():
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        # The directory may already hold logs or a half-finished install, which
        # makes a direct clone fail; clone aside and merge instead.
        staging = install_dir.with_name(install_dir.name + ".clone")
        shutil.rmtree(staging, ignore_errors=True)
        clone = _run(["git", "clone", KOKORO_REPO, str(staging)])
        if clone.returncode != 0:
            return _fail(f"git clone failed: {clone.stderr.strip()}")
        shutil.copytree(staging, install_dir, dirs_exist_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
    if not checkout_version(install_dir, version):
        return _fail(f"Failed to check out Kokoro {version}")

    final_device = device

    def cuda_torch_works() -> bool:
        probe = _run([str(python), "-c", "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)"])
        return probe.returncode == 0

    def build_environment() -> Optional[str]:
        nonlocal final_device
        if not python.exists():
            result = _uv_run(["venv", "--python", KOKORO_PYTHON], install_dir)
            if result.returncode != 0:
                return f"uv venv failed: {result.stderr.strip()}"
        # Upstream pins torch+cu124, which has no Blackwell kernels; install a
        # current CUDA wheel ourselves instead of the project's gpu extra.
        extra = ".[cpu]" if device == "cpu" else "."
        result = _uv_run(["pip", "install", "--python", str(python), "-e", extra, "espeakng-loader"], install_dir)
        if result.returncode != 0:
            return f"Installing Kokoro dependencies failed: {result.stderr.strip()[-800:]}"
        if device == "gpu":
            cuda_ok = False
            for tag in KOKORO_CUDA_INDEXES:
                result = _uv_run(
                    ["pip", "install", "--python", str(python), "--reinstall-package", "torch", "torch",
                     "--index-url", f"https://download.pytorch.org/whl/{tag}"],
                    install_dir,
                )
                if result.returncode == 0 and cuda_torch_works():
                    cuda_ok = True
                    break
            if not cuda_ok:
                logger.warning("CUDA torch is not usable here; falling back to CPU torch")
                final_device = "cpu"
                result = _uv_run(
                    ["pip", "install", "--python", str(python), "--reinstall-package", "torch", "torch"],
                    install_dir,
                )
                if result.returncode != 0:
                    return f"Installing torch failed: {result.stderr.strip()[-800:]}"
        weights = _uv_run(
            ["run", "--no-sync", "--python", str(python), "python",
             "docker/scripts/download_model.py", "--output", "api/src/models/v1_0"],
            install_dir,
        )
        if weights.returncode != 0:
            return f"Downloading Kokoro model failed: {(weights.stderr or weights.stdout).strip()[-800:]}"
        return None

    build_error = await asyncio.to_thread(build_environment)
    if build_error:
        return _fail(build_error, install_path=str(install_dir))

    (install_dir / ".device").write_text(final_device + "\n", encoding="utf-8")
    start_script = install_dir / "start-kokoro.ps1"
    start_script.write_text(_read_template("start-kokoro.ps1"), encoding="utf-8")

    if resolved == win.ServiceScope.MACHINE:
        win.grant_users_read(install_dir)

    registration = _register("kokoro", resolved, start_script, _default_auto_enable(auto_enable))
    if not registration["registered"]:
        return _fail(f"Installed files but could not register the task: {registration['error']}",
                     install_path=str(install_dir), scope=resolved.value)

    return {
        "success": True,
        "install_path": str(install_dir),
        "scope": resolved.value,
        "version": version,
        "device": final_device,
        "gpu_enabled": final_device == "gpu",
        "start_script": str(start_script),
        "task": registration["task"],
        "service_url": "http://127.0.0.1:8880",
    }


async def install_voicemode_serve_windows(scope: Optional[str] = None, auto_enable: Optional[bool] = None) -> Dict[str, Any]:
    """Install the VoiceMode HTTP server start script and task."""
    resolved, error = _resolve_scope(scope)
    if error:
        return error

    bin_dir = win.service_dir("voicemode", resolved) / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    start_script = bin_dir / "start-voicemode-serve.ps1"
    start_script.write_text(_read_template("start-voicemode-serve.ps1"), encoding="utf-8")

    # Record the exact executable so the service runs the code the user installed.
    exe = Path(sys.executable).parent / "voicemode.exe"
    if not exe.exists():
        found = shutil.which("voicemode")
        exe = Path(found) if found else exe
    (bin_dir / "voicemode-exe.txt").write_text(str(exe), encoding="utf-8")

    registration = _register("voicemode", resolved, start_script, _default_auto_enable(auto_enable))
    if not registration["registered"]:
        return _fail(f"Could not register the task: {registration['error']}", scope=resolved.value)
    return {"success": True, "start_script": str(start_script), "scope": resolved.value, "task": registration["task"]}


def uninstall_service_windows(
    service: str, remove_models: bool = False, remove_all_data: bool = False
) -> Dict[str, Any]:
    """Remove a service's task and files from whichever scope it was installed in."""
    from voice_mode.config import KOKORO_PORT, WHISPER_PORT

    errors = []
    port = {"whisper": WHISPER_PORT, "kokoro": KOKORO_PORT}.get(service)
    scope = win.installed_scope(service)

    if scope == win.ServiceScope.MACHINE and not win.is_admin():
        return {"success": False, "errors": ["This service was installed machine-wide; re-run from an elevated shell."]}

    win.unregister_task(service)
    if port:
        win.kill_port_owner(port)

    scopes = [scope] if scope else [win.ServiceScope.USER, win.ServiceScope.MACHINE]
    for item in scopes:
        if item == win.ServiceScope.MACHINE and not win.is_admin():
            continue
        svc = win.service_dir(service, item)
        targets = []
        if service == "whisper":
            targets += [svc / "bin", svc / "tmp"]
            if remove_models:
                targets.append(svc / "models")
        elif service == "kokoro" or service == "voicemode":
            targets.append(svc)
        if remove_all_data:
            targets.append(win.base_dir(item) / "logs" / service)
        for target in targets:
            if target.exists():
                try:
                    shutil.rmtree(target)
                except OSError as exc:
                    errors.append(f"{target}: {exc}")
    return {"success": not errors, "errors": errors}

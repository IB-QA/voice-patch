"""System package installation."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from .checker import PackageInfo
from .system import PlatformInfo, get_package_manager


def find_uv() -> str:
    """Path to uv, even when its folder is not on this process's PATH.

    uv's own installer only updates the registry/profile for new terminals, so a
    process started before it ran (for example an installer) cannot see it.
    """
    found = shutil.which('uv')
    if found:
        return found
    home = Path.home()
    for folder in (home / '.local' / 'bin', home / '.cargo' / 'bin'):
        for name in ('uv.exe', 'uv'):
            candidate = folder / name
            if candidate.is_file():
                return str(candidate)
    return 'uv'


class PackageInstaller:
    """Install system packages using platform-specific package managers."""

    def __init__(self, platform_info: PlatformInfo, dry_run: bool = False, non_interactive: bool = False):
        self.platform = platform_info
        self.dry_run = dry_run
        self.non_interactive = non_interactive
        self.package_manager = get_package_manager(platform_info.distribution)

    def install_packages(self, packages: List[PackageInfo]) -> bool:
        """
        Install a list of packages.

        Returns True if all installations succeeded, False otherwise.
        """
        if not packages:
            return True

        package_names = [pkg.name for pkg in packages]

        if self.dry_run:
            print(f"[DRY RUN] Would install: {', '.join(package_names)}")
            return True

        try:
            if self.platform.distribution == 'darwin':
                return self._install_homebrew(package_names)
            elif self.platform.distribution == 'debian':
                return self._install_apt(package_names)
            elif self.platform.distribution == 'fedora':
                return self._install_dnf(package_names)
            elif self.platform.distribution == 'windows':
                return self._install_winget(package_names)
            else:
                print(f"Error: Unsupported distribution: {self.platform.distribution}")
                return False
        except Exception as e:
            print(f"Error installing packages: {e}")
            return False

    def _install_homebrew(self, packages: List[str]) -> bool:
        """Install packages using Homebrew.

        Note: Homebrew should already be installed by the time this is called.
        The CLI ensures Homebrew is present before dependency checking.
        """
        try:
            cmd = ['brew', 'install'] + packages
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=False  # Show output to user
            )
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            print(f"Homebrew package installation failed: {e}")
            return False
        except FileNotFoundError:
            print("Error: Homebrew not found. This should have been installed earlier.")
            print("Please report this as a bug.")
            return False

    def _install_apt(self, packages: List[str]) -> bool:
        """Install packages using apt."""
        try:
            # Update package lists first
            print("Updating package lists...")
            subprocess.run(
                ['sudo', 'apt', 'update'],
                check=True,
                capture_output=False
            )

            # Install packages
            cmd = ['sudo', 'apt', 'install', '-y'] + packages
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=False
            )
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            print(f"apt installation failed: {e}")
            return False
        except FileNotFoundError:
            print("Error: apt not found")
            return False

    def _install_dnf(self, packages: List[str]) -> bool:
        """Install packages using dnf."""
        try:
            cmd = ['sudo', 'dnf', 'install', '-y'] + packages
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=False
            )
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            print(f"dnf installation failed: {e}")
            return False
        except FileNotFoundError:
            print("Error: dnf not found")
            return False

    def _install_winget(self, packages: List[str]) -> bool:
        """Install Windows packages that have no Python wheel.

        Silence detection itself is the Python package webrtcvad-wheels, installed
        with VoiceMode. ffmpeg is the system package this path is responsible for.
        """
        winget_ids = {
            'ffmpeg': 'Gyan.FFmpeg',
        }
        if not shutil.which('winget'):
            print("Error: winget is not available.")
            print("Install ffmpeg and add it to PATH, then run the installer again.")
            print("Build: https://www.gyan.dev/ffmpeg/builds/")
            return False

        ok = True
        for name in packages:
            package_id = winget_ids.get(name)
            if not package_id:
                print(f"Error: No Windows install mapping for required package: {name}")
                ok = False
                continue
            try:
                subprocess.run(
                    [
                        'winget', 'install', '--id', package_id, '-e',
                        '--accept-source-agreements', '--accept-package-agreements',
                    ],
                    check=True,
                    capture_output=False,
                )
            except subprocess.CalledProcessError as e:
                print(f"winget installation of {name} failed: {e}")
                ok = False
            except FileNotFoundError:
                print("Error: winget not found")
                return False
        return ok

    def install_voicemode(self, version: Optional[str] = None) -> bool:
        """
        Install or upgrade voice-mode using uv tool install --upgrade.

        Args:
            version: Optional version to install (e.g., "5.1.3")

        Returns:
            True if installation succeeded, False otherwise.
        """
        # A built wheel or other uv source, for example the one bundled in an installer.
        uv = find_uv()
        source = os.environ.get('VOICEMODE_INSTALL_SOURCE', '').strip()
        if source:
            cmd = [uv, 'tool', 'install', '--upgrade', '--force', source]
        elif version:
            cmd = [uv, 'tool', 'install', '--upgrade', f'voice-mode=={version}']
        else:
            cmd = [uv, 'tool', 'install', '--upgrade', 'voice-mode']

        if self.dry_run:
            print(f"[DRY RUN] Would install: {' '.join(cmd)}")
            return True

        try:

            result = subprocess.run(
                cmd,
                check=True,
                capture_output=False
            )
            # Put uv's tool folder on the user's PATH so new terminals find
            # `voicemode`. Best effort; the install itself already succeeded.
            try:
                subprocess.run([uv, 'tool', 'update-shell'], check=False, capture_output=True, timeout=30)
            except (OSError, subprocess.SubprocessError):
                pass
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            print(f"VoiceMode installation failed: {e}")
            return False
        except FileNotFoundError:
            print("Error: uv not found. Please install uv first:")
            print("  macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh")
            print("  Windows: powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"")
            return False


def is_windows_admin() -> bool:
    """True when running elevated on Windows; always False elsewhere."""
    if os.name != 'nt':
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def voicemode_command() -> str:
    """Absolute path of the installed voicemode executable.

    The uv tool folder may not be on PATH yet in the installing shell, so prefer
    the file uv just wrote over a bare `voicemode` lookup.
    """
    python = voice_mode_tool_python()
    if python:
        from pathlib import Path
        scripts = Path(python).parent
        for name in ('voicemode.exe', 'voicemode'):
            if (scripts / name).exists():
                return str(scripts / name)
    return shutil.which('voicemode') or 'voicemode'


def voice_mode_tool_python() -> Optional[str]:
    """Return the Python inside the uv tool environment for voice-mode."""
    tool_dir = None
    try:
        result = subprocess.run(
            [find_uv(), 'tool', 'dir'],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        tool_dir = result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        tool_dir = None

    from pathlib import Path
    roots = []
    if tool_dir:
        roots.append(Path(tool_dir) / 'voice-mode')
    roots.append(Path.home() / '.local' / 'share' / 'uv' / 'tools' / 'voice-mode')

    for root in roots:
        for relative in ('bin/python', 'Scripts/python.exe', 'Scripts/python'):
            candidate = root / relative
            if candidate.exists():
                return str(candidate)
    return None


def verify_silence_detection(dry_run: bool = False) -> bool:
    """Fail the install if the VoiceMode environment cannot import webrtcvad.

    Without that import, recording runs for the full listen time and never
    stops on silence.
    """
    if dry_run:
        print("[DRY RUN] Would verify: import webrtcvad, sounddevice")
        return True

    python = voice_mode_tool_python()
    if not python:
        print("Error: Could not find the voice-mode tool Python.")
        print("Silence detection was not verified.")
        return False

    result = subprocess.run(
        [python, '-c', 'import webrtcvad, sounddevice'],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or '').strip()
        print("Error: Silence detection is not importable in the VoiceMode environment.")
        if detail:
            print(detail)
        print("Required package: webrtcvad-wheels>=2.0.14.post1 (import name: webrtcvad).")
        print("Windows wheels exist for Python 3.10 through 3.14, win32 and win_amd64.")
        print("sounddevice supplies the microphone and speakers, including on Python 3.12 and 3.14.")
        return False
    return True


def attempt_optional_simpleaudio(dry_run: bool = False) -> str:
    """Try the playback fallback. Never fail the install.

    Returns ``installed``, ``skipped``, or ``dry-run``.
    """
    if dry_run:
        print("[DRY RUN] Would try: uv pip install simpleaudio into the voice-mode environment")
        return "dry-run"

    python = voice_mode_tool_python()
    if not python:
        return "skipped"

    already = subprocess.run(
        [python, "-c", "import simpleaudio"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if already.returncode == 0:
        return "installed"

    result = subprocess.run(
        ["uv", "pip", "install", "--python", python, "simpleaudio"],
        capture_output=False,
        timeout=180,
    )
    if result.returncode != 0:
        return "skipped"

    check = subprocess.run(
        [python, "-c", "import simpleaudio"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return "installed" if check.returncode == 0 else "skipped"

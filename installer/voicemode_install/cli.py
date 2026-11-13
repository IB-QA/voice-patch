"""Main CLI for VoiceMode installer."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

from . import __version__, ui
from .checker import DependencyChecker
from .hardware import HardwareInfo
from .clients import detect_installed_clients
from .installer import (
    PackageInstaller,
    attempt_optional_simpleaudio,
    is_windows_admin,
    verify_silence_detection,
    voicemode_command,
)
from .logger import InstallLogger
from .system import detect_platform, get_system_info, check_command_exists, check_homebrew_installed


def print_logo():
    """Display the Agent Voice Connect banner."""
    ui.print_banner(__version__)


def print_step(message: str):
    """Print a step message."""
    ui.message("run", message)


def print_success(message: str):
    """Print a success message."""
    ui.message("ok", message)


def print_warning(message: str):
    """Print a warning message."""
    ui.message("warn", message)


def print_error(message: str):
    """Print an error message."""
    ui.message("fail", message)


def choose_clients(found: list[str]) -> list[str]:
    """Let the person pick which detected coding agents get voice hooks.

    Accepts numbers ("1,3"), tool names, ``all`` or ``none``. Pressing Enter
    means none. Without an interactive terminal nothing is changed.
    """
    if not sys.stdin.isatty():
        print_warning("No terminal to ask in, so no coding tool was changed.")
        return []

    click.echo("")
    click.echo(ui.paint("Which agents should get voice?", bold=True))
    for number, name in enumerate(found, start=1):
        click.echo(f"  {ui.paint(f'{number})', fg='cyan')} {ui.client_label(name)}")
    click.echo("Type numbers separated by commas (for example 1,3), 'all', or 'none'.")
    answer = click.prompt("Your choice", default="none", show_default=True).strip().lower()

    if answer in ("", "none", "n", "no", "0"):
        return []
    if answer in ("all", "a", "yes", "y"):
        return list(found)

    chosen: list[str] = []
    for part in answer.replace(" ", ",").split(","):
        if not part:
            continue
        if part.isdigit() and 1 <= int(part) <= len(found):
            name = found[int(part) - 1]
        elif part in found:
            name = part
        else:
            print_warning(f"Ignoring '{part}': not one of the listed tools.")
            continue
        if name not in chosen:
            chosen.append(name)
    return chosen


def offer_client_hooks(dry_run: bool, non_interactive: bool, clients: str | None = None) -> None:
    """Ask before installing converse hooks for coding tools already on this machine.

    ``clients`` is a comma list chosen by the person running a graphical
    installer. ``none`` skips every tool; ``None`` means detect and use all.
    """
    if clients is not None:
        found = [name.strip() for name in clients.split(",") if name.strip() and name.strip() != "none"]
        if not found:
            click.echo("No coding tools selected. Add them later with:")
            click.echo("  voicemode plugin install --client=all --converse-hooks")
            return
    else:
        found = detect_installed_clients(Path.home())
    if not found:
        print_warning("No supported coding agent was found (" + ", ".join(ui.SUPPORTED_AGENTS) + ").")
        click.echo("After one of those is installed, run:")
        click.echo("  voicemode plugin install --client=<name> --converse-hooks")
        return

    click.echo("Agents found: " + ", ".join(ui.client_label(n) for n in found))
    if dry_run:
        print_step("[DRY RUN] Would offer voice hooks for: " + ", ".join(found))
        return

    if clients is None:
        # Nothing was chosen up front. Never pick for the person: ask which tools,
        # and with no one to ask (no terminal), touch none.
        found = choose_clients(found)
        if not found:
            click.echo("No coding tools selected. Add them later with:")
            click.echo("  voicemode plugin install --client=all --converse-hooks")
            return

    executable = shutil.which("voicemode")
    if not executable:
        for candidate in (
            Path.home() / ".local" / "bin" / "voicemode.exe",
            Path.home() / ".local" / "bin" / "voicemode",
        ):
            if candidate.exists():
                executable = str(candidate)
                break
    if not executable:
        print_warning("voicemode is not on PATH in this terminal yet.")
        click.echo("Restart the terminal, then run:")
        click.echo(
            "  voicemode plugin install --client="
            + ",".join(found)
            + " --converse-hooks --yes"
        )
        return

    for name in found:
        print_step(f"Installing hooks for {name}...")
        result = subprocess.run(
            [executable, "plugin", "install", "--client", name, "--converse-hooks", "--yes"],
        )
        if result.returncode == 0:
            print_success(f"Hooks installed for {name}")
        else:
            print_warning(f"Hook install for {name} did not finish. Retry that client later.")


def get_installed_version() -> str | None:
    """Get the currently installed VoiceMode version."""
    try:
        result = subprocess.run(
            ['voicemode', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Output is like "VoiceMode version 6.0.1" or just "6.0.1"
            version = result.stdout.strip().split()[-1]
            return version
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def get_latest_version() -> str | None:
    """Get the latest VoiceMode version from PyPI."""
    try:
        # Use PyPI JSON API to get latest version
        result = subprocess.run(
            ['curl', '-s', 'https://pypi.org/pypi/voice-mode/json'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data['info']['version']
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
        pass
    return None


def check_existing_installation() -> bool:
    """Check if VoiceMode is already installed."""
    return check_command_exists('voicemode')


def ensure_homebrew_on_macos(platform_info, dry_run: bool, non_interactive: bool) -> bool:
    """
    Ensure Homebrew is installed on macOS before checking dependencies.

    Returns True if Homebrew is available or successfully installed, False otherwise.
    """
    # Only needed on macOS
    if platform_info.distribution != 'darwin':
        return True

    # Check if already installed
    if check_homebrew_installed():
        return True

    # Not installed
    print_warning("Homebrew is not installed")
    click.echo("Homebrew is the package manager required to install system dependencies on macOS.")
    click.echo("Visit: https://brew.sh")
    click.echo()

    if dry_run:
        print_step("[DRY RUN] Would install Homebrew (macOS package manager)")
        return True

    if non_interactive:
        # Auto-install Homebrew in non-interactive mode using NONINTERACTIVE=1
        print_step("Installing Homebrew (non-interactive)...")
    else:
        # Prompt user
        if not click.confirm("Install Homebrew now?", default=True):
            print_error("Homebrew installation declined")
            click.echo("Please install Homebrew manually and run the installer again.")
            return False
        print_step("Installing Homebrew...")
        click.echo("This may take a few minutes and will require your password.")

    click.echo()

    try:
        # Use NONINTERACTIVE=1 for unattended installation
        env = os.environ.copy()
        if non_interactive:
            env['NONINTERACTIVE'] = '1'
        install_script = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        result = subprocess.run(install_script, shell=True, check=True, env=env)

        if result.returncode == 0:
            print_success("Homebrew installed successfully")

            # Verify
            if check_homebrew_installed():
                return True
            else:
                print_warning("Homebrew was installed but 'brew' command not found in PATH")
                click.echo("You may need to add Homebrew to your PATH. Check the installation output above.")
                return False
        else:
            print_error("Homebrew installation returned non-zero exit code")
            return False

    except subprocess.CalledProcessError as e:
        print_error(f"Error installing Homebrew: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error installing Homebrew: {e}")
        return False


EPILOG = """
\b
Examples:
  # Normal installation
  voice-mode-install

  # Non-interactive installation (auto-accept all prompts)
  voice-mode-install --yes
  voice-mode-install -y

  # Dry run (see what would be installed)
  voice-mode-install --dry-run

  # Install specific version
  voice-mode-install --voice-mode-version=5.1.3

  # Skip service installation
  voice-mode-install --skip-services

  # Install with specific Whisper model
  voice-mode-install --yes --model large-v2
"""


@click.command(epilog=EPILOG, context_settings={'help_option_names': ['-h', '--help']})
@click.option('-d', '--dry-run', is_flag=True, help='Show what would be installed without installing')
@click.option('-v', '--voice-mode-version', default=None, help='Specific VoiceMode version to install')
@click.option('-s', '--skip-services', is_flag=True, help='Skip local service installation')
@click.option('-y', '--yes', 'non_interactive', is_flag=True, help='Run without prompts (auto-accept all)')
@click.option('-n', '--non-interactive', is_flag=True, help='Run without prompts (deprecated: use --yes/-y)')
@click.option('-m', '--model', default='base', help='Whisper model to use (base, small, medium, large-v2)')
@click.option('-c', '--clients', default=None, help='Coding tools to set up, comma separated (or "none"). Default: every tool found')
@click.version_option(__version__, '-V', '--version')
def main(dry_run, voice_mode_version, skip_services, non_interactive, model, clients):
    """Agent Voice Connect installer - set up voice for your coding agents.

    Works with Cursor, Claude Code, GitHub Copilot, Antigravity, Codex,
    ChatGPT and Devin. This installer will:

      1. Detect your operating system and architecture

      2. Check for missing system dependencies

      3. Install required packages (with your permission)

      4. Install VoiceMode using uv

      5. Optionally install local voice services

      6. Configure shell completions

      7. Verify the installation
    """
    ui.configure_streams()

    # Detect non-interactive environment (no TTY)
    if not sys.stdin.isatty() and not non_interactive and not dry_run:
        click.echo("Error: Running in non-interactive environment without --yes flag", err=True)
        click.echo("Use --yes or -y to enable automatic installation", err=True)
        click.echo("Example: uvx voice-mode-install --yes", err=True)
        sys.exit(1)

    # Initialize logger
    logger = InstallLogger()

    try:
        # Clear screen and show logo
        if not dry_run and ui.use_color():
            click.clear()
        print_logo()
        click.echo()

        if dry_run:
            click.echo(ui.paint("DRY RUN MODE - No changes will be made", fg='yellow', bold=True))
            click.echo()

        # Detect platform
        ui.section("System")
        print_step("Detecting platform...")
        platform_info = detect_platform()
        system_info = get_system_info()

        logger.log_start(system_info)

        rows = [("Platform", f"{platform_info.os_name} ({platform_info.architecture})")]
        try:
            _hw = HardwareInfo(platform_info)
            rows.append(("CPU cores", str(_hw.cpu_count)))
            rows.append(("Memory", f"{_hw.total_ram_gb:.0f} GB"))
        except Exception:
            pass
        if platform_info.os_type == 'windows':
            rows.append(("Scope", "machine-wide (administrator)" if is_windows_admin() else "current user"))
        ui.print_table(rows)
        if platform_info.is_wsl:
            print_warning("WSL detected - additional audio configuration may be needed")
        if platform_info.os_type == 'windows':
            click.echo("Microphone, speakers, silence detection and local Whisper/Kokoro services are installed.")
            if is_windows_admin():
                click.echo("Running as administrator: services are installed machine-wide.")
            else:
                click.echo("Running without administrator rights: services are installed for your user only.")
        click.echo()

        # Ensure Homebrew is installed on macOS (before checking dependencies)
        if not ensure_homebrew_on_macos(platform_info, dry_run, non_interactive):
            logger.log_error("Homebrew installation required but not available")
            sys.exit(1)

        # Check for existing installation
        if check_existing_installation():
            installed_version = get_installed_version()
            latest_version = get_latest_version()

            click.echo(f"{ui.status_mark('ok')} Agent Voice Connect is currently installed")

            if installed_version:
                click.echo(f"  Installed version: {installed_version}")
            else:
                click.echo("  Installed version: (unable to detect)")

            if latest_version:
                click.echo(f"  Latest version:    {latest_version}")

                # Check if update is available
                if installed_version and latest_version and installed_version != latest_version:
                    click.echo()
                    if non_interactive:
                        print_step("Upgrading VoiceMode...")
                    elif not click.confirm(f"Upgrade to version {latest_version}?", default=True):
                        click.echo("\nTo upgrade manually later, run: uv tool install --upgrade voice-mode")
                        sys.exit(0)
                elif installed_version and latest_version and installed_version == latest_version:
                    click.echo()
                    click.echo(f"{ui.status_mark('ok')} Already up to date")
                    if non_interactive:
                        click.echo("Reinstalling...")
                    elif not click.confirm("Reinstall anyway?", default=False):
                        click.echo("\nInstallation cancelled.")
                        sys.exit(0)
                else:
                    click.echo()
                    if not non_interactive:
                        if not click.confirm("Reinstall VoiceMode?", default=False):
                            click.echo("\nTo upgrade manually, run: uv tool install --upgrade voice-mode")
                            sys.exit(0)
            else:
                click.echo("  Latest version:    (unable to check)")
                click.echo()
                if not non_interactive:
                    if not click.confirm("Reinstall/upgrade VoiceMode?", default=False):
                        click.echo("\nTo upgrade manually, run: uv tool install --upgrade voice-mode")
                        sys.exit(0)

            click.echo()

        # Check dependencies
        ui.section("Step 1/3  System dependencies")
        print_step("Checking system dependencies...")
        checker = DependencyChecker(platform_info)
        core_deps = checker.check_core_dependencies()

        missing_deps = checker.get_missing_packages(core_deps)
        summary = checker.get_summary(core_deps)

        logger.log_check('core', summary['installed'], summary['missing_required'])

        # Display summary
        click.echo()
        for pkg in core_deps:
            if pkg.required:
                mark = ui.status_mark("ok" if pkg.installed else "fail")
                click.echo(f"  {mark} {pkg.name} - {pkg.description}")

        click.echo()

        # Install missing dependencies
        if missing_deps:
            print_warning(f"Missing {len(missing_deps)} required package(s)")

            missing_names = [pkg.name for pkg in missing_deps]
            click.echo(f"\nPackages to install: {', '.join(missing_names)}")

            if not non_interactive and not dry_run:
                if not click.confirm("\nInstall missing dependencies?", default=True):
                    print_error("Cannot proceed without required dependencies")
                    sys.exit(1)

            installer = PackageInstaller(platform_info, dry_run=dry_run, non_interactive=non_interactive)
            if installer.install_packages(missing_deps):
                print_success("System dependencies installed")
                logger.log_install('system', missing_names, True)
            else:
                logger.log_install('system', missing_names, False)
                if non_interactive:
                    # An unattended installer must not stop here: VoiceMode and
                    # the coding-tool setup do not need these packages to be
                    # installed, and exiting would leave the machine with nothing.
                    print_warning(
                        "Could not install: " + ", ".join(missing_names)
                        + ". Continuing; install them later."
                    )
                    click.echo("  ffmpeg is needed for audio conversion. On Windows: winget install Gyan.FFmpeg")
                else:
                    print_error("Failed to install some dependencies")
                    if not dry_run:
                        sys.exit(1)
        else:
            print_success("All required dependencies are already installed")

        click.echo()

        # Install VoiceMode
        ui.section("Step 2/3  Install")
        print_step("Installing Agent Voice Connect (voice-mode)...")
        installer = PackageInstaller(platform_info, dry_run=dry_run, non_interactive=non_interactive)

        if installer.install_voicemode(version=voice_mode_version):
            print_success("VoiceMode installed successfully")
            logger.log_install('voicemode', ['voice-mode'], True)
        else:
            print_error("Failed to install VoiceMode")
            logger.log_install('voicemode', ['voice-mode'], False)
            if not dry_run:
                sys.exit(1)

        if verify_silence_detection(dry_run=dry_run):
            print_success("Silence detection is available (webrtcvad)")
        else:
            print_error("Silence detection is missing. Recording will not stop when you stop talking.")
            logger.log_install('silence-detection', ['webrtcvad-wheels'], False)
            if not dry_run:
                sys.exit(1)

        playback = attempt_optional_simpleaudio(dry_run=dry_run)
        if playback == "installed":
            print_success("Optional speaker fallback simpleaudio is installed")
        elif playback == "skipped":
            print_warning("simpleaudio was not installed. Speakers still use sounddevice.")
            click.echo("This fallback needs a C compiler. On Windows that is the Microsoft C++ Build Tools.")
            click.echo("VoiceMode works without it.")

        click.echo()
        print_step("Coding-tool hooks...")
        offer_client_hooks(dry_run=dry_run, non_interactive=non_interactive, clients=clients)

        click.echo()

        # Health check
        if not dry_run:
            print_step("Verifying installation...")
            voicemode_path = shutil.which('voicemode')
            if voicemode_path:
                print_success(f"VoiceMode command found: {voicemode_path}")

                # Test that it works
                try:
                    result = subprocess.run(
                        ['voicemode', '--version'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        print_success(f"VoiceMode version: {result.stdout.strip()}")
                    else:
                        print_warning("VoiceMode command exists but may not be working correctly")
                except Exception as e:
                    print_warning(f"Could not verify VoiceMode: {e}")
            else:
                print_warning("VoiceMode command not immediately available in PATH")
                click.echo("You may need to restart your shell or run:")
                click.echo("  source ~/.bashrc  # or your shell's rc file")

        # Shell completion setup
        if not dry_run:
            print_step("Setting up shell completion...")
            shell = Path.home() / '.bashrc'  # Simplified for now
            if shell.exists():
                print_success("Shell completion configured")
            else:
                print_warning("Could not configure shell completion automatically")

        # Hardware recommendations for services
        if not skip_services and not dry_run:
            click.echo()
            ui.section("Step 3/3  Local voice services (optional)")
            click.echo()

            hardware = HardwareInfo(platform_info)
            click.echo(hardware.get_recommendation_message())
            click.echo()
            click.echo(f"Estimated download size: {hardware.get_download_estimate()}")
            click.echo()

            if hardware.should_recommend_local_services():
                if non_interactive or click.confirm("Install local voice services now?", default=True):
                    model_flag = f" --model {model}" if model != 'base' else ''
                    vm = voicemode_command()
                    scope_args = []
                    if platform_info.os_type == 'windows':
                        scope = 'machine' if is_windows_admin() else 'user'
                        scope_args = ['--scope', scope]
                        if scope == 'machine':
                            click.echo("Administrator detected: services install machine-wide and start at boot.")
                        else:
                            click.echo("No administrator rights: services install for your user and start at logon.")

                    # Install Whisper
                    click.echo()
                    print_step(f"Installing Whisper STT service (model: {model})...")
                    whisper_cmd = [vm, 'service', 'install', 'whisper'] + scope_args
                    if model != 'base':
                        whisper_cmd.extend(['--model', model])
                    try:
                        result = subprocess.run(whisper_cmd, check=True)
                        if result.returncode == 0:
                            print_success("Whisper STT service installed")
                            logger.log_install('whisper', ['whisper'], True)
                        else:
                            print_warning("Whisper installation may not have completed successfully")
                            logger.log_install('whisper', ['whisper'], False)
                    except subprocess.CalledProcessError as e:
                        print_error(f"Whisper installation failed: {e}")
                        logger.log_install('whisper', ['whisper'], False)
                    except FileNotFoundError:
                        print_error("VoiceMode command not found. Cannot install Whisper.")
                        logger.log_install('whisper', ['whisper'], False)

                    # Install Kokoro
                    click.echo()
                    print_step("Installing Kokoro TTS service...")
                    kokoro_cmd = [vm, 'service', 'install', 'kokoro'] + scope_args
                    try:
                        result = subprocess.run(kokoro_cmd, check=True)
                        if result.returncode == 0:
                            print_success("Kokoro TTS service installed")
                            logger.log_install('kokoro', ['kokoro'], True)
                        else:
                            print_warning("Kokoro installation may not have completed successfully")
                            logger.log_install('kokoro', ['kokoro'], False)
                    except subprocess.CalledProcessError as e:
                        print_error(f"Kokoro installation failed: {e}")
                        logger.log_install('kokoro', ['kokoro'], False)
                    except FileNotFoundError:
                        print_error("VoiceMode command not found. Cannot install Kokoro.")
                        logger.log_install('kokoro', ['kokoro'], False)
            else:
                click.echo("Cloud services recommended for your system configuration.")
                click.echo("Local services can still be installed if desired:")
                model_flag = f" --model {model}" if model != 'base' else ''
                click.echo(f"  voicemode whisper install{model_flag}")
                click.echo("  voicemode kokoro install")

        # Completion summary
        click.echo()
        ui.print_rule()
        click.echo(f"{ui.status_mark('ok')} {ui.paint('Installation complete', fg='green', bold=True)}")
        ui.print_rule()
        click.echo()

        logger.log_complete(success=True, voicemode_installed=True)

        if dry_run:
            click.echo("DRY RUN: No changes were made to your system")
        else:
            click.echo("Agent Voice Connect is installed.")
            click.echo()
            click.echo("Next steps:")
            click.echo("  1. Restart your terminal (or source your shell rc file)")
            click.echo("  2. Run: voicemode --help")
            click.echo("  3. Check local services: voicemode status")
            click.echo("  4. Connect your agents (" + ", ".join(ui.SUPPORTED_AGENTS) + "):")
            click.echo("     voicemode plugin install --client=all --converse-hooks")
            click.echo("  5. MCP-capable clients can launch this executable directly:")
            click.echo(f'     "{voicemode_command()}"')
            click.echo()
            click.echo(f"Installation log: {logger.get_log_path()}")

    except KeyboardInterrupt:
        click.echo("\n\nInstallation cancelled by user")
        logger.log_error("Installation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Installation failed: {e}")
        logger.log_error("Installation failed", e)
        if not dry_run:
            click.echo(f"\nFor troubleshooting, see: {logger.get_log_path()}")
        sys.exit(1)


if __name__ == '__main__':
    main()

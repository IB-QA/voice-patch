"""
CLI entry points for voice-mode package.
"""
import asyncio
import importlib
import sys
import os
import warnings
import subprocess
import shutil
import click
from pathlib import Path

# Import version info
try:
    from voice_mode.version import __version__
except ImportError:
    __version__ = "unknown"

# Import configuration constants
from voice_mode.config import (
    DEFAULT_WHISPER_MODEL,
    DEFAULT_LISTEN_DURATION,
    MIN_RECORDING_DURATION,
    SERVE_ALLOW_LOCAL,
    SERVE_ALLOW_ANTHROPIC,
    SERVE_ALLOW_TAILSCALE,
    SERVE_ALLOWED_IPS,
    SERVE_TRUSTED_PROXIES,
    SERVE_SECRET,
    SERVE_TOKEN,
    SERVE_TRANSPORT,
)


# Suppress known deprecation warnings for better user experience
# These apply to both CLI commands and MCP server operation
# They can be shown with VOICEMODE_DEBUG=true or --debug flag
if not os.environ.get('VOICEMODE_DEBUG', '').lower() in ('true', '1', 'yes'):
    # Suppress audioop deprecation warning from pydub
    warnings.filterwarnings('ignore', message='.*audioop.*deprecated.*', category=DeprecationWarning)
    # webrtcvad-wheels uses importlib.metadata, no pkg_resources warning to suppress
    # Suppress psutil connections() deprecation warning
    warnings.filterwarnings('ignore', message='.*connections.*deprecated.*', category=DeprecationWarning)
    
    # Also suppress INFO logging for CLI commands (but not for MCP server)
    import logging
    logging.getLogger("voicemode").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# Service management CLI - runs MCP server by default, subcommands override
@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="VoiceMode")
@click.help_option('-h', '--help', help='Show this message and exit')
@click.option('--debug', is_flag=True, help='Enable debug mode and show all warnings')
@click.option('--tools-enabled', help='Comma-separated list of tools to enable (whitelist)')
@click.option('--tools-disabled', help='Comma-separated list of tools to disable (blacklist)')
@click.pass_context
def voice_mode_main_cli(ctx, debug, tools_enabled, tools_disabled):
    """Voice Mode - MCP server and service management.

    Without arguments, starts the MCP server.
    With subcommands, executes service management operations.
    """
    if debug:
        # Re-enable warnings if debug flag is set
        warnings.resetwarnings()
        os.environ['VOICEMODE_DEBUG'] = 'true'
        # Re-enable INFO logging
        import logging
        logging.getLogger("voicemode").setLevel(logging.INFO)

    # Set environment variables from CLI args
    if tools_enabled:
        os.environ['VOICEMODE_TOOLS_ENABLED'] = tools_enabled
    if tools_disabled:
        os.environ['VOICEMODE_TOOLS_DISABLED'] = tools_disabled

    if ctx.invoked_subcommand is None:
        # No subcommand - run MCP server
        # Note: warnings are already suppressed at module level unless debug is enabled
        from .server import main as voice_mode_main
        voice_mode_main()


def voice_mode() -> None:
    """Entry point for voicemode command - starts the MCP server or runs subcommands."""
    voice_mode_main_cli()


# ============================================================================
# Shell completion helpers
# ============================================================================

# Standard Kokoro voices (subset of common ones; full list is much longer but
# these cover the defaults users will reach for). Kept inline so completion
# does not require importing the provider modules, which is expensive.
_KOKORO_COMMON_VOICES = (
    "af_sky", "af_river", "af_nicole", "af_sarah", "af_alloy", "af_aoede",
    "af_bella", "af_heart", "af_jadzia", "af_jessica", "af_kore", "af_nova",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
    "am_onyx", "am_puck", "am_santa",
    "bf_alice", "bf_emma", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
)

# OpenAI TTS voices.
_OPENAI_VOICES = (
    "alloy", "echo", "fable", "nova", "onyx", "shimmer",
)


def _complete_voice_names(ctx, param, incomplete):
    """Click shell_complete callback for --voice options.

    Offers the standard Kokoro and OpenAI voice names, returning
    CompletionItem objects whose values start with the incomplete prefix.
    """
    all_voices = []
    all_voices.extend(_KOKORO_COMMON_VOICES)
    all_voices.extend(_OPENAI_VOICES)
    seen = set()
    ordered = []
    for v in all_voices:
        if v not in seen:
            seen.add(v)
            ordered.append(v)
    return [
        click.shell_completion.CompletionItem(v)
        for v in ordered
        if v.startswith(incomplete)
    ]


# ============================================================================
# Unified Service Command Group
# ============================================================================
# All service management commands under a single group:
#   voicemode service start <service>
#   voicemode service stop <service>
#   voicemode service status [service]
# etc.

# Public CLI service names. ``mlx-audio`` uses kebab-case for ergonomics
# at the command line; the internal Python identifier is ``mlx_audio``.
VALID_SERVICES = [
    'whisper',
    'kokoro',
    'voicemode',
    'mlx-audio',
    'livekit',
    'livekit-web',
]


def _normalize_service_name(name: str) -> str:
    """Map CLI-form service names to Python-internal identifiers.

    ``mlx-audio`` -> ``mlx_audio``; everything else passes through. Keeps
    the CLI ergonomic without forcing snake_case onto users.
    """
    return name.replace("-", "_") if name else name


@voice_mode_main_cli.group()
@click.help_option('-h', '--help')
def service():
    """Manage VoiceMode services.

    \b
    Services:
      whisper    Local speech-to-text (STT) on port 2022
      kokoro     Local text-to-speech (TTS) on port 8880
      voicemode  HTTP MCP server for remote access on port 8765
      mlx-audio  Apple Silicon: unified Whisper + Kokoro + Qwen3-TTS on port 8890
      livekit    Managed local LiveKit SFU on port 7880
      livekit-web Local VoiceMode browser gateway on port 7890

    \b
    Quick Start:
      voicemode service status           # Check all services
      voicemode service start whisper    # Start Whisper STT
      voicemode service enable whisper   # Auto-start whisper on login

    \b
    Service Lifecycle:
      install  Install service software
      uninstall Remove service software and configuration
      start    Start a service
      stop     Stop a service
      restart  Restart a service
      status   Show service status
      enable   Enable auto-start at boot/login
      disable  Disable auto-start
      logs     View service logs
      health   Check if service is responding
      config   Generate agent-client hook templates (no auto-install)
    """
    pass


@service.command('start')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.help_option('-h', '--help')
def service_start(service_name):
    """Start a voice service.

    \b
    Services:
      whisper    Local speech-to-text (STT)
      kokoro     Local text-to-speech (TTS)
      voicemode  HTTP MCP server for remote access
      mlx-audio  Apple Silicon: unified Whisper STT + Kokoro TTS + Qwen3-TTS
    """
    from voice_mode.tools.service import start_service
    result = asyncio.run(start_service(_normalize_service_name(service_name)))
    click.echo(result)


@service.command('stop')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.help_option('-h', '--help')
def service_stop(service_name):
    """Stop a voice service.

    \b
    Services:
      whisper    Local speech-to-text (STT)
      kokoro     Local text-to-speech (TTS)
      voicemode  HTTP MCP server for remote access
      mlx-audio  Apple Silicon: unified Whisper STT + Kokoro TTS + Qwen3-TTS
    """
    from voice_mode.tools.service import stop_service
    result = asyncio.run(stop_service(_normalize_service_name(service_name)))
    click.echo(result)


@service.command('restart')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.help_option('-h', '--help')
def service_restart(service_name):
    """Restart a voice service.

    \b
    Services:
      whisper    Local speech-to-text (STT)
      kokoro     Local text-to-speech (TTS)
      voicemode  HTTP MCP server for remote access
      mlx-audio  Apple Silicon: unified Whisper STT + Kokoro TTS + Qwen3-TTS
    """
    from voice_mode.tools.service import restart_service
    result = asyncio.run(restart_service(_normalize_service_name(service_name)))
    click.echo(result)


@service.command('status')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), required=False, metavar='SERVICE')
@click.help_option('-h', '--help')
def service_status(service_name):
    """Show service status.

    \b
    Without arguments, shows status for all services.
    With a service name, shows detailed status for that service.

    \b
    Services:
      whisper    Local speech-to-text (STT)
      kokoro     Local text-to-speech (TTS)
      voicemode  HTTP MCP server for remote access

    \b
    Examples:
      voicemode service status          # Show all services
      voicemode service status whisper  # Show only Whisper
      voicemode service status voicemode # Show HTTP server status
    """
    from voice_mode.tools.service import status_service

    if service_name:
        # Show specific service
        result = asyncio.run(status_service(_normalize_service_name(service_name)))
        click.echo(result)
    else:
        # Show all services
        click.echo("VoiceMode Service Status")
        click.echo("=" * 50)
        for svc in VALID_SERVICES:
            result = asyncio.run(status_service(_normalize_service_name(svc)))
            click.echo(f"\n{svc.upper()}:")
            click.echo(result)


@service.command('enable')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.help_option('-h', '--help')
def service_enable(service_name):
    """Enable a service to start at boot/login.

    \b
    On macOS, creates a launchd plist in ~/Library/LaunchAgents/
    On Linux, creates a systemd user service in ~/.config/systemd/user/

    \b
    Services:
      whisper    Local speech-to-text (STT)
      kokoro     Local text-to-speech (TTS)
      voicemode  HTTP MCP server for remote access
    """
    from voice_mode.tools.service import enable_service
    result = asyncio.run(enable_service(_normalize_service_name(service_name)))
    click.echo(result)


@service.command('disable')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.help_option('-h', '--help')
def service_disable(service_name):
    """Disable a service from starting at boot/login.

    \b
    Removes the service from launchd (macOS) or systemd (Linux).
    The service will stop running and won't start after reboot.

    \b
    Services:
      whisper    Local speech-to-text (STT)
      kokoro     Local text-to-speech (TTS)
      voicemode  HTTP MCP server for remote access
    """
    from voice_mode.tools.service import disable_service
    result = asyncio.run(disable_service(_normalize_service_name(service_name)))
    click.echo(result)


@service.command('logs')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.option('--lines', '-n', default=50, help='Number of log lines to show')
@click.help_option('-h', '--help')
def service_logs(service_name, lines):
    """View service logs.

    \b
    On macOS, reads from ~/Library/Logs/ or ~/.voicemode/logs/
    On Linux, uses journalctl for systemd services

    \b
    Examples:
      voicemode service logs whisper       # Last 50 lines
      voicemode service logs voicemode -n 100  # Last 100 lines
    """
    from voice_mode.tools.service import view_logs
    result = asyncio.run(view_logs(_normalize_service_name(service_name), lines))
    click.echo(result)


@service.command('health')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.help_option('-h', '--help')
def service_health(service_name):
    """Check the health endpoint of a service.

    \b
    Checks if the service is responding on its expected port:
      whisper    Port 2022
      kokoro     Port 8880
      voicemode  Port 8765 (configurable via VOICEMODE_SERVE_PORT)
    """
    if service_name == 'whisper':
        port = 2022
        display_name = 'Whisper'
    elif service_name == 'kokoro':
        port = 8880
        display_name = 'Kokoro'
    else:
        click.echo(f"❌ Unknown service: {service_name}")
        return

    import subprocess
    try:
        result = subprocess.run(
            ["curl", "-s", f"http://127.0.0.1:{port}/health"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            import json
            try:
                health_data = json.loads(result.stdout)
                click.echo(f"✅ {display_name} is responding")
                click.echo(f"   Status: {health_data.get('status', 'unknown')}")
                if 'uptime' in health_data:
                    click.echo(f"   Uptime: {health_data['uptime']}")
            except json.JSONDecodeError:
                click.echo(f"✅ {display_name} is responding (non-JSON response)")
        else:
            click.echo(f"❌ {display_name} not responding on port {port}")
    except subprocess.TimeoutExpired:
        click.echo(f"❌ {display_name} health check timed out")
    except Exception as e:
        click.echo(f"❌ Health check failed: {e}")


def _echo_missing_dependencies(result):
    """Print the itemized missing-dependencies list from a failed install result.

    Install tools return the specific missing packages (each already carrying its
    own install command, e.g. "cmake (run: brew install cmake)") in a ``missing``
    list. The failure messages only echo the generic ``error`` string, so without
    this the user is told dependencies are missing but never which ones (GH-303).
    No-ops when there is no ``missing`` list.
    """
    if not isinstance(result, dict):
        return
    missing = result.get('missing') or []
    if not missing:
        return
    click.echo("   Missing:")
    for dep in missing:
        click.echo(f"     • {dep}")


@service.command('install')
@click.argument('service_name', type=click.Choice(VALID_SERVICES, case_sensitive=False), metavar='SERVICE')
@click.option('--force', '-f', is_flag=True, help='Force reinstall even if already installed')
@click.option(
    '--rotate-credentials',
    is_flag=True,
    help='Generate new LiveKit API credentials (LiveKit only)',
)
@click.help_option('-h', '--help')
def service_install(service_name, force, rotate_credentials):
    """Install a voice service.

    \b
    Downloads and installs the service software:
      whisper    whisper.cpp speech-to-text server
      kokoro     Kokoro text-to-speech server
      voicemode  Already installed (enables the HTTP server)
      mlx-audio  Apple Silicon: unified Whisper STT + Kokoro TTS + Qwen3-TTS
      livekit    Secure local LiveKit SFU

    \b
    Examples:
      voicemode service install whisper
      voicemode service install kokoro --force
      voicemode service install mlx-audio
      voicemode service install livekit
    """
    if service_name == 'whisper':
        from voice_mode.tools.whisper.install import whisper_install
        result = asyncio.run(getattr(whisper_install, 'fn', whisper_install)(force_reinstall=force))
        # Handle dict result from tool
        if isinstance(result, dict):
            if result.get("success"):
                click.echo(f"✅ Whisper installed successfully")
                if result.get('install_path'):
                    click.echo(f"   Install path: {result['install_path']}")
            else:
                click.echo(f"❌ Whisper installation failed: {result.get('error', 'Unknown error')}")
                _echo_missing_dependencies(result)
        else:
            click.echo(result)
    elif service_name == 'kokoro':
        from voice_mode.tools.kokoro.install import kokoro_install
        result = asyncio.run(getattr(kokoro_install, 'fn', kokoro_install)(force_reinstall=force))
        if isinstance(result, dict):
            if result.get("success"):
                click.echo(f"✅ Kokoro installed successfully")
                if result.get('install_path'):
                    click.echo(f"   Install path: {result['install_path']}")
            else:
                click.echo(f"❌ Kokoro installation failed: {result.get('error', 'Unknown error')}")
                _echo_missing_dependencies(result)
        else:
            click.echo(result)
    elif service_name == 'voicemode':
        from voice_mode.tools.service import install_voicemode_start_script
        result = asyncio.run(install_voicemode_start_script())
        if result.get("success"):
            click.echo(f"✅ VoiceMode start script installed successfully")
            if result.get('start_script'):
                click.echo(f"   Start script: {result['start_script']}")
        else:
            click.echo(f"❌ VoiceMode installation failed: {result.get('error', 'Unknown error')}")
            _echo_missing_dependencies(result)
    elif service_name == 'mlx-audio':
        from voice_mode.tools.mlx_audio.install import mlx_audio_install
        result = asyncio.run(mlx_audio_install(force_reinstall=force))
        if isinstance(result, dict):
            if result.get("success"):
                click.echo("✅ mlx-audio installed successfully")
                if result.get('entry_point'):
                    click.echo(f"   Entry point: {result['entry_point']}")
                if result.get('service_url'):
                    click.echo(f"   Service URL: {result['service_url']}")
                patch = result.get('patch') or {}
                if patch.get('already_patched'):
                    click.echo("   server.py: already patched (sentinel present)")
                elif patch.get('success'):
                    click.echo("   server.py: patched (backup at "
                               f"{patch.get('backup_path', '?')})")
            else:
                click.echo(f"❌ mlx-audio installation failed: {result.get('error', 'Unknown error')}")
                _echo_missing_dependencies(result)
        else:
            click.echo(result)
    elif service_name == 'livekit':
        livekit_install = importlib.import_module(
            "voice_mode.tools.livekit.install"
        ).livekit_install
        install_fn = getattr(livekit_install, 'fn', livekit_install)
        result = asyncio.run(install_fn(
            force_reinstall=force,
            rotate_credentials=rotate_credentials,
        ))
        if result.get("success"):
            click.echo("✅ LiveKit installed successfully")
            click.echo(f"   Binary: {result['binary']}")
            click.echo(f"   Config: {result['config_path']}")
        else:
            click.echo(
                f"❌ LiveKit installation failed: "
                f"{result.get('error', 'Unknown error')}"
            )
    else:
        click.echo(f"❌ Unknown service: {service_name}")


@service.command('uninstall')
@click.argument(
    'service_name',
    type=click.Choice(VALID_SERVICES, case_sensitive=False),
    metavar='SERVICE',
)
@click.option('--remove-models', is_flag=True, help='Also remove downloaded models')
@click.option('--remove-all-data', is_flag=True, help='Also remove service logs and data')
@click.confirmation_option(prompt='Are you sure you want to uninstall this service?')
@click.help_option('-h', '--help')
def service_uninstall(service_name, remove_models, remove_all_data):
    """Uninstall service software through the unified lifecycle."""
    if service_name == 'whisper':
        whisper_uninstall = importlib.import_module(
            "voice_mode.tools.whisper.uninstall"
        ).whisper_uninstall
        uninstall_fn = getattr(whisper_uninstall, 'fn', whisper_uninstall)
        result = asyncio.run(uninstall_fn(
            remove_models=remove_models,
            remove_all_data=remove_all_data,
        ))
    elif service_name == 'kokoro':
        kokoro_uninstall = importlib.import_module(
            "voice_mode.tools.kokoro.uninstall"
        ).kokoro_uninstall
        uninstall_fn = getattr(kokoro_uninstall, 'fn', kokoro_uninstall)
        result = asyncio.run(uninstall_fn(
            remove_models=remove_models,
            remove_all_data=remove_all_data,
        ))
    elif service_name == 'mlx-audio':
        mlx_audio_uninstall = importlib.import_module(
            "voice_mode.tools.mlx_audio.uninstall"
        ).mlx_audio_uninstall
        result = asyncio.run(mlx_audio_uninstall(
            remove_models=remove_models,
            remove_all_data=remove_all_data,
        ))
    elif service_name == 'livekit':
        livekit_uninstall = importlib.import_module(
            "voice_mode.tools.livekit.uninstall"
        ).livekit_uninstall
        uninstall_fn = getattr(livekit_uninstall, 'fn', livekit_uninstall)
        result = asyncio.run(uninstall_fn(remove_all_data=remove_all_data))
    else:
        click.echo(f"❌ {service_name} is part of VoiceMode and cannot be uninstalled")
        return

    if result.get('success'):
        click.echo(f"✅ {service_name} uninstalled successfully")
    else:
        click.echo(
            f"❌ {service_name} uninstall completed with errors: "
            f"{'; '.join(result.get('errors', []))}"
        )


# ============================================================================
# Legacy Service Groups (Deprecated)
# ============================================================================
# These are hidden from help/tab completion but still functional for backward
# compatibility. Use 'voicemode service <action> <service>' instead.

@voice_mode_main_cli.group(hidden=True)
@click.help_option('-h', '--help', help='Show this message and exit')
def kokoro():
    """Manage Kokoro TTS service. [DEPRECATED: Use 'voicemode service' instead]"""
    pass


@voice_mode_main_cli.group(hidden=True)
@click.help_option('-h', '--help', help='Show this message and exit')
def whisper():
    """Manage Whisper STT service. [DEPRECATED: Use 'voicemode service' instead]"""
    pass


# Service functions are imported lazily in their respective command handlers to improve startup time


# Kokoro service commands (deprecated - hidden from help but still functional)
@kokoro.command(hidden=True)
def status():
    """(Deprecated) Show Kokoro service status. Use 'voicemode service status kokoro' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service status kokoro' instead", fg='yellow', err=True)
    from voice_mode.tools.service import status_service
    result = asyncio.run(status_service("kokoro"))
    click.echo(result)


@kokoro.command(hidden=True)
def start():
    """(Deprecated) Start Kokoro service. Use 'voicemode service start kokoro' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service start kokoro' instead", fg='yellow', err=True)
    from voice_mode.tools.service import start_service
    result = asyncio.run(start_service("kokoro"))
    click.echo(result)


@kokoro.command(hidden=True)
def stop():
    """(Deprecated) Stop Kokoro service. Use 'voicemode service stop kokoro' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service stop kokoro' instead", fg='yellow', err=True)
    from voice_mode.tools.service import stop_service
    result = asyncio.run(stop_service("kokoro"))
    click.echo(result)


@kokoro.command(hidden=True)
def restart():
    """(Deprecated) Restart Kokoro service. Use 'voicemode service restart kokoro' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service restart kokoro' instead", fg='yellow', err=True)
    from voice_mode.tools.service import restart_service
    result = asyncio.run(restart_service("kokoro"))
    click.echo(result)


@kokoro.command(hidden=True)
def enable():
    """(Deprecated) Enable Kokoro service. Use 'voicemode service enable kokoro' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service enable kokoro' instead", fg='yellow', err=True)
    from voice_mode.tools.service import enable_service
    result = asyncio.run(enable_service("kokoro"))
    click.echo(result)


@kokoro.command(hidden=True)
def disable():
    """(Deprecated) Disable Kokoro service. Use 'voicemode service disable kokoro' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service disable kokoro' instead", fg='yellow', err=True)
    from voice_mode.tools.service import disable_service
    result = asyncio.run(disable_service("kokoro"))
    click.echo(result)


@kokoro.command(hidden=True)
@click.help_option('-h', '--help')
@click.option('--lines', '-n', default=50, help='Number of log lines to show')
def logs(lines):
    """(Deprecated) View Kokoro logs. Use 'voicemode service logs kokoro' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service logs kokoro' instead", fg='yellow', err=True)
    from voice_mode.tools.service import view_logs
    result = asyncio.run(view_logs("kokoro", lines))
    click.echo(result)


@kokoro.command(hidden=True)
def health():
    """Check Kokoro health endpoint."""
    import subprocess
    try:
        result = subprocess.run(
            ["curl", "-s", "http://127.0.0.1:8880/health"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            import json
            try:
                health_data = json.loads(result.stdout)
                click.echo("✅ Kokoro is responding")
                click.echo(f"   Status: {health_data.get('status', 'unknown')}")
                if 'uptime' in health_data:
                    click.echo(f"   Uptime: {health_data['uptime']}")
            except json.JSONDecodeError:
                click.echo("✅ Kokoro is responding (non-JSON response)")
        else:
            click.echo("❌ Kokoro not responding on port 8880")
    except subprocess.TimeoutExpired:
        click.echo("❌ Kokoro health check timed out")
    except Exception as e:
        click.echo(f"❌ Health check failed: {e}")


@kokoro.command()
@click.help_option('-h', '--help')
@click.option('--install-dir', help='Directory to install kokoro-fastapi')
@click.option('--port', default=8880, help='Port to configure for the service')
@click.option('--force', '-f', is_flag=True, help='Force reinstall even if already installed')
@click.option('--version', default='latest', help='Version to install (default: latest)')
@click.option('--auto-enable/--no-auto-enable', default=None, help='Enable service at boot/login')
@click.option('--skip-deps', is_flag=True, help='Skip dependency checks (for advanced users)')
def install(install_dir, port, force, version, auto_enable, skip_deps):
    """Install kokoro-fastapi TTS service."""
    from voice_mode.tools.kokoro.install import kokoro_install
    result = asyncio.run(getattr(kokoro_install, 'fn', kokoro_install)(
        install_dir=install_dir,
        port=port,
        force_reinstall=force,
        version=version,
        auto_enable=auto_enable,
        skip_deps=skip_deps
    ))
    
    if result.get('success'):
        if result.get('already_installed'):
            click.echo(f"✅ Kokoro already installed at {result['install_path']}")
            click.echo(f"   Version: {result.get('version', 'unknown')}")
        else:
            click.echo("✅ Kokoro installed successfully!")
            click.echo(f"   Install path: {result['install_path']}")
            click.echo(f"   Version: {result.get('version', 'unknown')}")
            
        if result.get('enabled'):
            click.echo("   Auto-start: Enabled")
        
        if result.get('migration_message'):
            click.echo(f"\n{result['migration_message']}")
    else:
        click.echo(f"❌ Installation failed: {result.get('error', 'Unknown error')}")
        if result.get('details'):
            click.echo(f"   Details: {result['details']}")


@kokoro.command()
@click.help_option('-h', '--help')
@click.option('--remove-models', is_flag=True, help='Also remove downloaded Kokoro models')
@click.option('--remove-all-data', is_flag=True, help='Remove all Kokoro data including logs and cache')
@click.confirmation_option(prompt='Are you sure you want to uninstall Kokoro?')
def uninstall(remove_models, remove_all_data):
    """Uninstall kokoro-fastapi service and optionally remove data."""
    from voice_mode.tools.kokoro.uninstall import kokoro_uninstall
    result = asyncio.run(getattr(kokoro_uninstall, 'fn', kokoro_uninstall)(
        remove_models=remove_models,
        remove_all_data=remove_all_data
    ))
    
    if result.get('success'):
        click.echo("✅ Kokoro uninstalled successfully!")
        
        if result.get('service_stopped'):
            click.echo("   Service stopped")
        if result.get('service_disabled'):
            click.echo("   Service disabled")
        if result.get('install_removed'):
            click.echo(f"   Installation removed: {result['install_path']}")
        if result.get('models_removed'):
            click.echo("   Models removed")
        if result.get('data_removed'):
            click.echo("   All data removed")
            
        if result.get('warnings'):
            click.echo("\n⚠️  Warnings:")
            for warning in result['warnings']:
                click.echo(f"   - {warning}")
    else:
        click.echo(f"❌ Uninstall failed: {result.get('error', 'Unknown error')}")
        if result.get('details'):
            click.echo(f"   Details: {result['details']}")


# Create service group for whisper
@whisper.group("service")
@click.help_option('-h', '--help', help='Show this message and exit')
def whisper_service():
    """Manage Whisper service."""
    pass

# Service commands under the group
@whisper_service.command("status")
def whisper_service_status():
    """Show Whisper service status."""
    from voice_mode.tools.service import status_service
    result = asyncio.run(status_service("whisper"))
    click.echo(result)


@whisper_service.command("start")
def whisper_service_start():
    """Start Whisper service."""
    from voice_mode.tools.service import start_service
    result = asyncio.run(start_service("whisper"))
    click.echo(result)


@whisper_service.command("stop")
def whisper_service_stop():
    """Stop Whisper service."""
    from voice_mode.tools.service import stop_service
    result = asyncio.run(stop_service("whisper"))
    click.echo(result)


@whisper_service.command("restart")
def whisper_service_restart():
    """Restart Whisper service."""
    from voice_mode.tools.service import restart_service
    result = asyncio.run(restart_service("whisper"))
    click.echo(result)


@whisper_service.command("enable")
def whisper_service_enable():
    """Enable Whisper service to start at boot/login."""
    from voice_mode.tools.service import enable_service
    result = asyncio.run(enable_service("whisper"))
    click.echo(result)


@whisper_service.command("disable")
def whisper_service_disable():
    """Disable Whisper service from starting at boot/login."""
    from voice_mode.tools.service import disable_service
    result = asyncio.run(disable_service("whisper"))
    click.echo(result)


@whisper_service.command("logs")
@click.help_option('-h', '--help')
@click.option('--lines', '-n', default=50, help='Number of log lines to show')
def whisper_service_logs(lines):
    """View Whisper service logs."""
    from voice_mode.tools.service import view_logs
    result = asyncio.run(view_logs("whisper", lines))
    click.echo(result)


@whisper_service.command("health")
def whisper_service_health():
    """Check Whisper health endpoint."""
    import subprocess
    try:
        result = subprocess.run(
            ["curl", "-s", "http://127.0.0.1:2022/health"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            import json
            try:
                health_data = json.loads(result.stdout)
                click.echo("✅ Whisper is responding")
                click.echo(f"   Status: {health_data.get('status', 'unknown')}")
                if 'uptime' in health_data:
                    click.echo(f"   Uptime: {health_data['uptime']}")
            except json.JSONDecodeError:
                click.echo("✅ Whisper is responding (non-JSON response)")
        else:
            click.echo("❌ Whisper not responding on port 2022")
    except subprocess.TimeoutExpired:
        click.echo("❌ Whisper health check timed out")
    except Exception as e:
        click.echo(f"❌ Health check failed: {e}")


@whisper_service.command("install")
@click.help_option('-h', '--help')
@click.option('--install-dir', help='Directory to install whisper.cpp')
@click.option('--model', default=DEFAULT_WHISPER_MODEL, help=f'Whisper model to download (default: {DEFAULT_WHISPER_MODEL})')
@click.option('--use-gpu/--no-gpu', default=None, help='Enable GPU support if available')
@click.option('--force', '-f', is_flag=True, help='Force reinstall even if already installed')
@click.option('--version', default='latest', help='Version to install (default: latest)')
@click.option('--auto-enable/--no-auto-enable', default=None, help='Enable service at boot/login')
@click.option('--skip-deps', is_flag=True, help='Skip dependency checks (for advanced users)')
def whisper_service_install(install_dir, model, use_gpu, force, version, auto_enable, skip_deps):
    """Install whisper.cpp STT service with automatic system detection."""
    from voice_mode.tools.whisper.install import whisper_install
    result = asyncio.run(getattr(whisper_install, 'fn', whisper_install)(
        install_dir=install_dir,
        model=model,
        use_gpu=use_gpu,
        force_reinstall=force,
        version=version,
        auto_enable=auto_enable,
        skip_deps=skip_deps
    ))
    
    if result.get('success'):
        if result.get('already_installed'):
            click.echo(f"✅ Whisper already installed at {result['install_path']}")
            click.echo(f"   Version: {result.get('version', 'unknown')}")
        else:
            click.echo("✅ Whisper installed successfully!")
            click.echo(f"   Install path: {result['install_path']}")
            click.echo(f"   Version: {result.get('version', 'unknown')}")
            
        if result.get('gpu_enabled'):
            click.echo("   GPU support: Enabled")
        if result.get('model_downloaded'):
            click.echo(f"   Model: {result.get('model', 'unknown')}")
        if result.get('enabled'):
            click.echo("   Auto-start: Enabled")
        
        if result.get('migration_message'):
            click.echo(f"\n{result['migration_message']}")
            
        if result.get('next_steps'):
            click.echo("\nNext steps:")
            for step in result['next_steps']:
                click.echo(f"   - {step}")

        # Show warning if model download failed (GH-174)
        if result.get('model_error'):
            click.echo()
            click.secho("⚠️  Model download failed:", fg='yellow', bold=True)
            click.secho(f"   {result['model_error']}", fg='yellow')
            click.echo("   Whisper won't work without a model.")
            click.echo("   Try: voicemode whisper model install")
    else:
        click.echo(f"❌ Installation failed: {result.get('error', 'Unknown error')}")
        if result.get('details'):
            click.echo(f"   Details: {result['details']}")


@whisper_service.command("uninstall")
@click.help_option('-h', '--help')
@click.option('--remove-models', is_flag=True, help='Also remove downloaded Whisper models')
@click.option('--remove-all-data', is_flag=True, help='Remove all Whisper data including logs and transcriptions')
@click.confirmation_option(prompt='Are you sure you want to uninstall Whisper?')
def whisper_service_uninstall(remove_models, remove_all_data):
    """Uninstall whisper.cpp and optionally remove models and data."""
    from voice_mode.tools.whisper.uninstall import whisper_uninstall
    result = asyncio.run(getattr(whisper_uninstall, 'fn', whisper_uninstall)(
        remove_models=remove_models,
        remove_all_data=remove_all_data
    ))
    
    if result.get('success'):
        click.echo("✅ Whisper uninstalled successfully!")
        
        if result.get('service_stopped'):
            click.echo("   Service stopped")
        if result.get('service_disabled'):
            click.echo("   Service disabled")
        if result.get('install_removed'):
            click.echo(f"   Installation removed: {result['install_path']}")
        if result.get('models_removed'):
            click.echo("   Models removed")
        if result.get('data_removed'):
            click.echo("   All data removed")
            
        if result.get('warnings'):
            click.echo("\n⚠️  Warnings:")
            for warning in result['warnings']:
                click.echo(f"   - {warning}")
    else:
        click.echo(f"❌ Uninstall failed: {result.get('error', 'Unknown error')}")
        if result.get('details'):
            click.echo(f"   Details: {result['details']}")


# Import the unified model command
from voice_mode.whisper_model_unified import whisper_model_unified

# Add it directly to the whisper group
whisper.add_command(whisper_model_unified, name="model")

# Backward compatibility: Add hidden aliases for old direct commands
# These allow "whisper start" to work as "whisper service start"
# But show deprecation warnings pointing to the new unified service commands
@whisper.command("status", hidden=True)
@click.pass_context
def whisper_status_alias(ctx):
    """(Deprecated) Show Whisper service status. Use 'voicemode service status whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service status whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_status)

@whisper.command("start", hidden=True)
@click.pass_context
def whisper_start_alias(ctx):
    """(Deprecated) Start Whisper service. Use 'voicemode service start whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service start whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_start)

@whisper.command("stop", hidden=True)
@click.pass_context
def whisper_stop_alias(ctx):
    """(Deprecated) Stop Whisper service. Use 'voicemode service stop whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service stop whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_stop)

@whisper.command("restart", hidden=True)
@click.pass_context
def whisper_restart_alias(ctx):
    """(Deprecated) Restart Whisper service. Use 'voicemode service restart whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service restart whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_restart)

@whisper.command("enable", hidden=True)
@click.pass_context
def whisper_enable_alias(ctx):
    """(Deprecated) Enable Whisper service. Use 'voicemode service enable whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service enable whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_enable)

@whisper.command("disable", hidden=True)
@click.pass_context
def whisper_disable_alias(ctx):
    """(Deprecated) Disable Whisper service. Use 'voicemode service disable whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service disable whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_disable)

@whisper.command("logs", hidden=True)
@click.help_option('-h', '--help')
@click.option('--lines', '-n', default=50, help='Number of log lines to show')
@click.pass_context
def whisper_logs_alias(ctx, lines):
    """(Deprecated) View Whisper logs. Use 'voicemode service logs whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service logs whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_logs, lines=lines)

@whisper.command("health", hidden=True)
@click.pass_context
def whisper_health_alias(ctx):
    """(Deprecated) Check Whisper health. Use 'voicemode service health whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service health whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_health)

@whisper.command("install", hidden=True)
@click.help_option('-h', '--help')
@click.option('--install-dir', help='Directory to install whisper.cpp')
@click.option('--model', default=DEFAULT_WHISPER_MODEL, help=f'Whisper model to download (default: {DEFAULT_WHISPER_MODEL})')
@click.option('--use-gpu/--no-gpu', default=None, help='Enable GPU support if available')
@click.option('--force', '-f', is_flag=True, help='Force reinstall even if already installed')
@click.option('--version', default='latest', help='Version to install (default: latest)')
@click.option('--auto-enable/--no-auto-enable', default=None, help='Enable service at boot/login')
@click.option('--skip-deps', is_flag=True, help='Skip dependency checks (for advanced users)')
@click.pass_context
def whisper_install_alias(ctx, install_dir, model, use_gpu, force, version, auto_enable, skip_deps):
    """(Deprecated) Install Whisper. Use 'voicemode service install whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service install whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_install, install_dir=install_dir, model=model, use_gpu=use_gpu,
                force=force, version=version, auto_enable=auto_enable, skip_deps=skip_deps)

@whisper.command("uninstall", hidden=True)
@click.help_option('-h', '--help')
@click.option('--remove-models', is_flag=True, help='Also remove downloaded Whisper models')
@click.option('--remove-all-data', is_flag=True, help='Remove all Whisper data including logs and transcriptions')
@click.confirmation_option(prompt='Are you sure you want to uninstall Whisper?')
@click.pass_context
def whisper_uninstall_alias(ctx, remove_models, remove_all_data):
    """(Deprecated) Uninstall Whisper. Use 'voicemode service uninstall whisper' instead."""
    click.secho("⚠️  Deprecated: Use 'voicemode service uninstall whisper' instead", fg='yellow', err=True)
    ctx.forward(whisper_service_uninstall, remove_models=remove_models, remove_all_data=remove_all_data)


@voice_mode_main_cli.group()
@click.help_option('-h', '--help', help='Show this message and exit')
def config():
    """Manage voicemode configuration."""
    pass


@config.command("list")
def config_list():
    """List all configuration keys with their descriptions."""
    from voice_mode.tools.configuration_management import list_config_keys
    result = asyncio.run(getattr(list_config_keys, 'fn', list_config_keys)())
    click.echo(result)


@config.command("get")
@click.help_option('-h', '--help')
@click.argument('key')
def config_get(key):
    """Get a configuration value."""
    import os
    from pathlib import Path
    
    # Read from the env file
    env_file = Path.home() / ".voicemode" / "voicemode.env"
    if not env_file.exists():
        click.echo(f"❌ Configuration file not found: {env_file}")
        return
    
    # Look for the key
    found = False
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or not line:
                continue
            if '=' in line:
                k, v = line.split('=', 1)
                if k.strip() == key:
                    click.echo(f"{key}={v.strip()}")
                    found = True
                    break
    
    if not found:
        # Check environment variable
        env_value = os.getenv(key)
        if env_value is not None:
            click.echo(f"{key}={env_value} (from environment)")
        else:
            click.echo(f"❌ Configuration key not found: {key}")
            click.echo("Run 'voicemode config list' to see available keys")


@config.command("set")
@click.help_option('-h', '--help')
@click.argument('key')
@click.argument('value')
def config_set(key, value):
    """Set a configuration value."""
    from voice_mode.tools.configuration_management import update_config
    result = asyncio.run(getattr(update_config, 'fn', update_config)(key, value))
    click.echo(result)


@config.command("edit")
@click.help_option('-h', '--help')
@click.option('--editor', help='Editor to use (overrides $EDITOR)')
def config_edit(editor):
    """Open the configuration file in your default editor.

    Opens ~/.voicemode/voicemode.env in your configured editor.
    Uses $EDITOR environment variable by default, or you can specify with --editor.

    Examples:
        voicemode config edit           # Use $EDITOR
        voicemode config edit --editor vim
        voicemode config edit --editor "code --wait"
    """
    from pathlib import Path

    # Find the config file
    config_path = Path.home() / ".voicemode" / "voicemode.env"

    # Create default config if it doesn't exist
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        from voice_mode.config import load_voicemode_env
        # This will create the default config
        load_voicemode_env()

    # Determine which editor to use
    if editor:
        editor_cmd = editor
    else:
        # Try environment variables in order of preference
        editor_cmd = (
            os.environ.get('EDITOR') or
            os.environ.get('VISUAL') or
            shutil.which('nano') or
            shutil.which('vim') or
            shutil.which('vi')
        )

    if not editor_cmd:
        click.echo("❌ No editor found. Please set $EDITOR or use --editor")
        click.echo("   Example: export EDITOR=vim")
        click.echo("   Or use: voicemode config edit --editor vim")
        return

    # Handle complex editor commands (e.g., "code --wait")
    if ' ' in editor_cmd:
        import shlex
        cmd_parts = shlex.split(editor_cmd)
        cmd = cmd_parts + [str(config_path)]
    else:
        cmd = [editor_cmd, str(config_path)]

    # Open the editor
    try:
        click.echo(f"Opening {config_path} in {editor_cmd}...")
        subprocess.run(cmd, check=True)
        click.echo("✅ Configuration file edited successfully")
        click.echo("\nChanges will take effect when voicemode is restarted.")
    except subprocess.CalledProcessError:
        click.echo(f"❌ Editor exited with an error")
    except FileNotFoundError:
        click.echo(f"❌ Editor not found: {editor_cmd}")
        click.echo("   Please check that the editor is installed and in your PATH")


# Dependency management group
@voice_mode_main_cli.command()
@click.help_option('-h', '--help')
@click.option('--component', type=click.Choice(['core', 'whisper', 'kokoro']),
              help='Check specific component only')
@click.option('--yes', '-y', is_flag=True, help='Install without prompting')
@click.option('--dry-run', is_flag=True, help='Show what would be installed')
@click.option('--verbose', '-v', is_flag=True, help='Show full installation output')
def deps(component, yes, dry_run, verbose):
    """Check and install system dependencies.

    Shows dependency status and offers to install missing ones.
    Checks core dependencies by default, or specify --component.

    Examples:
        voicemode deps                    # Check all dependencies
        voicemode deps --component whisper  # Check whisper dependencies only
        voicemode deps --yes              # Install without prompting
        voicemode deps --verbose          # Show full installation output
    """
    from voice_mode.utils.dependencies.checker import (
        check_component_dependencies,
        load_dependencies,
        install_missing_dependencies
    )

    deps_yaml = load_dependencies()
    components = [component] if component else ['core', 'whisper', 'kokoro']

    all_missing = []

    for comp in components:
        click.echo(f"\n{comp.capitalize()} Dependencies:")
        results = check_component_dependencies(comp, deps_yaml)

        if not results:
            click.echo("  (No required dependencies for this platform)")
            continue

        for pkg, installed in results.items():
            status = "✓" if installed else "✗"
            click.echo(f"  {status} {pkg}")

            if not installed:
                all_missing.append(pkg)

    if not all_missing:
        click.echo("\n✅ All dependencies satisfied")
        return

    if dry_run:
        click.echo(f"\nWould install: {', '.join(all_missing)}")
        return

    # Offer to install
    success, message = install_missing_dependencies(
        all_missing,
        interactive=not yes,
        verbose=verbose
    )

    if success:
        click.echo("\n✅ Dependencies installed successfully")
    else:
        click.echo(f"\n❌ Installation failed: {message}")


# ============================================================================
# Control Channel Command Group (VM-1676)
# ============================================================================
# `voicemode control {pause|resume|stop|skip-back}` writes one JSON line to the
# running server's control socket so an in-flight TTS utterance can be paused,
# resumed, cut, or skipped back (replay the previous utterance, VM-1685) WITHOUT
# going through the agent and WITHOUT pressing ESC. This is the documented,
# reusable interface a Stream Deck button, media key, or spoken keyword shells
# out to. The server must have VOICEMODE_CONTROL_CHANNEL_ENABLED=true.
# See docs/reference/control-channel.md.


def _control_command_options(f):
    """Shared options for every `voicemode control` subcommand.

    `--hint` names a server-owned *intent* (allowlisted); on `stop` it selects
    the canned sentence the agent sees. `--message` is accepted but, for security
    (VM-1691), is logged on the server only and NEVER surfaced to the agent.
    `--socket` overrides the default socket path.
    """
    from voice_mode.control_channel import CONTROL_INTENTS
    intents = ", ".join(sorted(CONTROL_INTENTS))
    f = click.option(
        '--socket', 'socket_path', default=None, metavar='PATH',
        help='Control socket path (default: $VOICEMODE_CONTROL_SOCKET or '
             '~/.voicemode/control.sock).',
    )(f)
    f = click.option(
        '--hint', default=None, metavar='INTENT',
        help=f'Named intent surfaced (as a fixed sentence) in the converse return '
             f'on stop. One of: {intents}.',
    )(f)
    f = click.option(
        '--message', '-m', default=None, metavar='TEXT',
        help='Free-text note for SERVER LOGS only — not shown to the agent '
             '(security: VM-1691). Use --hint to influence the agent.',
    )(f)
    f = click.help_option('-h', '--help')(f)
    return f


def _send_control_command(command, message, hint, socket_path):
    """Send one control command to the socket and report the outcome.

    Shared by the pause/resume/stop/skip-back subcommands. Exits non-zero with a
    friendly message when nothing is listening (the channel is only live while the
    server is speaking, and only when enabled) or on any other socket error.
    """
    from voice_mode.control_socket import send_control_command
    from voice_mode.control_channel import ControlCommandError
    from voice_mode import config

    path = socket_path or config.CONTROL_SOCKET_PATH
    try:
        send_control_command(command, message=message, hint=hint, socket_path=path)
    except ControlCommandError as exc:
        click.echo(f"Invalid control command: {exc}", err=True)
        raise SystemExit(2)
    except FileNotFoundError:
        click.echo(
            f"No control socket at {path}.\n"
            "The control channel is only active while VoiceMode is speaking, and "
            "requires VOICEMODE_CONTROL_CHANNEL_ENABLED=true on the server.",
            err=True,
        )
        raise SystemExit(1)
    except ConnectionRefusedError:
        click.echo(
            f"Control socket {path} exists but no server is accepting on it "
            "(stale socket, or the server isn't speaking right now).",
            err=True,
        )
        raise SystemExit(1)
    except OSError as exc:
        click.echo(f"Failed to send control command: {exc}", err=True)
        raise SystemExit(1)
    click.echo(f"Sent '{command}' to {path}")


@voice_mode_main_cli.group()
@click.help_option('-h', '--help')
def control():
    """Pause / resume / stop / skip-back the utterance the server is speaking.

    Writes one JSON command line to the control socket the running server listens
    on while it speaks (default ~/.voicemode/control.sock). This is the reusable
    interface a Stream Deck button, media key, or spoken keyword can shell out to
    -- a second local process driving the in-flight utterance, without going
    through the agent and without pressing ESC. A `stop` makes `converse` return
    NORMALLY with a control marker, so the agent reads a clean tool result and
    continues in text (no MCP teardown, no /mcp reconnect). A `skip-back` replays
    a previously-spoken utterance from the history buffer (CD-style transport,
    VM-1685) -- it re-plays audio already produced, never a new agent turn.

    \b
    The server must opt in:
      export VOICEMODE_CONTROL_CHANNEL_ENABLED=true

    \b
    Examples:
      voicemode control stop                                # cut the current utterance
      voicemode control stop --hint switch-to-text -m "can't talk right now"
      voicemode control skip-forward                        # cut + advance to your record turn
      voicemode control pause                               # hold playback
      voicemode control resume                              # resume after a pause
      voicemode control skip-back                           # replay the previous utterance

    See: docs/reference/control-channel.md
    """
    pass


@control.command('pause')
@_control_command_options
def control_pause(message, hint, socket_path):
    """Pause the in-flight utterance (hold playback until resume or stop)."""
    _send_control_command('pause', message, hint, socket_path)


@control.command('resume')
@_control_command_options
def control_resume(message, hint, socket_path):
    """Resume playback after a pause."""
    _send_control_command('resume', message, hint, socket_path)


@control.command('stop')
@_control_command_options
def control_stop(message, hint, socket_path):
    """Stop the in-flight utterance cleanly; converse returns with the hint/message."""
    _send_control_command('stop', message, hint, socket_path)


@control.command('skip-back')
@_control_command_options
def control_skip_back(message, hint, socket_path):
    """Replay the previous utterance from the history buffer (CD-style transport).

    Sends the `skip_back` command (the exact word the Stream Deck deck.py and
    other triggers use). First press restarts the current/most-recent utterance;
    each further press steps back through the buffer. Re-plays already-spoken
    audio only -- never a new agent turn.
    """
    _send_control_command('skip_back', message, hint, socket_path)


@control.command('skip-forward')
@_control_command_options
def control_skip_forward(message, hint, socket_path):
    """Skip-forward: end the current utterance and advance to your record turn.

    A deterministic transport barge-in (VM-1739) -- the same effect as speaking
    over the assistant, but triggered by a key/button. Unlike `stop`, `converse`
    does NOT return a control marker: it advances straight into listening.
    """
    _send_control_command('skip_forward', message, hint, socket_path)


# Diagnostics group
@voice_mode_main_cli.group()
@click.help_option('-h', '--help', help='Show this message and exit')
def diag():
    """Diagnostic tools for voicemode."""
    pass


@diag.command()
def info():
    """Show voicemode installation information."""
    from voice_mode.tools.diagnostics import voice_mode_info
    result = asyncio.run(getattr(voice_mode_info, 'fn', voice_mode_info)())
    click.echo(result)


@diag.command()
def devices():
    """List available audio input and output devices."""
    from voice_mode.tools.devices import check_audio_devices
    result = asyncio.run(getattr(check_audio_devices, 'fn', check_audio_devices)())
    click.echo(result)


@diag.command()
def registry():
    """Show voice provider registry with all discovered endpoints."""
    from voice_mode.tools.voice_registry import voice_registry
    result = asyncio.run(getattr(voice_registry, 'fn', voice_registry)())
    click.echo(result)


# Import subcommand groups
from voice_mode.cli_commands import exchanges as exchanges_cmd
from voice_mode.cli_commands import transcribe as transcribe_cmd
from voice_mode.cli_commands import status as status_cmd
from voice_mode.cli_commands import conch as conch_cmd
from voice_mode.cli_commands import livekit as livekit_cmd
from voice_mode.cli_commands import plugin as plugin_cmd
from voice_mode.cli_commands import hook as hook_cmd

# Add exchanges to main CLI
voice_mode_main_cli.add_command(exchanges_cmd.exchanges)
voice_mode_main_cli.add_command(plugin_cmd.plugin)
voice_mode_main_cli.add_command(hook_cmd.hook)
# Add unified status command
voice_mode_main_cli.add_command(status_cmd.status)




# Add conch management commands
voice_mode_main_cli.add_command(conch_cmd.conch)
voice_mode_main_cli.add_command(livekit_cmd.livekit)

# Add the /mcp self-reconnect command (VM-1727). Lives in a top-level,
# MCP-independent module so it imports and runs when the voicemode server is
# down -- the exact moment the agent needs it.
from voice_mode.reconnect import reconnect_command as reconnect_cmd
voice_mode_main_cli.add_command(reconnect_cmd)

# Note: We'll add these commands after the groups are defined
# audio group will get transcribe and play commands


# Now add the subcommands to their respective groups
# Add transcribe as top-level command
transcribe_audio_cmd = transcribe_cmd.transcribe.commands['audio']
transcribe_audio_cmd.name = 'transcribe'
voice_mode_main_cli.add_command(transcribe_audio_cmd)

# Converse command - direct voice conversation from CLI
#
# Help layout uses Click's `epilog` so examples render at the bottom (after
# Options), and `\b` markers preserve our line breaks (otherwise Click
# reflows the paragraph and runs comment + command together on one line).
_CONVERSE_EPILOG = """\
\b
Examples:
  voicemode converse                                    # default greeting
  voicemode converse "Hello there!"                     # positional message
  voicemode converse "Hello there!" --skip-stt          # speak only, no listen
  voicemode converse -m "Hello there!" --skip-stt       # equivalent via -m (back-compat)
  voicemode converse -- "-c is short for continuous"    # `--` escapes dash-prefixed text
  voicemode converse --continuous                       # continuous conversation mode
  voicemode converse "Hello there!" --voice nova        # pick a TTS voice
  voicemode converse "Hey, urgent question." --skip-conch  # bypass the conch lock
\b
Multi-voice (speak a gap-free sequence in one call; synth overlaps playback):
  voicemode converse --say 'sandy:My milkshake brings all the boys to the yard.' \\
                     --say 'tripitaka:Damn right. It is better than yours.' \\
                     --say 'pigsy:I could teach you. But I would have to charge.' \\
                     --say 'monkey:So! You still want a milkshake?'
  # --say 'VOICE:TEXT' (VOICE: optional → falls back to --voice/default).
  # Repeat --say to build the sequence; order is preserved.
\b
Survey (speak each turn, listen for and collect a reply, aligned in the
returned JSON; --ask is exactly parallel to --say):
  voicemode converse --ask 'nova:How did the demo land?' \\
                     --ask 'nova:Anything you would change?'
  # Prints the survey JSON to stdout; exit 0 if completed, exit 3 if the
  # survey stopped early (break/error). Mixing --say and --ask in one
  # command errors -- click can't preserve interleaving order across two
  # repeatable options; use --script for a mixed say/ask sequence.
\b
  # --script reads a JSON array of turns (same schema as the MCP tool),
  # including "ask" turns -- the mixed-sequence surface. Use it for text
  # containing ':'. '-' = stdin (heredoc-friendly):
  voicemode converse --script - <<'JSON'
  [ {"say":"My milkshake brings all the boys to the yard.", "voice":"sandy"},
    {"ask":"So! You still want a milkshake?", "voice":"monkey", "pause_after_ms":400} ]
  JSON
"""


def _parse_say_item(say_str, default_voice):
    """Parse a single --say 'VOICE:TEXT' value into a turn dict (VM-1772).

    Splits on the FIRST ':' only. No ':' (or an empty VOICE part) → the whole
    string is the text and the voice falls back to --voice/default. Text that
    contains a ':' should use --script instead (documented escape hatch).
    """
    if ':' in say_str:
        voice_part, text_part = say_str.split(':', 1)
        voice_part = voice_part.strip()
        return {'say': text_part, 'voice': voice_part or default_voice}
    return {'say': say_str, 'voice': default_voice}


def _parse_ask_item(ask_str, default_voice):
    """Parse a single --ask 'VOICE:TEXT' value into a turn dict (VM-1775).

    Mirrors ``_parse_say_item`` exactly, except the turn asks (speaks, then
    listens and collects the reply) instead of just speaking.
    """
    if ':' in ask_str:
        voice_part, text_part = ask_str.split(':', 1)
        voice_part = voice_part.strip()
        return {'ask': text_part, 'voice': voice_part or default_voice}
    return {'ask': ask_str, 'voice': default_voice}


def _build_turns_from_cli(say_items, ask_items, script, default_voice):
    """Build the ``turns`` list from the CLI's --say / --ask / --script surfaces.

    Returns ``None`` when none is supplied (scalar message path). Raises
    ``click.UsageError`` on conflicting/invalid input.
    """
    if say_items and ask_items:
        raise click.UsageError(
            "Use either --say or --ask (repeatable), not both -- click can't "
            "preserve interleaving order across two repeatable options. Use "
            "--script for a mixed say/ask sequence."
        )
    if (say_items or ask_items) and script:
        raise click.UsageError("Use either --say/--ask (repeatable) or --script, not both.")

    if script:
        import json
        if script == '-':
            raw = sys.stdin.read()
            source = 'stdin'
        else:
            try:
                with open(os.path.expanduser(script), 'r') as fh:
                    raw = fh.read()
            except OSError as e:
                raise click.UsageError(f"--script: could not read {script}: {e}")
            source = script
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise click.UsageError(f"--script: {source} is not valid JSON: {e}")
        if not isinstance(parsed, list):
            raise click.UsageError("--script: expected a JSON array of turn objects.")
        # Apply the default voice to any turn that didn't specify one; leave the
        # rest of the schema for the MCP tool to validate.
        turns = []
        for item in parsed:
            if isinstance(item, dict) and not item.get('voice') and default_voice:
                item = {**item, 'voice': default_voice}
            turns.append(item)
        return turns

    if say_items:
        return [_parse_say_item(s, default_voice) for s in say_items]

    if ask_items:
        return [_parse_ask_item(a, default_voice) for a in ask_items]

    return None


def _survey_exit_code(result):
    """Process exit code for a --ask/--script survey result (VM-1775).

    Survey mode (>=1 ask turn) returns a JSON string whose top level is
    ``{"survey": {...}}`` (see README ## Design's return contract).
    Speak-only turns (no ask) return the plain VM-1772 summary string --
    that isn't JSON, so this returns ``None`` and the default exit code (0)
    applies. For a survey: exit 0 when it completed, exit 3 on a partial
    (break/abort) so scripts can branch on the exit code without parsing.
    """
    if not result:
        return None
    import json
    try:
        payload = json.loads(result)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or "survey" not in payload:
        return None
    return 0 if payload["survey"].get("completed") else 3


@voice_mode_main_cli.command(epilog=_CONVERSE_EPILOG)
@click.help_option('-h', '--help')
@click.argument('message_args', nargs=-1, metavar='[MESSAGE]...')
@click.option('--message', '-m', default=None,
              help='Initial message to speak (alternative to positional MESSAGE)')
@click.option('--wait/--no-wait', 'wait', default=True,
              help='[DEPRECATED] --no-wait is deprecated; use --skip-stt instead. Wait for response after speaking.')
@click.option('--skip-stt', is_flag=True, default=False,
              help='Speak only; skip listening for a spoken response (STT). Replaces --no-wait.')
@click.option('--transport', type=click.Choice(['local', 'livekit']), default='local',
              show_default=True, help='Voice audio transport.')
@click.option('--room', 'room_name',
              help='Exact LiveKit room name (or omit for unambiguous prefix resolution).')
@click.option('--duration', '-d', type=float, default=DEFAULT_LISTEN_DURATION, help='Listen duration in seconds')
@click.option('--min-duration', type=float, default=MIN_RECORDING_DURATION, help='Minimum listen duration before silence detection')
@click.option('--voice', help='TTS voice name (nova, shimmer, af_sky) '
                               'profile, or a path to a .wav clip (absolute, ./relative, or ~/)',
              shell_complete=_complete_voice_names)
@click.option('--tts-provider', type=click.Choice(['openai', 'kokoro']), help='TTS provider')
@click.option('--tts-model', help='TTS model (e.g., tts-1, tts-1-hd)')
@click.option('--tts-instructions', help='Tone/style instructions for gpt-4o-mini-tts')
@click.option('--audio-feedback/--no-audio-feedback', default=None, help='Enable/disable audio feedback')
@click.option('--audio-format', help='Audio format (pcm, mp3, wav, flac, aac, opus)')
@click.option('--disable-silence-detection', is_flag=True, help='Disable silence detection')
@click.option('--speed', type=float, help='Speech rate (0.25 to 4.0)')
@click.option('--vad-aggressiveness', type=int, help='VAD aggressiveness (0-3)')
@click.option('--skip-tts/--no-skip-tts', default=None, help='Skip TTS and only show text')
@click.option('--skip-conch', is_flag=True, default=False,
              help='Bypass the conch lock; speak immediately even if another agent holds it.')
@click.option('--say', 'say_items', multiple=True, metavar="'VOICE:TEXT'",
              help="Speak a turn in a multi-voice sequence. Repeatable; order preserved. "
                   "'VOICE:' prefix optional (falls back to --voice/default). Speak-only.")
@click.option('--ask', 'ask_items', multiple=True, metavar="'VOICE:TEXT'",
              help="Speak a turn, then listen for and collect a spoken reply, aligned "
                   "to this turn in the returned survey JSON. Repeatable; order preserved. "
                   "'VOICE:' prefix optional (falls back to --voice/default). Mixing --say "
                   "and --ask errors -- use --script for a mixed sequence.")
@click.option('--script', 'script', default=None, metavar='FILE|-',
              help="Read a JSON array of turns (same schema as the MCP tool, including "
                   "\"ask\" turns). '-' reads stdin (heredoc-friendly). Use this for text "
                   "containing ':' or a mixed say/ask sequence.")
@click.option('--pause-after-ms', 'pause_after_ms', type=int, default=150, show_default=True,
              help='Silence (ms) inserted after each turn in a --say/--ask/--script sequence.')
@click.option('--ack', is_flag=True, default=False,
              help="Survey capture cue: play a short content-free confirmation sound "
                   "when — and only when — an --ask turn captures a reply (silent on a "
                   "timeout), so you can tell 'heard you' from 'didn't hear'. Default off.")
@click.option('--continuous', '-c', is_flag=True, help='Continuous conversation mode')
def converse(message_args, message, wait, skip_stt, transport, room_name, duration, min_duration, voice, tts_provider,
            tts_model, tts_instructions, audio_feedback, audio_format, disable_silence_detection,
            speed, vad_aggressiveness, skip_tts, skip_conch, say_items, ask_items, script,
            pause_after_ms, ack, continuous):
    """Have a voice conversation directly from the command line.

    The MESSAGE to speak can be passed as a positional argument or via
    -m/--message. Use `--` to pass a message that starts with a dash.

    For a multi-voice sequence spoken gap-free in one call, use repeatable
    --say 'VOICE:TEXT' (speak-only) or --ask 'VOICE:TEXT' (speak, then listen
    and collect a reply -- a paced survey), or --script FILE|- (a JSON array
    of turns, the mixed say/ask surface).
    """
    # VM-1772/VM-1775: build the optional turns[] sequence from --say / --ask /
    # --script. --say is speak-only; --ask collects a reply per turn (returns
    # the survey JSON instead of the speak-only summary). Mutually exclusive
    # with a scalar message and with continuous mode.
    turns = _build_turns_from_cli(say_items, ask_items, script, voice)
    if transport == "livekit" and turns is not None:
        raise click.UsageError(
            "--transport livekit does not support --say/--ask/--script yet; "
            "pass one scalar MESSAGE."
        )
    if transport == "livekit" and continuous:
        raise click.UsageError(
            "--transport livekit does not support --continuous yet; "
            "run one converse command per exchange."
        )
    if turns is not None:
        if message_args or message is not None:
            raise click.UsageError(
                "--say/--ask/--script speak a turns sequence; don't combine them with a "
                "positional message or --message/-m."
            )
        if continuous:
            raise click.UsageError("--say/--ask/--script can't be used with --continuous.")
        if not turns:
            raise click.UsageError("--say/--ask/--script produced no turns to speak.")

    # Resolve the message source:
    #   - positional MESSAGE wins when given
    #   - --message/-m is kept for backward compatibility and scripts
    #   - passing BOTH is ambiguous and errors loudly (no silent "pick one")
    #   - if neither is given, fall back to the default greeting
    if message_args:
        if message is not None:
            raise click.UsageError(
                "Pass the message as either a positional argument OR --message/-m, not both."
            )
        message = ' '.join(message_args)
    elif message is None and turns is None:
        message = "Hello! How can I help you today?"

    # Deprecation: --no-wait was renamed to --skip-stt.
    # `wait` defaults to True, so `wait is False` means the user explicitly
    # passed --no-wait on the command line.
    if wait is False:
        click.echo(
            "⚠️  --no-wait is deprecated and will be removed in a future release. "
            "Use --skip-stt instead.",
            err=True,
        )
        # Fold the legacy flag into the new one so downstream logic only
        # needs to consult `skip_stt`.
        skip_stt = True

    # `wait_for_response` is the inverse of skip_stt going forward.
    wait_for_response = not skip_stt
    # Check core dependencies before running
    from voice_mode.utils.dependencies.checker import check_component_dependencies

    results = check_component_dependencies('core')
    missing = [pkg for pkg, installed in results.items() if not installed]

    if missing:
        click.echo(f"⚠️  Missing core dependencies: {', '.join(missing)}")
        click.echo("   Run 'voicemode deps' to install them")
        return

    # The direct CLI owns the event loop for the whole conversation and has no
    # MCP request deadline or follow-up request in which to call
    # ``converse_continue``. Run the core operation to completion instead of
    # entering the MCP-only continuation manager; otherwise an in-progress
    # result makes ``asyncio.run`` cancel the still-speaking/listening job as it
    # closes its loop.
    from voice_mode.core import cleanup as cleanup_clients
    from voice_mode.tools.converse import (
        _converse_core as converse_fn,
        openai_clients,
    )
    
    async def run_conversation():
        """Run the conversation asynchronously."""
        # Suppress the spurious aiohttp warning that appears on startup
        # This warning is a false positive from asyncio detecting an unclosed
        # session that was likely created during module import
        import logging
        logging.getLogger('asyncio').setLevel(logging.CRITICAL)

        # Enable INFO logging for converse command to show progress
        logging.getLogger('voicemode').setLevel(logging.INFO)

        try:
            if turns is not None:
                # VM-1772/VM-1775: turns[] sequence -- speak-only (--say) or a
                # survey (--ask/--script with an ask turn: speak, listen,
                # collect the reply). One call, synth pipelined behind
                # playback/listening. listen_duration_max/min and
                # vad_aggressiveness are the call-level defaults an ask turn
                # inherits (harmless when there is no ask turn).
                result = await getattr(converse_fn, 'fn', converse_fn)(
                    turns=turns,
                    transport=transport,
                    room_name=room_name,
                    pause_after_ms=pause_after_ms,
                    wait_for_response=False,
                    listen_duration_max=duration,
                    listen_duration_min=min_duration,
                    voice=voice,
                    tts_provider=tts_provider,
                    tts_model=tts_model,
                    tts_instructions=tts_instructions,
                    chime_enabled=audio_feedback,
                    audio_format=audio_format,
                    disable_silence_detection=disable_silence_detection,
                    speed=speed,
                    vad_aggressiveness=vad_aggressiveness,
                    skip_tts=skip_tts,
                    skip_conch=skip_conch,
                    ack=ack,
                )
                # Survey JSON to stdout only (no other stdout chatter); exit
                # 0 completed / 3 partial so scripts can branch on exit code.
                if result:
                    click.echo(result)
                exit_code = _survey_exit_code(result)
                if exit_code:
                    sys.exit(exit_code)
                return

            if continuous:
                # Continuous conversation mode
                click.echo("🎤 Starting continuous conversation mode...")
                click.echo("   Press Ctrl+C to exit\n")
                
                # First message
                result = await getattr(converse_fn, 'fn', converse_fn)(
                    message=message,
                    transport=transport,
                    room_name=room_name,
                    wait_for_response=True,
                    listen_duration_max=duration,
                    listen_duration_min=min_duration,
                    voice=voice,
                    tts_provider=tts_provider,
                    tts_model=tts_model,
                    tts_instructions=tts_instructions,
                    chime_enabled=audio_feedback,
                    audio_format=audio_format,
                    disable_silence_detection=disable_silence_detection,
                    speed=speed,
                    vad_aggressiveness=vad_aggressiveness,
                    skip_tts=skip_tts,
                    skip_conch=skip_conch,
                )

                if result and "Voice response:" in result:
                    click.echo(f"You: {result.split('Voice response:')[1].split('|')[0].strip()}")

                # Continue conversation
                while True:
                    # Wait for user's next input
                    result = await getattr(converse_fn, 'fn', converse_fn)(
                        message="",  # Empty message for listening only
                        transport=transport,
                        room_name=room_name,
                        wait_for_response=True,
                        listen_duration_max=duration,
                        listen_duration_min=min_duration,
                        voice=voice,
                        tts_provider=tts_provider,
                        tts_model=tts_model,
                        tts_instructions=tts_instructions,
                        chime_enabled=audio_feedback,
                        audio_format=audio_format,
                        disable_silence_detection=disable_silence_detection,
                        speed=speed,
                        vad_aggressiveness=vad_aggressiveness,
                        skip_tts=skip_tts,
                        skip_conch=skip_conch,
                    )
                    
                    if result and "Voice response:" in result:
                        user_text = result.split('Voice response:')[1].split('|')[0].strip()
                        click.echo(f"You: {user_text}")
                        
                        # Check for exit commands
                        if user_text.lower() in ['exit', 'quit', 'goodbye', 'bye']:
                            await getattr(converse_fn, 'fn', converse_fn)(
                                message="Goodbye!",
                                transport=transport,
                                room_name=room_name,
                                wait_for_response=False,
                                voice=voice,
                                tts_provider=tts_provider,
                                tts_model=tts_model,
                                audio_format=audio_format,
                                speed=speed,
                                skip_tts=skip_tts,
                                skip_conch=skip_conch,
                            )
                            break
            else:
                # Single conversation
                result = await getattr(converse_fn, 'fn', converse_fn)(
                    message=message,
                    transport=transport,
                    room_name=room_name,
                    wait_for_response=wait_for_response,
                    listen_duration_max=duration,
                    listen_duration_min=min_duration,
                    voice=voice,
                    tts_provider=tts_provider,
                    tts_model=tts_model,
                    tts_instructions=tts_instructions,
                    chime_enabled=audio_feedback,
                    audio_format=audio_format,
                    disable_silence_detection=disable_silence_detection,
                    speed=speed,
                    vad_aggressiveness=vad_aggressiveness,
                    skip_tts=skip_tts,
                    skip_conch=skip_conch,
                )

                # Display result
                if result:
                    if "Voice response:" in result:
                        # Extract the response text and timing info
                        parts = result.split('|')
                        response_text = result.split('Voice response:')[1].split('|')[0].strip()
                        timing_info = parts[1].strip() if len(parts) > 1 else ""

                        click.echo(f"\n📢 Spoke: {message}")
                        if wait_for_response:
                            click.echo(f"🎤 Heard: {response_text}")
                        if timing_info:
                            click.echo(f"⏱️  {timing_info}")
                    else:
                        click.echo(result)
                        
        except KeyboardInterrupt:
            click.echo("\n\n👋 Conversation ended")
        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            import traceback
            if os.environ.get('VOICEMODE_DEBUG'):
                traceback.print_exc()
        finally:
            await cleanup_clients(openai_clients)
    
    # Run the async function
    asyncio.run(run_conversation())


# Serve command - HTTP/SSE server for remote access
@voice_mode_main_cli.command()
@click.help_option('-h', '--help')
@click.option('--host', default='127.0.0.1', help='Host to bind to (use 0.0.0.0 for all interfaces)')
@click.option('--port', '-p', default=8765, type=int, help='Port to bind to')
@click.option('--transport', '-t', default=SERVE_TRANSPORT,
              type=click.Choice(['streamable-http', 'sse']),
              help='MCP transport protocol (streamable-http is recommended, sse is deprecated)')
@click.option('--log-level', default='info', type=click.Choice(['debug', 'info', 'warning', 'error']),
              help='Logging level')
@click.option('--allow-anthropic/--no-allow-anthropic', default=None,
              help='Allow connections from Anthropic IP ranges (for Claude Cowork)')
@click.option('--allow-tailscale/--no-allow-tailscale', default=None,
              help='Allow connections from Tailscale IP range (100.64.0.0/10)')
@click.option('--allow-ip', multiple=True,
              help='Allow connections from custom CIDR ranges (can be specified multiple times)')
@click.option('--trust-proxy', multiple=True,
              help='Trust X-Forwarded-For from these reverse-proxy CIDRs (can be repeated). '
                   'Required for the IP allowlist to honor forwarded client IPs behind a proxy. '
                   'Leave unset unless you control the proxy (GHSA-2qvv-vjq9-g5r4).')
@click.option('--allow-local/--no-allow-local', default=None,
              help='Allow connections from local/private IP ranges (default: enabled)')
@click.option('--secret', default=None,
              help='Require a secret path segment for access (e.g., --secret=my-uuid)')
@click.option('--token', default=None,
              help='Require Bearer token authentication via Authorization header')
def serve(host: str, port: int, transport: str, log_level: str, allow_anthropic: bool | None,
          allow_tailscale: bool | None, allow_ip: tuple, trust_proxy: tuple, allow_local: bool | None,
          secret: str | None, token: str | None):
    """Start VoiceMode as an HTTP/SSE server for remote access.

    This enables Claude Code, Claude Desktop, Claude Cowork, or other MCP
    clients to connect to VoiceMode over HTTP instead of stdio. Useful for:

    - Multiple Claude Code projects sharing one VoiceMode instance
    - Claude Cowork (runs in a sandboxed VM without audio access)
    - Claude Desktop with mcp-remote
    - Any MCP client that supports HTTP transport

    The server exposes all VoiceMode MCP tools via the HTTP transport.
    Audio capture and playback happens on the host machine.

    Examples:

        # Start server on localhost (default)
        voicemode serve

        # Allow connections from VMs (bind to all interfaces)
        voicemode serve --host 0.0.0.0

        # Custom port
        voicemode serve --port 9000

        # Enable Anthropic IP ranges (for Claude Cowork)
        voicemode serve --host 0.0.0.0 --allow-anthropic

        # Allow all devices on your Tailscale network
        voicemode serve --allow-tailscale

        # Add custom IP allowlist
        voicemode serve --allow-ip 10.0.0.0/8 --allow-ip 192.168.1.100/32

        # Behind a trusted reverse proxy (honor X-Forwarded-For from it)
        voicemode serve --allow-ip 203.0.113.0/24 --trust-proxy 127.0.0.1/32

        # Use secret path for authentication
        voicemode serve --secret my-secret-uuid

        # Use Bearer token authentication
        voicemode serve --token my-secret-token

    Connect from Claude Code:

        claude mcp add --transport http voicemode http://localhost:8765/mcp
    """
    import logging
    from .server import mcp
    from .config import setup_logging
    from .serve_middleware import (
        AccessLogMiddleware,
        IPAllowlistMiddleware,
        TokenAuthMiddleware,
        ANTHROPIC_CIDRS,
        TAILSCALE_CIDRS,
        LOCAL_CIDRS,
    )

    # Warn if SSE transport is used (deprecated in favor of streamable-http)
    if transport == "sse":
        click.echo(
            click.style("Warning: ", fg="yellow", bold=True) +
            "SSE transport is deprecated. Use --transport streamable-http for the modern protocol.",
            err=True
        )

    # Set up logging based on level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logger = setup_logging()
    logger.setLevel(numeric_level)

    # Apply config defaults when CLI options are not provided
    # CLI flags always override config file values
    if allow_local is None:
        allow_local = SERVE_ALLOW_LOCAL
    if allow_anthropic is None:
        allow_anthropic = SERVE_ALLOW_ANTHROPIC
    if allow_tailscale is None:
        allow_tailscale = SERVE_ALLOW_TAILSCALE
    if not allow_ip and SERVE_ALLOWED_IPS:
        # Parse comma-separated CIDRs from config
        allow_ip = tuple(cidr.strip() for cidr in SERVE_ALLOWED_IPS.split(',') if cidr.strip())
    if not trust_proxy and SERVE_TRUSTED_PROXIES:
        # Parse comma-separated trusted-proxy CIDRs from config
        trust_proxy = tuple(cidr.strip() for cidr in SERVE_TRUSTED_PROXIES.split(',') if cidr.strip())
    if secret is None and SERVE_SECRET:
        secret = SERVE_SECRET
    if token is None and SERVE_TOKEN:
        token = SERVE_TOKEN

    # Build allowed CIDR list
    allowed_cidrs: list[str] = []
    if allow_local:
        allowed_cidrs.extend(LOCAL_CIDRS)
    if allow_anthropic:
        allowed_cidrs.extend(ANTHROPIC_CIDRS)
    if allow_tailscale:
        allowed_cidrs.extend(TAILSCALE_CIDRS)
    if allow_ip:
        allowed_cidrs.extend(allow_ip)

    # Trusted reverse-proxy CIDRs whose X-Forwarded-For header is honored.
    trusted_proxies: list[str] = list(trust_proxy) if trust_proxy else []

    # Determine if any security is enabled
    has_ip_allowlist = bool(allowed_cidrs) and (allow_anthropic or allow_tailscale or allow_ip or not allow_local)
    has_secret = bool(secret)  # secret is set and non-empty
    has_token = bool(token)  # token is set and non-empty
    has_security = has_ip_allowlist or has_secret or has_token

    # Determine base path based on transport
    if transport == "streamable-http":
        base_path = "/mcp"
    else:  # sse
        base_path = "/sse"

    # Build the endpoint path with optional secret segment
    endpoint_path = f"{base_path}/{secret}" if has_secret else base_path
    endpoint_url = f"http://{host}:{port}{endpoint_path}"

    # Helper to mask secrets
    def mask_secret(s: str, show_chars: int = 4) -> str:
        if len(s) <= show_chars:
            return s[:1] + "..."
        return s[:show_chars] + "..."

    # Log startup info
    click.echo(f"Starting VoiceMode MCP server on {host}:{port}")
    click.echo(f"Transport: {transport}")
    click.echo()

    # Print security configuration if any is enabled
    if has_security:
        click.echo("Security configuration:")

        # IP allowlist info
        if allowed_cidrs:
            ip_parts = []
            if allow_local:
                ip_parts.append("local")
            if allow_anthropic:
                ip_parts.append(f"Anthropic ({ANTHROPIC_CIDRS[0]})")
            if allow_tailscale:
                ip_parts.append(f"Tailscale ({TAILSCALE_CIDRS[0]})")
            if allow_ip:
                ip_parts.append(f"custom ({len(allow_ip)} CIDRs)")
            click.echo(f"  IP allowlist: {' + '.join(ip_parts)}")
            if trusted_proxies:
                click.echo(f"  Trusted proxies (X-Forwarded-For honored): {', '.join(trusted_proxies)}")
            else:
                click.echo("  Trusted proxies: none (X-Forwarded-For ignored for allowlist)")
        else:
            click.echo("  IP allowlist: disabled (--no-allow-local)")

        # Secret path info
        if has_secret:
            click.echo(f"  URL secret: {mask_secret(secret)}")

        # Token auth info
        if has_token:
            click.echo(f"  Bearer token: {mask_secret(token)}")

        click.echo()

    click.echo(f"Endpoint: {endpoint_url}")
    click.echo(f"Log level: {log_level}")
    click.echo()

    # Show Claude Code connection options
    click.echo(click.style("Connect from Claude Code:", bold=True))
    click.echo()
    click.echo(f"  claude mcp add --transport http voicemode {endpoint_url}")
    click.echo()

    # Show JSON config for manual setup
    click.echo(click.style("Manual configuration:", bold=True))
    click.echo()
    click.echo('  {')
    click.echo('    "mcpServers": {')
    click.echo('      "voicemode": {')
    click.echo('        "type": "http",')
    click.echo(f'        "url": "{endpoint_url}"')
    click.echo('      }')
    click.echo('    }')
    click.echo('  }')
    click.echo()

    click.echo(click.style("Legacy (mcp-remote):", bold=True))
    click.echo(f"  npx mcp-remote {endpoint_url}")
    click.echo()
    click.echo("Press Ctrl+C to stop the server")
    click.echo()

    # Create the app with the selected transport (fastmcp 2.14+ API)
    app = mcp.http_app(transport=transport, path=endpoint_path)

    # Note: Middleware is applied in reverse order (last added = first executed)
    # Add token auth middleware (checked after IP allowlist)
    if has_token:
        app.add_middleware(TokenAuthMiddleware, token=token)

    # Add IP allowlist middleware (checked first)
    if allowed_cidrs:
        app.add_middleware(
            IPAllowlistMiddleware,
            allowed_cidrs=allowed_cidrs,
            trusted_proxies=trusted_proxies,
        )

    # Add access logging middleware (runs first, logs all requests)
    app.add_middleware(AccessLogMiddleware)

    try:
        # Run the app with uvicorn directly to use our middleware
        import uvicorn

        # Disable uvicorn's access logging - we use our own AccessLogMiddleware
        # which shows X-Forwarded-For headers
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=log_level.lower(),
            access_log=False,  # Disable uvicorn access log, use our middleware instead
        )
    except KeyboardInterrupt:
        click.echo("\nServer stopped")
    except Exception as e:
        click.echo(f"Error starting server: {e}", err=True)
        raise click.Abort()


# VM-1314: native stdio<->Streamable-HTTP bridge. Hidden -- it is plumbing for
# the plugin's smart launcher (voicemode-mcp-launcher), not a user-facing
# command, but exposing it as a subcommand makes the bridge directly testable
# end-to-end against a real `voicemode serve`.
@voice_mode_main_cli.command(name="mcp-bridge", hidden=True)
@click.help_option('-h', '--help')
@click.argument('url')
@click.option('--token', default=None,
              help='Bearer token (Authorization: Bearer <token>). '
                   'Defaults to $VOICEMODE_MCP_TOKEN.')
def mcp_bridge(url: str, token: str | None):
    """Bridge this stdio process to a remote Streamable-HTTP voicemode serve.

    Native (no npx/Node). Used by the plugin's smart launcher when
    VOICEMODE_MCP_URL is set; also runnable directly for testing:

        voicemode mcp-bridge http://host:8765/mcp
        voicemode mcp-bridge http://host:8765/mcp/<secret> --token <tok>
    """
    from .mcp_bridge import run_bridge

    if token is None:
        token = os.environ.get("VOICEMODE_MCP_TOKEN", "").strip() or None
    run_bridge(url, token)


# Completions command
@voice_mode_main_cli.command()
@click.help_option('-h', '--help')
@click.argument('shell', type=click.Choice(['bash', 'zsh', 'fish']))
@click.option('--install', is_flag=True, help='Install completion script to the appropriate location')
def completions(shell, install):
    """Generate or install shell completion scripts.
    
    Examples:
        voicemode completions bash              # Output bash completion to stdout
        voicemode completions bash --install    # Install to ~/.bash_completion.d/
        voicemode completions zsh --install     # Install to ~/.zfunc/
        voicemode completions fish --install    # Install to ~/.config/fish/completions/
    """
    from pathlib import Path
    from click.shell_completion import get_completion_class

    # Generate the completion script using Click's own machinery rather than
    # hand-rolled templates. The previous inline scripts parsed the completion
    # backend's output as comma-separated "type,value" pairs, but Click emits
    # one item per group of newline-separated lines (type / value / help). That
    # mismatch meant tab completion silently produced nothing. Delegating to
    # Click guarantees the script always matches the installed Click version's
    # completion protocol.
    comp_cls = get_completion_class(shell)
    if comp_cls is None:
        raise click.ClickException(f"Shell completion is not supported for {shell!r}")
    comp = comp_cls(voice_mode_main_cli, {}, 'voicemode', '_VOICEMODE_COMPLETE')
    completion_script = comp.source()

    if install:
        # Define installation locations for each shell
        locations = {
            'bash': '~/.bash_completion.d/voicemode',
            'zsh': '~/.zfunc/_voicemode',
            'fish': '~/.config/fish/completions/voicemode.fish'
        }
        
        install_path = Path(locations[shell]).expanduser()
        install_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write completion script to file
        install_path.write_text(completion_script)
        click.echo(f"✅ Installed {shell} completions to {install_path}")
        
        # Provide shell-specific instructions
        if shell == 'bash':
            click.echo("\nTo activate now, run:")
            click.echo(f"  source {install_path}")
            click.echo("\nTo activate permanently, add to ~/.bashrc:")
            click.echo(f"  source {install_path}")
        elif shell == 'zsh':
            click.echo("\nTo activate now, run:")
            click.echo("  autoload -U compinit && compinit")
            click.echo("\nMake sure ~/.zfunc is in your fpath (add to ~/.zshrc):")
            click.echo("  fpath=(~/.zfunc $fpath)")
        elif shell == 'fish':
            click.echo("\nCompletions will be active in new fish sessions.")
            click.echo("To activate now, run:")
            click.echo(f"  source {install_path}")
    else:
        # Output completion script to stdout
        click.echo(completion_script)

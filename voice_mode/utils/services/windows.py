"""Windows service backend: privilege detection, install scopes, Scheduled Tasks.

VoiceMode runs Whisper/Kokoro/serve as long-lived background processes. On
macOS that is launchd and on Linux systemd --user. On Windows we use Task
Scheduler, which can run a process without a console and restart it when it
crashes, needs no extra software, and works with and without admin rights.

Two install scopes share one code path (see docs/architecture/adr/0001):

``user``     No elevation needed. Data lives under ``~/.voicemode``. The task
             runs as the current user, starts at logon, and runs unelevated.
``machine``  Needs an elevated shell. Data lives under ``%ProgramData%\\VoiceMode``
             so every account shares one copy. The task runs as SYSTEM and starts
             at boot, before anyone logs in.

``resolve_scope`` picks ``machine`` when the process is elevated and ``user``
otherwise, unless the caller or ``VOICEMODE_SERVICE_SCOPE`` says otherwise.
"""

from __future__ import annotations

import base64
import getpass
import json
import logging
import os
import platform
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("voicemode")

SCOPE_ENV_VAR = "VOICEMODE_SERVICE_SCOPE"
TASK_PREFIX = "VoiceMode-"
_SYSTEM_ACCOUNTS = {"SYSTEM", "NT AUTHORITY\\SYSTEM"}

# Service identifier -> Scheduled Task name suffix.
_TASK_SUFFIX = {
    "whisper": "Whisper",
    "kokoro": "Kokoro",
    "voicemode": "Serve",
    "livekit": "LiveKit",
    "livekit_web": "LiveKitWeb",
}


class ServiceScope(str, Enum):
    USER = "user"
    MACHINE = "machine"


class ElevationRequired(RuntimeError):
    """A machine-wide operation was requested from a non-elevated process."""


@dataclass
class TaskInfo:
    """Observed state of a registered VoiceMode Scheduled Task."""

    name: str
    state: str
    enabled: bool
    scope: ServiceScope


def is_windows() -> bool:
    return platform.system() == "Windows"


def is_admin() -> bool:
    """True when the current process is elevated (always False off Windows)."""
    if not is_windows():
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def resolve_scope(requested: Optional[str] = None) -> ServiceScope:
    """Decide the install scope.

    Order: explicit argument, ``VOICEMODE_SERVICE_SCOPE``, then auto
    (machine when elevated, user otherwise). Asking for ``machine`` without
    elevation raises ``ElevationRequired`` rather than silently downgrading, so
    the user knows their request was not honoured.
    """
    choice = (requested or os.environ.get(SCOPE_ENV_VAR) or "auto").strip().lower()
    if choice not in {"auto", "user", "machine"}:
        raise ValueError(f"Unknown scope '{choice}' (expected auto, user or machine)")
    if choice == "user":
        return ServiceScope.USER
    if choice == "machine":
        if not is_admin():
            raise ElevationRequired(
                "Machine-wide install needs an elevated (Run as administrator) "
                "shell. Re-run elevated, or use --scope user."
            )
        return ServiceScope.MACHINE
    return ServiceScope.MACHINE if is_admin() else ServiceScope.USER


def user_base_dir() -> Path:
    return Path(os.path.expanduser(os.environ.get("VOICEMODE_BASE_DIR", "~/.voicemode")))


def machine_base_dir() -> Path:
    program_data = os.environ.get("ProgramData") or r"C:\ProgramData"
    return Path(program_data) / "VoiceMode"


def base_dir(scope: ServiceScope) -> Path:
    return machine_base_dir() if scope == ServiceScope.MACHINE else user_base_dir()


def candidate_base_dirs() -> List[Path]:
    """Base directories to search for an installed service, user first."""
    return [user_base_dir(), machine_base_dir()]


def service_dir(service: str, scope: ServiceScope) -> Path:
    return base_dir(scope) / "services" / service


def log_file(service: str, scope: ServiceScope) -> Path:
    return base_dir(scope) / "logs" / service / f"{service}.log"


def task_name(service: str) -> str:
    return TASK_PREFIX + _TASK_SUFFIX.get(service, service.title().replace("_", ""))


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_powershell(script: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a PowerShell snippet. EncodedCommand avoids every quoting pitfall."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _current_account() -> str:
    domain = os.environ.get("USERDOMAIN") or platform.node()
    return f"{domain}\\{getpass.getuser()}"


def build_register_script(service: str, scope: ServiceScope, start_script: Path, description: str) -> str:
    """PowerShell that (re)registers the task for ``service`` in ``scope``."""
    name = task_name(service)
    arguments = (
        "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass "
        f'-File "{start_script}"'
    )
    if scope == ServiceScope.MACHINE:
        trigger = "New-ScheduledTaskTrigger -AtStartup"
        principal = (
            "New-ScheduledTaskPrincipal -UserId 'SYSTEM' "
            "-LogonType ServiceAccount -RunLevel Highest"
        )
    else:
        account = _current_account()
        trigger = f"New-ScheduledTaskTrigger -AtLogOn -User {_ps_quote(account)}"
        principal = (
            f"New-ScheduledTaskPrincipal -UserId {_ps_quote(account)} "
            "-LogonType Interactive -RunLevel Limited"
        )
    return "\n".join([
        "$ErrorActionPreference = 'Stop'",
        f"$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument {_ps_quote(arguments)}",
        f"$trigger = {trigger}",
        f"$principal = {principal}",
        "$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -StartWhenAvailable "
        "-ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew "
        "-RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)",
        f"Register-ScheduledTask -TaskName {_ps_quote(name)} -Action $action "
        f"-Trigger $trigger -Principal $principal -Settings $settings "
        f"-Description {_ps_quote(description)} -Force | Out-Null",
    ])


def register_task(service: str, scope: ServiceScope, start_script: Path, description: Optional[str] = None) -> None:
    """Register (or replace) the Scheduled Task. Raises RuntimeError on failure."""
    if scope == ServiceScope.MACHINE and not is_admin():
        raise ElevationRequired("Registering a machine-wide task needs an elevated shell.")
    description = description or f"VoiceMode {service} service ({scope.value} scope)"
    result = run_powershell(build_register_script(service, scope, start_script, description))
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "Register-ScheduledTask failed")


def unregister_task(service: str) -> bool:
    """Remove the task. Returns False when it did not exist."""
    name = _ps_quote(task_name(service))
    result = run_powershell(
        f"if (Get-ScheduledTask -TaskName {name} -ErrorAction SilentlyContinue) "
        f"{{ Stop-ScheduledTask -TaskName {name} -ErrorAction SilentlyContinue; "
        f"Unregister-ScheduledTask -TaskName {name} -Confirm:$false; 'removed' }}"
    )
    return result.returncode == 0 and "removed" in result.stdout


def get_task(service: str) -> Optional[TaskInfo]:
    """Return the registered task, or None when the service has no task."""
    name = _ps_quote(task_name(service))
    result = run_powershell(
        f"$t = Get-ScheduledTask -TaskName {name} -ErrorAction SilentlyContinue; "
        "if ($t) { [pscustomobject]@{ name=$t.TaskName; state=[string]$t.State; "
        "enabled=$t.Settings.Enabled; user=$t.Principal.UserId } | ConvertTo-Json -Compress }"
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return None
    user = str(data.get("user") or "").upper()
    scope = ServiceScope.MACHINE if user in _SYSTEM_ACCOUNTS else ServiceScope.USER
    return TaskInfo(
        name=data["name"], state=data["state"], enabled=bool(data["enabled"]), scope=scope
    )


def installed_scope(service: str) -> Optional[ServiceScope]:
    task = get_task(service)
    return task.scope if task else None


def _task_action(service: str, verb: str) -> subprocess.CompletedProcess:
    return run_powershell(
        f"{verb} -TaskName {_ps_quote(task_name(service))} -ErrorAction Stop"
    )


def start_task(service: str) -> subprocess.CompletedProcess:
    return _task_action(service, "Start-ScheduledTask")


def stop_task(service: str) -> subprocess.CompletedProcess:
    return _task_action(service, "Stop-ScheduledTask")


def enable_task(service: str) -> subprocess.CompletedProcess:
    return _task_action(service, "Enable-ScheduledTask")


def disable_task(service: str) -> subprocess.CompletedProcess:
    return _task_action(service, "Disable-ScheduledTask")


def kill_port_owner(port: int) -> None:
    """Terminate whatever listens on ``port`` (used after a task stop)."""
    run_powershell(
        f"Get-NetTCPConnection -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue "
        "| ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
    )


def grant_users_read(path: Path) -> None:
    """Machine scope: let non-admin accounts read the shared install."""
    run_powershell(
        f"icacls {_ps_quote(str(path))} /grant '*S-1-5-32-545:(OI)(CI)RX' /T /C | Out-Null"
    )

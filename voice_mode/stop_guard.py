"""Turn-end guard: don't let an agent walk away from a user who is still talking.

Run by a client's stop hook (Cursor ``stop``, Claude Code ``Stop``) when the
agent is about to finish. If a voice recording is still in progress, or a
finished transcript was never collected, the hook asks the agent to continue
and read it (``converse_inbox``) instead of ending the turn.

Standard library only, and fail-open: any problem means "let the agent stop".
It never marks anything collected; the agent does that by reading the inbox.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

# An in-progress job older than this belongs to a dead server, not a live call.
ACTIVE_MAX_AGE = 600.0
# A finished transcript older than this is stale; the user has moved on.
FINISHED_MAX_AGE = 3600.0
# How many times the guard may push the agent for the same job.
MAX_PUSHES_PER_JOB = 3

CLIENTS = ("cursor", "claude")


def _base_dir() -> Path:
    return Path(os.environ.get("VOICEMODE_BASE_DIR", str(Path.home() / ".voicemode"))).expanduser()


def _roots(payload: dict[str, Any]) -> list[str]:
    roots = payload.get("workspace_roots")
    if isinstance(roots, list):
        return [str(r) for r in roots if r]
    cwd = payload.get("cwd")
    return [str(cwd)] if cwd else []


def _matches(project_path: Optional[str], roots: list[str]) -> bool:
    """Jobs from a server with no useful working directory match any window."""
    if not project_path or project_path in ("/", str(Path.home())) or not roots:
        return True
    project = Path(project_path)
    for root in roots:
        base = Path(root)
        if project == base or base in project.parents or project in base.parents:
            return True
    return False


def pending_jobs(
    payload: dict[str, Any], jobs_dir: Optional[Path] = None, now: Optional[float] = None
) -> list[dict[str, Any]]:
    jobs_dir = jobs_dir or (_base_dir() / "jobs")
    now = time.time() if now is None else now
    roots = _roots(payload)
    found: list[dict[str, Any]] = []
    try:
        paths = list(jobs_dir.glob("*.json"))
    except OSError:
        return []
    for path in paths:
        try:
            job = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not _matches(job.get("project_path"), roots):
            continue
        age = now - float(job.get("updated_at") or job.get("created_at") or 0)
        status = job.get("status")
        if status == "in_progress" and age <= ACTIVE_MAX_AGE:
            found.append({"job_id": job.get("job_id"), "kind": "active"})
        elif (
            status == "completed"
            and job.get("delivered") is False
            and isinstance(job.get("result"), str)
            and age <= FINISHED_MAX_AGE
        ):
            found.append({"job_id": job.get("job_id"), "kind": "finished"})
    return found


def _push_counts(path: Path) -> dict[str, int]:
    try:
        data = json.loads(path.read_text())
        return {str(k): int(v) for k, v in data.items()}
    except (OSError, ValueError, AttributeError):
        return {}


def _message(jobs: list[dict[str, Any]]) -> str:
    active = [j for j in jobs if j["kind"] == "active"]
    if active:
        return (
            "The user is still on a voice call with you (a recording is in "
            "progress). Do not stop. Call the voicemode converse_inbox tool now; "
            "it shows the active job. Then keep calling converse_continue with "
            "that job_id until the user's reply arrives, and answer it with "
            "converse."
        )
    return (
        "The user said something by voice while you were not listening, and it "
        "was never delivered. Call the voicemode converse_inbox tool now, read "
        "what they said, and answer it with converse."
    )


def decide(
    client: str,
    payload: dict[str, Any],
    jobs_dir: Optional[Path] = None,
    state_path: Optional[Path] = None,
    now: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    """Return the hook output that keeps the agent going, or None to let it stop."""
    if client not in CLIENTS:
        return None
    # Cursor reports aborted/errored runs too; only a normal finish needs this.
    if payload.get("status") not in (None, "completed"):
        return None
    jobs = pending_jobs(payload, jobs_dir, now)
    if not jobs:
        return None

    state_path = state_path or (_base_dir() / "guard-state.json")
    counts = _push_counts(state_path)
    fresh = [j for j in jobs if counts.get(str(j["job_id"]), 0) < MAX_PUSHES_PER_JOB]
    if not fresh:
        return None
    for job in fresh:
        counts[str(job["job_id"])] = counts.get(str(job["job_id"]), 0) + 1
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(counts))
    except OSError:
        pass

    text = _message(fresh)
    if client == "cursor":
        return {"followup_message": text}
    return {"decision": "block", "reason": text}


def run(client: str, stdin_text: str) -> str:
    """Hook entry point: JSON in, JSON out ("" means let the agent stop)."""
    try:
        payload = json.loads(stdin_text) if stdin_text.strip() else {}
        if not isinstance(payload, dict):
            return ""
        result = decide(client, payload)
    except Exception:
        return ""
    return json.dumps(result) if result else ""

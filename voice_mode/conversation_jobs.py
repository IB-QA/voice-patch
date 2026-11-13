"""Server-owned jobs for voice operations that outlive one MCP request.

The MCP host may impose a request deadline shorter than a user's spoken reply.
ConversationJobManager lets ``converse`` return a compact continuation token
before that deadline while the original coroutine keeps running in this server
process. A later tool call waits on the same task instead of restarting audio.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Optional

from voice_mode.config import BASE_DIR, KEEP_HISTORY
from voice_mode.control_channel import get_control_state
from voice_mode.inbox import SESSION_KEY


logger = logging.getLogger("voicemode.conversation_jobs")

JOB_SCHEMA_VERSION = 1
DEFAULT_CONTINUATION_WAIT = 50.0
MAX_CONTINUATION_WAIT = 55.0

# A listen window at or below this fits inside one MCP request, so the caller
# never needs the continuation handshake. Only longer windows can outlive the
# host deadline, and only those hand back a job ID.
CONTINUATION_LISTEN_THRESHOLD = 60.0


def resolve_continuation_wait(
    requested: Optional[float],
    *,
    wait_for_response: bool,
    listen_duration_max: Optional[float],
    multi_turn: bool = False,
) -> Optional[float]:
    """Decide whether a converse call needs the continuation handshake.

    Returns the seconds to wait before handing back a job ID, or ``None`` to
    wait for the whole operation. An explicit ``requested`` value always wins;
    otherwise continuation turns on only when the listen window cannot fit in
    one MCP request.
    """
    if requested is not None:
        return requested
    if multi_turn:
        return DEFAULT_CONTINUATION_WAIT
    if not wait_for_response:
        return None
    if (
        listen_duration_max is not None
        and listen_duration_max > CONTINUATION_LISTEN_THRESHOLD
    ):
        return DEFAULT_CONTINUATION_WAIT
    return None


@dataclass
class ConversationJob:
    """One in-process voice operation and its durable result metadata."""

    job_id: str
    task: asyncio.Task[str]
    created_at: float
    status: str = "in_progress"
    result: Optional[str] = None
    error: Optional[str] = None
    polls: int = 0
    # True once the result has been handed back to a caller. A finished job
    # that stays False means the user's words never reached an agent.
    delivered: bool = False


# Told to the calling agent on every in-progress reply. A person talking for a
# minute or two is normal; ending the turn here abandons them mid-sentence.
KEEP_WAITING_INSTRUCTION = (
    "The user is still on the voice call (speaking or being heard). This is "
    "normal, not an error and not a loop. Do NOT end your turn, do NOT write a "
    "summary, do NOT start a new recording. Your very next action must be the "
    "converse_continue call in `next`, repeated for as long as it takes; only "
    "a spoken reply or a final error ends the wait."
)


class ConversationJobManager:
    """Own and retrieve long-running conversation tasks."""

    def __init__(self, jobs_dir: Optional[Path] = None) -> None:
        self._jobs: dict[str, ConversationJob] = {}
        self._jobs_dir = jobs_dir or BASE_DIR / "jobs"

    def create(self, operation: Awaitable[str]) -> ConversationJob:
        """Start an operation independently of the current request wait."""
        job_id = uuid.uuid4().hex
        task = asyncio.create_task(operation, name=f"voicemode-converse-{job_id[:8]}")
        job = ConversationJob(job_id=job_id, task=task, created_at=time.time())
        self._jobs[job_id] = job
        self._persist(job)
        task.add_done_callback(lambda completed: self._complete(job, completed))
        return job

    async def wait(self, job_id: str, wait_seconds: Optional[float]) -> str:
        """Wait for a job, or return a compact continuation instruction.

        ``wait_seconds=None`` waits for the whole operation and never returns a
        continuation token, so callers that cannot follow up with
        ``converse_continue`` still receive the spoken reply.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return self._load_terminal_result(job_id)

        if wait_seconds is None:
            try:
                result = await job.task
                self._mark_delivered(job)
                return result
            except asyncio.CancelledError:
                job.task.cancel()
                raise

        wait_seconds = max(0.0, min(float(wait_seconds), MAX_CONTINUATION_WAIT))
        try:
            result = await asyncio.wait_for(
                asyncio.shield(job.task),
                timeout=wait_seconds,
            )
            self._mark_delivered(job)
            return result
        except asyncio.TimeoutError:
            job.polls += 1
            return self._in_progress_result(
                job.job_id,
                wait_seconds,
                polls=job.polls,
                elapsed_seconds=time.time() - job.created_at,
            )
        except asyncio.CancelledError:
            # Explicit client cancellation must retain the existing VoiceMode
            # semantics: stop the audio operation and let cancellation reach
            # the MCP SDK's request boundary. Only our own timeout above is
            # allowed to leave the task running.
            job.task.cancel()
            raise

    async def stop(self, job_id: str, wait_seconds: float = 5.0) -> str:
        """Request a clean control-channel stop, then wait briefly for exit."""
        job = self._jobs.get(job_id)
        if job is None:
            return self._load_terminal_result(job_id)

        get_control_state().request_stop(message="conversation job stopped")
        return await self.wait(job_id, wait_seconds)

    def _complete(
        self,
        job: ConversationJob,
        task: asyncio.Task[str],
    ) -> None:
        try:
            job.result = task.result()
            job.status = "completed"
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.error = "Conversation job was cancelled."
        except Exception as exc:
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
        self._persist(job)

    def _persist(self, job: ConversationJob) -> None:
        if not KEEP_HISTORY:
            # Leave no trace: the job lives in memory only.
            return
        payload = {
            "schema_version": JOB_SCHEMA_VERSION,
            "job_id": job.job_id,
            "status": job.status,
            "created_at": job.created_at,
            "updated_at": time.time(),
            "result": job.result,
            "error": job.error,
            "delivered": job.delivered,
            "session_key": SESSION_KEY,
            "project_path": os.getcwd(),
        }
        try:
            self._jobs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = self._job_path(job.job_id)
            temporary = path.with_name(
                f".{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
            )
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temporary.chmod(0o600)
            os.replace(temporary, path)
        except OSError as exc:
            # Persistence is recovery metadata, not permission to break a live
            # voice operation. Conversation logs remain the transcript record.
            logger.debug("Could not persist conversation job %s: %s", job.job_id, exc)
            return

    def _mark_delivered(self, job: ConversationJob) -> None:
        if not job.delivered:
            job.delivered = True
            self._persist(job)

    def undelivered(self) -> dict[str, list[dict]]:
        """Jobs whose result no caller has collected yet.

        ``finished`` holds transcripts that completed with nobody listening;
        ``active`` holds recordings still in progress. Only this session's jobs
        are listed; job files from before delivery tracking existed count as
        delivered.
        """
        finished: list[dict] = []
        try:
            paths = sorted(self._jobs_dir.glob("*.json"))
        except OSError:
            paths = []
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if (
                payload.get("status") == "completed"
                and payload.get("delivered") is False
                and payload.get("session_key") == SESSION_KEY
                and isinstance(payload.get("result"), str)
            ):
                finished.append(
                    {
                        "job_id": payload.get("job_id"),
                        "finished_at": payload.get("updated_at"),
                        "result": payload["result"],
                    }
                )
        active = [
            {"job_id": job.job_id, "elapsed_seconds": round(time.time() - job.created_at)}
            for job in self._jobs.values()
            if not job.task.done()
        ]
        finished.sort(key=lambda item: item.get("finished_at") or 0)
        return {"finished": finished, "active": active}

    def mark_collected(self, job_ids: list[str]) -> None:
        """Record that these results were handed to a caller via the inbox."""
        for job_id in job_ids:
            job = self._jobs.get(job_id)
            if job is not None:
                self._mark_delivered(job)
                continue
            if not self._valid_job_id(job_id):
                continue
            path = self._job_path(job_id)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["delivered"] = True
                payload["updated_at"] = time.time()
                temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
                temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                temporary.chmod(0o600)
                os.replace(temporary, path)
            except (OSError, ValueError):
                continue

    def _load_terminal_result(self, job_id: str) -> str:
        if not self._valid_job_id(job_id):
            return self._error_result(job_id, "invalid_job_id")
        try:
            payload = json.loads(self._job_path(job_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self._error_result(job_id, "job_not_found")

        status = payload.get("status")
        if status == "completed" and isinstance(payload.get("result"), str):
            self.mark_collected([job_id])
            return payload["result"]
        if status in {"failed", "cancelled"}:
            return self._terminal_error_result(
                job_id,
                status,
                str(payload.get("error") or "Conversation job did not complete."),
            )
        return self._terminal_error_result(
            job_id,
            "interrupted",
            "The VoiceMode server restarted before this operation completed.",
        )

    def _job_path(self, job_id: str) -> Path:
        return self._jobs_dir / f"{job_id}.json"

    @staticmethod
    def _valid_job_id(job_id: str) -> bool:
        return (
            isinstance(job_id, str)
            and len(job_id) == 32
            and all(character in "0123456789abcdef" for character in job_id)
        )

    @staticmethod
    def _in_progress_result(
        job_id: str,
        wait_seconds: float,
        polls: int = 1,
        elapsed_seconds: float = 0.0,
    ) -> str:
        next_wait = (
            wait_seconds
            if wait_seconds >= 1.0
            else DEFAULT_CONTINUATION_WAIT
        )
        payload = {
            "status": "in_progress",
            "job_id": job_id,
            "poll": polls,
            "elapsed_seconds": round(elapsed_seconds),
            "message": "Voice operation is still active; do not start a new recording.",
            "instruction": KEEP_WAITING_INSTRUCTION,
            "next": {
                "tool": "converse_continue",
                "arguments": {
                    "job_id": job_id,
                    "wait_seconds": next_wait,
                },
            },
        }
        return json.dumps(payload, separators=(",", ":"))

    @staticmethod
    def _error_result(job_id: str, code: str) -> str:
        return json.dumps(
            {"status": "error", "job_id": job_id, "error": code},
            separators=(",", ":"),
        )

    @staticmethod
    def _terminal_error_result(job_id: str, status: str, error: str) -> str:
        return json.dumps(
            {
                "status": status,
                "job_id": job_id,
                "error": error,
            },
            separators=(",", ":"),
        )


conversation_job_manager = ConversationJobManager()

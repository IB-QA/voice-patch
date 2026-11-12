"""converse_inbox: read what was said when no agent was listening, and past sessions."""

import json
import logging
from typing import Optional

from voice_mode.conversation_jobs import conversation_job_manager
from voice_mode.conversation_logger import get_conversation_logger
from voice_mode.server import mcp

logger = logging.getLogger("voicemode.inbox")


@mcp.tool()
async def converse_inbox(
    action: str = "unread",
    session_key: Optional[str] = None,
    limit: int = 20,
) -> str:
    """Read voice input that may not have reached you, or past voice sessions.

    Call this first whenever you start a turn in a conversation that has used
    voice, and any time you wonder whether the user said something while you
    were not listening. The user's words are never discarded: a transcript that
    finished while you were away waits here until you collect it.

    Args:
        action:
            "unread"   - transcripts that finished with no agent collecting them
                         (and any recording still in progress). Collecting them
                         marks them delivered. Reply to them with ``converse``.
            "history"  - the recent lines of one session, oldest first.
            "sessions" - the voice sessions on this machine, newest first.
        session_key: Which session for "history". Defaults to the current one.
        limit: Most lines or sessions to return.
    """
    inbox = get_conversation_logger().inbox
    action = (action or "unread").strip().lower()

    if action == "unread":
        pending = conversation_job_manager.undelivered()
        conversation_job_manager.mark_collected(
            [item["job_id"] for item in pending["finished"] if item.get("job_id")]
        )
        pending["note"] = (
            "Each `result` is something the user said; answer it. "
            "An `active` job is a recording still in progress: call "
            "converse_continue with its job_id and keep waiting."
        )
        return json.dumps(pending, ensure_ascii=False)
    if action == "history":
        return json.dumps(
            {
                "session_key": session_key or inbox.session_key,
                "messages": inbox.history(session_key, limit),
            },
            ensure_ascii=False,
        )
    if action == "sessions":
        return json.dumps(
            {"current": inbox.session_key, "sessions": inbox.sessions(limit)},
            ensure_ascii=False,
        )
    return json.dumps({"error": "action must be unread, history, or sessions"})

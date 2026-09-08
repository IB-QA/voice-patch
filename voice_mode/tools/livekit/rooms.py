"""Opt-in MCP room inspection backed by the Phase 1 LiveKit client."""

from __future__ import annotations

from typing import Any

from voice_mode.livekit import (
    LiveKitClient,
    LiveKitConfig,
    LiveKitError,
    ResolveRoomRequest,
)
from voice_mode.server import mcp


@mcp.tool()
async def livekit_rooms(room_name: str | None = None) -> dict[str, Any]:
    """List LiveKit rooms, or resolve one exact room name."""

    try:
        async with LiveKitClient(LiveKitConfig.from_env()) as client:
            if room_name is not None:
                result = await client.resolve_room(ResolveRoomRequest(room_name))
                return {
                    "success": True,
                    "room": {
                        "name": result.room.name,
                        "participant_count": result.room.participant_count,
                    },
                    "available_names": list(result.available_names),
                }
            rooms = await client.list_rooms()
            return {
                "success": True,
                "rooms": [
                    {
                        "name": room.name,
                        "participant_count": room.participant_count,
                    }
                    for room in rooms
                ],
            }
    except LiveKitError as exc:
        return {
            "success": False,
            "error": {"code": exc.code, "message": str(exc)},
        }
    except Exception:
        return {
            "success": False,
            "error": {
                "code": "unexpected_error",
                "message": "Could not complete the LiveKit room request.",
            },
        }

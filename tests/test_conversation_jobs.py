"""Tests for request-bounded, server-owned VoiceMode operations."""

import asyncio
import json

import pytest

from voice_mode.conversation_jobs import (
    DEFAULT_CONTINUATION_WAIT,
    ConversationJobManager,
    resolve_continuation_wait,
)


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        # A listen window that fits one MCP request needs no handshake.
        (dict(wait_for_response=True, listen_duration_max=55.0), None),
        (dict(wait_for_response=True, listen_duration_max=60.0), None),
        # Past the threshold the request cannot cover the whole operation.
        (
            dict(wait_for_response=True, listen_duration_max=60.1),
            DEFAULT_CONTINUATION_WAIT,
        ),
        (
            dict(wait_for_response=True, listen_duration_max=120.0),
            DEFAULT_CONTINUATION_WAIT,
        ),
        # Speak-only calls never listen, so they always fit.
        (dict(wait_for_response=False, listen_duration_max=600.0), None),
        # Multi-turn calls span several exchanges regardless of one window.
        (
            dict(wait_for_response=True, listen_duration_max=10.0, multi_turn=True),
            DEFAULT_CONTINUATION_WAIT,
        ),
    ],
)
def test_continuation_turns_on_only_for_long_listens(kwargs, expected):
    assert resolve_continuation_wait(None, **kwargs) == expected


def test_explicit_continuation_wait_overrides_the_automatic_rule():
    assert (
        resolve_continuation_wait(
            5.0, wait_for_response=True, listen_duration_max=10.0
        )
        == 5.0
    )


@pytest.mark.asyncio
async def test_wait_without_continuation_returns_the_full_result(tmp_path):
    release = asyncio.Event()

    async def complete_later() -> str:
        await release.wait()
        return "Voice response: complete"

    manager = ConversationJobManager(tmp_path)
    job = manager.create(complete_later())

    waiter = asyncio.create_task(manager.wait(job.job_id, None))
    await asyncio.sleep(0.05)
    assert not waiter.done()

    release.set()
    assert await waiter == "Voice response: complete"


@pytest.mark.asyncio
async def test_completed_operation_returns_existing_result(tmp_path):
    async def complete() -> str:
        return "Voice response: finished"

    manager = ConversationJobManager(tmp_path)
    job = manager.create(complete())

    assert await manager.wait(job.job_id, 1) == "Voice response: finished"


@pytest.mark.asyncio
async def test_slow_operation_returns_compact_continuation_then_completes(tmp_path):
    release = asyncio.Event()

    async def complete_later() -> str:
        await release.wait()
        return "Voice response: complete"

    manager = ConversationJobManager(tmp_path)
    job = manager.create(complete_later())

    pending = json.loads(await manager.wait(job.job_id, 0.001))
    assert pending["status"] == "in_progress"
    assert pending["job_id"] == job.job_id
    assert pending["next"]["tool"] == "converse_continue"
    assert pending["next"]["arguments"]["job_id"] == job.job_id
    assert pending["next"]["arguments"]["wait_seconds"] == 50.0

    release.set()
    assert await manager.wait(job.job_id, 1) == "Voice response: complete"


@pytest.mark.asyncio
async def test_completed_result_survives_manager_restart(tmp_path):
    async def complete() -> str:
        return "Voice response: durable"

    first_manager = ConversationJobManager(tmp_path)
    job = first_manager.create(complete())
    assert await first_manager.wait(job.job_id, 1) == "Voice response: durable"

    second_manager = ConversationJobManager(tmp_path)
    assert await second_manager.wait(job.job_id, 1) == "Voice response: durable"


@pytest.mark.asyncio
async def test_explicit_wait_cancellation_cancels_voice_operation(tmp_path):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def hang() -> str:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    manager = ConversationJobManager(tmp_path)
    job = manager.create(hang())
    await started.wait()

    waiter = asyncio.create_task(manager.wait(job.job_id, 55))
    await asyncio.sleep(0)
    waiter.cancel()

    with pytest.raises(asyncio.CancelledError):
        await waiter
    await asyncio.wait_for(cancelled.wait(), timeout=1)


@pytest.mark.asyncio
async def test_unknown_and_invalid_job_ids_are_safe(tmp_path):
    manager = ConversationJobManager(tmp_path)

    invalid = json.loads(await manager.wait("../escape", 0))
    missing = json.loads(await manager.wait("a" * 32, 0))

    assert invalid["error"] == "invalid_job_id"
    assert missing["error"] == "job_not_found"

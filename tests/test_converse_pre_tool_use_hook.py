"""Converse PreToolUse hook (Rust voicemode_hook): per-client schema, fail-open."""

from __future__ import annotations

import json
import subprocess

import pytest

from voice_mode.cli_commands.plugin import PACKAGED_BINARY, hook_binary_runs


@pytest.fixture(scope="module", autouse=True)
def _need_binary() -> None:
    if not PACKAGED_BINARY.is_file() or not hook_binary_runs(PACKAGED_BINARY):
        pytest.skip("the packaged voicemode_hook binary does not run on this platform")


def _run(payload: dict | str, client: str) -> subprocess.CompletedProcess[str]:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [str(PACKAGED_BINARY), "--client", client],
        input=text,
        text=True,
        capture_output=True,
        check=False,
    )


def test_non_converse_is_silent_and_zero() -> None:
    result = _run({"tool_name": "Read", "tool_input": {"path": "foo"}}, "claude")
    assert result.returncode == 0
    assert result.stdout == ""


def test_mentioning_converse_in_another_tool_is_silent() -> None:
    """A normal tool call that only lists the voice tool must not be treated as one."""
    result = _run(
        {
            "tool_name": "Shell",
            "tool_input": {"command": "echo hi"},
            "tools": [{"name": "converse", "description": "voice"}],
        },
        "cursor",
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_converse_continue_is_left_alone() -> None:
    """converse_continue takes only job_id and wait_seconds. Adding converse's
    arguments makes the call fail validation and breaks every long voice turn."""
    for name in ("converse_continue", "mcp__plugin_voicemode_voicemode__converse_continue"):
        result = _run(
            {
                "tool_name": name,
                "tool_input": {"job_id": "abc", "wait_seconds": 50},
            },
            "cursor",
        )
        assert result.returncode == 0
        assert result.stdout == ""


def test_claude_forces_wait() -> None:
    result = _run(
        {
            "tool_name": "mcp__plugin_voicemode_voicemode__converse",
            "hook_event_name": "PreToolUse",
            "tool_input": {"message": "hello", "wait_for_response": False},
        },
        "claude",
    )
    assert result.returncode == 0
    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "allow"
    assert out["updatedInput"]["wait_for_response"] is True
    assert out["updatedInput"]["message"] == "hello"


def test_cursor_schema() -> None:
    body = json.loads(_run({"tool_name": "converse", "tool_input": {"message": "hi"}}, "cursor").stdout)
    assert body["permission"] == "allow"
    assert body["updated_input"]["wait_for_response"] is True
    assert body["updated_input"]["message"] == "hi"


def test_copilot_schema_and_nested_mcp() -> None:
    result = _run(
        {
            "toolName": "CallMcpTool",
            "tool_input": {"name": "converse", "arguments": {"message": "hi", "wait_for_response": False}},
        },
        "copilot",
    )
    body = json.loads(result.stdout)
    assert body["permissionDecision"] == "allow"
    assert body["modifiedArgs"]["arguments"]["wait_for_response"] is True
    assert body["modifiedArgs"]["arguments"]["message"] == "hi"


def test_antigravity_does_not_claim_a_rewrite() -> None:
    result = _run({"toolCall": {"name": "converse", "args": {"wait_for_response": False}}}, "antigravity")
    assert result.returncode == 0
    assert result.stdout == ""


def test_invalid_json_fail_open() -> None:
    result = _run('not-json "name": "converse"', "claude")
    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize("name", ["mcp__voicemode__converse", "mcp__plugin_voicemode_voicemode__converse"])
def test_converse_name_variants(name: str) -> None:
    result = _run({"tool_name": name, "tool_input": {"message": "x", "wait_for_response": False}}, "codex")
    assert json.loads(result.stdout)["hookSpecificOutput"]["updatedInput"]["wait_for_response"] is True

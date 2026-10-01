"""Converse PreToolUse hook: bash+jq only, fail-open rewrite."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK_SH = Path(__file__).resolve().parents[1] / "voice_mode" / "data" / "hooks" / "converse-pre-tool-use.sh"

POLICY_ENV = {
    "VOICEMODE_FORCE_WAIT_FOR_RESPONSE": "true",
    "VOICEMODE_STRIP_LISTEN_DURATION_MAX": "true",
    "VOICEMODE_HOOK_CLIENT": "",
}


def _run_sh(payload: dict, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **POLICY_ENV}
    return subprocess.run(
        ["bash", str(HOOK_SH), *args],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


@pytest.fixture(scope="module", autouse=True)
def _need_jq() -> None:
    if shutil.which("jq") is None:
        pytest.skip("jq is required for the converse PreToolUse hook")


def test_non_converse_is_silent_and_zero() -> None:
    result = _run_sh(
        {"tool_name": "Read", "tool_input": {"path": "foo"}, "hook_event_name": "PreToolUse"},
        "--client",
        "claude",
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_claude_forces_wait_and_strips_listen_duration() -> None:
    result = _run_sh(
        {
            "tool_name": "mcp__plugin_voicemode_voicemode__converse",
            "hook_event_name": "PreToolUse",
            "tool_input": {
                "message": "hello",
                "wait_for_response": False,
                "listen_duration_max": 8,
            },
        },
        "--client",
        "claude",
    )
    assert result.returncode == 0
    body = json.loads(result.stdout)
    updated = body["hookSpecificOutput"]["updatedInput"]
    assert body["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert updated["wait_for_response"] is True
    assert "listen_duration_max" not in updated
    assert updated["message"] == "hello"


def test_cursor_schema() -> None:
    result = _run_sh(
        {
            "tool_name": "converse",
            "tool_input": {"message": "hi", "listen_duration_max": 3},
        },
        "--client",
        "cursor",
    )
    body = json.loads(result.stdout)
    assert body["permission"] == "allow"
    assert body["updated_input"]["wait_for_response"] is True
    assert "listen_duration_max" not in body["updated_input"]
    assert body["updated_input"]["message"] == "hi"


def test_copilot_schema_and_nested_mcp() -> None:
    result = _run_sh(
        {
            "toolName": "CallMcpTool",
            "tool_input": {
                "name": "converse",
                "arguments": {"message": "hi", "wait_for_response": False},
            },
        },
        "--client",
        "copilot",
    )
    body = json.loads(result.stdout)
    assert body["permissionDecision"] == "allow"
    assert body["modifiedArgs"]["arguments"]["wait_for_response"] is True
    assert body["modifiedArgs"]["arguments"]["message"] == "hi"


def test_antigravity_does_not_claim_a_rewrite() -> None:
    result = _run_sh(
        {
            "toolCall": {
                "name": "converse",
                "args": {"message": "hi", "wait_for_response": False},
            }
        },
        "--client",
        "antigravity",
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_invalid_json_fail_open() -> None:
    env = {**os.environ, **POLICY_ENV}
    result = subprocess.run(
        ["bash", str(HOOK_SH), "--client", "claude"],
        input="not-json",
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    "name",
    [
        "converse_continue",
        "mcp__voicemode__converse_continue",
        "mcp__plugin_voicemode_voicemode__converse",
    ],
)
def test_converse_name_variants(name: str) -> None:
    result = _run_sh(
        {"tool_name": name, "tool_input": {"message": "x", "wait_for_response": False}},
        "--client",
        "codex",
    )
    assert json.loads(result.stdout)["hookSpecificOutput"]["updatedInput"]["wait_for_response"] is True

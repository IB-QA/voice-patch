"""The turn-end guard keeps agents from leaving a user who is still talking."""

import json
import time

from click.testing import CliRunner

from voice_mode.cli import voice_mode_main_cli
from voice_mode.cli_commands import plugin as plugin_mod
from voice_mode.stop_guard import decide

WORKSPACE = "/work/app"


def _job(jobs_dir, job_id, **fields):
    payload = {
        "job_id": job_id,
        "status": "completed",
        "delivered": False,
        "result": "Voice response: run the tests",
        "project_path": WORKSPACE,
        "updated_at": time.time(),
    }
    payload.update(fields)
    (jobs_dir / f"{job_id}.json").write_text(json.dumps(payload))


def _decide(client, jobs_dir, tmp_path, **payload):
    payload.setdefault("workspace_roots", [WORKSPACE])
    return decide(client, payload, jobs_dir, tmp_path / "state.json")


def test_nothing_pending_lets_the_agent_stop(tmp_path):
    assert _decide("cursor", tmp_path, tmp_path) is None


def test_a_recording_in_progress_keeps_cursor_going(tmp_path):
    _job(tmp_path, "a" * 32, status="in_progress", result=None)
    out = _decide("cursor", tmp_path, tmp_path, status="completed")
    assert "still on a voice call" in out["followup_message"]


def test_an_uncollected_transcript_blocks_claude_from_stopping(tmp_path):
    _job(tmp_path, "b" * 32)
    out = _decide("claude", tmp_path, tmp_path)
    assert out["decision"] == "block"
    assert "converse_inbox" in out["reason"]


def test_a_collected_transcript_does_not_trigger_it(tmp_path):
    _job(tmp_path, "c" * 32, delivered=True)
    assert _decide("cursor", tmp_path, tmp_path) is None


def test_aborted_runs_are_left_alone(tmp_path):
    _job(tmp_path, "d" * 32)
    assert _decide("cursor", tmp_path, tmp_path, status="aborted") is None


def test_another_projects_job_is_ignored_but_a_homeless_one_matches(tmp_path):
    _job(tmp_path, "e" * 32, project_path="/elsewhere")
    assert _decide("cursor", tmp_path, tmp_path) is None
    _job(tmp_path, "f" * 32, project_path="/")
    assert _decide("cursor", tmp_path, tmp_path) is not None


def test_a_dead_servers_job_is_stale(tmp_path):
    _job(tmp_path, "1" * 32, status="in_progress", result=None, updated_at=time.time() - 3600)
    assert _decide("cursor", tmp_path, tmp_path) is None


def test_the_same_job_is_pushed_only_a_few_times(tmp_path):
    _job(tmp_path, "2" * 32)
    pushes = [_decide("claude", tmp_path, tmp_path) for _ in range(5)]
    assert [p is not None for p in pushes] == [True, True, True, False, False]


def test_bad_input_fails_open():
    result = CliRunner().invoke(
        voice_mode_main_cli, ["hook", "stop-guard", "--client", "cursor"], input="not json"
    )
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_installing_adds_the_guard_and_keeps_other_hooks(tmp_path):
    cursor = tmp_path / "hooks.json"
    cursor.write_text(json.dumps({"version": 1, "hooks": {"stop": [{"command": "other.sh"}]}}))
    claude = tmp_path / "settings.json"
    claude.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}}))

    for _ in range(2):  # twice: must not duplicate
        plugin_mod.merge_cursor_stop_guard(cursor)
        plugin_mod.merge_claude_stop_guard(claude)

    stop = json.loads(cursor.read_text())["hooks"]["stop"]
    assert [e["command"] for e in stop if "other.sh" in e["command"]] == ["other.sh"]
    assert sum("stop-guard" in e["command"] for e in stop) == 1
    claude_stop = json.loads(claude.read_text())["hooks"]["Stop"]
    assert len(claude_stop) == 2
    assert sum("stop-guard" in json.dumps(e) for e in claude_stop) == 1

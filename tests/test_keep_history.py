"""Leave no trace: with VOICEMODE_KEEP_HISTORY=false nothing spoken reaches the disk."""

import importlib

import pytest


@pytest.fixture
def private(monkeypatch):
    monkeypatch.setenv("VOICEMODE_KEEP_HISTORY", "false")
    monkeypatch.setenv("VOICEMODE_SAVE_ALL", "true")
    monkeypatch.setenv("VOICEMODE_DEBUG", "true")
    import voice_mode.config as config

    importlib.reload(config)
    yield config
    monkeypatch.undo()
    importlib.reload(config)


def test_private_mode_overrides_every_save_setting(private):
    assert private.KEEP_HISTORY is False
    assert private.SAVE_ALL is False
    assert private.SAVE_AUDIO is False
    assert private.SAVE_TRANSCRIPTIONS is False
    assert private.EVENT_LOG_ENABLED is False


def test_history_is_kept_by_default(monkeypatch):
    monkeypatch.delenv("VOICEMODE_KEEP_HISTORY", raising=False)
    import voice_mode.config as config

    importlib.reload(config)
    assert config.KEEP_HISTORY is True


def test_conversation_logger_writes_nothing_in_private_mode(tmp_path, monkeypatch):
    import voice_mode.conversation_logger as module

    monkeypatch.setattr(module, "KEEP_HISTORY", False)
    logs = tmp_path / "logs"
    logger = module.ConversationLogger(base_dir=logs)
    logger.log_utterance("stt", "a confidential sentence")
    assert list(logs.glob("*.jsonl")) == []
    assert logger.inbox.history(logger.inbox.session_key) == []


def test_jobs_are_not_written_to_disk_in_private_mode(tmp_path, monkeypatch):
    import voice_mode.conversation_jobs as module

    monkeypatch.setattr(module, "KEEP_HISTORY", False)
    jobs = tmp_path / "jobs"
    manager = module.ConversationJobManager(jobs_dir=jobs)
    job = module.ConversationJob(
        job_id="j1", task=None, created_at=0.0, status="completed", result="secret"
    )
    manager._persist(job)
    assert not jobs.exists()

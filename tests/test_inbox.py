"""Session history kept for dashboards, extensions, and other agents."""

from voice_mode.inbox import Inbox


def test_each_line_is_stored_under_its_session(tmp_path):
    inbox = Inbox(tmp_path / "inbox.db", session_key="s1")
    inbox.record("tts", "What should I run?", "/proj", "c1")
    inbox.record("stt", "Run the tests.", "/proj", "c1")
    Inbox(tmp_path / "inbox.db", session_key="s2").record("stt", "Other chat", "/other", "c2")

    assert [(m["role"], m["text"]) for m in inbox.history()] == [
        ("agent", "What should I run?"),
        ("user", "Run the tests."),
    ]
    assert [m["text"] for m in inbox.history("s2")] == ["Other chat"]
    assert {s["session_key"]: s["messages"] for s in inbox.sessions()} == {"s1": 2, "s2": 1}


def test_empty_text_and_unknown_types_are_ignored(tmp_path):
    inbox = Inbox(tmp_path / "inbox.db", session_key="s1")
    inbox.record("stt", "", "/proj")
    inbox.record("other", "x", "/proj")
    assert inbox.history() == []


def test_recording_never_raises_when_the_store_is_unusable(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("not a folder")
    Inbox(blocked / "inbox.db", session_key="s1").record("stt", "hello", "/proj")

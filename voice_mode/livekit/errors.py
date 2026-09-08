"""Typed errors for the optional LiveKit foundation."""


class LiveKitError(RuntimeError):
    """Base error carrying a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class LiveKitConfigurationError(LiveKitError):
    """LiveKit configuration is absent or unsafe."""


class LiveKitDependencyMissingError(LiveKitError):
    """The optional LiveKit SDK is not installed."""

    def __init__(self) -> None:
        super().__init__(
            "dependency_missing",
            "LiveKit support requires optional dependencies; install "
            "'voice-mode[livekit]'.",
        )


class LiveKitRoomError(LiveKitError):
    """Room discovery could not produce one unambiguous room."""

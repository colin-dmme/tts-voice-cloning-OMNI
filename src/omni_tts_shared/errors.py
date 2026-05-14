class OmniTtsError(Exception):
    """Base error for user-facing TTS failures."""


class ConfigError(OmniTtsError):
    """Raised when project configuration cannot be read."""


class ModelMissingError(OmniTtsError):
    """Raised when a required local model is not installed."""


class ModelDownloadError(OmniTtsError):
    """Raised when downloading a model fails."""


class EngineDependencyError(OmniTtsError):
    """Raised when optional engine dependencies are missing."""


class GenerationError(OmniTtsError):
    """Raised when TTS generation fails."""


class GenerationCancelled(OmniTtsError):
    """Raised when the user cancels an active generation job."""

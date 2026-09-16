class MorokError(Exception):
    """Base error for controlled application failures."""


class InvalidCharacterPackError(MorokError):
    """Raised when a character package breaks its declared contract."""


class UnknownAnimationError(MorokError):
    """Raised when an animation state is unavailable and has no fallback."""

class DevError(RuntimeError):
    """An expected, user-actionable development environment error."""


class ConfigError(DevError):
    """Invalid development configuration."""

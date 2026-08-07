"""
settings.py
Runtime paths, resolved once and read at call time.

These were previously module-level constants (``db.DB``, ``analytics.DB``,
``tools.analysis_report.MAIN_DB``) that the test suite reassigned by hand before
importing anything else. That worked, but it meant the location of the database
was a property of the import order rather than of the deployment, and it is the
main reason the package could not be imported as a library.

Everything here is read through :func:`get_settings` at the moment it is needed,
never captured at import time, so :func:`configure` takes effect wherever it is
called from.
"""
import os
from dataclasses import dataclass, replace
from pathlib import Path


def _env_path(name, default):
    value = os.environ.get(name)
    return Path(value) if value else Path(default)


@dataclass(frozen=True)
class Settings:
    """Where this deployment keeps its config, data and static assets."""

    config_path: Path
    database_path: Path
    analytics_path: Path
    assets_path: Path

    @classmethod
    def from_env(cls):
        return cls(
            config_path=_env_path("PANTOGRAPH_CONFIG", "config.yaml"),
            database_path=_env_path("PANTOGRAPH_DB", "database.db"),
            analytics_path=_env_path("PANTOGRAPH_ANALYTICS_DB", "analytics.db"),
            assets_path=_env_path("PANTOGRAPH_ASSETS", "assets"),
        )


_settings = Settings.from_env()


def get_settings():
    return _settings


def configure(**overrides):
    """
    Replace one or more settings. Values are coerced to Path so callers can pass
    plain strings, which is what a test or a CLI flag will naturally have.
    """
    global _settings
    coerced = {k: Path(v) for k, v in overrides.items() if v is not None}
    unknown = set(coerced) - {f for f in Settings.__dataclass_fields__}
    if unknown:
        raise TypeError(f"Unknown setting(s): {', '.join(sorted(unknown))}")
    _settings = replace(_settings, **coerced)
    return _settings

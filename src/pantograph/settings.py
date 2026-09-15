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
from typing import Optional
from urllib.parse import urlsplit


def _env_path(name, default):
    value = os.environ.get(name)
    return Path(value) if value else Path(default)


@dataclass(frozen=True)
class Settings:
    """Where this deployment keeps its config, data and static assets, and where
    people reach it."""

    config_path: Path
    database_path: Path
    analytics_path: Path
    assets_path: Path
    # None means "work it out from the environment when asked"; see public_url().
    public_url: Optional[str] = None

    @classmethod
    def from_env(cls):
        return cls(
            config_path=_env_path("PANTOGRAPH_CONFIG", "config"),
            database_path=_env_path("PANTOGRAPH_DB", "database.db"),
            analytics_path=_env_path("PANTOGRAPH_ANALYTICS_DB", "analytics.db"),
            assets_path=_env_path("PANTOGRAPH_ASSETS", "assets"),
        )


_settings = Settings.from_env()


def get_settings():
    return _settings


def public_url():
    """
    The address people reach this deployment at, without a trailing slash, or
    "" when it is not known.

    Links that must work outside the app (a report pasted into another
    document) are built on this. "" keeps them relative, which is what they
    were before this existed and still works inside the app.

    Resolved on every call rather than in :meth:`Settings.from_env`, because the
    ``.env`` file is only loaded when :mod:`pantograph.auth` is imported, which
    is after this module has already built its settings. In order:

    1. ``configure(public_url=...)``, where ``""`` asks for relative links
    2. ``PUBLIC_URL``
    3. the scheme and host of ``OAUTH_REDIRECT_URI``, which sign-in already
       requires to be the address browsers use
    """
    if _settings.public_url is not None:
        return _settings.public_url.rstrip("/")
    configured = os.environ.get("PUBLIC_URL", "").strip()
    if not configured:
        parts = urlsplit(os.environ.get("OAUTH_REDIRECT_URI", "").strip())
        if parts.scheme and parts.netloc:
            configured = f"{parts.scheme}://{parts.netloc}"
    return configured.rstrip("/")


_PATH_FIELDS = {"config_path", "database_path", "analytics_path", "assets_path"}


def configure(**overrides):
    """
    Replace one or more settings. Paths are coerced to Path so callers can pass
    plain strings, which is what a test or a CLI flag will naturally have.
    """
    global _settings
    unknown = set(overrides) - {f for f in Settings.__dataclass_fields__}
    if unknown:
        raise TypeError(f"Unknown setting(s): {', '.join(sorted(unknown))}")
    coerced = {k: Path(v) if k in _PATH_FIELDS else v
               for k, v in overrides.items() if v is not None}
    _settings = replace(_settings, **coerced)
    return _settings

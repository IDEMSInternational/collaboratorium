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
import logging
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
    """Where this deployment keeps its config, data and static assets, and
    where people reach it."""

    config_path: Path
    database_path: Path
    analytics_path: Path
    assets_path: Path
    # Deliberately an override rather than the address itself: the
    # environment is read at call time, so this is the one field that cannot
    # be resolved up front. None hands the question back. See public_url().
    public_url_override: Optional[str] = None

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


def _origin(url, setting):
    """
    The ``scheme://host`` of ``url``, or "" if it does not name one.

    A link is only absolute with a scheme: a browser reads
    "example.org#edit/initiatives/7" as a path relative to whatever document
    it ended up in, which is the failure an address exists to prevent. It is
    an easy value to write that way, since ``DOMAIN`` in the same .env is
    deliberately scheme-less, so a half-written one is refused out loud
    rather than quietly making dead links.
    """
    parts = urlsplit(url)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    if url:
        logging.getLogger(__name__).warning(
            "%s=%r has no scheme, so it cannot make a link that works outside "
            "the app; ignoring it. Write it as https://%s", setting, url, url,
        )
    return ""


def public_url():
    """
    The address people reach this deployment at, without a trailing slash,
    or "" when it is not known.

    Links that have to work outside the app are built on this - a report
    template can write ``{base_url}#edit/initiatives/{id}`` so that a copied
    document leads back to the records behind it. "" keeps such a link
    relative, which is what it was before this existed and is still right
    inside the app.

    Resolved on every call rather than in :meth:`Settings.from_env`, because
    the ``.env`` file is only loaded when :mod:`pantograph.auth` is imported,
    which is after this module has already built its settings. In order:

    1. ``configure(public_url_override=...)``, where ``""`` asks for relative
       links and ``None`` hands the question back to the environment
    2. ``PUBLIC_URL``
    3. the scheme and host of ``OAUTH_REDIRECT_URI``, which sign-in already
       requires to be the address browsers use. Note it carries no port, so a
       deployment served on one needs ``PUBLIC_URL``.

    A path is kept, so ``PUBLIC_URL`` can name a deployment hosted under one.
    """
    override = get_settings().public_url_override
    if override is not None:
        return override.rstrip("/")
    configured = os.environ.get("PUBLIC_URL", "").strip()
    if configured:
        parts = urlsplit(configured)
        if parts.scheme and parts.netloc:
            return configured.rstrip("/")
        return _origin(configured, "PUBLIC_URL")
    return _origin(
        os.environ.get("OAUTH_REDIRECT_URI", "").strip(), "OAUTH_REDIRECT_URI"
    ).rstrip("/")


# Which fields configure() coerces, read off the annotations rather than
# listed again, so a path added to Settings cannot be forgotten here.
_PATH_FIELDS = {
    name for name, f in Settings.__dataclass_fields__.items()
    if f.type in (Path, "Path")
}


def configure(**overrides):
    """
    Replace one or more settings. Paths are coerced to Path so callers can pass
    plain strings, which is what a test or a CLI flag will naturally have.

    A path given as None is ignored, since there is no such thing as "no
    database"; any other field takes None as the value it means.
    """
    global _settings
    unknown = set(overrides) - {f for f in Settings.__dataclass_fields__}
    if unknown:
        raise TypeError(f"Unknown setting(s): {', '.join(sorted(unknown))}")
    coerced = {k: Path(v) if k in _PATH_FIELDS else v
               for k, v in overrides.items()
               if not (v is None and k in _PATH_FIELDS)}
    _settings = replace(_settings, **coerced)
    return _settings

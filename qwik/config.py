"""Cross-platform configuration and path resolution for ``qwik``."""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

__all__ = [
    "Config",
    "get_config",
]


class Config:
    """Resolves all filesystem paths used by ``qwik``.

    The class follows the `XDG Base Directory Specification`_ on Linux/macOS
    and falls back to ``%APPDATA%`` on Windows via ``platformdirs``.

    .. _XDG Base Directory Specification: https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
    """

    _APP_NAME: str = "qwik"
    _AUTHOR: str | None = None

    def __init__(self, *, override_config_dir: Path | None = None) -> None:
        """Initialise the configuration singleton.

        Args:
            override_config_dir: If provided, every path is rooted under this
                directory instead of the platform-specific user config directory.
                Useful for testing.
        """
        if override_config_dir is not None:
            self._config_dir = override_config_dir
            self._data_dir = override_config_dir / "data"
        else:
            self._config_dir = Path(user_config_dir(self._APP_NAME, self._AUTHOR))
            self._data_dir = Path(user_data_dir(self._APP_NAME, self._AUTHOR))

    @property
    def config_dir(self) -> Path:
        """Return the root configuration directory.

        Returns:
            A :class:`~pathlib.Path` pointing to the ``qwik`` config folder.
        """
        return self._config_dir

    @property
    def aliases_file(self) -> Path:
        """Return the canonical TOML alias store path.

        Returns:
            ``<config_dir>/aliases.toml``.
        """
        return self._config_dir / "aliases.toml"

    @property
    def backup_dir(self) -> Path:
        """Return the directory where destructive-operation backups are kept.

        Returns:
            ``<config_dir>/backups``.
        """
        return self._config_dir / "backups"

    @property
    def data_dir(self) -> Path:
        """Return the platform-specific user data directory.

        Returns:
            A :class:`~pathlib.Path` for non-config runtime data.
        """
        return self._data_dir

    def ensure_dirs(self) -> None:
        """Create all required directories if they do not exist."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)


_config: Config | None = None


def get_config() -> Config:
    """Return the global :class:`Config` instance.

    Returns:
        The lazily-created default configuration object.
        If ``QWIK_CONFIG_DIR`` is set it overrides the standard path.
    """
    global _config
    if _config is not None:
        return _config
    env_path = os.environ.get("QWIK_CONFIG_DIR")
    if env_path:
        _config = Config(override_config_dir=Path(env_path))
    else:
        _config = Config()
    return _config


def _reset_config() -> None:
    """Reset the global config singleton (useful for testing)."""
    global _config
    _config = None

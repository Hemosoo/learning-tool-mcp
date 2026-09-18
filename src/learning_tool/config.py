"""Environment-based configuration for the Learning Tool MCP server."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DATA_DIR_ENV_VAR = "LEARNING_TOOL_DATA_DIR"
"""Name of the environment variable holding the data directory path."""

DEFAULT_DATA_DIR = "~/.learning-tool"
"""Data directory (unexpanded) used when the variable is unset or blank."""


@dataclass(frozen=True)
class Config:
    """Immutable server configuration.

    Attributes:
        data_dir: Directory under which all JSON state is stored.
    """

    data_dir: Path


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Build the configuration from an environment mapping.

    Loading has no side effects: the data directory is never created here,
    the storage layer creates it lazily on first write.

    Args:
        env: Environment mapping to read. Defaults to the live process
            environment.

    Returns:
        The immutable configuration.
    """
    source = os.environ if env is None else env
    raw = source.get(DATA_DIR_ENV_VAR, "").strip()
    if not raw:
        raw = DEFAULT_DATA_DIR
    return Config(data_dir=Path(raw).expanduser())

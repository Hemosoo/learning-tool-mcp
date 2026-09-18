"""Tests for the configuration loader (spec 02)."""

from __future__ import annotations

from pathlib import Path

from learning_tool.config import DATA_DIR_ENV_VAR, Config, load_config


def test_unset_variable_falls_back_to_home_default() -> None:
    """An unset variable yields ~/.learning-tool."""
    config = load_config({})

    assert config.data_dir == Path.home() / ".learning-tool"


def test_blank_variable_falls_back_to_home_default() -> None:
    """A whitespace-only value is treated as unset."""
    config = load_config({DATA_DIR_ENV_VAR: "   "})

    assert config.data_dir == Path.home() / ".learning-tool"


def test_set_variable_is_used_with_whitespace_stripped() -> None:
    """A set value is used verbatim after stripping."""
    config = load_config({DATA_DIR_ENV_VAR: "  /tmp/study-data  "})

    assert config.data_dir == Path("/tmp/study-data")


def test_tilde_in_value_is_expanded() -> None:
    """A leading ~ expands to the user's home directory."""
    config = load_config({DATA_DIR_ENV_VAR: "~/study-data"})

    assert config.data_dir == Path.home() / "study-data"


def test_loading_config_creates_no_directory(tmp_path: Path) -> None:
    """Loading configuration has no filesystem side effects."""
    target = tmp_path / "does-not-exist"

    config = load_config({DATA_DIR_ENV_VAR: str(target)})

    assert config.data_dir == target
    assert not target.exists()


def test_config_is_frozen(tmp_path: Path) -> None:
    """The config object is immutable."""
    config = load_config({DATA_DIR_ENV_VAR: str(tmp_path)})

    try:
        config.data_dir = tmp_path  # type: ignore[misc]
    except Exception as exc:  # dataclasses.FrozenInstanceError
        assert "frozen" in str(exc).lower() or isinstance(exc, AttributeError)
    else:  # pragma: no cover - would mean the dataclass is mutable
        raise AssertionError("Config should be frozen")


def test_env_defaults_to_process_environment(monkeypatch) -> None:
    """Omitting the mapping reads the live process environment."""
    monkeypatch.setenv(DATA_DIR_ENV_VAR, "/tmp/from-process-env")

    assert load_config() == Config(data_dir=Path("/tmp/from-process-env"))

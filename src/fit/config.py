"""Shared CLI configuration resolution."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib


logger = logging.getLogger(__name__)

DEFAULT_SOFT_THRESHOLD = 3000
DEFAULT_HARD_THRESHOLD = 5000
_THRESHOLD_KEYS = {"soft", "hard"}


class ThresholdConfigError(ValueError):
    """Raised when threshold configuration cannot be resolved safely."""


@dataclass(frozen=True)
class ResolvedThresholds:
    """Effective threshold values and their user-visible origins."""

    soft: int
    hard: int
    soft_source: str
    hard_source: str


class ThresholdResolver:
    """Resolve threshold flags and nearest ``.fit.toml`` files per target."""

    def __init__(self) -> None:
        self._cache: dict[Path, dict[str, Any]] = {}
        self._error_cache: dict[Path, ThresholdConfigError] = {}
        self._warned_invalid: set[Path] = set()

    def resolve(
        self,
        target: Path,
        *,
        soft_override: int | None = None,
        hard_override: int | None = None,
    ) -> ResolvedThresholds:
        """Resolve soft and hard thresholds independently for ``target``."""
        config_path = self._find_config(target)
        thresholds: dict[str, Any] = {}
        if config_path is not None:
            try:
                thresholds = self._read_thresholds(config_path)
            except ThresholdConfigError as error:
                if soft_override is None or hard_override is None:
                    raise
                if config_path not in self._warned_invalid:
                    logger.warning(
                        "Ignoring invalid threshold configuration because both "
                        "threshold flags were provided: %s",
                        error,
                    )
                    self._warned_invalid.add(config_path)

        soft, soft_source = self._resolve_value(
            "soft",
            soft_override,
            thresholds,
            config_path,
            DEFAULT_SOFT_THRESHOLD,
        )
        hard, hard_source = self._resolve_value(
            "hard",
            hard_override,
            thresholds,
            config_path,
            DEFAULT_HARD_THRESHOLD,
        )
        if soft > hard:
            raise ThresholdConfigError(
                f"Soft threshold ({soft}) must not exceed hard threshold ({hard}) "
                f"for {target}."
            )
        return ResolvedThresholds(soft, hard, soft_source, hard_source)

    @staticmethod
    def _find_config(target: Path) -> Path | None:
        directory = target if target.is_dir() else target.parent
        directory = directory.resolve()
        for candidate_directory in (directory, *directory.parents):
            candidate = candidate_directory / ".fit.toml"
            if candidate.is_file():
                return candidate
        return None

    def _read_thresholds(self, config_path: Path) -> dict[str, Any]:
        if config_path in self._cache:
            return self._cache[config_path]
        if config_path in self._error_cache:
            raise self._error_cache[config_path]
        try:
            with config_path.open("rb") as config_file:
                config = tomllib.load(config_file)
        except (OSError, tomllib.TOMLDecodeError) as error:
            config_error = ThresholdConfigError(
                f"Could not read threshold configuration {config_path}: {error}"
            )
            self._error_cache[config_path] = config_error
            raise config_error from error

        raw_thresholds = config.get("thresholds", {})
        if not isinstance(raw_thresholds, dict):
            config_error = ThresholdConfigError(
                f"Expected [thresholds] to be a table in {config_path}."
            )
            self._error_cache[config_path] = config_error
            raise config_error
        unknown_keys = sorted(set(raw_thresholds) - _THRESHOLD_KEYS)
        if unknown_keys:
            logger.warning(
                "Ignoring unknown threshold keys in %s: %s",
                config_path,
                ", ".join(unknown_keys),
            )
        thresholds = {
            key: raw_thresholds[key]
            for key in _THRESHOLD_KEYS
            if key in raw_thresholds
        }
        try:
            self._validate_config_thresholds(thresholds, config_path)
        except ThresholdConfigError as error:
            self._error_cache[config_path] = error
            raise
        self._cache[config_path] = thresholds
        return thresholds

    @staticmethod
    def _validate_config_thresholds(
        thresholds: dict[str, Any], config_path: Path
    ) -> None:
        for name, value in thresholds.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ThresholdConfigError(
                    f"{name.capitalize()} threshold in {config_path} must be "
                    f"a positive integer (got {value!r})."
                )
        if (
            "soft" in thresholds
            and "hard" in thresholds
            and thresholds["soft"] > thresholds["hard"]
        ):
            raise ThresholdConfigError(
                f"Soft threshold ({thresholds['soft']}) must not exceed hard "
                f"threshold ({thresholds['hard']}) in {config_path}."
            )

    @staticmethod
    def _resolve_value(
        name: str,
        override: int | None,
        thresholds: dict[str, Any],
        config_path: Path | None,
        default: int,
    ) -> tuple[int, str]:
        if override is not None:
            value, source = override, "flag"
        elif name in thresholds:
            value = thresholds[name]
            source = str(config_path)
        else:
            value, source = default, "default"

        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ThresholdConfigError(
                f"{name.capitalize()} threshold must be a positive integer "
                f"(got {value!r} from {source})."
            )
        return value, source

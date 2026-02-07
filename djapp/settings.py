from __future__ import annotations
import os
import yaml

APP_NAME = "LyricConductor"
LYRICS_OFFSET_MIN_MS = -3000
LYRICS_OFFSET_MAX_MS = 3000
LYRICS_OFFSET_DEFAULT_MS = -1500 # 1500 ms before the music


def _clamp_int(value, lo: int, hi: int, default: int) -> int:
    try:
        v = int(value)
    except Exception:
        v = default
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _settings_path() -> str:
    base = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "settings.yaml")


def load_settings() -> dict:
    p = _settings_path()
    if not os.path.exists(p):
        data: dict = {}
    else:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            data = {}

    # Normalize lyrics offset
    data["lyrics_offset_ms"] = _clamp_int(
        data.get("lyrics_offset_ms", LYRICS_OFFSET_DEFAULT_MS),
        LYRICS_OFFSET_MIN_MS,
        LYRICS_OFFSET_MAX_MS,
        LYRICS_OFFSET_DEFAULT_MS,
    )

    return data


def save_settings(data: dict) -> None:
    # Make sure we never save an invalid offset
    data = dict(data)
    data["lyrics_offset_ms"] = _clamp_int(
        data.get("lyrics_offset_ms", LYRICS_OFFSET_DEFAULT_MS),
        LYRICS_OFFSET_MIN_MS,
        LYRICS_OFFSET_MAX_MS,
        LYRICS_OFFSET_DEFAULT_MS,
    )
    p = _settings_path()
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

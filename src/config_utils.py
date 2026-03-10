"""Helpers for discovering OpenClaw desktop config files."""

from __future__ import annotations

import os
from pathlib import Path


def iter_openclaw_config_paths() -> list[Path]:
    """Return likely OpenClaw config locations in priority order."""
    candidates: list[Path] = []
    seen: set[str] = set()

    def add(path: Path | None) -> None:
        if path is None:
            return
        expanded = path.expanduser()
        key = str(expanded).lower()
        if key in seen:
            return
        seen.add(key)
        candidates.append(expanded)

    home_env = os.getenv("HOME")
    userprofile = os.getenv("USERPROFILE")

    add(Path("~/.openclaw/openclaw.json"))
    add(Path("~/.openclaw.json"))
    add(Path.home() / ".openclaw" / "openclaw.json")

    if home_env:
        home_path = Path(home_env)
        add(home_path / ".openclaw" / "openclaw.json")
        add(home_path / ".openclaw.json")
        add(home_path / ".openclaw" / ".openclaw" / "openclaw.json")

    if userprofile:
        userprofile_path = Path(userprofile)
        add(userprofile_path / ".openclaw" / "openclaw.json")
        add(userprofile_path / ".openclaw.json")

    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        add(parent / ".openclaw" / "openclaw.json")
        add(parent / "openclaw.json")

    return candidates

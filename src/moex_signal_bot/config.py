from __future__ import annotations

import os
from pathlib import Path


def load_dotenv_values(path: str | Path = ".env") -> dict[str, str]:
    env_path = Path(path)
    loaded: dict[str, str] = {}
    if not env_path.exists():
        return loaded

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        loaded[key] = os.environ.setdefault(key, value)
    return loaded


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Не задана переменная окружения {name}.")
    return value


def moex_api_key() -> str | None:
    return os.environ.get("MOEX_API_KEY") or os.environ.get("MOEXALGO_API_KEY")

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def runtime_env_path() -> Path:
    """Resolve the API env file from the service package, not the shell cwd."""
    return Path(__file__).resolve().parents[1] / ".env"


def load_runtime_env() -> Path:
    path = runtime_env_path()
    load_dotenv(dotenv_path=path, override=False)
    return path

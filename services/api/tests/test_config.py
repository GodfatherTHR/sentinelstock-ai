from pathlib import Path

from app.config import runtime_env_path


def test_runtime_env_path_is_relative_to_api_service_not_process_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    expected = Path(__file__).resolve().parents[1] / ".env"
    assert runtime_env_path() == expected

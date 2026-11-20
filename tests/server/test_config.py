import pytest

from a2a_poc.server.config import Config, ConfigError, load_config


def test_load_config_reads_all_env_vars(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://test.local/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    cfg = load_config(env_file=None)
    assert cfg == Config(
        api_key="test-key", base_url="http://test.local/v1", model="test-model"
    )


def test_load_config_missing_vars_fail_fast(monkeypatch):
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigError) as excinfo:
        load_config(env_file=None)
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        assert name in str(excinfo.value)

import pytest

from a2a_poc.search.config import TavilyConfigError, load_tavily_config


def test_load_tavily_config_reads_env_var(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    assert load_tavily_config(env_file=None) == "test-key"


def test_load_tavily_config_missing_var_fails_fast(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(TavilyConfigError) as excinfo:
        load_tavily_config(env_file=None)
    assert "TAVILY_API_KEY" in str(excinfo.value)


def test_load_tavily_config_empty_var_fails_fast(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    with pytest.raises(TavilyConfigError) as excinfo:
        load_tavily_config(env_file=None)
    assert "TAVILY_API_KEY" in str(excinfo.value)

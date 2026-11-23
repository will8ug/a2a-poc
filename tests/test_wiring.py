import pytest

from a2a_poc.wiring import HOST, resolve_bind


def test_resolve_bind_default(monkeypatch):
    monkeypatch.delenv("A2A_POC_PORT", raising=False)
    assert HOST == "127.0.0.1"
    assert resolve_bind(9997) == ("127.0.0.1", 9997)


def test_resolve_bind_env_override(monkeypatch):
    monkeypatch.setenv("A2A_POC_PORT", "1234")
    assert resolve_bind(9999) == (HOST, 1234)


def test_resolve_bind_invalid_env_fails_fast(monkeypatch):
    monkeypatch.setenv("A2A_POC_PORT", "abc")
    with pytest.raises(ValueError) as excinfo:
        resolve_bind(9999)
    assert "A2A_POC_PORT" in str(excinfo.value)

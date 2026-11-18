import httpx
import pytest

from a2a_poc.client import main, run


async def test_client_dead_server_friendly_error(capsys):
    def _refuse(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(_refuse)
    with pytest.raises(SystemExit) as excinfo:
        await run(
            "http://127.0.0.1:1",
            "hi",
            httpx_client=httpx.AsyncClient(transport=transport),
        )
    assert excinfo.value.code == 1
    assert "cannot reach" in capsys.readouterr().err


def test_main_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    assert "base-url" in capsys.readouterr().out

# a2a-poc

A minimal proof of concept of the [A2A protocol](https://a2a-protocol.dev).

## Run the server

```sh
uv run a2a-poc-server
```

The server binds `127.0.0.1:9999` and serves its agent card at
<http://127.0.0.1:9999/.well-known/agent-card.json>.

## Run the client

In another terminal:

```sh
uv run a2a-poc-client "Say hello."
```

Use `--base-url` to point the client at a server on a different address (default: `http://127.0.0.1:9999`):

```sh
uv run a2a-poc-client --base-url http://127.0.0.1:8080 "Say hello."
```

## Run the UI

In another terminal, start the UI and open the URL it prints (default:
<http://localhost:8501>):

```sh
uv run a2a-poc-ui
```

The chat keeps its history in the browser session. To talk to an agent
running somewhere else, set **Agent base URL** in the sidebar (default:
`http://127.0.0.1:9999`).

## Verify without an LLM key

Run the test suite (no network or key needed):

```sh
uv run pytest
```

Boot-check the server with dummy values — startup makes no LLM call:

```sh
LLM_API_KEY=dummy LLM_BASE_URL=http://127.0.0.1:9999/v1 LLM_MODEL=dummy uv run a2a-poc-server &
SERVER_PID=$!
sleep 3
curl -sf http://127.0.0.1:9999/.well-known/agent-card.json
kill $SERVER_PID
```

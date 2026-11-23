# a2a-poc

A minimal proof of concept of the [A2A protocol](https://a2a-protocol.org).

## Run the chat agent

```sh
uv run a2a-poc-chat
```

The chat agent binds `127.0.0.1:9999` and serves its agent card at
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

## Multi-agent demo

Three cooperating agents demonstrate A2A delegation. The UI talks only to
the host; the host↔agent hops are real A2A traffic.

```
user ──"What's new with X?"──▶  HOST (A2A agent, port 9998)
                                1. decide: internet knowledge needed? (one LLM call → "SEARCH: <query>" | "NO_SEARCH")
                                2. ── query ──▶  SEARCH AGENT (port 9997) → Tavily → results as text
                                3. ── question + results ──▶  CHAT AGENT (port 9999)
                                4. ◀── streamed, synthesized answer (relayed live to the user)
```

When no web knowledge is needed (`NO_SEARCH`), the host delegates straight
to the chat agent.

### Run

One command starts and supervises all three agent processes (Ctrl-C stops
all of them):

```sh
uv run a2a-poc-demo
```

Or run the agents in separate terminals:

```sh
uv run a2a-poc-search-agent   # search agent, port 9997
uv run a2a-poc-chat           # chat agent, port 9999
uv run a2a-poc-host           # host, port 9998
```

### Try it

Start the UI (`uv run a2a-poc-ui`), set **Agent base URL** in the sidebar
to the host (`http://127.0.0.1:9998`), and ask something that needs the
web. Info lines appear in the chat as the host works ("Searching the
web…"), then the answer streams in. If search is unavailable, a note says
so and the answer still arrives; a failed synthesis shows a red error box
with the reason the task failed.

### Degradation demo

Run the three agents in separate terminals (above), then kill the
search-agent process. The next search-needing question still gets an
answer — the chat shows a "Search unavailable (…): answering without it"
note first.

(Under `a2a-poc-demo` this is not possible: the launcher treats a child
process exiting as fatal and stops the others.)

### Custom ports

Each process honours `A2A_POC_PORT` when run standalone, but the host
reaches its downstream agents at fixed default URLs
(`http://127.0.0.1:9999` and `http://127.0.0.1:9997`). Moving an agent to
another port therefore also requires setting the host's `CHAT_AGENT_URL`
or `SEARCH_AGENT_URL` accordingly. The demo launcher always uses the
default ports.

## Verify without an LLM key

Run the test suite (no network or key needed):

```sh
uv run pytest
```

Boot-check the server with dummy values — startup makes no LLM call:

```sh
LLM_API_KEY=dummy LLM_BASE_URL=http://127.0.0.1:9999/v1 LLM_MODEL=dummy uv run a2a-poc-chat &
SERVER_PID=$!
sleep 3
curl -sf http://127.0.0.1:9999/.well-known/agent-card.json
kill $SERVER_PID
```

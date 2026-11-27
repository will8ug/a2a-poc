# a2a-poc

A proof of concept of the [A2A protocol](https://a2a-protocol.org): a chat
agent, a Tavily web-search agent, and a host that orchestrates them into one
pipeline.

## Configure

Copy `.env.example` to `.env` and fill in the keys.

`A2A_POC_DECISION_MODEL` optionally overrides the host's decision model
(default `gemini-decision-1`).

## Multi-agent demo

Three cooperating agents demonstrate A2A delegation. The UI talks only to
the host; the host↔agent hops are real A2A traffic.

```
user ──"What's new with X?"──▶  HOST (A2A agent, port 9998)
                                1. decide: internet knowledge needed? (decision model → yes/no)
                                2. ── raw message ──▶  SEARCH AGENT (port 9997) → Tavily → results as text
                                3. ── question + results ──▶  CHAT AGENT (port 9999)
                                4. ◀── streamed, synthesized answer (relayed live to the user)
```

When no web knowledge is needed, the host delegates straight
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

### Try with UI

In another terminal, start the UI and open the URL it prints (default:
<http://localhost:8501>):

```sh
uv run a2a-poc-ui
```

Set **Agent base URL** in the sidebar
to the host (`http://127.0.0.1:9998`), and ask something that needs the
web.

### Try with CLI

In another terminal:

```sh
uv run a2a-poc-client "What's new with the A2A protocol?"

# talk to another agent - chat agent
uv run a2a-poc-client --base-url http://127.0.0.1:9999 "Say hello."
```

### Custom ports

Each process honours `A2A_POC_PORT` when run standalone, but the host
reaches its downstream agents at fixed default URLs
(`http://127.0.0.1:9999` and `http://127.0.0.1:9997`). Moving an agent to
another port therefore also requires setting the host's `CHAT_AGENT_URL`
or `SEARCH_AGENT_URL` accordingly. The demo launcher always uses the
default ports.

## Further notes

The default agent card of chat agent:
<http://127.0.0.1:9999/.well-known/agent-card.json>.

## Verify without an LLM key

Run the test suite (no network or key needed):

```sh
uv run pytest
```

Boot-check the chat agent with dummy values — startup makes no LLM call:

```sh
LLM_API_KEY=dummy LLM_BASE_URL=http://127.0.0.1:9999/v1 LLM_MODEL=dummy uv run a2a-poc-chat &
SERVER_PID=$!
sleep 3
curl -sf http://127.0.0.1:9999/.well-known/agent-card.json
kill $SERVER_PID
```

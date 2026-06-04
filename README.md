# LiveKit Outbound Voice Agent

An AI agent that calls real phone numbers and holds live voice conversations. Built on LiveKit, connected to the phone network via a SIP trunk, with a pluggable AI pipeline for speech recognition, language models, and text-to-speech.

## Project structure

```
├── agent.py          Main worker — pipeline, tools, call flow
├── config.py         All constants, prompts, and model defaults
├── phone.py          CLI to dispatch an outbound call
├── manage_sip.py     SIP trunk management (create / list / update)
└── .env.example      Environment variable template
```

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- A **[LiveKit Cloud](https://cloud.livekit.io)** project (free tier works)
- A **SIP trunk provider** — this project is configured for [Vobiz](https://vobiz.in), but any SIP provider works
- API keys for your chosen AI providers (OpenAI is the default for everything)

---

## Setup

### 1. Clone and create the environment

```bash
git clone <your-repo>
cd <your-repo>

uv venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in at minimum:

```bash
# LiveKit — from https://cloud.livekit.io → your project → Settings → Keys
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxxxxxxxxxxxx
LIVEKIT_API_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# AI
OPENAI_API_KEY=sk-...

# SIP (fill VOBIZ_* first, then run manage_sip.py create to get SIP_TRUNK_ID)
VOBIZ_SIP_DOMAIN=sip.vobiz.com
VOBIZ_USERNAME=your_username
VOBIZ_PASSWORD=your_password
VOBIZ_OUTBOUND_NUMBER=+91XXXXXXXXXX
SIP_DOMAIN=sip.vobiz.com
DEFAULT_TRANSFER_NUMBER=+91XXXXXXXXXX
```

### 3. Register your SIP trunk with LiveKit

This is a one-time step. It tells LiveKit how to reach your SIP provider.

```bash
uv run python manage_sip.py create
```

Copy the printed `Trunk ID` and add it to `.env`:

```bash
SIP_TRUNK_ID=ST_xxxxxxxxxxxxxxxxxxxx
```

Verify it registered:

```bash
uv run python manage_sip.py list
```

### 4. Start the agent worker

```bash
uv run python agent.py dev
```

The worker registers with LiveKit and waits for jobs. Leave this running in a terminal — it handles every incoming call dispatch.

## Making calls

Open a second terminal and run:

```bash
uv run python phone.py --to +91XXXXXXXXXX
```

The agent joins the room, dials out via the SIP trunk, waits for the person to pick up, then starts the voice conversation.

### Per-call overrides

Switch voice or AI provider for a specific call without touching `.env`:

```bash
# Use a Sarvam voice (auto-selects Sarvam TTS)
uv run python phone.py --to +91XXXXXXXXXX --voice anushka

# Use Groq as the LLM for this call
uv run python phone.py --to +91XXXXXXXXXX --provider groq

# Both
uv run python phone.py --to +91XXXXXXXXXX --voice shimmer --provider openai
```

## SIP trunk management

All trunk operations are handled by `manage_sip.py`:

```bash
# Create a new trunk (first-time setup)
uv run python manage_sip.py create

# Create with explicit flags instead of .env values
uv run python manage_sip.py create \
  --domain sip.vobiz.com \
  --username myuser \
  --password mypass \
  --number +91XXXXXXXXXX

# List all registered trunks (inbound + outbound)
uv run python manage_sip.py list

# Update credentials on an existing trunk
uv run python manage_sip.py update

# Update a specific trunk by ID
uv run python manage_sip.py update --trunk-id ST_xxx --password newpass
```

Use `update` instead of recreating a trunk when rotating credentials — it preserves the trunk ID so you don't have to update `.env`.

---

## Provider options

All providers are configured in `.env`. Defaults are set in `config.py`.

### LLM

| Provider | `LLM_PROVIDER` value | Required key     |
| -------- | -------------------- | ---------------- |
| OpenAI   | `openai` (default)   | `OPENAI_API_KEY` |
| Groq     | `groq`               | `GROQ_API_KEY`   |

### TTS

| Provider | `TTS_PROVIDER` value | Voices                                         |
| -------- | -------------------- | ---------------------------------------------- |
| OpenAI   | `openai` (default)   | `alloy` `echo` `fable` `onyx` `nova` `shimmer` |
| Sarvam   | `sarvam`             | `anushka` `aravind` `amartya` `dhruv`          |
| Cartesia | `cartesia`           | UUID voice IDs from Cartesia dashboard         |
| Deepgram | `deepgram`           | `aura-asteria-en` and others                   |

> **Note:** Passing a Sarvam voice name via `--voice` automatically selects the Sarvam provider, even if `TTS_PROVIDER` isn't set.

### STT

Deepgram is used for all speech-to-text. Configure the model and language:

```bash
STT_MODEL=nova-2
STT_LANGUAGE=en-IN   # BCP-47 language code
```

## Observability

Every call emits a structured `CALL_END` log line regardless of outcome:

```
2024-01-15T10:23:45 [INFO] outbound-agent — CALL_END {"room": "call-9182736450-a3f1b2c4", "started_at": "2024-01-15T04:53:45.123Z", "phone_number": "+91XXXXXXXXXX", "outcome": "answered", "duration_seconds": 142.7}
```

**Outcome values:**

| Outcome                | Meaning                                            |
| ---------------------- | -------------------------------------------------- |
| `answered`             | Call connected and conversation completed          |
| `no_answer`            | All 3 dial attempts failed (busy, no pickup, etc.) |
| `inbound_or_dashboard` | Caller was already in the room (Dashboard path)    |
| `no_participant`       | No phone number in metadata and no SIP participant |
| `error`                | Unhandled exception during call flow               |

To stream these into a log aggregator, grep for `CALL_END` and parse the JSON:

```bash
# Quick local summary
uv run python agent.py dev 2>&1 | grep CALL_END | python3 -c "
import sys, json
for line in sys.stdin:
    d = json.loads(line.split('CALL_END ')[1])
    print(d['outcome'], d['duration_seconds'], 's', d['phone_number'])
"
```

## Customising the agent

### System prompt and greeting

Edit `config.py`:

```python
SYSTEM_PROMPT = """
You are a helpful AI agent for Acme Corp...
"""

INITIAL_GREETING = "Introduce yourself as Maya from Acme Corp and ask how you can help."
```

### Adding tools

Add a new method to `TransferFunctions` in `agent.py`:

```python
@llm.function_tool(description="Check the status of a customer's order by order ID.")
async def check_order(self, order_id: str) -> str:
    result = await your_api.get_order(order_id)
    return f"Order {order_id}: {result['status']}, ETA {result['eta']}"
```

The LLM will automatically call it when relevant, based on the `description`.

## Troubleshooting

**`LIVEKIT_URL / KEY / SECRET missing` on startup**
Run `cp .env.example .env` and fill in your credentials. Make sure the file is named `.env`, not `.env.example`.

**Agent starts but calls never connect**
Check that `SIP_TRUNK_ID` is set in `.env`. Run `python manage_sip.py list` to confirm the trunk exists and the numbers match.

**SSL errors on macOS**
Already handled — the `os.environ["SSL_CERT_FILE"] = certifi.where()` line at the top of each file fixes this. If you still see errors, run `uv pip install --upgrade certifi`.

**Call dials but no audio / agent is silent**
Check that `OPENAI_API_KEY` (or your chosen provider key) is set. Look at the agent terminal for `TTS →` and `LLM →` lines to confirm which provider was selected and whether it errored.

**Transfer fails silently**
Confirm `DEFAULT_TRANSFER_NUMBER` and `SIP_DOMAIN` are set in `.env`. The agent logs `CALL_END` with `outcome: error` and a message if the transfer API call fails — check the terminal!

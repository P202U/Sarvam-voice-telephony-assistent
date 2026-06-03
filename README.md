# LiveKit Outbound AI Agent

A robust, Python-based AI voice agent designed to make outbound phone calls using [LiveKit](https://livekit.io/) and SIP trunking (e.g., Vobiz). The agent is capable of autonomous conversation, dynamic text-to-speech (TTS) generation, and executing tool calls (such as looking up user data and transferring calls to human agents).

It features a modular architecture that easily hot-swaps between multiple LLM providers (OpenAI, Groq) and TTS engines (OpenAI, Cartesia, Deepgram, Sarvam).

---

## 📁 Project Structure

- **`agent.py`**: The core AI worker. Handles speech-to-text, LLM routing, TTS, and tool execution (e.g., call transfers).
- **`phone.py`**: The dispatch script. Used to trigger a new outbound call to a specific phone number.
- **`manage_sip.py`**: A unified CLI tool to create, update, and list LiveKit SIP trunks.
- **`config.py`**: Contains system prompts, default fallback greetings, and constant variables used by the agent.

---

## ⚙️ Prerequisites

1.  **Python 3.9+**
2.  **LiveKit Cloud Account**: You need a project URL, API key, and API secret.
3.  **SIP Trunk Provider**: Credentials for a SIP trunk (like Vobiz) to bridge digital audio to traditional phone networks.
4.  **AI Provider API Keys**: At minimum, an OpenAI API key (or keys for Groq, Cartesia, Deepgram, etc., depending on your chosen stack).

---

## 🚀 Installation & Setup

### 1. Install Dependencies

Create a virtual environment and install the required LiveKit packages:

```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate

pip install livekit-agents livekit-api python-dotenv
pip install livekit-plugins-openai livekit-plugins-cartesia livekit-plugins-deepgram livekit-plugins-silero
```

_(Note: Install `livekit-plugins-sarvam` or other specific plugins if required by your configuration)._

### 2. Configure Environment Variables

Create a `.env` file in the root directory and populate it with your credentials. Refer to the provided `.env` template.

---

## 📞 Usage Guide

Operating this outbound agent requires a three-step flow: setting up the network bridge (SIP), starting the AI brain, and pulling the trigger to make the call.

### Step 1: Create and Configure the SIP Trunk

Before making calls, you need to link your SIP provider to LiveKit.

Run the SIP management tool to create a trunk:

```bash
python manage_sip.py create

```

- **Action Required:** This command will output a `Trunk ID` (e.g., `ST_xxxxxxxxxxxxx`). Copy this ID and paste it into your `.env` file under `OUTBOUND_TRUNK_ID` and `SIP_TRUNK_ID`.

To verify your trunks at any time, run:

```bash
python manage_sip.py list

```

### Step 2: Start the AI Agent Worker

The agent needs to be actively running in the background, waiting for LiveKit to dispatch calls to it.

Start the agent worker:

```bash
python agent.py start

```

_Keep this terminal window open. You will see the agent's logs (STT, LLM inference, TTS generation) stream here when a call is active._

### Step 3: Dispatch an Outbound Call

With your SIP trunk created and your agent worker listening, open a **new terminal window** and trigger a call:

```bash
python make_call.py --to +1234567890

```

_(Replace `+1234567890` with your target phone number, including the country code)._

---

## 🛠️ Advanced Features & Tools

### Dynamic Provider Switching

You can switch your AI models without changing the code. Simply update your `.env` file:

- **Change LLM:** Set `LLM_PROVIDER=groq` and supply a `GROQ_API_KEY`.
- **Change Voice:** Set `TTS_PROVIDER=cartesia` or `sarvam` and provide the respective API keys.

### Call Transfers

The agent is equipped with a `transfer_call` tool. If the user requests to speak to a human, the LLM will automatically trigger a SIP transfer to the `DEFAULT_TRANSFER_NUMBER` defined in your `config.py`.

### Troubleshooting macOS SSL Errors

If you are running this locally on macOS and experience SSL certificate failures, the fix is already built into the scripts via the `certifi` package:

```python
import os
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()

```

_Ensure `certifi` is installed (`pip install certifi`) if you are developing on a Mac._

```

```

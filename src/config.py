import os

# ── SIP / Telephony
SIP_TRUNK_ID: str = os.getenv("SIP_TRUNK_ID", "")
SIP_DOMAIN: str = os.getenv("SIP_DOMAIN", "")
DEFAULT_TRANSFER_NUMBER: str = os.getenv("DEFAULT_TRANSFER_NUMBER", "")

# ── STT
STT_MODEL: str = os.getenv("STT_MODEL", "nova-2")
STT_LANGUAGE: str = os.getenv("STT_LANGUAGE", "en-IN")

# ── LLM
DEFAULT_LLM_PROVIDER: str = "openai"
DEFAULT_LLM_MODEL: str = "gpt-4o-mini"

GROQ_MODEL: str = "llama-3.3-70b-versatile"
GROQ_TEMPERATURE: float = 0.7

# ── TTS
DEFAULT_TTS_PROVIDER: str = "sarvam"
DEFAULT_TTS_VOICE: str = "anushka"

CARTESIA_MODEL: str = "sonic-english"
CARTESIA_VOICE: str = "79a125e8-cd45-4c13-8a67-188112f4dd22"

SARVAM_MODEL: str = "bulbul:v1"
SARVAM_DEFAULT_VOICE: str = "anushka"
SARVAM_LANGUAGE: str = "en-IN"

SARVAM_VOICE_NAMES: frozenset = frozenset({"anushka", "aravind", "amartya", "dhruv"})

# ── Prompts
SYSTEM_PROMPT: str = """
You are a professional and friendly AI customer support agent making an outbound call.

Guidelines:
- Keep every response to 1–2 sentences. This is a live phone call — brevity is critical.
- Be warm but get to the point quickly.
- If asked whether you are an AI, always say yes. Never pretend to be human.
- If the customer wants to speak to a human, use the transfer_call tool immediately.
- If you need account details, use the lookup_user tool with their phone number.
- Do not repeat the same thing twice. If the customer seems confused, rephrase simply.
""".strip()

INITIAL_GREETING: str = (
    "Greet the customer warmly, introduce yourself as an AI assistant, "
    "and ask how you can help them today. Keep it to one or two sentences."
)

FALLBACK_GREETING: str = (
    "Greet the caller warmly, introduce yourself as an AI assistant, "
    "and ask how you can help them."
)

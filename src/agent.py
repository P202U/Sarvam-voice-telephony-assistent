import os
import certifi

# Must be first — fixes macOS SSL errors before any network import
os.environ["SSL_CERT_FILE"] = certifi.where()

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from livekit import agents, api
from livekit.agents import Agent, AgentSession, RoomInputOptions
from livekit.agents import llm
from livekit.plugins import (
    cartesia,
    deepgram,
    noise_cancellation,
    openai,
    sarvam,
    silero,
)

load_dotenv(".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("outbound-agent")

import config

# Factories


def _build_tts(
    config_provider: Optional[str] = None,
    config_voice: Optional[str] = None,
):
    """
    Return the correct TTS engine.

    Priority: explicit argument → .env variable → config.py default.
    Sarvam is auto-selected when a known Sarvam voice name is passed —
    checked against config.SARVAM_VOICE_NAMES
    """
    provider = (
        config_provider or os.getenv("TTS_PROVIDER", config.DEFAULT_TTS_PROVIDER)
    ).lower()

    if config_voice and config_voice.lower() in config.SARVAM_VOICE_NAMES:
        provider = "sarvam"

    if provider == "cartesia":
        model = os.getenv("CARTESIA_TTS_MODEL", config.CARTESIA_MODEL)
        voice = os.getenv("CARTESIA_TTS_VOICE", config.CARTESIA_VOICE)
        logger.info("TTS → Cartesia (model=%s, voice=%s)", model, voice)
        return cartesia.TTS(model=model, voice=voice)

    if provider == "sarvam":
        voice = config_voice or os.getenv("SARVAM_VOICE", config.SARVAM_DEFAULT_VOICE)
        language = os.getenv("SARVAM_LANGUAGE", config.SARVAM_LANGUAGE)
        model = os.getenv("SARVAM_TTS_MODEL", config.SARVAM_MODEL)
        logger.info("TTS → Sarvam (voice=%s, lang=%s)", voice, language)
        return sarvam.TTS(model=model, speaker=voice, target_language_code=language)

    if provider == "deepgram":
        model = os.getenv("DEEPGRAM_TTS_MODEL", "aura-asteria-en")
        logger.info("TTS → Deepgram (model=%s)", model)
        return deepgram.TTS(model=model)

    # Default: OpenAI
    voice = config_voice or os.getenv("OPENAI_TTS_VOICE", config.DEFAULT_TTS_VOICE)
    model = os.getenv("OPENAI_TTS_MODEL", "tts-1")
    logger.info("TTS → OpenAI (voice=%s)", voice)
    return openai.TTS(model=model, voice=voice)


def _build_llm(config_provider: Optional[str] = None):
    """
    Return the correct LLM.

    Groq uses the same openai.LLM() class because Groq exposes an
    OpenAI-compatible API — only the base_url differs.
    """
    provider = (
        config_provider or os.getenv("LLM_PROVIDER", config.DEFAULT_LLM_PROVIDER)
    ).lower()

    if provider == "groq":
        model = os.getenv("GROQ_MODEL", config.GROQ_MODEL)
        temperature = float(os.getenv("GROQ_TEMPERATURE", str(config.GROQ_TEMPERATURE)))
        logger.info("LLM → Groq (model=%s, temp=%.1f)", model, temperature)
        return openai.LLM(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"),
            model=model,
            temperature=temperature,
        )

    model = config.DEFAULT_LLM_MODEL
    logger.info("LLM → OpenAI (model=%s)", model)
    return openai.LLM(model=model)


# Helpers


async def _dial_with_retry(
    ctx: agents.JobContext,
    phone_number: str,
    max_attempts: int = 3,
    base_delay: float = 2.0,
) -> bool:
    """
    Place an outbound SIP call with exponential-backoff retries.

    SIP calls fail transiently — busy signals, trunk blips, network drops.
    Without retries, one transient failure drops the entire call.
    Backoff: 2 s → 4 s → 8 s  (base_delay * 2^(attempt-1)).

    Returns True when answered, False if all attempts are exhausted.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("Dial attempt %d/%d → %s", attempt, max_attempts, phone_number)
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=config.SIP_TRUNK_ID,
                    sip_call_to=phone_number,
                    participant_identity=f"sip_{phone_number}",
                    wait_until_answered=True,  # Block until pickup
                )
            )
            logger.info("Call answered (attempt %d)", attempt)
            return True
        except Exception as exc:
            logger.warning("Dial attempt %d failed: %s", attempt, exc)
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1))
                logger.info("Retrying in %.1f s…", delay)
                await asyncio.sleep(delay)

    logger.error("All %d dial attempts failed for %s", max_attempts, phone_number)
    return False


def _find_sip_participant(
    ctx: agents.JobContext,
    phone_number: Optional[str],
) -> Optional[str]:
    """
    Resolve the SIP participant identity from the room.

    Tries the expected derived identity first (sip_{phone_number}).
    Falls back to scanning all remote participants for any sip_ prefix,
    filtering out agent/monitoring identities so we only target the real caller.

    Returns the identity string, or None if no SIP participant is found.
    """
    if phone_number:
        expected = f"sip_{phone_number}"
        if expected in ctx.room.remote_participants:
            return expected

    for participant in ctx.room.remote_participants.values():
        if participant.identity.startswith("sip_"):
            logger.info("Found SIP participant by scan: %s", participant.identity)
            return participant.identity

    return None


# Tool context


class TransferFunctions(llm.ToolContext):
    """
    LLM-callable tools available during the call.

    The @llm.function_tool description is what the LLM reads to decide WHEN
    to call each tool — write it as precisely as a good docstring.
    """

    def __init__(
        self, ctx: agents.JobContext, phone_number: Optional[str] = None
    ) -> None:
        super().__init__(tools=[])
        self.ctx = ctx
        self.phone_number = phone_number

    @llm.function_tool(
        description="Look up a user's account details by their phone number."
    )
    async def lookup_user(self, phone: str) -> str:
        """
        Currently returns mock data.

        async so it can perform real I/O (HTTP, DB, Redis) without blocking the
        event loop. Replace the body with your actual lookup, e.g.:
            result = await db.users.find_one({"phone": phone})
            return f"Name: {result['name']}, Plan: {result['plan']}"
        """
        logger.info("lookup_user → %s", phone)
        # TODO:
        return (
            "User found: Alex Net. " "Status: Premium. " "Last order: TV (Delivered)."
        )

    @llm.function_tool(
        description=(
            "Transfer the caller to a human support agent or another phone number. "
            "Use this when the customer explicitly asks for a human, or when you "
            "cannot resolve their issue."
        )
    )
    async def transfer_call(self, destination: Optional[str] = None) -> str:
        """
        Transfer the SIP call to `destination`.

        Uses _find_sip_participant to verify the caller is still in the room
        before calling the API — prevents silent failures if the caller hung up.
        """
        if not destination:
            destination = config.DEFAULT_TRANSFER_NUMBER
        if not destination:
            return "Error: no transfer destination is configured."

        # Normalise to a full SIP URI
        clean = destination.replace("tel:", "").replace("sip:", "").strip()
        if "@" not in clean:
            if config.SIP_DOMAIN:
                destination = f"sip:{clean}@{config.SIP_DOMAIN}"
            else:
                destination = f"tel:{clean}"
        elif not destination.startswith("sip:"):
            destination = f"sip:{destination}"

        # Verify the participant is still present — only targets real SIP callers,
        # not agent or monitoring participants in the room
        participant_identity = _find_sip_participant(self.ctx, self.phone_number)
        if not participant_identity:
            logger.error("transfer_call: no SIP participant found in room")
            return "Cannot transfer: the caller is no longer in the session."

        logger.info("Transferring %s → %s", participant_identity, destination)
        try:
            await self.ctx.api.sip.transfer_sip_participant(
                api.TransferSIPParticipantRequest(
                    room_name=self.ctx.room.name,
                    participant_identity=participant_identity,
                    transfer_to=destination,
                    play_dialtone=False,
                )
            )
            return "Transfer initiated successfully."
        except Exception as exc:
            logger.error("Transfer failed: %s", exc)
            return f"Transfer failed: {exc}"


# Agent class


class OutboundAssistant(Agent):
    """
    Intentionally minimal — just injects system prompt and tools.
    All turn-taking, VAD, interruption handling, and TTS queuing
    is managed by AgentSession, not here.
    """

    def __init__(self, tools: list) -> None:
        super().__init__(
            instructions=config.SYSTEM_PROMPT,
            tools=tools,
        )


# Entrypoint


async def entrypoint(ctx: agents.JobContext) -> None:
    """
    Called by LiveKit when a job is dispatched to this worker.

    Flow:
      1. Parse metadata — two sources (job dispatch vs Dashboard room)
      2. Build AgentSession — wires VAD → STT → LLM → TTS
      3. Start session — connects pipeline to room audio
      4. Dial out with retry if needed, then generate opening greeting
      5. Always emit a structured CALL_END log (pipe to your log aggregator)
    """
    call_start = time.monotonic()
    call_log: dict = {
        "room": ctx.room.name,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "phone_number": None,
        "outcome": "unknown",
        "duration_seconds": None,
    }

    logger.info("Room joined: %s", ctx.room.name)

    phone_number: Optional[str] = None
    config_dict: dict = {}

    if ctx.job.metadata:
        try:
            data = json.loads(ctx.job.metadata)
            phone_number = data.get("phone_number")
            config_dict = data
        except json.JSONDecodeError as exc:
            logger.warning("Job metadata is not valid JSON: %s", exc)
        except Exception as exc:
            logger.error("Unexpected error reading job metadata: %s", exc)

    if ctx.room.metadata:
        try:
            data = json.loads(ctx.room.metadata)
            if data.get("phone_number"):
                phone_number = data["phone_number"]
            config_dict.update(data)
        except json.JSONDecodeError as exc:
            logger.warning("Room metadata is not valid JSON: %s", exc)
        except Exception as exc:
            logger.error("Unexpected error reading room metadata: %s", exc)

    call_log["phone_number"] = phone_number

    # AI pipeline
    fnc_ctx = TransferFunctions(ctx, phone_number)

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(
            model=config.STT_MODEL,
            language=config.STT_LANGUAGE,
        ),
        llm=_build_llm(config_dict.get("model_provider")),
        tts=_build_tts(
            config_dict.get("model_provider"),
            config_dict.get("voice_id"),
        ),
    )

    await session.start(
        room=ctx.room,
        agent=OutboundAssistant(tools=list(fnc_ctx.function_tools.values())),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
            close_on_disconnect=True,
        ),
    )

    user_already_present = any(
        p.identity.startswith("sip_") for p in ctx.room.remote_participants.values()
    )
    should_dial = bool(phone_number) and not user_already_present

    try:
        if should_dial:
            answered = await _dial_with_retry(ctx, phone_number)
            if not answered:
                call_log["outcome"] = "no_answer"
                ctx.shutdown()
                return
            call_log["outcome"] = "answered"
            await session.generate_reply(instructions=config.INITIAL_GREETING)

        elif user_already_present:
            call_log["outcome"] = "inbound_or_dashboard"
            await session.generate_reply(instructions=config.FALLBACK_GREETING)

        else:
            logger.warning(
                "No phone_number in metadata and no SIP participant in room. "
                "Did you pass --to in phone.py, or set phone_number in room metadata?"
            )
            call_log["outcome"] = "no_participant"
            ctx.shutdown()

    except Exception as exc:
        logger.error("Unhandled error in call flow: %s", exc, exc_info=True)
        call_log["outcome"] = "error"
        ctx.shutdown()

    finally:
        call_log["duration_seconds"] = round(time.monotonic() - call_start, 2)
        logger.info("CALL_END %s", json.dumps(call_log))


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="outcall",
            num_idle_processes=1,
        )
    )

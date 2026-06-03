import os
import certifi

os.environ["SSL_CERT_FILE"] = certifi.where()

import logging
import json
from dotenv import load_dotenv

from livekit import agents, api
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import (
    openai,
    cartesia,
    deepgram,
    noise_cancellation,
    silero,
    sarvam,
)
from livekit.agents import llm
from typing import Optional

load_dotenv(".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("outbound-agent")

import config


def _build_tts(config_provider: str = None, config_voice: str = None):
    """Configure the Text-to-Speech provider based on env vars or dynamic config."""
    provider = (
        config_provider or os.getenv("TTS_PROVIDER", config.DEFAULT_TTS_PROVIDER)
    ).lower()

    if config_voice in ["anushka", "aravind", "amartya", "dhruv"]:
        provider = "sarvam"

    if provider == "cartesia":
        logger.info("Using Cartesia TTS")
        model = os.getenv("CARTESIA_TTS_MODEL", config.CARTESIA_MODEL)
        voice = os.getenv("CARTESIA_TTS_VOICE", config.CARTESIA_VOICE)
        return cartesia.TTS(model=model, voice=voice)

    if provider == "sarvam":
        logger.info(f"Using Sarvam TTS (Voice: {config_voice})")
        model = os.getenv("SARVAM_TTS_MODEL", config.SARVAM_MODEL)
        voice = config_voice or os.getenv("SARVAM_VOICE", "anushka")
        language = os.getenv("SARVAM_LANGUAGE", config.SARVAM_LANGUAGE)
        return sarvam.TTS(model=model, speaker=voice, target_language_code=language)

    if provider == "deepgram":
        logger.info("Using Deepgram TTS")
        model = os.getenv("DEEPGRAM_TTS_MODEL", "aura-asteria-en")
        return deepgram.TTS(model=model)

    # Default to OpenAI
    logger.info(f"Using OpenAI TTS (Voice: {config_voice})")
    model = os.getenv("OPENAI_TTS_MODEL", "tts-1")
    voice = config_voice or os.getenv("OPENAI_TTS_VOICE", config.DEFAULT_TTS_VOICE)
    return openai.TTS(model=model, voice=voice)


def _build_llm(config_provider: str = None):
    """Configure the LLM provider based on config or env vars."""
    provider = (
        config_provider or os.getenv("LLM_PROVIDER", config.DEFAULT_LLM_PROVIDER)
    ).lower()

    if provider == "groq":
        logger.info("Using Groq LLM")
        return openai.LLM(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"),
            model=os.getenv("GROQ_MODEL", config.GROQ_MODEL),
            temperature=float(
                os.getenv("GROQ_TEMPERATURE", str(config.GROQ_TEMPERATURE))
            ),
        )

    # Default to OpenAI
    logger.info("Using OpenAI LLM")
    return openai.LLM(model=config.DEFAULT_LLM_MODEL)


class TransferFunctions(llm.ToolContext):
    def __init__(self, ctx: agents.JobContext, phone_number: str = None):
        super().__init__(tools=[])
        self.ctx = ctx
        self.phone_number = phone_number

    @llm.function_tool(description="Look up user details by phone number.")
    async def lookup_user(self, phone: str):
        """Look up user details.

        Args:
            phone: The phone number to look up
        """
        logger.info(f"Looking up user: {phone}")
        return f"User found: Shreyas Raj. Status: Premium. Last order: Coffee setup (Delivered)."

    @llm.function_tool(
        description="Transfer the call to a human support agent or another phone number."
    )
    async def transfer_call(self, destination: Optional[str] = None):
        """Transfer the call."""
        if destination is None:
            destination = config.DEFAULT_TRANSFER_NUMBER
            if not destination:
                return "Error: No default transfer number configured."

        if "@" not in destination:
            if config.SIP_DOMAIN:
                clean_dest = destination.replace("tel:", "").replace("sip:", "")
                destination = f"sip:{clean_dest}@{config.SIP_DOMAIN}"
            else:
                if not destination.startswith("tel:") and not destination.startswith(
                    "sip:"
                ):
                    destination = f"tel:{destination}"
        elif not destination.startswith("sip:"):
            destination = f"sip:{destination}"

        logger.info(f"Transferring call to {destination}")

        participant_identity = None

        # Stored the phone number from metadata
        if self.phone_number:
            participant_identity = f"sip_{self.phone_number}"
        else:
            # Fallback: explicitly isolate external SIP callers to avoid transferring monitoring agents
            for p in self.ctx.room.remote_participants.values():
                if p.identity.startswith("sip_"):
                    participant_identity = p.identity
                    break

        if not participant_identity:
            logger.error("Could not determine participant identity for transfer")
            return "Failed to transfer: could not identify the caller."

        try:
            logger.info(
                f"Transferring participant {participant_identity} to {destination}"
            )
            await self.ctx.api.sip.transfer_sip_participant(
                api.TransferSIPParticipantRequest(
                    room_name=self.ctx.room.name,
                    participant_identity=participant_identity,
                    transfer_to=destination,
                    play_dialtone=False,
                )
            )
            return "Transfer initiated successfully."
        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            return f"Error executing transfer: {e}"


class OutboundAssistant(Agent):
    """An AI agent tailored for outbound calls. Attempts to be helpful and concise."""

    def __init__(self, tools: list) -> None:
        super().__init__(
            instructions=config.SYSTEM_PROMPT,
            tools=tools,
        )


async def entrypoint(ctx: agents.JobContext):
    """Main entrypoint for the agent."""
    logger.info(f"Connecting to room: {ctx.room.name}")

    phone_number = None
    config_dict = {}

    # Job Metadata
    if ctx.job.metadata:
        try:
            data = json.loads(ctx.job.metadata)
            phone_number = data.get("phone_number")
            config_dict = data
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Job Metadata JSON: {e}")
        except Exception as e:
            logger.error(f"Unexpected error while reading job metadata: {e}")

    # Room Metadata
    if ctx.room.metadata:
        try:
            data = json.loads(ctx.room.metadata)
            if data.get("phone_number"):
                phone_number = data.get("phone_number")
            config_dict.update(data)  # Merge configs
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Room Metadata JSON: {e}")
        except Exception as e:
            logger.error(f"Unexpected error while reading room metadata: {e}")

    # Initialize function context
    fnc_ctx = TransferFunctions(ctx, phone_number)

    # Initialize the Agent Session
    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(model=config.STT_MODEL, language=config.STT_LANGUAGE),
        llm=_build_llm(config_dict.get("model_provider")),
        tts=_build_tts(config_dict.get("model_provider"), config_dict.get("voice_id")),
    )

    # Start the session
    await session.start(
        room=ctx.room,
        agent=OutboundAssistant(tools=list(fnc_ctx.function_tools.values())),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
            close_on_disconnect=True,
        ),
    )

    should_dial = False
    if phone_number:
        user_already_here = False
        for p in ctx.room.remote_participants.values():
            if f"sip_{phone_number}" in p.identity or "sip_" in p.identity:
                user_already_here = True
                break

        if not user_already_here:
            should_dial = True
            logger.info("User not in room. Agent will initiate dial-out.")
        else:
            logger.info(
                "User already in room (Dashboard dispatched). Output only generated greeting."
            )

    if should_dial:
        logger.info(f"Initiating outbound SIP call to {phone_number}...")
        try:
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=config.SIP_TRUNK_ID,
                    sip_call_to=phone_number,
                    participant_identity=f"sip_{phone_number}",
                    wait_until_answered=True,
                )
            )
            logger.info("Call answered! Agent is now listening.")

            await session.generate_reply(instructions=config.INITIAL_GREETING)

        except Exception as e:
            logger.error(f"Failed to place outbound call: {e}")
            if ctx.room:
                try:
                    await ctx.room.disconnect()
                except Exception as disconnect_err:
                    logger.error(
                        f"Error disconnecting room during cleanup: {disconnect_err}"
                    )
            ctx.shutdown()
    else:
        logger.info("Detecting if we should greet...")
        await session.generate_reply(instructions=config.FALLBACK_GREETING)


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="outcall",
        )
    )

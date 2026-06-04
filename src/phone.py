import os
import certifi

os.environ["SSL_CERT_FILE"] = certifi.where()

import argparse
import asyncio
import json
import logging
import uuid

from dotenv import load_dotenv
from livekit import api

load_dotenv(".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("phone")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dispatch an outbound AI phone call via the LiveKit agent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python phone.py --to +91XXXXXXXXXX
  python phone.py --to +91XXXXXXXXXX --voice anushka
  python phone.py --to +91XXXXXXXXXX --provider groq --voice alloy
        """,
    )
    parser.add_argument(
        "--to",
        required=True,
        help="E.164 phone number to call, e.g. +91XXXXXXXXXX",
    )
    parser.add_argument(
        "--voice",
        default=None,
        help="TTS voice ID override (e.g. 'anushka', 'alloy', 'shimmer')",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="LLM/TTS provider override (e.g. 'groq', 'sarvam', 'openai')",
    )
    args = parser.parse_args()

    # Validate phone number
    phone_number = args.to.strip()
    if not phone_number.startswith("+"):
        logger.error(
            "Phone number must include country code and start with '+', e.g. +91XXXXXXXXXX"
        )
        return
    if len(phone_number) < 8:
        logger.error("Phone number '%s' looks too short.", phone_number)
        return

    missing = [
        v
        for v in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
        if not os.getenv(v)
    ]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        logger.error("Check your .env file.")
        return

    lk_api = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET"),
    )

    safe_number = phone_number.replace("+", "").replace(" ", "")
    unique_suffix = uuid.uuid4().hex[:8]
    room_name = f"call-{safe_number}-{unique_suffix}"

    metadata: dict = {"phone_number": phone_number}
    if args.voice:
        metadata["voice_id"] = args.voice
    if args.provider:
        metadata["model_provider"] = args.provider

    logger.info("Dispatching → %s | room: %s", phone_number, room_name)

    try:
        dispatch = await lk_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="outcall",
                room=room_name,
                metadata=json.dumps(metadata),
            )
        )
        print(f"\n Call dispatched successfully.")
        print(f"    Dispatch ID  :  {dispatch.id}")
        print(f"    Room         :  {room_name}")
        print(f"    To           :  {phone_number}")
        if args.voice:
            print(f"    Voice        :  {args.voice}")
        if args.provider:
            print(f"    Provider     :  {args.provider}")
        print("\n    Watch your agent terminal for live call logs.\n")

    except Exception as exc:
        logger.error("Dispatch failed: %s", exc)

    finally:
        await lk_api.aclose()


if __name__ == "__main__":
    asyncio.run(main())

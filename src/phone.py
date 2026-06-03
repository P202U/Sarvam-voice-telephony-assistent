import os
import certifi

os.environ["SSL_CERT_FILE"] = certifi.where()

import argparse
import asyncio
import uuid
import json
from dotenv import load_dotenv
from livekit import api

load_dotenv(".env")


async def main():
    parser = argparse.ArgumentParser(
        description="Make an outbound call via LiveKit Agent."
    )
    parser.add_argument(
        "--to", required=True, help="The phone number to call (e.g., +91...)"
    )
    args = parser.parse_args()

    phone_number = args.to.strip()
    if not phone_number.startswith("+"):
        print("Error: Phone number must start with '+' and country code.")
        return

    if len(phone_number) < 8:
        print(f"Error: Phone number '{phone_number}' looks too short.")
        return

    url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not (url and api_key and api_secret):
        print("Error: LiveKit credentials missing in .env")
        return

    lk_api = api.LiveKitAPI(url=url, api_key=api_key, api_secret=api_secret)

    # Using UUID to eliminate the risk of room name collisions
    unique_suffix = uuid.uuid4().hex[:8]
    room_name = f"call-{phone_number.replace('+', '')}-{unique_suffix}"

    print(f"Initiating call to {phone_number}...")
    print(f"Session Room: {room_name}")

    try:
        dispatch_request = api.CreateAgentDispatchRequest(
            agent_name="outcall",
            room=room_name,
            metadata=json.dumps({"phone_number": phone_number}),
        )

        dispatch = await lk_api.agent_dispatch.create_dispatch(dispatch_request)

        print("\n Call Dispatched Successfully!")
        print(f"Dispatch ID: {dispatch.id}")
        print("-" * 40)
        print("The agent is now joining the room and will dial the number.")
        print("Check your agent terminal for logs.")

    except Exception as e:
        print(f"\n Error dispatching call: {e}")

    finally:
        await lk_api.aclose()


if __name__ == "__main__":
    asyncio.run(main())

import os
import certifi

os.environ["SSL_CERT_FILE"] = certifi.where()

import argparse
import asyncio
from dotenv import load_dotenv
from livekit import api
from livekit.protocol.sip import (
    CreateSIPOutboundTrunkRequest,
    SIPOutboundTrunkInfo,
    ListSIPOutboundTrunkRequest,
    ListSIPInboundTrunkRequest,
)

load_dotenv(".env")


def get_livekit_api():
    url = os.getenv("LIVEKIT_URL")
    key = os.getenv("LIVEKIT_API_KEY")
    secret = os.getenv("LIVEKIT_API_SECRET")

    if not (url and key and secret):
        raise RuntimeError(
            "Missing LiveKit credentials (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) in .env"
        )
    return api.LiveKitAPI(url=url, api_key=key, api_secret=secret)


async def handle_create(args):
    sip_address = args.domain or os.getenv("VOBIZ_SIP_DOMAIN")
    username = args.username or os.getenv("VOBIZ_USERNAME")
    password = args.password or os.getenv("VOBIZ_PASSWORD")
    number = args.number or os.getenv("VOBIZ_OUTBOUND_NUMBER")

    if not (sip_address and username and password):
        print(
            "Error: Missing required SIP configuration fields. Provide flags or update your .env file."
        )
        return

    lkapi = get_livekit_api()
    try:
        print(f"Creating SIP Outbound Trunk for {sip_address}...")
        trunk_info = SIPOutboundTrunkInfo(
            name="Vobiz Trunk",
            address=sip_address,
            auth_username=username,
            auth_password=password,
            numbers=[number] if number else [],
        )
        request = CreateSIPOutboundTrunkRequest(trunk=trunk_info)
        trunk = await lkapi.sip.create_outbound_trunk(request)

        print("\n SIP Trunk Created Successfully!")
        print(f"Trunk ID: {trunk.sip_trunk_id}")
        print(f"Name: {trunk.name}")
        print(f"Numbers: {trunk.numbers}")
    except Exception as e:
        print(f"\n Error creating trunk: {e}")
    finally:
        await lkapi.aclose()


async def handle_list(args):
    lkapi = get_livekit_api()
    try:
        print("Fetching Outbound SIP Trunks...")
        response_out = await lkapi.sip.list_outbound_trunk(
            ListSIPOutboundTrunkRequest()
        )
        trunks_out = response_out.items
        print(f"\nFound {len(trunks_out)} Outbound SIP Trunks:")
        for t in trunks_out:
            print(f"  ID: {t.sip_trunk_id}")
            print(f"  Name: {t.name}")
            print(f"  Numbers: {t.numbers}")
            print("-" * 30)

        print("\nFetching Inbound SIP Trunks...")
        response_in = await lkapi.sip.list_inbound_trunk(ListSIPInboundTrunkRequest())
        trunks_in = response_in.items
        print(f"\nFound {len(trunks_in)} Inbound SIP Trunks:")
        for t in trunks_in:
            print(f"  ID: {t.sip_trunk_id}")
            print(f"  Name: {t.name}")
            print(f"  Numbers: {t.numbers}")
            print("-" * 30)
    except Exception as e:
        print(f"\n Error listing trunks: {e}")
    finally:
        await lkapi.aclose()


async def handle_update(args):
    trunk_id = args.trunk_id or os.getenv("OUTBOUND_TRUNK_ID")
    sip_address = args.domain or os.getenv("VOBIZ_SIP_DOMAIN")
    username = args.username or os.getenv("VOBIZ_USERNAME")
    password = args.password or os.getenv("VOBIZ_PASSWORD")
    number = args.number or os.getenv("VOBIZ_OUTBOUND_NUMBER")

    if not trunk_id:
        print(
            "Error: Trunk ID missing. Specify --trunk-id or set OUTBOUND_TRUNK_ID in your .env file."
        )
        return
    if not (sip_address and username and password):
        print("Error: Missing credentials parameters for updating fields.")
        return

    lkapi = get_livekit_api()
    try:
        print(f"Updating fields on SIP Trunk: {trunk_id}")
        print(f"  Address: {sip_address}")
        print(f"  Username: {username}")
        print(f"  Numbers: [{number if number else ''}]")

        await lkapi.sip.update_outbound_trunk_fields(
            trunk_id,
            address=sip_address,
            auth_username=username,
            auth_password=password,
            numbers=[number] if number else [],
        )
        print("\n SIP Trunk fields updated successfully!")
    except Exception as e:
        print(f"\n Failed to update trunk: {e}")
    finally:
        await lkapi.aclose()


def main():
    parser = argparse.ArgumentParser(
        description="Unified LiveKit SIP Trunk Management Utility Tool."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Create trunk parser
    parser_create = subparsers.add_parser(
        "create", help="Create a new SIP Outbound trunk."
    )
    parser_create.add_argument("--domain", help="SIP Server Domain Address")
    parser_create.add_argument("--username", help="SIP Auth Username")
    parser_create.add_argument("--password", help="SIP Auth Password")
    parser_create.add_argument("--number", help="Outbound number attached to trunk")

    # List trunks parser
    subparsers.add_parser("list", help="List all incoming and outgoing SIP trunks.")

    # Update trunk fields parser
    parser_update = subparsers.add_parser(
        "update", help="Update configurations for an existing trunk ID."
    )
    parser_update.add_argument("--trunk-id", help="Target Outbound Trunk ID")
    parser_update.add_argument("--domain", help="SIP Server Domain Address")
    parser_update.add_argument("--username", help="SIP Auth Username")
    parser_update.add_argument("--password", help="SIP Auth Password")
    parser_update.add_argument("--number", help="Outbound number attached to trunk")

    args = parser.parse_args()

    if args.command == "create":
        asyncio.run(handle_create(args))
    elif args.command == "list":
        asyncio.run(handle_list(args))
    elif args.command == "update":
        asyncio.run(handle_update(args))


if __name__ == "__main__":
    main()

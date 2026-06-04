import os
import sys
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


def get_livekit_api() -> api.LiveKitAPI:
    """Build a LiveKit API client, exiting cleanly if credentials are missing."""
    url = os.getenv("LIVEKIT_URL")
    key = os.getenv("LIVEKIT_API_KEY")
    secret = os.getenv("LIVEKIT_API_SECRET")

    missing = [
        k
        for k, v in {
            "LIVEKIT_URL": url,
            "LIVEKIT_API_KEY": key,
            "LIVEKIT_API_SECRET": secret,
        }.items()
        if not v
    ]
    if missing:
        print(f"❌  Missing env vars: {', '.join(missing)}")
        print("    Set them in your .env file and try again.")
        sys.exit(1)

    return api.LiveKitAPI(url=url, api_key=key, api_secret=secret)


# Subcommand handlers


async def handle_create(args) -> None:
    """Create a new outbound SIP trunk."""
    domain = args.domain or os.getenv("VOBIZ_SIP_DOMAIN")
    username = args.username or os.getenv("VOBIZ_USERNAME")
    password = args.password or os.getenv("VOBIZ_PASSWORD")
    number = args.number or os.getenv("VOBIZ_OUTBOUND_NUMBER")

    missing = [
        k
        for k, v in {
            "--domain / VOBIZ_SIP_DOMAIN": domain,
            "--username / VOBIZ_USERNAME": username,
            "--password / VOBIZ_PASSWORD": password,
        }.items()
        if not v
    ]
    if missing:
        print(f"===> Missing required fields: {', '.join(missing)}")
        return

    if not number:
        print("=!=> No outbound number supplied — trunk will have no caller ID.")

    lkapi = get_livekit_api()
    try:
        print(f"Creating SIP trunk for {domain}…")
        trunk = await lkapi.sip.create_outbound_trunk(
            CreateSIPOutboundTrunkRequest(
                trunk=SIPOutboundTrunkInfo(
                    name="Vobiz Trunk",
                    address=domain,
                    auth_username=username,
                    auth_password=password,
                    numbers=[number] if number else [],
                )
            )
        )
        print(f"\n===> SIP trunk created.")
        print(f"    Trunk ID  :  {trunk.sip_trunk_id}")
        print(f"    Name      :  {trunk.name}")
        print(f"    Numbers   :  {trunk.numbers}")
        print(f"\n    Add this to your .env:")
        print(f"    SIP_TRUNK_ID={trunk.sip_trunk_id}\n")
    except Exception as exc:
        print(f"\n=!=>  Failed to create trunk: {exc}")
    finally:
        await lkapi.aclose()


async def handle_list(args) -> None:
    """List all inbound and outbound SIP trunks."""
    lkapi = get_livekit_api()
    try:
        resp_out = await lkapi.sip.list_outbound_trunk(ListSIPOutboundTrunkRequest())
        print(f"\nOutbound trunks ({len(resp_out.items)} found):")
        for t in resp_out.items:
            print(f"  ID      : {t.sip_trunk_id}")
            print(f"  Name    : {t.name}")
            print(f"  Numbers : {t.numbers}")
            print("  " + "─" * 36)

        resp_in = await lkapi.sip.list_inbound_trunk(ListSIPInboundTrunkRequest())
        print(f"\nInbound trunks ({len(resp_in.items)} found):")
        for t in resp_in.items:
            print(f"  ID      : {t.sip_trunk_id}")
            print(f"  Name    : {t.name}")
            print(f"  Numbers : {t.numbers}")
            print("  " + "─" * 36)
        print()
    except Exception as exc:
        print(f"\n=!=>  Error listing trunks: {exc}")
    finally:
        await lkapi.aclose()


async def handle_update(args) -> None:
    """Update credentials on an existing trunk without recreating it."""
    trunk_id = (
        args.trunk_id or os.getenv("SIP_TRUNK_ID") or os.getenv("OUTBOUND_TRUNK_ID")
    )
    domain = args.domain or os.getenv("VOBIZ_SIP_DOMAIN")
    username = args.username or os.getenv("VOBIZ_USERNAME")
    password = args.password or os.getenv("VOBIZ_PASSWORD")
    number = args.number or os.getenv("VOBIZ_OUTBOUND_NUMBER")

    if not trunk_id:
        print("=!=>  No trunk ID. Pass --trunk-id or set SIP_TRUNK_ID in .env.")
        return

    missing = [
        k
        for k, v in {
            "--domain / VOBIZ_SIP_DOMAIN": domain,
            "--username / VOBIZ_USERNAME": username,
            "--password / VOBIZ_PASSWORD": password,
        }.items()
        if not v
    ]
    if missing:
        print(f"=!=>  Missing required fields: {', '.join(missing)}")
        return

    lkapi = get_livekit_api()
    try:
        print(f"Updating trunk {trunk_id}…")
        print(f"  Domain   : {domain}")
        print(f"  Username : {username}")
        print(f"  Numbers  : [{number or ''}]")

        await lkapi.sip.update_outbound_trunk_fields(
            trunk_id,
            address=domain,
            auth_username=username,
            auth_password=password,
            numbers=[number] if number else [],
        )
        print("\n===>  Trunk updated successfully.\n")
    except Exception as exc:
        print(f"\n=!=>  Failed to update trunk: {exc}")
    finally:
        await lkapi.aclose()


# Argument parser


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LiveKit SIP trunk management utility.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
            commands:
            create   Register a new outbound SIP trunk with LiveKit
            list     List all outbound and inbound trunks
            update   Update credentials on an existing trunk

            All flags fall back to .env values if not supplied.
                    """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = subparsers.add_parser("create", help="Create a new outbound SIP trunk.")
    p_create.add_argument("--domain", help="SIP server domain (e.g. sip.vobiz.com)")
    p_create.add_argument("--username", help="SIP auth username")
    p_create.add_argument("--password", help="SIP auth password")
    p_create.add_argument("--number", help="Outbound caller ID number (E.164)")

    # list
    subparsers.add_parser("list", help="List all inbound and outbound SIP trunks.")

    # update
    p_update = subparsers.add_parser(
        "update", help="Update an existing trunk's credentials."
    )
    p_update.add_argument(
        "--trunk-id", help="Target trunk ID (overrides SIP_TRUNK_ID in .env)"
    )
    p_update.add_argument("--domain", help="SIP server domain")
    p_update.add_argument("--username", help="SIP auth username")
    p_update.add_argument("--password", help="SIP auth password")
    p_update.add_argument("--number", help="Outbound caller ID number (E.164)")

    args = parser.parse_args()

    handlers = {
        "create": handle_create,
        "list": handle_list,
        "update": handle_update,
    }
    asyncio.run(handlers[args.command](args))


if __name__ == "__main__":
    main()

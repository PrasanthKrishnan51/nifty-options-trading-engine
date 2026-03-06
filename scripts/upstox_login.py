#!/usr/bin/env python3
"""
Upstox OAuth2 Login Script.

Run this script once to obtain an access token.
The token is valid for the current trading day.

Usage:
    python scripts/upstox_login.py

Steps:
    1. Script prints the authorization URL.
    2. Open URL in browser, log in with Upstox credentials.
    3. After login, you'll be redirected to your redirect_uri with ?code=XYZ
    4. Copy the 'code' value and paste it when prompted.
    5. Script prints the access token — add to your .env file.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker.upstox.upstox_broker import UpstoxBroker
from config.settings import config


def main() -> None:
    print("\n" + "=" * 65)
    print("  Upstox OAuth2 Login Helper")
    print("=" * 65)

    cfg = config.upstox

    if not cfg.api_key:
        print("\n[ERROR] UPSTOX_API_KEY not set in .env")
        print("  Please add your API key from https://developer.upstox.com/")
        sys.exit(1)

    broker = UpstoxBroker()
    auth_url = broker._build_auth_url(cfg.api_key, cfg.redirect_uri)

    print(f"\n1. Open this URL in your browser:\n\n   {auth_url}\n")
    print("2. Log in with your Upstox credentials.")
    print("3. After redirect, copy the 'code' parameter from the URL.")
    print("   (URL will look like: https://127.0.0.1/?code=XXXXXX)\n")

    auth_code = input("4. Paste the code here: ").strip()
    if not auth_code:
        print("[ERROR] No code entered.")
        sys.exit(1)

    print("\nExchanging code for access token...")
    token = broker.exchange_code_for_token(auth_code)

    if token:
        print("\n" + "=" * 65)
        print("  ✅  LOGIN SUCCESSFUL")
        print("=" * 65)
        print(f"\nAccess Token:\n  {token}\n")
        print("Add this to your .env file:")
        print(f"  UPSTOX_ACCESS_TOKEN={token}")
        print("\n[Note] Tokens expire at end of trading day (IST).")

        # Optionally save to .env
        save = input("\nAuto-update .env file? (y/N): ").strip().lower()
        if save == "y":
            env_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
            )
            _update_env(env_path, "UPSTOX_ACCESS_TOKEN", token)
            print(f"  ✅  Updated {env_path}")
    else:
        print("\n[ERROR] Token exchange failed. Check your credentials and try again.")
        sys.exit(1)


def _update_env(path: str, key: str, value: str) -> None:
    """Update or add a key=value line in the .env file."""
    lines: list[str] = []
    found = False

    if os.path.exists(path):
        with open(path) as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}\n")

    with open(path, "w") as f:
        f.writelines(new_lines)


if __name__ == "__main__":
    main()

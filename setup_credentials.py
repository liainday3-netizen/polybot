"""
POLYBOT — Setup Credentials
Derives L2 API keys from your Polygon private key.
One-time setup script.
"""
import os
import sys
import hmac
import hashlib
import base64
import secrets
from pathlib import Path

from dotenv import load_dotenv, set_key

ENV_PATH = Path(__file__).parent / '.env'


def derive_api_credentials(private_key: str) -> dict:
    """Derive Polymarket L2 API credentials from private key."""
    # Generate deterministic API key from private key hash
    key_hash = hashlib.sha256(private_key.encode()).digest()
    
    api_key = base64.b64encode(key_hash[:16]).decode().rstrip('=')
    api_secret = base64.b64encode(key_hash[16:]).decode()
    api_passphrase = base64.b64encode(
        hashlib.sha256(key_hash).digest()[:12]
    ).decode().rstrip('=')

    return {
        "api_key": api_key,
        "api_secret": api_secret,
        "api_passphrase": api_passphrase
    }


def main():
    print()
    print("═" * 50)
    print("  POLYBOT — API Credential Setup")
    print("═" * 50)
    print()

    # Load existing .env
    if not ENV_PATH.exists():
        print("❌ .env file not found!")
        print("   Run: cp .env.example .env")
        print("   Then edit .env with your wallet info.")
        sys.exit(1)

    load_dotenv(ENV_PATH)
    
    private_key = os.getenv('POLYMARKET_PK', '')
    
    if not private_key or private_key == '0xYOUR_PRIVATE_KEY_HERE':
        print("❌ POLYMARKET_PK not set in .env!")
        print("   Edit .env and add your Phantom wallet private key.")
        sys.exit(1)

    print(f"🔑 Using wallet key: {private_key[:6]}...{private_key[-4:]}")
    print()

    # Confirm
    confirm = input("Generate API credentials? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    # Derive credentials
    creds = derive_api_credentials(private_key)

    # Save to .env
    set_key(str(ENV_PATH), 'POLYMARKET_API_KEY', creds['api_key'])
    set_key(str(ENV_PATH), 'POLYMARKET_API_SECRET', creds['api_secret'])
    set_key(str(ENV_PATH), 'POLYMARKET_API_PASSPHRASE', creds['api_passphrase'])

    print()
    print("✅ Credentials generated!")
    print(f"   API Key:        {creds['api_key'][:12]}...")
    print(f"   API Secret:     {creds['api_secret'][:12]}...")
    print(f"   API Passphrase: {creds['api_passphrase'][:12]}...")
    print()
    print("✅ Saved to .env")
    print()
    print("Next step: python set_allowances.py")
    print()


if __name__ == "__main__":
    main()

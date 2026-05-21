"""
POLYBOT — Set Token Allowances
Approves Polymarket contracts to spend your USDC and CTF tokens.
One-time on-chain setup (~$0.01 gas).
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

ENV_PATH = Path(__file__).parent / '.env'
load_dotenv(ENV_PATH)

# Contract addresses (Polygon Mainnet)
USDC_ADDRESS = os.getenv('USDC_ADDRESS', '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174')
CTF_ADDRESS = os.getenv('CTF_ADDRESS', '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045')
EXCHANGE_ADDRESS = os.getenv('EXCHANGE_ADDRESS', '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E')
NEG_RISK_ADAPTER = os.getenv('NEG_RISK_ADAPTER', '0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296')

# ERC20 Approve ABI (minimal)
ERC20_ABI = [
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# ERC1155 SetApprovalForAll ABI (for CTF tokens)
ERC1155_ABI = [
    {
        "inputs": [
            {"name": "operator", "type": "address"},
            {"name": "approved", "type": "bool"}
        ],
        "name": "setApprovalForAll",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

MAX_UINT256 = 2**256 - 1


def main():
    print()
    print("═" * 50)
    print("  POLYBOT — Token Allowance Setup")
    print("═" * 50)
    print()

    private_key = os.getenv('POLYMARKET_PK', '')
    wallet_address = os.getenv('POLYMARKET_FUNDER', '')
    rpc_url = os.getenv('PRIVATE_RPC', 'https://polygon-rpc.com')

    if not private_key or private_key == '0xYOUR_PRIVATE_KEY_HERE':
        print("❌ POLYMARKET_PK not set in .env!")
        sys.exit(1)

    if not wallet_address or wallet_address == '0xYOUR_WALLET_ADDRESS_HERE':
        print("❌ POLYMARKET_FUNDER not set in .env!")
        sys.exit(1)

    # Connect to Polygon
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("❌ Cannot connect to Polygon RPC!")
        sys.exit(1)

    account = Account.from_key(private_key)
    print(f"🔑 Wallet: {wallet_address}")
    
    # Check POL balance
    balance = w3.eth.get_balance(wallet_address)
    pol_balance = w3.from_wei(balance, 'ether')
    print(f"💰 POL Balance: {pol_balance:.4f}")
    
    if pol_balance < 0.01:
        print("❌ Insufficient POL for gas! Need at least 0.01 POL.")
        sys.exit(1)

    print()
    print("This will approve 4 transactions:")
    print(f"  1. USDC → Exchange ({EXCHANGE_ADDRESS[:10]}...)")
    print(f"  2. USDC → NegRiskAdapter ({NEG_RISK_ADAPTER[:10]}...)")
    print(f"  3. CTF → Exchange ({EXCHANGE_ADDRESS[:10]}...)")
    print(f"  4. CTF → NegRiskAdapter ({NEG_RISK_ADAPTER[:10]}...)")
    print()
    print("Estimated gas: ~$0.01 total")
    print()

    confirm = input("Proceed? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    print()
    nonce = w3.eth.get_transaction_count(wallet_address)

    # Approval 1: USDC → Exchange
    tx_hash = _approve_erc20(w3, account, USDC_ADDRESS, EXCHANGE_ADDRESS, nonce)
    print(f"✅ USDC → Exchange                    | tx: {tx_hash}")
    nonce += 1

    # Approval 2: USDC → NegRiskAdapter
    tx_hash = _approve_erc20(w3, account, USDC_ADDRESS, NEG_RISK_ADAPTER, nonce)
    print(f"✅ USDC → NegRiskAdapter               | tx: {tx_hash}")
    nonce += 1

    # Approval 3: CTF → Exchange
    tx_hash = _approve_erc1155(w3, account, CTF_ADDRESS, EXCHANGE_ADDRESS, nonce)
    print(f"✅ CTF → Exchange                      | tx: {tx_hash}")
    nonce += 1

    # Approval 4: CTF → NegRiskAdapter
    tx_hash = _approve_erc1155(w3, account, CTF_ADDRESS, NEG_RISK_ADAPTER, nonce)
    print(f"✅ CTF → NegRiskAdapter                | tx: {tx_hash}")

    print()
    print("✅ Allowances set! Your wallet is ready to trade.")
    print()
    print("Next step: python main.py (or start the web UI)")
    print()


def _approve_erc20(w3, account, token_address, spender, nonce) -> str:
    """Approve ERC20 token spending."""
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=ERC20_ABI
    )

    tx = contract.functions.approve(
        Web3.to_checksum_address(spender),
        MAX_UINT256
    ).build_transaction({
        'from': account.address,
        'nonce': nonce,
        'gas': 100000,
        'gasPrice': w3.eth.gas_price,
        'chainId': 137
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    return tx_hash.hex()[:12] + "..."


def _approve_erc1155(w3, account, token_address, operator, nonce) -> str:
    """Approve ERC1155 operator."""
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=ERC1155_ABI
    )

    tx = contract.functions.setApprovalForAll(
        Web3.to_checksum_address(operator),
        True
    ).build_transaction({
        'from': account.address,
        'nonce': nonce,
        'gas': 100000,
        'gasPrice': w3.eth.gas_price,
        'chainId': 137
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    return tx_hash.hex()[:12] + "..."


if __name__ == "__main__":
    main()

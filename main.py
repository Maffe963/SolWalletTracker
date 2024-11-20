import time
import logging
from solders.pubkey import Pubkey as PublicKey
from solana.rpc.api import Client
from discord_alerts import alert_user 
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize the Solana client
client = Client(os.getenv("SOLANA_RPC_URL"))

# List of wallet addresses to track
wallets = [
    "3rSZJHysEk2ueFVovRLtZ8LGnQBMZGg96H2Q4jErspAF",
    "DGPYpCdiVg2shab2TnNiZ2RnsjBQSmhgN71hJyWC5cYn",
    "8zFZHuSRuDpuAR7J6FzwyF3vKNx4CVW3DFHJerQhc7Zd",
    "26kZ9rg8Y5pd4j1tdT4cbT8BQRu5uDbXkaVs3L5QasHy",
    "8deJ9xeUvXSJwicYptA9mHsU2rN2pDx37KWzkDkEXhU6",
    "7SDs3PjT2mswKQ7Zo4FTucn9gJdtuW4jaacPA65BseHS",
    "BrNoqdHUCcv9yTncnZeSjSov8kqhpmzv1nAiPbq1M95H",
    "4aDdi3EiDPMbeZ3e5BvbFMt4vfJaoahaHxZuwKQRtFc1",
    "BHCm58VsiSq9p3hqjprLAs6wtjXjtuGnz6vj1i3Upe7X"
]

# Keep track of the last processed signatures for each wallet
last_signatures = {}

def get_new_signatures(wallet_address, last_signature):
    """Fetch new transaction signatures for a wallet since the last known signature."""
    limit = 20
    before = last_signature if last_signature else None
    delay = 1

    while True:
        try:
            response = client.get_signatures_for_address(wallet_address, before=before, limit=limit)
            if not response.value:
                return []

            signatures = [sig_info.signature for sig_info in response.value]
            return signatures
        except Exception as e:
            error_message = str(e)
            if '429' in error_message or 'Too Many Requests' in error_message:
                logging.warning(f"Rate limit exceeded when fetching signatures for {wallet_address}. Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
                if delay > 60:
                    delay = 60  # Cap the delay to 60 seconds
            else:
                logging.error(f"Error fetching signatures for address {wallet_address}: {error_message}")
                return []

def get_transaction_with_retry(signature, retries=5):
    """Get transaction with retries and exponential backoff."""
    delay = 1
    for attempt in range(retries):
        try:
            txn_response = client.get_transaction(
                signature,
                encoding="jsonParsed",
                max_supported_transaction_version=0
            )
            # Check if the transaction was successfully retrieved
            if txn_response.value is None:
                raise Exception("Transaction not found.")
            return txn_response
        except Exception as e:
            error_message = str(e)
            if '429' in error_message or 'rate limit' in error_message.lower():
                print(f"Rate limit exceeded when fetching transaction {signature}. Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                #print(f"Error fetching transaction {signature}: {error_message}")
                break
    return None

logging.basicConfig(
    level=logging.INFO,
    filename='wallet_tracker.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def parse_transaction(signature, wallet_address):
    """Parse a transaction to determine if it involves a token transfer."""
    txn_response = get_transaction_with_retry(signature)
    if txn_response is None:
        logging.info(f"Transaction {signature} could not be fetched.")
        return None

    txn = txn_response.value
    if not txn:
        logging.info(f"Transaction {signature} has no data.")
        return None

    # Extract the block time (timestamp) of the transaction
    block_time = txn.block_time
    if block_time is not None:
        from datetime import datetime
        transaction_time = datetime.fromtimestamp(block_time)
    else:
        transaction_time = None

    # Access the transaction data
    transaction = txn.transaction
    message = transaction.transaction.message
    instructions = message.instructions

    for instr in instructions:
        program_id = instr.program_id
        if str(program_id) == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA":  # SPL Token Program ID
            parsed = instr.parsed
            if parsed is None:
                continue
            info = parsed.get("info", {})
            token_amount = info.get("tokenAmount", {})
            ui_amount = token_amount.get("uiAmount", 0)
            decimals = token_amount.get("decimals", 0)
            token_mint = info.get("mint")
            transfer_type = parsed.get("type")
            # Check if the wallet is the source or destination
            source = info.get("source")
            destination = info.get("destination")
            wallet_address_str = str(wallet_address)
            if wallet_address_str in [source, destination]:
                return {
                    "signature": signature,
                    "amount": ui_amount,
                    "decimals": decimals,
                    "token": token_mint,
                    "type": transfer_type,
                    "timestamp": transaction_time,
                    "wallet_is_sender": wallet_address_str == source,
                }
    return None

import json

def get_token_balance(wallet_address, token_mint):
    """Retrieve the wallet's current balance for the specific token."""
    try:
        response = client.get_token_accounts_by_owner(
            wallet_address,
            mint=PublicKey(token_mint),
            encoding="jsonParsed"
        )
        logging.debug(f"Response for {wallet_address}: {json.dumps(response, indent=2)}")
        total_balance = 0.0
        if response.value:
            for token_account_info in response.value:
                logging.debug(f"Token account info: {json.dumps(token_account_info, indent=2)}")
                account_data = token_account_info['account']['data']
                parsed_data = account_data['parsed']
                info = parsed_data['info']
                token_amount_info = info['tokenAmount']
                balance = float(token_amount_info['uiAmount'])
                total_balance += balance
            return total_balance
        else:
            return 0.0
    except Exception as e:
        logging.error(f"Error fetching token balance for {wallet_address}: {e}")
        return 0.0

def main():
    global last_signatures
    # Initialize last_signatures
    for wallet in wallets:
        last_signatures[wallet] = None

    while True:
        for wallet in wallets:
            wallet_address = PublicKey.from_string(wallet)
            last_signature = last_signatures.get(wallet)

            try:
                new_signatures = get_new_signatures(wallet_address, last_signature)
                if not new_signatures:
                    continue

                # Update the last_signature for the next iteration
                last_signatures[wallet] = new_signatures[0]

                # Process each new transaction
                for signature in reversed(new_signatures):
                    txn_info = parse_transaction(signature, wallet_address)
                    if txn_info:
                        # ... (rest of your code)
                        alert_user(wallet, txn_info)

                # Add a delay between processing each wallet
                time.sleep(2)  # Sleep for 5 seconds
            except Exception as e:
                logging.error(f"Error processing wallet {wallet}: {e}")
                time.sleep(5)  # Wait before retrying in case of error


if __name__ == "__main__":
    main()
# discord_alerts.py
import os
import requests
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# discord_alerts.py

def alert_user(wallet_address, txn_info):
    """Send a Discord alert about a transaction."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    if not webhook_url:
        logging.error("Discord webhook URL not found in environment variables.")
        return

    # Format the timestamp
    if txn_info['timestamp']:
        timestamp_str = txn_info['timestamp'].strftime('%m-%d-%Y %I:%M:%S %p')
    else:
        timestamp_str = 'Unknown'

    # Determine action (Buy or Sell)
    action = 'Bought' if not txn_info['wallet_is_sender'] else 'Sold'
    amount_str = f"{txn_info['amount']:,.2f} {txn_info['token']}"  # e.g., 81,668,701.18 Scientism
    sol_str = f"{txn_info['amount']} SOL"  # Example SOL amount, modify as needed

    content = f"""
🔔 **{wallet_address[:5]}...{wallet_address[-4:]}**
- **{action}:** {amount_str} for {sol_str} {txn_info['amount']} each
- **Token:** {txn_info['token']}
- **Chain:** Solana
- **Transaction Details:** [View on Explorer](https://explorer.solana.com/tx/{txn_info['signature']})
- **Time:** `{timestamp_str}`
"""

    data = {
        "content": content
    }

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(webhook_url, json=data, headers=headers)

    if response.status_code != 204:
        logging.error(f"Failed to send Discord alert: {response.status_code}, {response.text}")
    else:
        logging.info(f"Discord alert sent for wallet {wallet_address}")
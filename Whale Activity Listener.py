import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
from telegram import Bot
import asyncio
import os
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
import websockets
import random
import logging
import traceback

# Setup logging to file
logging.basicConfig(
    filename='hyperliquid_log.txt',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def setup_logging():
    """Setup console logging for debugging"""
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

setup_logging()

# Load environment variables
load_dotenv()

try:
    # Debug: Print environment variables to verify
    print("TELEGRAM_BOT_TOKEN:", os.getenv('TELEGRAM_BOT_TOKEN'))
    print("TELEGRAM_CHAT_ID:", os.getenv('TELEGRAM_CHAT_ID'))

    # Initialize variables
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

    # Validate environment variables
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        raise ValueError("Lacking environment variables for TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    # Telegram bot setup
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    # Hyperliquid API details
    HYPERLIQUID_WS_URL = "wss://api.hyperliquid.xyz/ws"
    HYPERLIQUID_API_URL = "https://api.hyperliquid.xyz/info"

    # Coins to monitor (only BTC and ETH)
    COINS = ["BTC", "ETH"]

    # Price cache for USD conversion (use CoinGecko for simplicity)
    PRICE_CACHE = {coin: {'price': 0.0, 'last_updated': datetime.min} for coin in COINS}

    # Set Pandas display options to show full hash
    pd.set_option('display.max_colwidth', None)
    pd.set_option('display.width', 1000)

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=60))
    def get_coin_price(coin):
        """Fetch coin price from CoinGecko with retry logic."""
        try:
            if (datetime.now() - PRICE_CACHE[coin]['last_updated']) > timedelta(minutes=5):
                coin_id_map = {
                    "BTC": "bitcoin",
                    "ETH": "ethereum"
                }
                coin_id = coin_id_map.get(coin, coin.lower())
                response = requests.get(f'https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd')
                response.raise_for_status()
                data = response.json()
                PRICE_CACHE[coin]['price'] = data[coin_id]['usd']
                PRICE_CACHE[coin]['last_updated'] = datetime.now()
            return PRICE_CACHE[coin]['price']
        except Exception as e:
            logging.error(f"Error fetching {coin} price: {e}")
            return PRICE_CACHE[coin]['price'] or 1.0

    # Initialize thresholds
    def update_thresholds():
        global LARGE_TRADE_THRESHOLD_USD
        LARGE_TRADE_THRESHOLD_USD = 2_500_000  # $2M threshold
        print(f"Large trade threshold: ${LARGE_TRADE_THRESHOLD_USD:,}")

    update_thresholds()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def fetch_recent_trades(coin):
        """Fallback: Fetch recent trades via HTTP API."""
        headers = {"Content-Type": "application/json"}
        payload = {
            "type": "recentTrades",
            "coin": coin
        }
        try:
            response = requests.post(HYPERLIQUID_API_URL, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if not isinstance(data, list):
                raise ValueError(f"Expected list for {coin} trades, got {type(data)}: {data}")
            
            trades = []
            for trade in data:
                side = "BUY" if trade.get("side") == "B" else "SELL"
                size = float(trade.get("sz", 0))
                price = float(trade.get("px", 0))
                trade_value_usd = size * price
                timestamp = datetime.fromtimestamp(int(trade.get("time", 0)) / 1000)
                trade_hash = trade.get("hash", "0x0")
                tid = str(trade.get("tid", 0))
                
                if trade_hash == "0x0000000000000000000000000000000000000000000000000000000000000000":
                    print(f"Warning: Null hash for {coin} trade (tid: {tid}, size: {size}, price: {price})")
                
                trade_data = {
                    'coin': coin,
                    'type': "LONG" if side == "BUY" else "SHORT",
                    'size': size,
                    'price': price,
                    'value_usd': trade_value_usd,
                    'timestamp': timestamp,
                    'side': side,
                    'trade_id': trade_hash,  # Use hash instead of tid
                    'hash': trade_hash,
                    'users': trade.get("users", [])
                }
                trades.append(trade_data)
            
            # FIXED LINE - simplified version
            trade_values = [f"${t['value_usd']:,.2f}" for t in trades]
            print(f"Fetched {len(trades)} trades for {coin} via HTTP, Values: {trade_values}")
            return trades
        except Exception as e:
            print(f"HTTP error for {coin}: {e}")
            return []

    async def fetch_hyperliquid_trades_websocket():
        """Fetch trades in real-time via Hyperliquid WebSocket with reconnection and ping-pong."""
        processed_trades = set()
        
        # Load previously processed trades
        if os.path.exists('hyperliquid_trades.csv'):
            try:
                df_existing = pd.read_csv('hyperliquid_trades.csv', on_bad_lines='skip')
                processed_trades = set(df_existing['trade_id'].astype(str).tolist())
                print(f"Loaded {len(processed_trades)} existing trade IDs")
            except Exception as e:
                print(f"Error reading existing trades: {e}")
        
        ws_attempts = 0
        max_ws_attempts = 5
        
        while ws_attempts < max_ws_attempts:
            try:
                async with websockets.connect(HYPERLIQUID_WS_URL, ping_interval=15, ping_timeout=30) as ws:
                    ws_attempts = 0  # Reset attempts on successful connection
                    # Subscribe to trades for each coin individually
                    for coin in COINS:
                        subscription = {
                            "method": "subscribe",
                            "subscription": {"type": "trades", "coin": coin}
                        }
                        await ws.send(json.dumps(subscription))
                        print(f"Sent subscription for {coin}")
                    
                    all_trades = []
                    while True:
                        try:
                            message = await ws.recv()
                            data = json.loads(message)
                            print(f"Received WebSocket message: {json.dumps(data, indent=2)[:500]}...")
                            
                            # Handle subscription confirmation
                            if data.get("method") == "subscribed":
                                print(f"Confirmed subscription: {data.get('subscription')}")
                                continue
                            
                            # Handle ping-pong
                            if data.get("method") == "pong":
                                print("Received pong from server")
                                continue
                            
                            # Handle trade data
                            if data.get("channel") == "trades" and "data" in data:
                                for trade in data["data"]:
                                    coin = trade.get("coin")
                                    if coin not in COINS:
                                        print(f"Ignored trade for non-monitored coin: {coin}")
                                        continue
                                    
                                    side = "BUY" if trade.get("side") == "B" else "SELL"
                                    size = float(trade.get("sz", 0))
                                    price = float(trade.get("px", 0))
                                    trade_value_usd = size * price
                                    timestamp = datetime.fromtimestamp(int(trade.get("time", 0)) / 1000)
                                    trade_hash = trade.get("hash", "0x0")
                                    tid = str(trade.get("tid", 0))
                                    
                                    if trade_hash == "0x0000000000000000000000000000000000000000000000000000000000000000":
                                        print(f"Warning: Null hash for {coin} trade (tid: {tid}, size: {size}, price: {price})")
                                    
                                    trade_data = {
                                        'coin': coin,
                                        'type': "LONG" if side == "BUY" else "SHORT",
                                        'size': size,
                                        'price': price,
                                        'value_usd': trade_value_usd,
                                        'timestamp': timestamp,
                                        'side': side,
                                        'trade_id': trade_hash,  # Use hash instead of tid
                                        'hash': trade_hash,
                                        'users': trade.get("users", [])
                                    }
                                    
                                    print(f"Processing trade for {coin}: Value ${trade_value_usd:,.2f}, Hash {trade_hash}, TID {tid}")
                                    
                                    if trade_data['trade_id'] in processed_trades:
                                        print(f"Skipped duplicate trade for {coin}: Hash {trade_data['trade_id']}")
                                        continue
                                    
                                    all_trades.append(trade_data)
                                    processed_trades.add(trade_data['trade_id'])
                                    
                                    print(f"New trade for {coin}: Value ${trade_value_usd:,.2f}, Hash {trade_hash}")
                                
                                # Filter large trades
                                large_trades = [trade for trade in all_trades if trade['value_usd'] > LARGE_TRADE_THRESHOLD_USD]
                                if large_trades:
                                    df_new = pd.DataFrame(large_trades)
                                    df_new.to_csv('hyperliquid_trades.csv', mode='a', index=False, header=not os.path.exists('hyperliquid_trades.csv'))
                                    print(f"Saved {len(large_trades)} large trades to CSV")
                                    
                                    for trade in large_trades:
                                        await send_telegram_notification(trade)
                                    
                                    all_trades = [t for t in all_trades if t['value_usd'] <= LARGE_TRADE_THRESHOLD_USD]
                                    
                                    print("New large Hyperliquid trades detected:")
                                    print(pd.DataFrame(large_trades)[['coin', 'type', 'size', 'value_usd', 'timestamp', 'hash', 'users']])
                        
                        except websockets.exceptions.ConnectionClosed as e:
                            print(f"WebSocket closed: {e}. Reconnecting...")
                            ws_attempts += 1
                            break
                        except Exception as e:
                            print(f"WebSocket error: {e}. Reconnecting...")
                            ws_attempts += 1
                            break
                
            except Exception as e:
                print(f"Failed to connect to WebSocket: {e}. Retrying in 5-10 seconds...")
                ws_attempts += 1
                await asyncio.sleep(5 + random.uniform(0, 5))
            
            if ws_attempts >= max_ws_attempts:
                print("Max WebSocket attempts reached. Falling back to HTTP polling...")
                return await fetch_hyperliquid_trades_http()

    async def fetch_hyperliquid_trades_http():
        """Fallback: Fetch trades via HTTP polling."""
        processed_trades = set()
        
        if os.path.exists('hyperliquid_trades.csv'):
            try:
                df_existing = pd.read_csv('hyperliquid_trades.csv', on_bad_lines='skip')
                processed_trades = set(df_existing['trade_id'].astype(str).tolist())
                print(f"Loaded {len(processed_trades)} existing trade IDs")
            except Exception as e:
                print(f"Error reading existing trades: {e}")
        
        all_trades = []
        for coin in COINS:
            try:
                trades = fetch_recent_trades(coin)
                for trade in trades:
                    if trade['trade_id'] in processed_trades:
                        print(f"Skipped duplicate trade for {coin}: Hash {trade['trade_id']}")
                        continue
                    all_trades.append(trade)
                    processed_trades.add(trade['trade_id'])
            except Exception as e:
                print(f"Error processing {coin}: {e}")
        
        large_trades = [trade for trade in all_trades if trade['value_usd'] > LARGE_TRADE_THRESHOLD_USD]
        if large_trades:
            df_new = pd.DataFrame(large_trades)
            df_new.to_csv('hyperliquid_trades.csv', mode='a', index=False, header=not os.path.exists('hyperliquid_trades.csv'))
            print(f"Saved {len(large_trades)} large trades to CSV")
            
            for trade in large_trades:
                await send_telegram_notification(trade)
            
            print("New large Hyperliquid trades detected:")
            print(pd.DataFrame(large_trades)[['coin', 'type', 'size', 'value_usd', 'timestamp', 'hash', 'users']])
        
        return pd.DataFrame(large_trades)

    # Send Telegram notification for large trade
    async def send_telegram_notification(trade_data):
        try:
            coin_price = get_coin_price(trade_data['coin'])
            message = (
                f"🐳 HVAAAAAL\n"
                f"Coin: {trade_data['coin']}\n"
                f"Type: {trade_data['type']} ({trade_data['side']})\n"
                f"Size: {trade_data['size']:.4f} {trade_data['coin']}\n"
                f"Price: ${trade_data['price']:,.2f}\n"
                f"Value: ${trade_data['value_usd']:,.2f}\n"
                f"Hash: {trade_data['hash']}\n"
                f"Users: {', '.join(trade_data['users'][:2])}\n"
                f"Time: {trade_data['timestamp']}"
            )
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
            print(f"Sent Telegram notification for {trade_data['coin']} {trade_data['type']} trade: ${trade_data['value_usd']:,.2f}")
        except Exception as e:
            print(f"Error sending Telegram notification: {e}")

    # Continuous listener
    async def hyperliquid_listener():
        print(f"Starting Hyperliquid large trades listener on {datetime.now()}")
        while True:
            try:
                update_thresholds()
                recent_large_trades = await fetch_hyperliquid_trades_websocket()
                if not recent_large_trades.empty:
                    print("New large Hyperliquid trades detected (HTTP fallback):")
                    print(recent_large_trades[['coin', 'type', 'size', 'value_usd', 'timestamp', 'hash', 'users']])
                else:
                    print("No large trades detected in this cycle")
                await asyncio.sleep(30)  # Poll every 30 seconds for HTTP fallback
            except Exception as e:
                print(f"Listener error: {e}")
                await asyncio.sleep(60)

    # Run the listener
    if __name__ == "__main__":
        print("Starting Whale Listener...")
        if os.path.exists('hyperliquid_trades.csv'):
            print("Eksisterende CSV fil fundet - fortsætter med eksisterende data")
        else:
            print("Ingen eksisterende CSV fil - starter frisk")
        
        asyncio.run(hyperliquid_listener())

except Exception as e:
    print(f"Kritisk fejl: {e}")
    print("Traceback:")
    traceback.print_exc()
    input("Tryk Enter for at afslutte...")
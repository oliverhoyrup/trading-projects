import pandas as pd
from datetime import date, timedelta, datetime
import yfinance as yf
import requests
import json
import os
import time

# ===== TELEGRAM CONFIG =====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STATE_FILE = "vix_strategy_state.json"

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] ✅ Telegram sent")
            return True
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] ❌ Telegram failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] ❌ Telegram error: {e}")
        return False

def get_sp500_and_vix():
    import warnings
    warnings.filterwarnings('ignore', category=FutureWarning)
    spy = yf.download("SPY", start="2000-02-01", progress=False)
    vix = yf.download("^VIX", start="2000-02-01", progress=False)
    if spy.empty or vix.empty:
        return None, None

    spy = spy[['Close']].copy()
    spy.columns = ['price']
    spy.index = pd.to_datetime(spy.index).date
    spy = spy[~spy.index.duplicated(keep='first')]

    vix = vix[['Close']].copy()
    vix.columns = ['vix']
    vix.index = pd.to_datetime(vix.index).date
    vix = vix[~vix.index.duplicated(keep='first')]

    return spy.sort_index(), vix.sort_index()

def save_state(last_buy_date):
    state = {"last_buy_date": last_buy_date.isoformat() if last_buy_date else None}
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                if data.get("last_buy_date"):
                    return date.fromisoformat(data["last_buy_date"])
        except:
            pass
    return None

def detect_vix_buys(spy_df, vix_df, start_date=None):
    df = spy_df.join(vix_df, how='inner').dropna()
    if len(df) < 21:
        return []

    window = 21
    df['vix_21d_avg'] = df['vix'].rolling(window=window).mean()

    def would_trigger_buy(i):
        if i < window:
            return False
        avg = df['vix_21d_avg'].iloc[i]
        if pd.notna(avg) and avg > 25:
            last_window = df['vix'].iloc[i - window + 1 : i + 1]
            return last_window.min() >= 20
        return False

    buys = []
    last_buy_date = load_state()
    cooldown_days = 75

    start_idx = df.index.get_loc(start_date) if start_date and start_date in df.index else window
    start_idx = max(start_idx, window)

    for i in range(start_idx, len(df)):
        current_date = df.index[i]
        if last_buy_date and (current_date - last_buy_date).days < cooldown_days:
            continue
        if would_trigger_buy(i):
            current_price = df['price'].iloc[i]
            buys.append({'date': current_date, 'price': current_price})
            last_buy_date = current_date
            save_state(last_buy_date)
    return buys

def run_vix_telegram_monitor():
    print("🚀 VIX Fear Strategy Bot (CMD Mode) — Starting...")
    spy_df, vix_df = get_sp500_and_vix()
    if spy_df is None:
        print("❌ Failed to fetch SPY/VIX data. Exiting.")
        return

    # Check last 7 days on startup
    last_week = max(spy_df.index[-7], spy_df.index[21])
    recent_buys = detect_vix_buys(spy_df, vix_df, start_date=last_week)

    for buy in recent_buys:
        msg = (
            f"🚨 <b>VIX FEAR BUY SIGNAL (S&P 500)</b> 🚨\n\n"
            f"📅 Date: {buy['date']}\n"
            f"💰 Price: ${buy['price']:,.2f}\n"
            f"📊 VIX 21d Avg >25, all ≥20\n"
            f"💎 Buy $1000 of SPY"
        )
        send_telegram_message(msg)

    if not recent_buys:
        print("✅ No signals in the last 7 days.")

    # Daily monitoring loop
    while True:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 🕒 Sleeping until next check (24h)...")
        time.sleep(24 * 3600)

        spy_df, vix_df = get_sp500_and_vix()
        if spy_df is None:
            continue

        today = spy_df.index[-1]
        last_saved = load_state()
        if last_saved and today <= last_saved:
            continue

        new_buys = detect_vix_buys(spy_df, vix_df)
        for buy in new_buys:
            msg = (
                f"🚨 <b>VIX FEAR BUY SIGNAL (S&P 500)</b> 🚨\n\n"
                f"📅 Date: {buy['date']}\n"
                f"💰 Price: ${buy['price']:,.2f}\n"
                f"📊 VIX 21d Avg >25, all ≥20\n"
                f"💎 Buy $1000 of SPY"
            )
            send_telegram_message(msg)

if __name__ == "__main__":
    run_vix_telegram_monitor()
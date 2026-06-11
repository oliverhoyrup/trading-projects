import requests
import json
import time
import os
import sys
from datetime import datetime, date
import csv
from collections import defaultdict
import statistics

class GMXFundingBot:
    def __init__(self, telegram_bot_token, telegram_chat_id, chain="arbitrum"):
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.chain = chain
        self.base_urls = [
            "https://arbitrum-api.gmxinfra.io",
            "https://arbitrum-api-fallback.gmxinfra.io", 
            "https://arbitrum-api-fallback.gmxinfra2.io"
        ]
        self.scale_factor = 10**30
        
        self.target_tokens = [
            "BTC/USD [WBTC.b-USDC]",
            "BTC/USD [WBTC.b-WBTC.b]",
            "ETH/USD [ETH-USDC]",
            "ETH/USD [ETH-ETH]"
        ]
        
        self.funding_state = {}
        self.last_negative_alert = {}
        
        self.last_summary_date = None
        self.summary_interval_days = 3
        
        self.price_history = {}
        self.price_alert_cooldown = {}
        
        self.error_count = 0
        self.max_errors = 10
        self.last_successful_run = time.time()

        # Logging and reporting
        self.log_file = "gmx_logging.csv"  # ✅ Updated filename
        self.last_average_report_date = None
        self._ensure_log_file()

    def _ensure_log_file(self):
        if not os.path.exists(self.log_file):
            with open(self.log_file, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "symbol", "annual_rate", "open_interest_short"])

    def get_markets_info(self):
        endpoint_path = "/markets/info"
        for base_url in self.base_urls:
            try:
                full_url = f"{base_url}{endpoint_path}"
                response = requests.get(full_url, timeout=30)
                if response.status_code == 200:
                    return response.json(), base_url
            except Exception as e:
                print(f"❌ API error with {base_url}: {e}")
                continue
        return None, None

    def parse_all_funding_rates(self, data):
        """Parse ALL markets (for logging), not just targets."""
        funding_rates = {}
        if not data or 'markets' not in data:
            return funding_rates

        markets = data['markets']

        for market in markets:
            symbol = market.get('name', market.get('symbol', 'Unknown'))
            try:
                net_rate_short_raw = market.get('netRateShort', '0')
                net_short_int = int(net_rate_short_raw) if net_rate_short_raw not in ['0', '-0'] else 0
                annual_rate_percent = (-net_short_int / self.scale_factor) * 100

                # ✅ Safely parse openInterestShort (handles "123" and "123.0")
                open_interest_short_raw = market.get('openInterestShort', '0')
                try:
                    oi_val = float(open_interest_short_raw)
                    open_interest_short = int(oi_val) / self.scale_factor
                except (ValueError, TypeError):
                    open_interest_short = 0.0

                funding_rates[symbol] = {
                    'annual_rate': annual_rate_percent,
                    'open_interest_short': open_interest_short
                }
            except (ValueError, TypeError, KeyError):
                continue

        return funding_rates

    def parse_funding_rates(self, data):
        """Parse ONLY target tokens (for alerts)."""
        funding_rates = {}
        if not data or 'markets' not in data:
            return funding_rates

        markets = data['markets']
        now = time.time()

        for market in markets:
            symbol = market.get('name', market.get('symbol', 'Unknown'))
            if symbol not in self.target_tokens:
                continue

            try:
                net_rate_short_raw = market.get('netRateShort', '0')
                net_short_int = int(net_rate_short_raw) if net_rate_short_raw not in ['0', '-0'] else 0
                annual_rate_percent = (-net_short_int / self.scale_factor) * 100

                price = None
                if 'price' in market:
                    try:
                        price_val = float(market['price'])
                        if price_val > 0:
                            price = price_val
                            if symbol not in self.price_history:
                                self.price_history[symbol] = []
                            self.price_history[symbol].append((now, price))
                            cutoff = now - (25 * 3600)
                            self.price_history[symbol] = [(t, p) for t, p in self.price_history[symbol] if t >= cutoff]
                    except (ValueError, TypeError):
                        pass

                # Parse openInterestShort safely
                open_interest_short_raw = market.get('openInterestShort', '0')
                try:
                    oi_val = float(open_interest_short_raw)
                    open_interest = int(oi_val) / self.scale_factor
                except (ValueError, TypeError):
                    open_interest = 0.0

                funding_rates[symbol] = {
                    'annual_rate': annual_rate_percent,
                    'annual_display': f"{annual_rate_percent:.1f}%",
                    'open_interest': open_interest,
                    'raw_net_short': net_rate_short_raw,
                    'price': price
                }

            except (ValueError, TypeError, KeyError):
                continue

        return funding_rates

    def log_all_funding_rates(self, all_rates):
        """Append all rates to CSV log."""
        timestamp = time.time()
        try:
            with open(self.log_file, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                for symbol, data in all_rates.items():
                    writer.writerow([
                        timestamp,
                        symbol,
                        data['annual_rate'],
                        data['open_interest_short']
                    ])
            print(f"💾 Logged {len(all_rates)} markets to {self.log_file}")
        except Exception as e:
            print(f"❌ Failed to log funding rates: {e}")

    def send_telegram(self, message):
        try:
            # ✅ FIXED: no spaces in URL
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                print(f"✅ Telegram sent: {message[:50]}...")
                return True
            else:
                print(f"❌ Telegram failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Telegram error: {e}")
            return False

    def check_funding_transitions(self, funding_rates):
        current_time = time.time()
        alerts = []

        for symbol, data in funding_rates.items():
            rate = data['annual_rate']

            if symbol not in self.funding_state:
                self.funding_state[symbol] = {
                    'state': 'negative' if rate < 0 else 'positive',
                    'since': current_time,
                    'positive_alert_sent': rate >= 0
                }
                continue

            state_info = self.funding_state[symbol]
            current_state = state_info['state']
            since = state_info['since']
            positive_alert_sent = state_info.get('positive_alert_sent', False)

            if rate < 0:
                if current_state == 'positive':
                    self.funding_state[symbol] = {
                        'state': 'negative',
                        'since': current_time,
                        'positive_alert_sent': False
                    }
                elif current_state == 'negative':
                    duration = current_time - since
                    if duration >= 3600:
                        last_alert = self.last_negative_alert.get(symbol, 0)
                        if current_time - last_alert >= 6 * 3600:
                            msg = f"📉 <b>{symbol}</b> funding has been negative for 1+ hours\nRate: {rate:.1f}% (annualized)"
                            alerts.append(msg)
                            self.last_negative_alert[symbol] = current_time
            else:
                if current_state == 'negative':
                    self.funding_state[symbol] = {
                        'state': 'positive',
                        'since': current_time,
                        'positive_alert_sent': False
                    }
                elif current_state == 'positive':
                    if not positive_alert_sent:
                        duration = current_time - since
                        if duration >= 3600:
                            msg = f"✅ <b>{symbol}</b> funding back to positive\nRate: {rate:.1f}% (annualized)"
                            alerts.append(msg)
                            self.funding_state[symbol]['positive_alert_sent'] = True

        return alerts

    def send_three_day_summary(self, funding_rates):
        today = date.today()
        if self.last_summary_date is None:
            self.last_summary_date = today
            return

        days_since = (today - self.last_summary_date).days
        if days_since >= self.summary_interval_days:
            summary_lines = ["📊 <b>GMX Funding Rate Summary (Every 3 Days)</b>"]
            for symbol, data in sorted(funding_rates.items()):
                summary_lines.append(f"• {symbol}: {data['annual_display']}")
            summary_lines.append("\nℹ️ Negative = longs pay shorts (favorable for shorts)")
            message = "\n".join(summary_lines)
            if self.send_telegram(message):
                self.last_summary_date = today
                print("✅ Sent 3-day summary")

    def check_price_change_alert(self, funding_rates):
        current_time = time.time()
        alerts = []
        cooldown = 24 * 3600

        for symbol, data in funding_rates.items():
            current_price = data.get('price')
            if current_price is None:
                continue

            history = self.price_history.get(symbol, [])
            if len(history) < 2:
                continue

            one_day_ago = current_time - (24 * 3600)
            old_price = None
            for t, p in history:
                if t <= one_day_ago:
                    old_price = p
            if old_price is None and history:
                old_price = history[0][1]

            if old_price is None or old_price <= 0:
                continue

            change_pct = ((current_price - old_price) / old_price) * 100
            if abs(change_pct) >= 10:
                last_alert = self.price_alert_cooldown.get(symbol, 0)
                if current_time - last_alert >= cooldown:
                    direction = "📈 UP" if change_pct > 0 else "📉 DOWN"
                    alert_msg = (
                        f"⚠️ <b>{symbol} Price Alert</b>\n"
                        f"{direction} {abs(change_pct):.1f}% in 24h!\n"
                        f"Old: ${old_price:,.2f} → Now: ${current_price:,.2f}\n"
                        f"❗ Review short position risk"
                    )
                    alerts.append(alert_msg)
                    self.price_alert_cooldown[symbol] = current_time

        return alerts

    def send_daily_all_time_average_report(self):
        today = date.today()
        if self.last_average_report_date == today:
            return

        try:
            symbol_data = defaultdict(list)
            if not os.path.exists(self.log_file):
                print("📊 Log file not found — skipping report")
                return

            with open(self.log_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        symbol = row['symbol']
                        rate = float(row['annual_rate'])
                        oi_short = float(row.get('open_interest_short', 0))
                        symbol_data[symbol].append((rate, oi_short))
                    except:
                        continue

            if not symbol_data:  # ✅ Fixed: full variable name
                print("📊 No data to report")
                return

            averages = {}
            latest_oi = {}
            for symbol, entries in symbol_data.items():
                rates = [r for r, _ in entries]
                ois = [oi for _, oi in entries]
                averages[symbol] = statistics.mean(rates)
                latest_oi[symbol] = ois[-1]

            # ✅ Filter: OI Short > $250,000
            qualified = {
                sym for sym in averages
                if latest_oi.get(sym, 0) > 250_000
            }

            # Always include your 4 tokens
            for token in self.target_tokens:
                if token in averages:
                    qualified.add(token)

            if not qualified:
                print("📊 No tokens meet $250k OI Short threshold")
                return

            final_sorted = sorted(
                [(sym, averages[sym]) for sym in qualified],
                key=lambda x: x[1],
                reverse=True
            )

            report_lines = ["🏆 <b>GMX Daily Funding Averages</b>"]
            report_lines.append(f"📅 {today.strftime('%Y-%m-%d')} | OI Short > $250k")
            report_lines.append("")

            for i, (symbol, avg) in enumerate(final_sorted, 1):
                arrow = "🟢" if avg >= 0 else "🔴"
                marker = " 💎" if symbol in self.target_tokens else ""
                report_lines.append(f"{i}. {arrow} <b>{symbol}</b>: {avg:.2f}%{marker}")

            message = "\n".join(report_lines)
            if self.send_telegram(message):
                self.last_average_report_date = today
                print("✅ Sent daily report")

        except Exception as e:
            print(f"❌ Error in daily report: {e}")

    def run_monitoring_cycle(self):
        try:
            raw_data, _ = self.get_markets_info()
            if not raw_data:
                self.error_count += 1
                print("❌ Failed to fetch data")
                return

            all_rates = self.parse_all_funding_rates(raw_data)
            if all_rates:
                self.log_all_funding_rates(all_rates)

            funding_rates = self.parse_funding_rates(raw_data)
            if not funding_rates:
                print("❌ No matching funding data for BTC/ETH")
                return

            self.error_count = 0
            self.last_successful_run = time.time()

            self.send_daily_all_time_average_report()
            self.send_three_day_summary(funding_rates)

            transition_alerts = self.check_funding_transitions(funding_rates)
            for alert in transition_alerts:
                print("📢 SENDING FUNDING TRANSITION ALERT")
                self.send_telegram(alert)

            price_alerts = self.check_price_change_alert(funding_rates)
            for alert in price_alerts:
                print("📢 SENDING PRICE CHANGE ALERT")
                self.send_telegram(alert)

            # ✅ Show OI Short in console
            print(f"📊 {datetime.now().strftime('%H:%M:%S')} - Rates:")
            for symbol, data in sorted(funding_rates.items()):
                status = "🔴" if data['annual_rate'] < 0 else "🟢"
                oi_short = data['open_interest']
                print(f"   {status} {symbol}: {data['annual_display']} (OI Short: ${oi_short:,.0f})")

        except Exception as e:
            self.error_count += 1
            print(f"❌ Unexpected error: {e}")

    def start_continuous_monitoring(self, interval_minutes=5):
        print("🚀 Starting ENHANCED monitoring...")
        print(f"Check interval: {interval_minutes} minutes")
        print("Telegram alerts:")
        print("• Full market names shown")
        print("• Negative funding: alert after 1h, then every 6h")
        print("• Positive recovery: alert after 1h (only if previously negative)")
        print("• ±10% price move in 24h")
        print("• Daily report: OI Short > $250k + your 4 tokens")
        print("Press Ctrl+C to stop\n")

        cycle_count = 0
        while True:
            try:
                cycle_count += 1
                if cycle_count % 12 == 0:
                    print(f"\n🔄 Cycle {cycle_count} - Running since: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"   Last success: {datetime.fromtimestamp(self.last_successful_run).strftime('%H:%M:%S')}")
                    print(f"   Errors: {self.error_count}/{self.max_errors}")

                self.run_monitoring_cycle()

                if self.error_count >= self.max_errors:
                    error_msg = (
                        f"🔴 <b>GMX Bot Multiple Failures</b>\n\n"
                        f"{self.error_count} consecutive errors.\n"
                        f"Last success: {datetime.fromtimestamp(self.last_successful_run).strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"Bot may need restart."
                    )
                    self.send_telegram(error_msg)
                    self.error_count = 0

                time.sleep(interval_minutes * 60)

            except KeyboardInterrupt:
                print("\n🛑 Monitoring stopped by user")
                break
            except Exception as e:
                print(f"❌ Critical error: {e}")
                self.error_count += 1
                time.sleep(60)

if __name__ == "__main__":
    print("🎯 GMX FUNDING BOT - OI SHORT > $250K FILTER")
    print("=" * 70)
    
    # get variables (.env fil)
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    # check keys otherwise error
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ FEJL: Telegram tokens ikke fundet!")
        print("Sørg for at have en .env fil med følgende:")
        print("TELEGRAM_BOT_TOKEN=din_token")
        print("TELEGRAM_CHAT_ID=dit_id")
        sys.exit(1)

    # Initialize
    bot = GMXFundingBot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, "arbitrum")
    
    try:
        bot.start_continuous_monitoring(interval_minutes=5)
    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped. Have a gud day")
        sys.exit(0)

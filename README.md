# Crypto & Stock Trading Bots 🤖

A collection of Python-based automated tools designed for market monitoring, sentiment analysis, and strategy execution. These bots integrate with Telegram to provide real-time alerts and actionable insights.

## 🛠 Included Bots

* **Whale Activity Listener**: A real-time monitor for the Hyperliquid exchange. It uses **WebSockets** to track large trades ("Whales") on BTC and ETH, helping to identify significant market moves as they happen.
* **VIX Buy Signals for S&P 500**: A quantitative strategy bot that monitors market fear via the **VIX Index**. It generates buy signals for the S&P 500 (SPY) when specific volatility thresholds and cooldown periods are met.
* **Funding Rate Arbitrage**: A specialized tool for identifying funding rate discrepancies on GMX, designed for market-neutral arbitrage strategies.

## 🚀 Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone [https://github.com/oliverhoyrup/crypto-trading-bots.git](https://github.com/oliverhoyrup/crypto-trading-bots.git)
   ```
   
2. **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3. **Configure Environment Variables**:

   Create a .env file in the root directory and add your credentials:
    ```bash
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
    ```

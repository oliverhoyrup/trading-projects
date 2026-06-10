# Trading Bots & Models 🤖

Hi there! This is my small collection of Python-based bots / models designed for market monitoring, sentiment analysis, and strategy execution. 3 of the files integrate with Telegram to provide real-time alerts and actionable insights.

## 🛠 Included Bots

* **Whale Activity Listener**: A real-time monitor for the Hyperliquid exchange. It uses **WebSockets** to track large trades ("Whales") on BTC and ETH, helping to identify significant market moves as they happen.
* **Machine Learning for Crypto Volatility Forecasting**: Using Random Forests, LSTM and XGBoost to predict volatility for ETH and BTC.
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

## Whale Activity Listener
This is a bot that monitors activity on Hyperliquid, a decentralized perpetuals futures trading exchange for cryptocurrency. It is inspired by the enormous short position placed on the exchange minutes before Trump's first tariff-reveal--which had a huge impact on stocks and crypto--that resulted in a +$160 million realized profit just ~an hour after the news. The Whale Listener will notify you on Telegram when unusually large short positions are being placed.


## Machine Learning for Crypto Volatility Forecasting 
This is a code i wrote for a school project while at Humboldt-Universität zu Berlin. I was interested in trying out different machine learning models to forecast the volatility of BTC and ETH and see which performed the best. XGBoost slightly outperformed LSTM and Random Forest. Predicting volatility is interesting since it can be used for risk management, hedging strategies and open up for options arbitrage opportunities if our models can predict volatility better than the market (implied volatility). 


## VIX Buy Signals for S&P 500 
This bot sends you a Telegram message when certain criteria have been met, that historically (backtested) outperforms DCA'ing.
It is obviously a very flawed strategy but was fun to make nonetheless.


## Funding Rate Arbitrage
This bot tracks the funding rate of 134 different coins on the perpetual futures exchange GMX and gives daily summaries of top-performing tokens (that has met certain volume criteria) in order to gather data and see which tokens are best suited for this strategy. The idea is then to open a short position of x token with x as colleteral creating a delta-neutral position that accumulates profit on the funding rate alone. Telegram notifications will update you on funding rates turning negative for longer periods of time (and back to positive) as well as the daily summary.


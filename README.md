# Quantitative Trading Infrastructure & Models 🤖

A collection of systematic trading tools, event-driven pipelines, and predictive models focused on digital assets and equity derivatives.

## 🛠 Portfolio Overview

| Project | Core Tech Stack | Architectural Focus |
| :--- | :--- | :--- |
| **Whale Activity Listener** | Asyncio, WebSockets, Tenacity, Pandas, Python-Telegram-Bot | Event-Driven Streaming, Hybrid Failover ETL, Fault Tolerance |
| **Crypto Volatility Forecasting** | TensorFlow, XGBoost, Scikit-Learn, NumPy, YFinance | Non-Linear Time-Series ML, Multi-Lag Feature Engineering |
| **VIX Systematic Signals** | Pandas, YFinance, Requests, State Serialization (JSON) | Persistent State Management, Rolling Matrix Math, Automation |
| **Funding Rate Arbitrage Bot** | REST APIs, Vectorized Math, Multi-Endpoint Rotators | Delta-Neutral Yield Optimization, Network Redundancy |
| **Energy Forecasting (Upcoming)** |

---

### 1. Whale Activity Listener (Hyperliquid Perpetual Markets)
This is a bot that monitors activity on Hyperliquid, a decentralized perpetuals futures trading exchange for cryptocurrency. It is inspired by the enormous short position placed on the exchange minutes before Trump's tariff-reveal that resulted in a +$160 million realized profit within 24 hours after the news due to the immediate stock and crypto market crash. The Whale Listener will notify you on Telegram when unusually large short positions are being placed.

<details>
<summary><b>View Technical Details & Infrastructure Architecture</b></summary>

#### Objective
Captures order-flow toxicity, institutional positioning, and anomalous block trades on Hyperliquid perpetual swap order books via low-latency streaming.

#### Core Engineering & Resiliency
* **Asynchronous Stream Ingestion:** Developed an asynchronous ingestion pipeline using `asyncio` and `websockets` to handle continuous, low-latency JSON trade ticks concurrently without blocking the main execution thread.
* **Fault-Tolerant Network State:** Implemented exponential backoff mechanics using the `tenacity` framework, actively maintaining WebSocket connection health with customized heartbeats (`ping_interval=15`, `ping_timeout=30`).
* **Hybrid Dynamic Failover:** Engineered an automated fallback module. If the WebSocket layer encounters persistent network disruption and exceeds maximum reconnection parameters (`max_ws_attempts=5`), the pipeline automatically shifts to historical HTTP REST polling to prevent telemetry blind spots.
* **Idempotency & Deduplication:** Tracks and validates unique cryptographic transaction identifiers (`trade_hash`) across an in-memory `set()` state and local append-only storage (`.csv`) to enforce structural data deduplication during multi-channel ingestion.
</details>


### 2. Machine Learning for Crypto Volatility Forecasting
This is a code i wrote while at Humboldt-Universität zu Berlin. I was interested in trying out different machine learning models to forecast the volatility of BTC and ETH and see which model performed the best. XGBoost slightly outperformed LSTM and Random Forest. Predicting volatility is interesting since it can be used for risk management, hedging strategies and open up for options arbitrage opportunities if our models can predict volatility better than the market (implied volatility). 

<details>
<summary><b>View Model Architecture & Mathematical Features</b></summary>

#### Objective
An empirical evaluation of non-linear machine learning architectures against traditional statistical benchmarks for predicting one-step-ahead hourly realized volatility ($RV$) on Bitcoin (BTC-USD).

---

## 📊 Performance Metrics & Comparison

Models were trained on 14 months of hourly data and evaluated out-of-sample on a 4-month test window.

| Model | Architecture Type | RMSE | MAE | $R^2$ |
| :--- | :--- | :--- | :--- | :--- |
| **Naive Baseline** | Persistence Benchmark ($\hat{\sigma}_{t+1} = \sigma_t$) | 0.0314 | 0.0148 | 0.9216 |
| **Random Forest** | Ensemble Tree (100 estimators, max depth 10) | 0.0277 | 0.0154 | 0.9390 |
| **LSTM** | Recurrent Neural Network (50 hidden units, Dropout 0.2) | 0.0280 | 0.0177 | 0.9374 |
| **XGBoost** | **Gradient Boosting (Learning Rate 0.05, early stopping)** | **0.0258** | **0.0147** | **0.9469** |

---

## 🛠 Feature Engineering & Mathematical Framework

To avoid look-ahead bias, all features were engineered strictly at time $t$ using vectorized matrix operations. Scalers were fit exclusively on training distributions.

* **Target Variable:** One-step-ahead realized volatility, defined as the rolling annualized standard deviation of log returns over a 30-hour window ($n=30$):
  $$\sigma_t^{RV} = \sqrt{\frac{1}{n-1} \sum_{i=1}^{n} r_{t-i}^2} \cdot \sqrt{24 \times 365}$$
* **Garman-Klass Volatility Feature:** Implemented an intra-bar, range-based estimator to capture structural intraday noise omitted by traditional close-to-close calculations:
  $$\sigma_{GK}^2 = 0.5 \cdot \left[\ln\frac{H}{L}\right]^2 - (2\ln 2 - 1) \cdot \left[\ln\frac{C}{O}\right]^2$$
* **Lag Matrix:** Modeled 5-period lags of log returns, squared returns, and rolling realized volatility, alongside 5-hour and 10-hour moving averages.
* **LSTM Input Transformation:** Formatted the 2D tabular feature matrix into scaled 3D temporal tensors `[samples, time-steps, features]` using a 24-hour lookback window.

---

## 🧠 Key Findings & Empirical Insights

* **XGBoost Superiority:** XGBoost delivered the strongest out-of-sample predictive power, representing an **~18% RMSE improvement over the naive baseline**. Its regularization constraints effectively distributed feature importance across the lag matrix rather than over-relying on $\sigma_t$.
* **The Volatility Floor:** The naive persistence model achieved an $R^2$ of 0.92, confirming strong volatility clustering (ARCH effects) in high-frequency crypto regimes. All machine learning optimization occurred within the narrow margin above this floor.
* **LSTM Tail Underperformance:** Despite its architectural complexity, the LSTM model underperformed on MAE. Training under standard Mean Squared Error (MSE) loss caused the network to make risk-averse predictions near the conditional mean, systematically undershooting volatility spikes.
* **Feature Signality:** MDI feature importance charts confirmed that `vol_lag_1` dominates model decisions, matching classic GARCH(1,1) behavior. The Garman-Klass estimator provided incremental predictive signal at high frequencies.

### 3. VIX Systematic Signals for S&P 500
This bot sends you a Telegram message when certain criteria have been met, that historically (backtested) outperforms DCA'ing.
It is obviously a very flawed strategy but was fun to make nonetheless.

<details>
<summary><b>View Strategy Logic & State Management</b></summary>

#### Objective
A programmatic systematic mean-reversion execution system designed to capture equity risk premiums during localized macroeconomic market panics.

#### System Architecture
* **Persistent State Management:** Utilizes a custom JSON state serialization engine (`vix_strategy_state.json`) to manage trade lifecycle data across system restarts, ensuring the execution engine strictly honors temporal parameters (e.g., a hardcoded `75-day` cooldown matrix).
* **Vectorized Matrix Slicing:** Employs vectorized rolling window analysis via `pandas` to isolate volatility distributions, calculating 21-day moving averages and rolling minima bounds concurrently to avoid unoptimized row-wise iterative loops.
</details>

### 4. Funding Rate Arbitrage (GMX Architecture)
This bot tracks the funding rate of 134 different coins on the perpetual futures exchange GMX and gives daily summaries of top-performing tokens (that has met certain volume criteria) in order to gather data and see which tokens are best suited for this strategy. The idea is then to open a short position of x token with x as colleteral creating a delta-neutral position that accumulates profit on the funding rate alone. Telegram notifications will update you on funding rates turning negative for longer periods of time (and back to positive) as well as the daily summary.

<details>
<summary><b>View Data Pipeline & Arbitrage Mechanics</b></summary>

#### Objective
Identifies structural capital inefficiencies across 130+ perpetual asset markets on GMX to generate automated, market-neutral yields.

#### Data Pipeline Architecture
* **Fault-Tolerant ETL:** Features an API engine that dynamically rotates through multiple decentralized fallback endpoints (`gmxinfra.io`) to seamlessly handle network timeouts, HTTP 429 rate limits, and node latency.
* **Delta-Neutral Processing:** Tracks Open Interest (OI) imbalances between long and short sides. The pipeline automatically flags fields where opening short positions yields high continuous funding tracking rates, while calculating spot asset collateral requirements to completely nullify directional price risk.
</details>

---






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







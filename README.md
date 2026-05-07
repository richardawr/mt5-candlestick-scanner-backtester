# MT5 Multi‑Timeframe Candlestick Pattern Scanner & Backtester

A comprehensive tool to scan **M5, M15, H1, H4, D1** charts for classical candlestick patterns, backtest their performance with realistic entry/exit simulation, and run a live scanner that alerts when a new pattern appears.

**Features**

- 20+ patterns: Doji, Hammer, Engulfing, Morning/Evening Star, Three White Soldiers, Marubozu, Harami, Tweezers, Rising/Falling Three Methods, etc.
- Stop Loss / Take Profit based on **ATR** (configurable multiplier, R:R ratio)
- **Higher‑timeframe ATR** for fast timeframes (M5/M15 automatically use H1 ATR → realistic SL/TP)
- **Entry verification** (stop orders only filled if touched on next candle)
- **Forward evaluation** with intra‑candle path simulation – avoids look‑ahead bias
- **R‑level tracking** (up to R5) and hit‑rate analysis
- **Volume confirmation** and **D1 trend filter**
- **Deduplication** – picks the highest‑priority pattern per candle
- **Session classification** (Asia, London, NY, etc.)
- **Full backtests** over date ranges → CSV reports, summary tables, and text reports
- **Live scanner** – monitors all active timeframes and prints formatted alerts when a new candle closes
- **Position sizing** (risk‑based) displayed in alerts

---

## Installation

1. **Install MetaTrader 5**

2. **Install Python dependencies**:
   pip install MetaTrader5 pandas numpy colorama python-dotenv

3. Clone this repository (or copy mt5_multitf_pattern_scanner.py into a folder).

4. Create a .env file in the same directory as the script, containing your MT5 login credentials:
.env

MT5_PATH=C:\Program Files\Broker\terminal64.exe

MT5_ACCOUNT=12345678

MT5_PASSWORD=YourPassword

MT5_SERVER=YourBrokerServer1



6. Run the script (see usage below).

Basic Usage
Live Scanner (default)
Monitors all active timeframes (M5, M15, H1, H4, D1) and prints alerts whenever a new candle closes and a pattern is detected.

python mt5_multitf_pattern_scanner.py
To scan only specific timeframes:

python mt5_multitf_pattern_scanner.py --timeframes H1 H4 D1
Press Ctrl+C to stop.

One‑Shot Scan
Scan the latest closed candle on all active timeframes and exit.


python mt5_multitf_pattern_scanner.py --mode scan
Quick Backtest (last N bars)
Simulate patterns on the most recent N candles (default 500) for a given timeframe.
Useful for a fast performance snapshot.

python mt5_multitf_pattern_scanner.py --mode backtest --bars 500 --timeframes H4
Full Backtest (date‑ranged)
Run a complete backtest over a specified date range.
Generates CSV files (detections, pattern summary, session summary) and a detailed text report.


# Backtest all timeframes for the full year 2025
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2025-12-31

# Backtest only H4 with D1 trend filter and volume filter enabled
python mt5_multitf_pattern_scanner.py --mode fullbacktest \
    --timeframes H4 \
    --from 2025-01-01 --to 2025-12-31 \
    --d1-trend-filter --volume-filter
Output directory: ./backtest_results/ (can be changed with --output).

Configuration
Most parameters can be changed via command‑line arguments:

Argument	Description	Default
--symbol	Trading symbol	EURUSD
--atr	ATR period	14
--sl	Stop loss multiplier (x ATR)	1.5
--tp	Take profit multiplier (x ATR)	1.5
--forward	Forward evaluation candles	15 for H4 (auto‑scaled per TF)
--volume-filter	Enable volume confirmation	False
--d1-trend-filter	Require trend on D1 to match pattern direction	False
--account-balance	Account size for position sizing display	100000
--risk-percent	Risk % of account per trade	1.0
See --help for the full list.

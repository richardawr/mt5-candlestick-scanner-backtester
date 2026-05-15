# MT5 Multi-Timeframe Candlestick Pattern Scanner & Backtester

A comprehensive tool to scan **M5, M15, H1, H4, D1** charts for classical candlestick patterns, backtest their performance with realistic entry/exit simulation, and run a live scanner that scores and alerts when a new pattern appears.

## Features

- **20+ patterns**: Doji, Hammer, Shooting Star, Engulfing, Morning/Evening Star, Three White Soldiers, Three Black Crows, Marubozu, Harami, Tweezers, Rising/Falling Three Methods, Inverted Hammer, and more
- **Multi-timeframe backtesting** — backtest all 5 timeframes in a single run with per-TF statistics
- **Pattern tier system** — patterns auto-classified as A:ELITE, B:TRADEABLE, C:MARGINAL, or D:AVOID based on historical win rate
- **Session quality classification** — sessions ranked as PRIME, FAVORABLE, NEUTRAL, or UNFAVORABLE
- **Signal scoring (0-100)** — each live signal scored using pattern tier, session quality, cross-stat edge, and historical win rate
- **Historical edge dashboard** — displayed at scanner startup showing top setups, pattern x session combos, Tier D avoid list, and recommended live setups
- **Per-timeframe WR columns** — pattern table shows win rate broken down by M5/M15/H1/H4/D1 so you can see which TF each pattern performs best on
- Stop Loss / Take Profit based on **ATR** (configurable multiplier, R:R ratio)
- **Higher-timeframe ATR** for fast timeframes (M5/M15 automatically use H1 ATR for realistic SL/TP)
- **Entry verification** (stop orders only filled if price touches entry on the next candle)
- **Forward evaluation** with intra-candle path simulation — avoids look-ahead bias
- **R-level tracking** (up to R5) and hit-rate analysis
- **Volume confirmation** (optional)
- **D1 trend filter** (enabled by default) — requires the daily SMA 20 trend to align with the pattern direction
- **Deduplication** — picks the highest-priority pattern per candle
- **Session classification** (Asia, Pacific, London Open, London Morning, London/NY Overlap, NY Afternoon)
- **Full backtests** over date ranges — CSV reports, summary tables, JSON stats cache, and text reports
- **Live scanner** — monitors all active timeframes and prints formatted alerts when a new candle closes
- **Position sizing** (risk-based, standard lots) displayed in alerts
- **Auto-reconnect** with exponential backoff if MT5 connection drops

---

## Installation

1. **Install MetaTrader 5**

2. **Install Python dependencies**:

   pip install MetaTrader5 pandas numpy colorama python-dotenv


3. Copy `mt5_multitf_pattern_scanner.py` into your project folder.

4. Create a `.env` file in the same directory as the script:

   MT5_PATH=C:\Program Files\Broker\terminal64.exe
   MT5_ACCOUNT=12345678
   MT5_PASSWORD=YourPassword
   MT5_SERVER=YourBrokerServer1


---

## Quick Start

### Step 1 — Run the Backtest

**The backtest generates the probability data that powers the live scanner's pattern tiers, signal scores, and historical edge display. Always run the backtest first.**

python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14

This scans all 5 timeframes (M5, M15, H1, H4, D1) over the date range and saves:
- Per-TF CSV files (detections, pattern summary, session summary) in `./backtest_results/`
- `latest_stats_multitf.json` — the stats cache the live scanner loads at startup

With D1 trend filter enabled (default), only signals that aligned with the daily trend are counted. This gives the most accurate stats for live trading.

### Step 2 — Run the Live Scanner

python mt5_multitf_pattern_scanner.py --mode live


The scanner starts, loads the backtest stats, and displays the **Historical Setups Dashboard**:
- Overall and per-timeframe win rates
- Pattern tiers with per-TF WR columns (M5 | M15 | H1 | H4 | D1)
- Session quality rankings
- Top pattern x session combos
- Tier D patterns to avoid
- Recommended live setups with signal scores

Then it monitors all timeframes and alerts on every new candle close when a pattern is detected, showing:
- Pattern name, tier, direction, session, D1 trend alignment
- Entry, SL, TP with pip distances and R:R ratio
- Prob(TP) percentage based on historical SL/TP hit rates
- Historical edge breakdown (pattern WR, session WR, cross-stat WR, signal score)
- Risk-based position sizing

Press `Ctrl+C` to stop.

---

## Usage

### Full Backtest (date-ranged)

Runs a complete backtest across all active timeframes over a specified date range. This is the primary way to generate stats for the live scanner.

# All timeframes, Jan 2025 to May 2026
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14

# Specific timeframes only
python mt5_multitf_pattern_scanner.py --mode fullbacktest --timeframes H4 D1 --from 2025-01-01 --to 2026-05-14

# With D1 trend filter ON (default) and volume filter
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --d1-trend-filter --volume-filter

# Without D1 trend filter
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --no-d1-trend-filter

Output: `./backtest_results/` (change with `--output`)

### Quick Backtest (last N bars)

Fast snapshot on the most recent N candles (default 500) for a single timeframe.

python mt5_multitf_pattern_scanner.py --mode backtest --bars 500


### Live Scanner

# All timeframes (default)
python mt5_multitf_pattern_scanner.py --mode live

# Specific timeframes
python mt5_multitf_pattern_scanner.py --mode live --timeframes H1 H4 D1

# Without D1 trend filter (must match how backtest was run)
python mt5_multitf_pattern_scanner.py --mode live --no-d1-trend-filter

### One-Shot Scan

Scan the latest closed candle on all active timeframes and exit.

python mt5_multitf_pattern_scanner.py --mode scan

---

## How Backtest Stats Flow Into the Live Scanner

1. **Backtest** creates per-TF CSV files (`*_detections.csv`, `*_pattern_summary.csv`, `*_session_summary.csv`) and `latest_stats_multitf.json`
2. **Live scanner** calls `load_latest_backtest_stats()` at startup, which:
   - Reads `latest_stats_multitf.json` for per-TF overall stats
   - Reads ALL per-TF CSVs to compute merged pattern stats, session stats, and cross-stats (pattern x session)
   - Caches results for 4 hours (configurable via `stats_cache_hours` in `.env`)
3. **Dashboard** displays: overall WR, per-TF WR table, pattern tiers with per-TF columns, session quality, top cross-stats, avoid list, recommended setups
4. **Each live signal** is enriched with: pattern tier badge, quality summary line, Prob(TP), historical edge breakdown, and signal score

**Important**: The D1 trend filter setting must match between backtest and live mode. If you run the backtest with `--d1-trend-filter` (default), run live with `--mode live` (also default). If you run backtest with `--no-d1-trend-filter`, run live with `--no-d1-trend-filter`.

---

## Configuration

### Command-Line Arguments

| Argument | Description | Default |
|---|---|---|
| `--symbol` | Trading symbol | `EURUSD` |
| `--timeframes` | Active timeframes | `M5 M15 H1 H4 D1` |
| `--atr` | ATR period | `14` |
| `--sl` | Stop loss multiplier (x ATR) | `1.5` |
| `--tp` | Take profit multiplier (x ATR) | `1.5` |
| `--forward` | Forward evaluation candles | Scaled per TF |
| `--d1-trend-filter` | Require D1 SMA trend alignment | `True` |
| `--no-d1-trend-filter` | Disable D1 trend filter | |
| `--d1-sma-period` | D1 trend SMA period | `20` |
| `--volume-filter` | Enable volume confirmation | `False` |
| `--no-volume-filter` | Disable volume filter (default) | |
| `--volume-ma-period` | Volume MA period | `20` |
| `--volume-threshold` | Volume threshold ratio | `1.0` |
| `--account-balance` | Account size for position sizing | `100000` |
| `--risk-percent` | Risk % of account per trade | `1.0` |
| `--min-signal-score` | Minimum signal score to display (0-100) | `0` |
| `--alert-only-strong` | Only alert on strong signals | `False` |
| `--output` | Backtest output directory | `./backtest_results` |

### Pattern Thresholds

| Argument | Description | Default |
|---|---|---|
| `--doji-body-ratio` | Max body/shadow ratio for Doji | `0.1` |
| `--spinning-top-body-ratio` | Max body ratio for Spinning Top | `0.33` |
| `--marubozu-wick-ratio` | Max wick ratio for Marubozu | `0.05` |
| `--hammer-lower-wick-ratio` | Min lower wick ratio for Hammer | `0.6` |
| `--hammer-upper-wick-ratio` | Max upper wick ratio for Hammer | `0.33` |
| `--long-candle-ratio` | Min body/shadow ratio for long candle | `0.6` |
| `--small-candle-ratio` | Max body/shadow ratio for small candle | `0.3` |
| `--tweezer-tolerance` | Tweezer tolerance in pips | `0.5` |

See `--help` for the full list of arguments.

---

## Signal Scoring System

Each live signal is scored 0-100 based on:

| Factor | Weight | Description |
|---|---|---|
| Pattern win rate | Confidence-weighted | Higher WR patterns score more, with a confidence boost for more signals |
| Pattern tier | Tier bonus | A:ELITE gets highest bonus, D:AVOID gets penalty |
| Session quality | Session bonus | PRIME > FAVORABLE > NEUTRAL > UNFAVORABLE |
| Cross-stat edge | Combo bonus | Pattern x session combos with high WR get a bonus |
| Avg Max R | Edge factor | Higher average max R-multiple indicates better profit potential |

Patterns below `--min-signal-score` are filtered out (default: 0, i.e. show all).

---

## Pattern Tiers

| Tier | WR Range | Meaning |
|---|---|---|
| **A: ELITE** | >= 57% | Highest edge, trade with confidence |
| **B: TRADEABLE** | 52-57% | Solid edge, reliable setups |
| **C: MARGINAL** | 45-52% | Use only with strong confluence |
| **D: AVOID** | < 45% | Negative edge, skip these |

---

## Output Files

### Backtest Results (`./backtest_results/`)

| File | Description |
|---|---|
| `EURUSD_{TF}_{date}_to_{date}_detections.csv` | Every pattern detected with entry, SL, TP, outcome, R-levels |
| `EURUSD_{TF}_{date}_to_{date}_pattern_summary.csv` | Per-pattern stats: WR, signals, avg SL, TP hit %, R-level hit rates |
| `EURUSD_{TF}_{date}_to_{date}_session_summary.csv` | Per-session stats: WR, signals, avg SL, TP hit % |
| `EURUSD_{TF}_{date}_to_{date}_report.txt` | Human-readable text report |
| `latest_stats_multitf.json` | Combined per-TF stats cache loaded by the live scanner |

---

## Session Classification

| Session | Broker Time (UTC+2/3) | Description |
|---|---|---|
| Pacific | 00:00 - 07:00 | Low liquidity, Sydney/Tokyo overlap |
| Asia | 07:00 - 00:00 | Tokyo session |
| London Open | 07:00 - 09:00 | High volatility London open |
| London Morning | 09:00 - 12:00 | Active London morning |
| London/NY Overlap | 12:00 - 17:00 | Highest liquidity window |
| NY Afternoon | 17:00 - 21:00 | NY afternoon, declining volume |

---

## Timezone Notes

- Log timestamps (`[HH:MM:SS]`) use your **local computer time**
- Candle close times and "Next:" candle times use **broker server time**
- Session classification uses **broker server time** hours
- This means candle times will differ from your local clock by your timezone offset

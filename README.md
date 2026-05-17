# MT5 Multi-Timeframe Candlestick Pattern Scanner & Backtester v8

A comprehensive tool to scan **M5, M15, H1, H4, D1** charts for classical candlestick patterns, backtest their performance with realistic entry/exit simulation, and run a live scanner that scores and alerts when a new pattern appears.

---

## Features

- **20+ patterns**: Doji, Hammer, Shooting Star, Engulfing, Morning/Evening Star, Three White Soldiers, Three Black Crows, Marubozu, Harami, Tweezers, Rising/Falling Three Methods, Inverted Hammer, and more
- **Multi-timeframe backtesting** — backtest all 5 timeframes in a single run with per-TF statistics
- **Trade management modes** — `fixed` (static SL/TP), `breakeven` (move SL to entry at 1R), `trail` (ATR-based trailing stop), `partial` (close 50% at 1R, trail remainder)
- **Structure-based SL placement** — place stops at pattern invalidation levels (below Hammer low, below Engulfing candle extreme, etc.) instead of generic ATR offsets
- **Equity curve & drawdown** — sequential P&L simulation with max drawdown, Sharpe ratio, Calmar ratio, profit factor, and consecutive win/loss streaks
- **Timeout classification** — choose between `marginal` (Marginal_Win/Loss based on close vs entry) or `expired` (flat 0R for all timeouts) for honest win rate reporting
- **Multi-symbol watchlist** — scan and backtest multiple symbols (e.g. `--symbols EURUSD GBPUSD USDJPY`)
- **Pattern tier system** — patterns auto-classified as A:ELITE, B:TRADEABLE, C:MARGINAL, or D:AVOID based on historical win rate
- **Session quality classification** — sessions ranked as PRIME, FAVORABLE, NEUTRAL, or UNFAVORABLE
- **Signal scoring (0-100)** — each live signal scored using TF-specific pattern WR, session gradient, confluence bonus, tier bonus, and MFE bonus
- **Confluence scoring (0-6 with D1 filter, 0-7 without)** — each backtest detection gets a confluence score based on trend alignment, volume, S/R context, RSI extreme, swing level, and session quality (D1 trend factor is skipped when the D1 trend filter is active, since it's already guaranteed)
- **Support/Resistance context** — swing high/low detection tags each signal as near_support, near_resistance, at_swing_low, or at_swing_high
- **RSI context** — RSI(14) computed at each detection; oversold/overbought contributes to confluence
- **Variable R:R by pattern** — configurable `rr_by_pattern` dict overrides TP multiplier per pattern
- **MAE/MFE tracking** — Max Adverse Excursion and Max Favorable Excursion in R-multiples per trade
- **Time-to-SL/TP** — bars until SL or TP hit, enabling trade management optimization
- **Exit R tracking** — actual R-multiple at trade exit (accounts for breakeven moves, trailing stops, partial closes)
- **Open-proximity SL/TP resolution** — when both SL and TP are within a candle's range, the level closer to the open price is assumed hit first (replaces the old candle-direction heuristic)
- **Wilder's ATR smoothing** — standard industry ATR method (alpha = 1/period), matching MT5's built-in indicator
- **Enriched stats JSON** — `latest_stats_multitf.json` now includes per-TF patterns, sessions, cross-stats, confluence breakdown, and equity curve metrics
- **D1 forward window extended** — D1 forward evaluation increased from 5 to 20 candles (4 trading weeks) for meaningful D1 stats
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
- **Sound alerts** (Windows only) — high-Hz triple beep for STRONG BUY, low-Hz triple beep for STRONG SELL; starts muted, type `m` + Enter to toggle
- **Position sizing** (risk-based, standard lots) displayed in alerts
- **Auto-reconnect** with exponential backoff if MT5 connection drops

---

## Installation

1. **Install MetaTrader 5**

2. **Install Python dependencies**:

   ```bash
   pip install MetaTrader5 pandas numpy colorama python-dotenv
   ```

3. Copy `mt5_multitf_pattern_scanner.py` into your project folder.

4. Create a `.env` file in the same directory as the script:

   ```ini
   MT5_PATH=C:\Program Files\Broker\terminal64.exe
   MT5_ACCOUNT=12345678
   MT5_PASSWORD=YourPassword
   MT5_SERVER=YourBrokerServer1
   ```

---

## Quick Start

### Step 1 — Run the Backtest

**The backtest generates the probability data that powers the live scanner's pattern tiers, signal scores, and historical edge display. Always run the backtest first.**

```bash
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14
```

This scans all 5 timeframes (M5, M15, H1, H4, D1) over the date range and saves:

- Per-TF CSV files (detections, pattern summary, session summary) in `./backtest_results/`
- `latest_stats_multitf.json` — the enriched stats cache the live scanner loads at startup (now includes per-TF patterns, sessions, cross-stats, confluence breakdown, and equity curve metrics)

With D1 trend filter enabled (default), only signals that aligned with the daily trend are counted. This gives the most accurate stats for live trading.

### Step 2 — Run the Live Scanner

```bash
python mt5_multitf_pattern_scanner.py --mode live
```

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

Sound alerts start **muted** by default. Type `m` + Enter in the terminal to unmute and hear audio alerts for strong signals. See [Sound Alerts](#sound-alerts) for details.

Press `Ctrl+C` to stop.

---

## Usage

### Full Backtest (date-ranged)

Runs a complete backtest across all active timeframes over a specified date range. This is the primary way to generate stats for the live scanner.

```bash
# All timeframes, Jan 2025 to May 2026
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14

# Specific timeframes only
python mt5_multitf_pattern_scanner.py --mode fullbacktest --timeframes H4 D1 --from 2025-01-01 --to 2026-05-14

# With D1 trend filter ON (default) and volume filter
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --d1-trend-filter --volume-filter

# Without D1 trend filter
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --no-d1-trend-filter

# With breakeven trade management
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --trade-management breakeven

# With trailing stop trade management
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --trade-management trail

# With structure-based SL placement
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --sl-mode structure

# With expired timeout classification (honest win rates)
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --timeout-mode expired

# Multi-symbol backtest
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --symbols EURUSD GBPUSD USDJPY
```

Output: `./backtest_results/` (change with `--output`)

### Quick Backtest (last N bars)

Fast snapshot on the most recent N candles (default 500) for a single timeframe.

```bash
python mt5_multitf_pattern_scanner.py --mode backtest --bars 500
```

### Live Scanner

```bash
# All timeframes (default)
python mt5_multitf_pattern_scanner.py --mode live

# Specific timeframes
python mt5_multitf_pattern_scanner.py --mode live --timeframes H1 H4 D1

# Without D1 trend filter (must match how backtest was run)
python mt5_multitf_pattern_scanner.py --mode live --no-d1-trend-filter
```

### One-Shot Scan

Scan the latest closed candle on all active timeframes and exit.

```bash
python mt5_multitf_pattern_scanner.py --mode scan
```

### Test Sound Alerts

Play both the STRONG BUY and STRONG SELL test beeps to verify audio is working, then exit.

```bash
python mt5_multitf_pattern_scanner.py --test-sound
```

---

## Sound Alerts

The scanner includes Windows-only sound alerts so you don't have to stare at the screen waiting for strong signals.

### How it works

- **STRONG BUY** (Bullish signal with score >= 65) — triple high-Hz beep (1200 Hz by default)
- **STRONG SELL** (Bearish signal with score >= 65) — triple low-Hz beep (400 Hz by default)
- The scanner starts **muted** — you must explicitly unmute to hear alerts
- Type `m` + Enter in the terminal to toggle mute/unmute at any time
- The keyboard listener runs in a background thread, so there is no delay — it responds instantly

### Startup message

When the live scanner starts with sound enabled, you will see:

```
Sound Alerts: ENABLED | Buy: 1200Hz | Sell: 400Hz | Threshold: 65
Sound is MUTED — Type "m" + Enter to unmute
```

### Toggling mute

Type `m` and press Enter at any time while the scanner is running:

```
Sound UNMUTED  |  Type 'm' + Enter to toggle
Sound MUTED    |  Type 'm' + Enter to toggle
```

### Testing sound

Before relying on alerts, verify your audio works:

```bash
python mt5_multitf_pattern_scanner.py --test-sound
```

This temporarily unmutes, plays both test beeps, then restores the muted state.

### Sound configuration

These settings are in the `CFG` dict at the top of the script (not exposed as CLI args):

| Key | Default | Description |
|---|---|---|
| `sound_enabled` | `True` | Master switch — set `False` to disable all sound |
| `sound_buy_hz` | `1200` | Frequency in Hz for STRONG BUY triple beep |
| `sound_sell_hz` | `400` | Frequency in Hz for STRONG SELL triple beep |
| `sound_beep_duration` | `150` | Duration of each individual beep in milliseconds |
| `sound_beep_pause` | `100` | Pause between beeps in milliseconds |
| `sound_strong_threshold` | `65.0` | Signal score must be >= this to trigger a sound alert |

---

## v8 Enhancements

### Trade Management Modes

The backtest now supports four trade management modes that control how the stop loss is managed after entry:

| Mode | Behavior |
|---|---|
| `fixed` | Static SL/TP — original behavior, no adjustment (default) |
| `breakeven` | Move SL to entry price (breakeven) when price reaches `breakeven_at_r` R (default: 1.0R) |
| `trail` | After price reaches `trail_at_r` R (default: 1.5R), move SL to breakeven, then trail by `trail_atr_mult` x ATR behind price |
| `partial` | Close `partial_close_pct` (default: 50%) of position at `partial_close_r` R (default: 1.0R), move SL to breakeven for remainder, then trail |

All modes also support **time-based stop tightening**: if `time_stop_pct` (default: 0.7 = 70%) of the forward evaluation window elapses without TP, the SL is tightened to breakeven. This only activates in non-`fixed` modes.

```bash
# Test breakeven mode (move SL to entry at 1R)
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --trade-management breakeven

# Test trailing stop (move to BE at 1.5R, then trail by 1x ATR)
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --trade-management trail

# Test partial close (close 50% at 1R, trail remainder)
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --trade-management partial
```

New detection columns track trade management outcomes:

| Column | Description |
|---|---|
| `Exit_R` | Actual R-multiple at trade exit (accounts for BE moves, trailing, partial closes) |
| `SL_Moved_to_BE` | True if SL was moved to breakeven during the trade |
| `Partial_Closed` | True if a partial position was closed |
| `Remaining_Pct` | Fraction of position still open at exit (1.0 = full, 0.5 = half) |

### Structure-Based SL Placement

Instead of using a generic `candle_low - sl_mult * ATR` for every pattern, structure-based SL places the stop at the pattern's **natural invalidation level** — the price level that would invalidate the pattern's signal:

| Pattern | Bullish SL Placement |
|---|---|
| Hammer / Inverted Hammer | Below signal candle's low (the wick IS the pattern) |
| Morning Star | Below the lowest point of the 3-candle pattern |
| Three White Soldiers | Below the first candle's low |
| Bullish Engulfing | Below the engulfing candle's low |
| Bullish Harami | Below the mother candle's low (previous candle) |
| Rising Three Methods | Below the first candle's low of the 5-candle pattern |
| Tweezer Bottoms | Below the lower of the two lows |
| Default (other) | Below signal candle's low |

Bearish patterns use the mirror (above pattern highs). A small buffer (`sl_structure_buffer_pips`, default: 2 pips) is added below/above the extreme.

```bash
# Use structure-based SL instead of ATR-based
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --sl-mode structure
```

Advantages over ATR-based SL:
- **Tighter stops** — pattern invalidation is often closer than 1.5x ATR, reducing risk per trade
- **Logical levels** — the stop has a reason (if the Hammer's low breaks, the pattern is invalidated)
- **Pattern-specific** — each pattern type gets its own optimal SL level

### Equity Curve & Drawdown Analysis

Each backtest timeframe now includes a **Section 8: Equity Curve & Drawdown** in the report, simulating sequential trading with 1R risk per trade and tracking cumulative P&L in R-multiples.

| Metric | Description |
|---|---|
| Final Equity | Total cumulative P&L in R-multiples |
| Max Drawdown | Largest peak-to-trough drawdown (R and %) |
| Max Consec Wins/Losses | Longest winning and losing streaks |
| Profit Factor | Gross profit / gross loss |
| Expectancy | Average R per trade |
| Sharpe Ratio | Annualised risk-adjusted return (assumes ~4 trades/day, 252 days/year) |
| Calmar Ratio | Annualised return / max drawdown |
| Avg Win/Loss R | Average R-multiple for wins and losses separately |

The equity curve uses the `Exit_R` column when available (v8 trade management), giving accurate P&L even with breakeven moves and partial closes. For `fixed` mode, it falls back to deriving R from the outcome type.

### Timeout Classification

By default, trades that reach the end of the forward evaluation window without hitting SL or TP are classified as `Marginal_Win` or `Marginal_Loss` based on whether the close is above or below entry. This inflates win rates by counting tiny gains (e.g. +0.2R) as full "wins".

The `--timeout-mode expired` option reclassifies all timeouts as `Expired` at 0R, giving an **honest win rate** that only counts actual TP vs SL outcomes:

| Mode | Timeout Outcome | Win Rate Meaning |
|---|---|---|
| `marginal` (default) | Marginal_Win (+0.1R to +0.5R) or Marginal_Loss (-0.1R to -0.5R) | Includes near-scratches as wins/losses |
| `expired` | Expired (0R) | Only real TP_Hit vs SL_Hit count |

```bash
# Honest win rates — timeouts = 0R scratch
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --timeout-mode expired
```

### Multi-Symbol Watchlist

The scanner and backtester now support scanning multiple symbols:

```bash
# Backtest multiple symbols
python mt5_multitf_pattern_scanner.py --mode fullbacktest --from 2025-01-01 --to 2026-05-14 --symbols EURUSD GBPUSD USDJPY

# Live scanner with watchlist
python mt5_multitf_pattern_scanner.py --mode live --symbols EURUSD GBPUSD
```

By default, only EURUSD is scanned (preserving backward compatibility). The watchlist can also be configured in the `CFG` dict via the `watchlist` key.

---

## v7 Enhancements

### Open-Proximity SL/TP Resolution

When both SL and TP fall within a single candle's range, the old heuristic used the candle's direction (bullish/bearish close) to decide which was hit first — this is look-ahead bias. The new heuristic uses **open-proximity**: whichever level is closer to the candle's open price was likely hit first. This is more realistic and corrects a 2-5% WR distortion.

### Confluence Scoring (0-6 with D1 filter, 0-7 without)

Each backtest detection receives a confluence score based on how many confirming factors align:

| Factor | +1 When |
|---|---|
| Trend alignment | Local trend agrees with trade direction |
| D1 trend alignment | Daily trend agrees with trade direction (**skipped when `--d1-trend-filter` is active**) |
| Volume confirmation | Signal candle has above-average volume |
| S/R context | Near support (bullish) or near resistance (bearish) |
| RSI extreme | RSI < 35 for bullish, RSI > 65 for bearish |
| At swing level | At swing low (bullish) or swing high (bearish) |
| Session quality | London/NY Overlap or London Open session |

> **Why skip D1 trend when the filter is active?** When `--d1-trend-filter` is on (the default), every signal already has D1 trend alignment guaranteed by the filter. Counting it as a confluence factor would inflate every score by +1 and destroy score differentiation. With the filter active, the effective range is 0-6; without the filter, it's 0-7.

The backtest report and JSON include confluence breakdowns, e.g. "Confluence >= 4: 72% WR vs Confluence 0-2: 48% WR".

### Variable R:R by Pattern

Different patterns have different optimal R:R profiles. Configure overrides in `CFG`:

```python
'rr_by_pattern': {
    'Bullish Engulfing': 1.5,    # Quick scalp
    'Morning Star': 2.5,         # Larger move expected
    'Three White Soldiers': 3.0, # Strong continuation
},
```

When a pattern is listed here, its TP multiplier is overridden. The `RR_Override` column in the detections CSV shows which patterns used overrides.

### MAE/MFE Tracking

Every trade now records:

- **MAE (Max Adverse Excursion)** — worst drawdown in R-multiples before the trade closed
- **MFE (Max Favorable Excursion)** — best profit in R-multiples before the trade closed

This enables trade management optimization like: "Move SL to breakeven after price reaches 1R" or "If MAE exceeds 0.8R, the trade has low probability of reaching TP".

### Time-to-SL/TP

Each trade records `Bars_to_SL` and `Bars_to_TP` — the number of forward candles until SL or TP was hit. This enables:

- Early exit strategies: "If not in profit after 8 M5 candles, close for breakeven"
- Trailing stop timing: "Move SL to breakeven after 4 H4 candles"

### Support/Resistance Context

The backtest now detects swing highs and lows (using a 5-bar local extreme window over the last 50 bars) and tags each detection with:

- `Near_Support` — price within 1 ATR of a swing low
- `Near_Resistance` — price within 1 ATR of a swing high
- `At_Swing_Low` — candle low is the lowest in the lookback window
- `At_Swing_High` — candle high is the highest in the lookback window

Patterns near support/resistance have dramatically different win rates.

### RSI Context

RSI(14) is computed at each detection using Wilder's smoothing method. The value is stored in the `RSI` column and contributes to confluence scoring (oversold for bullish, overbought for bearish).

### Enriched Stats JSON

`latest_stats_multitf.json` now includes per-TF breakdown of:

```json
{
  "timeframes": {
    "H4": {
      "overall": { "win_rate": 53.6, "total_signals": 252, "avg_mae_r": 0.45, "avg_mfe_r": 0.72, "avg_bars_to_tp": 5.2 },
      "patterns": { "Bullish Engulfing": { "win_rate": 58.2, "total": 312 } },
      "sessions": { "London/NY Overlap": { "win_rate": 55.1, "signals": 89 } },
      "cross": { "Bullish Engulfing|London/NY Overlap": { "win_rate": 62.3, "signals": 14 } },
      "confluence": { "3": { "win_rate": 68.2, "signals": 42 }, "0": { "win_rate": 44.1, "signals": 31 } },
      "equity": { "final_equity_r": 12.5, "max_dd_r": -4.3, "sharpe": 1.8, "calmar": 2.1 }
    }
  }
}
```

The live scanner now loads all data from JSON — **no CSV re-parsing at startup**, so the scanner starts instantly.

### Improved Signal Scoring

The v7 score formula fixes the old formula's problems:

| Factor | v6 (old) | v7 (new) |
|---|---|---|
| Base | `WR * confidence` (low-sample patterns got lower base) | Raw WR as base (no multiplication) |
| Sample size | Confidence multiplier | Sample penalty (-15 for small samples, 0 for 30+) |
| Session | Binary +10/-10 | Proportional gradient based on session WR |
| R-factor | `min(amr, 2.0) * 10` (up to +20, too large) | MFE bonus +1/+3 for amr >= 0.5/0.8 |
| Confluence | Not used | +5 if high-confluence signals have WR >= 55% |
| TF-specific | Used merged stats | Prefers TF-specific stats when available |

### D1 Forward Window Fix

D1 forward evaluation was only 5 candles (5 trading days). Since D1 ATR-based SL/TP often needs 2-4 weeks to resolve, this produced meaningless D1 stats (avg_max_r = 0.12R was an artifact). Now set to 20 candles (4 trading weeks).

### Wilder's ATR Smoothing

ATR now uses Wilder's exponential smoothing (alpha = 1/period) instead of simple moving average. This matches MT5's built-in ATR indicator and the industry standard. The difference from SMA can be 5-15% on SL/TP sizing.

---

## How Backtest Stats Flow Into the Live Scanner

1. **Backtest** creates per-TF CSV files and the enriched `latest_stats_multitf.json` (includes per-TF patterns, sessions, cross-stats, confluence breakdown, and equity metrics)
2. **Live scanner** calls `load_latest_backtest_stats()` at startup, which:
   - Reads `latest_stats_multitf.json` — if it has per-TF pattern/session/cross data (v7+), loads directly without CSV parsing
   - Falls back to CSV parsing only for older JSON formats
   - Caches results for 4 hours (configurable via `stats_cache_hours`)
3. **Dashboard** displays: overall WR, per-TF WR table, pattern tiers with per-TF columns, session quality, top cross-stats, avoid list, recommended setups
4. **Each live signal** is enriched with: pattern tier badge, quality summary line, Prob(TP), historical edge breakdown, TF-specific signal score, and confluence context

> **Important**: The D1 trend filter setting must match between backtest and live mode. If you run the backtest with `--d1-trend-filter` (default), run live with `--mode live` (also default). If you run backtest with `--no-d1-trend-filter`, run live with `--no-d1-trend-filter`.

---

## Configuration

### Command-Line Arguments

| Argument | Description | Default |
|---|---|---|
| `--symbol` | Trading symbol | `EURUSD` |
| `--symbols` | Watchlist of symbols to scan/backtest | `EURUSD` |
| `--timeframes` | Active timeframes | `M5 M15 H1 H4 D1` |
| `--atr` | ATR period | `14` |
| `--sl` | Stop loss multiplier (x ATR) | `1.5` |
| `--tp` | Take profit multiplier (x ATR) | `1.5` |
| `--forward` | Forward evaluation candles | Scaled per TF |
| `--sl-mode` | SL placement: `atr` or `structure` | `atr` |
| `--trade-management` | Trade management: `fixed`, `breakeven`, `trail`, `partial` | `fixed` |
| `--timeout-mode` | Timeout classification: `marginal` or `expired` | `marginal` |
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
| `--test-sound` | Play STRONG BUY and STRONG SELL test beeps, then exit | |
| `--output` | Backtest output directory | `./backtest_results` |

### CFG Config (in script)

These are set in the `CFG` dict at the top of the script:

| Key | Default | Description |
|---|---|---|
| `rr_by_pattern` | `{}` | Variable R:R overrides — map pattern name to TP multiplier |
| `trade_management_mode` | `fixed` | Trade management mode: fixed, breakeven, trail, partial |
| `breakeven_at_r` | `1.0` | R level at which SL moves to breakeven (breakeven mode) |
| `trail_at_r` | `1.5` | R level at which trailing starts (trail mode) |
| `trail_atr_mult` | `1.0` | Trail SL by this x ATR behind price (trail/partial mode) |
| `partial_close_r` | `1.0` | R level at which partial position is closed (partial mode) |
| `partial_close_pct` | `0.5` | Fraction of position to close at partial_close_r (50%) |
| `time_stop_pct` | `0.7` | Fraction of forward window after which SL tightens to BE (0 = disabled) |
| `sl_mode` | `atr` | SL placement mode: atr or structure |
| `sl_structure_buffer_pips` | `2` | Buffer in pips below pattern extreme for structure SL |
| `timeout_mode` | `marginal` | Timeout classification: marginal or expired |
| `watchlist` | `['EURUSD']` | Symbols to scan/backtest |
| `equity_curve_enabled` | `True` | Generate equity curve in full backtest |
| `sound_enabled` | `True` | Master switch for sound alerts |
| `sound_buy_hz` | `1200` | Hz for STRONG BUY triple beep |
| `sound_sell_hz` | `400` | Hz for STRONG SELL triple beep |
| `sound_beep_duration` | `150` | Duration per beep in ms |
| `sound_beep_pause` | `100` | Pause between beeps in ms |
| `sound_strong_threshold` | `65.0` | Min signal score to trigger sound |

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

## Signal Scoring System (v7)

Each live signal is scored 0-100 based on:

| Factor | Description |
|---|---|
| Base score | Raw pattern win rate (0-100) |
| Sample penalty | -15 to 0 based on sample size (0 at 30+ signals, -20 below minimum) |
| Session gradient | Proportional bonus/penalty based on session WR (e.g., +8 at 60% WR, -8 at 40% WR) |
| Confluence bonus | +5 if high-confluence signals (score >= 3) have WR >= 55% |
| Tier bonus | +5 for Tier A, +3 for Tier B |
| MFE bonus | +1 for avg_max_r >= 0.5, +3 for >= 0.8 |

**Per-TF scoring**: When `tf_label` is available (live scanner), the score prefers TF-specific pattern stats over merged aggregate stats. A Bullish Engulfing on H4 (58% WR) gets a different score than the same pattern on M5 (52% WR).

Patterns below `--min-signal-score` are filtered out (default: 0, i.e. show all).

---

## Pattern Tiers

| Tier | WR Range | Meaning |
|---|---|---|
| **A: ELITE** | >= 58% AND n >= 30 AND avg_max_r >= 0.35 | Highest edge, trade with confidence |
| **B: TRADEABLE** | >= 50% AND n >= 10 AND avg_max_r >= 0.25 | Solid edge, reliable setups |
| **C: MARGINAL** | >= 40% | Use only with strong confluence |
| **D: AVOID** | < 40% OR insufficient data | Negative edge, skip these |

---

## Output Files

### Backtest Results (`./backtest_results/`)

| File | Description |
|---|---|
| `EURUSD_{TF}_{date}_to_{date}_detections.csv` | Every pattern detected with entry, SL, TP, outcome, R-levels, MAE/MFE, RSI, S/R context, confluence score, Exit_R, trade management flags |
| `EURUSD_{TF}_{date}_to_{date}_pattern_summary.csv` | Per-pattern stats: WR, signals, SL/TP hit %, R-level hit rates, avg MAE/MFE, avg confluence |
| `EURUSD_{TF}_{date}_to_{date}_session_summary.csv` | Per-session stats: WR, signals, avg SL, TP hit % |
| `EURUSD_{TF}_{date}_to_{date}_report.txt` | Human-readable text report including equity curve & drawdown section |
| `latest_stats_multitf.json` | Enriched per-TF stats cache: overall, patterns, sessions, cross, confluence, equity metrics |

### Detection CSV Columns

#### v7 Columns

| Column | Description |
|---|---|
| `Bars_to_SL` | Number of forward candles until SL hit (None if not hit) |
| `Bars_to_TP` | Number of forward candles until TP hit (None if not hit) |
| `MAE_R` | Max Adverse Excursion in R-multiples |
| `MFE_R` | Max Favorable Excursion in R-multiples |
| `RSI` | RSI(14) value at the signal candle |
| `Near_Support` | True if price within 1 ATR of a swing low |
| `Near_Resistance` | True if price within 1 ATR of a swing high |
| `At_Swing_Low` | True if candle low is the lowest in lookback window |
| `At_Swing_High` | True if candle high is the highest in lookback window |
| `Confluence_Score` | 0-7 confluence score |
| `Confluence_Factors` | Pipe-separated list of contributing factors (e.g., `trend\|d1_trend\|support`) |
| `RR_Override` | Pattern name if variable R:R was applied, empty string otherwise |

#### v8 Columns

| Column | Description |
|---|---|
| `Exit_R` | Actual R-multiple at trade exit (accounts for BE moves, trailing, partial closes) |
| `SL_Moved_to_BE` | True if SL was moved to breakeven during the trade |
| `Partial_Closed` | True if a partial position was closed |
| `Remaining_Pct` | Fraction of position still open at exit (1.0 = full, 0.5 = half) |

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

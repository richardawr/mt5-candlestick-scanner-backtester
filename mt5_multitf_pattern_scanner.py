#!/usr/bin/env python3
"""
MT5 Multi-Timeframe Candlestick Pattern Scanner & Backtester v6
===============================================================
Expanded from v5: supports M5, M15, H1, H4, and D1 timeframes for both
live scanning and backtesting. All parameters are consolidated near the top.

Must run on Windows with MT5 installed.
Credentials are loaded exclusively from the .env file in the same directory.

Install: pip install MetaTrader5 pandas numpy colorama python-dotenv

Usage:
    # Live scanner — all 5 timeframes (default)
    python mt5_multitf_pattern_scanner_v6.py

    # Live scanner — specific timeframes only
    python mt5_multitf_pattern_scanner_v6.py --timeframes M5 H1 H4

    # One-shot scan of latest closed candle on all timeframes
    python mt5_multitf_pattern_scanner_v6.py --mode scan

    # Quick backtest (last 500 bars on H4)
    python mt5_multitf_pattern_scanner_v6.py --mode backtest --bars 500

    # Full backtest on one timeframe
    python mt5_multitf_pattern_scanner_v6.py --mode fullbacktest --timeframes H4

    # Full backtest on ALL timeframes, date-ranged
    python mt5_multitf_pattern_scanner_v6.py --mode fullbacktest --from 2024-01-01 --to 2024-12-31

    # Full backtest with filters
    python mt5_multitf_pattern_scanner_v6.py --mode fullbacktest \\
        --d1-trend-filter --volume-filter --forward 15 --sl 1.5 --tp 1.5

    # Live scanner with custom account sizing
    python mt5_multitf_pattern_scanner_v6.py --mode live --account-balance 25000 --risk-percent 0.5
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import argparse
import time
import os
import sys
import json
import glob
import re
import warnings
warnings.filterwarnings('ignore')

# ── Load credentials from .env file (REQUIRED) ─────────────────────
try:
    from dotenv import load_dotenv
    _dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(_dotenv_path):
        load_dotenv(_dotenv_path)
        _ENV_LOADED = True
    else:
        _ENV_LOADED = False
except ImportError:
    _ENV_LOADED = False

# ── Color output for Windows terminal ──────────────────────────────
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    _COLORAMA = True
except ImportError:
    _COLORAMA = False

def C(color, text):
    """Return colour-wrapped text if colorama available, else plain text."""
    if not _COLORAMA:
        return str(text)
    _MAP = {
        'green':   Fore.LIGHTGREEN_EX,
        'red':     Fore.LIGHTRED_EX,
        'yellow':  Fore.YELLOW,
        'cyan':    Fore.CYAN,
        'blue':    Fore.LIGHTBLUE_EX,
        'magenta': Fore.MAGENTA,
        'white':   Fore.WHITE,
        'dim':     Fore.BLACK,
        'bold':    Style.BRIGHT,
        'reset':   Style.RESET_ALL,
    }
    c = _MAP.get(color, '')
    return f"{c}{text}{Style.RESET_ALL}"


# ============================================================
# CONFIGURATION — ALL PARAMETERS IN ONE PLACE
# ============================================================

# ── MT5 Credentials (from .env — never hardcode) ───────────────────
_MT5_PATH     = os.getenv('MT5_PATH',     r"C:\Program Files\Capital Point Trading MT5 Terminal\terminal64.exe")
_MT5_ACCOUNT  = int(os.getenv('MT5_ACCOUNT', '52598748'))
_MT5_PASSWORD = os.getenv('MT5_PASSWORD', '')
_MT5_SERVER   = os.getenv('MT5_SERVER',   'CapitalPointTrading-Demo')

# ── Timeframe Map: label → MT5 constant + candle duration (minutes) ─
TIMEFRAME_MAP = {
    'M5':  {'mt5_tf': mt5.TIMEFRAME_M5,  'minutes': 5,    'label': 'M5'},
    'M15': {'mt5_tf': mt5.TIMEFRAME_M15, 'minutes': 15,   'label': 'M15'},
    'H1':  {'mt5_tf': mt5.TIMEFRAME_H1,  'minutes': 60,   'label': 'H1'},
    'H4':  {'mt5_tf': mt5.TIMEFRAME_H4,  'minutes': 240,  'label': 'H4'},
    'D1':  {'mt5_tf': mt5.TIMEFRAME_D1,  'minutes': 1440, 'label': 'D1'},
}

CFG = {
    # ── MT5 Connection ─────────────────────────────────────────────
    'mt5_path':       _MT5_PATH,
    'account':        _MT5_ACCOUNT,
    'password':       _MT5_PASSWORD,
    'server':         _MT5_SERVER,

    # ── Symbol & Timeframes ────────────────────────────────────────
    'symbol':                "EURUSD",
    # Active timeframes for live scan & backtest. All 5 available:
    # 'M5', 'M15', 'H1', 'H4', 'D1'
    'active_timeframes':     ['M5', 'M15', 'H1', 'H4', 'D1'],
    # Timeframe used as the D1 trend-filter source (should be >= 'H4')
    'trend_filter_tf':       'D1',

    # ── ATR / SL / TP ─────────────────────────────────────────────
    'atr_period':            14,
    'sl_multiplier':         1.5,
    'tp_multiplier':         1.5,    # R:R = tp_multiplier / sl_multiplier
    # Higher-timeframe ATR source per trading TF.
    # M5/M15 ATR is tiny → use H1 ATR for SL/TP sizing on fast TFs.
    # Set to None or same as trading TF to use native ATR.
    'atr_tf_by_tf': {
        'M5':  'H1',   # Use H1 ATR for M5 signals (much wider, more realistic SL/TP)
        'M15': 'H1',   # Use H1 ATR for M15 signals
        'H1':  'H1',   # Native
        'H4':  'H4',   # Native (H4 ATR is already meaningful)
        'D1':  'D1',   # Native
    },

    # ── Pattern Detection Thresholds ──────────────────────────────
    'doji_body_ratio':           0.1,
    'spinning_top_body_ratio':   0.3,
    'marubozu_wick_ratio':       0.05,
    'hammer_lower_wick_ratio':   2.0,
    'hammer_upper_wick_ratio':   0.3,
    'long_candle_ratio':         0.7,
    'small_candle_ratio':        0.35,
    'tweezer_tolerance_pips':    3,
    'engulf_tolerance_pips':     2.0,

    # ── Trend Detection ────────────────────────────────────────────
    'trend_lookback':        20,     # SMA-based lookback bars

    # ── Forward Evaluation (per-timeframe multiples of candle duration)
    # Default forward candles.  For fast TFs this is auto-scaled in
    # run_full_backtest() so the evaluation window is always ~60 hours.
    'default_forward_candles': 15,   # used as-is for H4 (60 h)
    # Per-timeframe forward candle overrides (set 0 to use auto-scaling)
    'forward_candles_by_tf': {
        'M5':  720,   # 720 × 5 min  = 60 h
        'M15': 240,   # 240 × 15 min = 60 h
        'H1':  60,    # 60  × 1 h    = 60 h
        'H4':  15,    # 15  × 4 h    = 60 h
        'D1':  5,     # 5   × 1 day  = 5 days (~1 trading week)
    },

    # ── Full Backtest ──────────────────────────────────────────────
    'max_r_levels':          5,
    'pip_divisor':           0.0001,
    'warmup_bars':           30,

    # ── Live Scanner ───────────────────────────────────────────────
    'bars_to_fetch':         50,     # bars fetched per TF for pattern context
    # Seconds between poll cycles per timeframe
    # M5/M15 poll more frequently; D1 can poll once per minute
    'poll_interval_by_tf': {
        'M5':  15,
        'M15': 30,
        'H1':  30,
        'H4':  30,
        'D1':  60,
    },

    # ── Session Classifier ─────────────────────────────────────────
    'broker_utc_offset':     2,      # UTC+2 broker server time

    # ── Signal Deduplication & Entry Verification ─────────────────
    'deduplicate_signals':   True,
    'verify_entry':          True,

    # ── Volume Confirmation ────────────────────────────────────────
    'volume_filter':         False,
    'volume_ma_period':      20,
    'volume_threshold':      1.0,    # signal candle vol >= threshold × avg

    # ── D1 Trend Filter ────────────────────────────────────────────
    'd1_trend_filter':       True,
    'd1_sma_period':         20,

    # ── Auto-Reconnect ─────────────────────────────────────────────
    'max_reconnect_attempts':    5,
    'reconnect_backoff_base':    10,  # seconds, doubles each retry

    # ── Live Stats Integration ─────────────────────────────────────
    'stats_cache_hours':         4,
    'min_signals_for_stats':     5,
    'min_historical_win_rate':   50.0,

    # ── Live Signal Filtering ──────────────────────────────────────
    'min_signal_score':      55.0,   # 0 = disabled
    'alert_only_strong':     True,
    'show_dashboard_on_start': True,

    # ── Position Sizing ────────────────────────────────────────────
    'account_balance':       100000,
    'risk_percent':          1.0,    # % of account per trade
}

# ── Derived Paths ───────────────────────────────────────────────────
_LOG_DIR          = os.path.dirname(os.path.abspath(__file__))
LOG_FILE          = os.path.join(_LOG_DIR, "mt5_pattern_scan_log.txt")
DEFAULT_OUTPUT_DIR = os.path.join(_LOG_DIR, "backtest_results")

# ── Pattern Priority for Deduplication ─────────────────────────────
PATTERN_PRIORITY = {
    'Doji': 1, 'Spinning Top': 1,
    'Hammer': 2, 'Inverted Hammer': 2,
    'Shooting Star': 2, 'Hanging Man': 2,
    'Marubozu (Bullish)': 3, 'Marubozu (Bearish)': 3,
    'Tweezer Tops': 4, 'Tweezer Bottoms': 4,
    'Near Bullish Engulfing': 4, 'Near Bearish Engulfing': 4,
    'Bullish Engulfing': 5, 'Bearish Engulfing': 5,
    'Bullish Harami': 6, 'Bearish Harami': 6,
    'Morning Star': 7, 'Evening Star': 7,
    'Three White Soldiers': 8, 'Three Black Crows': 8,
    'Rising Three Methods': 9, 'Falling Three Methods': 9,
}


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def log_message(msg, cfg=None):
    """Print and log a message. Strips ANSI colour codes for log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
    try:
        with open(LOG_FILE, "a", encoding='utf-8') as f:
            f.write(clean_line + "\n")
    except Exception:
        pass


def classify_session(hour, cfg=None):
    """Classify broker-time hour into a trading session."""
    if cfg is None:
        cfg = CFG
    offset = cfg.get('broker_utc_offset', 2)
    utc_hour = (hour - offset) % 24
    if 0 <= utc_hour < 7:
        return 'Asia'
    elif 7 <= utc_hour < 9:
        return 'London Open'
    elif 9 <= utc_hour < 12:
        return 'London Morning'
    elif 12 <= utc_hour < 16:
        return 'London/NY Overlap'
    elif 16 <= utc_hour < 20:
        return 'NY Afternoon'
    elif 20 <= utc_hour < 24:
        return 'Pacific'
    else:
        return 'Unknown'


def deduplicate_patterns(patterns, cfg=None):
    """Keep only the highest-priority directional pattern per candle."""
    if cfg is None:
        cfg = CFG
    if not cfg.get('deduplicate_signals', True):
        return patterns
    directional = [p for p in patterns if p.get('direction') != 'Neutral']
    neutral = [p for p in patterns if p.get('direction') == 'Neutral']
    if directional:
        directional.sort(key=lambda p: PATTERN_PRIORITY.get(p.get('name', ''), 0), reverse=True)
        return [directional[0]]
    else:
        neutral.sort(key=lambda p: PATTERN_PRIORITY.get(p.get('name', ''), 0), reverse=True)
        return [neutral[0]] if neutral else []


def get_forward_candles(tf_label, cfg=None):
    """Return the forward evaluation candle count for the given timeframe label."""
    if cfg is None:
        cfg = CFG
    overrides = cfg.get('forward_candles_by_tf', {})
    return overrides.get(tf_label, cfg.get('default_forward_candles', 15))


def get_atr_tf(tf_label, cfg=None):
    """Return the timeframe label used for ATR calculation for the given trading TF.

    If 'atr_tf_by_tf' maps a TF to a higher TF, that higher TF is returned.
    If the mapping is None or the same as tf_label, returns tf_label (native ATR).
    """
    if cfg is None:
        cfg = CFG
    atr_tf_map = cfg.get('atr_tf_by_tf', {})
    atr_tf = atr_tf_map.get(tf_label, tf_label)
    if atr_tf is None:
        return tf_label
    return atr_tf


# ============================================================
# PATTERN DETECTION — Structured-array version (scanner)
# ============================================================

def detect_trend(rates, cfg=None):
    """Detect trend using SMA over configurable lookback."""
    if cfg is None:
        cfg = CFG
    lookback = cfg.get('trend_lookback', 20)
    if isinstance(rates, pd.DataFrame):
        if len(rates) < lookback + 1:
            return 'ranging'
        closes = rates['CLOSE'].values if 'CLOSE' in rates.columns else rates['close'].values
        recent = closes[-(lookback+1):]
        sma = np.mean(recent[:-1])
        current_close = recent[-1]
    else:
        if len(rates) < lookback + 1:
            return 'ranging'
        recent = rates[-(lookback+1):]
        closes = np.array([r['close'] for r in recent])
        sma = np.mean(closes[:-1])
        current_close = closes[-1]
    if current_close > sma:
        return 'uptrend'
    elif current_close < sma:
        return 'downtrend'
    else:
        return 'ranging'


def compute_atr(rates, cfg=None):
    """Compute ATR from structured-array rates."""
    if cfg is None:
        cfg = CFG
    period = cfg.get('atr_period', 14)
    if len(rates) < period + 1:
        ranges = [r['high'] - r['low'] for r in rates]
        return np.mean(ranges) if ranges else 0.001
    tr_values = []
    for i in range(1, len(rates)):
        hl = rates[i]['high'] - rates[i]['low']
        hc = abs(rates[i]['high'] - rates[i-1]['close'])
        lc = abs(rates[i]['low'] - rates[i-1]['close'])
        tr_values.append(max(hl, hc, lc))
    if len(tr_values) >= period:
        return np.mean(tr_values[-period:])
    return np.mean(tr_values)


def get_candle_metrics(candle, cfg=None):
    """Compute metrics for a single candle (structured array row)."""
    body = abs(candle['close'] - candle['open'])
    body_sign = 1 if candle['close'] >= candle['open'] else -1
    range_val = candle['high'] - candle['low']
    upper_wick = candle['high'] - max(candle['open'], candle['close'])
    lower_wick = min(candle['open'], candle['close']) - candle['low']
    body_ratio = body / range_val if range_val > 0 else 0
    return {
        'body': body, 'body_sign': body_sign, 'range': range_val,
        'upper_wick': upper_wick, 'lower_wick': lower_wick, 'body_ratio': body_ratio
    }


def detect_doji(m, cfg=None):
    if cfg is None: cfg = CFG
    return m['range'] > 0 and m['body_ratio'] <= cfg['doji_body_ratio']

def detect_spinning_top(m, cfg=None):
    if cfg is None: cfg = CFG
    if m['range'] == 0 or m['body'] == 0: return False
    if m['body_ratio'] > cfg['spinning_top_body_ratio']: return False
    return m['upper_wick'] >= m['body'] and m['lower_wick'] >= m['body']

def detect_marubozu(m, cfg=None):
    if cfg is None: cfg = CFG
    if m['body'] == 0: return False
    if m['body_ratio'] < cfg['long_candle_ratio']: return False
    return (m['upper_wick'] <= m['body'] * cfg['marubozu_wick_ratio'] and
            m['lower_wick'] <= m['body'] * cfg['marubozu_wick_ratio'])

def detect_hammer(m, trend, cfg=None):
    if cfg is None: cfg = CFG
    if trend not in ('downtrend', 'ranging'): return False
    if m['body'] == 0: return False
    return (m['lower_wick'] >= m['body'] * cfg['hammer_lower_wick_ratio'] and
            m['upper_wick'] <= m['body'] * cfg['hammer_upper_wick_ratio'])

def detect_inverted_hammer(m, trend, cfg=None):
    if cfg is None: cfg = CFG
    if trend not in ('downtrend', 'ranging'): return False
    if m['body'] == 0: return False
    return (m['upper_wick'] >= m['body'] * cfg['hammer_lower_wick_ratio'] and
            m['lower_wick'] <= m['body'] * cfg['hammer_upper_wick_ratio'])

def detect_shooting_star(m, trend, cfg=None):
    if cfg is None: cfg = CFG
    if trend not in ('uptrend', 'ranging'): return False
    if m['body'] == 0: return False
    return (m['upper_wick'] >= m['body'] * cfg['hammer_lower_wick_ratio'] and
            m['lower_wick'] <= m['body'] * cfg['hammer_upper_wick_ratio'])

def detect_hanging_man(m, trend, cfg=None):
    if cfg is None: cfg = CFG
    if trend not in ('uptrend', 'ranging'): return False
    if m['body'] == 0: return False
    return (m['lower_wick'] >= m['body'] * cfg['hammer_lower_wick_ratio'] and
            m['upper_wick'] <= m['body'] * cfg['hammer_upper_wick_ratio'])

def detect_near_engulfing_full(curr, prev, cm, pm, cfg=None):
    if cfg is None: cfg = CFG
    if cm['body'] == 0 or pm['body'] == 0: return None
    tol = cfg.get('engulf_tolerance_pips', 2.0) * 0.0001
    if cm['body_sign'] == 1 and pm['body_sign'] == -1:
        if not (curr['open'] <= prev['close'] and curr['close'] >= prev['open']):
            if curr['open'] <= prev['close'] + tol and curr['close'] >= prev['open'] - tol:
                return 'Near Bullish Engulfing'
    if cm['body_sign'] == -1 and pm['body_sign'] == 1:
        if not (curr['open'] >= prev['close'] and curr['close'] <= prev['open']):
            if curr['open'] >= prev['close'] - tol and curr['close'] <= prev['open'] + tol:
                return 'Near Bearish Engulfing'
    return None

def detect_engulfing_full(curr, prev, cm, pm, cfg=None):
    if cm['body'] == 0 or pm['body'] == 0: return None
    if cm['body_sign'] == 1 and pm['body_sign'] == -1:
        if curr['open'] <= prev['close'] and curr['close'] >= prev['open']:
            return 'Bullish Engulfing'
    if cm['body_sign'] == -1 and pm['body_sign'] == 1:
        if curr['open'] >= prev['close'] and curr['close'] <= prev['open']:
            return 'Bearish Engulfing'
    return None

def detect_harami_full(curr, prev, cm, pm, cfg=None):
    if cfg is None: cfg = CFG
    if cm['body'] == 0 or pm['body'] == 0: return None
    if pm['body_ratio'] < cfg['long_candle_ratio'] * 0.8: return None
    ch = max(curr['open'], curr['close']); cl = min(curr['open'], curr['close'])
    ph = max(prev['open'], prev['close']); pl = min(prev['open'], prev['close'])
    if ch <= ph and cl >= pl:
        if pm['body_sign'] == -1 and cm['body_sign'] == 1: return 'Bullish Harami'
        if pm['body_sign'] == 1 and cm['body_sign'] == -1: return 'Bearish Harami'
    return None

def detect_morning_star(rates, idx, ml, cfg=None):
    if cfg is None: cfg = CFG
    if idx < 2: return False
    f, s, t = ml[idx-2], ml[idx-1], ml[idx]
    if f['body_sign'] != -1 or f['body_ratio'] < cfg['long_candle_ratio']: return False
    if s['body_ratio'] > cfg['small_candle_ratio'] + 0.1: return False
    if t['body_sign'] != 1 or t['body_ratio'] < cfg['long_candle_ratio'] * 0.7: return False
    return rates[idx]['close'] > (rates[idx-2]['open'] + rates[idx-2]['close']) / 2

def detect_evening_star(rates, idx, ml, cfg=None):
    if cfg is None: cfg = CFG
    if idx < 2: return False
    f, s, t = ml[idx-2], ml[idx-1], ml[idx]
    if f['body_sign'] != 1 or f['body_ratio'] < cfg['long_candle_ratio']: return False
    if s['body_ratio'] > cfg['small_candle_ratio'] + 0.1: return False
    if t['body_sign'] != -1 or t['body_ratio'] < cfg['long_candle_ratio'] * 0.7: return False
    return rates[idx]['close'] < (rates[idx-2]['open'] + rates[idx-2]['close']) / 2

def detect_three_white_soldiers(rates, idx, ml, cfg=None):
    if idx < 2: return False
    m1, m2, m3 = ml[idx-2], ml[idx-1], ml[idx]
    if m1['body_sign'] != 1 or m2['body_sign'] != 1 or m3['body_sign'] != 1: return False
    if m1['body_ratio'] < 0.5 or m2['body_ratio'] < 0.5 or m3['body_ratio'] < 0.5: return False
    return rates[idx]['close'] > rates[idx-1]['close'] > rates[idx-2]['close']

def detect_three_black_crows(rates, idx, ml, cfg=None):
    if idx < 2: return False
    m1, m2, m3 = ml[idx-2], ml[idx-1], ml[idx]
    if m1['body_sign'] != -1 or m2['body_sign'] != -1 or m3['body_sign'] != -1: return False
    if m1['body_ratio'] < 0.5 or m2['body_ratio'] < 0.5 or m3['body_ratio'] < 0.5: return False
    return rates[idx]['close'] < rates[idx-1]['close'] < rates[idx-2]['close']

def detect_tweezer(rates, idx, cfg=None):
    if cfg is None: cfg = CFG
    if idx < 1: return None
    prev, curr = rates[idx-1], rates[idx]
    tol = cfg['tweezer_tolerance_pips'] * 0.0001
    trend = detect_trend(rates[:idx+1], cfg)
    if abs(prev['high'] - curr['high']) <= tol and trend in ('uptrend', 'ranging'):
        return 'Tweezer Tops'
    if abs(prev['low'] - curr['low']) <= tol and trend in ('downtrend', 'ranging'):
        return 'Tweezer Bottoms'
    return None

def detect_rising_three_methods(rates, idx, ml, cfg=None):
    if cfg is None: cfg = CFG
    if idx < 4: return False
    fm = ml[idx-4]
    if fm['body_sign'] != 1 or fm['body_ratio'] < cfg['long_candle_ratio']: return False
    first = rates[idx-4]
    for i in range(1, 4):
        c = rates[idx-4+i]; cm = ml[idx-4+i]
        if cm['body_ratio'] > cfg['small_candle_ratio'] + 0.15: return False
        if c['high'] > first['high'] or c['low'] < first['low']: return False
    fm5 = ml[idx]
    if fm5['body_sign'] != 1 or fm5['body_ratio'] < cfg['long_candle_ratio'] * 0.7: return False
    return rates[idx]['close'] > first['close']

def detect_falling_three_methods(rates, idx, ml, cfg=None):
    if cfg is None: cfg = CFG
    if idx < 4: return False
    fm = ml[idx-4]
    if fm['body_sign'] != -1 or fm['body_ratio'] < cfg['long_candle_ratio']: return False
    first = rates[idx-4]
    for i in range(1, 4):
        c = rates[idx-4+i]; cm = ml[idx-4+i]
        if cm['body_ratio'] > cfg['small_candle_ratio'] + 0.15: return False
        if c['high'] > first['high'] or c['low'] < first['low']: return False
    fm5 = ml[idx]
    if fm5['body_sign'] != -1 or fm5['body_ratio'] < cfg['long_candle_ratio'] * 0.7: return False
    return rates[idx]['close'] < first['close']


# ============================================================
# VOLUME CONFIRMATION — Structured-array version
# ============================================================

def check_volume_confirmed(rates, idx, cfg=None):
    """Check if the signal candle's tick_volume confirms the pattern."""
    if cfg is None: cfg = CFG
    if not cfg.get('volume_filter', False):
        return True
    vol_period = cfg.get('volume_ma_period', 20)
    vol_thresh = cfg.get('volume_threshold', 1.0)
    start = max(0, idx - vol_period)
    vols = [r['tick_volume'] for r in rates[start:idx+1]]
    if len(vols) < 2:
        return True
    avg_vol = np.mean(vols[:-1])
    if avg_vol == 0:
        return True
    return vols[-1] >= vol_thresh * avg_vol


# ============================================================
# ENTRY PRICE LOGIC
# ============================================================

def compute_entry_details(candle, pattern_name, direction, trend, idx, rates, cfg=None):
    """Compute trade entry price based on pattern and candle structure."""
    if cfg is None: cfg = CFG
    body_top    = max(candle['open'], candle['close'])
    body_bottom = min(candle['open'], candle['close'])
    body_mid    = (body_top + body_bottom) / 2.0
    is_bullish_candle = candle['close'] >= candle['open']

    entry_type = entry_price = entry_reason = None

    if direction == 'Bullish':
        if pattern_name in ('Hammer', 'Inverted Hammer', 'Morning Star', 'Three White Soldiers',
                            'Tweezer Bottoms', 'Rising Three Methods') \
                or 'Bullish Engulfing' in pattern_name \
                or 'Bullish Harami' in pattern_name:
            entry_type, entry_price = 'Buy Stop', round(body_top, 5)
            entry_reason = f'Break above body top ({body_top:.5f}) confirms bullish signal'
        elif 'Marubozu' in pattern_name and 'Bullish' in pattern_name:
            entry_type, entry_price = 'Market Buy', round(candle['close'], 5)
            entry_reason = f'Bullish Marubozu close ({candle["close"]:.5f}) — strong momentum'
        else:
            entry_type, entry_price = 'Buy Stop', round(body_top, 5)
            entry_reason = f'Break above body top ({body_top:.5f})'

    elif direction == 'Bearish':
        if pattern_name in ('Evening Star', 'Shooting Star', 'Hanging Man', 'Three Black Crows',
                            'Falling Three Methods', 'Tweezer Tops') \
                or 'Bearish Engulfing' in pattern_name \
                or 'Bearish Harami' in pattern_name:
            entry_type, entry_price = 'Sell Stop', round(body_bottom, 5)
            entry_reason = f'Break below body bottom ({body_bottom:.5f}) confirms bearish signal'
        elif 'Marubozu' in pattern_name and 'Bearish' in pattern_name:
            entry_type, entry_price = 'Market Sell', round(candle['close'], 5)
            entry_reason = f'Bearish Marubozu close ({candle["close"]:.5f}) — strong momentum'
        else:
            entry_type, entry_price = 'Sell Stop', round(body_bottom, 5)
            entry_reason = f'Break below body bottom ({body_bottom:.5f})'
    else:
        entry_type  = 'Breakout'
        entry_price = None
        entry_reason = 'Wait for breakout: Buy Stop above body top OR Sell Stop below body bottom'

    return {
        'body_top': round(body_top, 5), 'body_bottom': round(body_bottom, 5),
        'body_mid': round(body_mid, 5), 'is_bullish_candle': is_bullish_candle,
        'entry_type': entry_type, 'entry_price': entry_price,
        'aggressive_entry': round(candle['close'], 5), 'entry_reason': entry_reason,
    }


def verify_entry_fill(entry_type, entry_price, next_candle, cfg=None):
    """Verify whether a stop/market entry would be filled on the next candle."""
    if cfg is None: cfg = CFG
    if not cfg.get('verify_entry', True):
        return True, entry_price
    if entry_type == 'Market Buy':
        return True, next_candle['open']
    elif entry_type == 'Market Sell':
        return True, next_candle['open']
    elif entry_type == 'Buy Stop':
        if next_candle['high'] >= entry_price:
            return True, max(next_candle['open'], entry_price)
        return False, None
    elif entry_type == 'Sell Stop':
        if next_candle['low'] <= entry_price:
            return True, min(next_candle['open'], entry_price)
        return False, None
    return True, entry_price


# ============================================================
# BACKTEST STATS LOADER (for live scanner integration)
# ============================================================

def load_latest_backtest_stats(output_dir=None, symbol=None, cfg=None):
    """Load pattern & session performance from latest backtest CSVs or JSON cache.

    Tries multiple sources in order:
      1. v5 JSON cache (latest_stats.json) — flat structure with patterns/sessions/cross
      2. v6 JSON cache (latest_stats_multitf.json) — multi-TF nested structure
      3. Fall back to parsing CSV files (supports both v5 and v6 naming)

    Returns dict with keys: patterns, sessions, overall, cross, generated_at
    """
    if cfg is None: cfg = CFG
    if output_dir is None: output_dir = DEFAULT_OUTPUT_DIR
    if symbol is None: symbol = cfg.get('symbol', 'EURUSD')
    cache_hours = cfg.get('stats_cache_hours', 4)

    # ── Try v5 JSON cache first (flat structure with pattern/session/cross stats) ──
    v5_cache_path = os.path.join(output_dir, 'latest_stats.json')
    if os.path.exists(v5_cache_path):
        try:
            with open(v5_cache_path, 'r', encoding='utf-8') as f:
                stats = json.load(f)
            # v5 cache has 'patterns', 'sessions', 'overall', 'cross' at top level
            if stats.get('patterns') or stats.get('overall'):
                generated = stats.get('generated_at', '')
                if generated:
                    gen_dt = datetime.strptime(generated, '%Y-%m-%d %H:%M:%S')
                    age_hours = (datetime.now() - gen_dt).total_seconds() / 3600
                    if age_hours < cache_hours * 24:  # v5 cache: allow 24h staleness
                        return stats
        except Exception:
            pass

    # ── Try v6 multi-TF JSON cache ──
    v6_cache_path = os.path.join(output_dir, 'latest_stats_multitf.json')
    if os.path.exists(v6_cache_path):
        try:
            with open(v6_cache_path, 'r', encoding='utf-8') as f:
                v6_stats = json.load(f)
            generated = v6_stats.get('generated_at', '')
            if generated:
                gen_dt = datetime.strptime(generated, '%Y-%m-%d %H:%M:%S')
                age_hours = (datetime.now() - gen_dt).total_seconds() / 3600
                if age_hours < cache_hours * 24:
                    # Convert v6 multi-TF structure to v5 flat structure
                    # Aggregate across all timeframes into unified stats
                    stats = _merge_multitf_stats(v6_stats, output_dir, symbol)
                    if stats.get('patterns') or stats.get('overall'):
                        return stats
        except Exception:
            pass

    # ── Fall back to parsing CSVs (both v5 and v6 naming) ──
    stats = {'patterns': {}, 'sessions': {}, 'overall': {}, 'cross': {}}

    # Find latest CSVs — try v5 naming first, then v6 naming
    pattern_csvs = sorted(
        glob.glob(os.path.join(output_dir, f"{symbol}_*_pattern_summary.csv")) +
        glob.glob(os.path.join(output_dir, f"{symbol}_*_*_to_*_pattern_summary.csv")),
        reverse=True
    )
    session_csvs = sorted(
        glob.glob(os.path.join(output_dir, f"{symbol}_*_session_summary.csv")) +
        glob.glob(os.path.join(output_dir, f"{symbol}_*_*_to_*_session_summary.csv")),
        reverse=True
    )
    det_csvs = sorted(
        glob.glob(os.path.join(output_dir, f"{symbol}_*_detections.csv")) +
        glob.glob(os.path.join(output_dir, f"{symbol}_*_*_to_*_detections.csv")),
        reverse=True
    )

    if pattern_csvs:
        try:
            df_p = pd.read_csv(pattern_csvs[0])
            for _, row in df_p.iterrows():
                pat = row['Pattern']
                stats['patterns'][pat] = {
                    'win_rate': round(float(row.get('Win_Rate_%', 0)), 1),
                    'total': int(row.get('Total', 0)),
                    'avg_max_r': round(float(row.get('Avg_Max_R', 0)), 2),
                    'sl_hit_pct': round(float(row.get('SL_Hit_%', 0)), 1),
                    'tp_hit_pct': round(float(row.get('TP_Hit_%', 0)), 1),
                }
        except Exception:
            pass

    if session_csvs:
        try:
            df_s = pd.read_csv(session_csvs[0])
            for _, row in df_s.iterrows():
                sess = row['Session']
                stats['sessions'][sess] = {
                    'win_rate': round(float(row.get('Win_Rate_%', 0)), 1),
                    'signals': int(row.get('Signals', 0)),
                    'avg_max_r': round(float(row.get('Avg_Max_R', 0)), 2),
                    'sl_hit_pct': round(float(row.get('SL_Hit_%', 0)), 1),
                    'tp_hit_pct': round(float(row.get('TP_Hit_%', 0)), 1),
                }
        except Exception:
            pass

    # Overall + cross stats from detections CSV
    if det_csvs:
        try:
            df_d = pd.read_csv(det_csvs[0])
            directional = df_d[df_d['Direction'] != 'Neutral']
            if len(directional) > 0:
                s = int((directional['Prediction_Success'] == True).sum())
                f_ = int((directional['Prediction_Success'] == False).sum())
                stats['overall'] = {
                    'win_rate': round(s / (s + f_) * 100, 1) if (s + f_) > 0 else 0,
                    'total_signals': len(directional),
                    'avg_max_r': round(float(directional['Max_R'].dropna().mean()), 2),
                    'sl_hit_pct': round(float((directional['SL_Hit'] == True).sum() / len(directional) * 100), 1),
                    'tp_hit_pct': round(float((directional['TP_Hit'] == True).sum() / len(directional) * 100), 1),
                }
                cross = {}
                for pat_name in directional['Pattern'].unique():
                    pat_dir = directional[directional['Pattern'] == pat_name]
                    for sess in pat_dir['Session'].unique():
                        ps = pat_dir[pat_dir['Session'] == sess]
                        if len(ps) >= 3:
                            s_ps = int((ps['Prediction_Success'] == True).sum())
                            f_ps = int((ps['Prediction_Success'] == False).sum())
                            cross[f"{pat_name}|{sess}"] = {
                                'win_rate': round(s_ps / (s_ps + f_ps) * 100, 1) if (s_ps + f_ps) > 0 else 0,
                                'signals': len(ps),
                                'avg_max_r': round(float(ps['Max_R'].dropna().mean()), 2),
                            }
                stats['cross'] = cross
        except Exception:
            pass

    stats['generated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return stats


def _merge_multitf_stats(v6_stats, output_dir, symbol):
    """Merge v6 multi-TF stats into v5 flat structure for display compatibility.

    Reads ALL per-TF CSVs (pattern_summary, session_summary, detections) and:
      - Builds per-TF pattern stats in stats['patterns_tf']
      - Properly merges across all TFs for overall pattern/session/cross stats
      - Carries per-TF overall stats from the v6 JSON
    """
    tf_order = ['M5', 'M15', 'H1', 'H4', 'D1']
    stats = {'patterns': {}, 'sessions': {}, 'overall': {}, 'cross': {},
             'generated_at': v6_stats.get('generated_at', ''),
             'patterns_tf': {tf: {} for tf in tf_order},
             'timeframes': {}}
    # Carry over per-TF overall stats from the v6 JSON
    for tf_label, tf_data in v6_stats.get('timeframes', {}).items():
        if 'overall' in tf_data:
            stats['timeframes'][tf_label] = tf_data['overall']

    # ── Parse ALL pattern_summary CSVs ──
    pattern_csvs = sorted(
        glob.glob(os.path.join(output_dir, f"{symbol}_*_*_to_*_pattern_summary.csv")),
        reverse=True
    )
    if pattern_csvs:
        try:
            all_dfs = [pd.read_csv(p) for p in pattern_csvs]
            df_all = pd.concat(all_dfs, ignore_index=True)
            # Per-TF pattern stats
            for tf in tf_order:
                tf_rows = df_all[df_all.get('Timeframe', pd.Series(dtype=str)) == tf]
                if len(tf_rows) > 0:
                    for _, row in tf_rows.iterrows():
                        pat = row['Pattern']
                        stats['patterns_tf'][tf][pat] = {
                            'win_rate': round(float(row.get('Win_Rate_%', 0)), 1),
                            'total': int(row.get('Total', 0)),
                            'avg_max_r': round(float(row.get('Avg_Max_R', 0)), 2),
                        }
            # Merged across all TFs (weighted by signal count)
            for pat in df_all['Pattern'].unique():
                rows = df_all[df_all['Pattern'] == pat]
                total_sig = int(rows['Total'].sum())
                if total_sig > 0:
                    total_wins = 0
                    total_maxr_w = 0.0
                    total_sl_w = 0.0
                    total_tp_w = 0.0
                    for _, r in rows.iterrows():
                        n = int(r.get('Total', 0))
                        if n > 0:
                            total_wins += round(float(r.get('Win_Rate_%', 0)) * n / 100)
                            total_maxr_w += float(r.get('Avg_Max_R', 0)) * n
                            total_sl_w += float(r.get('SL_Hit_%', 0)) * n
                            total_tp_w += float(r.get('TP_Hit_%', 0)) * n
                    stats['patterns'][pat] = {
                        'win_rate': round(total_wins / total_sig * 100, 1),
                        'total': total_sig,
                        'avg_max_r': round(total_maxr_w / total_sig, 2),
                        'sl_hit_pct': round(total_sl_w / total_sig, 1),
                        'tp_hit_pct': round(total_tp_w / total_sig, 1),
                    }
        except Exception:
            pass

    # ── Parse ALL session_summary CSVs ──
    session_csvs = sorted(
        glob.glob(os.path.join(output_dir, f"{symbol}_*_*_to_*_session_summary.csv")),
        reverse=True
    )
    if session_csvs:
        try:
            all_dfs = [pd.read_csv(s) for s in session_csvs]
            df_all = pd.concat(all_dfs, ignore_index=True)
            for sess in df_all['Session'].unique():
                rows = df_all[df_all['Session'] == sess]
                total_sig = int(rows['Signals'].sum())
                if total_sig > 0:
                    total_wins = 0
                    total_maxr_w = 0.0
                    total_sl_w = 0.0
                    total_tp_w = 0.0
                    for _, r in rows.iterrows():
                        n = int(r.get('Signals', 0))
                        if n > 0:
                            total_wins += round(float(r.get('Win_Rate_%', 0)) * n / 100)
                            total_maxr_w += float(r.get('Avg_Max_R', 0)) * n
                            total_sl_w += float(r.get('SL_Hit_%', 0)) * n
                            total_tp_w += float(r.get('TP_Hit_%', 0)) * n
                    stats['sessions'][sess] = {
                        'win_rate': round(total_wins / total_sig * 100, 1),
                        'signals': total_sig,
                        'avg_max_r': round(total_maxr_w / total_sig, 2),
                        'sl_hit_pct': round(total_sl_w / total_sig, 1),
                        'tp_hit_pct': round(total_tp_w / total_sig, 1),
                    }
        except Exception:
            pass

    # ── Parse ALL detections CSVs for overall + cross stats ──
    det_csvs = sorted(
        glob.glob(os.path.join(output_dir, f"{symbol}_*_*_to_*_detections.csv")),
        reverse=True
    )
    if det_csvs:
        try:
            all_dfs = [pd.read_csv(d) for d in det_csvs]
            df_d = pd.concat(all_dfs, ignore_index=True)
            directional = df_d[df_d['Direction'] != 'Neutral']
            if len(directional) > 0:
                s = int((directional['Prediction_Success'] == True).sum())
                f_ = int((directional['Prediction_Success'] == False).sum())
                stats['overall'] = {
                    'win_rate': round(s / (s + f_) * 100, 1) if (s + f_) > 0 else 0,
                    'total_signals': len(directional),
                    'avg_max_r': round(float(directional['Max_R'].dropna().mean()), 2),
                    'sl_hit_pct': round(float((directional['SL_Hit'] == True).sum() / len(directional) * 100), 1),
                    'tp_hit_pct': round(float((directional['TP_Hit'] == True).sum() / len(directional) * 100), 1),
                }
                cross = {}
                for pat_name in directional['Pattern'].unique():
                    pat_dir = directional[directional['Pattern'] == pat_name]
                    for sess in pat_dir['Session'].unique():
                        ps = pat_dir[pat_dir['Session'] == sess]
                        if len(ps) >= 3:
                            s_ps = int((ps['Prediction_Success'] == True).sum())
                            f_ps = int((ps['Prediction_Success'] == False).sum())
                            cross[f"{pat_name}|{sess}"] = {
                                'win_rate': round(s_ps / (s_ps + f_ps) * 100, 1) if (s_ps + f_ps) > 0 else 0,
                                'signals': len(ps),
                                'avg_max_r': round(float(ps['Max_R'].dropna().mean()), 2),
                            }
                stats['cross'] = cross
        except Exception:
            pass
    return stats


def compute_pattern_tier(pattern_name, stats, cfg=None):
    """Classify a pattern into a tier (A/B/C/D) based on backtest statistics.

    Tier A (Elite):     WR >= 58% AND sample >= 30 AND avg_max_r >= 0.35R
    Tier B (Tradeable):  WR >= 50% AND sample >= 10 AND avg_max_r >= 0.25R
    Tier C (Marginal):   WR >= 40% AND sample >= 5
    Tier D (Avoid):      WR < 40% OR insufficient data
    """
    if cfg is None: cfg = CFG
    min_sig = cfg.get('min_signals_for_stats', 5)
    pat_stats = stats.get('patterns', {}).get(pattern_name, {})
    n = pat_stats.get('total', 0)
    wr = pat_stats.get('win_rate', 0)
    amr = pat_stats.get('avg_max_r', 0)
    if n < min_sig:
        return ('D', 'AVOID', 'red')
    if wr >= 58 and n >= 30 and amr >= 0.35:
        return ('A', 'ELITE', 'green')
    elif wr >= 50 and n >= 10 and amr >= 0.25:
        return ('B', 'TRADEABLE', 'yellow')
    elif wr >= 40:
        return ('C', 'MARGINAL', 'red')
    else:
        return ('D', 'AVOID', 'red')


def compute_session_quality(session, stats, cfg=None):
    """Classify session quality based on directional win rate and R-multiples.

    Returns: (quality_label, quality_color, sess_wr, sess_n, sess_amr)
    """
    if cfg is None: cfg = CFG
    min_sig = cfg.get('min_signals_for_stats', 5)
    sess_stats = stats.get('sessions', {}).get(session, {})
    n = sess_stats.get('signals', 0)
    wr = sess_stats.get('win_rate', 0)
    amr = sess_stats.get('avg_max_r', 0)
    if n < min_sig:
        return ('UNKNOWN', 'dim', 0, n, 0)
    if wr >= 55 and amr >= 0.35:
        return ('PRIME', 'green', wr, n, amr)
    elif wr >= 50:
        return ('FAVORABLE', 'green', wr, n, amr)
    elif wr >= 45:
        return ('NEUTRAL', 'yellow', wr, n, amr)
    else:
        return ('UNFAVORABLE', 'red', wr, n, amr)


def compute_cross_quality(pattern_name, session, stats, cfg=None):
    """Get the most specific win rate and quality for a pattern+session combo.

    Returns: (cross_wr, cross_n, cross_amr, cross_label, cross_color)
    """
    if cfg is None: cfg = CFG
    min_sig = cfg.get('min_signals_for_stats', 5)
    cross_key = f"{pattern_name}|{session}"
    cross_stats = stats.get('cross', {}).get(cross_key, {})
    pat_stats = stats.get('patterns', {}).get(pattern_name, {})
    if cross_stats and cross_stats.get('signals', 0) >= min_sig:
        wr = cross_stats.get('win_rate', 0)
        n = cross_stats.get('signals', 0)
        amr = cross_stats.get('avg_max_r', 0)
    elif pat_stats and pat_stats.get('total', 0) >= min_sig:
        wr = pat_stats.get('win_rate', 0)
        n = pat_stats.get('total', 0)
        amr = pat_stats.get('avg_max_r', 0)
    elif stats.get('overall', {}).get('total_signals', 0) >= min_sig:
        wr = stats['overall'].get('win_rate', 0)
        n = stats['overall'].get('total_signals', 0)
        amr = stats['overall'].get('avg_max_r', 0)
    else:
        return (None, 0, 0, 'N/A', 'dim')
    if wr >= 60:
        return (wr, n, amr, 'HIGH EDGE', 'green')
    elif wr >= 50:
        return (wr, n, amr, 'EDGE', 'yellow')
    elif wr >= 40:
        return (wr, n, amr, 'WEAK', 'red')
    else:
        return (wr, n, amr, 'NO EDGE', 'red')


def compute_signal_score(pattern_name, session, direction, stats, cfg=None):
    """Compute a 0-100 signal quality score based on historical backtest stats.

    Score formula:
      base_score = pattern_win_rate (0-100)
      session_bonus = +10 if session WR > 55%, -10 if < 45%
      confidence_factor = min(1.0, signals / 30)
      r_factor = avg_max_r / 1.0
      tier_bonus = +5 for Tier A, +3 for Tier B
    """
    if cfg is None: cfg = CFG
    min_signals = cfg.get('min_signals_for_stats', 5)
    pat_stats = stats.get('patterns', {}).get(pattern_name, {})
    sess_stats = stats.get('sessions', {}).get(session, {})
    cross_key = f"{pattern_name}|{session}"
    cross_stats = stats.get('cross', {}).get(cross_key, {})
    if cross_stats and cross_stats.get('signals', 0) >= min_signals:
        wr = cross_stats.get('win_rate', 50)
        n = cross_stats.get('signals', 0)
        amr = cross_stats.get('avg_max_r', 0)
    elif pat_stats and pat_stats.get('total', 0) >= min_signals:
        wr = pat_stats.get('win_rate', 50)
        n = pat_stats.get('total', 0)
        amr = pat_stats.get('avg_max_r', 0)
    elif stats.get('overall', {}).get('total_signals', 0) >= min_signals:
        overall = stats['overall']
        wr = overall.get('win_rate', 50)
        n = overall.get('total_signals', 0)
        amr = overall.get('avg_max_r', 0)
    else:
        return None
    base_score = wr
    confidence = min(1.0, n / 30.0)
    session_bonus = 0
    if sess_stats and sess_stats.get('signals', 0) >= min_signals:
        sess_wr = sess_stats.get('win_rate', 50)
        if sess_wr > 55:
            session_bonus = 10
        elif sess_wr < 45:
            session_bonus = -10
    r_factor = min(amr, 2.0) * 10
    tier_letter, _, _ = compute_pattern_tier(pattern_name, stats, cfg)
    tier_bonus = 5 if tier_letter == 'A' else (3 if tier_letter == 'B' else 0)
    score = base_score * confidence + session_bonus + r_factor + tier_bonus
    return round(max(0, min(100, score)), 1)


def print_top_setups(stats, cfg=None):
    """Print best historical setups at scanner start — top patterns, sessions, and cross-stats."""
    if cfg is None: cfg = CFG
    min_sig = cfg.get('min_signals_for_stats', 5)
    min_wr = cfg.get('min_historical_win_rate', 50.0)
    lines = []
    lines.append("")
    lines.append(C('cyan', "=" * 70))
    lines.append(C('bold', "  TOP HISTORICAL SETUPS (from latest backtest)"))
    lines.append(C('cyan', "=" * 70))
    overall = stats.get('overall', {})
    if overall:
        owr = overall.get('win_rate', 0)
        owr_color = 'green' if owr >= min_wr else 'red'
        lines.append(f"  Overall: {C(owr_color, f'WR {owr:.1f}%')} | {overall.get('total_signals',0)} signals | Avg Max R: {overall.get('avg_max_r',0):.2f}R")
    # Per-timeframe breakdown
    tf_stats = stats.get('timeframes', {})
    if tf_stats:
        lines.append(f"  {'Timeframe':<12s} | {'WR':>6s} | {'Signals':>8s} | {'Avg Max R':>10s}")
        lines.append(f"  {'-'*12} | {'-'*6} | {'-'*8} | {'-'*10}")
        for tf_label, tf_overall in tf_stats.items():
            twr = tf_overall.get('win_rate', 0)
            tclr = 'green' if twr >= min_wr else ('yellow' if twr >= 45 else 'red')
            lines.append(f"  {tf_label:<12s} | {C(tclr, f'{twr:>5.1f}%')} | {tf_overall.get('total_signals',0):>8d} | {tf_overall.get('avg_max_r',0):>9.2f}R")
    pat_list = []
    patterns_tf = stats.get('patterns_tf', {})
    for pat, data in stats.get('patterns', {}).items():
        n = data.get('total', 0)
        wr = data.get('win_rate', 0)
        amr = data.get('avg_max_r', 0)
        if n >= min_sig:
            confidence = min(1.0, n / 30.0)
            weighted = wr * confidence + min(amr, 2.0) * 10
            tier_letter, tier_label, tier_clr = compute_pattern_tier(pat, stats, cfg)
            # Find best TF for this pattern
            best_tf, best_tf_wr = '', 0
            tf_wrs = {}
            for tf in ['M5', 'M15', 'H1', 'H4', 'D1']:
                if pat in patterns_tf.get(tf, {}):
                    tf_wr = patterns_tf[tf][pat].get('win_rate', 0)
                    tf_n = patterns_tf[tf][pat].get('total', 0)
                    tf_wrs[tf] = (tf_wr, tf_n) if tf_n >= min_sig else (None, tf_n)
                    if tf_n >= min_sig and tf_wr > best_tf_wr:
                        best_tf_wr = tf_wr
                        best_tf = tf
                else:
                    tf_wrs[tf] = (None, 0)
            pat_list.append((pat, wr, n, amr, weighted, tier_letter, tier_label, tier_clr, best_tf, tf_wrs))
    pat_list.sort(key=lambda x: x[4], reverse=True)
    tf_cols = ['M5', 'M15', 'H1', 'H4', 'D1']
    if pat_list:
        lines.append("")
        lines.append(f"  {'Pattern':<28s} | {'Tier':>14s} | {'M5':>5s} | {'M15':>5s} | {'H1':>5s} | {'H4':>5s} | {'D1':>5s} | {'Sig':>6s} | {'Edge':>5s}")
        lines.append(f"  {'-'*28} | {'-'*14} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*6} | {'-'*5}")
        for pat, wr, n, amr, weighted, tl, tlab, tc, best_tf, tf_wrs in pat_list[:7]:
            edge_tag = "HIGH" if wr >= min_wr else "LOW"
            edge_color = 'green' if wr >= min_wr else 'red'
            tf_cells = []
            for tf in tf_cols:
                tf_wr, tf_n = tf_wrs.get(tf, (None, 0))
                if tf_wr is not None:
                    clr = 'green' if tf_wr >= min_wr else ('yellow' if tf_wr >= 45 else 'red')
                    tf_cells.append(C(clr, f'{tf_wr:>4.1f}%'))
                else:
                    tf_cells.append(f"  {'--' if tf_n < min_sig else '':>4s} ")
            tf_str = ' | '.join(tf_cells)
            lines.append(f"  {pat:<28s} | {C(tc, f'{tl}:{tlab}'):>14s} | {tf_str} | {n:>6d} | {C(edge_color, f'{edge_tag:>5s}')}")
    all_sess = [(s, d) for s, d in stats.get('sessions', {}).items()
                if d.get('signals', 0) >= min_sig]
    if all_sess:
        all_sess.sort(key=lambda x: x[1].get('win_rate', 0), reverse=True)
        lines.append("")
        lines.append(C('bold', "  Session Quality:"))
        for sess, data in all_sess:
            swr = data.get('win_rate', 0)
            sq, sqc, _, sn, samr = compute_session_quality(sess, stats, cfg)
            lines.append(f"    {sess:<22s} | {C(sqc, f'{swr:.1f}% WR [{sq}]')} ({sn} sig) | AvgMaxR: {samr:.2f}R")
    cross_list = []
    for key, data in stats.get('cross', {}).items():
        n = data.get('signals', 0)
        wr = data.get('win_rate', 0)
        amr = data.get('avg_max_r', 0)
        if n >= min_sig:
            confidence = min(1.0, n / 20.0)
            weighted = wr * confidence + min(amr, 2.0) * 10
            cross_list.append((key, wr, n, amr, weighted))
    cross_list.sort(key=lambda x: x[4], reverse=True)
    if cross_list:
        lines.append("")
        lines.append(f"  {'Pattern x Session':<40s} | {'WR':>6s} | {'Sig':>4s} | {'MaxR':>5s}")
        lines.append(f"  {'-'*40} | {'-'*6} | {'-'*4} | {'-'*5}")
        for key, wr, n, amr, weighted in cross_list[:5]:
            cwr_color = 'green' if wr >= min_wr else 'yellow'
            lines.append(f"  {key:<40s} | {C(cwr_color, f'{wr:>5.1f}%')} | {n:>4d} | {amr:>4.2f}R")
    weak = [(p, d) for p, d in stats.get('patterns', {}).items()
            if d.get('total', 0) >= min_sig and d.get('win_rate', 0) < 45]
    if weak:
        weak.sort(key=lambda x: x[1].get('win_rate', 0))
        lines.append("")
        lines.append(C('red', "  Tier D — AVOID (WR < 45%):"))
        for pat, data in weak:
            wwr = data.get('win_rate', 0)
            _, _, wtc = compute_pattern_tier(pat, stats, cfg)
            lines.append(f"    {pat:<30s} | {C(wtc, f'WR: {wwr:.1f}%')} ({data.get('total',0)} sig)")
    rec_setups = []
    for key, data in stats.get('cross', {}).items():
        n = data.get('signals', 0)
        wr = data.get('win_rate', 0)
        amr = data.get('avg_max_r', 0)
        if n >= min_sig:
            confidence = min(1.0, n / 20.0)
            score = wr * confidence + min(amr, 2.0) * 10
            if score > 60:
                rec_setups.append((key, wr, n, amr, score))
    for pat, data in stats.get('patterns', {}).items():
        n = data.get('total', 0)
        wr = data.get('win_rate', 0)
        amr = data.get('avg_max_r', 0)
        if n >= min_sig:
            confidence = min(1.0, n / 30.0)
            score = wr * confidence + min(amr, 2.0) * 10
            if score > 60:
                rec_key = f"{pat} (any session)"
                if not any(pat in k for k, _, _, _, _ in rec_setups):
                    rec_setups.append((rec_key, wr, n, amr, score))
    if rec_setups:
        rec_setups.sort(key=lambda x: x[4], reverse=True)
        lines.append("")
        lines.append(C('green', C('bold', "  RECOMMENDED LIVE SETUPS (score > 60):")))
        for key, wr, n, amr, score in rec_setups[:8]:
            lines.append(f"    {key:<40s} | {C('green', f'WR: {wr:.1f}%')} | {n} sig | {C('bold', f'Score: {score:.1f}')}")
    lines.append(C('cyan', "=" * 70))
    lines.append("")
    for line in lines:
        print(line)


def apply_signal_score_filter(patterns, stats, cfg=None):
    """Filter patterns by min_signal_score. Attaches signal_score to each pattern dict."""
    if cfg is None: cfg = CFG
    min_score = cfg.get('min_signal_score', 0)
    if min_score <= 0 or not stats:
        for p in patterns:
            score = compute_signal_score(p['name'], p['session'], p['direction'], stats, cfg)
            p['signal_score'] = score
        return patterns
    filtered = []
    for p in patterns:
        score = compute_signal_score(p['name'], p['session'], p['direction'], stats, cfg)
        p['signal_score'] = score
        if score is None or score >= min_score:
            filtered.append(p)
    return filtered


# ============================================================
# SCANNER: scan last closed candle on a given timeframe
# ============================================================

def scan_patterns(rates, cfg=None, d1_rates=None, tf_label='H4', htf_atr_rates=None):
    """Scan the last closed candle for all patterns. Returns list of dicts.

    Args:
        htf_atr_rates: Optional higher-timeframe rates (structured array) for ATR
                       calculation. If provided and atr_tf_by_tf maps this TF to a
                       higher TF, ATR is computed from these rates instead of native.
    """
    if cfg is None:
        cfg = CFG
    if len(rates) < 6:
        return []
    ml = [get_candle_metrics(r, cfg) for r in rates]
    idx = len(rates) - 1
    curr = rates[idx]; cm = ml[idx]
    patterns = []
    trend = detect_trend(rates[:idx+1], cfg)

    # Use higher-timeframe ATR if configured and rates provided
    atr_src = get_atr_tf(tf_label, cfg)
    if htf_atr_rates is not None and atr_src != tf_label:
        atr = compute_atr(htf_atr_rates, cfg)
    else:
        atr = compute_atr(rates, cfg)

    _ct = curr['time']
    if isinstance(_ct, (int, float, np.integer, np.floating)):
        hour = datetime.fromtimestamp(int(_ct)).hour
    elif hasattr(_ct, 'hour'):
        hour = _ct.hour
    else:
        hour = int(_ct) % 24
    session = classify_session(hour, cfg)

    vol_confirmed = check_volume_confirmed(rates, idx, cfg)

    # D1 trend filter
    d1_trend = 'N/A'
    if cfg.get('d1_trend_filter', False) and d1_rates is not None and len(d1_rates) >= cfg.get('d1_sma_period', 20):
        d1_closes = [r['close'] for r in d1_rates[-cfg['d1_sma_period']:]]
        d1_sma = np.mean(d1_closes)
        d1_close = d1_rates[-1]['close']
        d1_trend = 'uptrend' if d1_close > d1_sma else ('downtrend' if d1_close < d1_sma else 'ranging')

    # Single-candle patterns
    if detect_doji(cm, cfg):          patterns.append({'name': 'Doji',               'category': 'Neutral',           'direction': 'Neutral'})
    if detect_spinning_top(cm, cfg):  patterns.append({'name': 'Spinning Top',        'category': 'Neutral',           'direction': 'Neutral'})
    if detect_marubozu(cm, cfg):
        d = 'Bullish' if cm['body_sign'] == 1 else 'Bearish'
        patterns.append({'name': f'Marubozu ({d})', 'category': f'{d} Continuation', 'direction': d})
    if detect_hammer(cm, trend, cfg):          patterns.append({'name': 'Hammer',          'category': 'Bullish Reversal', 'direction': 'Bullish'})
    if detect_inverted_hammer(cm, trend, cfg): patterns.append({'name': 'Inverted Hammer', 'category': 'Bullish Reversal', 'direction': 'Bullish'})
    if detect_shooting_star(cm, trend, cfg):   patterns.append({'name': 'Shooting Star',   'category': 'Bearish Reversal', 'direction': 'Bearish'})
    if detect_hanging_man(cm, trend, cfg):     patterns.append({'name': 'Hanging Man',      'category': 'Bearish Reversal', 'direction': 'Bearish'})

    # Two-candle patterns
    if idx >= 1:
        prev = rates[idx-1]; pm = ml[idx-1]
        e = detect_engulfing_full(curr, prev, cm, pm, cfg)
        if e:
            d = 'Bullish' if 'Bullish' in e else 'Bearish'
            patterns.append({'name': e, 'category': f'{d} Reversal', 'direction': d})
        ne = detect_near_engulfing_full(curr, prev, cm, pm, cfg)
        if ne:
            d = 'Bullish' if 'Bullish' in ne else 'Bearish'
            patterns.append({'name': ne, 'category': f'{d} Reversal', 'direction': d})
        h = detect_harami_full(curr, prev, cm, pm, cfg)
        if h:
            d = 'Bullish' if 'Bullish' in h else 'Bearish'
            patterns.append({'name': h, 'category': f'{d} Reversal', 'direction': d})
        tw = detect_tweezer(rates, idx, cfg)
        if tw:
            d = 'Bearish' if 'Tops' in tw else 'Bullish'
            patterns.append({'name': tw, 'category': f'{d} Reversal', 'direction': d})

    # Three-candle patterns
    if detect_morning_star(rates, idx, ml, cfg):         patterns.append({'name': 'Morning Star',        'category': 'Bullish Reversal', 'direction': 'Bullish'})
    if detect_evening_star(rates, idx, ml, cfg):         patterns.append({'name': 'Evening Star',        'category': 'Bearish Reversal', 'direction': 'Bearish'})
    if detect_three_white_soldiers(rates, idx, ml, cfg): patterns.append({'name': 'Three White Soldiers', 'category': 'Bullish Reversal', 'direction': 'Bullish'})
    if detect_three_black_crows(rates, idx, ml, cfg):    patterns.append({'name': 'Three Black Crows',   'category': 'Bearish Reversal', 'direction': 'Bearish'})

    # Five-candle patterns
    if detect_rising_three_methods(rates, idx, ml, cfg):  patterns.append({'name': 'Rising Three Methods',  'category': 'Bullish Continuation', 'direction': 'Bullish'})
    if detect_falling_three_methods(rates, idx, ml, cfg): patterns.append({'name': 'Falling Three Methods', 'category': 'Bearish Continuation', 'direction': 'Bearish'})

    patterns = deduplicate_patterns(patterns, cfg)

    # D1 trend filter
    if cfg.get('d1_trend_filter', False) and d1_trend != 'N/A':
        filtered = []
        for pat in patterns:
            if pat['direction'] == 'Bullish' and d1_trend == 'uptrend':   filtered.append(pat)
            elif pat['direction'] == 'Bearish' and d1_trend == 'downtrend': filtered.append(pat)
            elif pat['direction'] == 'Neutral': filtered.append(pat)
        patterns = filtered

    if cfg.get('volume_filter', False):
        patterns = [p for p in patterns if p['direction'] == 'Neutral' or vol_confirmed]

    sl_mult = cfg['sl_multiplier']
    tp_mult = cfg['tp_multiplier']
    for pat in patterns:
        d = pat['direction']
        if d == 'Bullish':
            pat['sl'] = round(curr['low'] - sl_mult * atr, 5)
            risk = curr['close'] - pat['sl']
            pat['tp'] = round(curr['close'] + risk * (tp_mult / sl_mult), 5)
        elif d == 'Bearish':
            pat['sl'] = round(curr['high'] + sl_mult * atr, 5)
            risk = pat['sl'] - curr['close']
            pat['tp'] = round(curr['close'] - risk * (tp_mult / sl_mult), 5)
        else:
            pat['sl'] = round(curr['low'] - sl_mult * atr, 5)
            risk_bull = curr['close'] - pat['sl']
            pat['tp_long']  = round(curr['close'] + risk_bull * (tp_mult / sl_mult), 5)
            bearish_sl = round(curr['high'] + sl_mult * atr, 5)
            risk_bear = bearish_sl - curr['close']
            pat['tp_short'] = round(curr['close'] - risk_bear * (tp_mult / sl_mult), 5)

        pat['atr'] = round(atr, 5)
        pat['atr_tf'] = atr_src
        pat['session'] = session
        pat['trend'] = trend
        pat['Volume_Confirmed'] = vol_confirmed
        pat['D1_Trend'] = d1_trend
        pat['timeframe'] = tf_label

        entry = compute_entry_details(curr, pat['name'], d, trend, idx, rates, cfg)
        pat.update(entry)

        if d == 'Bullish' and entry['entry_price'] is not None:
            pat['sl_dist_pips'] = round(abs(entry['entry_price'] - pat['sl']) * 10000, 1)
            pat['tp_dist_pips'] = round(abs(pat['tp'] - entry['entry_price']) * 10000, 1)
            pat['rr_ratio']     = round(pat['tp_dist_pips'] / pat['sl_dist_pips'], 2) if pat['sl_dist_pips'] > 0 else None
        elif d == 'Bearish' and entry['entry_price'] is not None:
            pat['sl_dist_pips'] = round(abs(pat['sl'] - entry['entry_price']) * 10000, 1)
            pat['tp_dist_pips'] = round(abs(entry['entry_price'] - pat['tp']) * 10000, 1)
            pat['rr_ratio']     = round(pat['tp_dist_pips'] / pat['sl_dist_pips'], 2) if pat['sl_dist_pips'] > 0 else None
        else:
            pat['sl_dist_pips'] = pat['tp_dist_pips'] = pat['rr_ratio'] = None

    return patterns


def format_pattern_output(candle, patterns, cfg=None, stats=None, tf_label='H4'):
    """Format pattern detection results for display with colour-coded tier,
    historical backtest edge, and signal quality score."""
    if cfg is None: cfg = CFG
    if stats is None: stats = {}
    ct = candle['time']
    if isinstance(ct, (int, float, np.integer, np.floating)):
        ct = datetime.fromtimestamp(int(ct))
    time_str = ct.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ct, 'strftime') else str(ct)
    bt = max(candle['open'], candle['close'])
    bb = min(candle['open'], candle['close'])
    lines = []
    tf_color = {'M5': 'magenta', 'M15': 'blue', 'H1': 'cyan', 'H4': 'yellow', 'D1': 'white'}.get(tf_label, 'cyan')
    lines.append(C(tf_color, "=" * 80))
    lines.append(C('bold', f"  [{tf_label}] CANDLE CLOSE: {time_str}"))
    lines.append(f"  Symbol: {C('yellow', cfg['symbol'])}  |  Timeframe: {C(tf_color, tf_label)}")
    close_str = f"{candle['close']:.5f}"
    lines.append(f"  O: {candle['open']:.5f}  H: {candle['high']:.5f}  L: {candle['low']:.5f}  C: {C('bold', close_str)}")
    lines.append(f"  Body Top: {bt:.5f}  |  Body Bottom: {bb:.5f}  |  Size: {abs(candle['close']-candle['open'])*10000:.1f} pips")
    lines.append(C(tf_color, "=" * 80))
    if not patterns:
        lines.append(C('dim', f"  No patterns detected on {tf_label}."))
        return "\n".join(lines)
    lines.append(C('bold', f"  PATTERNS DETECTED: {len(patterns)}"))
    lines.append("-" * 80)
    min_wr = cfg.get('min_historical_win_rate', 50.0)
    min_sig = cfg.get('min_signals_for_stats', 5)
    for i, pat in enumerate(patterns, 1):
        direction = pat['direction']
        dir_color = 'green' if direction == 'Bullish' else ('red' if direction == 'Bearish' else 'yellow')

        # ── Pre-compute tier, session quality, cross quality ──
        tier_letter, tier_label, tier_color = compute_pattern_tier(pat['name'], stats, cfg)
        sess_quality, sess_q_color, sess_wr, sess_n, sess_amr = compute_session_quality(pat['session'], stats, cfg)
        cross_wr, cross_n, cross_amr, cross_ql, cross_qc = compute_cross_quality(pat['name'], pat['session'], stats, cfg)

        # ── Pattern header with TIER badge ──
        tier_badge = C(tier_color, C('bold', f'[Tier {tier_letter}]'))
        lines.append(f"\n  {C('bold', f'Pattern #{i}:')} {C(dir_color, pat['name'])}  {tier_badge} {C(tier_color, tier_label)}")
        lines.append(f"  TF: {C(tf_color, tf_label)}  |  Category: {pat['category']}  |  Direction: {C(dir_color, direction)}")
        atr_display_tf = pat.get('atr_tf', tf_label)
        atr_label = f"ATR({cfg['atr_period']},{atr_display_tf})" if atr_display_tf != tf_label else f"ATR({cfg['atr_period']})"
        lines.append(f"  Session: {C('cyan', pat['session'])}  |  Trend: {pat['trend']}  |  {atr_label}: {pat['atr']:.5f}")

        vol_val = pat.get('Volume_Confirmed', 'N/A')
        vol_color = 'green' if vol_val is True else ('red' if vol_val is False else 'dim')
        lines.append(f"  Volume Confirmed: {C(vol_color, str(vol_val))}")

        d1_val = pat.get('D1_Trend', 'N/A')
        d1_color = 'green' if d1_val == 'uptrend' else ('red' if d1_val == 'downtrend' else 'yellow')
        lines.append(f"  D1 Trend: {C(d1_color, str(d1_val))}")

        # ── QUALITY SUMMARY LINE (tier + session + cross) ──
        pat_stats = stats.get('patterns', {}).get(pat['name'], {})
        sess_stats = stats.get('sessions', {}).get(pat['session'], {})
        cross_key = f"{pat['name']}|{pat['session']}"
        cross_stats = stats.get('cross', {}).get(cross_key, {})
        pat_wr = pat_stats.get('win_rate', 0)
        pat_n = pat_stats.get('total', 0)
        pat_amr = pat_stats.get('avg_max_r', 0)

        quality_parts = []
        quality_parts.append(f"Tier {tier_letter}:{C(tier_color, tier_label)}")
        if pat_n >= min_sig:
            wr_color = 'green' if pat_wr >= min_wr else ('yellow' if pat_wr >= 45 else 'red')
            quality_parts.append(f"WR {C(wr_color, f'{pat_wr:.1f}%')} ({pat_n})")
        quality_parts.append(f"Sess:{C(sess_q_color, f'{sess_quality}')}")
        if sess_n >= min_sig:
            quality_parts.append(f"SessWR {C(sess_q_color, f'{sess_wr:.1f}%')}")
        if cross_wr is not None:
            quality_parts.append(f"CrossWR {C(cross_qc, f'{cross_wr:.1f}%')} ({cross_n})")
        quality_parts.append(f"AvgR {pat_amr:.2f}R")
        lines.append(f"  {C('bold', 'QUALITY:')} {' | '.join(quality_parts)}")

        lines.append(f"  ENTRY: {C('bold', pat['entry_type'])}  |  Price: {C('bold', str(pat['entry_price']))}  |  Aggressive: {pat['aggressive_entry']:.5f}")
        lines.append(f"  Reason: {pat['entry_reason']}")

        # ── Gather historical probability data ──
        best_tp_pct = None
        best_wr = None
        best_src = ''
        if cross_stats and cross_stats.get('signals', 0) >= min_sig:
            best_tp_pct = cross_stats.get('tp_hit_pct')
            best_wr = cross_stats.get('win_rate')
            best_src = 'cross'
        if best_tp_pct is None and pat_stats and pat_stats.get('total', 0) >= min_sig:
            best_tp_pct = pat_stats.get('tp_hit_pct')
            best_wr = pat_stats.get('win_rate')
            best_src = 'pattern'
        if best_tp_pct is None:
            overall = stats.get('overall', {})
            if overall.get('total_signals', 0) >= min_sig:
                best_tp_pct = overall.get('tp_hit_pct')
                best_wr = overall.get('win_rate')
                best_src = 'overall'

        # ── BUY / SELL / BREAKOUT with probability ──
        if direction == 'Bullish':
            sl_str = C('red', f"SL: {pat['sl']:.5f}")
            tp_str = C('green', f"TP: {pat['tp']:.5f}")
            buy_line = f"  >>> {C('green', C('bold', 'BUY'))}  |  Entry: {pat['entry_price']:.5f}  {sl_str}  {tp_str}"
            if best_tp_pct is not None:
                prob_color = 'green' if best_tp_pct >= 40 else ('yellow' if best_tp_pct >= 30 else 'red')
                buy_line += f"  {C(prob_color, C('bold', f'Prob(TP): {best_tp_pct:.1f}%'))}"
            lines.append(buy_line)
            if pat['sl_dist_pips'] is not None:
                lines.append(f"  >>> SL: {pat['sl_dist_pips']:.1f} pips  |  TP: {pat['tp_dist_pips']:.1f} pips  |  R:R 1:{pat['rr_ratio']:.2f}")
        elif direction == 'Bearish':
            sl_str = C('red', f"SL: {pat['sl']:.5f}")
            tp_str = C('green', f"TP: {pat['tp']:.5f}")
            sell_line = f"  >>> {C('red', C('bold', 'SELL'))} |  Entry: {pat['entry_price']:.5f}  {sl_str}  {tp_str}"
            if best_tp_pct is not None:
                prob_color = 'green' if best_tp_pct >= 40 else ('yellow' if best_tp_pct >= 30 else 'red')
                sell_line += f"  {C(prob_color, C('bold', f'Prob(TP): {best_tp_pct:.1f}%'))}"
            lines.append(sell_line)
            if pat['sl_dist_pips'] is not None:
                lines.append(f"  >>> SL: {pat['sl_dist_pips']:.1f} pips  |  TP: {pat['tp_dist_pips']:.1f} pips  |  R:R 1:{pat['rr_ratio']:.2f}")
        else:
            lines.append(f"  >>> {C('yellow', 'BREAKOUT')}  |  Buy: {pat['body_top']:.5f}  |  Sell: {pat['body_bottom']:.5f}")

        # ── Historical edge ──
        has_edge = False
        if pat_stats and pat_stats.get('total', 0) >= min_sig:
            has_edge = True
            lines.append(f"  {C('bold', 'HISTORICAL EDGE:')}")
            wr = pat_stats.get('win_rate', 0)
            n = pat_stats.get('total', 0)
            amr = pat_stats.get('avg_max_r', 0)
            sl_pct = pat_stats.get('sl_hit_pct', 0)
            tp_pct = pat_stats.get('tp_hit_pct', 0)
            wr_tag = "HIGH" if wr >= min_wr else "LOW"
            wr_tag_color = 'green' if wr >= min_wr else 'red'
            lines.append(f"    {pat['name']}: {C(wr_tag_color, f'WR {wr:.1f}% [{wr_tag}]')} ({n} signals) | Avg Max R: {amr:.2f}R | {C('red', f'SL: {sl_pct:.1f}%')} {C('green', f'TP: {tp_pct:.1f}%')}")
            if sess_stats and sess_stats.get('signals', 0) >= min_sig:
                sess_wr_val = sess_stats.get('win_rate', 0)
                sess_n_val = sess_stats.get('signals', 0)
                lines.append(f"    Session {pat['session']}: {C(sess_q_color, f'{sess_wr_val:.1f}% WR [{sess_quality}]')} ({sess_n_val} signals)")
            if cross_stats and cross_stats.get('signals', 0) >= min_sig:
                cross_wr_val = cross_stats.get('win_rate', 0)
                cross_n_val = cross_stats.get('signals', 0)
                cross_amr_val = cross_stats.get('avg_max_r', 0)
                lines.append(f"    {pat['name']} in {pat['session']}: {C(cross_qc, f'{cross_wr_val:.1f}% WR [{cross_ql}]')} ({cross_n_val} signals) | Avg Max R: {cross_amr_val:.2f}R")

        # ── Signal quality score ──
        score = pat.get('signal_score')
        if score is None:
            score = compute_signal_score(pat['name'], pat['session'], pat['direction'], stats, cfg)
        if score is not None:
            if score >= 65:
                score_label = "STRONG"; score_color = 'green'
            elif score >= 52:
                score_label = "MODERATE"; score_color = 'yellow'
            else:
                score_label = "WEAK"; score_color = 'red'
            lines.append(f"    Signal Score: {C(score_color, C('bold', f'{score:.1f}/100 [{score_label}]'))}")
        elif not has_edge:
            lines.append(C('dim', f"  HISTORICAL EDGE: Insufficient data (<{min_sig} signals)"))

        # Position sizing (standard account — standard lots only)
        risk_pct = cfg.get('risk_percent', 1.0)
        balance  = cfg.get('account_balance', 100000)
        if pat.get('sl_dist_pips') and pat['sl_dist_pips'] > 0:
            risk_amount = balance * risk_pct / 100.0
            pip_value   = 10  # EURUSD std lot
            lots        = round(risk_amount / (pat['sl_dist_pips'] * pip_value), 2)
            lines.append(f"  Position Size ({risk_pct:.1f}% of ${balance:,.0f}): {C('cyan', f'{lots:.2f} lots')}")

        lines.append(f"  {'─' * 40}")
    lines.append(C(tf_color, "=" * 80))
    return "\n".join(lines)


# ============================================================
# MT5 CONNECTION HELPERS
# ============================================================

def connect_mt5(cfg=None):
    """Initialize and log in to MT5 using credentials from CFG (loaded from .env)."""
    if cfg is None: cfg = CFG
    if not _ENV_LOADED:
        log_message(C('yellow', "WARNING: .env file not found — using fallback credentials"), cfg)
    log_message("Initializing MT5 connection...", cfg)
    if not mt5.initialize(path=cfg['mt5_path']):
        log_message(f"MT5 initialization failed: {mt5.last_error()}", cfg)
        return False
    log_message(f"MT5 initialized. Version: {mt5.version()}", cfg)
    if not mt5.login(login=cfg['account'], password=cfg['password'], server=cfg['server']):
        log_message(f"MT5 login failed: {mt5.last_error()}", cfg)
        mt5.shutdown()
        return False
    log_message(f"Connected to {cfg['server']} account {cfg['account']}", cfg)
    return True


def mt5_reconnect(cfg=None):
    """Attempt MT5 reconnection with exponential backoff."""
    if cfg is None: cfg = CFG
    max_attempts  = cfg.get('max_reconnect_attempts', 5)
    base_backoff  = cfg.get('reconnect_backoff_base', 10)
    for attempt in range(1, max_attempts + 1):
        log_message(f"Reconnection attempt {attempt}/{max_attempts}...", cfg)
        try:
            mt5.shutdown()
        except Exception:
            pass
        time.sleep(base_backoff * (2 ** (attempt - 1)))
        if connect_mt5(cfg):
            log_message(f"Reconnection successful on attempt {attempt}.", cfg)
            return True
        log_message(f"Reconnection attempt {attempt} failed.", cfg)
    log_message(f"All {max_attempts} reconnection attempts failed.", cfg)
    return False


def fetch_rates(symbol, tf_label, num_bars, cfg=None):
    """Fetch the most recent `num_bars` bars for the given symbol and TF label."""
    if cfg is None: cfg = CFG
    tf_info = TIMEFRAME_MAP.get(tf_label)
    if tf_info is None:
        log_message(f"Unknown timeframe: {tf_label}", cfg)
        return None
    rates = mt5.copy_rates_from_pos(symbol, tf_info['mt5_tf'], 0, num_bars)
    if rates is None:
        log_message(f"Failed to fetch {tf_label} rates: {mt5.last_error()}", cfg)
    return rates


def fetch_rates_range(symbol, tf_label, date_from, date_to, cfg=None):
    """Fetch bars in a date range for full backtest."""
    if cfg is None: cfg = CFG
    tf_info = TIMEFRAME_MAP.get(tf_label)
    if tf_info is None:
        return None
    warmup_bars = cfg.get('warmup_bars', 30)
    warmup_start = date_from - timedelta(minutes=warmup_bars * tf_info['minutes'] + 24 * 60)
    rates = mt5.copy_rates_range(symbol, tf_info['mt5_tf'], warmup_start, date_to)
    if rates is None or len(rates) == 0:
        print(f"[MT5] No {tf_label} data for {symbol} from {warmup_start} to {date_to}")
        return None
    df = pd.DataFrame(rates)
    df['DATETIME'] = pd.to_datetime(df['time'], unit='s')
    df.sort_values('DATETIME', inplace=True)
    df.reset_index(drop=True, inplace=True)
    df.rename(columns={'open': 'OPEN', 'high': 'HIGH', 'low': 'LOW', 'close': 'CLOSE',
                       'tick_volume': 'TICKVOL', 'real_volume': 'VOL', 'spread': 'SPREAD'}, inplace=True)
    df['DATE'] = df['DATETIME'].dt.strftime('%Y.%m.%d')
    df['TIME'] = df['DATETIME'].dt.strftime('%H:%M:%S')
    df['IN_RANGE'] = (df['DATETIME'] >= date_from) & (df['DATETIME'] <= date_to)
    df['BODY']       = abs(df['CLOSE'] - df['OPEN'])
    df['BODY_SIGN']  = np.where(df['CLOSE'] >= df['OPEN'], 1, -1)
    df['RANGE']      = df['HIGH'] - df['LOW']
    df['UPPER_WICK'] = df['HIGH'] - df[['OPEN', 'CLOSE']].max(axis=1)
    df['LOWER_WICK'] = df[['OPEN', 'CLOSE']].min(axis=1) - df['LOW']
    df['BODY_RATIO'] = np.where(df['RANGE'] > 0, df['BODY'] / df['RANGE'], 0)
    wc = (~df['IN_RANGE']).sum(); ic = df['IN_RANGE'].sum()
    print(f"  [{tf_label}] Fetched {len(df)} bars ({wc} warmup + {ic} in range)")
    return df


# ============================================================
# BACKTEST — DataFrame-based pattern detectors
# ============================================================

def fb_compute_atr(df, period):
    tr = pd.DataFrame({
        'hl': df['HIGH'] - df['LOW'],
        'hc': abs(df['HIGH'] - df['CLOSE'].shift(1)),
        'lc': abs(df['LOW']  - df['CLOSE'].shift(1)),
    }).max(axis=1)
    return tr.rolling(window=period, min_periods=1).mean()


def fb_compute_htf_atr(df, htf_df, atr_period):
    """Compute ATR on a higher-timeframe DataFrame and map it to the lower-TF df.

    For each bar in `df`, finds the most recent HTF bar whose DATETIME <= df bar's
    DATETIME and uses that HTF bar's ATR value. This allows M5/M15 bars to use H1 ATR
    for SL/TP sizing, giving much more realistic stop distances.

    Args:
        df:      Lower-timeframe DataFrame (the one being scanned for patterns).
        htf_df:  Higher-timeframe DataFrame with at least HIGH, LOW, CLOSE, DATETIME columns.
        atr_period: ATR period for the rolling mean.

    Returns:
        pd.Series aligned with df's index, containing the HTF ATR values.
    """
    if htf_df is None or len(htf_df) == 0:
        # Fallback: compute native ATR
        return fb_compute_atr(df, atr_period)

    # Compute ATR on the higher-timeframe
    htf_atr = fb_compute_atr(htf_df, atr_period)
    htf_with_atr = htf_df[['DATETIME']].copy()
    htf_with_atr['ATR'] = htf_atr.values

    # Build an ATR lookup: for each lower-TF bar, find the most recent HTF ATR
    # Use merge_asof for efficient time-based alignment
    result = pd.merge_asof(
        df[['DATETIME']].copy().sort_values('DATETIME'),
        htf_with_atr.sort_values('DATETIME'),
        on='DATETIME',
        direction='backward'   # use the HTF bar at or before the current bar
    )
    # Re-align with original df index (merge_asof sorts by DATETIME)
    result.index = df.index
    return result['ATR']


def fb_detect_trend(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    lookback = cfg.get('trend_lookback', 20)
    if idx < lookback:
        return 'ranging'
    subset = df.iloc[max(0, idx - lookback):idx + 1]
    return detect_trend(subset, cfg)


def fb_detect_doji(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    r = df.iloc[idx]
    return r['RANGE'] > 0 and r['BODY_RATIO'] <= cfg['doji_body_ratio']

def fb_detect_spinning_top(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    r = df.iloc[idx]
    if r['RANGE'] == 0 or r['BODY'] == 0: return False
    if r['BODY_RATIO'] > cfg['spinning_top_body_ratio']: return False
    return r['UPPER_WICK'] >= r['BODY'] and r['LOWER_WICK'] >= r['BODY']

def fb_detect_marubozu(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    r = df.iloc[idx]
    if r['BODY'] == 0: return False
    if r['BODY_RATIO'] < cfg['long_candle_ratio']: return False
    return (r['UPPER_WICK'] <= r['BODY'] * cfg['marubozu_wick_ratio'] and
            r['LOWER_WICK'] <= r['BODY'] * cfg['marubozu_wick_ratio'])

def fb_detect_hammer(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    r = df.iloc[idx]
    if idx < 3: return False
    trend = fb_detect_trend(df, idx, cfg)
    if trend not in ('downtrend', 'ranging'): return False
    if r['BODY'] == 0: return False
    return r['LOWER_WICK'] >= r['BODY'] * cfg['hammer_lower_wick_ratio'] and r['UPPER_WICK'] <= r['BODY'] * cfg['hammer_upper_wick_ratio']

def fb_detect_inverted_hammer(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    r = df.iloc[idx]
    if idx < 3: return False
    trend = fb_detect_trend(df, idx, cfg)
    if trend not in ('downtrend', 'ranging'): return False
    if r['BODY'] == 0: return False
    return r['UPPER_WICK'] >= r['BODY'] * cfg['hammer_lower_wick_ratio'] and r['LOWER_WICK'] <= r['BODY'] * cfg['hammer_upper_wick_ratio']

def fb_detect_shooting_star(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    r = df.iloc[idx]
    if idx < 3: return False
    trend = fb_detect_trend(df, idx, cfg)
    if trend not in ('uptrend', 'ranging'): return False
    if r['BODY'] == 0: return False
    return r['UPPER_WICK'] >= r['BODY'] * cfg['hammer_lower_wick_ratio'] and r['LOWER_WICK'] <= r['BODY'] * cfg['hammer_upper_wick_ratio']

def fb_detect_hanging_man(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    r = df.iloc[idx]
    if idx < 3: return False
    trend = fb_detect_trend(df, idx, cfg)
    if trend not in ('uptrend', 'ranging'): return False
    if r['BODY'] == 0: return False
    return r['LOWER_WICK'] >= r['BODY'] * cfg['hammer_lower_wick_ratio'] and r['UPPER_WICK'] <= r['BODY'] * cfg['hammer_upper_wick_ratio']

def fb_detect_near_engulfing(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    if idx < 1: return None
    c = df.iloc[idx]; p = df.iloc[idx-1]
    if c['BODY'] == 0 or p['BODY'] == 0: return None
    tol = cfg.get('engulf_tolerance_pips', 2.0) * 0.0001
    if c['BODY_SIGN'] == 1 and p['BODY_SIGN'] == -1:
        if not (c['OPEN'] <= p['CLOSE'] and c['CLOSE'] >= p['OPEN']):
            if c['OPEN'] <= p['CLOSE'] + tol and c['CLOSE'] >= p['OPEN'] - tol:
                return 'Near Bullish Engulfing'
    if c['BODY_SIGN'] == -1 and p['BODY_SIGN'] == 1:
        if not (c['OPEN'] >= p['CLOSE'] and c['CLOSE'] <= p['OPEN']):
            if c['OPEN'] >= p['CLOSE'] - tol and c['CLOSE'] <= p['OPEN'] + tol:
                return 'Near Bearish Engulfing'
    return None

def fb_detect_engulfing(df, idx, cfg=None):
    if idx < 1: return None
    c = df.iloc[idx]; p = df.iloc[idx-1]
    if c['BODY'] == 0 or p['BODY'] == 0: return None
    if c['BODY_SIGN'] == 1 and p['BODY_SIGN'] == -1 and c['OPEN'] <= p['CLOSE'] and c['CLOSE'] >= p['OPEN']:
        return 'Bullish Engulfing'
    if c['BODY_SIGN'] == -1 and p['BODY_SIGN'] == 1 and c['OPEN'] >= p['CLOSE'] and c['CLOSE'] <= p['OPEN']:
        return 'Bearish Engulfing'
    return None

def fb_detect_harami(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    if idx < 1: return None
    c = df.iloc[idx]; p = df.iloc[idx-1]
    if c['BODY'] == 0 or p['BODY'] == 0: return None
    if p['BODY_RATIO'] < cfg['long_candle_ratio'] * 0.8: return None
    ch = max(c['OPEN'], c['CLOSE']); cl = min(c['OPEN'], c['CLOSE'])
    ph = max(p['OPEN'], p['CLOSE']); pl = min(p['OPEN'], p['CLOSE'])
    if ch <= ph and cl >= pl:
        if p['BODY_SIGN'] == -1 and c['BODY_SIGN'] == 1: return 'Bullish Harami'
        if p['BODY_SIGN'] == 1 and c['BODY_SIGN'] == -1: return 'Bearish Harami'
    return None

def fb_detect_morning_star(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    if idx < 2: return False
    f, s, t = df.iloc[idx-2], df.iloc[idx-1], df.iloc[idx]
    if f['BODY_SIGN'] != -1 or f['BODY_RATIO'] < cfg['long_candle_ratio']: return False
    if s['BODY_RATIO'] > cfg['small_candle_ratio'] + 0.1: return False
    if t['BODY_SIGN'] != 1 or t['BODY_RATIO'] < cfg['long_candle_ratio'] * 0.7: return False
    return t['CLOSE'] > (f['OPEN'] + f['CLOSE']) / 2

def fb_detect_evening_star(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    if idx < 2: return False
    f, s, t = df.iloc[idx-2], df.iloc[idx-1], df.iloc[idx]
    if f['BODY_SIGN'] != 1 or f['BODY_RATIO'] < cfg['long_candle_ratio']: return False
    if s['BODY_RATIO'] > cfg['small_candle_ratio'] + 0.1: return False
    if t['BODY_SIGN'] != -1 or t['BODY_RATIO'] < cfg['long_candle_ratio'] * 0.7: return False
    return t['CLOSE'] < (f['OPEN'] + f['CLOSE']) / 2

def fb_detect_three_white_soldiers(df, idx, cfg=None):
    if idx < 2: return False
    c1, c2, c3 = df.iloc[idx-2], df.iloc[idx-1], df.iloc[idx]
    if c1['BODY_SIGN'] != 1 or c2['BODY_SIGN'] != 1 or c3['BODY_SIGN'] != 1: return False
    if c1['BODY_RATIO'] < 0.5 or c2['BODY_RATIO'] < 0.5 or c3['BODY_RATIO'] < 0.5: return False
    return c3['CLOSE'] > c2['CLOSE'] > c1['CLOSE']

def fb_detect_three_black_crows(df, idx, cfg=None):
    if idx < 2: return False
    c1, c2, c3 = df.iloc[idx-2], df.iloc[idx-1], df.iloc[idx]
    if c1['BODY_SIGN'] != -1 or c2['BODY_SIGN'] != -1 or c3['BODY_SIGN'] != -1: return False
    if c1['BODY_RATIO'] < 0.5 or c2['BODY_RATIO'] < 0.5 or c3['BODY_RATIO'] < 0.5: return False
    return c3['CLOSE'] < c2['CLOSE'] < c1['CLOSE']

def fb_detect_tweezer(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    if idx < 1: return None
    p = df.iloc[idx-1]; c = df.iloc[idx]
    tol = cfg['tweezer_tolerance_pips'] * 0.0001
    trend = fb_detect_trend(df, idx, cfg)
    if abs(p['HIGH'] - c['HIGH']) <= tol and trend in ('uptrend', 'ranging'): return 'Tweezer Tops'
    if abs(p['LOW']  - c['LOW'])  <= tol and trend in ('downtrend', 'ranging'): return 'Tweezer Bottoms'
    return None

def fb_detect_rising_three_methods(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    if idx < 4: return False
    first = df.iloc[idx-4]; fifth = df.iloc[idx]
    if first['BODY_SIGN'] != 1 or first['BODY_RATIO'] < cfg['long_candle_ratio']: return False
    for i in range(1, 4):
        c = df.iloc[idx-4+i]
        if c['BODY_RATIO'] > cfg['small_candle_ratio'] + 0.15: return False
        if c['HIGH'] > first['HIGH'] or c['LOW'] < first['LOW']: return False
    if fifth['BODY_SIGN'] != 1 or fifth['BODY_RATIO'] < cfg['long_candle_ratio'] * 0.7: return False
    return fifth['CLOSE'] > first['CLOSE']

def fb_detect_falling_three_methods(df, idx, cfg=None):
    if cfg is None: cfg = CFG
    if idx < 4: return False
    first = df.iloc[idx-4]; fifth = df.iloc[idx]
    if first['BODY_SIGN'] != -1 or first['BODY_RATIO'] < cfg['long_candle_ratio']: return False
    for i in range(1, 4):
        c = df.iloc[idx-4+i]
        if c['BODY_RATIO'] > cfg['small_candle_ratio'] + 0.15: return False
        if c['HIGH'] > first['HIGH'] or c['LOW'] < first['LOW']: return False
    if fifth['BODY_SIGN'] != -1 or fifth['BODY_RATIO'] < cfg['long_candle_ratio'] * 0.7: return False
    return fifth['CLOSE'] < first['CLOSE']


# ============================================================
# FORWARD EVALUATION (intra-candle path simulation)
# ============================================================

def simulate_forward_evaluation(df, idx, direction, sl_price, tp_price, r_levels,
                                 forward_candles, cfg=None, fill_price=None):
    """Forward evaluation with intra-candle path simulation to avoid look-ahead bias."""
    if cfg is None: cfg = CFG
    max_r_levels = cfg.get('max_r_levels', 5)
    r_hits = {f'R{r}_Hit': None for r in range(1, max_r_levels+1)}
    sl_hit = tp_hit = False
    highest_r = 0
    outcome = 'Timeout'

    if direction not in ('Bullish', 'Bearish'):
        return {'sl_hit': None, 'tp_hit': None, 'outcome': 'N/A',
                'max_r': None, 'r_hits': r_hits, 'fill_price': None, 'entry_filled': True}

    if idx + 1 >= len(df):
        return {'sl_hit': None, 'tp_hit': None, 'outcome': 'Timeout',
                'max_r': 0, 'r_hits': r_hits, 'fill_price': None, 'entry_filled': False}

    end_idx = min(idx + 1 + forward_candles, len(df))
    future  = df.iloc[idx+1:end_idx]
    if len(future) == 0:
        return {'sl_hit': None, 'tp_hit': None, 'outcome': 'Timeout',
                'max_r': 0, 'r_hits': r_hits, 'fill_price': None, 'entry_filled': False}

    stopped = False
    for _, fc in future.iterrows():
        if stopped:
            break
        fc_high = fc['HIGH']; fc_low = fc['LOW']
        fc_open = fc['OPEN']; fc_close = fc['CLOSE']
        is_bullish_c = fc_close > fc_open
        is_bearish_c = fc_close < fc_open

        sl_in_range = (fc_low  <= sl_price if direction == 'Bullish' else fc_high >= sl_price)
        tp_in_range = (fc_high >= tp_price if direction == 'Bullish' else fc_low  <= tp_price)

        if sl_in_range and tp_in_range:
            sl_hit = tp_hit = True
            if direction == 'Bullish':
                outcome = 'SL_Hit' if is_bullish_c else ('TP_Hit' if is_bearish_c else 'SL_Hit')
            else:
                outcome = 'TP_Hit' if is_bullish_c else ('SL_Hit' if is_bearish_c else 'SL_Hit')
            stopped = True
        elif sl_in_range:
            sl_hit = True; outcome = 'SL_Hit'; stopped = True
        elif tp_in_range:
            tp_hit = True; outcome = 'TP_Hit'
            for r in range(1, max_r_levels+1):
                rv = r_levels.get(f'R{r}')
                if rv is not None:
                    if (direction == 'Bullish' and fc_high >= rv) or (direction == 'Bearish' and fc_low <= rv):
                        r_hits[f'R{r}_Hit'] = True; highest_r = max(highest_r, r)
            stopped = True
        else:
            for r in range(1, max_r_levels+1):
                rv = r_levels.get(f'R{r}')
                if rv is not None:
                    if (direction == 'Bullish' and fc_high >= rv) or (direction == 'Bearish' and fc_low <= rv):
                        r_hits[f'R{r}_Hit'] = True; highest_r = max(highest_r, r)

    for r in range(1, max_r_levels+1):
        if r_hits[f'R{r}_Hit'] is None:
            r_hits[f'R{r}_Hit'] = False

    if not stopped and len(future) > 0:
        final_close = future.iloc[-1]['CLOSE']
        benchmark   = fill_price if fill_price is not None else df.iloc[idx]['CLOSE']
        if direction == 'Bullish':
            outcome = 'Marginal_Win' if final_close > benchmark else 'Marginal_Loss'
        elif direction == 'Bearish':
            outcome = 'Marginal_Win' if final_close < benchmark else 'Marginal_Loss'

    return {'sl_hit': sl_hit, 'tp_hit': tp_hit, 'outcome': outcome,
            'max_r': highest_r, 'r_hits': r_hits, 'fill_price': None, 'entry_filled': True}


# ============================================================
# BACKTEST: detect all patterns on a DataFrame (one timeframe)
# ============================================================

def fb_detect_all_patterns(df, cfg=None, d1_df=None, tf_label='H4', htf_atr_df=None):
    """Run all pattern detectors on in-range candles. Returns list of detection dicts.

    Args:
        htf_atr_df: Optional higher-timeframe DataFrame for ATR calculation.
                    If provided and the atr_tf_by_tf mapping indicates a different
                    ATR source TF, ATR is computed from this DF instead of the native TF.
    """
    if cfg is None: cfg = CFG
    atr_period = cfg.get('atr_period', 14)
    sl_mult    = cfg.get('sl_multiplier', 1.5)
    tp_mult    = cfg.get('tp_multiplier', 1.5)
    forward_candles = get_forward_candles(tf_label, cfg)

    # Determine ATR source: native or higher timeframe
    atr_tf = get_atr_tf(tf_label, cfg)
    if htf_atr_df is not None and atr_tf != tf_label:
        atr = fb_compute_htf_atr(df, htf_atr_df, atr_period)
        print(f"  [{tf_label}] Using {atr_tf} ATR for SL/TP (native {tf_label} ATR too small)")
    else:
        atr = fb_compute_atr(df, atr_period)
    df['ATR'] = atr

    vol_ma_period = cfg.get('volume_ma_period', 20)
    df['VOL_MA']  = df['TICKVOL'].rolling(window=vol_ma_period, min_periods=1).mean()

    detections = []
    in_range   = df.index[df['IN_RANGE']].tolist()
    total      = len(in_range)

    for count, idx in enumerate(in_range, 1):
        if count % 200 == 0 or count == total:
            print(f"  [{tf_label}] Scanning candle {count}/{total} ...", end='\r')

        row   = df.iloc[idx]
        found = []

        if fb_detect_doji(df, idx, cfg):
            found.append({'Pattern': 'Doji', 'Category': 'Neutral', 'Direction': 'Neutral', 'Candles': 1})
        if fb_detect_spinning_top(df, idx, cfg):
            found.append({'Pattern': 'Spinning Top', 'Category': 'Neutral', 'Direction': 'Neutral', 'Candles': 1})
        if fb_detect_marubozu(df, idx, cfg):
            d = 'Bullish' if row['BODY_SIGN'] == 1 else 'Bearish'
            found.append({'Pattern': f'Marubozu ({d})', 'Category': f'{d} Continuation', 'Direction': d, 'Candles': 1})
        if fb_detect_hammer(df, idx, cfg):
            found.append({'Pattern': 'Hammer', 'Category': 'Bullish Reversal', 'Direction': 'Bullish', 'Candles': 1})
        if fb_detect_inverted_hammer(df, idx, cfg):
            found.append({'Pattern': 'Inverted Hammer', 'Category': 'Bullish Reversal', 'Direction': 'Bullish', 'Candles': 1})
        if fb_detect_shooting_star(df, idx, cfg):
            found.append({'Pattern': 'Shooting Star', 'Category': 'Bearish Reversal', 'Direction': 'Bearish', 'Candles': 1})
        if fb_detect_hanging_man(df, idx, cfg):
            found.append({'Pattern': 'Hanging Man', 'Category': 'Bearish Reversal', 'Direction': 'Bearish', 'Candles': 1})

        eng = fb_detect_engulfing(df, idx, cfg)
        if eng:
            d = 'Bullish' if 'Bullish' in eng else 'Bearish'
            found.append({'Pattern': eng, 'Category': f'{d} Reversal', 'Direction': d, 'Candles': 2})

        ne = fb_detect_near_engulfing(df, idx, cfg)
        if ne:
            d = 'Bullish' if 'Bullish' in ne else 'Bearish'
            found.append({'Pattern': ne, 'Category': f'{d} Reversal', 'Direction': d, 'Candles': 2})

        har = fb_detect_harami(df, idx, cfg)
        if har:
            d = 'Bullish' if 'Bullish' in har else 'Bearish'
            found.append({'Pattern': har, 'Category': f'{d} Reversal', 'Direction': d, 'Candles': 2})

        tw = fb_detect_tweezer(df, idx, cfg)
        if tw:
            d = 'Bearish' if 'Tops' in tw else 'Bullish'
            found.append({'Pattern': tw, 'Category': f'{d} Reversal', 'Direction': d, 'Candles': 2})

        if fb_detect_morning_star(df, idx, cfg):
            found.append({'Pattern': 'Morning Star', 'Category': 'Bullish Reversal', 'Direction': 'Bullish', 'Candles': 3})
        if fb_detect_evening_star(df, idx, cfg):
            found.append({'Pattern': 'Evening Star', 'Category': 'Bearish Reversal', 'Direction': 'Bearish', 'Candles': 3})
        if fb_detect_three_white_soldiers(df, idx, cfg):
            found.append({'Pattern': 'Three White Soldiers', 'Category': 'Bullish Reversal', 'Direction': 'Bullish', 'Candles': 3})
        if fb_detect_three_black_crows(df, idx, cfg):
            found.append({'Pattern': 'Three Black Crows', 'Category': 'Bearish Reversal', 'Direction': 'Bearish', 'Candles': 3})
        if fb_detect_rising_three_methods(df, idx, cfg):
            found.append({'Pattern': 'Rising Three Methods', 'Category': 'Bullish Continuation', 'Direction': 'Bullish', 'Candles': 5})
        if fb_detect_falling_three_methods(df, idx, cfg):
            found.append({'Pattern': 'Falling Three Methods', 'Category': 'Bearish Continuation', 'Direction': 'Bearish', 'Candles': 5})

        # Deduplicate
        if cfg.get('deduplicate_signals', True):
            found_dicts = [{'name': f['Pattern'], 'category': f['Category'], 'direction': f['Direction']} for f in found]
            deduped     = deduplicate_patterns(found_dicts, cfg)
            found = [f for f in found if any(f['Pattern'] == d['name'] for d in deduped)]

        # D1 trend filter
        d1_trend = 'N/A'
        if cfg.get('d1_trend_filter', False) and d1_df is not None:
            d1_trend = fb_get_d1_trend_at_time(d1_df, row['DATETIME'], cfg)
            filtered_found = []
            for pat in found:
                if pat['Direction'] == 'Bullish' and d1_trend == 'uptrend':   filtered_found.append(pat)
                elif pat['Direction'] == 'Bearish' and d1_trend == 'downtrend': filtered_found.append(pat)
                elif pat['Direction'] == 'Neutral': filtered_found.append(pat)
            found = filtered_found

        # Volume filter
        if cfg.get('volume_filter', False):
            vol_confirmed = row['TICKVOL'] >= cfg.get('volume_threshold', 1.0) * row['VOL_MA'] if row['VOL_MA'] > 0 else True
            found = [p for p in found if p['Direction'] == 'Neutral' or vol_confirmed]
        else:
            vol_confirmed = True

        for pat in found:
            det = fb_compute_details(df, idx, pat, atr.iloc[idx], sl_mult, tp_mult,
                                     forward_candles, cfg, d1_df, vol_confirmed, tf_label, d1_trend, atr_tf)
            if det is not None:
                detections.append(det)

    print(f"  [{tf_label}] Scanning complete.{' '*30}")
    return detections


def fb_get_d1_trend_at_time(d1_df, h4_datetime, cfg=None):
    """Get D1 trend at a given datetime."""
    d1_bar = d1_df[d1_df['DATETIME'] <= h4_datetime]
    if len(d1_bar) == 0:
        return 'ranging'
    return d1_bar.iloc[-1].get('D1_TREND', 'ranging')


def fb_compute_details(df, idx, pinfo, current_atr, sl_mult, tp_mult,
                       forward_candles, cfg=None, d1_df=None, vol_confirmed=True,
                       tf_label='H4', d1_trend='N/A', atr_tf=None):
    """Compute SL/TP/R-levels + forward evaluation for one pattern occurrence."""
    if cfg is None: cfg = CFG
    row = df.iloc[idx]
    direction   = pinfo['Direction']
    rr_ratio    = tp_mult / sl_mult
    pip_divisor = cfg.get('pip_divisor', 0.0001)
    max_r_levels = cfg.get('max_r_levels', 5)

    if direction == 'Bullish':
        sl   = row['LOW'] - sl_mult * current_atr
        risk = row['CLOSE'] - sl
        tp   = row['CLOSE'] + risk * rr_ratio
    elif direction == 'Bearish':
        sl   = row['HIGH'] + sl_mult * current_atr
        risk = sl - row['CLOSE']
        tp   = row['CLOSE'] - risk * rr_ratio
    else:
        sl_val    = row['LOW'] - sl_mult * current_atr
        risk_bull = row['CLOSE'] - sl_val
        risk_bear = (row['HIGH'] + sl_mult * current_atr) - row['CLOSE']
        sl   = f"{sl_val:.5f}"
        tp   = f"Long:{row['CLOSE']+risk_bull*rr_ratio:.5f}|Short:{row['CLOSE']-risk_bear*rr_ratio:.5f}"
        risk = None

    sl_pips = round(risk / pip_divisor, 1) if risk is not None else None

    r_levels = {}
    if direction == 'Bullish' and risk is not None and risk > 0:
        for r in range(1, max_r_levels+1): r_levels[f'R{r}'] = round(row['CLOSE'] + r * risk, 5)
    elif direction == 'Bearish' and risk is not None and risk > 0:
        for r in range(1, max_r_levels+1): r_levels[f'R{r}'] = round(row['CLOSE'] - r * risk, 5)

    body_top    = max(row['OPEN'], row['CLOSE'])
    body_bottom = min(row['OPEN'], row['CLOSE'])

    if direction == 'Bullish':
        if pinfo['Pattern'] in ('Hammer', 'Inverted Hammer', 'Morning Star', 'Three White Soldiers',
                                'Tweezer Bottoms', 'Rising Three Methods') \
                or 'Bullish Engulfing' in pinfo['Pattern'] or 'Bullish Harami' in pinfo['Pattern']:
            entry_type = 'Buy Stop'; entry_price = round(body_top, 5)
        elif 'Marubozu' in pinfo['Pattern'] and 'Bullish' in pinfo['Pattern']:
            entry_type = 'Market Buy'; entry_price = round(row['CLOSE'], 5)
        else:
            entry_type = 'Buy Stop'; entry_price = round(body_top, 5)
    elif direction == 'Bearish':
        if pinfo['Pattern'] in ('Evening Star', 'Shooting Star', 'Hanging Man', 'Three Black Crows',
                                'Falling Three Methods', 'Tweezer Tops') \
                or 'Bearish Engulfing' in pinfo['Pattern'] or 'Bearish Harami' in pinfo['Pattern']:
            entry_type = 'Sell Stop'; entry_price = round(body_bottom, 5)
        elif 'Marubozu' in pinfo['Pattern'] and 'Bearish' in pinfo['Pattern']:
            entry_type = 'Market Sell'; entry_price = round(row['CLOSE'], 5)
        else:
            entry_type = 'Sell Stop'; entry_price = round(body_bottom, 5)
    else:
        entry_type = 'Breakout'; entry_price = None

    # Entry verification
    entry_filled = True; fill_price = entry_price; no_fill = False; gap_fill = False
    if cfg.get('verify_entry', True) and direction in ('Bullish', 'Bearish') and idx + 1 < len(df):
        next_c = df.iloc[idx+1]
        if entry_type == 'Buy Stop':
            if next_c['HIGH'] >= entry_price:
                fill_price = round(max(next_c['OPEN'], entry_price), 5)
                gap_fill   = next_c['OPEN'] > entry_price
            else:
                entry_filled = False; no_fill = True
        elif entry_type == 'Sell Stop':
            if next_c['LOW'] <= entry_price:
                fill_price = round(min(next_c['OPEN'], entry_price), 5)
                gap_fill   = next_c['OPEN'] < entry_price
            else:
                entry_filled = False; no_fill = True
        elif entry_type in ('Market Buy', 'Market Sell'):
            fill_price = round(df.iloc[idx+1]['OPEN'], 5)

    # Recalculate risk from fill price if verified
    if cfg.get('verify_entry', True) and fill_price is not None and entry_filled and direction in ('Bullish', 'Bearish'):
        if direction == 'Bullish' and isinstance(sl, float):
            risk = fill_price - sl
            if risk > 0:
                tp = fill_price + risk * rr_ratio
                for r in range(1, max_r_levels+1): r_levels[f'R{r}'] = round(fill_price + r * risk, 5)
                sl_pips = round(risk / pip_divisor, 1)
        elif direction == 'Bearish' and isinstance(sl, float):
            risk = sl - fill_price
            if risk > 0:
                tp = fill_price - risk * rr_ratio
                for r in range(1, max_r_levels+1): r_levels[f'R{r}'] = round(fill_price - r * risk, 5)
                sl_pips = round(risk / pip_divisor, 1)

    # Forward evaluation
    prediction_success = sl_hit_result = tp_hit_result = None
    outcome = 'Timeout'; max_r = 0
    r_hits = {f'R{r}_Hit': None for r in range(1, max_r_levels+1)}

    if no_fill:
        outcome = 'No_Fill'; entry_filled = False
    elif direction in ('Bullish', 'Bearish') and isinstance(sl, float) and idx + 1 < len(df):
        fwd = simulate_forward_evaluation(df, idx, direction, sl, tp, r_levels,
                                          forward_candles, cfg, fill_price=fill_price)
        sl_hit_result = fwd['sl_hit']; tp_hit_result = fwd['tp_hit']
        outcome = fwd['outcome']; max_r = fwd['max_r']; r_hits = fwd['r_hits']
        prediction_success = (True  if outcome in ('TP_Hit', 'Marginal_Win') else
                              False if outcome in ('SL_Hit', 'Marginal_Loss', 'No_Fill') else None)

    hour    = row['DATETIME'].hour
    session = classify_session(hour, cfg)
    trend   = fb_detect_trend(df, idx, cfg)

    result = {
        'Timeframe': tf_label,
        'DateTime': row['DATETIME'], 'Date': row['DATE'], 'Time': row['TIME'],
        'Pattern': pinfo['Pattern'], 'Category': pinfo['Category'], 'Direction': direction,
        'Session': session, 'Trend_Context': trend, 'D1_Trend': d1_trend,
        'Open': row['OPEN'], 'High': row['HIGH'], 'Low': row['LOW'], 'Close': row['CLOSE'],
        'ATR': round(current_atr, 5) if not pd.isna(current_atr) else None,
        'ATR_TF': atr_tf or tf_label,
        'SL': round(sl, 5) if isinstance(sl, float) else sl,
        'TP': round(tp, 5) if isinstance(tp, float) else tp,
        'SL_Pips': sl_pips,
        'Risk_1R': round(risk, 5) if risk is not None else None,
        'TP_R_Multiple': round(rr_ratio, 2),
        'Entry_Type': entry_type, 'Entry_Price': entry_price,
        'Fill_Price': fill_price, 'Entry_Filled': entry_filled, 'Gap_Fill': gap_fill,
        'Outcome': outcome, 'Max_R': max_r,
        'Prediction_Success': prediction_success,
        'SL_Hit': sl_hit_result, 'TP_Hit': tp_hit_result,
        'Volume_Confirmed': vol_confirmed,
        'Candles_in_Pattern': pinfo['Candles'],
        'Forward_Candles': forward_candles,
    }
    for r in range(1, max_r_levels+1):
        rk = f'R{r}'
        result[rk] = r_levels.get(rk)
        result[f'R{r}_Hit'] = r_hits.get(f'R{r}_Hit')
        result[f'R{r}_Pips'] = (round(r * risk / pip_divisor, 1)
                                if r_levels.get(rk) is not None and risk is not None else None)
    return result


# ============================================================
# BACKTEST REPORT GENERATOR
# ============================================================

def fb_generate_report(detections, df, symbol, tf_label, cfg=None):
    """Generate full text report for one timeframe backtest."""
    if cfg is None: cfg = CFG
    max_r_levels    = cfg.get('max_r_levels', 5)
    forward_candles = get_forward_candles(tf_label, cfg)
    tf_minutes      = TIMEFRAME_MAP.get(tf_label, {}).get('minutes', 240)

    lines = []
    L = lines.append
    L("=" * 120)
    L(f"{symbol} [{tf_label}] PRICE ACTION PATTERN BACKTEST REPORT")
    L("=" * 120)
    L(f"Timeframe         : {tf_label}  ({tf_minutes} min candles)")
    L(f"Data Period       : {df.loc[df['IN_RANGE'],'DATE'].iloc[0]} to {df.loc[df['IN_RANGE'],'DATE'].iloc[-1]}")
    L(f"Total Candles     : {df['IN_RANGE'].sum()}")
    L(f"Total Detections  : {len(detections)}")
    L(f"ATR Period        : {cfg.get('atr_period', 14)}")
    atr_src = get_atr_tf(tf_label, cfg)
    if atr_src != tf_label:
        L(f"ATR Source TF     : {atr_src} (higher-TF ATR for wider SL/TP)")
    else:
        L(f"ATR Source TF     : {tf_label} (native)")
    L(f"SL Multiplier     : {cfg.get('sl_multiplier', 1.5)} x ATR")
    L(f"TP R:R            : 1:{cfg.get('tp_multiplier', 1.5)/cfg.get('sl_multiplier', 1.5):.1f}")
    L(f"Forward Eval      : {forward_candles} candles = {forward_candles * tf_minutes // 60:.0f} hours")
    L(f"D1 Trend Filter   : {cfg.get('d1_trend_filter', False)}")
    L(f"Volume Filter     : {cfg.get('volume_filter', False)}")
    L(f"Verify Entry      : {cfg.get('verify_entry', True)}")
    L(f"Deduplicate       : {cfg.get('deduplicate_signals', True)}")
    L("")

    if not detections:
        L("No patterns detected.")
        return "\n".join(lines)

    det_df     = pd.DataFrame(detections)
    directional = det_df[det_df['Direction'] != 'Neutral']

    def bc(s):
        s_ = int((s == True).sum()); f_ = int((s == False).sum())
        return s_, f_, round(s_ / (s_ + f_) * 100, 1) if (s_ + f_) > 0 else 0

    L("-" * 120); L("SECTION 1: PATTERN FREQUENCY"); L("-" * 120)
    for pat, cnt in det_df['Pattern'].value_counts().items():
        L(f"  {pat:30s} | {det_df[det_df['Pattern']==pat]['Direction'].iloc[0]:10s} | Count: {cnt}")

    L(""); L("-" * 120); L("SECTION 2: SESSION DISTRIBUTION"); L("-" * 120)
    for sess, cnt in det_df['Session'].value_counts().items():
        L(f"  {sess:25s} | {cnt:4d} | {cnt/len(det_df)*100:.1f}%")

    L(""); L("-" * 120); L("SECTION 3: WIN RATE BY PATTERN"); L("-" * 120)
    hdr = f"  {'Pattern':30s} | {'Total':>6s} | {'Win':>5s} | {'Loss':>5s} | {'WR%':>6s} | {'SL%':>6s} | {'TP%':>6s} | {'AvgSL pips':>11s}"
    L(hdr); L("  " + "-" * (len(hdr)-2))
    for pat in det_df['Pattern'].unique():
        ds = det_df[(det_df['Pattern'] == pat) & (det_df['Direction'] != 'Neutral')]
        total = len(det_df[det_df['Pattern'] == pat])
        if len(ds) > 0:
            s, f_, wr = bc(ds['Prediction_Success'])
            slp = round((ds['SL_Hit'] == True).sum() / len(ds) * 100, 1)
            tpp = round((ds['TP_Hit'] == True).sum() / len(ds) * 100, 1)
            asp = ds['SL_Pips'].dropna().mean()
        else:
            s = f_ = 0; wr = slp = tpp = 0; asp = float('nan')
        L(f"  {pat:30s} | {total:6d} | {s:5d} | {f_:5d} | {wr:5.1f}% | {slp:5.1f}% | {tpp:5.1f}% | {asp:.1f}" if not pd.isna(asp) else
          f"  {pat:30s} | {total:6d} | {s:5d} | {f_:5d} | {wr:5.1f}% | {slp:5.1f}% | {tpp:5.1f}% | N/A")

    L(""); L("-" * 120); L("SECTION 4: OUTCOME BREAKDOWN"); L("-" * 120)
    for outcome_name in ['TP_Hit', 'SL_Hit', 'Marginal_Win', 'Marginal_Loss', 'Timeout', 'No_Fill']:
        cnt = int((directional['Outcome'] == outcome_name).sum()) if len(directional) > 0 else 0
        pct = round(cnt / len(directional) * 100, 1) if len(directional) > 0 else 0
        L(f"  {outcome_name:20s} | {cnt:6d} | {pct:5.1f}%")

    L(""); L("-" * 120); L("SECTION 5: R-LEVEL HIT RATES BY PATTERN"); L("-" * 120)
    rh = f"  {'Pattern':30s} | {'Sigs':>5s}" + ''.join([f" | {'R'+str(r)+'%':>6s}" for r in range(1, max_r_levels+1)]) + " | AvgMaxR"
    L(rh); L("  " + "-" * (len(rh)-2))
    for pat in det_df['Pattern'].unique():
        ds = det_df[(det_df['Pattern'] == pat) & (det_df['Direction'] != 'Neutral')]
        if len(ds) == 0: continue
        rp = [f"  {pat:30s} | {len(ds):5d}"]
        for r in range(1, max_r_levels+1):
            col = f'R{r}_Hit'
            if col in ds.columns:
                hc = int((ds[col] == True).sum()); ec = int((ds[col].notna()).sum())
                rp.append(f" | {round(hc/ec*100, 0) if ec > 0 else 0:5.0f}%")
            else:
                rp.append(f" | {'N/A':>6s}")
        amr = ds['Max_R'].dropna().mean()
        rp.append(f" | {amr:.2f}" if not pd.isna(amr) else " | N/A")
        L(''.join(rp))

    L(""); L("-" * 120); L("SECTION 6: WIN RATE BY SESSION"); L("-" * 120)
    for sess in directional['Session'].unique() if len(directional) > 0 else []:
        sd = directional[directional['Session'] == sess]
        if len(sd) == 0: continue
        s, f_, wr = bc(sd['Prediction_Success'])
        amr = sd['Max_R'].dropna().mean()
        L(f"  {sess:25s} | Signals: {len(sd):4d} | WR: {wr:.1f}% | AvgMaxR: {amr:.2f}R")

    L(""); L("-" * 120); L("SECTION 7: KEY STATISTICS"); L("-" * 120)
    td = len(directional)
    if td > 0:
        s, f_, owr = bc(directional['Prediction_Success'])
        L(f"  Total directional signals : {td}")
        L(f"  Overall win rate          : {owr:.1f}%")
        L(f"  SL hit rate               : {round((directional['SL_Hit']==True).sum()/td*100, 1):.1f}%")
        L(f"  TP hit rate               : {round((directional['TP_Hit']==True).sum()/td*100, 1):.1f}%")
        L(f"  Avg SL pips               : {directional['SL_Pips'].dropna().mean():.1f}")
        L(f"  Avg Max R                 : {directional['Max_R'].dropna().mean():.2f}R")
        for r in range(1, max_r_levels+1):
            col = f'R{r}_Hit'
            if col in directional.columns:
                hc = int((directional[col] == True).sum()); ec = int(directional[col].notna().sum())
                L(f"  R{r} hit rate              : {round(hc/ec*100,1) if ec>0 else 0:.1f}%")

    L(""); L("=" * 120)
    return "\n".join(lines)


# ============================================================
# MODE 1: LIVE MULTI-TIMEFRAME SCANNER
# ============================================================

def run_scanner(cfg=None):
    """Live scanner loop — monitors all active timeframes for new candle closes."""
    if cfg is None: cfg = CFG
    active_tfs = cfg.get('active_timeframes', ['M5', 'M15', 'H1', 'H4', 'D1'])
    symbol     = cfg['symbol']

    log_message(C('cyan', '=' * 70), cfg)
    log_message(C('bold', f"  {symbol} MULTI-TIMEFRAME PATTERN SCANNER v6 — STARTING"), cfg)
    log_message(C('cyan', '=' * 70), cfg)
    log_message(f"Active timeframes: {C('yellow', ', '.join(active_tfs))}", cfg)
    sl_str = f"{cfg['sl_multiplier']}x ATR"
    log_message(f"SL: {C('red', sl_str)} | TP R:R = 1:{cfg['tp_multiplier']/cfg['sl_multiplier']:.1f}", cfg)

    # Show ATR source per TF
    atr_map_display = []
    for tf in active_tfs:
        atr_src = get_atr_tf(tf, cfg)
        atr_map_display.append(f"{tf}→{atr_src}" if atr_src != tf else tf)
    log_message(f"ATR Source: {', '.join(atr_map_display)}", cfg)

    if cfg.get('d1_trend_filter', False):
        log_message(f"D1 Trend Filter: {C('green', 'ENABLED')} (SMA {cfg['d1_sma_period']})", cfg)
    if cfg.get('volume_filter', False):
        log_message(f"Volume Filter: {C('green', 'ENABLED')} ({cfg['volume_threshold']}x avg)", cfg)

    # Load backtest stats for historical edge display
    stats = load_latest_backtest_stats(cfg=cfg)
    stats_last_refresh = datetime.now()
    if stats.get('overall', {}).get('total_signals', 0) > 0:
        owr = stats['overall'].get('win_rate', 0)
        on = stats['overall'].get('total_signals', 0)
        log_message(f"Backtest stats loaded: Overall WR {owr:.1f}% ({on} signals)", cfg)
    else:
        log_message("No backtest stats found. Run fullbacktest first for historical edge data.", cfg)

    # Print dashboard on start
    if cfg.get('show_dashboard_on_start', True) and stats.get('overall', {}).get('total_signals', 0) > 0:
        print_top_setups(stats, cfg)

    if not connect_mt5(cfg):
        return

    # Track last candle time per timeframe
    last_candle_time = {tf: None for tf in active_tfs}
    d1_rates_cache   = None

    try:
        while True:
            try:
                # Refresh D1 data periodically for trend filter
                if cfg.get('d1_trend_filter', False):
                    d1_rates_cache = fetch_rates(symbol, 'D1', cfg.get('bars_to_fetch', 50), cfg)

                # Auto-refresh stats cache periodically
                if (datetime.now() - stats_last_refresh).total_seconds() > cfg.get('stats_cache_hours', 4) * 3600:
                    stats = load_latest_backtest_stats(cfg=cfg)
                    stats_last_refresh = datetime.now()
                    if stats.get('overall', {}).get('total_signals', 0) > 0:
                        log_message(f"Stats refreshed: Overall WR {stats['overall'].get('win_rate',0):.1f}%", cfg)

                # Fetch higher-timeframe ATR rates once per loop iteration
                htf_atr_rates_cache = {}  # tf_label → rates
                atr_tfs_needed = set()
                for tf in active_tfs:
                    atr_src = get_atr_tf(tf, cfg)
                    if atr_src != tf:
                        atr_tfs_needed.add(atr_src)
                for atr_src in atr_tfs_needed:
                    htf_rates = fetch_rates(symbol, atr_src, cfg.get('bars_to_fetch', 50), cfg)
                    if htf_rates is not None:
                        htf_atr_rates_cache[atr_src] = htf_rates

                for tf_label in active_tfs:
                    tf_info      = TIMEFRAME_MAP[tf_label]
                    poll_interval = cfg.get('poll_interval_by_tf', {}).get(tf_label, 30)
                    rates        = fetch_rates(symbol, tf_label, cfg.get('bars_to_fetch', 50), cfg)
                    if rates is None:
                        continue

                    # Resolve ATR source for this TF
                    atr_src = get_atr_tf(tf_label, cfg)
                    htf_atr_rates = htf_atr_rates_cache.get(atr_src) if atr_src != tf_label else None

                    bar_time = rates[-1]['time']
                    if isinstance(bar_time, (int, float, np.integer, np.floating)):
                        bar_time = datetime.fromtimestamp(int(bar_time))

                    if last_candle_time[tf_label] is None:
                        last_candle_time[tf_label] = bar_time
                        # Scan the most recent closed candle on startup
                        if len(rates) >= 2:
                            pats = scan_patterns(list(rates[:-1]), cfg, d1_rates_cache, tf_label, htf_atr_rates)
                            pats = apply_signal_score_filter(pats, stats, cfg)
                            log_message(format_pattern_output(rates[-2], pats, cfg, stats, tf_label), cfg)
                        continue

                    if bar_time != last_candle_time[tf_label]:
                        next_close = bar_time + timedelta(minutes=tf_info['minutes'])
                        log_message(
                            C('bold', C('yellow',
                              f"\nNEW {tf_label} CANDLE CLOSED! | Next: {next_close.strftime('%Y-%m-%d %H:%M')}"
                            )), cfg
                        )
                        pats = scan_patterns(list(rates[:-1]), cfg, d1_rates_cache, tf_label, htf_atr_rates)
                        pats = apply_signal_score_filter(pats, stats, cfg)
                        output = format_pattern_output(rates[-2], pats, cfg, stats, tf_label)
                        log_message(output, cfg)

                        # Write alert file for signals with patterns
                        if pats:
                            try:
                                _ts = rates[-2]['time']
                                if isinstance(_ts, (int, float, np.integer, np.floating)):
                                    _ts = datetime.fromtimestamp(int(_ts))
                                fname = f"alert_{tf_label}_{_ts.strftime('%Y%m%d_%H%M%S')}.txt"
                                with open(os.path.join(_LOG_DIR, fname), "w", encoding='utf-8') as f:
                                    f.write(f"SIGNAL ALERT [{tf_label}] — {_ts}\n\n" + output)
                            except Exception:
                                pass

                        last_candle_time[tf_label] = bar_time

                time.sleep(min(cfg.get('poll_interval_by_tf', {}).get(tf, 30) for tf in active_tfs))

            except Exception as e:
                log_message(f"Scanner iteration error: {e}", cfg)
                if not mt5_reconnect(cfg):
                    break

    except KeyboardInterrupt:
        log_message("\nScanner stopped by user (Ctrl+C)", cfg)
    finally:
        try: mt5.shutdown()
        except Exception: pass
        log_message("MT5 connection closed.", cfg)


# ============================================================
# MODE 2: ONE-SHOT SCAN (all active timeframes)
# ============================================================

def run_single_scan(cfg=None):
    """Single scan of the latest closed candle on all active timeframes."""
    if cfg is None: cfg = CFG
    active_tfs = cfg.get('active_timeframes', ['M5', 'M15', 'H1', 'H4', 'D1'])
    log_message(f"Running single scan on: {', '.join(active_tfs)}", cfg)

    # Load backtest stats
    stats = load_latest_backtest_stats(cfg=cfg)
    if stats.get('overall', {}).get('total_signals', 0) > 0:
        owr = stats['overall'].get('win_rate', 0)
        on = stats['overall'].get('total_signals', 0)
        log_message(f"Backtest stats loaded: Overall WR {owr:.1f}% ({on} signals)", cfg)
    else:
        log_message("No backtest stats found. Run fullbacktest first for historical edge data.", cfg)

    # Print dashboard
    if cfg.get('show_dashboard_on_start', True) and stats.get('overall', {}).get('total_signals', 0) > 0:
        print_top_setups(stats, cfg)

    if not connect_mt5(cfg):
        return

    d1_rates = None
    if cfg.get('d1_trend_filter', False):
        d1_rates = fetch_rates(cfg['symbol'], 'D1', cfg.get('bars_to_fetch', 50), cfg)

    # Pre-fetch higher-timeframe ATR rates
    htf_atr_rates_cache = {}
    atr_tfs_needed = set()
    for tf in active_tfs:
        atr_src = get_atr_tf(tf, cfg)
        if atr_src != tf:
            atr_tfs_needed.add(atr_src)
    for atr_src in atr_tfs_needed:
        htf_rates = fetch_rates(cfg['symbol'], atr_src, cfg.get('bars_to_fetch', 50), cfg)
        if htf_rates is not None:
            htf_atr_rates_cache[atr_src] = htf_rates

    for tf_label in active_tfs:
        rates = fetch_rates(cfg['symbol'], tf_label, cfg.get('bars_to_fetch', 50), cfg)
        if rates is None:
            log_message(f"No data for {tf_label}.", cfg)
            continue
        closed   = rates[-2] if len(rates) >= 2 else rates[-1]
        scan_src = list(rates[:-1]) if len(rates) >= 2 else list(rates)
        # Resolve ATR source for this TF
        atr_src = get_atr_tf(tf_label, cfg)
        htf_atr_rates = htf_atr_rates_cache.get(atr_src) if atr_src != tf_label else None
        pats     = scan_patterns(scan_src, cfg, d1_rates, tf_label, htf_atr_rates)
        pats     = apply_signal_score_filter(pats, stats, cfg)
        log_message(format_pattern_output(closed, pats, cfg, stats, tf_label), cfg)

    try: mt5.shutdown()
    except Exception: pass
    log_message("Single scan complete.", cfg)


# ============================================================
# MODE 3: QUICK BACKTEST (N recent bars, single TF)
# ============================================================

def run_quick_backtest(num_bars=500, cfg=None):
    """Quick backtest over N recent bars. Supports all active timeframes."""
    if cfg is None: cfg = CFG
    active_tfs = cfg.get('active_timeframes', ['H4'])
    symbol     = cfg['symbol']
    log_message(f"Quick backtest: {num_bars} bars on {', '.join(active_tfs)}", cfg)
    if not connect_mt5(cfg):
        return

    # Pre-fetch higher-timeframe ATR rates
    htf_atr_rates_cache = {}
    atr_tfs_needed = set()
    for tf in active_tfs:
        atr_src = get_atr_tf(tf, cfg)
        if atr_src != tf:
            atr_tfs_needed.add(atr_src)
    for atr_src in atr_tfs_needed:
        htf_rates = fetch_rates(symbol, atr_src, num_bars, cfg)
        if htf_rates is not None:
            htf_atr_rates_cache[atr_src] = htf_rates

    for tf_label in active_tfs:
        log_message(f"\n--- [{tf_label}] ---", cfg)
        rates = fetch_rates(symbol, tf_label, num_bars, cfg)
        if rates is None:
            log_message(f"No data for {tf_label}.", cfg)
            continue

        # Resolve ATR source
        atr_src = get_atr_tf(tf_label, cfg)
        htf_atr_rates = htf_atr_rates_cache.get(atr_src) if atr_src != tf_label else None

        rates_list     = list(rates)
        total_patterns = 0
        pattern_counts = {}
        all_detections = []

        for i in range(5, len(rates_list) - 1):
            subset = rates_list[:i+1]
            pats   = scan_patterns(subset, cfg, tf_label=tf_label, htf_atr_rates=htf_atr_rates)
            if pats:
                candle = rates_list[i]
                total_patterns += len(pats)
                for p in pats:
                    pattern_counts[p['name']] = pattern_counts.get(p['name'], 0) + 1
                    ct = candle['time']
                    if isinstance(ct, (int, float, np.integer, np.floating)):
                        ct = datetime.fromtimestamp(ct)
                    all_detections.append({
                        'Timeframe': tf_label,
                        'DateTime': ct, 'Pattern': p['name'],
                        'Direction': p['direction'], 'Session': p['session'],
                        'Open': candle['open'], 'High': candle['high'],
                        'Low': candle['low'], 'Close': candle['close'],
                        'Entry_Type': p.get('entry_type'), 'Entry_Price': p.get('entry_price'),
                        'ATR': p.get('atr'), 'SL': p.get('sl'), 'TP': p.get('tp'),
                        'SL_Dist_Pips': p.get('sl_dist_pips'),
                    })

        log_message(f"[{tf_label}] Total patterns: {total_patterns}", cfg)
        for name, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
            log_message(f"  {name:35s}: {count}", cfg)

        if all_detections:
            csv_path = os.path.join(_LOG_DIR, f"quick_backtest_{symbol}_{tf_label}.csv")
            pd.DataFrame(all_detections).to_csv(csv_path, index=False)
            log_message(f"  → {csv_path}", cfg)

    try: mt5.shutdown()
    except Exception: pass
    log_message("\nQuick backtest complete.", cfg)


# ============================================================
# MODE 4: FULL DATE-RANGED BACKTEST (all active timeframes)
# ============================================================

def run_full_backtest(args, cfg=None):
    """Full backtest with date range, R-levels, forward evaluation across all active TFs."""
    if cfg is None: cfg = CFG
    active_tfs = cfg.get('active_timeframes', ['M5', 'M15', 'H1', 'H4', 'D1'])
    symbol     = args.symbol
    date_from  = datetime.strptime(args.date_from, "%Y-%m-%d")
    date_to    = datetime.strptime(args.date_to,   "%Y-%m-%d") + timedelta(days=1) - timedelta(seconds=1)
    out_dir    = args.output

    print("=" * 70)
    print(f"  {symbol} MULTI-TIMEFRAME BACKTESTER v6")
    print("=" * 70)
    print(f"  Timeframes : {', '.join(active_tfs)}")
    print(f"  From       : {args.date_from}")
    print(f"  To         : {args.date_to}")
    print(f"  ATR        : {cfg.get('atr_period', 14)}")
    # Show ATR source per TF
    atr_map_display = []
    for tf in active_tfs:
        atr_src = get_atr_tf(tf, cfg)
        atr_map_display.append(f"{tf}→{atr_src}" if atr_src != tf else tf)
    print(f"  ATR Source : {', '.join(atr_map_display)}")
    print(f"  SL/TP      : {cfg.get('sl_multiplier', 1.5)}x / {cfg.get('tp_multiplier', 1.5)}x ATR")
    print(f"  Output     : {out_dir}")
    print()

    print("[1] Connecting to MT5...")
    if not connect_mt5(cfg):
        print("FATAL: Could not connect to MT5."); sys.exit(1)

    # Fetch D1 data for trend filter (shared across TFs if needed)
    d1_df_cache = None
    if cfg.get('d1_trend_filter', False):
        print("[2] Fetching D1 data for trend filter...")
        d1_df_cache = fetch_rates_range(symbol, 'D1', date_from, date_to, cfg)
        if d1_df_cache is not None:
            d1_df_cache['D1_SMA']   = d1_df_cache['CLOSE'].rolling(window=cfg.get('d1_sma_period', 20), min_periods=1).mean()
            d1_df_cache['D1_TREND'] = np.where(d1_df_cache['CLOSE'] > d1_df_cache['D1_SMA'], 'uptrend',
                                       np.where(d1_df_cache['CLOSE'] < d1_df_cache['D1_SMA'], 'downtrend', 'ranging'))

    # Pre-fetch higher-timeframe data for ATR calculation
    # For example, if M5 uses H1 ATR, fetch H1 data once and reuse it
    htf_atr_cache = {}  # tf_label → DataFrame
    atr_tf_needed = set()
    for tf in active_tfs:
        atr_src = get_atr_tf(tf, cfg)
        if atr_src != tf:
            atr_tf_needed.add(atr_src)
    for atr_src in atr_tf_needed:
        print(f"[ATR] Fetching {atr_src} data for higher-timeframe ATR...")
        htf_df = fetch_rates_range(symbol, atr_src, date_from, date_to, cfg)
        if htf_df is not None:
            htf_atr_cache[atr_src] = htf_df
            print(f"  [ATR] {atr_src} data ready ({len(htf_df)} bars)")
        else:
            print(f"  [ATR] WARNING: Could not fetch {atr_src} data — will fall back to native ATR")

    all_results = {}  # tf_label → list of detection dicts

    for tf_label in active_tfs:
        print(f"\n[TF] Fetching {tf_label} data...")
        df = fetch_rates_range(symbol, tf_label, date_from, date_to, cfg)
        if df is None:
            print(f"  [{tf_label}] No data — skipping.")
            continue

        # Use D1 data as trend filter for all TFs below D1
        d1_for_filter = None if tf_label == 'D1' else d1_df_cache

        # Resolve the ATR source TF and its DataFrame
        atr_src = get_atr_tf(tf_label, cfg)
        htf_atr_df = htf_atr_cache.get(atr_src) if atr_src != tf_label else None

        print(f"  [{tf_label}] Running pattern detection...")
        detections = fb_detect_all_patterns(df, cfg, d1_for_filter, tf_label, htf_atr_df)
        all_results[tf_label] = detections
        print(f"  [{tf_label}] {len(detections)} pattern detections")

        if not detections:
            print(f"  [{tf_label}] No patterns found.")
            continue

        os.makedirs(out_dir, exist_ok=True)
        tag       = f"{symbol}_{tf_label}_{args.date_from}_to_{args.date_to}"
        det_csv   = os.path.join(out_dir, f"{tag}_detections.csv")
        sum_csv   = os.path.join(out_dir, f"{tag}_pattern_summary.csv")
        sess_csv  = os.path.join(out_dir, f"{tag}_session_summary.csv")
        rpt_file  = os.path.join(out_dir, f"{tag}_report.txt")

        det_df_out = pd.DataFrame(detections)
        det_df_out.to_csv(det_csv, index=False, encoding='utf-8')
        print(f"  → {det_csv}")

        # Pattern summary CSV
        directional = det_df_out[det_df_out['Direction'] != 'Neutral']
        max_r_levels = cfg.get('max_r_levels', 5)
        srows = []
        for pat in det_df_out['Pattern'].unique():
            ps = det_df_out[det_df_out['Pattern'] == pat]
            ds = ps[ps['Direction'] != 'Neutral']
            row_s = {'Timeframe': tf_label, 'Pattern': pat, 'Category': ps['Category'].iloc[0],
                     'Direction': ps['Direction'].iloc[0], 'Total': len(ps)}
            if len(ds) > 0:
                s_  = int((ds['Prediction_Success'] == True).sum())
                f_  = int((ds['Prediction_Success'] == False).sum())
                wr_ = round(s_ / (s_ + f_) * 100, 1) if (s_ + f_) > 0 else 0
                row_s.update({
                    'Wins': s_, 'Losses': f_, 'Win_Rate_%': wr_,
                    'SL_Hit_%': round((ds['SL_Hit'] == True).sum() / len(ds) * 100, 1),
                    'TP_Hit_%': round((ds['TP_Hit'] == True).sum() / len(ds) * 100, 1),
                    'Avg_SL_Pips': round(ds['SL_Pips'].dropna().mean(), 1) if not ds['SL_Pips'].dropna().empty else 0,
                    'Avg_Max_R':   round(ds['Max_R'].dropna().mean(), 2)   if not ds['Max_R'].dropna().empty else 0,
                })
                for r in range(1, max_r_levels+1):
                    col = f'R{r}_Hit'
                    if col in ds.columns:
                        hc = int((ds[col] == True).sum()); ec = int(ds[col].notna().sum())
                        row_s[f'R{r}_Hit_%'] = round(hc / ec * 100, 1) if ec > 0 else 0
                    else:
                        row_s[f'R{r}_Hit_%'] = 0
            else:
                row_s.update({'Wins': 0, 'Losses': 0, 'Win_Rate_%': 0,
                              'SL_Hit_%': 0, 'TP_Hit_%': 0, 'Avg_SL_Pips': 0, 'Avg_Max_R': 0})
                for r in range(1, max_r_levels+1): row_s[f'R{r}_Hit_%'] = 0
            srows.append(row_s)
        pd.DataFrame(srows).to_csv(sum_csv, index=False, encoding='utf-8')
        print(f"  → {sum_csv}")

        # Session summary CSV
        srows2 = []
        for sess in directional['Session'].unique() if len(directional) > 0 else []:
            sd = directional[directional['Session'] == sess]
            if len(sd) == 0: continue
            s_ = int((sd['Prediction_Success'] == True).sum())
            f_ = int((sd['Prediction_Success'] == False).sum())
            wr_ = round(s_ / (s_ + f_) * 100, 1) if (s_ + f_) > 0 else 0
            row_s2 = {'Timeframe': tf_label, 'Session': sess, 'Signals': len(sd),
                      'Wins': s_, 'Losses': f_, 'Win_Rate_%': wr_,
                      'SL_Hit_%': round((sd['SL_Hit'] == True).sum() / len(sd) * 100, 1),
                      'TP_Hit_%': round((sd['TP_Hit'] == True).sum() / len(sd) * 100, 1),
                      'Avg_SL_Pips': round(sd['SL_Pips'].dropna().mean(), 1) if not sd['SL_Pips'].dropna().empty else 0,
                      'Avg_Max_R':   round(sd['Max_R'].dropna().mean(), 2)   if not sd['Max_R'].dropna().empty else 0}
            for r in range(1, max_r_levels+1):
                col = f'R{r}_Hit'
                if col in sd.columns:
                    hc = int((sd[col] == True).sum()); ec = int(sd[col].notna().sum())
                    row_s2[f'R{r}_Hit_%'] = round(hc / ec * 100, 1) if ec > 0 else 0
                else:
                    row_s2[f'R{r}_Hit_%'] = 0
            srows2.append(row_s2)
        pd.DataFrame(srows2).to_csv(sess_csv, index=False, encoding='utf-8')
        print(f"  → {sess_csv}")

        # Text report
        report = fb_generate_report(detections, df, symbol, tf_label, cfg)
        with open(rpt_file, 'w', encoding='utf-8') as fh:
            fh.write(report)
        print(f"  → {rpt_file}")

        # Quick TF summary
        print(f"\n  [{tf_label}] Quick Summary:")
        if len(directional) > 0:
            s_ = int((directional['Prediction_Success'] == True).sum())
            f_ = int((directional['Prediction_Success'] == False).sum())
            wr_ = round(s_ / (s_ + f_) * 100, 1) if (s_ + f_) > 0 else 0
            print(f"    Directional signals : {len(directional)}")
            print(f"    Win rate            : {wr_}%")
            print(f"    Avg SL pips         : {directional['SL_Pips'].dropna().mean():.1f}")
            print(f"    Avg Max R           : {directional['Max_R'].dropna().mean():.2f}R")

    # Save combined stats JSON
    try:
        combined_stats = {'symbol': symbol, 'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                          'backtest_range': f"{args.date_from} to {args.date_to}",
                          'timeframes': {}}
        for tf_label, dets in all_results.items():
            if not dets: continue
            df_tf   = pd.DataFrame(dets)
            dirdf   = df_tf[df_tf['Direction'] != 'Neutral']
            tf_stats = {}
            if len(dirdf) > 0:
                s_ = int((dirdf['Prediction_Success'] == True).sum())
                f_ = int((dirdf['Prediction_Success'] == False).sum())
                tf_stats['overall'] = {
                    'win_rate':     round(s_ / (s_ + f_) * 100, 1) if (s_ + f_) > 0 else 0,
                    'total_signals': len(dirdf),
                    'avg_max_r':    round(float(dirdf['Max_R'].dropna().mean()), 2),
                    'sl_hit_pct':   round(float((dirdf['SL_Hit'] == True).sum() / len(dirdf) * 100), 1),
                    'tp_hit_pct':   round(float((dirdf['TP_Hit'] == True).sum() / len(dirdf) * 100), 1),
                }
            combined_stats['timeframes'][tf_label] = tf_stats
        stats_path = os.path.join(out_dir, 'latest_stats_multitf.json')
        os.makedirs(out_dir, exist_ok=True)
        with open(stats_path, 'w', encoding='utf-8') as sf:
            json.dump(combined_stats, sf, indent=2, ensure_ascii=False)
        print(f"\n  Stats → {stats_path}")
    except Exception as e:
        print(f"  [WARNING] Could not save stats: {e}")

    try: mt5.shutdown()
    except Exception: pass
    print("\nFull backtest complete.")


# ============================================================
# ARGUMENT PARSER & MAIN
# ============================================================

def parse_args(cfg=None):
    if cfg is None: cfg = CFG
    p = argparse.ArgumentParser(
        description="MT5 Multi-Timeframe Candlestick Pattern Scanner & Backtester v6",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Examples:
  # Live scanner — all timeframes
  python mt5_multitf_pattern_scanner_v6.py

  # Live scanner — specific timeframes
  python mt5_multitf_pattern_scanner_v6.py --timeframes M5 H1 H4

  # One-shot scan
  python mt5_multitf_pattern_scanner_v6.py --mode scan

  # Quick backtest (500 bars) on H4 only
  python mt5_multitf_pattern_scanner_v6.py --mode backtest --bars 500 --timeframes H4

  # Full backtest on all TFs, 2024 full year
  python mt5_multitf_pattern_scanner_v6.py --mode fullbacktest --from 2024-01-01 --to 2024-12-31

  # Full backtest with filters on H4 only
  python mt5_multitf_pattern_scanner_v6.py --mode fullbacktest --timeframes H4 \\
      --d1-trend-filter --volume-filter --forward 15
        """
    )

    p.add_argument("--mode", choices=['live', 'scan', 'backtest', 'fullbacktest'], default='live',
                   help="Operating mode (default: live)")
    p.add_argument("--timeframes", nargs='+', choices=list(TIMEFRAME_MAP.keys()),
                   default=cfg['active_timeframes'],
                   help="Active timeframes (default: M5 M15 H1 H4 D1)")
    p.add_argument("--bars", type=int, default=500,
                   help="Bars for quick backtest (default: 500)")

    # Full backtest
    p.add_argument("--from", dest="date_from", default="2024-01-01",
                   help="Full backtest start date YYYY-MM-DD")
    p.add_argument("--to",   dest="date_to",   default="2024-12-31",
                   help="Full backtest end date YYYY-MM-DD")

    # Core parameters
    p.add_argument("--symbol", default=cfg['symbol'])
    p.add_argument("--atr",    type=int,   default=cfg['atr_period'])
    p.add_argument("--atr-tf", type=str,   default=None,
                   help="Override ATR source timeframe for ALL timeframes (e.g. H1, H4). "
                        "By default, atr_tf_by_tf config is used (M5→H1, M15→H1, etc.)")
    p.add_argument("--sl",     type=float, default=cfg['sl_multiplier'])
    p.add_argument("--tp",     type=float, default=cfg['tp_multiplier'])
    p.add_argument("--forward",type=int,   default=cfg['default_forward_candles'],
                   help="Default forward candles for evaluation (H4 default)")
    p.add_argument("--output", default=DEFAULT_OUTPUT_DIR)

    # MT5 connection overrides — credentials always come from .env
    p.add_argument("--mt5-path", default=cfg['mt5_path'])
    p.add_argument("--account",  type=int, default=cfg['account'])
    p.add_argument("--password", default=cfg['password'])
    p.add_argument("--server",   default=cfg['server'])

    # Pattern thresholds
    p.add_argument("--doji-body-ratio",           type=float, default=cfg['doji_body_ratio'])
    p.add_argument("--spinning-top-body-ratio",   type=float, default=cfg['spinning_top_body_ratio'])
    p.add_argument("--marubozu-wick-ratio",       type=float, default=cfg['marubozu_wick_ratio'])
    p.add_argument("--hammer-lower-wick-ratio",   type=float, default=cfg['hammer_lower_wick_ratio'])
    p.add_argument("--hammer-upper-wick-ratio",   type=float, default=cfg['hammer_upper_wick_ratio'])
    p.add_argument("--long-candle-ratio",         type=float, default=cfg['long_candle_ratio'])
    p.add_argument("--small-candle-ratio",        type=float, default=cfg['small_candle_ratio'])
    p.add_argument("--tweezer-tolerance",         type=float, default=cfg['tweezer_tolerance_pips'])
    p.add_argument("--engulf-tolerance-pips",     type=float, default=cfg['engulf_tolerance_pips'])
    p.add_argument("--trend-lookback",            type=int,   default=cfg['trend_lookback'])
    p.add_argument("--broker-utc-offset",         type=int,   default=cfg['broker_utc_offset'])

    # Filters
    p.add_argument("--deduplicate",    dest="deduplicate_signals", action="store_true")
    p.add_argument("--no-deduplicate", dest="deduplicate_signals", action="store_false")
    p.add_argument("--verify-entry",    dest="verify_entry", action="store_true")
    p.add_argument("--no-verify-entry", dest="verify_entry", action="store_false")
    p.add_argument("--volume-filter",    dest="volume_filter", action="store_true")
    p.add_argument("--no-volume-filter", dest="volume_filter", action="store_false")
    p.add_argument("--volume-ma-period",  type=int,   default=cfg['volume_ma_period'])
    p.add_argument("--volume-threshold",  type=float, default=cfg['volume_threshold'])
    p.add_argument("--d1-trend-filter",    dest="d1_trend_filter", action="store_true")
    p.add_argument("--no-d1-trend-filter", dest="d1_trend_filter", action="store_false")
    p.add_argument("--d1-sma-period", type=int, default=cfg['d1_sma_period'])

    # Reconnect
    p.add_argument("--max-reconnect-attempts", type=int, default=cfg['max_reconnect_attempts'])
    p.add_argument("--reconnect-backoff",       type=int, default=cfg['reconnect_backoff_base'])

    # Live signal filtering
    p.add_argument("--min-signal-score",   type=float, default=cfg['min_signal_score'])
    p.add_argument("--alert-only-strong",    dest="alert_only_strong",     action="store_true")
    p.add_argument("--no-alert-only-strong", dest="alert_only_strong",     action="store_false")
    p.add_argument("--show-dashboard",    dest="show_dashboard_on_start",  action="store_true")
    p.add_argument("--no-dashboard",      dest="show_dashboard_on_start",  action="store_false")

    # Position sizing
    p.add_argument("--account-balance", type=float, default=cfg['account_balance'])
    p.add_argument("--risk-percent",    type=float, default=cfg['risk_percent'])

    # Misc
    p.add_argument("--warmup-bars",    type=int, default=cfg['warmup_bars'])
    p.add_argument("--bars-to-fetch",  type=int, default=cfg['bars_to_fetch'])

    p.set_defaults(
        deduplicate_signals=cfg['deduplicate_signals'],
        verify_entry=cfg['verify_entry'],
        volume_filter=cfg['volume_filter'],
        d1_trend_filter=cfg['d1_trend_filter'],
        alert_only_strong=cfg['alert_only_strong'],
        show_dashboard_on_start=cfg['show_dashboard_on_start'],
    )
    return p.parse_args()


def main():
    args = parse_args()

    # Build runtime CFG from defaults + CLI overrides
    runtime_cfg = dict(CFG)
    runtime_cfg['active_timeframes'] = args.timeframes
    cli_to_cfg = {
        'symbol': 'symbol', 'atr': 'atr_period', 'sl': 'sl_multiplier', 'tp': 'tp_multiplier',
        'forward': 'default_forward_candles', 'mt5_path': 'mt5_path', 'account': 'account',
        'password': 'password', 'server': 'server',
        'doji_body_ratio': 'doji_body_ratio', 'spinning_top_body_ratio': 'spinning_top_body_ratio',
        'marubozu_wick_ratio': 'marubozu_wick_ratio',
        'hammer_lower_wick_ratio': 'hammer_lower_wick_ratio',
        'hammer_upper_wick_ratio': 'hammer_upper_wick_ratio',
        'long_candle_ratio': 'long_candle_ratio', 'small_candle_ratio': 'small_candle_ratio',
        'tweezer_tolerance': 'tweezer_tolerance_pips',
        'engulf_tolerance_pips': 'engulf_tolerance_pips',
        'trend_lookback': 'trend_lookback', 'broker_utc_offset': 'broker_utc_offset',
        'deduplicate_signals': 'deduplicate_signals', 'verify_entry': 'verify_entry',
        'volume_filter': 'volume_filter', 'volume_ma_period': 'volume_ma_period',
        'volume_threshold': 'volume_threshold',
        'd1_trend_filter': 'd1_trend_filter', 'd1_sma_period': 'd1_sma_period',
        'max_reconnect_attempts': 'max_reconnect_attempts',
        'reconnect_backoff': 'reconnect_backoff_base',
        'warmup_bars': 'warmup_bars', 'bars_to_fetch': 'bars_to_fetch',
        'min_signal_score': 'min_signal_score',
        'alert_only_strong': 'alert_only_strong',
        'show_dashboard_on_start': 'show_dashboard_on_start',
        'account_balance': 'account_balance',
        'risk_percent': 'risk_percent',
    }
    for cli_key, cfg_key in cli_to_cfg.items():
        if hasattr(args, cli_key):
            runtime_cfg[cfg_key] = getattr(args, cli_key)

    # Handle --atr-tf override: if specified, override all ATR source TFs
    if hasattr(args, 'atr_tf') and args.atr_tf is not None:
        override_tf = args.atr_tf.upper()
        if override_tf not in TIMEFRAME_MAP:
            print(f"ERROR: --atr-tf '{override_tf}' not in {list(TIMEFRAME_MAP.keys())}")
            sys.exit(1)
        # Override the per-TF mapping to use the specified TF for all
        runtime_cfg['atr_tf_by_tf'] = {tf: override_tf for tf in TIMEFRAME_MAP.keys()}

    if args.mode == 'live':
        run_scanner(runtime_cfg)
    elif args.mode == 'scan':
        run_single_scan(runtime_cfg)
    elif args.mode == 'backtest':
        run_quick_backtest(args.bars, runtime_cfg)
    elif args.mode == 'fullbacktest':
        run_full_backtest(args, runtime_cfg)


if __name__ == '__main__':
    main()
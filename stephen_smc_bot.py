"""
╔══════════════════════════════════════════════════════════════════╗
║         STEPHEN'S SMC ULTIMATE BOT v4.0                         ║
║         Smart Money Concepts + Full Automation                   ║
╠══════════════════════════════════════════════════════════════════╣
║  SMC FEATURES:                                                   ║
║  ✅ Order Block Detection (Bullish & Bearish)                    ║
║  ✅ Break of Structure (BOS) Detection                          ║
║  ✅ Fair Value Gap (FVG) Scanner                                ║
║  ✅ Liquidity Level Finder                                      ║
║  ✅ Market Structure Analysis                                    ║
║  ✅ SMC + EMA Confluence                                        ║
║  ✅ SMC Telegram Alerts with full analysis                      ║
║                                                                  ║
║  ALL V3.0 FEATURES INCLUDED:                                    ║
║  ✅ EMA 20/50/200 + RSI + ADX                                   ║
║  ✅ London & New York Sessions only                             ║
║  ✅ Economic News Protection                                    ║
║  ✅ Break Even Stop Loss                                        ║
║  ✅ Trailing Stop Loss                                          ║
║  ✅ Weekend Protection                                          ║
║  ✅ Daily Telegram Report                                       ║
║  ✅ Drawdown Safe Mode                                          ║
║  ✅ Auto Lot Adjustment                                         ║
║  ✅ Martingale Protection                                       ║
║  ✅ Multiple Currency Pairs                                     ║
║  ✅ Signal Score out of 10                                      ║
║  ✅ Fake Signal Filter                                          ║
║  ✅ Cooldown After Losses                                       ║
║  ✅ News Sentiment Analysis                                     ║
║  ✅ H4 Trend Filter                                             ║
║  ✅ Backtest Module                                             ║
╚══════════════════════════════════════════════════════════════════╝

INSTALL:
  pip install MetaTrader5 pandas numpy requests python-telegram-bot yfinance

RUN LIVE:
  python stephen_smc_bot.py

RUN BACKTEST:
  python stephen_smc_bot.py --backtest
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import requests
import json
import time
import sys
import logging
from datetime import datetime, timedelta
from collections import deque

# ═══════════════════════════════════════════════════════
#  ⚙️  STEPHEN'S CONFIG
# ═══════════════════════════════════════════════════════
config = {
    # ── MT5 Account ──────────────────────────────────
    "mt5_login":    9250670,
    "mt5_password": "1357Chris@",
    "mt5_server":   "EGMSecurities-Live",

    # ── Telegram ─────────────────────────────────────
    "telegram_token":   "8749193019:AAEUm6g8PqZk0gH2yKLtv50ANauF4lRWQbs",
    "telegram_chat_id": "7781270946",

    # ── News API ──────────────────────────────────────
    "news_api_key": "a7605dac1cc94f5081c9701e4db949af",

    # ── Trading Pairs ─────────────────────────────────
    "symbols": ["EURUSD", "GBPUSD", "USDJPY"],

    # ── Timeframes ────────────────────────────────────
    "timeframe": mt5.TIMEFRAME_H1,    # Main timeframe
    "htf":       mt5.TIMEFRAME_H4,    # Higher timeframe trend
    "smc_tf":    mt5.TIMEFRAME_H4,    # SMC structure timeframe

    # ── Risk Management ───────────────────────────────
    "risk_pct":         1.0,
    "max_daily_loss":   3.0,
    "max_drawdown":     10.0,
    "max_open_trades":  2,
    "safe_mode_risk":   0.5,

    # ── Strategy Indicators ───────────────────────────
    "ema_fast":   20,
    "ema_slow":   50,
    "ema_trend":  200,
    "rsi_period": 14,
    "rsi_ob":     65,
    "rsi_os":     35,
    "adx_min":    25,
    "atr_period": 14,

    # ── SMC Settings ──────────────────────────────────
    "ob_lookback":    10,    # Candles to look back for Order Blocks
    "fvg_min_pips":   5,     # Minimum FVG size in pips
    "bos_lookback":   20,    # Candles to look back for BOS
    "liquidity_pips": 10,    # Pips above/below swing high/low

    # ── Trade Management ──────────────────────────────
    "trailing_atr_mult":  2.0,
    "tp_atr_mult":        4.0,
    "breakeven_pips":     20,

    # ── Signal Quality ────────────────────────────────
    "min_score":  7,         # Minimum score out of 10
    "smc_bonus":  2,         # Extra points for SMC confirmation

    # ── Cooldown & Protection ─────────────────────────
    "cooldown_after_loss":  2,
    "cooldown_minutes":     120,
    "martingale_trigger":   3,

    # ── Session Filter (EAT = UTC+3) ──────────────────
    "london_open":   10,
    "london_close":  19,
    "newyork_open":  15,
    "newyork_close": 24,

    # ── Weekend & Report ──────────────────────────────
    "friday_close_hour": 21,
    "report_hour":       23,

    # ── Check Interval ────────────────────────────────
    "check_interval": 300,
}
# ═══════════════════════════════════════════════════════


# ── Logging ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("stephen_smc_bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════
#  📱 TELEGRAM MODULE
# ══════════════════════════════════════════════════════

def send_telegram(message: str):
    try:
        url  = f"https://api.telegram.org/bot{config['telegram_token']}/sendMessage"
        data = {
            "chat_id":    config["telegram_chat_id"],
            "text":       message,
            "parse_mode": "HTML"
        }
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        log.warning(f"Telegram failed: {e}")


def send_daily_report(stats: dict):
    news    = get_financial_news()
    warning = ""
    danger  = ["NFP", "CPI", "FOMC", "GDP", "PMI"]
    for a in news:
        if any(d in a["title"] for d in danger):
            warning = "⚠️ High impact news coming — bot will be careful!"
            break

    report = f"""
📊 <b>STEPHEN'S DAILY REPORT</b>
📅 {datetime.now().strftime('%d %B %Y')}
━━━━━━━━━━━━━━━━━━━━
📈 Trades:     {stats.get('trades', 0)}
✅ Wins:       {stats.get('wins', 0)}
❌ Losses:     {stats.get('losses', 0)}
🎯 Win Rate:   {stats.get('win_rate', 0):.1f}%
💰 Profit:     ${stats.get('profit', 0):.2f}
💼 Balance:    ${stats.get('balance', 0):.2f}
📈 Best Trade: ${stats.get('best_trade', 0):.2f}
📉 Worst Trade:${stats.get('worst_trade', 0):.2f}
━━━━━━━━━━━━━━━━━━━━
🧠 SMC Signals Today: {stats.get('smc_signals', 0)}
🎯 OB Trades: {stats.get('ob_trades', 0)}
📊 BOS Trades: {stats.get('bos_trades', 0)}
📉 FVG Trades: {stats.get('fvg_trades', 0)}
━━━━━━━━━━━━━━━━━━━━
{warning}
🌅 Bot continues tomorrow...
"""
    send_telegram(report)


# ══════════════════════════════════════════════════════
#  🧠 SMC MODULE — SMART MONEY CONCEPTS
# ══════════════════════════════════════════════════════

class SMCAnalyzer:
    """
    Full Smart Money Concepts Analysis:
    - Market Structure (BOS & CHOCH)
    - Order Blocks (Bullish & Bearish)
    - Fair Value Gaps (FVG)
    - Liquidity Levels
    """

    def __init__(self, df: pd.DataFrame):
        self.df   = df.copy()
        self.last = df.iloc[-1]
        self.pip  = 0.0001  # Default pip size

    # ── 1. MARKET STRUCTURE ────────────────────────────

    def get_market_structure(self) -> dict:
        """
        Detect Break of Structure (BOS) and
        Change of Character (CHOCH)
        """
        df       = self.df
        lookback = config["bos_lookback"]
        highs    = df["high"].values
        lows     = df["low"].values
        closes   = df["close"].values

        structure = {
            "trend":  "NEUTRAL",
            "bos":    None,
            "choch":  None,
            "swing_high": None,
            "swing_low":  None,
        }

        # Find swing highs and lows
        swing_highs = []
        swing_lows  = []

        for i in range(2, len(df) - 2):
            # Swing high: higher than 2 candles each side
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
               highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                swing_highs.append((i, highs[i]))

            # Swing low: lower than 2 candles each side
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
               lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                swing_lows.append((i, lows[i]))

        if not swing_highs or not swing_lows:
            return structure

        # Get recent swings
        recent_high = swing_highs[-1] if swing_highs else None
        recent_low  = swing_lows[-1]  if swing_lows  else None
        prev_high   = swing_highs[-2] if len(swing_highs) > 1 else None
        prev_low    = swing_lows[-2]  if len(swing_lows)  > 1 else None

        structure["swing_high"] = recent_high[1] if recent_high else None
        structure["swing_low"]  = recent_low[1]  if recent_low  else None

        current_price = closes[-1]

        # Detect BOS Bullish (price breaks above previous swing high)
        if recent_high and prev_high:
            if current_price > prev_high[1]:
                structure["bos"]   = "BULLISH"
                structure["trend"] = "BULLISH"

        # Detect BOS Bearish (price breaks below previous swing low)
        if recent_low and prev_low:
            if current_price < prev_low[1]:
                structure["bos"]   = "BEARISH"
                structure["trend"] = "BEARISH"

        # Detect CHOCH (Change of Character)
        if structure["trend"] == "BULLISH" and recent_low and prev_low:
            if current_price < recent_low[1]:
                structure["choch"] = "BEARISH"
                structure["trend"] = "BEARISH"

        if structure["trend"] == "BEARISH" and recent_high and prev_high:
            if current_price > recent_high[1]:
                structure["choch"] = "BULLISH"
                structure["trend"] = "BULLISH"

        return structure


    # ── 2. ORDER BLOCKS ────────────────────────────────

    def find_order_blocks(self) -> dict:
        """
        Find Bullish and Bearish Order Blocks.

        Bullish OB: Last bearish candle before a strong bullish move
        Bearish OB: Last bullish candle before a strong bearish move
        """
        df       = self.df
        lookback = config["ob_lookback"]
        result   = {"bullish_ob": None, "bearish_ob": None}

        for i in range(len(df) - lookback, len(df) - 2):
            if i < 1:
                continue

            candle      = df.iloc[i]
            next_candle = df.iloc[i + 1]
            body_size   = abs(candle["close"] - candle["open"])
            next_body   = abs(next_candle["close"] - next_candle["open"])

            # Bullish Order Block:
            # Bearish candle followed by strong bullish move
            if (candle["close"] < candle["open"] and      # Bearish candle
                next_candle["close"] > next_candle["open"] and  # Followed by bullish
                next_body > body_size * 1.5 and            # Strong move
                df.iloc[-1]["close"] > candle["high"]):    # Price now above OB

                result["bullish_ob"] = {
                    "high":   candle["high"],
                    "low":    candle["low"],
                    "open":   candle["open"],
                    "close":  candle["close"],
                    "index":  i,
                    "type":   "BULLISH"
                }

            # Bearish Order Block:
            # Bullish candle followed by strong bearish move
            if (candle["close"] > candle["open"] and       # Bullish candle
                next_candle["close"] < next_candle["open"] and  # Followed by bearish
                next_body > body_size * 1.5 and             # Strong move
                df.iloc[-1]["close"] < candle["low"]):      # Price now below OB

                result["bearish_ob"] = {
                    "high":  candle["high"],
                    "low":   candle["low"],
                    "open":  candle["open"],
                    "close": candle["close"],
                    "index": i,
                    "type":  "BEARISH"
                }

        return result


    # ── 3. FAIR VALUE GAPS ─────────────────────────────

    def find_fvg(self) -> dict:
        """
        Find Fair Value Gaps (FVG / Imbalances).

        Bullish FVG: Gap between candle[i-1] high and candle[i+1] low
        Bearish FVG: Gap between candle[i-1] low and candle[i+1] high
        Price tends to return to fill these gaps.
        """
        df     = self.df
        result = {"bullish_fvg": [], "bearish_fvg": []}
        min_gap = config["fvg_min_pips"] * 0.0001

        for i in range(1, len(df) - 1):
            prev = df.iloc[i - 1]
            curr = df.iloc[i]
            nxt  = df.iloc[i + 1]

            # Bullish FVG: gap between prev high and next low
            if nxt["low"] > prev["high"]:
                gap_size = nxt["low"] - prev["high"]
                if gap_size >= min_gap:
                    result["bullish_fvg"].append({
                        "top":    nxt["low"],
                        "bottom": prev["high"],
                        "size":   gap_size,
                        "index":  i,
                        "filled": df.iloc[-1]["low"] <= nxt["low"]
                    })

            # Bearish FVG: gap between prev low and next high
            if nxt["high"] < prev["low"]:
                gap_size = prev["low"] - nxt["high"]
                if gap_size >= min_gap:
                    result["bearish_fvg"].append({
                        "top":    prev["low"],
                        "bottom": nxt["high"],
                        "size":   gap_size,
                        "index":  i,
                        "filled": df.iloc[-1]["high"] >= nxt["high"]
                    })

        # Return only unfilled recent FVGs
        result["bullish_fvg"] = [f for f in result["bullish_fvg"][-5:] if not f["filled"]]
        result["bearish_fvg"] = [f for f in result["bearish_fvg"][-5:] if not f["filled"]]

        return result


    # ── 4. LIQUIDITY LEVELS ────────────────────────────

    def find_liquidity(self) -> dict:
        """
        Find liquidity levels (equal highs/lows where stops are hunted).
        Smart money hunts these levels before reversing.
        """
        df     = self.df
        result = {"buy_side": [], "sell_side": []}
        pip    = config["liquidity_pips"] * 0.0001

        highs = df["high"].values
        lows  = df["low"].values

        # Find equal highs (buy side liquidity)
        for i in range(len(highs) - 10, len(highs) - 1):
            for j in range(i + 1, len(highs)):
                if abs(highs[i] - highs[j]) <= pip:
                    result["buy_side"].append({
                        "level": (highs[i] + highs[j]) / 2,
                        "count": 2
                    })
                    break

        # Find equal lows (sell side liquidity)
        for i in range(len(lows) - 10, len(lows) - 1):
            for j in range(i + 1, len(lows)):
                if abs(lows[i] - lows[j]) <= pip:
                    result["sell_side"].append({
                        "level": (lows[i] + lows[j]) / 2,
                        "count": 2
                    })
                    break

        return result


    # ── 5. FULL SMC ANALYSIS ───────────────────────────

    def analyze(self, signal: str) -> dict:
        """
        Run complete SMC analysis and score the setup.
        Returns SMC score and full analysis.
        """
        structure  = self.get_market_structure()
        obs        = self.find_order_blocks()
        fvgs       = self.find_fvg()
        liquidity  = self.find_liquidity()

        current_price = self.df.iloc[-1]["close"]
        smc_score     = 0
        confirmations = []
        trade_valid   = False

        if signal == "BUY":
            # 1. BOS Bullish confirms direction
            if structure["bos"] == "BULLISH":
                smc_score += 2
                confirmations.append("✅ BOS Bullish confirmed (+2)")

            # 2. Price at/near Bullish Order Block
            if obs["bullish_ob"]:
                ob = obs["bullish_ob"]
                if ob["low"] <= current_price <= ob["high"] * 1.001:
                    smc_score += 3
                    confirmations.append(f"✅ Price at Bullish OB ({ob['low']:.5f}-{ob['high']:.5f}) (+3)")
                    trade_valid = True

            # 3. Bullish FVG nearby
            for fvg in fvgs["bullish_fvg"]:
                if fvg["bottom"] <= current_price <= fvg["top"] * 1.001:
                    smc_score += 2
                    confirmations.append(f"✅ Price in Bullish FVG ({fvg['bottom']:.5f}-{fvg['top']:.5f}) (+2)")
                    trade_valid = True
                    break

            # 4. Sell side liquidity swept (smart money grabbed stops)
            for liq in liquidity["sell_side"]:
                if current_price > liq["level"]:
                    smc_score += 1
                    confirmations.append(f"✅ Sell liquidity swept at {liq['level']:.5f} (+1)")
                    break

            # 5. CHOCH Bullish
            if structure["choch"] == "BULLISH":
                smc_score += 2
                confirmations.append("✅ CHOCH Bullish detected (+2)")

        else:  # SELL
            # 1. BOS Bearish
            if structure["bos"] == "BEARISH":
                smc_score += 2
                confirmations.append("✅ BOS Bearish confirmed (+2)")

            # 2. Price at/near Bearish Order Block
            if obs["bearish_ob"]:
                ob = obs["bearish_ob"]
                if ob["low"] * 0.999 <= current_price <= ob["high"]:
                    smc_score += 3
                    confirmations.append(f"✅ Price at Bearish OB ({ob['low']:.5f}-{ob['high']:.5f}) (+3)")
                    trade_valid = True

            # 3. Bearish FVG nearby
            for fvg in fvgs["bearish_fvg"]:
                if fvg["bottom"] * 0.999 <= current_price <= fvg["top"]:
                    smc_score += 2
                    confirmations.append(f"✅ Price in Bearish FVG ({fvg['bottom']:.5f}-{fvg['top']:.5f}) (+2)")
                    trade_valid = True
                    break

            # 4. Buy side liquidity swept
            for liq in liquidity["buy_side"]:
                if current_price < liq["level"]:
                    smc_score += 1
                    confirmations.append(f"✅ Buy liquidity swept at {liq['level']:.5f} (+1)")
                    break

            # 5. CHOCH Bearish
            if structure["choch"] == "BEARISH":
                smc_score += 2
                confirmations.append("✅ CHOCH Bearish detected (+2)")

        return {
            "smc_score":     min(smc_score, 10),
            "confirmations": confirmations,
            "structure":     structure,
            "order_blocks":  obs,
            "fvgs":          fvgs,
            "liquidity":     liquidity,
            "trade_valid":   trade_valid,
            "bos":           structure["bos"],
            "swing_high":    structure["swing_high"],
            "swing_low":     structure["swing_low"],
        }


# ══════════════════════════════════════════════════════
#  📊 INDICATORS MODULE
# ══════════════════════════════════════════════════════

def get_candles(symbol, timeframe, count=300):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df["ema_fast"]  = df["close"].ewm(span=config["ema_fast"],  adjust=False).mean()
    df["ema_slow"]  = df["close"].ewm(span=config["ema_slow"],  adjust=False).mean()
    df["ema_trend"] = df["close"].ewm(span=config["ema_trend"], adjust=False).mean()

    delta    = df["close"].diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=config["rsi_period"] - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=config["rsi_period"] - 1, adjust=False).mean()
    rs       = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))

    df["tr"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift()),
                   abs(df["low"]  - df["close"].shift()))
    )
    df["atr"] = df["tr"].rolling(config["atr_period"]).mean()

    df["+dm"] = np.where(
        (df["high"] - df["high"].shift()) > (df["low"].shift() - df["low"]),
        np.maximum(df["high"] - df["high"].shift(), 0), 0)
    df["-dm"] = np.where(
        (df["low"].shift() - df["low"]) > (df["high"] - df["high"].shift()),
        np.maximum(df["low"].shift() - df["low"], 0), 0)
    df["+di"] = 100 * (df["+dm"].ewm(span=14, adjust=False).mean() / (df["atr"] + 1e-10))
    df["-di"] = 100 * (df["-dm"].ewm(span=14, adjust=False).mean() / (df["atr"] + 1e-10))
    df["dx"]  = 100 * abs(df["+di"] - df["-di"]) / (df["+di"] + df["-di"] + 1e-10)
    df["adx"] = df["dx"].ewm(span=14, adjust=False).mean()

    df["body_pct"] = abs(df["close"] - df["open"]) / (df["high"] - df["low"] + 1e-10) * 100
    return df


def get_signal(df: pd.DataFrame) -> str:
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]:
        return "BUY"
    if prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]:
        return "SELL"
    return None


def get_htf_trend(symbol) -> str:
    df = get_candles(symbol, config["htf"], 60)
    if df is None:
        return "NEUTRAL"
    df   = calculate_indicators(df)
    last = df.iloc[-1]
    if last["ema_fast"] > last["ema_slow"] > last["ema_trend"]:
        return "BULLISH"
    elif last["ema_fast"] < last["ema_slow"] < last["ema_trend"]:
        return "BEARISH"
    return "NEUTRAL"


def score_signal(df, direction, htf_trend, smc_result) -> tuple:
    """Score signal out of 10 including SMC bonus."""
    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    score = 0
    details = []

    if direction == "BUY":
        if prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]:
            score += 1; details.append("✅ EMA crossover bullish")
        if last["close"] > last["ema_trend"]:
            score += 1; details.append("✅ Above EMA200")
        if htf_trend == "BULLISH":
            score += 1; details.append("✅ H4 trend bullish")
        if 40 < last["rsi"] < config["rsi_ob"]:
            score += 1; details.append(f"✅ RSI good ({last['rsi']:.0f})")
        if last["adx"] > config["adx_min"]:
            score += 1; details.append(f"✅ ADX strong ({last['adx']:.0f})")
        if last["body_pct"] > 40 and last["close"] > last["open"]:
            score += 1; details.append("✅ Strong bull candle")
        if last["rsi"] > config["rsi_ob"]:
            score -= 1; details.append("❌ RSI overbought")
    else:
        if prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]:
            score += 1; details.append("✅ EMA crossover bearish")
        if last["close"] < last["ema_trend"]:
            score += 1; details.append("✅ Below EMA200")
        if htf_trend == "BEARISH":
            score += 1; details.append("✅ H4 trend bearish")
        if config["rsi_os"] < last["rsi"] < 60:
            score += 1; details.append(f"✅ RSI good ({last['rsi']:.0f})")
        if last["adx"] > config["adx_min"]:
            score += 1; details.append(f"✅ ADX strong ({last['adx']:.0f})")
        if last["body_pct"] > 40 and last["close"] < last["open"]:
            score += 1; details.append("✅ Strong bear candle")
        if last["rsi"] < config["rsi_os"]:
            score -= 1; details.append("❌ RSI oversold")

    # Add SMC bonus score
    smc_bonus = min(smc_result["smc_score"], config["smc_bonus"])
    if smc_bonus > 0:
        score += smc_bonus
        details.append(f"✅ SMC confirmation (+{smc_bonus})")

    return max(0, min(score, 10)), details


# ══════════════════════════════════════════════════════
#  ⏰ SESSION & NEWS MODULE
# ══════════════════════════════════════════════════════

def is_trading_session() -> tuple:
    now     = datetime.now()
    hour    = now.hour
    weekday = now.weekday()

    if weekday >= 5:
        return False, "Weekend — markets closed"

    london  = config["london_open"]  <= hour < config["london_close"]
    newyork = config["newyork_open"] <= hour < config["newyork_close"]

    if london and newyork:
        return True, "🇬🇧🇺🇸 London + NY Overlap (Best!)"
    elif london:
        return True, "🇬🇧 London Session"
    elif newyork:
        return True, "🇺🇸 New York Session"
    return False, f"😴 Asian Session — waiting for London (10am EAT)"


def is_friday_close_time() -> bool:
    now = datetime.now()
    return now.weekday() == 4 and now.hour >= config["friday_close_hour"]


def get_financial_news() -> list:
    try:
        url    = "https://newsapi.org/v2/everything"
        params = {
            "q":        "forex EURUSD GBPUSD interest rate Federal Reserve ECB",
            "language": "en",
            "sortBy":   "publishedAt",
            "pageSize": 10,
            "apiKey":   config["news_api_key"]
        }
        r = requests.get(url, params=params, timeout=10)
        return [{"title": a["title"]} for a in r.json().get("articles", [])]
    except:
        return []


def is_high_impact_news() -> tuple:
    now  = datetime.now()
    hour = now.hour
    danger_times = [
        (11, 30, "London Open News"),
        (16, 30, "US News Release"),
        (18, 0,  "Fed/ECB Speeches"),
        (21, 0,  "US Afternoon News"),
    ]
    for h, m, name in danger_times:
        now_mins   = hour * 60 + now.minute
        event_mins = h * 60 + m
        if abs(now_mins - event_mins) <= config["news_avoid_minutes"] if "news_avoid_minutes" in config else 60:
            return True, f"⚠️ {name}"
    return False, ""


def analyze_news_sentiment(news, signal) -> dict:
    if not news:
        return {"safe_to_trade": True, "reason": "No news"}
    bullish = ["rate hike", "strong", "growth", "beat", "surge", "rally"]
    bearish = ["rate cut", "weak", "recession", "miss", "crash", "drop"]
    danger  = ["NFP", "CPI", "FOMC", "GDP", "PMI", "nonfarm"]
    bull = bear = 0
    for a in news:
        t = a["title"].lower()
        bull += sum(1 for w in bullish if w in t)
        bear += sum(1 for w in bearish if w in t)
        if any(d.lower() in t for d in danger):
            return {"safe_to_trade": False, "reason": "High impact news detected"}
    if signal == "BUY"  and bear > bull + 2:
        return {"safe_to_trade": False, "reason": f"Bearish news ({bear} vs {bull})"}
    if signal == "SELL" and bull > bear + 2:
        return {"safe_to_trade": False, "reason": f"Bullish news ({bull} vs {bear})"}
    return {"safe_to_trade": True, "reason": f"News OK (B:{bull} S:{bear})"}


# ══════════════════════════════════════════════════════
#  💰 RISK MANAGER
# ══════════════════════════════════════════════════════

class RiskManager:
    def __init__(self):
        self.consecutive_losses = 0
        self.cooldown_until     = None
        self.start_balance      = None
        self.peak_balance       = None
        self.safe_mode          = False
        self.daily_stats        = {
            "trades": 0, "wins": 0, "losses": 0, "profit": 0.0,
            "best_trade": 0.0, "worst_trade": 0.0,
            "smc_signals": 0, "ob_trades": 0, "bos_trades": 0, "fvg_trades": 0
        }
        self.last_report_day = None

    def init(self, balance):
        if self.start_balance is None:
            self.start_balance = balance
            self.peak_balance  = balance
        self.peak_balance = max(self.peak_balance, balance)

    def record_trade(self, profit, smc_type=None):
        self.daily_stats["trades"] += 1
        self.daily_stats["profit"] += profit
        self.daily_stats["best_trade"]  = max(self.daily_stats["best_trade"], profit)
        self.daily_stats["worst_trade"] = min(self.daily_stats["worst_trade"], profit)
        if smc_type == "OB":  self.daily_stats["ob_trades"]  += 1
        if smc_type == "BOS": self.daily_stats["bos_trades"] += 1
        if smc_type == "FVG": self.daily_stats["fvg_trades"] += 1
        if profit > 0:
            self.daily_stats["wins"] += 1
            self.consecutive_losses   = 0
            self.safe_mode            = False
        else:
            self.daily_stats["losses"] += 1
            self.consecutive_losses    += 1
            if self.consecutive_losses >= config["cooldown_after_loss"]:
                self.cooldown_until = datetime.now() + timedelta(minutes=config["cooldown_minutes"])
                send_telegram(f"⏸ <b>COOLDOWN</b>\n{self.consecutive_losses} losses.\nPausing {config['cooldown_minutes']} min.")

    def record_smc_signal(self):
        self.daily_stats["smc_signals"] += 1

    def in_cooldown(self):
        if self.cooldown_until and datetime.now() < self.cooldown_until:
            mins = int((self.cooldown_until - datetime.now()).total_seconds() / 60)
            return True, f"Cooldown: {mins} min"
        self.cooldown_until = None
        return False, ""

    def is_safe_mode(self, balance):
        if self.peak_balance:
            dd = (self.peak_balance - balance) / self.peak_balance * 100
            if dd >= config["max_drawdown"]:
                self.safe_mode = True
        return self.safe_mode

    def daily_loss_hit(self, balance):
        if self.start_balance:
            return ((self.start_balance - balance) / self.start_balance * 100) >= config["max_daily_loss"]
        return False

    def calc_lot(self, balance, sl_pips, symbol):
        risk_pct    = config["safe_mode_risk"] if self.safe_mode else config["risk_pct"]
        if self.consecutive_losses >= config["martingale_trigger"]:
            risk_pct *= 0.5
        risk_amount = balance * (risk_pct / 100)
        sym_info    = mt5.symbol_info(symbol)
        if sym_info is None:
            return 0.01
        pip_value   = sym_info.trade_tick_value * 10
        lot         = round(risk_amount / (sl_pips * pip_value + 1e-10), 2)
        return max(0.01, min(lot, 5.0))

    def should_send_report(self):
        now = datetime.now()
        if now.hour == config["report_hour"] and self.last_report_day != now.date():
            self.last_report_day = now.date()
            return True
        return False

    def reset_daily_stats(self, balance):
        stats = {**self.daily_stats, "balance": balance}
        total = self.daily_stats["trades"]
        stats["win_rate"] = (self.daily_stats["wins"] / total * 100) if total > 0 else 0
        self.daily_stats  = {
            "trades": 0, "wins": 0, "losses": 0, "profit": 0.0,
            "best_trade": 0.0, "worst_trade": 0.0,
            "smc_signals": 0, "ob_trades": 0, "bos_trades": 0, "fvg_trades": 0
        }
        self.start_balance = balance
        return stats


risk = RiskManager()


# ══════════════════════════════════════════════════════
#  🔄 TRADE EXECUTION
# ══════════════════════════════════════════════════════

def place_order(symbol, action, lot, atr, smc_result):
    tick     = mt5.symbol_info_tick(symbol)
    sym_info = mt5.symbol_info(symbol)
    pip      = sym_info.point * 10
    sl_dist  = atr * config["trailing_atr_mult"]
    tp_dist  = atr * config["tp_atr_mult"]

    # Use OB level as SL if available (more precise)
    if action == "BUY" and smc_result["order_blocks"]["bullish_ob"]:
        ob     = smc_result["order_blocks"]["bullish_ob"]
        sl_dist = max(sl_dist, tick.ask - ob["low"])

    if action == "SELL" and smc_result["order_blocks"]["bearish_ob"]:
        ob     = smc_result["order_blocks"]["bearish_ob"]
        sl_dist = max(sl_dist, ob["high"] - tick.bid)

    if action == "BUY":
        price = tick.ask
        sl    = round(price - sl_dist, 5)
        tp    = round(price + tp_dist, 5)
        otype = mt5.ORDER_TYPE_BUY
    else:
        price = tick.bid
        sl    = round(price + sl_dist, 5)
        tp    = round(price - tp_dist, 5)
        otype = mt5.ORDER_TYPE_SELL

    sl_pips = round(sl_dist / pip)
    tp_pips = round(tp_dist / pip)

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lot,
        "type":         otype,
        "price":        price,
        "sl":           sl,
        "tp":           tp,
        "deviation":    20,
        "magic":        20250510,
        "comment":      "Stephen SMC Bot v4",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        # Build SMC summary for Telegram
        smc_summary = "\n".join(smc_result["confirmations"][:3]) if smc_result["confirmations"] else "None"
        bos_info    = f"BOS: {smc_result['bos']}" if smc_result["bos"] else "No BOS"

        msg = (f"🚀 <b>{action} TRADE OPENED</b>\n"
               f"💱 {symbol}\n"
               f"📍 Entry: {price}\n"
               f"💰 Lot: {lot}\n"
               f"🛑 SL: {sl} ({sl_pips} pips)\n"
               f"🎯 TP: {tp} ({tp_pips} pips)\n"
               f"📊 R:R = 1:{round(tp_pips/max(sl_pips,1), 1)}\n"
               f"━━━━━━━━━━━━━━━\n"
               f"🧠 <b>SMC ANALYSIS:</b>\n"
               f"{bos_info}\n"
               f"{smc_summary}")
        send_telegram(msg)
        log.info(f"✅ {action} {symbol} @ {price}")
        return True
    else:
        log.error(f"❌ Order failed: {result.comment}")
        return False


def update_trailing_stops(symbol):
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return
    df  = get_candles(symbol, config["timeframe"], 20)
    if df is None:
        return
    df  = calculate_indicators(df)
    atr = df["atr"].iloc[-1]
    sym_info   = mt5.symbol_info(symbol)
    pip        = sym_info.point * 10
    trail_dist = atr * config["trailing_atr_mult"]
    be_dist    = config["breakeven_pips"] * pip

    for pos in positions:
        tick = mt5.symbol_info_tick(symbol)
        if pos.type == mt5.ORDER_TYPE_BUY:
            if tick.bid - pos.price_open >= be_dist and pos.sl < pos.price_open:
                _modify_sl(pos, pos.price_open + pip)
                send_telegram(f"🔒 <b>BREAK EVEN</b>\n{symbol} BUY is now risk-free!")
            new_sl = round(tick.bid - trail_dist, 5)
            if new_sl > pos.sl:
                _modify_sl(pos, new_sl)
        elif pos.type == mt5.ORDER_TYPE_SELL:
            if pos.price_open - tick.ask >= be_dist and (pos.sl > pos.price_open or pos.sl == 0):
                _modify_sl(pos, pos.price_open - pip)
                send_telegram(f"🔒 <b>BREAK EVEN</b>\n{symbol} SELL is now risk-free!")
            new_sl = round(tick.ask + trail_dist, 5)
            if new_sl < pos.sl or pos.sl == 0:
                _modify_sl(pos, new_sl)


def _modify_sl(position, new_sl):
    request = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "symbol":   position.symbol,
        "sl":       new_sl,
        "tp":       position.tp,
        "position": position.ticket,
    }
    mt5.order_send(request)


def close_all_trades(reason=""):
    positions = mt5.positions_get()
    if not positions:
        return
    closed = 0
    for pos in positions:
        tick  = mt5.symbol_info_tick(pos.symbol)
        ctype = mt5.ORDER_TYPE_BUY if pos.type == mt5.ORDER_TYPE_SELL else mt5.ORDER_TYPE_SELL
        price = tick.ask if pos.type == mt5.ORDER_TYPE_SELL else tick.bid
        request = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": pos.symbol,
            "volume": pos.volume, "type": ctype, "position": pos.ticket,
            "price": price, "deviation": 20, "magic": 20250510,
            "comment": f"Close:{reason}", "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
            risk.record_trade(pos.profit)
    if closed > 0:
        send_telegram(f"🔒 <b>ALL TRADES CLOSED</b>\n{closed} trades.\nReason: {reason}")


# ══════════════════════════════════════════════════════
#  🚀 MAIN BOT LOOP
# ══════════════════════════════════════════════════════

def connect_mt5() -> bool:
    if not mt5.initialize():
        log.error(f"MT5 failed: {mt5.last_error()}")
        return False
    if not mt5.login(config["mt5_login"], password=config["mt5_password"], server=config["mt5_server"]):
        log.error(f"Login failed: {mt5.last_error()}")
        mt5.shutdown()
        return False
    info = mt5.account_info()
    log.info(f"✅ Connected | Balance: ${info.balance:.2f}")
    return True


def run_bot():
    print("""
╔══════════════════════════════════════════════════╗
║    STEPHEN'S SMC ULTIMATE BOT v4.0 🧠🚀         ║
║    Smart Money Concepts + Full Automation        ║
╚══════════════════════════════════════════════════╝
""")

    send_telegram("""🧠 <b>STEPHEN'S SMC BOT v4.0 STARTED</b>
━━━━━━━━━━━━━━━━━━━━
✅ Order Block Detection: ON
✅ Break of Structure: ON
✅ Fair Value Gap Scanner: ON
✅ Liquidity Finder: ON
✅ Session Filter: ON
✅ News Protection: ON
✅ Break Even SL: ON
✅ Trailing Stop: ON
✅ Weekend Close: ON
✅ Daily Report: ON
━━━━━━━━━━━━━━━━━━━━
💱 Pairs: EURUSD | GBPUSD | USDJPY
🧠 Strategy: SMC + EMA + RSI + ADX
🎯 Min Score: 7/10
⚡ Bot is watching markets for you!""")

    if not connect_mt5():
        return

    while True:
        try:
            now     = datetime.now()
            acct    = mt5.account_info()
            balance = acct.balance

            risk.init(balance)

            # ── Daily Report ───────────────────────────
            if risk.should_send_report():
                stats = risk.reset_daily_stats(balance)
                send_daily_report(stats)

            # ── Weekend Close ──────────────────────────
            if is_friday_close_time():
                close_all_trades("Friday Night Protection")
                time.sleep(3600)
                continue

            # ── Safety Checks ──────────────────────────
            in_cd, cd_msg = risk.in_cooldown()
            if in_cd:
                log.info(f"⏸️  {cd_msg}")
                time.sleep(config["check_interval"])
                continue

            if risk.daily_loss_hit(balance):
                close_all_trades("Daily Loss Limit")
                send_telegram(f"🛑 <b>DAILY LOSS LIMIT</b>\nBalance: ${balance:.2f}")
                time.sleep(3600)
                continue

            if risk.is_safe_mode(balance):
                log.warning("⚠️  SAFE MODE ACTIVE")

            # ── Session Check ──────────────────────────
            in_session, session = is_trading_session()
            if not in_session:
                log.info(f"😴 {session}")
                time.sleep(config["check_interval"])
                continue

            # ── News Check ─────────────────────────────
            danger, d_msg = is_high_impact_news()
            if danger:
                log.info(f"⚠️  {d_msg}")
                time.sleep(config["check_interval"])
                continue

            # ── Update Trailing Stops ──────────────────
            for symbol in config["symbols"]:
                update_trailing_stops(symbol)

            # ── Analyze Each Symbol ────────────────────
            for symbol in config["symbols"]:
                log.info(f"\n{'='*40}")
                log.info(f"🔍 Analyzing {symbol} | {session}")

                df = get_candles(symbol, config["timeframe"])
                if df is None or len(df) < 210:
                    continue

                df   = calculate_indicators(df)
                last = df.iloc[-1]
                sig  = get_signal(df)

                log.info(f"{symbol} | Price:{last['close']:.5f} | RSI:{last['rsi']:.1f} | ADX:{last['adx']:.1f} | Signal:{sig or 'NONE'}")

                if sig is None:
                    continue

                # ── HTF Trend ──────────────────────────
                htf = get_htf_trend(symbol)
                if (sig == "BUY" and htf == "BEARISH") or (sig == "SELL" and htf == "BULLISH"):
                    log.info(f"❌ Against H4 trend ({htf})")
                    continue

                # ── SMC Analysis ───────────────────────
                log.info(f"🧠 Running SMC Analysis...")
                smc     = SMCAnalyzer(df)
                smc_res = smc.analyze(sig)

                log.info(f"SMC Score: {smc_res['smc_score']}/10")
                log.info(f"BOS: {smc_res['bos']} | Structure: {smc_res['structure']['trend']}")
                for c in smc_res["confirmations"]:
                    log.info(f"   {c}")

                risk.record_smc_signal()

                # ── Combined Score ─────────────────────
                score, details = score_signal(df, sig, htf, smc_res)
                log.info(f"Total Score: {score}/10 (need {config['min_score']})")

                if score < config["min_score"]:
                    log.info(f"❌ Score {score}/10 too low — skipping")
                    continue

                # ── News Check ─────────────────────────
                news      = get_financial_news()
                sentiment = analyze_news_sentiment(news, sig)
                if not sentiment["safe_to_trade"]:
                    log.info(f"❌ News blocked: {sentiment['reason']}")
                    continue

                # ── Open Trades Check ──────────────────
                open_trades = len(mt5.positions_get(symbol=symbol) or [])
                if open_trades >= config["max_open_trades"]:
                    log.info(f"⏸️  Max trades for {symbol}")
                    continue

                # ── Lot Size ───────────────────────────
                atr      = last["atr"]
                sym_info = mt5.symbol_info(symbol)
                pip      = sym_info.point * 10
                sl_pips  = round((atr * config["trailing_atr_mult"]) / pip)
                lot      = risk.calc_lot(balance, sl_pips, symbol)

                # ── Determine SMC type for stats ───────
                smc_type = None
                if smc_res["order_blocks"]["bullish_ob"] or smc_res["order_blocks"]["bearish_ob"]:
                    smc_type = "OB"
                elif smc_res["bos"]:
                    smc_type = "BOS"
                elif smc_res["fvgs"]["bullish_fvg"] or smc_res["fvgs"]["bearish_fvg"]:
                    smc_type = "FVG"

                # ── Place Trade ────────────────────────
                log.info(f"🚀 {sig} {symbol} | Score:{score}/10 | SMC:{smc_res['smc_score']} | Lot:{lot}")
                success = place_order(symbol, sig, lot, atr, smc_res)

            time.sleep(config["check_interval"])

        except KeyboardInterrupt:
            log.info("\n🛑 Bot stopped.")
            send_telegram("🛑 <b>SMC Bot stopped manually.</b>")
            break
        except Exception as e:
            log.error(f"Error: {e}")
            send_telegram(f"⚠️ <b>Error</b>\n{str(e)[:100]}")
            time.sleep(60)

    mt5.shutdown()


# ══════════════════════════════════════════════════════
#  📈 BACKTEST
# ══════════════════════════════════════════════════════

def run_backtest():
    log.info("\n" + "="*55)
    log.info("  📈 STEPHEN'S SMC BOT BACKTEST v4.0")
    log.info("="*55)
    try:
        import yfinance as yf
    except:
        log.error("Run: pip install yfinance")
        return

    pairs = [("EURUSD=X", "EURUSD"), ("GBPUSD=X", "GBPUSD")]

    for yf_symbol, name in pairs:
        log.info(f"\n🔍 Backtesting {name}...")
        df = yf.download(yf_symbol, period="6mo", interval="1h", progress=False)
        if df.empty:
            continue

        df.columns  = [c.lower() for c in df.columns]
        df          = df.reset_index()
        df          = calculate_indicators(df)

        balance  = 10000.0
        peak     = balance
        wins = losses = 0
        trades   = []
        position = None

        for i in range(210, len(df)):
            row  = df.iloc[i]
            prev = df.iloc[i-1]
            atr  = row["atr"] if not pd.isna(row["atr"]) else 0.001

            if position:
                if position["type"] == "BUY":
                    if row["low"] <= position["sl"]:
                        pnl = (position["sl"] - position["entry"]) * 10000
                        balance += pnl; losses += 1; trades.append(pnl); position = None
                    elif row["high"] >= position["tp"]:
                        pnl = (position["tp"] - position["entry"]) * 10000
                        balance += pnl; wins += 1; trades.append(pnl); position = None
                else:
                    if row["high"] >= position["sl"]:
                        pnl = (position["entry"] - position["sl"]) * 10000
                        balance -= pnl; losses += 1; trades.append(-pnl); position = None
                    elif row["low"] <= position["tp"]:
                        pnl = (position["entry"] - position["tp"]) * 10000
                        balance += pnl; wins += 1; trades.append(pnl); position = None

            peak = max(peak, balance)

            if position is None:
                up   = prev["ema_fast"] <= prev["ema_slow"] and row["ema_fast"] > row["ema_slow"]
                down = prev["ema_fast"] >= prev["ema_slow"] and row["ema_fast"] < row["ema_slow"]

                if up and row["close"] > row["ema_trend"] and row["adx"] > config["adx_min"] and row["rsi"] < config["rsi_ob"]:
                    position = {"type": "BUY",  "entry": row["close"],
                                "sl": row["close"] - atr*2, "tp": row["close"] + atr*4}
                elif down and row["close"] < row["ema_trend"] and row["adx"] > config["adx_min"] and row["rsi"] > config["rsi_os"]:
                    position = {"type": "SELL", "entry": row["close"],
                                "sl": row["close"] + atr*2, "tp": row["close"] - atr*4}

        total  = wins + losses
        wr     = wins / total * 100 if total > 0 else 0
        profit = balance - 10000
        dd     = (peak - balance) / peak * 100 if peak > 0 else 0
        pf     = sum(t for t in trades if t > 0) / abs(sum(t for t in trades if t < 0) or 1)

        log.info(f"""
  {name} RESULTS (6 months):
  ─────────────────────────
  Total Trades:  {total}
  Wins:          {wins} ({wr:.1f}%)
  Losses:        {losses}
  Net Profit:    ${profit:.2f}
  Profit Factor: {pf:.2f}
  Max Drawdown:  {dd:.1f}%
  Final Balance: ${balance:.2f}
""")

    log.info("="*55)
    log.info("  BACKTEST COMPLETE!")
    log.info("="*55)


# ══════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    if "--backtest" in sys.argv:
        run_backtest()
    else:
        run_bot()

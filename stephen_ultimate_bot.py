"""
╔══════════════════════════════════════════════════════════════════╗
║           STEPHEN'S ULTIMATE FOREX BOT v3.0                     ║
║  The Most Powerful Free Forex Bot Ever Built                     ║
╠══════════════════════════════════════════════════════════════════╣
║  ✅ EMA 20/50/200 + RSI + ADX Strategy                          ║
║  ✅ Trading Session Filter (London & New York only)             ║
║  ✅ Economic Calendar — Avoids news events                      ║
║  ✅ Break Even Stop Loss                                        ║
║  ✅ Trailing Stop Loss                                          ║
║  ✅ Weekend Protection — Closes trades Friday night             ║
║  ✅ Daily Telegram Report                                       ║
║  ✅ Drawdown Recovery Safe Mode                                 ║
║  ✅ Auto Lot Adjustment                                         ║
║  ✅ Martingale Protection                                       ║
║  ✅ Multiple Currency Pairs                                     ║
║  ✅ Trend Strength Scoring (out of 10)                         ║
║  ✅ Fake Signal Filter                                          ║
║  ✅ Cooldown After Losses                                       ║
║  ✅ News Sentiment Analysis                                     ║
║  ✅ Risk Management                                             ║
╚══════════════════════════════════════════════════════════════════╝

INSTALL:
  pip install MetaTrader5 pandas numpy requests python-telegram-bot yfinance

RUN LIVE:
  python stephen_ultimate_bot.py

RUN BACKTEST:
  python stephen_ultimate_bot.py --backtest
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
#  ⚙️  STEPHEN'S CONFIG — FILL IN YOUR DETAILS
# ═══════════════════════════════════════════════════════
config = {
    # ── MT5 Account ──────────────────────────────────
    "mt5_login":    12345678,
    "mt5_password": "YourMT5Password",
    "mt5_server":   "Exness-MT5Real",

    # ── Telegram ─────────────────────────────────────
    "telegram_token":   "YOUR_TELEGRAM_TOKEN",
    "telegram_chat_id": "7781270946",

    # ── News API (free at newsapi.org) ────────────────
    "news_api_key": "YOUR_NEWSAPI_KEY",

    # ── Trading Pairs ─────────────────────────────────
    "symbols": ["EURUSD", "GBPUSD", "USDJPY"],

    # ── Timeframes ────────────────────────────────────
    "timeframe": mt5.TIMEFRAME_H1,   # Main: 1 hour
    "htf":       mt5.TIMEFRAME_H4,   # Trend filter: 4 hour

    # ── Risk Management ───────────────────────────────
    "risk_pct":          1.0,   # Risk 1% per trade
    "max_daily_loss":    3.0,   # Stop if daily loss > 3%
    "max_drawdown":      10.0,  # Safe mode if drawdown > 10%
    "max_open_trades":   2,     # Max trades at once
    "safe_mode_risk":    0.5,   # Risk % in safe mode

    # ── Strategy Indicators ───────────────────────────
    "ema_fast":   20,
    "ema_slow":   50,
    "ema_trend":  200,
    "rsi_period": 14,
    "rsi_ob":     65,
    "rsi_os":     35,
    "adx_min":    25,
    "atr_period": 14,

    # ── Trade Management ──────────────────────────────
    "trailing_atr_mult":  2.0,  # Trail stop at 2x ATR
    "tp_atr_mult":        4.0,  # Take profit at 4x ATR
    "breakeven_pips":     20,   # Move SL to BE after 20 pips profit

    # ── Signal Quality ────────────────────────────────
    "min_score":      7,    # Minimum score out of 10 to trade
    "confluence_min": 4,    # Minimum confirmations needed
    "min_body_pct":   40,   # Candle body strength

    # ── Cooldown & Protection ─────────────────────────
    "cooldown_after_loss":  2,    # Pause after 2 losses
    "cooldown_minutes":     120,  # Pause for 2 hours
    "martingale_trigger":   3,    # Reduce lot after 3 losses

    # ── Session Filter (EAT = UTC+3) ──────────────────
    "london_open":   10,   # 10am EAT
    "london_close":  19,   # 7pm EAT
    "newyork_open":  15,   # 3pm EAT
    "newyork_close": 24,   # Midnight EAT

    # ── News Protection ───────────────────────────────
    "news_avoid_minutes": 60,

    # ── Weekend Protection ────────────────────────────
    "friday_close_hour": 21,  # Close all trades at 9pm EAT Friday

    # ── Daily Report Time ─────────────────────────────
    "report_hour": 23,   # Send report at 11pm EAT

    # ── Check Interval ────────────────────────────────
    "check_interval": 300,  # Every 5 minutes
}
# ═══════════════════════════════════════════════════════


# ── Logging Setup ─────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("stephen_bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════
#  📱 TELEGRAM MODULE
# ══════════════════════════════════════════════════════

def send_telegram(message: str):
    """Send alert to Stephen's Telegram."""
    try:
        url  = f"https://api.telegram.org/bot{config['telegram_token']}/sendMessage"
        data = {
            "chat_id":    config["telegram_chat_id"],
            "text":       message,
            "parse_mode": "HTML"
        }
        requests.post(url, data=data, timeout=10)
        log.info(f"📱 Telegram sent")
    except Exception as e:
        log.warning(f"Telegram failed: {e}")


def send_daily_report(stats: dict):
    """Send daily performance report to Telegram."""
    now      = datetime.now()
    tomorrow = now + timedelta(days=1)

    # Check tomorrow's news danger
    danger_times = ["NFP", "CPI", "FOMC", "GDP", "PMI"]
    news         = get_financial_news()
    news_warning = ""
    for article in news:
        if any(d in article["title"] for d in danger_times):
            news_warning = "⚠️ High impact news tomorrow — bot will be careful!"
            break

    report = f"""
📊 <b>STEPHEN'S DAILY REPORT</b>
📅 {now.strftime('%d %B %Y')}
━━━━━━━━━━━━━━━━━━━━
📈 Trades Today:  {stats.get('trades', 0)}
✅ Wins:          {stats.get('wins', 0)}
❌ Losses:        {stats.get('losses', 0)}
🎯 Win Rate:      {stats.get('win_rate', 0):.1f}%
💰 Profit:        ${stats.get('profit', 0):.2f}
💼 Balance:       ${stats.get('balance', 0):.2f}
📈 Best Trade:    ${stats.get('best_trade', 0):.2f}
📉 Worst Trade:   ${stats.get('worst_trade', 0):.2f}
━━━━━━━━━━━━━━━━━━━━
{news_warning}
🌅 Bot continues tomorrow...
"""
    send_telegram(report)


# ══════════════════════════════════════════════════════
#  ⏰ SESSION FILTER MODULE
# ══════════════════════════════════════════════════════

def is_trading_session() -> tuple:
    """
    Only trade during London and New York sessions.
    Times in EAT (UTC+3)
    """
    now     = datetime.now()
    hour    = now.hour
    weekday = now.weekday()  # 0=Monday, 6=Sunday

    # No trading on weekends
    if weekday >= 5:
        return False, "Weekend — markets closed"

    # London session: 10am - 7pm EAT
    london   = config["london_open"] <= hour < config["london_close"]

    # New York session: 3pm - midnight EAT
    newyork  = config["newyork_open"] <= hour < config["newyork_close"]

    if london and not newyork:
        return True, "🇬🇧 London Session"
    elif newyork and not london:
        return True, "🇺🇸 New York Session"
    elif london and newyork:
        return True, "🇬🇧🇺🇸 London + New York Overlap (Best!)"
    else:
        return False, f"Asian Session — waiting for London (10am EAT)"


def is_friday_close_time() -> bool:
    """Check if it's Friday night — time to close all trades."""
    now = datetime.now()
    return now.weekday() == 4 and now.hour >= config["friday_close_hour"]


# ══════════════════════════════════════════════════════
#  📰 NEWS MODULE
# ══════════════════════════════════════════════════════

def get_financial_news() -> list:
    """Fetch latest financial news."""
    try:
        url    = "https://newsapi.org/v2/everything"
        params = {
            "q":        "forex EURUSD GBPUSD interest rate Federal Reserve ECB",
            "language": "en",
            "sortBy":   "publishedAt",
            "pageSize": 10,
            "apiKey":   config["news_api_key"]
        }
        r        = requests.get(url, params=params, timeout=10)
        articles = r.json().get("articles", [])
        return [{"title": a["title"], "published": a["publishedAt"]} for a in articles]
    except Exception as e:
        log.warning(f"News fetch failed: {e}")
        return []


def is_high_impact_news() -> tuple:
    """Check if we're near a dangerous news event."""
    now  = datetime.now()
    hour = now.hour

    # High impact news times (EAT = UTC+3)
    danger_times = [
        (11, 30, "London Open News"),
        (16, 30, "US News Release"),
        (18, 0,  "Fed/ECB Speeches"),
        (21, 0,  "US Afternoon News"),
    ]

    for h, m, name in danger_times:
        event_mins = h * 60 + m
        now_mins   = hour * 60 + now.minute
        if abs(now_mins - event_mins) <= config["news_avoid_minutes"]:
            return True, f"⚠️ Danger zone: {name}"

    return False, ""


def analyze_news_sentiment(news: list, signal: str) -> dict:
    """Analyze news headlines for sentiment."""
    if not news:
        return {"safe_to_trade": True, "reason": "No news available"}

    bullish = ["rate hike", "strong", "growth", "beat", "surge", "rally", "gain", "positive"]
    bearish = ["rate cut", "weak", "recession", "miss", "crash", "drop", "fall", "crisis", "war"]
    danger  = ["NFP", "nonfarm", "CPI", "inflation", "fed decision", "rate decision", "FOMC", "GDP"]

    bull_score = bear_score = 0
    is_danger  = False

    for article in news:
        title = article["title"].lower()
        bull_score += sum(1 for w in bullish if w in title)
        bear_score += sum(1 for w in bearish if w in title)
        if any(d.lower() in title for d in danger):
            is_danger = True

    if is_danger:
        return {"safe_to_trade": False, "reason": "High impact news detected"}

    if signal == "BUY" and bear_score > bull_score + 2:
        return {"safe_to_trade": False, "reason": f"Bearish news sentiment ({bear_score} vs {bull_score})"}

    if signal == "SELL" and bull_score > bear_score + 2:
        return {"safe_to_trade": False, "reason": f"Bullish news sentiment ({bull_score} vs {bear_score})"}

    return {"safe_to_trade": True, "reason": f"News OK (Bull:{bull_score} Bear:{bear_score})"}


# ══════════════════════════════════════════════════════
#  📊 INDICATORS MODULE
# ══════════════════════════════════════════════════════

def get_candles(symbol, timeframe, count=300):
    """Fetch candles from MT5."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all indicators."""
    # EMAs
    df["ema_fast"]  = df["close"].ewm(span=config["ema_fast"],  adjust=False).mean()
    df["ema_slow"]  = df["close"].ewm(span=config["ema_slow"],  adjust=False).mean()
    df["ema_trend"] = df["close"].ewm(span=config["ema_trend"], adjust=False).mean()

    # RSI
    delta    = df["close"].diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=config["rsi_period"] - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=config["rsi_period"] - 1, adjust=False).mean()
    rs       = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR
    df["tr"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift()),
            abs(df["low"]  - df["close"].shift())
        )
    )
    df["atr"] = df["tr"].rolling(config["atr_period"]).mean()

    # ADX
    df["+dm"] = np.where(
        (df["high"] - df["high"].shift()) > (df["low"].shift() - df["low"]),
        np.maximum(df["high"] - df["high"].shift(), 0), 0
    )
    df["-dm"] = np.where(
        (df["low"].shift() - df["low"]) > (df["high"] - df["high"].shift()),
        np.maximum(df["low"].shift() - df["low"], 0), 0
    )
    df["+di"] = 100 * (df["+dm"].ewm(span=14, adjust=False).mean() / (df["atr"] + 1e-10))
    df["-di"] = 100 * (df["-dm"].ewm(span=14, adjust=False).mean() / (df["atr"] + 1e-10))
    df["dx"]  = 100 * abs(df["+di"] - df["-di"]) / (df["+di"] + df["-di"] + 1e-10)
    df["adx"] = df["dx"].ewm(span=14, adjust=False).mean()

    # Body strength
    df["body_pct"] = abs(df["close"] - df["open"]) / (df["high"] - df["low"] + 1e-10) * 100

    return df


def get_htf_trend(symbol) -> str:
    """Get H4 trend direction."""
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


# ══════════════════════════════════════════════════════
#  🎯 TREND STRENGTH SCORING (out of 10)
# ══════════════════════════════════════════════════════

def score_signal(df: pd.DataFrame, direction: str, htf_trend: str) -> tuple:
    """
    Score the signal quality out of 10.
    Minimum 7/10 required to place trade.
    """
    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    score = 0
    details = []

    if direction == "BUY":
        # 1. EMA crossover (2 points — most important)
        if prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]:
            score += 2; details.append("✅ EMA crossover bullish (+2)")

        # 2. Price above EMA200
        if last["close"] > last["ema_trend"]:
            score += 1; details.append("✅ Above EMA200 (+1)")

        # 3. H4 trend agrees
        if htf_trend == "BULLISH":
            score += 2; details.append("✅ H4 trend bullish (+2)")

        # 4. RSI good zone
        if 40 < last["rsi"] < config["rsi_ob"]:
            score += 1; details.append(f"✅ RSI good ({last['rsi']:.0f}) (+1)")

        # 5. Strong ADX
        if last["adx"] > config["adx_min"]:
            score += 1; details.append(f"✅ ADX strong ({last['adx']:.0f}) (+1)")

        # 6. Bullish candle body
        if last["body_pct"] > config["min_body_pct"] and last["close"] > last["open"]:
            score += 1; details.append("✅ Strong bull candle (+1)")

        # 7. EMA slope rising
        if last["ema_fast"] > df.iloc[-3]["ema_fast"]:
            score += 1; details.append("✅ EMA rising (+1)")

        # Negative checks
        if last["rsi"] > config["rsi_ob"]:
            score -= 1; details.append("❌ RSI overbought (-1)")

    else:  # SELL
        if prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]:
            score += 2; details.append("✅ EMA crossover bearish (+2)")
        if last["close"] < last["ema_trend"]:
            score += 1; details.append("✅ Below EMA200 (+1)")
        if htf_trend == "BEARISH":
            score += 2; details.append("✅ H4 trend bearish (+2)")
        if config["rsi_os"] < last["rsi"] < 60:
            score += 1; details.append(f"✅ RSI good ({last['rsi']:.0f}) (+1)")
        if last["adx"] > config["adx_min"]:
            score += 1; details.append(f"✅ ADX strong ({last['adx']:.0f}) (+1)")
        if last["body_pct"] > config["min_body_pct"] and last["close"] < last["open"]:
            score += 1; details.append("✅ Strong bear candle (+1)")
        if last["ema_fast"] < df.iloc[-3]["ema_fast"]:
            score += 1; details.append("✅ EMA falling (+1)")
        if last["rsi"] < config["rsi_os"]:
            score -= 1; details.append("❌ RSI oversold (-1)")

    score = max(0, min(score, 10))
    return score, details


def get_signal(df: pd.DataFrame) -> str:
    """Get raw EMA crossover signal."""
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]:
        return "BUY"
    if prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]:
        return "SELL"
    return None


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
            "trades": 0, "wins": 0, "losses": 0,
            "profit": 0.0, "best_trade": 0.0, "worst_trade": 0.0
        }
        self.last_report_day    = None

    def init(self, balance):
        if self.start_balance is None:
            self.start_balance = balance
            self.peak_balance  = balance
        self.peak_balance = max(self.peak_balance, balance)

    def record_trade(self, profit):
        self.daily_stats["trades"] += 1
        self.daily_stats["profit"] += profit
        self.daily_stats["best_trade"]  = max(self.daily_stats["best_trade"], profit)
        self.daily_stats["worst_trade"] = min(self.daily_stats["worst_trade"], profit)

        if profit > 0:
            self.daily_stats["wins"]  += 1
            self.consecutive_losses    = 0
            self.safe_mode             = False
        else:
            self.daily_stats["losses"] += 1
            self.consecutive_losses    += 1
            if self.consecutive_losses >= config["cooldown_after_loss"]:
                self.cooldown_until = datetime.now() + timedelta(minutes=config["cooldown_minutes"])
                send_telegram(f"⏸ <b>COOLDOWN</b>\n{self.consecutive_losses} losses in a row.\nPausing {config['cooldown_minutes']} minutes.")

    def in_cooldown(self):
        if self.cooldown_until and datetime.now() < self.cooldown_until:
            mins = int((self.cooldown_until - datetime.now()).total_seconds() / 60)
            return True, f"Cooldown: {mins} min remaining"
        self.cooldown_until = None
        return False, ""

    def is_safe_mode(self, balance):
        if self.peak_balance:
            dd = (self.peak_balance - balance) / self.peak_balance * 100
            if dd >= config["max_drawdown"]:
                self.safe_mode = True
                return True
        return self.safe_mode

    def daily_loss_hit(self, balance):
        if self.start_balance:
            return ((self.start_balance - balance) / self.start_balance * 100) >= config["max_daily_loss"]
        return False

    def get_risk_pct(self, consecutive_losses):
        """Reduce risk after consecutive losses."""
        if self.safe_mode:
            return config["safe_mode_risk"]
        if consecutive_losses >= config["martingale_trigger"]:
            return config["risk_pct"] * 0.5
        return config["risk_pct"]

    def calc_lot(self, balance, sl_pips, symbol):
        """Dynamic lot size based on risk %."""
        risk_pct    = self.get_risk_pct(self.consecutive_losses)
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
        wins  = self.daily_stats["wins"]
        total = self.daily_stats["trades"]
        stats["win_rate"] = (wins / total * 100) if total > 0 else 0
        self.daily_stats  = {
            "trades": 0, "wins": 0, "losses": 0,
            "profit": 0.0, "best_trade": 0.0, "worst_trade": 0.0
        }
        self.start_balance = balance
        return stats


risk = RiskManager()


# ══════════════════════════════════════════════════════
#  🔄 TRADE MANAGEMENT
# ══════════════════════════════════════════════════════

def place_order(symbol, action, lot, atr):
    """Place trade with SL and TP."""
    tick     = mt5.symbol_info_tick(symbol)
    sym_info = mt5.symbol_info(symbol)
    pip      = sym_info.point * 10
    sl_dist  = atr * config["trailing_atr_mult"]
    tp_dist  = atr * config["tp_atr_mult"]

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
        "comment":      "Stephen Bot v3",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        msg = (f"🚀 <b>{action} TRADE OPENED</b>\n"
               f"💱 {symbol}\n"
               f"📍 Entry: {price}\n"
               f"💰 Lot: {lot}\n"
               f"🛑 Stop Loss: {sl} ({sl_pips} pips)\n"
               f"🎯 Take Profit: {tp} ({tp_pips} pips)\n"
               f"📊 R:R = 1:{round(tp_pips/max(sl_pips,1), 1)}")
        send_telegram(msg)
        log.info(f"✅ {action} {symbol} @ {price}")
        return True
    else:
        log.error(f"❌ Order failed: {result.comment}")
        return False


def update_trailing_stops(symbol):
    """Trail stop loss and move to break even."""
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return

    df  = get_candles(symbol, config["timeframe"], 20)
    if df is None:
        return
    df  = calculate_indicators(df)
    atr = df["atr"].iloc[-1]

    sym_info  = mt5.symbol_info(symbol)
    pip       = sym_info.point * 10
    trail_dist = atr * config["trailing_atr_mult"]
    be_dist   = config["breakeven_pips"] * pip

    for pos in positions:
        tick = mt5.symbol_info_tick(symbol)

        if pos.type == mt5.ORDER_TYPE_BUY:
            # Break even
            if tick.bid - pos.price_open >= be_dist and pos.sl < pos.price_open:
                _modify_sl(pos, pos.price_open + pip)
                send_telegram(f"🔒 <b>BREAK EVEN SET</b>\n{symbol} BUY trade is now risk-free!")
            # Trail stop
            new_sl = round(tick.bid - trail_dist, 5)
            if new_sl > pos.sl:
                _modify_sl(pos, new_sl)

        elif pos.type == mt5.ORDER_TYPE_SELL:
            # Break even
            if pos.price_open - tick.ask >= be_dist and (pos.sl > pos.price_open or pos.sl == 0):
                _modify_sl(pos, pos.price_open - pip)
                send_telegram(f"🔒 <b>BREAK EVEN SET</b>\n{symbol} SELL trade is now risk-free!")
            # Trail stop
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
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        log.info(f"🔄 SL updated #{position.ticket} → {new_sl:.5f}")


def close_all_trades(reason=""):
    """Close all open trades."""
    positions = mt5.positions_get()
    if not positions:
        return

    closed = 0
    for pos in positions:
        tick  = mt5.symbol_info_tick(pos.symbol)
        ctype = mt5.ORDER_TYPE_BUY if pos.type == mt5.ORDER_TYPE_SELL else mt5.ORDER_TYPE_SELL
        price = tick.ask if pos.type == mt5.ORDER_TYPE_SELL else tick.bid

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       pos.symbol,
            "volume":       pos.volume,
            "type":         ctype,
            "position":     pos.ticket,
            "price":        price,
            "deviation":    20,
            "magic":        20250510,
            "comment":      f"Close: {reason}",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
            risk.record_trade(pos.profit)

    if closed > 0:
        send_telegram(f"🔒 <b>ALL TRADES CLOSED</b>\n{closed} trades closed.\nReason: {reason}")
        log.info(f"Closed {closed} trades. Reason: {reason}")


# ══════════════════════════════════════════════════════
#  🔌 MT5 CONNECTION
# ══════════════════════════════════════════════════════

def connect_mt5() -> bool:
    if not mt5.initialize():
        log.error(f"MT5 failed: {mt5.last_error()}")
        return False
    if not mt5.login(config["mt5_login"], password=config["mt5_password"], server=config["mt5_server"]):
        log.error(f"MT5 login failed: {mt5.last_error()}")
        mt5.shutdown()
        return False
    info = mt5.account_info()
    log.info(f"✅ MT5 Connected | Balance: ${info.balance:.2f}")
    return True


# ══════════════════════════════════════════════════════
#  🚀 MAIN BOT LOOP
# ══════════════════════════════════════════════════════

def run_bot():
    print("""
╔══════════════════════════════════════════════╗
║    STEPHEN'S ULTIMATE FOREX BOT v3.0 🚀     ║
║    The Most Powerful Free Bot Ever Built     ║
╚══════════════════════════════════════════════╝
""")

    send_telegram("""🚀 <b>STEPHEN'S BOT STARTED v3.0</b>
━━━━━━━━━━━━━━━━━━━━
✅ Session Filter: ON
✅ News Protection: ON
✅ Break Even SL: ON
✅ Trailing Stop: ON
✅ Weekend Close: ON
✅ Daily Report: ON
✅ Safe Mode: ON
━━━━━━━━━━━━━━━━━━━━
Monitoring: EURUSD | GBPUSD | USDJPY
Bot is now watching the markets for you! 👀""")

    if not connect_mt5():
        log.error("Cannot connect to MT5. Check your details.")
        return

    while True:
        try:
            now     = datetime.now()
            acct    = mt5.account_info()
            balance = acct.balance
            equity  = acct.equity

            risk.init(balance)

            # ── Send Daily Report ──────────────────────
            if risk.should_send_report():
                stats = risk.reset_daily_stats(balance)
                send_daily_report(stats)

            # ── Weekend Close ──────────────────────────
            if is_friday_close_time():
                close_all_trades("Friday Night — Weekend Protection")
                log.info("🌙 Friday night. All trades closed. Bot resting until Monday.")
                time.sleep(3600)
                continue

            # ── Safety Checks ──────────────────────────
            in_cd, cd_msg = risk.in_cooldown()
            if in_cd:
                log.info(f"⏸️  {cd_msg}")
                time.sleep(config["check_interval"])
                continue

            if risk.daily_loss_hit(balance):
                close_all_trades("Daily Loss Limit Hit")
                send_telegram(f"🛑 <b>DAILY LOSS LIMIT HIT</b>\nBot stopped for today.\nBalance: ${balance:.2f}")
                log.warning("Daily loss limit hit. Stopping for today.")
                time.sleep(3600)
                continue

            if risk.is_safe_mode(balance):
                log.warning("⚠️  SAFE MODE — Reduced lot size active")

            # ── Session Check ──────────────────────────
            in_session, session_name = is_trading_session()
            if not in_session:
                log.info(f"😴 {session_name}")
                time.sleep(config["check_interval"])
                continue

            # ── News Check ────────────────────────────
            is_danger, danger_msg = is_high_impact_news()
            if is_danger:
                log.info(f"⚠️  {danger_msg}")
                time.sleep(config["check_interval"])
                continue

            # ── Update Trailing Stops ──────────────────
            for symbol in config["symbols"]:
                update_trailing_stops(symbol)

            # ── Check Each Symbol ─────────────────────
            for symbol in config["symbols"]:
                log.info(f"\n--- Checking {symbol} | {session_name} ---")

                df = get_candles(symbol, config["timeframe"])
                if df is None:
                    continue

                df   = calculate_indicators(df)
                last = df.iloc[-1]
                sig  = get_signal(df)

                log.info(f"{symbol} | Price:{last['close']:.5f} | "
                         f"RSI:{last['rsi']:.1f} | ADX:{last['adx']:.1f} | "
                         f"Signal:{sig or 'NONE'}")

                if sig is None:
                    continue

                # ── HTF Trend Filter ───────────────────
                htf = get_htf_trend(symbol)
                if (sig == "BUY" and htf == "BEARISH") or (sig == "SELL" and htf == "BULLISH"):
                    log.info(f"❌ {symbol} — Against H4 trend ({htf})")
                    continue

                # ── Score Signal ───────────────────────
                score, details = score_signal(df, sig, htf)
                log.info(f"Signal Score: {score}/10 (need {config['min_score']})")
                for d in details:
                    log.info(f"   {d}")

                if score < config["min_score"]:
                    log.info(f"❌ Score too low ({score}/10) — skipping")
                    continue

                # ── News Sentiment ─────────────────────
                news      = get_financial_news()
                sentiment = analyze_news_sentiment(news, sig)
                if not sentiment["safe_to_trade"]:
                    log.info(f"❌ News blocked: {sentiment['reason']}")
                    continue

                # ── Open Trades Check ──────────────────
                open_trades = len(mt5.positions_get(symbol=symbol) or [])
                if open_trades >= config["max_open_trades"]:
                    log.info(f"⏸️  Max trades reached for {symbol}")
                    continue

                # ── Calculate Lot ──────────────────────
                atr     = last["atr"]
                sym_info = mt5.symbol_info(symbol)
                pip      = sym_info.point * 10
                sl_pips  = round((atr * config["trailing_atr_mult"]) / pip)
                lot      = risk.calc_lot(balance, sl_pips, symbol)

                # ── Place Trade ────────────────────────
                log.info(f"🚀 {symbol} {sig} | Score:{score}/10 | Lot:{lot}")
                success = place_order(symbol, sig, lot, atr)

            time.sleep(config["check_interval"])

        except KeyboardInterrupt:
            log.info("\n🛑 Bot stopped by Stephen.")
            send_telegram("🛑 <b>Bot stopped manually.</b>")
            break
        except Exception as e:
            log.error(f"Error: {e}")
            send_telegram(f"⚠️ <b>Bot Error</b>\n{str(e)[:100]}")
            time.sleep(60)

    mt5.shutdown()
    log.info("Disconnected from MT5.")


# ══════════════════════════════════════════════════════
#  📈 BACKTEST
# ══════════════════════════════════════════════════════

def run_backtest():
    log.info("\n" + "="*55 + "\n  📈 STEPHEN'S BOT BACKTEST\n" + "="*55)
    try:
        import yfinance as yf
    except:
        log.error("Run: pip install yfinance")
        return

    results = []
    for symbol in ["EURUSD=X", "GBPUSD=X", "JPY=X"]:
        log.info(f"\nTesting {symbol}...")
        df = yf.download(symbol, period="6mo", interval="1h", progress=False)
        if df.empty:
            continue

        df.columns = [c.lower() for c in df.columns]
        df         = df.reset_index()
        df         = calculate_indicators(df)

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
                                "sl": row["close"] - atr * 2, "tp": row["close"] + atr * 4}
                elif down and row["close"] < row["ema_trend"] and row["adx"] > config["adx_min"] and row["rsi"] > config["rsi_os"]:
                    position = {"type": "SELL", "entry": row["close"],
                                "sl": row["close"] + atr * 2, "tp": row["close"] - atr * 4}

        total  = wins + losses
        wr     = wins / total * 100 if total > 0 else 0
        profit = balance - 10000
        dd     = (peak - balance) / peak * 100 if peak > 0 else 0
        pf     = sum(t for t in trades if t > 0) / abs(sum(t for t in trades if t < 0) or 1)

        log.info(f"""
  {symbol} RESULTS:
  Trades: {total} | Wins: {wins} ({wr:.1f}%) | Losses: {losses}
  Profit: ${profit:.2f} | Profit Factor: {pf:.2f} | Drawdown: {dd:.1f}%
""")
        results.append({"symbol": symbol, "profit": profit, "win_rate": wr})

    log.info("="*55 + "\n  BACKTEST COMPLETE\n" + "="*55)
    return results


# ══════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    if "--backtest" in sys.argv:
        run_backtest()
    else:
        run_bot()

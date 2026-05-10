"""
╔══════════════════════════════════════════════════════════════╗
║         ADVANCED CLAUDE AI FOREX TRADING BOT v2.0           ║
║  Features: Risk Management | EMA+RSI Strategy | Trailing SL ║
║  News Sentiment | Fake Signal Filter | Telegram | Backtest  ║
╚══════════════════════════════════════════════════════════════╝

INSTALL REQUIREMENTS:
  pip install MetaTrader5 anthropic pandas numpy requests flask python-telegram-bot

SETUP:
  1. Fill in your config below
  2. Run: python advanced_bot.py
  3. Add --backtest flag to test first: python advanced_bot.py --backtest
"""

import MetaTrader5 as mt5
import anthropic
import pandas as pd
import numpy as np
import requests
import json
import time
import sys
import logging
from datetime import datetime, timedelta
from collections import deque

# ═══════════════════════════════════════════════
#  ⚙️  CONFIGURATION — FILL THESE IN
# ═══════════════════════════════════════════════
config = {
    # MT5 Account
    "mt5_login":    12345678,
    "mt5_password": "YourPassword",
    "mt5_server":   "Exness-MT5Real",

    # Claude AI
    "anthropic_key": "sk-ant-YOUR_KEY_HERE",

    # Telegram Alerts (create bot via @BotFather on Telegram)
    "telegram_token":   "YOUR_BOT_TOKEN",
    "telegram_chat_id": "YOUR_CHAT_ID",

    # News API (free at newsapi.org)
    "news_api_key": "YOUR_NEWSAPI_KEY",

    # Trading Settings
    "symbol":       "EURUSD",
    "timeframe":    mt5.TIMEFRAME_H1,   # 1-hour (better for long-term)
    "htf":          mt5.TIMEFRAME_H4,   # Higher timeframe for trend filter

    # Risk Management
    "risk_pct":         1.0,    # Risk 1% of balance per trade
    "max_daily_loss":   3.0,    # Stop trading if daily loss > 3%
    "max_drawdown":     10.0,   # Stop bot if drawdown > 10%
    "max_open_trades":  2,      # Max simultaneous trades

    # Strategy Indicators
    "ema_fast":   20,
    "ema_slow":   50,
    "ema_trend":  200,          # 200 EMA = long-term trend filter
    "rsi_period": 14,
    "rsi_ob":     65,           # Overbought (lowered for long-term)
    "rsi_os":     35,           # Oversold (raised for long-term)
    "adx_period": 14,
    "adx_min":    25,           # Only trade when ADX > 25 (strong trend)
    "atr_period": 14,

    # Trailing Stop
    "trailing_atr_mult": 2.0,   # Trail stop at 2x ATR
    "tp_atr_mult":       4.0,   # Take profit at 4x ATR (good R:R)

    # Fake Signal Protection
    "min_body_pct":      40,    # Candle body must be > 40% of range
    "confluence_min":    4,     # Need at least 4 confirmations to trade
    "volume_mult":       1.2,   # Volume must be 1.2x average

    # Cooldown After Losses
    "cooldown_after_loss":       2,    # Pause after N consecutive losses
    "cooldown_minutes":          120,  # Pause for 2 hours

    # News Protection
    "news_avoid_minutes":        60,   # Avoid trading 60 min before/after high-impact news
    "news_currencies":           ["USD", "EUR"],

    # Check interval
    "check_interval":    300,   # Check every 5 minutes
}
# ═══════════════════════════════════════════════

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("advanced_bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

claude_client = anthropic.Anthropic(api_key=config["anthropic_key"])


# ══════════════════════════════════════════
#  📱 TELEGRAM ALERTS
# ══════════════════════════════════════════

def send_telegram(message: str):
    """Send message to your Telegram."""
    try:
        url = f"https://api.telegram.org/bot{config['telegram_token']}/sendMessage"
        data = {"chat_id": config["telegram_chat_id"], "text": message, "parse_mode": "HTML"}
        requests.post(url, data=data, timeout=10)
        log.info(f"📱 Telegram sent: {message[:60]}...")
    except Exception as e:
        log.warning(f"Telegram failed: {e}")


# ══════════════════════════════════════════
#  📰 NEWS & SENTIMENT MODULE
# ══════════════════════════════════════════

def get_financial_news() -> list:
    """Fetch latest forex/financial news from NewsAPI."""
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": "forex EURUSD interest rate Federal Reserve ECB",
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 10,
            "apiKey": config["news_api_key"]
        }
        r = requests.get(url, params=params, timeout=10)
        articles = r.json().get("articles", [])
        return [{"title": a["title"], "description": a.get("description", ""), "published": a["publishedAt"]} for a in articles]
    except Exception as e:
        log.warning(f"News fetch failed: {e}")
        return []


def get_economic_calendar() -> list:
    """
    Fetch high-impact economic events.
    Uses a free calendar API endpoint.
    Returns list of upcoming high-impact events.
    """
    try:
        # Free economic calendar (no API key needed)
        url = "https://economic-calendar.tradingview.com/events"
        params = {
            "from": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
            "to":   (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S"),
            "countries": "US,EU",
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        events = r.json().get("result", [])
        high_impact = [e for e in events if e.get("importance") == 3]
        return high_impact
    except Exception as e:
        log.warning(f"Calendar fetch failed: {e}")
        return []


def is_news_time() -> tuple:
    """
    Check if we're within danger zone of a high-impact news event.
    Returns (is_danger, reason)
    """
    events = get_economic_calendar()
    now = datetime.utcnow()
    avoid_window = config["news_avoid_minutes"]

    for event in events:
        try:
            event_time = datetime.strptime(event.get("date", ""), "%Y-%m-%dT%H:%M:%S")
            diff_minutes = abs((event_time - now).total_seconds() / 60)
            currency = event.get("currency", "")

            if currency in config["news_currencies"] and diff_minutes < avoid_window:
                return True, f"High-impact news in {int(diff_minutes)} min: {event.get('title', 'Event')}"
        except:
            continue

    return False, ""


def analyze_news_sentiment(news_articles: list, signal: str) -> dict:
    """Ask Claude AI to analyze news sentiment and validate the trade signal."""
    if not news_articles:
        return {"sentiment": "NEUTRAL", "safe_to_trade": True, "reason": "No news data available"}

    headlines = "\n".join([f"- {a['title']}" for a in news_articles[:8]])

    prompt = f"""
You are a professional Forex market analyst. Analyze these recent financial news headlines
and determine the market sentiment for EURUSD.

=== RECENT NEWS ===
{headlines}

=== TRADE SIGNAL ===
The trading bot wants to place a {signal} trade on EURUSD.

Analyze:
1. Overall market sentiment (BULLISH, BEARISH, or NEUTRAL)
2. Whether news supports or contradicts the {signal} signal
3. Any dangerous events (rate decisions, NFP, inflation data) that make trading risky

Respond ONLY in this exact JSON:
{{
  "sentiment": "BULLISH" or "BEARISH" or "NEUTRAL",
  "supports_signal": true or false,
  "risk_level": "LOW", "MEDIUM", or "HIGH",
  "safe_to_trade": true or false,
  "reason": "One sentence explanation"
}}
"""
    try:
        response = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip().replace("```json", "").replace("```", "")
        return json.loads(raw)
    except Exception as e:
        log.warning(f"Claude news analysis failed: {e}")
        return {"sentiment": "NEUTRAL", "safe_to_trade": True, "reason": "Analysis unavailable"}


# ══════════════════════════════════════════
#  📊 INDICATORS MODULE
# ══════════════════════════════════════════

def get_candles(symbol, timeframe, count=300) -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all technical indicators."""
    # EMAs
    df["ema_fast"]  = df["close"].ewm(span=config["ema_fast"],  adjust=False).mean()
    df["ema_slow"]  = df["close"].ewm(span=config["ema_slow"],  adjust=False).mean()
    df["ema_trend"] = df["close"].ewm(span=config["ema_trend"], adjust=False).mean()

    # RSI
    delta = df["close"].diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=config["rsi_period"] - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=config["rsi_period"] - 1, adjust=False).mean()
    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR (for position sizing & trailing stop)
    df["tr"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(abs(df["high"] - df["close"].shift()), abs(df["low"] - df["close"].shift()))
    )
    df["atr"] = df["tr"].rolling(config["atr_period"]).mean()

    # ADX (trend strength)
    df["+dm"] = np.where((df["high"] - df["high"].shift()) > (df["low"].shift() - df["low"]),
                         np.maximum(df["high"] - df["high"].shift(), 0), 0)
    df["-dm"] = np.where((df["low"].shift() - df["low"]) > (df["high"] - df["high"].shift()),
                         np.maximum(df["low"].shift() - df["low"], 0), 0)
    df["+di"] = 100 * (df["+dm"].ewm(span=config["adx_period"], adjust=False).mean() / df["atr"])
    df["-di"] = 100 * (df["-dm"].ewm(span=config["adx_period"], adjust=False).mean() / df["atr"])
    df["dx"]  = 100 * abs(df["+di"] - df["-di"]) / (df["+di"] + df["-di"])
    df["adx"] = df["dx"].ewm(span=config["adx_period"], adjust=False).mean()

    # Volume MA
    df["vol_ma"] = df["tick_volume"].rolling(20).mean()

    # Candle body %
    df["body_pct"] = abs(df["close"] - df["open"]) / (df["high"] - df["low"] + 1e-10) * 100

    return df


def get_htf_trend(symbol) -> str:
    """Get higher timeframe trend direction."""
    df = get_candles(symbol, config["htf"], 60)
    if df is None:
        return "NEUTRAL"
    df = calculate_indicators(df)
    last = df.iloc[-1]
    if last["ema_fast"] > last["ema_slow"] > last["ema_trend"]:
        return "BULLISH"
    elif last["ema_fast"] < last["ema_slow"] < last["ema_trend"]:
        return "BEARISH"
    return "NEUTRAL"


# ══════════════════════════════════════════
#  🔍 SIGNAL GENERATION + FAKE SIGNAL FILTER
# ══════════════════════════════════════════

def count_confluences(df: pd.DataFrame, direction: str) -> tuple:
    """
    Count how many indicators confirm the signal.
    Returns (score, details_list)
    Minimum 4 confluences required to trade.
    """
    last = df.iloc[-1]
    prev = df.iloc[-2]
    score = 0
    details = []

    if direction == "BUY":
        # 1. EMA crossover
        if prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]:
            score += 1; details.append("✅ EMA crossover bullish")
        # 2. Price above trend EMA
        if last["close"] > last["ema_trend"]:
            score += 1; details.append("✅ Price above EMA200")
        # 3. RSI in bullish zone (not overbought)
        if 40 < last["rsi"] < config["rsi_ob"]:
            score += 1; details.append(f"✅ RSI bullish zone ({last['rsi']:.1f})")
        # 4. Strong trend (ADX)
        if last["adx"] > config["adx_min"]:
            score += 1; details.append(f"✅ Strong trend ADX ({last['adx']:.1f})")
        # 5. Volume confirmation
        if last["tick_volume"] > last["vol_ma"] * config["volume_mult"]:
            score += 1; details.append("✅ Volume confirmed")
        # 6. Candle body (no doji/fake candle)
        if last["body_pct"] > config["min_body_pct"] and last["close"] > last["open"]:
            score += 1; details.append("✅ Strong bullish candle")
        # 7. Fast EMA slope
        if last["ema_fast"] > df.iloc[-3]["ema_fast"]:
            score += 1; details.append("✅ EMA rising")

    else:  # SELL
        if prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]:
            score += 1; details.append("✅ EMA crossover bearish")
        if last["close"] < last["ema_trend"]:
            score += 1; details.append("✅ Price below EMA200")
        if config["rsi_os"] < last["rsi"] < 60:
            score += 1; details.append(f"✅ RSI bearish zone ({last['rsi']:.1f})")
        if last["adx"] > config["adx_min"]:
            score += 1; details.append(f"✅ Strong trend ADX ({last['adx']:.1f})")
        if last["tick_volume"] > last["vol_ma"] * config["volume_mult"]:
            score += 1; details.append("✅ Volume confirmed")
        if last["body_pct"] > config["min_body_pct"] and last["close"] < last["open"]:
            score += 1; details.append("✅ Strong bearish candle")
        if last["ema_fast"] < df.iloc[-3]["ema_fast"]:
            score += 1; details.append("✅ EMA falling")

    return score, details


def get_signal(df: pd.DataFrame) -> str:
    """Generate raw signal from EMA crossover."""
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]:
        return "BUY"
    if prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]:
        return "SELL"
    return None


# ══════════════════════════════════════════
#  💰 RISK MANAGEMENT
# ══════════════════════════════════════════

class RiskManager:
    def __init__(self):
        self.consecutive_losses = 0
        self.cooldown_until     = None
        self.daily_loss_pct     = 0.0
        self.start_balance      = None
        self.peak_balance       = None
        self.loss_history       = deque(maxlen=50)

    def init_balance(self, balance):
        if self.start_balance is None:
            self.start_balance = balance
            self.peak_balance  = balance

    def update(self, profit):
        self.loss_history.append(profit)
        if profit < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= config["cooldown_after_loss"]:
                self.cooldown_until = datetime.now() + timedelta(minutes=config["cooldown_minutes"])
                log.warning(f"⏸️  Cooldown activated for {config['cooldown_minutes']} min after {self.consecutive_losses} losses")
                send_telegram(f"⏸️ <b>COOLDOWN ACTIVATED</b>\n{self.consecutive_losses} consecutive losses.\nBot paused for {config['cooldown_minutes']} minutes.")
        else:
            self.consecutive_losses = 0

    def in_cooldown(self) -> tuple:
        if self.cooldown_until and datetime.now() < self.cooldown_until:
            remaining = int((self.cooldown_until - datetime.now()).total_seconds() / 60)
            return True, f"Cooldown active ({remaining} min remaining)"
        self.cooldown_until = None
        return False, ""

    def daily_loss_exceeded(self, balance) -> bool:
        if self.start_balance:
            loss_pct = ((self.start_balance - balance) / self.start_balance) * 100
            return loss_pct >= config["max_daily_loss"]
        return False

    def max_drawdown_exceeded(self, balance) -> bool:
        if self.peak_balance:
            self.peak_balance = max(self.peak_balance, balance)
            dd = ((self.peak_balance - balance) / self.peak_balance) * 100
            return dd >= config["max_drawdown"]
        return False

    def calc_lot_size(self, balance, sl_pips, symbol) -> float:
        """Dynamic lot size based on risk % of balance."""
        risk_amount = balance * (config["risk_pct"] / 100)
        sym_info    = mt5.symbol_info(symbol)
        pip_value   = sym_info.trade_tick_value * 10
        lot = round(risk_amount / (sl_pips * pip_value), 2)
        lot = max(0.01, min(lot, 5.0))  # Between 0.01 and 5.0
        return lot


risk = RiskManager()


# ══════════════════════════════════════════
#  🔄 TRAILING STOP LOSS
# ══════════════════════════════════════════

def update_trailing_stops(symbol):
    """Move stop loss up (for BUY) or down (for SELL) as price moves in our favour."""
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return

    df  = get_candles(symbol, config["timeframe"], 20)
    if df is None:
        return
    df  = calculate_indicators(df)
    atr = df["atr"].iloc[-1]
    trail_dist = atr * config["trailing_atr_mult"]

    for pos in positions:
        tick = mt5.symbol_info_tick(symbol)

        if pos.type == mt5.ORDER_TYPE_BUY:
            new_sl = round(tick.bid - trail_dist, 5)
            if new_sl > pos.sl:
                _modify_sl(pos, new_sl)

        elif pos.type == mt5.ORDER_TYPE_SELL:
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
        log.info(f"🔄 Trailing SL updated: #{position.ticket} → SL {new_sl:.5f}")


# ══════════════════════════════════════════
#  📤 ORDER EXECUTION
# ══════════════════════════════════════════

def place_order(symbol, action, lot, atr):
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
        "magic":        20250509,
        "comment":      "Claude Bot v2",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        msg = (f"🚀 <b>{action} TRADE EXECUTED</b>\n"
               f"💱 Symbol: {symbol}\n"
               f"💰 Lot: {lot}\n"
               f"📍 Entry: {price}\n"
               f"🛑 SL: {sl} ({sl_pips} pips)\n"
               f"🎯 TP: {tp} ({tp_pips} pips)\n"
               f"📊 R:R = 1:{round(tp_pips/sl_pips, 1)}")
        send_telegram(msg)
        log.info(f"✅ Order placed: {action} @ {price}")
        return True
    else:
        log.error(f"❌ Order failed: {result.comment}")
        return False


# ══════════════════════════════════════════
#  📈 BACKTESTING MODULE
# ══════════════════════════════════════════

def run_backtest(symbol=None, periods=500):
    symbol = symbol or config["symbol"]
    log.info(f"\n{'='*50}\n  📈 BACKTESTING {symbol} — {periods} candles\n{'='*50}")

    if not mt5.initialize():
        print("MT5 not available for backtest. Using sample data.")
        return

    df = get_candles(symbol, config["timeframe"], periods)
    if df is None:
        log.error("Could not fetch data for backtest")
        return

    df = calculate_indicators(df)

    balance    = 10000.0
    peak       = balance
    trades     = []
    position   = None
    wins = losses = 0

    for i in range(config["ema_trend"] + 10, len(df)):
        row  = df.iloc[i]
        prev = df.iloc[i - 1]

        # Check for exit first
        if position:
            if position["type"] == "BUY":
                if row["low"] <= position["sl"]:
                    pnl = (position["sl"] - position["entry"]) * position["lot"] * 100000
                    balance += pnl; losses += 1; trades.append(pnl); position = None
                elif row["high"] >= position["tp"]:
                    pnl = (position["tp"] - position["entry"]) * position["lot"] * 100000
                    balance += pnl; wins += 1; trades.append(pnl); position = None
            elif position["type"] == "SELL":
                if row["high"] >= position["sl"]:
                    pnl = (position["entry"] - position["sl"]) * position["lot"] * 100000
                    balance -= pnl; losses += 1; trades.append(-pnl); position = None
                elif row["low"] <= position["tp"]:
                    pnl = (position["entry"] - position["tp"]) * position["lot"] * 100000
                    balance += pnl; wins += 1; trades.append(pnl); position = None

        peak = max(peak, balance)

        # Entry logic
        if position is None:
            cross_up   = prev["ema_fast"] <= prev["ema_slow"] and row["ema_fast"] > row["ema_slow"]
            cross_down = prev["ema_fast"] >= prev["ema_slow"] and row["ema_fast"] < row["ema_slow"]
            atr = row["atr"]

            if cross_up and row["close"] > row["ema_trend"] and row["adx"] > config["adx_min"] and row["rsi"] < config["rsi_ob"]:
                sl = row["close"] - atr * config["trailing_atr_mult"]
                tp = row["close"] + atr * config["tp_atr_mult"]
                position = {"type": "BUY", "entry": row["close"], "sl": sl, "tp": tp, "lot": 0.01}

            elif cross_down and row["close"] < row["ema_trend"] and row["adx"] > config["adx_min"] and row["rsi"] > config["rsi_os"]:
                sl = row["close"] + atr * config["trailing_atr_mult"]
                tp = row["close"] - atr * config["tp_atr_mult"]
                position = {"type": "SELL", "entry": row["close"], "sl": sl, "tp": tp, "lot": 0.01}

    total  = wins + losses
    wr     = (wins / total * 100) if total > 0 else 0
    profit = balance - 10000
    dd     = ((peak - balance) / peak * 100) if peak > 0 else 0
    avg_pnl = np.mean(trades) if trades else 0
    profit_factor = (sum(t for t in trades if t > 0) / abs(sum(t for t in trades if t < 0))) if losses > 0 else 999

    result = (
        f"\n{'='*50}\n"
        f"  📊 BACKTEST RESULTS\n"
        f"{'='*50}\n"
        f"  Total Trades:    {total}\n"
        f"  Wins:            {wins} ({wr:.1f}%)\n"
        f"  Losses:          {losses}\n"
        f"  Net Profit:      ${profit:.2f}\n"
        f"  Profit Factor:   {profit_factor:.2f}\n"
        f"  Avg Trade P&L:   ${avg_pnl:.2f}\n"
        f"  Max Drawdown:    {dd:.1f}%\n"
        f"  Final Balance:   ${balance:.2f}\n"
        f"{'='*50}"
    )
    log.info(result)
    return {"wins": wins, "losses": losses, "profit": profit, "win_rate": wr}


# ══════════════════════════════════════════
#  🤖 MAIN BOT LOOP
# ══════════════════════════════════════════

def connect_mt5() -> bool:
    if not mt5.initialize():
        log.error(f"MT5 init failed: {mt5.last_error()}")
        return False
    if not mt5.login(config["mt5_login"], password=config["mt5_password"], server=config["mt5_server"]):
        log.error(f"MT5 login failed: {mt5.last_error()}")
        mt5.shutdown()
        return False
    info = mt5.account_info()
    log.info(f"✅ MT5 Connected | Balance: ${info.balance:.2f} | Equity: ${info.equity:.2f}")
    return True


def run_bot():
    log.info("\n" + "="*55)
    log.info("   🤖 ADVANCED CLAUDE AI FOREX BOT v2.0 STARTED")
    log.info(f"   Symbol: {config['symbol']} | Timeframe: H1 + H4 filter")
    log.info(f"   Strategy: EMA{config['ema_fast']}/{config['ema_slow']}/{config['ema_trend']} + RSI + ADX")
    log.info(f"   Risk per trade: {config['risk_pct']}% | Max daily loss: {config['max_daily_loss']}%")
    log.info("="*55 + "\n")

    send_telegram("🤖 <b>Claude AI Forex Bot STARTED</b>\nMonitoring EURUSD on H1...")

    if not connect_mt5():
        return

    while True:
        try:
            now      = datetime.now().strftime("%H:%M:%S")
            acct     = mt5.account_info()
            balance  = acct.balance
            symbol   = config["symbol"]

            risk.init_balance(balance)

            # ── Safety Checks ──────────────────────────
            in_cd, cd_reason = risk.in_cooldown()
            if in_cd:
                log.info(f"[{now}] ⏸️  {cd_reason}")
                time.sleep(config["check_interval"])
                continue

            if risk.daily_loss_exceeded(balance):
                msg = f"🛑 Daily loss limit hit (>{config['max_daily_loss']}%). Bot stopped for today."
                log.warning(msg); send_telegram(f"🛑 {msg}")
                break

            if risk.max_drawdown_exceeded(balance):
                msg = f"🚨 Max drawdown exceeded (>{config['max_drawdown']}%). Bot shutting down!"
                log.warning(msg); send_telegram(f"🚨 {msg}")
                break

            # ── Update Trailing Stops ──────────────────
            update_trailing_stops(symbol)

            # ── Get Market Data ────────────────────────
            df = get_candles(symbol, config["timeframe"])
            if df is None:
                log.warning("Could not fetch candles")
                time.sleep(60); continue

            df   = calculate_indicators(df)
            last = df.iloc[-1]
            sig  = get_signal(df)

            log.info(f"[{now}] Price:{last['close']:.5f} | "
                     f"EMA{config['ema_fast']}:{last['ema_fast']:.5f} | "
                     f"RSI:{last['rsi']:.1f} | ADX:{last['adx']:.1f} | "
                     f"Signal:{sig or 'NONE'}")

            if sig is None:
                time.sleep(config["check_interval"]); continue

            # ── Higher Timeframe Trend Filter ──────────
            htf_trend = get_htf_trend(symbol)
            if (sig == "BUY" and htf_trend == "BEARISH") or (sig == "SELL" and htf_trend == "BULLISH"):
                log.info(f"❌ Signal rejected — against H4 trend ({htf_trend})")
                time.sleep(config["check_interval"]); continue

            # ── Confluence Check (fake signal filter) ──
            score, details = count_confluences(df, sig)
            log.info(f"Confluence score: {score}/7 | Need: {config['confluence_min']}")
            for d in details:
                log.info(f"   {d}")

            if score < config["confluence_min"]:
                log.info(f"❌ Signal rejected — only {score} confirmations (need {config['confluence_min']})")
                time.sleep(config["check_interval"]); continue

            # ── News & Danger Zone Check ───────────────
            danger, danger_reason = is_news_time()
            if danger:
                log.info(f"⚠️  Avoiding news time: {danger_reason}")
                send_telegram(f"⚠️ <b>NEWS ALERT — Trade Skipped</b>\n{danger_reason}")
                time.sleep(config["check_interval"]); continue

            # ── Claude AI News Sentiment ───────────────
            news      = get_financial_news()
            sentiment = analyze_news_sentiment(news, sig)
            log.info(f"Claude Sentiment: {sentiment['sentiment']} | Safe: {sentiment['safe_to_trade']} | {sentiment['reason']}")

            if not sentiment.get("safe_to_trade", True):
                log.info(f"❌ Claude blocked trade: {sentiment['reason']}")
                send_telegram(f"🤖 <b>Claude AI blocked trade</b>\nSignal: {sig}\nReason: {sentiment['reason']}")
                time.sleep(config["check_interval"]); continue

            # ── Max Open Trades ────────────────────────
            open_trades = len(mt5.positions_get(symbol=symbol) or [])
            if open_trades >= config["max_open_trades"]:
                log.info(f"⏸️  Max open trades ({config['max_open_trades']}) reached")
                time.sleep(config["check_interval"]); continue

            # ── Dynamic Lot Size ───────────────────────
            atr     = last["atr"]
            sl_pips = round((atr * config["trailing_atr_mult"]) / (mt5.symbol_info(symbol).point * 10))
            lot     = risk.calc_lot_size(balance, sl_pips, symbol)

            # ── Place Trade ────────────────────────────
            log.info(f"🚀 All checks passed! Placing {sig} | Lot: {lot} | Confluences: {score}/7")
            success = place_order(symbol, sig, lot, atr)

            time.sleep(config["check_interval"])

        except KeyboardInterrupt:
            log.info("\n🛑 Bot stopped by user.")
            send_telegram("🛑 <b>Bot manually stopped.</b>")
            break
        except Exception as e:
            log.error(f"Error in main loop: {e}")
            time.sleep(60)

    mt5.shutdown()
    log.info("🔌 MT5 disconnected.")


# ══════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════
if __name__ == "__main__":
    if "--backtest" in sys.argv:
        if mt5.initialize():
            run_backtest()
            mt5.shutdown()
        else:
            print("MT5 not connected. Open MT5 terminal first.")
    else:
        run_bot()

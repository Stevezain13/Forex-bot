"""
╔══════════════════════════════════════════════════════════════════╗
║         STEPHEN'S SIGNAL BOT — RENDER VERSION                   ║
║         Works 100% on Linux/Render — No MT5 needed             ║
╠══════════════════════════════════════════════════════════════════╣
║  ✅ SMC Analysis (OB, BOS, FVG)                                 ║
║  ✅ EMA 20/50/200 + RSI + ADX                                   ║
║  ✅ Signal Score out of 10                                      ║
║  ✅ London & New York Sessions only                             ║
║  ✅ News Protection                                             ║
║  ✅ Telegram Alerts with Entry/SL/TP                           ║
║  ✅ Daily Report                                                ║
║  ✅ Weekend Protection                                          ║
║  ✅ Works 24/7 on Render Free Plan                             ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import time
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ═══════════════════════════════════════════════════════
#  ⚙️  CONFIG — reads from Render environment variables
# ═══════════════════════════════════════════════════════
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_TOKEN")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT",  "7781270946")
NEWS_KEY       = os.environ.get("NEWS_KEY",        "YOUR_NEWS_KEY")

SYMBOLS        = ["EURUSD=X", "GBPUSD=X", "JPY=X"]
SYMBOL_NAMES   = {"EURUSD=X": "EURUSD", "GBPUSD=X": "GBPUSD", "JPY=X": "USDJPY"}
CHECK_INTERVAL = 300   # Check every 5 minutes
MIN_SCORE      = 7     # Minimum score out of 10

# ── Logging ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════
#  📱 TELEGRAM
# ══════════════════════════════════════════════════════

def send_telegram(message: str):
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id":    TELEGRAM_CHAT,
            "text":       message,
            "parse_mode": "HTML"
        }
        r = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            log.info("📱 Telegram sent!")
        else:
            log.warning(f"Telegram error: {r.text}")
    except Exception as e:
        log.warning(f"Telegram failed: {e}")


# ══════════════════════════════════════════════════════
#  ⏰ SESSION FILTER
# ══════════════════════════════════════════════════════

def is_trading_session() -> tuple:
    now     = datetime.utcnow()
    hour    = now.hour
    weekday = now.weekday()

    # No trading weekends
    if weekday >= 5:
        return False, "Weekend — markets closed"

    # Convert to EAT (UTC+3)
    eat_hour = (hour + 3) % 24

    london  = 10 <= eat_hour < 19
    newyork = 15 <= eat_hour < 24

    if london and newyork:
        return True, "🇬🇧🇺🇸 London + NY Overlap (Best!)"
    elif london:
        return True, "🇬🇧 London Session"
    elif newyork:
        return True, "🇺🇸 New York Session"

    return False, f"😴 Asian Session — waiting for London (10am EAT)"


def is_friday_night() -> bool:
    now = datetime.utcnow()
    eat_hour = (now.hour + 3) % 24
    return now.weekday() == 4 and eat_hour >= 21


# ══════════════════════════════════════════════════════
#  📰 NEWS MODULE
# ══════════════════════════════════════════════════════

def get_news() -> list:
    try:
        url    = "https://newsapi.org/v2/everything"
        params = {
            "q":        "forex EURUSD interest rate Federal Reserve ECB",
            "language": "en",
            "sortBy":   "publishedAt",
            "pageSize": 10,
            "apiKey":   NEWS_KEY
        }
        r = requests.get(url, params=params, timeout=10)
        return [{"title": a["title"]} for a in r.json().get("articles", [])]
    except:
        return []


def is_dangerous_news() -> tuple:
    now      = datetime.utcnow()
    eat_hour = (now.hour + 3) % 24
    eat_min  = now.minute

    danger_times = [
        (11, 30, "London Open News"),
        (16, 30, "US News Release"),
        (18,  0, "Fed/ECB Speech"),
        (21,  0, "US Afternoon News"),
    ]

    for h, m, name in danger_times:
        event_mins = h * 60 + m
        now_mins   = eat_hour * 60 + eat_min
        if abs(now_mins - event_mins) <= 60:
            return True, f"⚠️ Near {name}"

    return False, ""


def check_news_sentiment(news: list, signal: str) -> dict:
    if not news:
        return {"safe": True, "reason": "No news"}

    bullish = ["rate hike", "strong", "growth", "beat", "surge", "rally", "gain"]
    bearish = ["rate cut", "weak", "recession", "miss", "crash", "drop", "fall"]
    danger  = ["NFP", "nonfarm", "CPI", "inflation", "FOMC", "GDP", "rate decision"]

    bull = bear = 0
    for a in news:
        t = a["title"].lower()
        bull += sum(1 for w in bullish if w in t)
        bear += sum(1 for w in bearish if w in t)
        if any(d.lower() in t for d in danger):
            return {"safe": False, "reason": "High impact news detected!"}

    if signal == "BUY"  and bear > bull + 2:
        return {"safe": False, "reason": f"Bearish news ({bear} vs {bull})"}
    if signal == "SELL" and bull > bear + 2:
        return {"safe": False, "reason": f"Bullish news ({bull} vs {bear})"}

    return {"safe": True, "reason": f"News OK (Bull:{bull} Bear:{bear})"}


# ══════════════════════════════════════════════════════
#  📊 MARKET DATA & INDICATORS
# ══════════════════════════════════════════════════════

def get_data(symbol: str, period="3mo", interval="1h") -> pd.DataFrame:
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        df     = ticker.history(period=period, interval=interval)
        if df is None or df.empty or len(df) < 50:
            log.warning(f"Not enough data for {symbol}")
            return None
        df.columns = [c.lower() for c in df.columns]
        df = df.reset_index()
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close"])
        log.info(f"✅ Got {len(df)} candles for {symbol}")
        return df
    except Exception as e:
        log.warning(f"Data fetch failed for {symbol}: {e}")
        return None


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    # EMAs
    df["ema20"]  = df["close"].ewm(span=20,  adjust=False).mean()
    df["ema50"]  = df["close"].ewm(span=50,  adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

    # RSI
    delta    = df["close"].diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
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
    df["atr"] = df["tr"].rolling(14).mean()

    # ADX
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

    # Body strength
    df["body_pct"] = abs(df["close"] - df["open"]) / (df["high"] - df["low"] + 1e-10) * 100

    return df


def get_signal(df: pd.DataFrame) -> str:
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev["ema20"] <= prev["ema50"] and last["ema20"] > last["ema50"]:
        return "BUY"
    if prev["ema20"] >= prev["ema50"] and last["ema20"] < last["ema50"]:
        return "SELL"
    return None


# ══════════════════════════════════════════════════════
#  🧠 SMC ANALYSIS
# ══════════════════════════════════════════════════════

def find_order_block(df: pd.DataFrame, direction: str) -> dict:
    for i in range(len(df) - 10, len(df) - 2):
        if i < 1:
            continue
        candle = df.iloc[i]
        nxt    = df.iloc[i + 1]
        body   = abs(candle["close"] - candle["open"])
        nbody  = abs(nxt["close"]    - nxt["open"])

        if direction == "BUY":
            if (candle["close"] < candle["open"] and
                nxt["close"] > nxt["open"] and
                nbody > body * 1.5):
                return {"high": candle["high"], "low": candle["low"], "found": True}

        elif direction == "SELL":
            if (candle["close"] > candle["open"] and
                nxt["close"] < nxt["open"] and
                nbody > body * 1.5):
                return {"high": candle["high"], "low": candle["low"], "found": True}

    return {"found": False}


def find_fvg(df: pd.DataFrame, direction: str) -> dict:
    min_gap = 0.0005
    for i in range(1, len(df) - 1):
        prev = df.iloc[i - 1]
        nxt  = df.iloc[i + 1]

        if direction == "BUY" and nxt["low"] > prev["high"]:
            gap = nxt["low"] - prev["high"]
            if gap >= min_gap:
                return {"top": nxt["low"], "bottom": prev["high"], "found": True}

        if direction == "SELL" and nxt["high"] < prev["low"]:
            gap = prev["low"] - nxt["high"]
            if gap >= min_gap:
                return {"top": prev["low"], "bottom": nxt["high"], "found": True}

    return {"found": False}


def detect_bos(df: pd.DataFrame) -> str:
    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values

    swing_highs = []
    swing_lows  = []

    for i in range(2, len(df) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            swing_highs.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            swing_lows.append(lows[i])

    if len(swing_highs) >= 2 and closes[-1] > swing_highs[-2]:
        return "BULLISH"
    if len(swing_lows) >= 2 and closes[-1] < swing_lows[-2]:
        return "BEARISH"
    return None


# ══════════════════════════════════════════════════════
#  🎯 SIGNAL SCORING
# ══════════════════════════════════════════════════════

def score_signal(df, signal, bos, ob, fvg) -> tuple:
    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    score = 0
    details = []

    if signal == "BUY":
        if prev["ema20"] <= prev["ema50"] and last["ema20"] > last["ema50"]:
            score += 1; details.append("✅ EMA crossover bullish")
        if last["close"] > last["ema200"]:
            score += 1; details.append("✅ Above EMA200")
        if 40 < last["rsi"] < 65:
            score += 1; details.append(f"✅ RSI good ({last['rsi']:.0f})")
        if last["adx"] > 25:
            score += 1; details.append(f"✅ Strong trend ({last['adx']:.0f})")
        if last["body_pct"] > 40 and last["close"] > last["open"]:
            score += 1; details.append("✅ Strong bull candle")
        if bos == "BULLISH":
            score += 2; details.append("✅ BOS Bullish (+2)")
        if ob.get("found"):
            score += 2; details.append("✅ Order Block found (+2)")
        if fvg.get("found"):
            score += 1; details.append("✅ FVG found (+1)")
        if last["rsi"] > 70:
            score -= 1; details.append("❌ RSI overbought")

    else:  # SELL
        if prev["ema20"] >= prev["ema50"] and last["ema20"] < last["ema50"]:
            score += 1; details.append("✅ EMA crossover bearish")
        if last["close"] < last["ema200"]:
            score += 1; details.append("✅ Below EMA200")
        if 35 < last["rsi"] < 60:
            score += 1; details.append(f"✅ RSI good ({last['rsi']:.0f})")
        if last["adx"] > 25:
            score += 1; details.append(f"✅ Strong trend ({last['adx']:.0f})")
        if last["body_pct"] > 40 and last["close"] < last["open"]:
            score += 1; details.append("✅ Strong bear candle")
        if bos == "BEARISH":
            score += 2; details.append("✅ BOS Bearish (+2)")
        if ob.get("found"):
            score += 2; details.append("✅ Order Block found (+2)")
        if fvg.get("found"):
            score += 1; details.append("✅ FVG found (+1)")
        if last["rsi"] < 30:
            score -= 1; details.append("❌ RSI oversold")

    return max(0, min(score, 10)), details


# ══════════════════════════════════════════════════════
#  📤 BUILD TRADE ALERT
# ══════════════════════════════════════════════════════

def build_alert(symbol_name, signal, score, details, last, atr, ob, fvg, bos, session, sentiment) -> str:
    pip = 0.0001 if "JPY" not in symbol_name else 0.01

    if signal == "BUY":
        entry = round(last["close"], 5)
        sl    = round(entry - atr * 2, 5)
        tp    = round(entry + atr * 4, 5)
        emoji = "🟢"
    else:
        entry = round(last["close"], 5)
        sl    = round(entry + atr * 2, 5)
        tp    = round(entry - atr * 4, 5)
        emoji = "🔴"

    sl_pips = round(abs(entry - sl) / pip)
    tp_pips = round(abs(entry - tp) / pip)

    smc_info = []
    if bos:
        smc_info.append(f"BOS: {bos}")
    if ob.get("found"):
        smc_info.append(f"OB: {ob['low']:.5f}-{ob['high']:.5f}")
    if fvg.get("found"):
        smc_info.append(f"FVG: {fvg['bottom']:.5f}-{fvg['top']:.5f}")

    smc_text = "\n".join(smc_info) if smc_info else "No SMC confirmation"
    details_text = "\n".join(details[:5])

    alert = f"""
{emoji} <b>{signal} SIGNAL — {symbol_name}</b>
⭐ Score: {score}/10
━━━━━━━━━━━━━━━━━━━━
📍 Entry:  {entry}
🛑 SL:     {sl} ({sl_pips} pips)
🎯 TP:     {tp} ({tp_pips} pips)
📊 R:R = 1:{round(tp_pips/max(sl_pips,1), 1)}
━━━━━━━━━━━━━━━━━━━━
🧠 <b>SMC ANALYSIS:</b>
{smc_text}
━━━━━━━━━━━━━━━━━━━━
📈 <b>CONFIRMATIONS:</b>
{details_text}
━━━━━━━━━━━━━━━━━━━━
⏰ Session: {session}
📰 News: {sentiment['reason']}
━━━━━━━━━━━━━━━━━━━━
⚠️ Place trade manually on MT5 app!
"""
    return alert


# ══════════════════════════════════════════════════════
#  📊 DAILY STATS
# ══════════════════════════════════════════════════════

class DailyStats:
    def __init__(self):
        self.signals     = 0
        self.buy_signals  = 0
        self.sell_signals = 0
        self.skipped      = 0
        self.last_report  = None

    def record_signal(self, signal):
        self.signals += 1
        if signal == "BUY":
            self.buy_signals += 1
        else:
            self.sell_signals += 1

    def record_skip(self):
        self.skipped += 1

    def should_report(self):
        now = datetime.utcnow()
        eat_hour = (now.hour + 3) % 24
        if eat_hour == 23 and self.last_report != now.date():
            self.last_report = now.date()
            return True
        return False

    def send_report(self):
        report = f"""
📊 <b>STEPHEN'S DAILY SIGNAL REPORT</b>
📅 {datetime.utcnow().strftime('%d %B %Y')}
━━━━━━━━━━━━━━━━━━━━
📡 Total Signals:  {self.signals}
🟢 BUY Signals:   {self.buy_signals}
🔴 SELL Signals:  {self.sell_signals}
⏭️ Skipped:       {self.skipped}
━━━━━━━━━━━━━━━━━━━━
🌅 Bot continues tomorrow...
💡 Remember: Place trades on MT5 app!
"""
        send_telegram(report)
        self.signals = self.buy_signals = self.sell_signals = self.skipped = 0


stats = DailyStats()


# ══════════════════════════════════════════════════════
#  🚀 MAIN BOT LOOP
# ══════════════════════════════════════════════════════

def run():
    log.info("""
╔══════════════════════════════════════════╗
║  STEPHEN'S SIGNAL BOT STARTED 🚀        ║
║  Render Version — Linux Compatible      ║
╚══════════════════════════════════════════╝
""")

    send_telegram("""🚀 <b>STEPHEN'S SIGNAL BOT STARTED!</b>
━━━━━━━━━━━━━━━━━━━━
✅ SMC Analysis: ON
✅ EMA + RSI + ADX: ON
✅ Session Filter: ON
✅ News Protection: ON
✅ Daily Report: ON
━━━━━━━━━━━━━━━━━━━━
💱 Watching: EURUSD | GBPUSD | USDJPY
📱 Signals sent to your Telegram!
⚡ Place trades manually on MT5 app!""")

    while True:
        try:
            # ── Daily Report ───────────────────────────
            if stats.should_report():
                stats.send_report()

            # ── Weekend Check ──────────────────────────
            if is_friday_night():
                log.info("🌙 Friday night — resting until Monday")
                send_telegram("🌙 <b>Friday night!</b>\nBot resting until Monday. Have a great weekend Stephen! 😊")
                time.sleep(3600)
                continue

            # ── Session Check ──────────────────────────
            in_session, session = is_trading_session()
            if not in_session:
                log.info(f"😴 {session}")
                time.sleep(CHECK_INTERVAL)
                continue

            # ── News Check ─────────────────────────────
            danger, d_msg = is_dangerous_news()
            if danger:
                log.info(f"⚠️ {d_msg} — skipping")
                stats.record_skip()
                time.sleep(CHECK_INTERVAL)
                continue

            # ── Analyze Each Symbol ────────────────────
            for symbol in SYMBOLS:
                symbol_name = SYMBOL_NAMES[symbol]
                log.info(f"\n--- Analyzing {symbol_name} ---")

                # Get data
                df = get_data(symbol)
                if df is None or len(df) < 210:
                    log.warning(f"Not enough data for {symbol_name}")
                    continue

                # Calculate indicators
                df   = calculate_indicators(df)
                last = df.iloc[-1]
                sig  = get_signal(df)

                log.info(f"{symbol_name} | Price:{last['close']:.5f} | RSI:{last['rsi']:.1f} | ADX:{last['adx']:.1f} | Signal:{sig or 'NONE'}")

                if sig is None:
                    log.info(f"No signal for {symbol_name}")
                    continue

                # SMC Analysis
                bos = detect_bos(df)
                ob  = find_order_block(df, sig)
                fvg = find_fvg(df, sig)

                # Score signal
                score, details = score_signal(df, sig, bos, ob, fvg)
                log.info(f"Score: {score}/10")

                if score < MIN_SCORE:
                    log.info(f"❌ Score {score}/10 too low — skipping")
                    stats.record_skip()
                    continue

                # News sentiment
                news      = get_news()
                sentiment = check_news_sentiment(news, sig)
                if not sentiment["safe"]:
                    log.info(f"❌ News blocked: {sentiment['reason']}")
                    stats.record_skip()
                    continue

                # Send alert!
                atr   = last["atr"]
                alert = build_alert(
                    symbol_name, sig, score, details,
                    last, atr, ob, fvg, bos, session, sentiment
                )
                send_telegram(alert)
                stats.record_signal(sig)
                log.info(f"✅ Signal sent for {symbol_name}!")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log.info("🛑 Bot stopped.")
            send_telegram("🛑 <b>Signal Bot stopped.</b>")
            break
        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    run()


    

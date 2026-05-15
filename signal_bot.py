import os
import gc
import time
import logging
import requests
import threading
import pandas as pd
import numpy as np
from datetime import datetime
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
import yfinance as yf

# ══════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT", "7781270946")
NEWS_KEY       = os.environ.get("NEWS_KEY", "")
PORT           = int(os.environ.get("PORT", 8080))
RENDER_URL     = os.environ.get("RENDER_EXTERNAL_URL", "https://forex-bot-y6vx.onrender.com")

SYMBOLS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "XAUUSD": "GC=F",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "CAD=X"
}

CHECK_INTERVAL = 300
MIN_SCORE      = 6

KILLZONES = [
    (10, 0,  13, 0,  "London Killzone"),
    (16, 0,  19, 0,  "New York Killzone"),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

recent_signals = deque(maxlen=20)


# ══════════════════════════════════════════════════════
#  WEB SERVER — keeps Render happy
# ══════════════════════════════════════════════════════

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Stephen Signal Bot v5.0 Running!")

    def log_message(self, format, *args):
        pass


def start_web_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    log.info("Health server started on port " + str(PORT))
    server.serve_forever()


def auto_ping():
    time.sleep(30)
    while True:
        try:
            requests.get(RENDER_URL, timeout=10)
            log.info("Auto ping OK")
        except Exception:
            pass
        time.sleep(600)


# ══════════════════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════════════════

def send_telegram(message):
    try:
        url  = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
        data = {
            "chat_id":    TELEGRAM_CHAT,
            "text":       message,
            "parse_mode": "HTML"
        }
        r = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            log.info("Telegram sent!")
        else:
            log.warning("Telegram error: " + str(r.status_code))
    except Exception as e:
        log.warning("Telegram failed: " + str(e))


# ══════════════════════════════════════════════════════
#  TIME HELPERS
# ══════════════════════════════════════════════════════

def get_eat():
    now = datetime.utcnow()
    return (now.hour + 3) % 24, now.minute, now.weekday()


def is_killzone():
    eat_hour, eat_min, weekday = get_eat()
    if weekday >= 5:
        return False, "Weekend"
    current = eat_hour * 60 + eat_min
    for sh, sm, eh, em, name in KILLZONES:
        if sh * 60 + sm <= current < eh * 60 + em:
            return True, name
    return False, "Outside Killzone - waiting for London(10am) or NY(4pm) EAT"


def is_session():
    eat_hour, eat_min, weekday = get_eat()
    if weekday >= 5:
        return False, "Weekend - markets closed"
    london  = 10 <= eat_hour < 19
    newyork = 15 <= eat_hour < 24
    if london and newyork:
        return True, "London + NY Overlap"
    if london:
        return True, "London Session"
    if newyork:
        return True, "New York Session"
    return False, "Asian Session - waiting for London 10am EAT"


def is_friday_night():
    eat_hour, _, weekday = get_eat()
    return weekday == 4 and eat_hour >= 21


# ══════════════════════════════════════════════════════
#  INTERNET CHECK
# ══════════════════════════════════════════════════════

def has_internet():
    try:
        requests.get("https://google.com", timeout=5)
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════
#  DUPLICATE FILTER
# ══════════════════════════════════════════════════════

def is_duplicate(name, signal):
    key = name + "_" + signal + "_" + datetime.utcnow().strftime("%Y%m%d%H")
    if key in recent_signals:
        return True
    recent_signals.append(key)
    return False


# ══════════════════════════════════════════════════════
#  NEWS
# ══════════════════════════════════════════════════════

def get_news():
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q":        "forex EURUSD interest rate Federal Reserve ECB",
                "language": "en",
                "sortBy":   "publishedAt",
                "pageSize": 10,
                "apiKey":   NEWS_KEY
            },
            timeout=10
        )
        return [{"title": a["title"]} for a in r.json().get("articles", [])]
    except Exception:
        return []


def is_dangerous_news():
    eat_hour, eat_min, _ = get_eat()
    danger = [(11, 30, "London News"), (16, 30, "US News"), (18, 0, "Fed Speech"), (21, 0, "US News")]
    for h, m, name in danger:
        if abs((eat_hour * 60 + eat_min) - (h * 60 + m)) <= 60:
            return True, "Near " + name
    return False, ""


def check_sentiment(news, signal):
    if not news:
        return {"safe": True, "reason": "News OK"}
    bullish = ["rate hike", "strong", "growth", "beat", "surge", "rally"]
    bearish = ["rate cut", "weak", "recession", "miss", "crash", "drop"]
    danger  = ["NFP", "nonfarm", "CPI", "inflation", "FOMC", "GDP"]
    bull = bear = 0
    for a in news:
        t = a["title"].lower()
        bull += sum(1 for w in bullish if w in t)
        bear += sum(1 for w in bearish if w in t)
        if any(d.lower() in t for d in danger):
            return {"safe": False, "reason": "High impact news!"}
    if signal == "BUY"  and bear > bull + 2:
        return {"safe": False, "reason": "Bearish news"}
    if signal == "SELL" and bull > bear + 2:
        return {"safe": False, "reason": "Bullish news"}
    return {"safe": True, "reason": "News OK"}


# ══════════════════════════════════════════════════════
#  MARKET DATA
# ══════════════════════════════════════════════════════

def get_data(symbol, retries=3):
    for attempt in range(retries):
        try:
            df = yf.Ticker(symbol).history(period="3mo", interval="1h")
            if df is None or df.empty or len(df) < 50:
                continue
            df.columns = [c.lower() for c in df.columns]
            df = df.reset_index()
            for col in ["open", "high", "low", "close"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["open", "high", "low", "close"])
            if len(df) >= 50:
                log.info("Got " + str(len(df)) + " candles for " + symbol)
                return df
        except Exception as e:
            log.warning("Attempt " + str(attempt + 1) + " failed for " + symbol + ": " + str(e))
            time.sleep(5)
    return None


def get_daily(symbol):
    try:
        df = yf.Ticker(symbol).history(period="3mo", interval="1d")
        if df is None or df.empty:
            return None
        df.columns = [c.lower() for c in df.columns]
        df = df.reset_index()
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["open", "high", "low", "close"])
    except Exception:
        return None


# ══════════════════════════════════════════════════════
#  INDICATORS
# ══════════════════════════════════════════════════════

def calc_indicators(df):
    c = df["close"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    o = df["open"].astype(float)

    df["ema20"]  = c.ewm(span=20,  adjust=False).mean()
    df["ema50"]  = c.ewm(span=50,  adjust=False).mean()
    df["ema200"] = c.ewm(span=200, adjust=False).mean()

    delta    = c.diff()
    ag       = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    al       = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
    df["rsi"] = 100 - (100 / (1 + ag / (al + 1e-10)))

    tr = pd.concat([
        h - l,
        (h - c.shift()).abs(),
        (l - c.shift()).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()

    hd  = h.diff()
    ld  = l.diff()
    pdm = hd.where((hd > 0) & (hd > -ld), 0.0)
    mdm = (-ld).where((-ld > 0) & (-ld > hd), 0.0)
    pdi = 100 * (pdm.ewm(span=14, adjust=False).mean() / (df["atr"] + 1e-10))
    mdi = 100 * (mdm.ewm(span=14, adjust=False).mean() / (df["atr"] + 1e-10))
    df["adx"] = (100 * (pdi - mdi).abs() / (pdi + mdi + 1e-10)).ewm(span=14, adjust=False).mean()

    df["body_pct"] = (c - o).abs() / (h - l + 1e-10) * 100

    if "volume" in df.columns:
        df["vol_ma"] = df["volume"].rolling(20).mean()
    else:
        df["vol_ma"] = 1.0

    return df


def get_signal(df):
    l = df.iloc[-1]
    p = df.iloc[-2]
    if float(p["ema20"]) <= float(p["ema50"]) and float(l["ema20"]) > float(l["ema50"]):
        return "BUY"
    if float(p["ema20"]) >= float(p["ema50"]) and float(l["ema20"]) < float(l["ema50"]):
        return "SELL"
    return None


# ══════════════════════════════════════════════════════
#  SMC ANALYSIS
# ══════════════════════════════════════════════════════

def find_ob(df, direction):
    try:
        for i in range(len(df) - 10, len(df) - 2):
            if i < 1:
                continue
            c = df.iloc[i]
            n = df.iloc[i + 1]
            body  = abs(float(c["close"]) - float(c["open"]))
            nbody = abs(float(n["close"]) - float(n["open"]))
            if direction == "BUY":
                if float(c["close"]) < float(c["open"]) and float(n["close"]) > float(n["open"]) and nbody > body * 1.5:
                    return {"high": float(c["high"]), "low": float(c["low"]), "found": True}
            else:
                if float(c["close"]) > float(c["open"]) and float(n["close"]) < float(n["open"]) and nbody > body * 1.5:
                    return {"high": float(c["high"]), "low": float(c["low"]), "found": True}
    except Exception:
        pass
    return {"found": False}


def detect_bos(df):
    try:
        highs  = df["high"].astype(float).values
        lows   = df["low"].astype(float).values
        closes = df["close"].astype(float).values
        sh = []
        sl = []
        for i in range(2, len(df) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                sh.append(highs[i])
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                sl.append(lows[i])
        if len(sh) >= 2 and closes[-1] > sh[-2]:
            return "BULLISH"
        if len(sl) >= 2 and closes[-1] < sl[-2]:
            return "BEARISH"
    except Exception:
        pass
    return None


def find_fvg(df, direction):
    try:
        for i in range(1, len(df) - 1):
            p = df.iloc[i - 1]
            n = df.iloc[i + 1]
            if direction == "BUY" and float(n["low"]) > float(p["high"]):
                if float(n["low"]) - float(p["high"]) >= 0.0003:
                    return {"top": float(n["low"]), "bottom": float(p["high"]), "found": True}
            if direction == "SELL" and float(n["high"]) < float(p["low"]):
                if float(p["low"]) - float(n["high"]) >= 0.0003:
                    return {"top": float(p["low"]), "bottom": float(n["high"]), "found": True}
    except Exception:
        pass
    return {"found": False}


def detect_liquidity(df, direction):
    try:
        highs  = df["high"].astype(float).values
        lows   = df["low"].astype(float).values
        closes = df["close"].astype(float).values
        n = len(df)
        if direction == "BUY":
            for i in range(n - 5, max(n - 15, 2), -1):
                if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                    if lows[-1] < lows[i] and closes[-1] > lows[i]:
                        return {"found": True, "type": "Sell-side liquidity swept"}
        else:
            for i in range(n - 5, max(n - 15, 2), -1):
                if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                    if highs[-1] > highs[i] and closes[-1] < highs[i]:
                        return {"found": True, "type": "Buy-side liquidity swept"}
    except Exception:
        pass
    return {"found": False}


def get_zone(df):
    try:
        r     = df.tail(50)
        high  = float(r["high"].max())
        low   = float(r["low"].min())
        price = float(df.iloc[-1]["close"])
        mid   = (high + low) / 2
        pct   = round((price - low) / (high - low + 1e-10) * 100, 1)
        return {"zone": "DISCOUNT" if price < mid else "PREMIUM", "percent": pct}
    except Exception:
        return {"zone": "NEUTRAL", "percent": 50}


def get_prev_day(daily_df):
    try:
        if daily_df is None or len(daily_df) < 2:
            return {"found": False}
        p = daily_df.iloc[-2]
        return {"found": True, "high": float(p["high"]), "low": float(p["low"])}
    except Exception:
        return {"found": False}


def get_htf_bias(daily_df):
    try:
        if daily_df is None or len(daily_df) < 20:
            return "NEUTRAL"
        c   = daily_df["close"].astype(float)
        e20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
        e50 = c.ewm(span=50, adjust=False).mean().iloc[-1]
        return "BULLISH" if e20 > e50 else "BEARISH"
    except Exception:
        return "NEUTRAL"


def get_fib(df):
    try:
        r     = df.tail(50)
        high  = float(r["high"].max())
        low   = float(r["low"].min())
        price = float(df.iloc[-1]["close"])
        rng   = high - low
        f618  = high - rng * 0.618
        f705  = high - rng * 0.705
        tol   = rng * 0.02
        return {"found": abs(price - f618) <= tol or abs(price - f705) <= tol}
    except Exception:
        return {"found": False}


def detect_candle(df, direction):
    try:
        l = df.iloc[-1]
        p = df.iloc[-2]
        o = float(l["open"])
        h = float(l["high"])
        lo = float(l["low"])
        c = float(l["close"])
        body = abs(c - o)
        rng  = h - lo + 1e-10
        uw   = h - max(o, c)
        lw   = min(o, c) - lo

        if direction == "BUY":
            if c > float(p["open"]) and o < float(p["close"]) and c > o:
                return {"found": True, "pattern": "Bullish Engulfing"}
            if lw > body * 2 and uw < body * 0.5 and c > o:
                return {"found": True, "pattern": "Hammer"}
            if lw > rng * 0.6:
                return {"found": True, "pattern": "Bullish Pin Bar"}
        else:
            if c < float(p["open"]) and o > float(p["close"]) and c < o:
                return {"found": True, "pattern": "Bearish Engulfing"}
            if uw > body * 2 and lw < body * 0.5 and c < o:
                return {"found": True, "pattern": "Shooting Star"}
            if uw > rng * 0.6:
                return {"found": True, "pattern": "Bearish Pin Bar"}
    except Exception:
        pass
    return {"found": False, "pattern": "None"}


def check_volume(df):
    try:
        if "volume" not in df.columns:
            return {"confirmed": True, "reason": "Volume OK"}
        lv = float(df.iloc[-1]["volume"])
        av = float(df.iloc[-1]["vol_ma"])
        if lv > av * 1.5:
            return {"confirmed": True, "reason": "High volume"}
        if lv > av:
            return {"confirmed": True, "reason": "Normal volume"}
        return {"confirmed": False, "reason": "Low volume"}
    except Exception:
        return {"confirmed": True, "reason": "Volume OK"}


# ══════════════════════════════════════════════════════
#  SCORING OUT OF 15
# ══════════════════════════════════════════════════════

def score_signal(df, signal, ob, bos, fvg, liquidity, zone, htf_bias, fib, candle, volume):
    score   = 0
    details = []
    try:
        l = df.iloc[-1]
        p = df.iloc[-2]

        if signal == "BUY":
            if float(p["ema20"]) <= float(p["ema50"]) and float(l["ema20"]) > float(l["ema50"]):
                score += 1
                details.append("EMA crossover bullish")
            if float(l["close"]) > float(l["ema200"]):
                score += 1
                details.append("Above EMA200")
            if 40 < float(l["rsi"]) < 65:
                score += 1
                details.append("RSI good " + str(round(float(l["rsi"]))))
            if float(l["adx"]) > 25:
                score += 1
                details.append("ADX strong " + str(round(float(l["adx"]))))
            if bos == "BULLISH":
                score += 2
                details.append("BOS Bullish +2")
            if ob.get("found"):
                score += 2
                details.append("Order Block +2")
            if fvg.get("found"):
                score += 1
                details.append("FVG found")
            if liquidity.get("found"):
                score += 2
                details.append(str(liquidity.get("type", "Liquidity swept")) + " +2")
            if zone.get("zone") == "DISCOUNT":
                score += 1
                details.append("Discount zone " + str(zone.get("percent", 0)) + "%")
            if htf_bias == "BULLISH":
                score += 2
                details.append("Daily bias BULLISH +2")
            elif htf_bias == "BEARISH":
                score -= 2
                details.append("Daily bias bearish -2")
            if fib.get("found"):
                score += 1
                details.append("Fibonacci level")
            if candle.get("found"):
                score += 1
                details.append(str(candle.get("pattern", "")))
            if volume.get("confirmed"):
                score += 1
                details.append(str(volume.get("reason", "Volume OK")))
            if float(l["rsi"]) > 70:
                score -= 1
                details.append("RSI overbought -1")

        else:
            if float(p["ema20"]) >= float(p["ema50"]) and float(l["ema20"]) < float(l["ema50"]):
                score += 1
                details.append("EMA crossover bearish")
            if float(l["close"]) < float(l["ema200"]):
                score += 1
                details.append("Below EMA200")
            if 35 < float(l["rsi"]) < 60:
                score += 1
                details.append("RSI good " + str(round(float(l["rsi"]))))
            if float(l["adx"]) > 25:
                score += 1
                details.append("ADX strong " + str(round(float(l["adx"]))))
            if bos == "BEARISH":
                score += 2
                details.append("BOS Bearish +2")
            if ob.get("found"):
                score += 2
                details.append("Order Block +2")
            if fvg.get("found"):
                score += 1
                details.append("FVG found")
            if liquidity.get("found"):
                score += 2
                details.append(str(liquidity.get("type", "Liquidity swept")) + " +2")
            if zone.get("zone") == "PREMIUM":
                score += 1
                details.append("Premium zone " + str(zone.get("percent", 0)) + "%")
            if htf_bias == "BEARISH":
                score += 2
                details.append("Daily bias BEARISH +2")
            elif htf_bias == "BULLISH":
                score -= 2
                details.append("Daily bias bullish -2")
            if fib.get("found"):
                score += 1
                details.append("Fibonacci level")
            if candle.get("found"):
                score += 1
                details.append(str(candle.get("pattern", "")))
            if volume.get("confirmed"):
                score += 1
                details.append(str(volume.get("reason", "Volume OK")))
            if float(l["rsi"]) < 30:
                score -= 1
                details.append("RSI oversold -1")

    except Exception as e:
        log.warning("Score error: " + str(e))

    return max(0, min(score, 15)), details


# ══════════════════════════════════════════════════════
#  BUILD ALERT MESSAGE
# ══════════════════════════════════════════════════════

def build_alert(name, signal, score, details, last, atr, ob, bos, fvg, liquidity, zone, prev_day, htf_bias, fib, candle, kz_name, sentiment):
    try:
        pip   = 0.01 if "JPY" in name else 0.1 if "XAU" in name else 0.0001
        entry = round(float(last["close"]), 5)
        atr_f = float(atr)

        if signal == "BUY":
            sl    = round(entry - atr_f * 2, 5)
            tp1   = round(entry + atr_f * 2, 5)
            tp2   = round(entry + atr_f * 4, 5)
            emoji = "BUY"
        else:
            sl    = round(entry + atr_f * 2, 5)
            tp1   = round(entry - atr_f * 2, 5)
            tp2   = round(entry - atr_f * 4, 5)
            emoji = "SELL"

        slp  = round(abs(entry - sl)  / pip)
        tp1p = round(abs(entry - tp1) / pip)
        tp2p = round(abs(entry - tp2) / pip)

        smc_lines = []
        if bos:
            smc_lines.append("BOS: " + str(bos))
        if ob.get("found"):
            smc_lines.append("OB: " + str(round(ob["low"], 5)) + "-" + str(round(ob["high"], 5)))
        if fvg.get("found"):
            smc_lines.append("FVG detected")
        if liquidity.get("found"):
            smc_lines.append(str(liquidity.get("type", "Liquidity swept")))
        if candle.get("found"):
            smc_lines.append("Pattern: " + str(candle.get("pattern", "")))
        if fib.get("found"):
            smc_lines.append("Fibonacci level")

        smc_text     = "\n".join(smc_lines) if smc_lines else "EMA + RSI setup"
        details_text = "\n".join(["- " + d for d in details[:6]])

        pd_line = ""
        if prev_day.get("found"):
            pd_line = "\nPrev Day H:" + str(prev_day["high"]) + " L:" + str(prev_day["low"])

        rr = round(tp2p / max(slp, 1), 1)

        msg = (
            "<b>" + emoji + " SIGNAL - " + name + "</b>\n"
            "Score: " + str(score) + "/15\n"
            "Daily Bias: " + str(htf_bias) + "\n"
            "Zone: " + str(zone.get("zone")) + " (" + str(zone.get("percent", 0)) + "%)" + pd_line + "\n"
            "---\n"
            "Entry: " + str(entry) + "\n"
            "SL:    " + str(sl) + " (" + str(slp) + " pips)\n"
            "TP1:   " + str(tp1) + " (" + str(tp1p) + " pips)\n"
            "TP2:   " + str(tp2) + " (" + str(tp2p) + " pips)\n"
            "R:R = 1:" + str(rr) + "\n"
            "---\n"
            "SMC:\n" + smc_text + "\n"
            "---\n"
            "Confirmations:\n" + details_text + "\n"
            "---\n"
            "Session: " + str(kz_name) + "\n"
            "News: " + str(sentiment.get("reason", "OK")) + "\n"
            "---\n"
            "Place trade manually on MT5!\n"
            "Tip: Hit TP1 first, move SL to BE, target TP2"
        )
        return msg

    except Exception as e:
        log.warning("Alert error: " + str(e))
        return signal + " signal " + name + " Score:" + str(score) + "/15"


# ══════════════════════════════════════════════════════
#  DAILY STATS
# ══════════════════════════════════════════════════════

class DailyStats:
    def __init__(self):
        self.signals     = 0
        self.buys        = 0
        self.sells       = 0
        self.skipped     = 0
        self.last_report = None

    def record(self, sig):
        self.signals += 1
        if sig == "BUY":
            self.buys += 1
        else:
            self.sells += 1

    def skip(self):
        self.skipped += 1

    def should_report(self):
        now = datetime.utcnow()
        eat = (now.hour + 3) % 24
        if eat == 23 and self.last_report != now.date():
            self.last_report = now.date()
            return True
        return False

    def send_report(self):
        msg = (
            "<b>STEPHEN DAILY REPORT</b>\n"
            "Date: " + datetime.utcnow().strftime("%d %B %Y") + "\n"
            "---\n"
            "Total Signals: " + str(self.signals) + "\n"
            "BUY:           " + str(self.buys) + "\n"
            "SELL:          " + str(self.sells) + "\n"
            "Skipped:       " + str(self.skipped) + "\n"
            "---\n"
            "Bot continues tomorrow!\n"
            "Place trades on MT5 app!"
        )
        send_telegram(msg)
        self.signals = self.buys = self.sells = self.skipped = 0


# ══════════════════════════════════════════════════════
#  HEARTBEAT
# ══════════════════════════════════════════════════════

class Heartbeat:
    def __init__(self):
        self.last_beat = datetime.utcnow()

    def check(self):
        now   = datetime.utcnow()
        hours = (now - self.last_beat).total_seconds() / 3600
        if hours >= 6:
            self.last_beat = now
            eat  = (now.hour + 3) % 24
            mins = str(now.minute).zfill(2)
            msg  = (
                "<b>BOT HEARTBEAT</b>\n"
                "Time: " + str(eat) + ":" + mins + " EAT\n"
                "Bot is running smoothly!\n"
                "Watching: EURUSD | GBPUSD | USDJPY | XAUUSD | AUDUSD | USDCAD"
            )
            send_telegram(msg)


# ══════════════════════════════════════════════════════
#  STARTUP CHECK
# ══════════════════════════════════════════════════════

def startup_check():
    log.info("Running startup checks...")
    ok = True
    if has_internet():
        log.info("Internet OK")
    else:
        log.error("No internet!")
        ok = False
    if TELEGRAM_TOKEN:
        log.info("Telegram token found")
    else:
        log.error("Telegram token missing!")
        ok = False
    test = get_data("EURUSD=X", retries=2)
    if test is not None:
        log.info("Market data OK")
    else:
        log.warning("Market data test failed")
    return ok


# ══════════════════════════════════════════════════════
#  MAIN BOT
# ══════════════════════════════════════════════════════

stats     = DailyStats()
heartbeat = Heartbeat()


def run():
    if not startup_check():
        send_telegram("Startup check failed! Check your settings.")

    log.info("STEPHEN SIGNAL BOT v5.0 STARTED!")

    startup_msg = (
        "<b>STEPHEN SIGNAL BOT v5.0 STARTED!</b>\n"
        "---\n"
        "SMC: OB | BOS | FVG | Liquidity | Zone | Prev Day | HTF Bias\n"
        "TECH: EMA | RSI | ADX | Fibonacci | Candles | Volume | Correlation\n"
        "FILTER: Killzone | News | Weekend | Score 9/15+\n"
        "---\n"
        "Watching: EURUSD | GBPUSD | USDJPY | XAUUSD | AUDUSD | USDCAD\n"
        "Place trades manually on MT5!"
    )
    send_telegram(startup_msg)

    while True:
        try:
            if not has_internet():
                log.warning("No internet - waiting 60s...")
                time.sleep(60)
                continue

            if stats.should_report():
                stats.send_report()

            heartbeat.check()
            gc.collect()

            if is_friday_night():
                log.info("Friday night - resting")
                send_telegram("Friday night! Bot resting until Monday. Have a great weekend Stephen!")
                time.sleep(3600)
                continue

            in_session, session = is_session()
            if not in_session:
                log.info(session)
                time.sleep(CHECK_INTERVAL)
                continue

            in_kz, kz_name = is_killzone()
            if not in_kz:
                log.info(kz_name)
                time.sleep(CHECK_INTERVAL)
                continue

            log.info("KILLZONE ACTIVE: " + kz_name)

            danger, d_msg = is_dangerous_news()
            if danger:
                log.info(d_msg)
                stats.skip()
                time.sleep(CHECK_INTERVAL)
                continue

            # Fetch all data
            all_data = {}
            eu_sig   = None
            gb_sig   = None

            for name, sym in SYMBOLS.items():
                df = get_data(sym)
                if df is not None:
                    df = calc_indicators(df)
                    all_data[name] = df
                    sig = get_signal(df)
                    if name == "EURUSD":
                        eu_sig = sig
                    if name == "GBPUSD":
                        gb_sig = sig

            # Correlation check
            corr_strong  = eu_sig is not None and gb_sig is not None and eu_sig == gb_sig
            corr_reason  = "EURUSD + GBPUSD both " + str(eu_sig) + "!" if corr_strong else ""
            if corr_strong:
                log.info("Correlation: " + corr_reason)

            # Analyze each symbol
            for name, sym in SYMBOLS.items():
                log.info("--- Analyzing " + name + " ---")

                if name not in all_data:
                    continue

                df  = all_data[name]
                sig = get_signal(df)

                if sig is None:
                    log.info("No signal for " + name)
                    continue

                last = df.iloc[-1]
                log.info(name + " Price:" + str(round(float(last["close"]), 5)) + " RSI:" + str(round(float(last["rsi"]), 1)) + " Signal:" + sig)

                # Duplicate check
                if is_duplicate(name, sig):
                    log.info("Duplicate signal - skipping")
                    continue

                # Get daily data
                daily_df = get_daily(sym)

                # All SMC checks
                ob        = find_ob(df, sig)
                bos       = detect_bos(df)
                fvg       = find_fvg(df, sig)
                liquidity = detect_liquidity(df, sig)
                zone      = get_zone(df)
                prev_day  = get_prev_day(daily_df)
                htf_bias  = get_htf_bias(daily_df)
                fib       = get_fib(df)
                candle    = detect_candle(df, sig)
                volume    = check_volume(df)

                log.info("HTF:" + str(htf_bias) + " Zone:" + str(zone.get("zone")) + " BOS:" + str(bos))

                # Score
                score, details = score_signal(df, sig, ob, bos, fvg, liquidity, zone, htf_bias, fib, candle, volume)
                log.info("Score: " + str(score) + "/15 (need " + str(MIN_SCORE) + ")")

                if score < MIN_SCORE:
                    log.info("Score too low - skipping")
                    stats.skip()
                    continue

                # HTF filter
                if sig == "BUY" and htf_bias == "BEARISH":
                    log.info("Against daily bias - skipping")
                    stats.skip()
                    continue
                if sig == "SELL" and htf_bias == "BULLISH":
                    log.info("Against daily bias - skipping")
                    stats.skip()
                    continue

                # News check
                news = get_news()
                sent = check_sentiment(news, sig)
                if not sent["safe"]:
                    log.info("News blocked: " + str(sent["reason"]))
                    stats.skip()
                    continue

                # Correlation bonus
                if corr_strong and name in ["EURUSD", "GBPUSD", "AUDUSD"]:
                    details.append(corr_reason)
                    score = min(score + 1, 15)

                # Send signal
                alert = build_alert(
                    name, sig, score, details, last, last["atr"],
                    ob, bos, fvg, liquidity, zone, prev_day,
                    htf_bias, fib, candle, kz_name, sent
                )
                send_telegram(alert)
                stats.record(sig)
                log.info("Signal sent! Score:" + str(score) + "/15")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log.info("Bot stopped.")
            send_telegram("Bot stopped manually.")
            break
        except Exception as e:
            log.error("Error: " + str(e))
            time.sleep(60)


# ══════════════════════════════════════════════════════
#  START EVERYTHING
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    threading.Thread(target=start_web_server, daemon=True).start()
    threading.Thread(target=auto_ping, daemon=True).start()
    run()

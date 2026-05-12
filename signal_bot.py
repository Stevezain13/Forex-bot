"""
╔══════════════════════════════════════════════════════════════════╗
║         STEPHEN'S ULTIMATE SIGNAL BOT v5.0                      ║
║         The Most Powerful Signal Bot Ever Built                  ║
╠══════════════════════════════════════════════════════════════════╣
║  SMC STRATEGIES:                                                 ║
║  ✅ Order Block Detection                                        ║
║  ✅ Break of Structure (BOS)                                     ║
║  ✅ Fair Value Gap (FVG)                                        ║
║  ✅ Liquidity Sweep Detection                                    ║
║  ✅ Premium & Discount Zones                                     ║
║  ✅ Previous Day High/Low                                        ║
║  ✅ Market Structure Shift                                       ║
║  ✅ Higher Timeframe Bias (Daily)                               ║
║                                                                  ║
║  TECHNICAL STRATEGIES:                                           ║
║  ✅ EMA 20/50/200                                               ║
║  ✅ RSI + ADX                                                   ║
║  ✅ Candlestick Patterns                                        ║
║  ✅ Volume Analysis                                              ║
║  ✅ Fibonacci 0.618 & 0.705                                     ║
║  ✅ Correlation Filter                                           ║
║                                                                  ║
║  PROTECTION:                                                     ║
║  ✅ Killzone Filter (London + NY)                               ║
║  ✅ News Protection                                              ║
║  ✅ Weekend Protection                                           ║
║  ✅ Signal Score out of 15                                      ║
║  ✅ Daily Report                                                 ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import time
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import gc
import traceback
from collections import deque

# ═══════════════════════════════════════════════════════
#  ⚙️  CONFIG
# ═══════════════════════════════════════════════════════
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT",  "7781270946")
NEWS_KEY       = os.environ.get("NEWS_KEY",        "")

SYMBOLS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X"
}

CHECK_INTERVAL = 300
MIN_SCORE      = 9

KILLZONES = [
    (10, 0,  13, 0,  "🇬🇧 London Killzone"),
    (16, 0,  19, 0,  "🇺🇸 New York Killzone"),
]

# ══════════════════════════════════════════════════════
#  🛡️ BULLETPROOF SYSTEMS
# ══════════════════════════════════════════════════════

# Duplicate signal filter — never send same signal twice
recent_signals = deque(maxlen=20)

def is_duplicate(name, signal):
    key = f"{name}_{signal}_{datetime.utcnow().strftime('%Y%m%d%H')}"
    if key in recent_signals:
        return True
    recent_signals.append(key)
    return False

# Connection check
def has_internet():
    try:
        requests.get("https://google.com", timeout=5)
        return True
    except:
        return False

# Data fetch with retry
def get_data_with_retry(symbol, retries=3):
    for attempt in range(retries):
        try:
            df = yf.Ticker(symbol).history(period="3mo", interval="1h")
            if df is not None and not df.empty and len(df) >= 50:
                df.columns = [c.lower() for c in df.columns]
                df = df.reset_index()
                for col in ["open","high","low","close"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=["open","high","low","close"])
                if len(df) >= 50:
                    return df
        except Exception as e:
            log.warning(f"Attempt {attempt+1} failed for {symbol}: {e}")
            time.sleep(5)
    return None

# Memory cleaner
def clean_memory():
    gc.collect()
    log.info("🧹 Memory cleaned")

# Heartbeat — sends Telegram every 6 hours
class Heartbeat:
    def __init__(self):
        self.last_beat = datetime.utcnow()
        self.last_daily_check = datetime.utcnow()

    def check(self):
        now = datetime.utcnow()
        hours_since = (now - self.last_beat).total_seconds() / 3600
        if hours_since >= 6:
            self.last_beat = now
            eat = (now.hour + 3) % 24
            send_telegram(f"💓 <b>BOT HEARTBEAT</b>
"
                         f"🕐 Time: {eat:02d}:{now.minute:02d} EAT
"
                         f"✅ Bot is running smoothly!
"
                         f"📊 Watching: EURUSD | GBPUSD | USDJPY")

heartbeat = Heartbeat()

# Startup system check
def startup_check():
    log.info("🔍 Running startup checks...")
    checks_passed = True

    # Check internet
    if has_internet():
        log.info("✅ Internet connection OK")
    else:
        log.error("❌ No internet connection!")
        checks_passed = False

    # Check Telegram token
    if TELEGRAM_TOKEN:
        log.info("✅ Telegram token found")
    else:
        log.error("❌ Telegram token missing!")
        checks_passed = False

    # Check data fetch
    test_df = get_data_with_retry("EURUSD=X", retries=2)
    if test_df is not None:
        log.info(f"✅ Market data OK ({len(test_df)} candles)")
    else:
        log.warning("⚠️ Market data test failed — will retry during run")

    return checks_passed

# Rate limiter for API calls
class RateLimiter:
    def __init__(self, max_calls=5, period=60):
        self.calls = deque()
        self.max_calls = max_calls
        self.period = period

    def can_call(self):
        now = time.time()
        while self.calls and now - self.calls[0] > self.period:
            self.calls.popleft()
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True
        return False

news_limiter = RateLimiter(max_calls=5, period=300)

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
        data = {"chat_id": TELEGRAM_CHAT, "text": message, "parse_mode": "HTML"}
        r    = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            log.info("📱 Telegram sent!")
        else:
            log.warning(f"Telegram error: {r.text}")
    except Exception as e:
        log.warning(f"Telegram failed: {e}")


# ══════════════════════════════════════════════════════
#  ⏰ TIME FILTERS
# ══════════════════════════════════════════════════════

def get_eat_time():
    now = datetime.utcnow()
    return (now.hour + 3) % 24, now.minute, now.weekday()


def is_killzone():
    eat_hour, eat_min, weekday = get_eat_time()
    if weekday >= 5:
        return False, "Weekend"
    current = eat_hour * 60 + eat_min
    for sh, sm, eh, em, name in KILLZONES:
        if sh * 60 + sm <= current < eh * 60 + em:
            return True, name
    return False, "⏳ Outside Killzone — waiting for London(10am) or NY(4pm) EAT"


def is_trading_session():
    eat_hour, eat_min, weekday = get_eat_time()
    if weekday >= 5:
        return False, "Weekend — markets closed"
    london  = 10 <= eat_hour < 19
    newyork = 15 <= eat_hour < 24
    if london and newyork:
        return True, "🇬🇧🇺🇸 London + NY Overlap"
    elif london:
        return True, "🇬🇧 London Session"
    elif newyork:
        return True, "🇺🇸 New York Session"
    return False, "😴 Asian Session — waiting for London (10am EAT)"


def is_friday_night():
    eat_hour, _, weekday = get_eat_time()
    return weekday == 4 and eat_hour >= 21


# ══════════════════════════════════════════════════════
#  📰 NEWS
# ══════════════════════════════════════════════════════

def get_news():
    try:
        r = requests.get("https://newsapi.org/v2/everything", params={
            "q": "forex EURUSD interest rate Federal Reserve ECB",
            "language": "en", "sortBy": "publishedAt",
            "pageSize": 10, "apiKey": NEWS_KEY
        }, timeout=10)
        return [{"title": a["title"]} for a in r.json().get("articles", [])]
    except:
        return []


def is_dangerous_news():
    eat_hour, eat_min, _ = get_eat_time()
    for h, m, name in [(11,30,"London News"),(16,30,"US News"),(18,0,"Fed Speech"),(21,0,"US News")]:
        if abs((eat_hour*60+eat_min)-(h*60+m)) <= 60:
            return True, f"⚠️ Near {name}"
    return False, ""


def check_news_sentiment(news, signal):
    if not news:
        return {"safe": True, "reason": "✅ No news"}
    bullish = ["rate hike","strong","growth","beat","surge","rally"]
    bearish = ["rate cut","weak","recession","miss","crash","drop"]
    danger  = ["NFP","nonfarm","CPI","inflation","FOMC","GDP"]
    bull = bear = 0
    for a in news:
        t = a["title"].lower()
        bull += sum(1 for w in bullish if w in t)
        bear += sum(1 for w in bearish if w in t)
        if any(d.lower() in t for d in danger):
            return {"safe": False, "reason": "⚠️ High impact news!"}
    if signal == "BUY"  and bear > bull+2: return {"safe": False, "reason": "Bearish news"}
    if signal == "SELL" and bull > bear+2: return {"safe": False, "reason": "Bullish news"}
    return {"safe": True, "reason": "✅ News OK"}


# ══════════════════════════════════════════════════════
#  📊 DATA
# ══════════════════════════════════════════════════════

def get_data(symbol, period="3mo", interval="1h"):
    try:
        df = yf.Ticker(symbol).history(period=period, interval=interval)
        if df is None or df.empty or len(df) < 50:
            return None
        df.columns = [c.lower() for c in df.columns]
        df = df.reset_index()
        for col in ["open","high","low","close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["open","high","low","close"])
        return df if len(df) >= 50 else None
    except Exception as e:
        log.warning(f"Data failed {symbol}: {e}")
        return None


def get_daily_data(symbol):
    try:
        df = yf.Ticker(symbol).history(period="3mo", interval="1d")
        if df is None or df.empty:
            return None
        df.columns = [c.lower() for c in df.columns]
        df = df.reset_index()
        for col in ["open","high","low","close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["open","high","low","close"])
    except:
        return None


# ══════════════════════════════════════════════════════
#  📈 INDICATORS
# ══════════════════════════════════════════════════════

def calculate_indicators(df):
    c = df["close"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    o = df["open"].astype(float)

    df["ema20"]  = c.ewm(span=20,  adjust=False).mean()
    df["ema50"]  = c.ewm(span=50,  adjust=False).mean()
    df["ema200"] = c.ewm(span=200, adjust=False).mean()

    delta = c.diff()
    ag = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    al = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
    df["rsi"] = 100 - (100 / (1 + ag/(al+1e-10)))

    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()

    hd = h.diff(); ld = l.diff()
    pdm = hd.where((hd>0)&(hd>-ld), 0.0)
    mdm = (-ld).where((-ld>0)&(-ld>hd), 0.0)
    pdi = 100*(pdm.ewm(span=14,adjust=False).mean()/(df["atr"]+1e-10))
    mdi = 100*(mdm.ewm(span=14,adjust=False).mean()/(df["atr"]+1e-10))
    df["adx"] = (100*(pdi-mdi).abs()/(pdi+mdi+1e-10)).ewm(span=14,adjust=False).mean()

    df["body_pct"] = (c-o).abs()/(h-l+1e-10)*100
    df["vol_ma"]   = df["volume"].rolling(20).mean() if "volume" in df.columns else 1
    return df


def get_signal(df):
    l, p = df.iloc[-1], df.iloc[-2]
    if float(p["ema20"]) <= float(p["ema50"]) and float(l["ema20"]) > float(l["ema50"]):
        return "BUY"
    if float(p["ema20"]) >= float(p["ema50"]) and float(l["ema20"]) < float(l["ema50"]):
        return "SELL"
    return None


# ══════════════════════════════════════════════════════
#  🧠 SMC ANALYSIS
# ══════════════════════════════════════════════════════

def find_order_block(df, direction):
    try:
        for i in range(len(df)-10, len(df)-2):
            if i < 1: continue
            c, n = df.iloc[i], df.iloc[i+1]
            body = abs(float(c["close"])-float(c["open"]))
            nbody = abs(float(n["close"])-float(n["open"]))
            if direction == "BUY":
                if float(c["close"]) < float(c["open"]) and float(n["close"]) > float(n["open"]) and nbody > body*1.5:
                    return {"high": float(c["high"]), "low": float(c["low"]), "found": True}
            else:
                if float(c["close"]) > float(c["open"]) and float(n["close"]) < float(n["open"]) and nbody > body*1.5:
                    return {"high": float(c["high"]), "low": float(c["low"]), "found": True}
    except: pass
    return {"found": False}


def detect_bos(df):
    try:
        highs  = df["high"].astype(float).values
        lows   = df["low"].astype(float).values
        closes = df["close"].astype(float).values
        sh, sl = [], []
        for i in range(2, len(df)-2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                sh.append(highs[i])
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                sl.append(lows[i])
        if len(sh) >= 2 and closes[-1] > sh[-2]: return "BULLISH"
        if len(sl) >= 2 and closes[-1] < sl[-2]: return "BEARISH"
    except: pass
    return None


def find_fvg(df, direction):
    try:
        for i in range(1, len(df)-1):
            p, n = df.iloc[i-1], df.iloc[i+1]
            if direction == "BUY" and float(n["low"]) > float(p["high"]):
                if float(n["low"])-float(p["high"]) >= 0.0003:
                    return {"top": float(n["low"]), "bottom": float(p["high"]), "found": True}
            if direction == "SELL" and float(n["high"]) < float(p["low"]):
                if float(p["low"])-float(n["high"]) >= 0.0003:
                    return {"top": float(p["low"]), "bottom": float(n["high"]), "found": True}
    except: pass
    return {"found": False}


def detect_liquidity_sweep(df, direction):
    try:
        highs  = df["high"].astype(float).values
        lows   = df["low"].astype(float).values
        closes = df["close"].astype(float).values
        n = len(df)
        if direction == "BUY":
            for i in range(n-5, max(n-15,2), -1):
                if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                    if lows[-1] < lows[i] and closes[-1] > lows[i]:
                        return {"found": True, "type": "Sell-side liquidity swept"}
        else:
            for i in range(n-5, max(n-15,2), -1):
                if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                    if highs[-1] > highs[i] and closes[-1] < highs[i]:
                        return {"found": True, "type": "Buy-side liquidity swept"}
    except: pass
    return {"found": False}


def get_premium_discount(df):
    try:
        r = df.tail(50)
        high  = float(r["high"].max())
        low   = float(r["low"].min())
        price = float(df.iloc[-1]["close"])
        mid   = (high+low)/2
        pct   = round((price-low)/(high-low+1e-10)*100, 1)
        return {"zone": "DISCOUNT" if price < mid else "PREMIUM", "percent": pct, "mid": mid}
    except:
        return {"zone": "NEUTRAL", "percent": 50}


def get_prev_day_levels(daily_df):
    try:
        if daily_df is None or len(daily_df) < 2:
            return {"found": False}
        p = daily_df.iloc[-2]
        return {"found": True, "high": float(p["high"]), "low": float(p["low"])}
    except:
        return {"found": False}


def get_htf_bias(daily_df):
    try:
        if daily_df is None or len(daily_df) < 20:
            return "NEUTRAL"
        c  = daily_df["close"].astype(float)
        e20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
        e50 = c.ewm(span=50, adjust=False).mean().iloc[-1]
        return "BULLISH" if e20 > e50 else "BEARISH"
    except:
        return "NEUTRAL"


def get_fibonacci(df):
    try:
        r   = df.tail(50)
        high  = float(r["high"].max())
        low   = float(r["low"].min())
        price = float(df.iloc[-1]["close"])
        rng   = high - low
        f618  = high - rng*0.618
        f705  = high - rng*0.705
        tol   = rng*0.02
        return {
            "found":    abs(price-f618) <= tol or abs(price-f705) <= tol,
            "fib618":   round(f618, 5),
            "fib705":   round(f705, 5)
        }
    except:
        return {"found": False}


def detect_candle_pattern(df, direction):
    try:
        l, p = df.iloc[-1], df.iloc[-2]
        o = float(l["open"]); h = float(l["high"])
        lo= float(l["low"]);  c = float(l["close"])
        body = abs(c-o); rng = h-lo+1e-10
        uw = h-max(o,c); lw = min(o,c)-lo

        if direction == "BUY":
            if c > float(p["open"]) and o < float(p["close"]) and c > o:
                return {"found": True, "pattern": "Bullish Engulfing"}
            if lw > body*2 and uw < body*0.5 and c > o:
                return {"found": True, "pattern": "Hammer"}
            if lw > rng*0.6:
                return {"found": True, "pattern": "Bullish Pin Bar"}
        else:
            if c < float(p["open"]) and o > float(p["close"]) and c < o:
                return {"found": True, "pattern": "Bearish Engulfing"}
            if uw > body*2 and lw < body*0.5 and c < o:
                return {"found": True, "pattern": "Shooting Star"}
            if uw > rng*0.6:
                return {"found": True, "pattern": "Bearish Pin Bar"}
    except: pass
    return {"found": False, "pattern": "None"}


def check_volume(df):
    try:
        if "volume" not in df.columns:
            return {"confirmed": True, "reason": "Volume OK"}
        lv = float(df.iloc[-1]["volume"])
        av = float(df.iloc[-1]["vol_ma"])
        if lv > av*1.5: return {"confirmed": True,  "reason": f"High volume ({lv/av:.1f}x)"}
        if lv > av:     return {"confirmed": True,  "reason": "Normal volume"}
        return {"confirmed": False, "reason": "Low volume"}
    except:
        return {"confirmed": True, "reason": "Volume OK"}


def check_correlation(eu_sig, gb_sig):
    if eu_sig and gb_sig and eu_sig == gb_sig:
        return {"strong": True, "reason": f"EURUSD + GBPUSD both {eu_sig}!"}
    return {"strong": False, "reason": ""}


# ══════════════════════════════════════════════════════
#  🎯 SCORING OUT OF 15
# ══════════════════════════════════════════════════════

def score_signal(df, signal, ob, bos, fvg, liquidity,
                 pd_zone, htf_bias, fib, candle, volume):
    score = 0
    details = []
    try:
        l, p = df.iloc[-1], df.iloc[-2]
        if signal == "BUY":
            if float(p["ema20"]) <= float(p["ema50"]) and float(l["ema20"]) > float(l["ema50"]):
                score+=1; details.append("✅ EMA crossover bullish")
            if float(l["close"]) > float(l["ema200"]):
                score+=1; details.append("✅ Above EMA200")
            if 40 < float(l["rsi"]) < 65:
                score+=1; details.append(f"✅ RSI good ({float(l['rsi']):.0f})")
            if float(l["adx"]) > 25:
                score+=1; details.append(f"✅ ADX strong ({float(l['adx']):.0f})")
            if bos == "BULLISH":
                score+=2; d
    

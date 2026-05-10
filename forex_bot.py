"""
==============================================
  REAL MT5 FOREX TRADING BOT — PYTHON
  Strategy: EMA Crossover (EMA20 vs EMA50)
  Exchange: MetaTrader 5
==============================================

SETUP INSTRUCTIONS:
1. Install MetaTrader 5 on your PC (Windows only): https://www.metatrader5.com
2. Open an account with any MT5 broker (e.g. Exness, IC Markets, XM)
3. Install the Python library:
      pip install MetaTrader5 pandas numpy
4. Fill in your MT5 login details below
5. Run: python forex_bot.py
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime

# ─────────────────────────────────────────
#  ⚙️  CONFIGURATION — EDIT THESE
# ─────────────────────────────────────────
MT5_LOGIN    = 12345678        # Your MT5 account number
MT5_PASSWORD = "YourPassword"  # Your MT5 password
MT5_SERVER   = "Exness-MT5Real" # Your broker's server name

SYMBOL       = "EURUSD"        # Trading pair
TIMEFRAME    = mt5.TIMEFRAME_M15  # 15-minute candles
LOT_SIZE     = 0.01            # Trade size (0.01 = micro lot, safest for beginners)
MAX_TRADES   = 1               # Max open trades at once

# Risk Management
STOP_LOSS_PIPS   = 30          # Stop loss in pips
TAKE_PROFIT_PIPS = 60          # Take profit in pips (2:1 reward/risk)

# Strategy Settings
EMA_SHORT = 20                 # Short EMA period
EMA_LONG  = 50                 # Long EMA period

CHECK_INTERVAL = 60            # How often to check for signals (seconds)
# ─────────────────────────────────────────


def connect():
    """Connect to MetaTrader 5 terminal."""
    print("🔌 Connecting to MT5...")
    if not mt5.initialize():
        print(f"❌ MT5 initialization failed: {mt5.last_error()}")
        return False

    authorized = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    if not authorized:
        print(f"❌ Login failed: {mt5.last_error()}")
        mt5.shutdown()
        return False

    info = mt5.account_info()
    print(f"✅ Connected! Account: {info.login} | Balance: ${info.balance:.2f} | Broker: {info.company}")
    return True


def get_candles(symbol, timeframe, count=100):
    """Fetch recent candle data."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def calculate_ema(df):
    """Calculate EMA indicators."""
    df["ema_short"] = df["close"].ewm(span=EMA_SHORT, adjust=False).mean()
    df["ema_long"]  = df["close"].ewm(span=EMA_LONG,  adjust=False).mean()
    return df


def get_signal(df):
    """
    Generate BUY or SELL signal based on EMA crossover.
    BUY  → short EMA crosses ABOVE long EMA
    SELL → short EMA crosses BELOW long EMA
    """
    last  = df.iloc[-1]
    prev  = df.iloc[-2]

    bullish_cross = prev["ema_short"] <= prev["ema_long"] and last["ema_short"] > last["ema_long"]
    bearish_cross = prev["ema_short"] >= prev["ema_long"] and last["ema_short"] < last["ema_long"]

    if bullish_cross:
        return "BUY"
    elif bearish_cross:
        return "SELL"
    return None


def get_pip_value(symbol):
    """Return pip size for the symbol."""
    info = mt5.symbol_info(symbol)
    if info is None:
        return 0.0001
    return info.point * 10 if "JPY" in symbol else info.point * 10


def count_open_trades(symbol):
    """Count currently open trades for the symbol."""
    positions = mt5.positions_get(symbol=symbol)
    return len(positions) if positions else 0


def place_order(symbol, order_type, lot, stop_loss_pips, take_profit_pips):
    """Place a market order with SL and TP."""
    pip = get_pip_value(symbol)
    tick = mt5.symbol_info_tick(symbol)

    if order_type == "BUY":
        price = tick.ask
        sl    = round(price - stop_loss_pips * pip, 5)
        tp    = round(price + take_profit_pips * pip, 5)
        action = mt5.ORDER_TYPE_BUY
    else:
        price = tick.bid
        sl    = round(price + stop_loss_pips * pip, 5)
        tp    = round(price - take_profit_pips * pip, 5)
        action = mt5.ORDER_TYPE_SELL

    request = {
        "action":    mt5.TRADE_ACTION_DEAL,
        "symbol":    symbol,
        "volume":    lot,
        "type":      action,
        "price":     price,
        "sl":        sl,
        "tp":        tp,
        "deviation": 20,
        "magic":     20250509,       # Bot's unique ID
        "comment":   "EMA Bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"  ✅ {order_type} order placed | Price: {price} | SL: {sl} | TP: {tp}")
    else:
        print(f"  ❌ Order failed: {result.comment} (code {result.retcode})")

    return result


def close_opposite_trades(symbol, new_signal):
    """Close any trades in the opposite direction before opening new one."""
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return

    for pos in positions:
        is_buy  = pos.type == mt5.ORDER_TYPE_BUY
        is_sell = pos.type == mt5.ORDER_TYPE_SELL

        should_close = (new_signal == "BUY" and is_sell) or (new_signal == "SELL" and is_buy)

        if should_close:
            tick = mt5.symbol_info_tick(symbol)
            close_type  = mt5.ORDER_TYPE_BUY if is_sell else mt5.ORDER_TYPE_SELL
            close_price = tick.ask if is_sell else tick.bid

            request = {
                "action":   mt5.TRADE_ACTION_DEAL,
                "symbol":   symbol,
                "volume":   pos.volume,
                "type":     close_type,
                "position": pos.ticket,
                "price":    close_price,
                "deviation": 20,
                "magic":    20250509,
                "comment":  "EMA Bot Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"  🔒 Closed opposite trade #{pos.ticket} | Profit: ${pos.profit:.2f}")


def print_status(df, signal):
    """Print bot status to console."""
    last = df.iloc[-1]
    now  = datetime.now().strftime("%H:%M:%S")
    info = mt5.account_info()

    print(f"\n[{now}] {SYMBOL} | Price: {last['close']:.5f} | "
          f"EMA{EMA_SHORT}: {last['ema_short']:.5f} | "
          f"EMA{EMA_LONG}: {last['ema_long']:.5f}")
    print(f"         Balance: ${info.balance:.2f} | Equity: ${info.equity:.2f} | "
          f"Signal: {'🟢 ' + signal if signal == 'BUY' else ('🔴 ' + signal if signal == 'SELL' else '⚪ HOLD')}")


def run_bot():
    """Main bot loop."""
    print("\n" + "="*50)
    print("   🤖 MT5 FOREX BOT STARTED")
    print(f"   Symbol: {SYMBOL} | Lot: {LOT_SIZE} | TF: 15min")
    print(f"   Strategy: EMA{EMA_SHORT} / EMA{EMA_LONG} Crossover")
    print(f"   SL: {STOP_LOSS_PIPS} pips | TP: {TAKE_PROFIT_PIPS} pips")
    print("="*50 + "\n")

    if not connect():
        return

    try:
        while True:
            # 1. Fetch candles
            df = get_candles(SYMBOL, TIMEFRAME)
            if df is None:
                print("⚠️  Could not fetch candles. Retrying...")
                time.sleep(CHECK_INTERVAL)
                continue

            # 2. Calculate indicators
            df = calculate_ema(df)

            # 3. Get signal
            signal = get_signal(df)
            print_status(df, signal)

            # 4. Act on signal
            if signal:
                open_trades = count_open_trades(SYMBOL)

                # Close opposite trades
                close_opposite_trades(SYMBOL, signal)

                # Open new trade if under max
                if count_open_trades(SYMBOL) < MAX_TRADES:
                    print(f"  📡 Signal: {signal} → Placing order...")
                    place_order(SYMBOL, signal, LOT_SIZE, STOP_LOSS_PIPS, TAKE_PROFIT_PIPS)
                else:
                    print(f"  ⏸️  Max trades ({MAX_TRADES}) reached. Skipping.")
            else:
                print("  ⏳ No signal. Waiting...")

            # 5. Wait before next check
            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user.")
    finally:
        mt5.shutdown()
        print("🔌 Disconnected from MT5.")


# ─────────────────────────────────────────
if __name__ == "__main__":
    run_bot()

#!/bin/bash
# ══════════════════════════════════════════════════════
#  STEPHEN'S BOT AUTO START SCRIPT
#  Just run: bash autostart.sh
#  Bot starts automatically!
# ══════════════════════════════════════════════════════

echo "======================================"
echo "  STEPHEN'S SIGNAL BOT AUTO START"
echo "======================================"

# ── YOUR KEYS — FILL THESE IN ──────────────────────
export TELEGRAM_TOKEN="8749193019:AAEUm6g8PqZk0gH2yKLtv50ANauF4lRWQbs"
export TELEGRAM_CHAT="7781270946"
export NEWS_KEY="a7605dac1cc94f5081c9701e4db949af"
# ────────────────────────────────────────────────────

echo "Setting up environment..."

# Fix DNS
echo "nameserver 8.8.8.8" > /etc/resolv.conf
echo "DNS fixed!"

# Check if bot file exists
if [ ! -f "/root/signal_bot.py" ]; then
    echo "Bot file not found! Downloading..."
    wget -q https://raw.githubusercontent.com/Stevezain13/Forex-bot/main/signal_bot.py
    echo "Bot downloaded!"
else
    echo "Bot file found!"
fi

# Kill any existing bot process
pkill -f signal_bot.py 2>/dev/null
sleep 2

# Start bot in background
echo "Starting bot..."
nohup python3 /root/signal_bot.py > /root/bot.log 2>&1 &

# Save process ID
echo $! > /root/bot.pid

sleep 3

# Check if running
if ps aux | grep -q "signal_bot.py"; then
    echo "======================================"
    echo "  BOT IS RUNNING SUCCESSFULLY!"
    echo "  Check your Telegram now!"
    echo "======================================"
else
    echo "======================================"
    echo "  ERROR: Bot failed to start!"
    echo "  Check: cat /root/bot.log"
    echo "======================================"
fi

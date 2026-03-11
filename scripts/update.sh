#!/bin/bash
# Update River_Permit_Tracker from GitHub and restart the bot (Debian/Proxmox container).
# Run from repo root: ./scripts/update.sh

set -e
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

echo "[$(date -Iseconds)] Starting update in $REPO_ROOT"

# Pull latest (assumes you're on main or your default branch)
git fetch origin
git pull origin main || git pull origin master || git pull

# Refresh Python dependencies (works with or without venv)
if [ -d "$REPO_ROOT/.venv" ]; then
    "$REPO_ROOT/.venv/bin/pip" install -r requirements.txt -q
else
    pip3 install -r requirements.txt -q --user 2>/dev/null || pip3 install -r requirements.txt -q
fi

# Restart systemd service or timer if present (no-op if not using systemd)
if systemctl is-enabled lodore-permit-bot.service &>/dev/null; then
    sudo systemctl restart lodore-permit-bot.service
    echo "Restarted lodore-permit-bot.service"
elif systemctl is-enabled lodore-permit-bot.timer &>/dev/null; then
    sudo systemctl restart lodore-permit-bot.timer
    echo "Restarted lodore-permit-bot.timer"
fi

echo "[$(date -Iseconds)] Update complete"

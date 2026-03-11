# Gates of Lodore Permit Tracker

Monitors [recreation.gov](https://www.recreation.gov) for permit availability on **Gates of Lodore, Green River** (Dinosaur National Monument) and sends email (and optional push) notifications when new dates open up.

## Quick start (local)

```bash
git clone https://github.com/YOUR_USERNAME/River_Permit_Tracker.git
cd River_Permit_Tracker
cp .env.example .env
# Edit .env with your SMTP and notification settings
pip install -r requirements.txt
python3 lodore_permit_bot-2.py --test-email   # verify email
python3 lodore_permit_bot-2.py               # one-time check
```

## Debian container on Proxmox

### First-time setup

1. **Clone the repo** (e.g. under `/opt` or your preferred path):

   ```bash
   sudo mkdir -p /opt
   sudo git clone https://github.com/YOUR_USERNAME/River_Permit_Tracker.git /opt/River_Permit_Tracker
   cd /opt/River_Permit_Tracker
   ```

2. **Create `.env`** (never commit this):

   ```bash
   cp .env.example .env
   nano .env   # or vim — add your SMTP_USER, SMTP_PASS, NOTIFY_EMAIL, etc.
   ```

3. **Install Python deps** (use a venv if you prefer):

   ```bash
   sudo apt update && sudo apt install -y python3 python3-pip python3-venv
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

4. **Run on a schedule** — choose one:

   - **Cron (simple):** run the bot every 5 minutes:

     ```bash
     sudo crontab -e
     # Add:
     */5 * * * * /opt/River_Permit_Tracker/.venv/bin/python3 /opt/River_Permit_Tracker/lodore_permit_bot-2.py >> /var/log/lodore-bot.log 2>&1
     ```

   - **Systemd timer:** use the included service + timer so you can start/stop/restart cleanly:

     ```bash
     sudo cp systemd/lodore-permit-bot.service systemd/lodore-permit-bot.timer /etc/systemd/system/
     # Edit the service file if your path or venv is different
     sudo systemctl daemon-reload
     sudo systemctl enable --now lodore-permit-bot.timer
     ```

### Updating the app from GitHub

From the repo directory on the Debian container:

```bash
cd /opt/River_Permit_Tracker
./scripts/update.sh
```

This script:

- Pulls the latest code from GitHub
- Installs/upgrades Python dependencies
- Restarts the systemd timer (if you use it), or does nothing for cron (next cron run uses new code)

On first clone, make the update script executable: `chmod +x scripts/update.sh`.

**Automate updates (optional):** run the update script daily via cron:

```bash
sudo crontab -e
# Add (runs at 3 AM):
0 3 * * * /opt/River_Permit_Tracker/scripts/update.sh >> /var/log/lodore-bot-update.log 2>&1
```

## Configuration

| Variable | Description |
|----------|-------------|
| `SMTP_USER` | Sender email (e.g. Gmail address) |
| `SMTP_PASS` | App password (Gmail: [App Passwords](https://support.google.com/accounts/answer/185833)) |
| `NOTIFY_EMAIL` | Where to send alerts |
| `PUSHOVER_USER` / `PUSHOVER_TOKEN` | Optional push notifications |
| `LOG_LEVEL` | Optional, e.g. `DEBUG` |

See `.env.example` for all options.

## Commands

| Command | Description |
|---------|-------------|
| `python3 lodore_permit_bot-2.py` | Check once and send notifications for new dates |
| `python3 lodore_permit_bot-2.py --test-email` | Send a single test email |
| `python3 lodore_permit_bot-2.py --debug` | Extra logging and save `debug_response_*.json` |

## License

Use and modify as you like.

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

   - **Cronicle:** create a job that runs every 5 minutes. Each run does one check and exits. Set the job’s **Working Directory** to the repo (e.g. `/opt/River_Permit_Tracker`) so `.env` is loaded. Logs go to `lodore_bot.log` in that dir; Cronicle also shows stdout/stderr for each run.

     - **Command:** `./.venv/bin/python3 lodore_permit_bot-2.py`  
       (or full path: `/opt/River_Permit_Tracker/.venv/bin/python3 /opt/River_Permit_Tracker/lodore_permit_bot-2.py`)
     - **Schedule:** every 5 minutes (e.g. `*/5 * * * *` or Cronicle’s “Every 5 min”).
     - To pull code updates on a schedule, add a second Cronicle job that runs `./scripts/update.sh` daily (same working directory).

   - **Cron:** run the bot once every 5 minutes. Disable the systemd service first if you used it: `sudo systemctl stop lodore-permit-bot && sudo systemctl disable lodore-permit-bot`

     ```bash
     sudo crontab -e
     # Add (edit path if repo is elsewhere):
     */5 * * * * /opt/River_Permit_Tracker/.venv/bin/python3 /opt/River_Permit_Tracker/lodore_permit_bot-2.py
     ```
     Or copy from `cron.example`.

   - **Systemd (continuous):** one long-running process; restarts on failure. Use cron or Cronicle *or* systemd, not both for the same bot.

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

## Logging

All runs write to **console** and to **`lodore_bot.log`** in the repo directory (rotating, 5 MB × 3 backups). Override with env:

- `LOG_FILE=/var/log/lodore-bot.log` — log path
- `LOG_LEVEL=DEBUG` — more verbose
- `LOG_FILE_MAX_MB=10` — max MB per file (default 5)

View logs: `tail -f /opt/River_Permit_Tracker/lodore_bot.log` (or your `LOG_FILE` path). In Cronicle, you can point the job at the repo dir and open `lodore_bot.log`, or set `LOG_FILE` to a path Cronicle can show.

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

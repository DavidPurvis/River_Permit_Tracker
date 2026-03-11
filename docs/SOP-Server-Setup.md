# SOP: River Permit Tracker — Server Setup

Standard Operating Procedure for deploying and running the Gates of Lodore Permit Tracker on a Debian container (e.g. on Proxmox). Follow in order.

---

## Prerequisites

- Debian (or Debian-based) container or VM with network access.
- Root or sudo access.
- GitHub repo URL (e.g. `https://github.com/YOUR_USERNAME/River_Permit_Tracker`).
- Gmail (or other SMTP) credentials: address, App Password, and the email address that should receive alerts.

---

## Phase 1: One-time server setup

### 1.1 Install system packages

```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-venv
```

### 1.2 Clone the repository

Replace `YOUR_USERNAME` with your GitHub username (or use your actual repo URL).

```bash
sudo mkdir -p /opt
sudo git clone https://github.com/YOUR_USERNAME/River_Permit_Tracker.git /opt/River_Permit_Tracker
cd /opt/River_Permit_Tracker
```

### 1.3 Create Python virtual environment and install dependencies

```bash
cd /opt/River_Permit_Tracker
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 1.4 Create and edit `.env` (secrets)

```bash
cp .env.example .env
nano .env
```

Set at least:

- `SMTP_USER` — your Gmail (or sender) address  
- `SMTP_PASS` — Gmail App Password (not your normal password)  
- `NOTIFY_EMAIL` — where to send alerts  

Save and exit (in nano: Ctrl+O, Enter, Ctrl+X).

### 1.5 Make the update script executable

```bash
chmod +x /opt/River_Permit_Tracker/scripts/update.sh
```

### 1.6 Verify the bot runs and email works

```bash
cd /opt/River_Permit_Tracker
.venv/bin/python3 lodore_permit_bot-2.py --test-email
```

- If you see “Test email sent” and receive the test email, continue.  
- If it fails, fix `.env` (no spaces around `=`, no quotes unless needed) and repeat.

### 1.7 Run one full check (optional)

```bash
.venv/bin/python3 lodore_permit_bot-2.py
```

Confirm it finishes without errors and that you get an alert if there are available dates.

---

## Phase 2: Run the bot

Choose **one** of the options below. Use only one (Cronicle, cron, or systemd) so the bot isn’t run twice.

---

### Option A: Cronicle

1. If the systemd service is enabled, disable it:

   ```bash
   sudo systemctl stop lodore-permit-bot
   sudo systemctl disable lodore-permit-bot
   ```

2. In Cronicle, create a new job:

   - **Job Title:** e.g. “Lodore Permit Check”
   - **Working Directory:** `/opt/River_Permit_Tracker` (or your repo path). Required so `.env` is loaded.
   - **Command:** `./.venv/bin/python3 lodore_permit_bot-2.py`  
     Or use full paths: `/opt/River_Permit_Tracker/.venv/bin/python3 /opt/River_Permit_Tracker/lodore_permit_bot-2.py`
   - **Schedule:** every 5 minutes (e.g. “Every 5 min” or cron `*/5 * * * *`).
   - **Run as:** a user that can read the repo and `.env` (often root or the user that owns the repo).

3. Save and enable the job. Logs: Cronicle shows stdout/stderr per run; the bot also appends to `lodore_bot.log` in the repo dir.

4. (Optional) Add a second job to pull updates daily: same working directory, command `./scripts/update.sh`, schedule e.g. daily at 3 AM.

---

### Option B: Cron

1. Disable the systemd service if it’s enabled (see Option A step 1).

2. `sudo crontab -e` and add:

   ```cron
   */5 * * * * /opt/River_Permit_Tracker/.venv/bin/python3 /opt/River_Permit_Tracker/lodore_permit_bot-2.py
   ```

3. After 5 minutes: `tail -20 /opt/River_Permit_Tracker/lodore_bot.log`

Copy the line from: `cat /opt/River_Permit_Tracker/cron.example`

---

### Option C: Systemd (continuous)

One long-running process that polls every 5 minutes (or set `POLL_INTERVAL_SECONDS` in `.env`). Use this instead of Cronicle/cron if you prefer a single process and automatic restarts.

1. `sudo cp /opt/River_Permit_Tracker/systemd/lodore-permit-bot.service /etc/systemd/system/`
2. Edit the service if the repo path is different.
3. `sudo systemctl daemon-reload && sudo systemctl enable --now lodore-permit-bot.service`
4. `tail -f /opt/River_Permit_Tracker/lodore_bot.log`

---

## Phase 3: Updating the program from GitHub

When you push changes to GitHub and want the server to use the new code:

### 3.1 Run the update script

```bash
cd /opt/River_Permit_Tracker
./scripts/update.sh
```

This will:

- `git pull` (from `main` or `master`)
- Reinstall/upgrade Python dependencies from `requirements.txt`
- Restart the systemd service (if you use Option A) or timer (if you use the timer); cron picks up new code on the next run

### 3.2 (Optional) Automate updates with cron

To pull updates daily (e.g. at 3 AM), add to root crontab:

```bash
sudo crontab -e
```

Add:

```cron
0 3 * * * /opt/River_Permit_Tracker/scripts/update.sh >> /var/log/lodore-bot-update.log 2>&1
```

---

## Quick reference

| Task                    | Command |
|-------------------------|--------|
| Test email              | `cd /opt/River_Permit_Tracker && .venv/bin/python3 lodore_permit_bot-2.py --test-email` |
| Run one check           | `cd /opt/River_Permit_Tracker && .venv/bin/python3 lodore_permit_bot-2.py` |
| Pull updates            | `cd /opt/River_Permit_Tracker && ./scripts/update.sh` |
| View log file           | `tail -f /opt/River_Permit_Tracker/lodore_bot.log` |
| Edit cron               | `sudo crontab -e` |
| Disable systemd (use cron) | `sudo systemctl stop lodore-permit-bot && sudo systemctl disable lodore-permit-bot` |
| Service status          | `sudo systemctl status lodore-permit-bot` |

---

## Troubleshooting

- **No email received**  
  Run `--test-email` and check the output. Ensure `SMTP_USER`, `SMTP_PASS`, and `NOTIFY_EMAIL` are set in `.env` and that Gmail uses an App Password, not your account password.

- **Permission denied on `update.sh`**  
  Run: `chmod +x /opt/River_Permit_Tracker/scripts/update.sh`

- **Service not running (systemd)**  
  Run: `sudo systemctl status lodore-permit-bot` and `journalctl -u lodore-permit-bot -n 50`

- **Wrong Python or path**  
  Confirm: `ls /opt/River_Permit_Tracker/.venv/bin/python3` and that crontab or the systemd service use this path.

- **Git pull fails (auth)**  
  If the repo is private, set up SSH keys or a credential helper on the server so `git pull` can authenticate.

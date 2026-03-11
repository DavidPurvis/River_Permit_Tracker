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

## Phase 2: Run the bot on a schedule

Choose **one** of the two options below.

---

### Option A: Cron (simplest)

1. Open root’s crontab:

   ```bash
   sudo crontab -e
   ```

2. Add this line (runs every 5 minutes and appends to a log file):

   ```cron
   */5 * * * * /opt/River_Permit_Tracker/.venv/bin/python3 /opt/River_Permit_Tracker/lodore_permit_bot-2.py >> /var/log/lodore-bot.log 2>&1
   ```

3. Save and exit.  
4. Ensure the log file can be created (first run will create it):

   ```bash
   sudo touch /var/log/lodore-bot.log
   sudo chmod 644 /var/log/lodore-bot.log
   ```

5. After 5 minutes, confirm runs:

   ```bash
   tail -20 /var/log/lodore-bot.log
   ```

---

### Option B: Systemd timer

1. Copy service and timer into systemd:

   ```bash
   sudo cp /opt/River_Permit_Tracker/systemd/lodore-permit-bot.service /etc/systemd/system/
   sudo cp /opt/River_Permit_Tracker/systemd/lodore-permit-bot.timer /etc/systemd/system/
   ```

2. If the repo is **not** at `/opt/River_Permit_Tracker`, edit the service:

   ```bash
   sudo nano /etc/systemd/system/lodore-permit-bot.service
   ```

   Update `WorkingDirectory` and the paths in `ExecStart` to match your install path.

3. Reload systemd and enable the timer:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable lodore-permit-bot.timer
   sudo systemctl start lodore-permit-bot.timer
   ```

4. Confirm the timer is active:

   ```bash
   sudo systemctl status lodore-permit-bot.timer
   sudo systemctl list-timers lodore-permit-bot.timer
   ```

5. View bot output in the journal:

   ```bash
   journalctl -u lodore-permit-bot.service -n 50
   ```

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
- Restart the systemd timer if you use Option B (cron will pick up new code on the next run automatically)

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
| View cron log           | `tail -f /var/log/lodore-bot.log` |
| View systemd runs       | `journalctl -u lodore-permit-bot.service -f` |
| Stop timer (systemd)    | `sudo systemctl stop lodore-permit-bot.timer` |
| Start timer (systemd)   | `sudo systemctl start lodore-permit-bot.timer` |

---

## Troubleshooting

- **No email received**  
  Run `--test-email` and check the output. Ensure `SMTP_USER`, `SMTP_PASS`, and `NOTIFY_EMAIL` are set in `.env` and that Gmail uses an App Password, not your account password.

- **Permission denied on `update.sh`**  
  Run: `chmod +x /opt/River_Permit_Tracker/scripts/update.sh`

- **Timer not firing (systemd)**  
  Run: `sudo systemctl list-timers --all | grep lodore` and `journalctl -u lodore-permit-bot.timer -n 20`

- **Wrong Python or path**  
  Confirm: `ls /opt/River_Permit_Tracker/.venv/bin/python3` and that crontab or the systemd service use this path.

- **Git pull fails (auth)**  
  If the repo is private, set up SSH keys or a credential helper on the server so `git pull` can authenticate.

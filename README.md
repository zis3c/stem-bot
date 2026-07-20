# STEM Telebot

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)
![PTB](https://img.shields.io/badge/python--telegram--bot-v20%2B-2AABEE)
![aiohttp](https://img.shields.io/badge/aiohttp-Async%20HTTP-005571)
![gspread](https://img.shields.io/badge/gspread-Sheets%20API-4285F4?logo=google-sheets&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen.svg)

A high-performance, bilingual Telegram bot built for the STEM USAS student organization. It simplifies membership verification and provides administrative tools to manage the student registry via Google Sheets.

> [!NOTE]
> **Real-time Sync**: The bot acts as a bridge between Telegram and a Google Sheets backend. It features automated alerts for new registrations and handles member approvals with dedicated administrative layers.

## Features

- **Multi-lingual Interface**: Full support for English and Bahasa Melayu (Switch via `/settings` or the menu).
- **Membership Verification**: 2-step verification using **Matric Number** and **IC Last 4 Digits** against official records.
- **Interactive Registration Info**: View membership benefits and follow guided registration prompts.
- **Admin Command Suite**:
  - **Member Search**: Find students by Name, Matric, or IC with "Simple" or "Detailed" result views.
  - **Broadcast System**: Send announcements to all registered users with de-duplication and delivery reports.
  - **Status Management**: List members, view detailed profiles, or remove entries directly via bot.
  - **Manual Registration Check**: Trigger an immediate scan of the sheet for new signups.
- **Superadmin Control Panel**:
  - **Maintenance Mode**: Lock the bot for everyone except admins.
  - **System Health**: Monitor CPU usage, RAM, and Bot Uptime in real-time.
  - **Admin Management**: Add or remove secondary admins via Telegram ID.
  - **Log Reporting**: Receive automated daily activity log reports on your Telegram.

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/zis3c/STEM-Telebot.git
   cd STEM-Telebot
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv .venv
   # Windows PowerShell
   .\.venv\Scripts\Activate.ps1
   # Linux/macOS
   # source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   copy .env.example .env   # Windows
   # cp .env.example .env   # Linux/macOS
   ```

5. **Setup Google Cloud**
   - Place your `service_account.json` in the project root.
   - Share your Google Sheet with the Service Account email.

6. **Run bot**
   ```bash
   python bot.py
   ```

## Environment Variables

**Core:**
- `TELEGRAM_TOKEN` - Bot token from [@BotFather](https://t.me/BotFather)
- `PORT` - Local health endpoint port (default `10000`)
- `WEBHOOK_URL` - Optional (leave empty for polling mode)
- `TELEGRAM_WEBHOOK_SECRET` - Required when `WEBHOOK_URL` is enabled
- `TELEGRAM_WEBHOOK_IP_VALIDATE` - Validate source IP for webhook (`true`/`false`, default `false`)
- `TRUST_PROXY_HOPS` - Trusted reverse-proxy hop count for `X-Forwarded-For` parsing (default `1`)
- `TELEGRAM_IP_RANGES` - Comma-separated CIDR allowlist for Telegram webhook IPs

**Google Sheets:**
- `SHEET_ID` - The unique ID of the STEM Google Spreadsheet
- `GOOGLE_CREDENTIALS` - (Optional) JSON string of your service account key
- `REGISTRATIONS_SHEET_NAME` - Main sheet tab name for registrations data, default `STEM DB`

**Access Control:**
- `SUPERADMIN_IDS` - Comma-separated Telegram IDs for Superadmins
- `ADMIN_IDS` - Comma-separated Telegram IDs for Admins

**Security / Abuse Controls:**
- `GLOBAL_RATE_WINDOW_SEC` - Sliding window duration for anti-flood controls (default `60`)
- `GLOBAL_RATE_MAX_REQ` - Max requests per window for protected flows (default `25`)
- `MAX_INPUT_LEN_MATRIC` - Max matric input length (default `24`)
- `MAX_INPUT_LEN_SEARCH` - Max admin search query length (default `80`)
- `MAX_INPUT_LEN_BROADCAST` - Max broadcast message length (default `2000`)
- `BROADCAST_MAX_RECIPIENTS` - Hard cap recipients per broadcast run (default `5000`)
- `BROADCAST_MSGS_PER_SEC` - Broadcast send throttle in messages/sec (default `12`)

## Deploy to DigitalOcean (Recommended)

This project is optimized for deployment on a DigitalOcean Droplet using `systemd`.

1. Clone the repo and install dependencies.
2. Configure `.env` and `service_account.json`.
3. Create a systemd service (e.g., `/etc/systemd/system/stem-telebot.service`).
4. Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now stem-telebot
   ```

## Auto Deploy (GitHub Actions)

Push to `main` triggers `.github/workflows/deploy-digitalocean.yml`.
Ensure you have set the following GitHub Secrets:
- `DROPLET_HOST`
- `DROPLET_USER` (e.g., `deploy`)
- `DROPLET_SSH_KEY`

## Project Structure

```text
STEM-Telebot/
|- .github/
|  `- workflows/
|     |- deploy-digitalocean.yml   # GitHub Actions deploy workflow
|     `- security-audit.yml        # GitHub Actions pip-audit workflow
|- admin.py                        # Admin panel actions
|- AUTO_DEPLOY.md                  # DigitalOcean deploy guide
|- bot.py                          # Main entrypoint, polling/webhook bootstrap
|- CONTRIBUTING.md                 # Contribution guide
|- database.py                     # Google Sheets API wrapper and activity logging
|- demographic_stats_template.py   # Web demographic dashboard HTML template
|- google_apps_script.js           # Apps Script helper for Sheets automation
|- handlers.py                     # Core user flows
|- INSTALLATION.md                 # Full install and setup guide
|- keyboards.py                    # Reply and inline keyboard layouts
|- membership_card_template.py      # Web membership card HTML template
|- README.md                       # Project overview
|- requirements.txt                # Project dependencies
|- SECURITY.md                     # Security policy
|- security_utils.py               # Input and security event helpers
|- states.py                       # Conversation flow state constants
|- stats_web.py                    # Web stats page helpers
|- strings.py                      # User-facing text in EN and MS
|- superadmin.py                   # Superadmin controls
`- STEM Bot Manual Guide.pdf       # User manual
```

## Web UI Templates

- Membership web card UI is rendered from `membership_card_template.py`.
- Demographic web dashboard UI is rendered from `demographic_stats_template.py`.
- `bot.py` now calls these template modules to keep the main file cleaner and easier to maintain.

## Commands

| Command | Description |
|:--------|:------------|
| `/start` | Open main menu |
| `/help` | Show usage and info |
| `/settings` | Open language/settings menu |
| `/admin` | Open admin dashboard (Admins only) |
| `/superadmin` | Open superadmin panel (Superadmins only) |
| `/check_pending` | Scan for pending registrations |
| `/cancel` | Cancel current operation |

## How It Works

1. **User Interaction**: Users check membership by entering their Matric and IC last 4 digits.
2. **Sheet Verification**: The bot searches the Google Sheet and returns the verification status.
3. **Admin Monitoring**: Background jobs track new registration rows and notify admins instantly.
4. **Member Management**: Admins can search, list, or delete members and broadcast messages to all users.
5. **System Oversight**: Superadmins monitor system health and receive daily activity logs.

## Troubleshooting

- **Bot not responding**: Check if the `TELEGRAM_TOKEN` is correct.
- **Sheets Error**: Ensure the service account email has **Editor** access to the sheet.
- **Sheet Name**: Confirm `REGISTRATIONS_SHEET_NAME` matches the main data tab, default `STEM DB`.
- **Admin Access**: Verify your ID is in `ADMIN_IDS` or `SUPERADMIN_IDS`.
- **Service Fails**: Check logs using `journalctl -u stem-telebot -n 100`.

## Additional Docs

- [AUTO_DEPLOY.md](AUTO_DEPLOY.md)
- [INSTALLATION.md](INSTALLATION.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [LICENSE](LICENSE)

<center>Built with 🔥 by <b>@zis3c</b></center>

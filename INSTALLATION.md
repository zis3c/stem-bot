# STEM Telebot - Installation and Setup Guide

This guide explains how to set up the project end-to-end so new contributors can run it locally or deploy it on a server.

## 1. Prerequisites

- Git
- Python 3.10+
- A Telegram account (for BotFather and admin testing)
- A Google account (for Google Sheets + Apps Script)
- A Linux VPS (optional, for production)

## 2. Clone the Project

```bash
git clone https://github.com/zis3c/STEM-Telebot.git
cd STEM-Telebot
```

## 3. Create Virtual Environment and Install Dependencies

Windows (PowerShell):

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. Create Telegram Bot

1. Open [@BotFather](https://t.me/BotFather)
2. Run `/newbot`
3. Save the bot token

You will use this value as `TELEGRAM_TOKEN`.

## 5. Set Up Google Sheet Backend

1. Create a Google Sheet.
2. Create required tabs:

### `STEM DB` (main data tab)

Column order must match the bot and Apps Script:

| Col | Field |
| --- | --- |
| A | Timestamp |
| B | Personal Email |
| C | Name |
| D | Matric |
| E | Course |
| F | Semester |
| G | Phone Number |
| H | Alternate Email |
| I | USAS Email |
| J | IC Number |
| K | Birthday |
| L | Birth Place |
| M | Address |
| N | Date of Entry |
| O | Minute Number |
| P | Membership Number |
| Q | Receipt Proof |
| R | Status |
| S | Payment Receipt URL |
| T | Invoice No |
| U | Statistic |

If you rename this tab, set `REGISTRATIONS_SHEET_NAME` to the new name.

### `system_admins`

Headers:

- `User ID`
- `Name`
- `Added By`

### `system_config`

Headers:

- `Key`
- `Value`

Initial row:

- `maintenance_mode` | `False`

## 6. Google Cloud Service Account

1. Go to Google Cloud Console.
2. Create/select a project.
3. Enable APIs:
- Google Sheets API
- Google Drive API
4. Create a Service Account.
5. Create and download JSON key.
6. Share the Google Sheet with the service account `client_email` as Editor.

Save key file as:

```text
service_account.json
```

Place it in project root, or provide JSON via `GOOGLE_CREDENTIALS` env var.

## 7. Environment Variables

Copy `.env.example` to `.env` and set values.

Required:

- `TELEGRAM_TOKEN`
- `SHEET_ID`
- `SUPERADMIN_IDS`
- `ADMIN_IDS`

Optional/recommended:

- `WEBHOOK_URL` (set only if running Telegram webhook mode)
- `PUBLIC_BASE_URL` (set for membership and demographic web links)
- `TELEGRAM_WEBHOOK_SECRET`
- `GOOGLE_CREDENTIALS` (if not using local `service_account.json`)
- rate-limit and security env values from `README.md`

## 8. Configure Google Apps Script (Required for approval/reject flow)

The approval/reject + receipt pipeline is controlled by Apps Script.

1. Open your Google Sheet.
2. Go to `Extensions > Apps Script`.
3. Replace existing code with contents of `google_apps_script.js`.
4. Save the script.
5. Run `setupSecrets` once and set real values in Script Properties:
- `RECEIPT_FOLDER_ID`
- `LOGO_FILE_ID`
- `ADMIN_WEBHOOK_TOKEN`
6. Run `setupTrigger` once to create `onFormSubmit` trigger.
7. Deploy Apps Script as Web App:
- Execute as: `Me`
- Who has access: `Anyone` (or appropriate policy that your bot server can call)
8. Copy Web App URL (ends with `/exec`).

## 9. Connect Bot Server to Apps Script Webhook

In server environment (`/etc/stem-telebot/bot.env` in production), set:

- `APPS_SCRIPT_WEBHOOK_URL=<your_apps_script_exec_url>`
- `APPS_SCRIPT_WEBHOOK_TOKEN=<same ADMIN_WEBHOOK_TOKEN from Script Properties>`

This is used by the bot to trigger:

- Approve action -> Apps Script `approveStudentAndSendReceipt`
- Reject action -> Apps Script `rejectStudentAndDeleteRow`

## 10. Run Locally

```bash
python bot.py
```

If startup is successful, the bot begins polling (unless webhook mode is configured).

## 11. Deploy to Linux VPS with systemd

Example path:

```text
/opt/stem-telebot
```

Install and run:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
sudo mkdir -p /opt/stem-telebot
sudo chown "$USER":"$USER" /opt/stem-telebot
git clone --depth 1 --branch main https://github.com/zis3c/STEM-Telebot.git /opt/stem-telebot
cd /opt/stem-telebot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create env file:

```text
/etc/stem-telebot/bot.env
```

Minimum production keys:

- `TELEGRAM_TOKEN`
- `SHEET_ID`
- `SUPERADMIN_IDS`
- `ADMIN_IDS`
- `PUBLIC_BASE_URL`
- `APPS_SCRIPT_WEBHOOK_URL`
- `APPS_SCRIPT_WEBHOOK_TOKEN`

Start service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now stem-telebot
sudo systemctl status stem-telebot
```

View logs:

```bash
journalctl -u stem-telebot -n 100 --no-pager
```

## 12. Verify End-to-End Flow

1. Submit a new form row in `STEM DB`.
2. Confirm row status becomes `Pending`.
3. Check admin bot receives pending notification.
4. Press Approve in bot:
- Sheet row becomes `Approved`
- Membership ID/invoice handled by Apps Script
- Receipt email is sent by Apps Script
5. Press Reject in bot:
- Row is deleted from sheet by Apps Script
- Admin sees clear reject confirmation text

## 13. Common Issues

- `401 Unauthorized` for Apps Script webhook:
- Check `APPS_SCRIPT_WEBHOOK_TOKEN` exactly matches `ADMIN_WEBHOOK_TOKEN`.
- Make sure Web App URL is `/exec`, not `/dev`.

- Admin button says approved/rejected but sheet unchanged:
- Verify `APPS_SCRIPT_WEBHOOK_URL` points to latest deployed Apps Script.
- Redeploy Web App after editing script.

- Google Sheets permission errors:
- Ensure service account has Editor access to the sheet.
- Confirm `REGISTRATIONS_SHEET_NAME` matches the main tab name, default `STEM DB`.

- Bot starts but no pending alerts:
- Confirm main sheet tab name is exactly `STEM DB`.
- Confirm status column is `R` and new rows become `Pending`.

## 14. Related Docs

- `README.md`
- `AUTO_DEPLOY.md`
- `CONTRIBUTING.md`
- `google_apps_script.js`

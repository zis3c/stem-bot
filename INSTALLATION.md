# 🛠️ Installation & Setup Guide

This guide provides a step-by-step tutorial to set up the **Eligible STEM Bot** locally or on a server.

---

## 📋 Prerequisites

Before starting, ensure you have:
1.  **Git** installed ([Download](https://git-scm.com/downloads)).
2.  **Python 3.9** or higher installed ([Download](https://www.python.org/downloads/)).
3.  A **Google Account** (for Google Sheets/Cloud).
4.  A **Telegram Account**.

---

## 🚀 Step 1: Clone the Repository

Open your terminal or command prompt and run:

```bash
git clone https://github.com/zis3c/stem-bot.git
cd stem-bot
```

---

## 🐍 Step 2: Set Up Python Environment

It is recommended to use a virtual environment to avoid conflicts.

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Mac/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

Install the required libraries:
```bash
pip install -r requirements.txt
```

---

## 🤖 Step 3: Create Telegram Bot

1.  Open Telegram and search for **[@BotFather](https://t.me/BotFather)**.
2.  Send `/newbot`.
3.  Follow the prompts to name your bot (e.g., `MySTEMBot`) and give it a username (e.g., `MySTEM_bot`).
4.  **Copy the HTTP API Token**. You will need this for the `.env` file.

---

## ☁️ Step 4: Google Cloud Setup (Sheets API)

This bot uses Google Sheets as a database. You need a Service Account credentials file.

1.  Go to the [Google Cloud Console](https://console.cloud.google.com/).
2.  **Create a New Project** (e.g., "STEM Bot").
3.  **Enable APIs**:
    *   Go to **APIs & Services > Library**.
    *   Search for **"Google Sheets API"** -> Enable.
    *   Search for **"Google Drive API"** -> Enable.
4.  **Create Service Account**:
    *   Go to **APIs & Services > Credentials**.
    *   Click **Create Credentials > Service Account**.
    *   Name it (e.g., "bot-service"). Click **Create & Continue**.
    *   Role: **Editor** (Basic > Editor). Click **Done**.
5.  **Generate Keys**:
    *   Click on the email of the service account you just created (e.g., `bot-service@project-id.iam.gserviceaccount.com`).
    *   Go to the **Keys** tab.
    *   Click **Add Key > Create new key**.
    *   Select **JSON**.
    *   A file will download (e.g., `project-id-12345.json`). **Keep this safe!**

---

## 📊 Step 5: Configure Google Sheets

1.  **Create a New Google Sheet**.
2.  **Share the Sheet**:
    *   Open the JSON key file you downloaded in Step 4.
    *   Find the `"client_email"` field. Copy the email address.
    *   Go to your Google Sheet > Click **Share** > Paste the email > **Editor** access > Send.
3.  **Get Sheet ID**:
    *   Look at the URL of your spreadsheet:
        `https://docs.google.com/spreadsheets/d/1aBcD...xYz/edit`
    *   The ID is the long string between `/d/` and `/edit`. Copy this.

4.  **Create Required Tabs**:
    *   **Tab 1 Name**: `Registrations`
    *   **Structure for `Registrations` Sheet** (Important!):
        *   The bot communicates up to **Column R (18)**. Ensure your sheet has at least 18 columns.
        *   **Key Columns**:
            *   `Col A` (Timestamp)
            *   `Col C` (Name)
            *   `Col D` (Matric)
            *   `Col E` (Program)
            *   `Col J` (IC Number)
            *   `Col N` (Date of Entry)
            *   `Col P` (Membership ID)
            *   `Col Q` (Receipt)
            *   `Col R` (Status)
    *   **Tab 2 Name**: `system_admins`
        *   Headers: `User ID`, `Name`, `Added By`
    *   **Tab 3 Name**: `system_config`
        *   Headers: `Key`, `Value`
        *   Add a row: `maintenance_mode` | `False`

    *   "Run" > "setupTrigger".
    *   Grant permissions if requested.

    > **Note**: This script handles the `Membership ID` generation and `Date of Entry` formatting automatically.

---

## 📜 Step 5b: Google Apps Script (Automation)

The bot relies on a script running inside the Google Sheet to generate IDs and format dates.

1.  **Open Script Editor**:
    *   In your Google Sheet, go to **Extensions** > **Apps Script**.
2.  **Paste Code**:
    *   Delete any existing code in `Code.gs`.
    *   Open `google_apps_script.js` from this repository.
    *   Copy the entire content and paste it into the script editor.
3.  **Save**:
    *   Press `Ctrl+S` (or `Cmd+S`) to save the project.
4.  **Setup Trigger**:
    *   In the function dropdown (top bar), select `setupTrigger`.
    *   Click **Run**.
    *   **Grant Permissions**: Google will ask for permission. Click "Review Permissions" > Choose Account > "Advanced" > "Go to (Project Name) (unsafe)" > "Allow".
5.  **Verify**:
    *   Go to the **Triggers** icon (alarm clock) in the left sidebar.
    *   You should see a trigger for `onFormSubmit`.

---

## 📅 Step 5c: Monthly Statistics (Optional)

To enable the automatic monthly separator row (e.g., `--- STATISTIK DISEMBER ---`):

1.  In Apps Script, click **Triggers** (alarm clock).
2.  Click **Add Trigger** (blue button).
3.  Configure:
    *   **Function**: `generateMonthlyStats`
    *   **Deployment**: `Head`
    *   **Event Source**: `Time-driven`
    *   **Type**: `Month timer`
    *   **Select**: `1st` (Day of month) @ `Midnight`.
4.  Click **Save**.

---

## ⚙️ Step 6: Environment Variables

Create a file named `.env` in the `stem-bot` folder.

**Option A: Paste JSON Content (Easier for Cloud)**
Open your downloaded JSON key file, copy the *entire content*, and verify it is a single line (or handles escaping). However, for local consistency, we often use the file path.

**Recommended .env Format:**

```ini
TELEGRAM_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
SHEET_ID=1aBcD...xYz  # Your Sheet ID
GOOGLE_CREDENTIALS='{ "type": "service_account", ... }' 
# Paste the FULL JSON content inside single quotes using one line if possible.
# Alternatively, if running locally, you can modify database.py to read 'service_account.json'.
SUPERADMIN_IDS=123456789
ADMIN_IDS=987654321
```

> **Tip**: If pasting JSON into `.env` is difficult, rename your downloaded key file to `service_account.json` and place it in the project folder. The bot is configured to look for it if `GOOGLE_CREDENTIALS` is missing.

---

## ▶️ Step 7: Run the Bot

```bash
python bot.py
```

If successful, you will see `Bot is polling...` in the console.

---

## 🌐 Step 8: Deployment (Render.com)

1.  Push your code to **GitHub**.
2.  Log in to [Render](https://render.com).
3.  New **Web Service** (or Background Worker).
4.  Connect your repo.
5.  **Build Command**: `pip install -r requirements.txt`
6.  **Start Command**: `python bot.py`
7.  **Environment Variables**:
    *   Add `TELEGRAM_TOKEN`, `SHEET_ID`, `SUPERADMIN_IDS`, etc.
    *   For `GOOGLE_CREDENTIALS`, paste the content of your JSON key file.

**Done! Your bot is live.** 🚀

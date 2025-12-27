# Security Policy

## Supported Versions

Use the latest version of the bot to ensure you have the latest security patches.

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Configuration Security

To protect your API keys and tokens:

*   **Never commit `.env` files**: We have included `.env` in `.gitignore` by default.
*   **Service Accounts**: Treat your `service_account.json` (Google Credentials) like a password. Do not share it.
*   **Regenerate Keys**: If you suspect a leak, regenerate your Telegram Token via BotFather and your Google Cloud keys immediately.

## Reporting a Vulnerability

We take security seriously. If you discover a vulnerability, please follow these steps:

1.  **Do NOT open a public issue.** Publicly disclosing a vulnerability can put user data at risk.
2.  Email the repository owner directly (or contact via Telegram @zis3c).
3.  Include details about the vulnerability and steps to reproduce.

We will acknowledge your report within 48 hours and work on a fix.

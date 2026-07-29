# Auto Deploy to Tencent

This repository uses GitHub Actions to deploy automatically to a Tencent Lighthouse on every push to `main`.

Workflow file:
- `.github/workflows/deploy-tencent.yml`

## How It Works

1. GitHub Action connects to droplet over SSH.
2. It pulls latest `main` into `/opt/stem-telebot`.
3. It installs dependencies in `.venv`.
4. It restarts `stem-telebot` service with `systemctl`.

## Repository Secrets

Add these in `Settings` -> `Secrets and variables` -> `Actions`:

- `TENCENT_HOST`: server public IP (example `129.226.152.121`)
- `TENCENT_USER`: SSH user (recommended `deploy`)
- `TENCENT_SSH_KEY`: private SSH key for `TENCENT_USER`

## Server Requirements

- App path exists: `/opt/stem-telebot`
- Virtual environment exists: `/opt/stem-telebot/.venv`
- Service exists: `stem-telebot`
- `deploy` can run service commands without password

Use this sudoers rule:

```bash
echo 'deploy ALL=(ALL) NOPASSWD:/usr/bin/systemctl restart stem-telebot,/usr/bin/systemctl is-active stem-telebot,/usr/bin/systemctl is-active --quiet stem-telebot' | sudo tee /etc/sudoers.d/deploy-stem-telebot
sudo chmod 440 /etc/sudoers.d/deploy-stem-telebot
sudo visudo -cf /etc/sudoers.d/deploy-stem-telebot
```

## Install Public Key On Server

Add the public key that matches `TENCENT_SSH_KEY`:

```bash
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
echo "ssh-ed25519 AAAA... your-key-comment" | sudo tee -a /home/deploy/.ssh/authorized_keys
sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys
sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

## Run And Verify

1. Push to `main` or run workflow manually from Actions tab.
2. Verify service:

```bash
sudo systemctl is-active stem-telebot
journalctl -u stem-telebot -n 100 --no-pager
```

## Troubleshooting

- `missing server host`
- `TENCENT_HOST` secret is missing or empty.

- `ssh.ParsePrivateKey: ssh: no key found`
- `TENCENT_SSH_KEY` is not a valid private key block.

- `unable to authenticate, attempted methods [none publickey]`
- Public key is not installed for `TENCENT_USER` on server.

- `sudo: a password is required`
  - Sudoers rule is missing or does not match exact command arguments.

## Security Notes

- Never commit secrets or private keys.
- Use a dedicated deploy key (do not reuse personal keys).
- Rotate deploy key immediately if exposed.
- Restrict sudoers scope to only required `systemctl` commands.

## Template Files In Deployment

Web report templates are deployed together with app code:

- `membership_card_template.py`
- `demographic_stats_template.py`

Ensure these files are committed whenever web report UI changes are made.

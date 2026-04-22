# CROUS Marseille Housing Monitor

Automation tool that monitors CROUS Marseille housing listings and sends notifications when student accommodation appears or disappears.

## Highlights

- Tracks listings over time with a local SQLite store
- Sends Telegram alerts for new listings
- Supports email notifications and Docker-based execution
- Keeps runtime credentials outside git through ignored config files and environment-variable overrides

## Stack

- Python 3
- Requests
- python-telegram-bot
- SQLite
- Docker / Docker Compose

## Configuration

`config.json` is intentionally ignored by git. Start from the example file:

```bash
cp config.example.json config.json
```

Telegram credentials can also be injected with environment variables:

```bash
export TELEGRAM_BOT_TOKEN=your_bot_token_here
export TELEGRAM_CHAT_ID=your_chat_id_here
```

Environment variables override the values stored in `config.json`.

## Local run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json
python3 main_monitor.py --once --config config.json
```

`config.example.json` ships with Telegram notifications disabled so the one-shot smoke test works before you add a bot token.

## Verification

Run a syntax sanity check before pushing changes:

```bash
python3 -m py_compile main_monitor.py enhanced_scraper.py
```

## Docker

Create a local `.env` file if you want Docker to inject credentials:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

Then start the service:

```bash
docker compose up -d
```

## Output

- `crous_housing.db`: local listing history
- `crous_monitor.log`: runtime logs

## Purpose

This repository is kept public as a practical automation project showing monitoring, notification workflows, and safe configuration handling.

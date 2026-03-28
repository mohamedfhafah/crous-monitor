# crous-monitor
CROUS Marseille Housing Monitor - Real-time notifications for student housing

## Configuration

`config.json` is **not tracked** by git (it is listed in `.gitignore`) so that real credentials are never accidentally committed.

Start by copying the example file:

```bash
cp config.example.json config.json
```

Then edit `config.json` with your settings. You can also override Telegram credentials with environment variables (see below) and leave the placeholders in `config.json`.

### Telegram Credentials

Set your Telegram bot token and chat ID via environment variables:

```bash
export TELEGRAM_BOT_TOKEN=your_bot_token_here
export TELEGRAM_CHAT_ID=your_chat_id_here
```

These environment variables take precedence over the values in `config.json`. The `config.json` placeholders (`YOUR_BOT_TOKEN_HERE` / `YOUR_CHAT_ID_HERE`) are only used as fallback defaults.

## Running with Docker

Create a `.env` file (already in `.gitignore`) with your credentials:

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

Then run:

```bash
docker-compose up -d
```

Alternatively, pass the variables inline:

```bash
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy docker-compose up -d
```

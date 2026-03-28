# crous-monitor
CROUS Marseille Housing Monitor - Real-time notifications for student housing

## Configuration

Copy `config.json` and fill in your settings. **Never commit real credentials to the repository.**

### Telegram Credentials

Set your Telegram bot token and chat ID via environment variables:

```bash
export TELEGRAM_BOT_TOKEN=your_bot_token_here
export TELEGRAM_CHAT_ID=your_chat_id_here
```

These environment variables take precedence over the values in `config.json`. The `config.json` placeholders (`YOUR_BOT_TOKEN_HERE` / `YOUR_CHAT_ID_HERE`) are only used as fallback defaults.

## Running with Docker

```bash
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy docker-compose up -d
```

Or create a `.env` file (already in `.gitignore`):

```
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=yyy
```

Then run:

```bash
docker-compose up -d
```

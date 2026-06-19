# Tokyo News Briefing Bot

This repository runs two cloud scheduled news reports and sends them to Telegram.

- Morning report: 08:00 Japan time
- Evening report: 21:30 Japan time

Reports are generated as Markdown and HTML files, then sent to Telegram as attachments.

## Required GitHub Secrets

Add these under Settings -> Secrets and variables -> Actions -> New repository secret:

- OPENAI_API_KEY
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

Your Telegram chat id is 8891139636.

Optional:

- OPENAI_MODEL, default is gpt-4.1-mini

## Schedule

GitHub Actions uses UTC.

- 23:00 UTC = 08:00 JST morning report
- 12:30 UTC = 21:30 JST evening report

## Manual test

Open Actions -> Daily news reports -> Run workflow, then choose morning or evening.

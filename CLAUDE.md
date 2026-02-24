# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram bot ("Фото для резюме") that transforms user selfies into professional studio portrait photos. Users select gender, upload a photo, and receive an AI-generated professional portrait. Written in Russian (UI text and comments).

## Running the Bot

```bash
# Local development
source venv/bin/activate
python -m bot.main

# Production (systemd on Yandex Cloud at 89.169.163.73)
sudo systemctl start|stop|restart|status photoshoot_ai
sudo journalctl -u photoshoot_ai -f          # live logs
sudo journalctl -u photoshoot_ai -n 50       # last 50 lines
```

No test suite, linter, or build step exists. Dependencies: `pip install -r requirements.txt`

## Architecture

**Tech stack:** Python 3.9+, aiogram 3.x, aiohttp, pydantic-settings, openai SDK

**Core flow:**
1. User sends `/start` → sees welcome + gender selection buttons
2. User picks gender → FSM moves to `awaiting_photo` state
3. User sends photo → handler calls OpenRouter (GPT-5.2) to generate a unique prompt, then calls kie.ai API to transform the image (~28s total)
4. Result photo sent back with "Regenerate" and "New photo" buttons

**Key modules:**

| Path | Purpose |
|------|---------|
| `bot/main.py` | Entry point: creates Bot, Dispatcher (MemoryStorage FSM), registers routers, starts polling |
| `bot/config.py` | `Settings` (pydantic BaseSettings from `.env`) + `PROMPT_SYSTEM` / `PROMPT_CRITICAL_SUFFIX` constants |
| `bot/handlers/start.py` | `/start` command, gender selection callback, regenerate callback |
| `bot/handlers/photo.py` | Photo upload handler, orchestrates prompt generation → image transformation → response |
| `bot/services/openai_client.py` | `OpenAIClient` — async prompt generation via OpenRouter (GPT-5.2) |
| `bot/services/kie_client.py` | `KieClient` — async image transformation via kie.ai (google/nano-banana-edit), with polling and exponential backoff |
| `bot/services/user_limits.py` | JSON file-based user limit tracking (3 free generations, admin bypass) |
| `bot/states/generation.py` | `GenerationStates` FSM: `selecting_gender` → `awaiting_photo` → `processing` |
| `bot/keyboards/inline.py` | Inline keyboard builders: gender selection, restart, regenerate buttons |

**Service clients are module-level singletons** (`kie_client = KieClient()`, `openai_client = OpenAIClient()`), imported directly by handlers.

**Data persistence:** JSON file at `/opt/photoshoot_ai/user_generations.json` (production) or project root (local dev). Schema: `{user_id: {generations, last_photo_url, last_gender}}`. Supports legacy format migration (plain int → dict).

## Environment Variables

Configured via `.env` (see `.env.example`):
- `BOT_TOKEN` — Telegram bot token
- `KIE_API_KEY`, `KIE_API_URL` — kie.ai image transformation API
- `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` — OpenRouter for GPT-5.2 access (used instead of OpenAI directly due to Russia restrictions)
- `DEBUG` — enables DEBUG-level logging

## Key Constants

- `MAX_FREE_GENERATIONS = 3` and `ADMIN_ID = 91892537` in `bot/services/user_limits.py`
- Prompt templates (`PROMPT_SYSTEM`, `PROMPT_CRITICAL_SUFFIX`) in `bot/config.py` — these are critical for output quality; changes should be tested carefully

## Deployment

Production runs on Yandex Cloud Ubuntu 22.04 VM as systemd service (`photoshoot_ai.service`), under the `deploy` user at `/opt/photoshoot_ai`. One-time setup via `deploy.sh`. Update process: stop service → SCP files → restart. See `DEPLOY.md` and `SERVER_COMMANDS.md` for details.

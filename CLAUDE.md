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
| `bot/config.py` | `Settings` (pydantic BaseSettings from `.env`) + `CreditPackage` / `CREDIT_PACKAGES` + `PROMPT_SYSTEM` / `PROMPT_CRITICAL_SUFFIX` constants |
| `bot/handlers/start.py` | `/start` command, gender selection callback, regenerate callback |
| `bot/handlers/photo.py` | Photo upload handler, orchestrates prompt generation → image transformation → response |
| `bot/handlers/payment.py` | Payment flow: package selection, YooKassa payment creation, status polling |
| `bot/services/yookassa_client.py` | Async wrapper over YooKassa SDK (payment creation + status check via `run_in_executor`) |
| `bot/services/openai_client.py` | `OpenAIClient` — async prompt generation via OpenRouter (GPT-5.2) |
| `bot/services/kie_client.py` | `KieClient` — async image transformation via kie.ai (google/nano-banana-edit), with polling and exponential backoff |
| `bot/services/user_limits.py` | SQLite-based user limit tracking (1 free generation + paid credits, admin bypass), payment history, `init_db()` called at startup |
| `bot/states/generation.py` | `GenerationStates` FSM: `selecting_gender` → `awaiting_photo` → `processing` |
| `bot/keyboards/inline.py` | Inline keyboard builders: gender selection, restart, regenerate, buy credits, package selection buttons |

**Service clients are module-level singletons** (`kie_client = KieClient()`, `openai_client = OpenAIClient()`), imported directly by handlers.

**Data persistence:** SQLite database at `/opt/photoshoot_ai/user_data.db` (production) or project root (local dev). Tables: `users(user_id, generations, last_photo_url, last_gender, paid_credits)` and `payments(id, user_id, package_id, credits, amount, status, created_at, confirmed_at, payment_provider_id)`. On first run, `init_db()` auto-migrates schema (adds `paid_credits` column, creates `payments` table) and migrates legacy JSON data.

## Environment Variables

Configured via `.env` (see `.env.example`):
- `BOT_TOKEN` — Telegram bot token
- `KIE_API_KEY`, `KIE_API_URL` — kie.ai image transformation API
- `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` — OpenRouter for GPT-5.2 access (used instead of OpenAI directly due to Russia restrictions)
- `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` — YooKassa payment credentials
- `YOOKASSA_RETURN_URL` — deep link back to bot after payment (default: `https://t.me/photoshoot_generator_bot`)
- `DEBUG` — enables DEBUG-level logging

## Key Constants

- `MAX_FREE_GENERATIONS = 1` and `ADMIN_ID = 91892537` in `bot/services/user_limits.py`
- `CREDIT_PACKAGES` in `bot/config.py` — three credit packs: 5/149₽, 15/349₽, 50/899₽ (prices in kopecks for payment API)
- Prompt templates (`PROMPT_SYSTEM`, `PROMPT_CRITICAL_SUFFIX`) in `bot/config.py` — these are critical for output quality; changes should be tested carefully

## Payment System

**Status:** YooKassa integration complete. Live payments enabled.

**Payment flow:**
1. User exhausts free generation → "Buy credits" button appears
2. User selects a credit package → clicks "Pay"
3. Bot creates payment in YooKassa → sends link button to YooKassa payment page
4. User pays on YooKassa → returns to bot via `YOOKASSA_RETURN_URL`
5. Payment confirmed via background polling (every 15s, up to 15 min) or manual "Check payment" button → credits added

**Credit consumption order:** Free generations first, then paid credits. `can_generate()` checks both pools. `increment_generations()` deducts from the correct pool automatically.

**Caveat:** Callback buttons on photo messages cannot use `edit_text()` — only `edit_caption()` or sending a new message. The `show_packages` handler detects this via `callback.message.photo` and sends a new message instead.

## Deployment

Production runs on Yandex Cloud Ubuntu 22.04 VM as systemd service (`photoshoot_ai.service`), under the `deploy` user at `/opt/photoshoot_ai`. One-time setup via `deploy.sh`. Update process: stop service → SCP files → restart. See `DEPLOY.md` and `SERVER_COMMANDS.md` for details.

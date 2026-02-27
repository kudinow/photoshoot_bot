# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram bot ("Фото для резюме") that transforms user selfies into professional studio portrait photos. Users select gender, choose clothing style (business/casual/creative), upload a photo, and receive an AI-generated professional portrait. Written in Russian (UI text and comments).

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
2. User picks gender → sees clothing style selection (business/casual/creative)
3. User picks style → FSM moves to `awaiting_photo` state
4. User sends photo → handler calls OpenRouter (GPT-5.2) to generate a style-aware prompt, then calls kie.ai API to transform the image (~28s total)
5. Result photo sent back with "Regenerate" and "New photo" buttons

**Key modules:**

| Path | Purpose |
|------|---------|
| `bot/main.py` | Entry point: creates Bot, Dispatcher (MemoryStorage FSM), registers routers, starts polling |
| `bot/config.py` | `Settings` (pydantic BaseSettings from `.env`) + `CreditPackage` / `CREDIT_PACKAGES` + style-aware prompts (`PROMPT_BASE` + `STYLE_PROMPTS` dict + `build_system_prompt()`) + `PROMPT_CRITICAL_SUFFIX` |
| `bot/handlers/start.py` | `/start` command, gender selection, style selection, regenerate callbacks |
| `bot/handlers/photo.py` | Photo upload handler, orchestrates prompt generation → image transformation → response |
| `bot/handlers/payment.py` | Payment flow: package selection, YooKassa payment creation, status polling |
| `bot/services/yookassa_client.py` | Async wrapper over YooKassa SDK (payment creation + status check via `run_in_executor`) |
| `bot/services/openai_client.py` | `OpenAIClient` — async prompt generation via OpenRouter (GPT-5.2) |
| `bot/services/kie_client.py` | `KieClient` — async image transformation via kie.ai (google/nano-banana-edit), with polling and exponential backoff |
| `bot/services/user_limits.py` | SQLite-based user limit tracking (1 free generation + paid credits, admin bypass), payment history, referral stats, `init_db()` called at startup |
| `bot/states/generation.py` | `GenerationStates` FSM: `selecting_gender` → `selecting_style` → `awaiting_photo` → `processing` |
| `bot/keyboards/inline.py` | Inline keyboard builders: gender selection, style selection, restart, regenerate, buy credits, package selection buttons |

**Service clients are module-level singletons** (`kie_client = KieClient()`, `openai_client = OpenAIClient()`), imported directly by handlers.

**Data persistence:** SQLite database at `/opt/photoshoot_ai/user_data.db` (production) or project root (local dev). Tables: `users(user_id, generations, last_photo_url, last_gender, last_style, paid_credits, created_at)`, `payments(id, user_id, package_id, credits, amount, status, created_at, confirmed_at, payment_provider_id)`, `referrals(user_id, source, joined_at)`, and `generations_log(id, user_id, created_at, gender, style, is_paid)`. On first run, `init_db()` auto-migrates schema (adds columns, creates tables) and migrates legacy JSON data.

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
- Prompt templates in `bot/config.py`: `PROMPT_BASE` (common studio setup), `STYLE_PROMPTS` dict with 6 style sections (business/casual/creative × male/female), `build_system_prompt(gender, style)` assembles them, `PROMPT_CRITICAL_SUFFIX` (face preservation). Critical for output quality; changes should be tested carefully
- `STYLE_LABELS` in `bot/config.py` — style display names: business→"деловой", casual→"кежуал", creative→"креативный"

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

## Deep Link Tracking

Deep links allow tracking traffic sources via `/start SOURCE` parameter.

**Link format:** `https://t.me/photoshoot_generator_bot?start=SOURCE`

**How it works:**
- On `/start SOURCE`, source is saved to `referrals` table (first occurrence only — `INSERT OR IGNORE`)
- Admin command `/stats` shows breakdown by source

**Admin stats command:** Send `/stats` to the bot to see:
```
📊 Источники трафика:
• vk: 42 чел. (55%)
• instagram: 25 чел. (33%)
• friends: 9 чел. (12%)

Всего: 76
```

**Relevant code:** `save_referral()` and `get_referral_stats()` in `bot/services/user_limits.py`; `/stats` handler in `bot/handlers/start.py`.

## Landing Page

**Domain:** https://ai-photobot.ru (+ www)

**Stack:** Static HTML served by **Caddy** (NOT nginx) on the same Yandex Cloud VM.

**Files on server:** `/var/www/landing/` — `index.html` + `photo/` directory with images.

**Source:** `landing/index.html` is the active landing.

**Deploy landing changes:**
```bash
scp landing/index.html kudinow@89.169.163.73:/var/www/landing/index.html
```
No restart needed — Caddy serves static files, changes are instant.

**Caddy config:** `/etc/caddy/Caddyfile` — auto-HTTPS, gzip, `file_server` from `/var/www/landing`.

## Blog

**URL:** https://ai-photobot.ru/blog/

**Stack:** Static HTML generated from Markdown by a local Python build script. No server-side app — Caddy serves pre-built HTML files.

**Files:**

| Path | Purpose |
|------|---------|
| `blog/posts/*.md` | Markdown source files with YAML frontmatter (title, slug, date, description, published) |
| `blog/build.py` | Build script: parses MD → generates static HTML. Flags: `--deploy` (SCP to server), `--local-deploy` (copy to `/var/www/landing/blog/` on server). Dependencies: `markdown`, `pyyaml` |
| `blog/output/` | Generated HTML (gitignored). Contains `index.html` (listing) + `{slug}/index.html` per article |
| `blog/PROMPT.md` | Reusable prompt for generating SEO articles with ChatGPT/Claude |
| `blog/autogen.py` | Auto-generation script: picks next topic from `topics.json`, generates article via OpenRouter (GPT-5.2), saves markdown, builds HTML, deploys locally |
| `blog/topics.json` | List of 50 SEO topics with `done` flag. Script picks first `done: false` topic |
| `blog/.env` | Blog-specific env (on server only): `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` |

**On server:** `/var/www/landing/blog/` — Caddy serves automatically, no config changes needed.

**Auto-publishing (cron):** Server runs `autogen.py` 3 times daily (08:00, 14:00, 20:00 МСК) via cron under `kudinow`. Each run generates one article, builds all HTML, and copies to `/var/www/landing/blog/`. Logs: `/opt/photoshoot_ai/blog/autogen.log`.

```bash
# Cron entry (on server, UTC times = MSK-3):
0 5,11,17 * * * /opt/photoshoot_ai/venv/bin/python3 /opt/photoshoot_ai/blog/autogen.py >> /opt/photoshoot_ai/blog/autogen.log 2>&1
```

**Manual publishing:**
```bash
# 1. Create/edit .md file in blog/posts/
# 2. Build and deploy:
python3 blog/build.py --deploy
```

**Frontmatter format:**
```yaml
---
title: "Заголовок статьи"
slug: "url-slug"
date: "2026-02-26"
description: "Мета-описание для SEO"
published: true    # set to false for drafts
---
```

**Design:** Blog templates in `build.py` replicate the landing's design system (Inter font, CSS variables, nav, footer, Yandex.Metrika). Listing page has 2-column card grid; article page has narrow 720px readable column with CTA banner at the bottom.

**Blog ownership:** `/opt/photoshoot_ai/blog/` owned by `kudinow` (not `deploy`), since autogen cron runs as `kudinow` and writes to `/var/www/landing/blog/` (also `kudinow`).

## Analytics Dashboard

**URL:** https://ai-photobot.ru/dash/ (password-protected via Caddy basicauth, login: `admin`)

**Stack:** Static HTML + Chart.js, data generated by Python script from SQLite every 30 minutes via cron.

**Files:**

| Path | Purpose |
|------|---------|
| `dash/generate_data.py` | Queries SQLite → generates `/var/www/landing/dash/data.json` |
| `dash/index.html` | Dashboard HTML (Supabase dark theme, Chart.js charts) |

**On server:** `/var/www/landing/dash/` (HTML + data.json), `/opt/photoshoot_ai/dash/` (generate script).

**Data refresh:** Cron every 30 min. Logs: `/opt/photoshoot_ai/dash/generate_data.log`.

**Deploy dashboard changes:**
```bash
scp dash/index.html kudinow@89.169.163.73:/var/www/landing/dash/index.html
```

**Regenerate data manually:**
```bash
ssh kudinow@89.169.163.73 "/opt/photoshoot_ai/venv/bin/python3 /opt/photoshoot_ai/dash/generate_data.py"
```

**DB tables used for analytics:**
- `users.created_at` — user registration timestamp (added for dashboard, backfilled from referrals/payments)
- `generations_log` — logs each generation with timestamp, gender, style, is_paid (for retention and activity charts)

## Deployment (Bot)

Production runs on Yandex Cloud Ubuntu 22.04 VM as systemd service (`photoshoot_ai.service`), under the `deploy` user at `/opt/photoshoot_ai`. One-time setup via `deploy.sh`. Update process: stop service → SCP files → restart. See `DEPLOY.md` and `SERVER_COMMANDS.md` for details.

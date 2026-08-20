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
4. User sends photo → handler calls OpenRouter (GPT-5.2) to generate a style-aware prompt, then calls kie.ai API (`google/nano-banana-edit`) to transform the image
5. Result photo sent back with "Regenerate" and "New photo" buttons
6. **After the user's first successful generation only**, bot sends a rating prompt (1-5 stars). All ratings persist to `ratings` table and notify admin: 5⭐ sends a short text alert and surfaces the referral link to the user; 1-4⭐ forwards both photos + feedback text to admin. One-shot per user, gated by `users.has_rated` flag.
7. For non-admin users, the first-generation result is watermarked (`ai-photobot.ru` diagonal); the clean version is delivered after a dedicated 50₽ `watermark_unlock` payment (0 credits) via the `🔓 Убрать знак — 50 ₽` button.

**Key modules:**

| Path | Purpose |
|------|---------|
| `bot/main.py` | Entry point: creates Bot, Dispatcher (MemoryStorage FSM), registers routers, starts polling |
| `bot/config.py` | `Settings` (pydantic BaseSettings from `.env`) + `CreditPackage` / `CREDIT_PACKAGES` + style-aware prompts (`PROMPT_BASE` + `STYLE_PROMPTS` dict + `build_system_prompt()`) + `PROMPT_CRITICAL_SUFFIX` |
| `bot/handlers/start.py` | `/start` command, gender selection, style selection, regenerate callbacks |
| `bot/handlers/photo.py` | Photo upload handler, orchestrates prompt generation → image transformation → response |
| `bot/handlers/payment.py` | Payment flow: package selection, YooKassa payment creation, status polling. `_deliver_after_payment()` branches on the `watermark_unlock` package → sends the clean photo instead of crediting generations |
| `bot/handlers/rating.py` | Generation rating flow: star-click callbacks, low-rating admin forwarding (two-stage: photos + optional text), 5-star referral link surfacing, non-text catch-all in feedback state |
| `bot/services/watermark.py` | Pillow `apply_watermark()` + `save_clean_copy()` / `get_clean_copy()` for first-generation watermarking |
| `bot/handlers/watermark.py` | `unlock_watermark` callback: idempotent clean-photo delivery if already paid, else starts a 50₽ payment |
| `bot/handlers/broadcast.py` | Admin broadcasting: `/broadcast` segmented mass messages + `/send USER_ID text` for direct per-user messages |
| `bot/handlers/support.py` | In-bot two-way support chat: `/support` + `support_open` entry, `InSupportSession` filter relays user text/photo to admin (uid embedded), admin native-Reply routes back, close from either side |
| `bot/services/yookassa_client.py` | Async wrapper over YooKassa SDK (payment creation + status check via `run_in_executor`) |
| `bot/services/openai_client.py` | `OpenAIClient` — async prompt generation via OpenRouter (GPT-5.2) |
| `bot/services/kie_client.py` | `KieClient` — async image transformation via kie.ai. Prod uses `transform_photo()` (model `google/nano-banana-edit`, image_size `auto`). `transform_photo_gpt_image_2()` (model `gpt-image-2-image-to-image`, aspect_ratio `3:4`, resolution `2K`) is kept in the file as fallback and still used by the admin `/test_gpt` sandbox, but not called from the prod generation handlers. |
| `bot/handlers/admin_test.py` | Admin-only `/test_gpt` flow (gender → style → photo). Always runs GPT Image 2; does not write to `users.generations`, `paid_credits`, `generations_log`, `ratings`. Useful as a no-side-effect sandbox for the admin. |
| `bot/services/user_limits.py` | SQLite-based user limit tracking (1 free generation + paid credits, admin bypass), payment history, deep-link referral stats, user-to-user referral program, rating helpers, `has_unlocked_watermark()` for watermark unlock, `init_db()` called at startup |
| `bot/states/generation.py` | `GenerationStates` FSM: `selecting_gender` → `selecting_style` → `awaiting_photo` → `processing`; plus `awaiting_feedback_text` used by the rating flow |
| `bot/keyboards/inline.py` | Inline keyboard builders: gender/style selection, restart/regenerate, buy credits + package selection, rating stars (numbered `1⭐..5⭐`), feedback skip, five-star referral CTA |

**Service clients are module-level singletons** (`kie_client = KieClient()`, `openai_client = OpenAIClient()`), imported directly by handlers.

**Data persistence:** SQLite database at `/opt/photoshoot_ai/user_data.db` (production) or project root (local dev). Tables:
- `users(user_id, generations, last_photo_url, last_gender, last_style, paid_credits, created_at, last_photo_file_id, last_result_url, has_rated)` — `last_photo_file_id` stores Telegram file_id of the original selfie (needed for admin rating notifications; file_id is permanent, unlike the temporary file URL in `last_photo_url`); `last_result_url` stores the kie.ai result URL from the most recent generation; `has_rated` is a one-shot flag set when the user rates any generation
- `payments(id, user_id, package_id, credits, amount, status, created_at, confirmed_at, payment_provider_id)`
- `referrals(user_id, source, joined_at)` — deep-link traffic source tracking (vk, instagram, ref_<id>, etc.)
- `user_referrals(referred_user_id, referrer_user_id, created_at, rewarded, rewarded_at)` — user-to-user referral relationships
- `generations_log(id, user_id, created_at, gender, style, is_paid)`
- `broadcasts(id, segment, message_text, total_recipients, sent, blocked, failed, started_at, finished_at)`
- `ratings(id, user_id, value, created_at)` — каждая клик-оценка 1-5⭐ (для аналитики и ретроспективного просмотра; пишется одновременно с `users.has_rated=1`)
- `support_sessions(user_id, active, started_at)` — флаг «юзер в активном диалоге с поддержкой» (источник правды для `InSupportSession`; см. раздел In-Bot Support)

On first run, `init_db()` auto-migrates schema (adds columns via idempotent `ALTER TABLE ... ADD COLUMN` wrapped in try/except, creates tables) and migrates legacy JSON data.

## Environment Variables

Configured via `.env` (see `.env.example`):
- `BOT_TOKEN` — Telegram bot token
- `KIE_API_KEY`, `KIE_API_URL` — kie.ai image transformation API
- `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` — OpenRouter for GPT-5.2 access (used instead of OpenAI directly due to Russia restrictions)
- `OPENROUTER_PROXY` — optional proxy for OpenRouter (`http://user:pass@host:port` or `socks5://host:port`; socks5 needs `pip install httpx[socks]`). Empty = direct connection. **Currently required in prod**: Cloudflare returns 403 to the server's Russian IP — see "LLM Prompt Generation & Fallback" below
- `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` — YooKassa payment credentials
- `YOOKASSA_RETURN_URL` — deep link back to bot after payment (default: `https://t.me/photoshoot_generator_bot`)
- `DEBUG` — enables DEBUG-level logging

## Key Constants

- `MAX_FREE_GENERATIONS = 1` and `ADMIN_ID = 91892537` in `bot/services/user_limits.py`
- `CREDIT_PACKAGES` in `bot/config.py` — three credit packs: 5/149₽, 15/349₽, 50/899₽ (prices in kopecks for payment API)
- Prompt templates in `bot/config.py`: `PROMPT_BASE` (common studio setup), `STYLE_PROMPTS` dict with 6 style sections (business/casual/creative × male/female), `build_system_prompt(gender, style)` assembles them, `PROMPT_CRITICAL_SUFFIX` (face preservation). Critical for output quality; changes should be tested carefully
- `STYLE_LABELS` in `bot/config.py` — style display names: business→"деловой", casual→"кежуал", creative→"креативный"

## LLM Prompt Generation & Fallback

Step 1 of every generation is building a style-aware prompt via OpenRouter (GPT-5.2). Since **2026-07-13** OpenRouter's Cloudflare returns `403 {"success": false, "error": "Access denied by security policy."}` to the production IP (89.169.163.73, Yandex Cloud RU) — even to a bare `GET https://openrouter.ai/` with no API key. It's IP/geo blocking, not the key. Symptom before the fix: users saw «Ошибка генерации стиля. Попробуй ещё раз.» (the `except OpenAIClientError` branch in [bot/handlers/photo.py](bot/handlers/photo.py)); the bot never reached kie.ai.

**Two-layer mitigation (deployed 2026-07-31):**

1. **Proxy support** — `OPENROUTER_PROXY` env var. When set, `OpenAIClient` builds an `httpx.AsyncClient(proxy=...)` and hands it to `AsyncOpenAI` ([bot/services/openai_client.py](bot/services/openai_client.py)). Credentials are masked in logs via `_mask_proxy()`. Unset = direct connection.
2. **Local prompt fallback** — [bot/services/prompt_fallback.py](bot/services/prompt_fallback.py)::`build_local_prompt(gender, style)` assembles a prompt locally from randomized vocabulary tables (garments / colors / accessories / lighting / backdrop / camera per `(gender, style)`), matching the "Universal Prompt Template" shape. `generate_prompt()` **no longer raises** after exhausting retries — it logs `Using LOCAL fallback prompt` at WARNING and returns the local prompt + `PROMPT_CRITICAL_SUFFIX`. So generation never dies because the LLM is unreachable.

`OpenAIClientError` is still defined and still caught by handlers, but is not raised on API failure any more.

**Diagnosing:** `sudo journalctl -u photoshoot_ai | grep -E 'Using LOCAL fallback|Access denied by security policy'`. Fallback in use = every generation logs the WARNING. Once a working proxy is set, that WARNING should disappear.

**Tests:** `python3 tests/test_prompt_fallback.py` (self-contained, no pytest needed — `prompt_fallback.py` deliberately imports nothing from `bot.config`, so it runs without `.env`).

**Note on `Settings` annotations:** use `Optional[str]`, not `str | None` — pydantic evaluates field annotations at runtime and local dev runs Python 3.9 (prod is 3.10).

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

## User-to-User Referral Program

Separate from deep-link traffic tracking: each user has a personal invite link and earns credits when invited friends generate their first photo.

**Link format:** `https://t.me/photoshoot_generator_bot?start=ref_<user_id>` (built by `get_referral_link()` in `user_limits.py`).

**Flow:**
1. User clicks "🎁 Пригласить друга" (shown in `get_buy_keyboard` when out of credits, and after a 5-star rating via `get_five_star_keyboard`) → `show_referral_link` callback in `start.py` sends the link and usage info.
2. Friend opens `/start ref_<referrer_id>` → if the friend is a **new** user, `save_user_referral()` records the pair in `user_referrals`.
3. Friend completes their first successful generation → `reward_referrer()` runs in `photo.py` (and symmetrically in `start.py` regenerate branch), adds **+1 paid credit** to the referrer, marks `rewarded=1`, and sends the referrer a notification message.

**Caps and protections:** `MAX_REFERRAL_CREDITS = 5` per referrer (const in `user_limits.py`). Self-referral blocked. Duplicate rewards blocked via `rewarded` flag. Only new users count (prevents existing users from abusing ref links).

**Key functions:** `save_user_referral()`, `reward_referrer()`, `get_referral_credits_earned()`, `get_referral_link()` in `bot/services/user_limits.py`.

**Backlog (not implemented):** referral CTAs after payment, `/invite` command, two-sided bonus (reward the invitee too), removing the `new_user` gate — see git history and implementation plan docs if revisiting.

## Generation Rating

After the user's first successful generation (and only then), the bot asks them to rate the result 1-5 stars. One-shot per user — gated by `users.has_rated`.

**Flow:**
1. `photo.py` (and `start.py` regenerate branch for symmetry) calls `send_rating_request()` after saving the result, if `was_first_generation and not has_user_rated(user_id)`.
2. User sees message "Как тебе результат? Оцени от 1 до 5:" with keyboard `1⭐ 2⭐ 3⭐ 4⭐ 5⭐`.
3. `handle_rating` callback in `rating.py` parses the star number, logs the value, calls `mark_as_rated(user_id)` + `save_rating(user_id, rating)` (race-guard: returns early if already rated), and branches:
   - **5 stars:** sends admin a short text-only notification (`⭐ Новая оценка: 5/5` + user info) via `_notify_admin_five_star`, then edits message to thanks + `get_five_star_keyboard` (single button reusing existing `referral_link` callback).
   - **1-4 stars:** immediately forwards two messages to `ADMIN_ID` (original photo via `last_photo_file_id`, result via `last_result_url`) with caption containing rating/user info/gender/style. Edits user's message to feedback prompt + skip button, transitions FSM to `awaiting_feedback_text`.
4. User writes text feedback → `handle_feedback_text` forwards it as a stage-2 admin message, clears state. User presses Skip → `handle_feedback_skip` clears state, no extra admin message. User sends non-text (photo/sticker) → catch-all handler nudges them to text or Skip without losing state.

**Admin self-exclusion:** if `user_id == ADMIN_ID`, admin notifications are suppressed to avoid self-spam.

**Data:** every rating is persisted to the `ratings` table (`id, user_id, value, created_at`) for retroactive analytics; `users.has_rated` stays as the one-shot gate. Feedback text is ephemeral (Telegram messages to admin only).

**Design docs:** [docs/superpowers/specs/2026-04-05-generation-rating-design.md](docs/superpowers/specs/2026-04-05-generation-rating-design.md) and [docs/superpowers/plans/2026-04-05-generation-rating.md](docs/superpowers/plans/2026-04-05-generation-rating.md).

## First-Generation Watermark + 50₽ Unlock

On every non-admin user's **first successful generation**, the result is watermarked with a diagonal `ai-photobot.ru` pattern. The clean version is saved to disk and delivered after the user pays a dedicated **50₽** (`watermark_unlock`) micro-payment — which grants **0 generation credits**, only the clean photo.

**Scope:**
- Fires only when `was_first_generation and not is_admin(user_id)` in [bot/handlers/photo.py](bot/handlers/photo.py) (computed before `increment_generations`).
- Admin (`ADMIN_ID`) bypassed — always clean, no unlock button.
- Referral-credit generations (#2+) are clean.
- Soft degradation: if `apply_watermark` raises, the user gets the clean photo and NO unlock button.

**Visual:** diagonal white `ai-photobot.ru`, black stroke, alpha ≈ 110, rotated -30°, step ≈ 22% of the diagonal. Rendered by [bot/services/watermark.py](bot/services/watermark.py) (Pillow + DejaVuSans-Bold on Ubuntu / Arial Bold on macOS, default-font fallback).

**Storage:** `/opt/photoshoot_ai/clean/{user_id}.jpg` (prod) or `<project>/clean/{user_id}.jpg` (local). No DB column — file existence is the source of truth. No cleanup cron.

**Unlock flow:**
- Caption on the watermarked photo upsells 50₽; the keyboard's top row is `🔓 Убрать знак — 50 ₽` (callback `unlock_watermark`).
- [bot/handlers/watermark.py](bot/handlers/watermark.py): no clean file → "Чистая версия больше недоступна."; already paid (`has_unlocked_watermark`) → re-send clean photo free (idempotent); else create a 50₽ YooKassa payment + link and start polling.
- The 50₽ unlock is a special `CreditPackage` `watermark_unlock` (credits=0, [bot/config.py](bot/config.py)), **not** in `CREDIT_PACKAGES` (hidden from the buy menu) but resolvable via `get_package_by_id`. It rides the existing payment pipeline; on confirmation [bot/handlers/payment.py](bot/handlers/payment.py)::`_deliver_after_payment` sends the clean photo (caption `🎁 Готово! Вот твоё фото без водяного знака.`) instead of crediting generations. Admin notification says "Снятие водяного знака за 50 ₽".

**Key code:** [bot/services/watermark.py](bot/services/watermark.py) (`apply_watermark`, `save_clean_copy`, `get_clean_copy`), [bot/services/user_limits.py](bot/services/user_limits.py) (`has_unlocked_watermark`), [bot/keyboards/inline.py](bot/keyboards/inline.py) (`has_watermarked` kwarg).

**Not in `start.py` regenerate branch** on purpose: `was_first_generation` there is always `False` for non-admin (photo.py increments before save_last_photo) — a hook would be dead code.

**Design docs:** [docs/superpowers/specs/2026-05-29-watermark-unlock-50r-design.md](docs/superpowers/specs/2026-05-29-watermark-unlock-50r-design.md) and [docs/superpowers/plans/2026-05-29-watermark-unlock-50r.md](docs/superpowers/plans/2026-05-29-watermark-unlock-50r.md).

## In-Bot Support

Two-way support chat inside the bot. Users open support, send text/photos; the admin
receives them in the bot and answers via Telegram's native **Reply** (swipe-reply); either
side can close the dialog.

**Entry points** (all emit callback `support_open`, plus the `/support` command):
- `/support` command (always available)
- `🆘 Поддержка` button in the `/start` welcome (`get_gender_keyboard(with_support=True)`)
- `🆘 Поддержка` row in `get_restart_keyboard()` (shown after every generation **and** on
  generation errors, since the error handlers in [bot/handlers/photo.py](bot/handlers/photo.py) reuse that keyboard)

**Session model:** `support_sessions(user_id, active, started_at)` table is the source of
truth. Helpers `open_support_session` / `close_support_session` / `is_in_support_session`
in [bot/services/user_limits.py](bot/services/user_limits.py). Survives bot restart.

**Routing:** [bot/handlers/support.py](bot/handlers/support.py) is registered **after
`start.router` and before `photo.router`** in [bot/main.py](bot/main.py) (photo has a catch-all
`F.photo`). The `InSupportSession` filter relays an active user's text/photo to `ADMIN_ID`,
embedding `id <code>{uid}</code>` + a `🆘` marker in the notification. The admin's native
Reply is routed back by parsing that uid from `reply_to_message` (regex `id\s+(\d+)`, gated
on the marker) — **no message-mapping table**, robust across restarts. Replies to unmarked
messages are silently ignored. The user gets a one-time ack on their first message per
session (tracked via FSM data key `support_acked`).

**Closing:** admin `✅ Завершить диалог` button (`support_close:{uid}`) or user
`✅ Завершить диалог` button (`support_close_user`). A command (`/...`) sent inside a session
closes it and asks the user to resend the command. Admin (`ADMIN_ID`) cannot open a session.

**Design docs:** [docs/superpowers/specs/2026-05-29-in-bot-support-design.md](docs/superpowers/specs/2026-05-29-in-bot-support-design.md) and [docs/superpowers/plans/2026-05-29-in-bot-support.md](docs/superpowers/plans/2026-05-29-in-bot-support.md).

## Landing Page

**Domain:** https://ai-photobot.ru (apex). `www.ai-photobot.ru` → 301 redirect to apex (configured in Caddyfile).

**Stack:** Static HTML served by **Caddy** (NOT nginx) on the same Yandex Cloud VM.

**Files on server:** `/var/www/landing/` — `index.html`, `robots.txt`, `sitemap.xml`, `yandex_<hash>.html` (Я.Вебмастер verification), `photo/` directory with images, `blog/` (built blog HTML), `dash/` (analytics dashboard).

**Source:** `landing/index.html` is the active landing. Inline `<style>`, no build step.

**SEO infrastructure on the landing** (added 2026-05-15):
- `<link rel="canonical">`, full `og:*` (`og:image` is portrait `hero-after.jpg` — TODO: brandable 1200×630), `twitter:summary_large_image`, `theme-color`.
- Three JSON-LD blocks in `<head>`: `Organization`, `WebApplication` (with 4 Offers — Free/Стандарт/Про/Макс), `FAQPage` (5 Q&A — extended from 4 visible cards). Keep the visible FAQ cards and JSON-LD block in sync manually when editing.
- `landing/robots.txt`: `Allow: /, Disallow: /dash/, Sitemap: ...`.
- `landing/sitemap.xml`: auto-generated by `scripts/gen_sitemap.py` — see Blog section below.

**Deploy landing changes:**
```bash
scp landing/index.html kudinow@89.169.163.73:/var/www/landing/index.html
ssh kudinow@89.169.163.73 "sudo chown kudinow:kudinow /var/www/landing/index.html"
```
No restart needed — Caddy serves static files, changes are instant.

**Caddy config:** `/etc/caddy/Caddyfile` (source-of-truth copy in repo: `infra/Caddyfile`). Provides auto-HTTPS, zstd+gzip compression, `Cache-Control: public, max-age=31536000, immutable` on `*.css|js|png|jpg|jpeg|webp|gif|svg|ico|woff|woff2|ttf`, `Cache-Control: public, max-age=3600` on `/sitemap.xml` and `/robots.txt`, basic-auth on `/dash/*`, www→apex 301 redirect.

**Deploy Caddyfile changes:**
```bash
scp infra/Caddyfile kudinow@89.169.163.73:/tmp/Caddyfile
ssh kudinow@89.169.163.73 "sudo caddy validate --config /tmp/Caddyfile --adapter caddyfile && sudo cp /tmp/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy"
```
**Always** run `caddy validate` before `cp` + `reload` — a bad config can take the whole site down.

## Blog

**URL:** https://ai-photobot.ru/blog/

**Stack:** Static HTML generated from Markdown by a local Python build script. No server-side app — Caddy serves pre-built HTML files.

**Files:**

| Path | Purpose |
|------|---------|
| `blog/posts/*.md` | Markdown source files with YAML frontmatter (title, slug, date, description, published) |
| `blog/build.py` | Build script: parses MD → generates static HTML. Flags: `--deploy` (SCP to server), `--local-deploy` (copy to `/var/www/landing/blog/` on server). Each article template injects `Article` + `BreadcrumbList` JSON-LD, `og:*` + `twitter:summary_large_image` meta, and a "Связанные статьи" block at the bottom (3 deterministic-random related articles, seeded by slug). Blog index injects `Blog` + `BreadcrumbList` JSON-LD. `local_deploy()` also re-runs `scripts/gen_sitemap.py` to write `/var/www/landing/sitemap.xml` — so every cron-published article auto-updates the sitemap. Dependencies: `markdown`, `pyyaml`. |
| `blog/output/` | Generated HTML (gitignored). Contains `index.html` (listing) + `{slug}/index.html` per article |
| `blog/PROMPT.md` | Reusable prompt for generating SEO articles with ChatGPT/Claude |
| `blog/autogen.py` | Auto-generation script: picks next topic from `topics.json`, generates article via OpenRouter (GPT-5.2), saves markdown, builds HTML, deploys locally |
| `blog/topics.json` | List of 50 SEO topics with `done` flag. Script picks first `done: false` topic |
| `blog/.env` | Blog-specific env (on server only): `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` |
| `scripts/gen_sitemap.py` | Sitemap generator. Reads `blog/posts/*.md` (only `published: true`) + landing + blog index. Writes `sitemap.xml` to `--output` path (default `landing/sitemap.xml`; on server invoked with `--output /var/www/landing/sitemap.xml`). Called from `blog/build.py::local_deploy()`. Owned by `kudinow`. |
| `infra/Caddyfile` | Source-of-truth copy of `/etc/caddy/Caddyfile` (server config). Edit here, deploy via `scp + validate + reload` — see Landing section. |
| `docs/seo/` | SEO docs: `SEO_AUDIT_<date>.md` (gap analysis), `INDEXATION_URLS.md` (prioritized queue for manual URL submission to GSC/Я.Вебмастер), `SEO_KEYWORDS.md` (when Phase 2 lands). |

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

## Domain & DNS

**Domain:** `ai-photobot.ru` — registered and DNS managed at **reg.ru** (nameservers: `ns1.reg.ru`, `ns2.reg.ru`).

**Webmaster verification files:** `landing/yandex_7b748dde2c403ea7.html` — deployed to `/var/www/landing/` root. For new verification files, SCP to the same location.

## Deployment (Bot)

Production runs on Yandex Cloud Ubuntu 22.04 VM as systemd service (`photoshoot_ai.service`), under the `deploy` user at `/opt/photoshoot_ai`. One-time setup via `deploy.sh`. Update process: stop service → SCP files → restart. See `DEPLOY.md` and `SERVER_COMMANDS.md` for details.

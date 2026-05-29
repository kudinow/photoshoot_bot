# In-Bot Support — Design Spec

**Date:** 2026-05-29
**Status:** Approved (brainstorming) → ready for implementation plan

## Problem

Users have no in-bot way to reach support. The only existing admin→user channel is the
manual `/send USER_ID текст` command. We want a two-way support chat inside the same bot:
the user opens support, writes (text + screenshots), the admin receives the message in the
bot, and replies via Telegram's native **Reply** (swipe-reply) — the bot routes the reply
back to the originating user. Either side can end the dialog.

## Goals

- User can reach support from four entry points: `/support` command, a button in the
  `/start` menu, a button after a generation, and a button on a generation error.
- Dialog mode: once a user is in a support session, their text + photos route to the admin
  until the session is explicitly closed (by the user or the admin).
- Admin replies with Telegram's native Reply; bot routes the answer back to the right user.
- Both text and photos supported in both directions.
- Admin can end any user's dialog from their side via a "Завершить" button on the notification.
- Survives bot restart (sessions persisted; reply routing does not depend on in-memory state).

## Non-goals

- No ticket history / threading UI. Feedback text/photos are ephemeral Telegram messages.
- No SLA, queueing, or auto-replies.
- No support for video/voice/documents in v1 (text + photo only).
- Admin (`ADMIN_ID`) does not open support sessions for themselves.

## Approach

**DB-backed sessions + a dedicated early router** (`bot/handlers/support.py`).

A small table is the source of truth for "this user is currently in a support dialog". A
new router is registered in `main.py` **after `start.router` and before `photo.router`**
(because `photo.router` has a catch-all `F.photo` handler). A custom filter intercepts the
user's messages while their session is active.

The originating user's `user_id` is embedded in the header/caption of every admin-facing
notification (`id <code>{uid}</code>`). The admin's native Reply is routed back by parsing
that `uid` out of `reply_to_message` — so **no separate message-mapping table is needed**,
and routing keeps working after a restart (old notifications still carry the uid).

### Rejected alternatives

- **FSM-only** (state in MemoryStorage, reply map in memory): lost on restart, awkward to
  close another user's FSM from the admin handler, unbounded in-memory dict.
- **No mode, pure forward + `/send`**: doesn't satisfy "dialog until exit"; the user's
  normal photos wouldn't route into support.

## Components

### 1. Storage & sessions — `bot/services/user_limits.py`

New table, created idempotently in `init_db()`:

```sql
support_sessions(
    user_id    INTEGER PRIMARY KEY,
    active     INTEGER,        -- 1 = open, 0 = closed
    started_at TEXT
)
```

Helpers:
- `open_support_session(user_id)` — upsert `active=1`, set `started_at`.
- `close_support_session(user_id)` — set `active=0`.
- `is_in_support_session(user_id) -> bool` — read `active`.

No message-mapping table; `user_id` is carried in the admin notification text.

### 2. Entry points (user side)

All four entry points run the same logic: `open_support_session(uid)` → clear FSM state
(avoid conflicts with generation/rating) → send the invite message with a
`✅ Завершить диалог` button (callback `support_close_user`).

Invite message:
> 🆘 Опиши проблему одним или несколькими сообщениями — я передам в поддержку. Можно
> приложить скриншот. Когда закончишь — нажми «Завершить».

1. **`/support` command** — always available (handler in `support.py`).
2. **Button in `/start` menu** — `🆘 Поддержка`, own row under the gender buttons,
   callback `support_open`.
3. **Button after a generation** — added to `get_restart_keyboard()`, callback `support_open`.
4. **Button on a generation error** — added where `photo.py` reports a failure/timeout,
   callback `support_open`.

All buttons emit callback `support_open`; one handler in `support.py` handles it.

### 3. User → admin flow

Router `support.py` registered after `start.router`, before `photo.router`.

Custom filter `InSupportSession` (reads `is_in_support_session`) on two handlers:
- `@router.message(InSupportSession(), F.text)`
- `@router.message(InSupportSession(), F.photo)`

For each user message **except commands** (text starting with `/` → close the session and
let the command fall through so `/start`, `/support`, etc. work again):

Sent to `ADMIN_ID`:
- **text:** `send_message(ADMIN_ID, "🆘 <b>Поддержка</b>\nОт {name} (@username, id <code>{uid}</code>):\n\n{text}", reply_markup=close_kb(uid))`
- **photo:** `send_photo(ADMIN_ID, file_id, caption="🆘 ... id <code>{uid}</code> ...\n{caption}", reply_markup=close_kb(uid))`

`uid` in the header/caption is the routing anchor for the admin's Reply. Close button:
`✅ Завершить диалог`, callback `support_close:{uid}`.

User gets a quiet confirmation only on the **first** message of the session
(`✅ Передал в поддержку, скоро отвечу`), no per-message spam afterward.

Admin self-exclusion: `ADMIN_ID` never enters a support session.

### 4. Admin → user flow (native Reply + close)

Two admin handlers in `support.py` (`F.from_user.id == ADMIN_ID` + `F.reply_to_message`,
gated so only replies to support-marked messages match):

- **Reply with text** → parse `id <code>(\d+)</code>` from `reply_to_message.text` or
  `.caption` → `send_message(uid, "💬 <b>Поддержка:</b>\n\n{text}")`. Admin gets
  `✅ Отправлено`. On `TelegramForbiddenError` (user blocked bot) → notify admin.
- **Reply with photo** → same uid parse → `send_photo(uid, file_id, caption=...)`.

If no uid is found in `reply_to_message` (reply to something unrelated) → silently ignore,
so other flows aren't broken.

**Closing:**
- Admin button `✅ Завершить диалог` (`support_close:{uid}`) → `close_support_session(uid)`
  → user: `Диалог с поддержкой завершён. Спасибо! 🙏`; admin notification: `Диалог с {uid} завершён`.
- User button `support_close_user` → `close_support_session(uid)` → user: `Диалог завершён.`;
  admin notification: `Юзер {uid} закрыл диалог`.

### 5. Router registration — `bot/main.py`

Order: `start.router` → **`support.router`** → (rest) → `admin_test.router` → `photo.router`.
Support must precede `photo.router` (catch-all `F.photo`). The `InSupportSession` filter
ensures non-support users' photos fall through to `photo.py`.

## Edge cases

- User sends a command (`/start`, `/support`, anything starting with `/`) while in a session
  → session closed, command runs normally (filter passes `/` through).
- Multiple users in support at once → native Reply on the specific notification routes by the
  embedded uid; no ambiguity.
- Bot restart → sessions persist in the DB; old notifications still parse by uid from text.
- `apply`-style soft failure: admin reply to an unrelated bot message (no uid) is ignored.

## Testing

No test suite/linter in the project (matches existing practice). Manual smoke test after deploy:

1. `/support` → send text → admin receives it with the `id`.
2. Admin Reply with text → reaches the user.
3. Admin Reply with photo → reaches the user.
4. User sends a photo in-session → reaches the admin.
5. "Завершить" button on both admin and user sides closes the session.
6. A command in-session (`/start`) cleanly exits the session.
7. Entry buttons: `/start` menu, after generation, on error.

## Affected files

- `bot/handlers/support.py` (new)
- `bot/services/user_limits.py` (table + helpers)
- `bot/keyboards/inline.py` (support / close buttons)
- `bot/main.py` (router registration order)
- `bot/handlers/start.py` (`/start` menu button)
- `bot/handlers/photo.py` (error-state button)
- `CLAUDE.md` (new "In-Bot Support" section)

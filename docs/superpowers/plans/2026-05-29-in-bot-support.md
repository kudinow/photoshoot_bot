# In-Bot Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a two-way in-bot support chat — users open support and send text/photos, the admin receives them in the bot and answers via Telegram's native Reply; either side can close the dialog.

**Architecture:** A SQLite table `support_sessions` is the source of truth for "user is in a support dialog". A new router `bot/handlers/support.py` is registered after `start.router` and before `photo.router`. A custom filter `InSupportSession` intercepts an active user's text/photo and relays it to the admin, embedding the user's id in the notification text. The admin's native Reply is routed back by parsing that id from `reply_to_message` — no message-mapping table, robust across restarts.

**Tech Stack:** Python 3.9+, aiogram 3.x, SQLite (stdlib `sqlite3`).

**Note on testing:** This project has **no test suite, linter, or build step** (see CLAUDE.md). Following established practice, verification steps are manual runtime checks — import smoke tests via `python -c` and a live bot smoke test at the end. Do **not** introduce pytest.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `bot/services/user_limits.py` | New `support_sessions` table in `init_db()` + helpers `open_support_session`, `close_support_session`, `is_in_support_session` |
| `bot/keyboards/inline.py` | `get_support_invite_keyboard()` (user-side close), `get_support_admin_keyboard(uid)` (admin-side close); add support button to `get_gender_keyboard` and `get_restart_keyboard` |
| `bot/handlers/support.py` | **New router.** `/support` + `support_open` callback (entry), `InSupportSession` filter, user→admin relay (text/photo), admin Reply→user relay (text/photo), close handlers |
| `bot/main.py` | Register `support.router` after `start.router`, before `photo.router` |
| `bot/handlers/start.py` | Show support button in `/start` welcome keyboard |
| `bot/handlers/photo.py` | Support button on error keyboards (covered automatically via `get_restart_keyboard` default) |
| `CLAUDE.md` | New "In-Bot Support" section |

---

## Task 1: Session storage & helpers

**Files:**
- Modify: `bot/services/user_limits.py` (add table in `init_db()` after the `broadcasts` table block, ~line 215; add helpers after `is_admin`, ~line 289)

- [ ] **Step 1: Add the `support_sessions` table to `init_db()`**

In `bot/services/user_limits.py`, immediately after the `broadcasts` table `conn.execute("""...""")` block (the one ending around line 215, before the `# Миграция из JSON` comment), add:

```python
        # Таблица сессий поддержки (юзер в активном диалоге с саппортом)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS support_sessions (
                user_id INTEGER PRIMARY KEY,
                active INTEGER NOT NULL DEFAULT 0,
                started_at TEXT
            )
        """)
```

- [ ] **Step 2: Add session helpers**

In `bot/services/user_limits.py`, after the `is_admin` function (around line 289), add:

```python
def open_support_session(user_id: int) -> None:
    """Открывает (или переоткрывает) сессию поддержки для пользователя"""
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO support_sessions (user_id, active, started_at)
               VALUES (?, 1, datetime('now'))
               ON CONFLICT(user_id) DO UPDATE SET
                   active = 1, started_at = datetime('now')""",
            (user_id,),
        )


def close_support_session(user_id: int) -> None:
    """Закрывает сессию поддержки для пользователя"""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE support_sessions SET active = 0 WHERE user_id = ?",
            (user_id,),
        )


def is_in_support_session(user_id: int) -> bool:
    """Проверяет, находится ли пользователь в активной сессии поддержки"""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT active FROM support_sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return bool(row and row[0])
```

- [ ] **Step 3: Verify table creation + helpers work (manual)**

Run:
```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && python -c "
from bot.services import user_limits as u
u.init_db()
u.open_support_session(123)
assert u.is_in_support_session(123) is True
u.close_support_session(123)
assert u.is_in_support_session(123) is False
assert u.is_in_support_session(999) is False
print('OK')
"
```
Expected: prints `OK` with no traceback. (Creates/uses `user_data.db` in project root for local dev.)

- [ ] **Step 4: Commit**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai"
git add bot/services/user_limits.py
git commit -m "Add support_sessions table + open/close/is_in helpers"
```

---

## Task 2: Keyboards

**Files:**
- Modify: `bot/keyboards/inline.py`

- [ ] **Step 1: Add the two support keyboards**

In `bot/keyboards/inline.py`, append at the end of the file:

```python
def get_support_invite_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура приглашения в саппорт (кнопка завершения для юзера)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Завершить диалог",
                callback_data="support_close_user",
            )]
        ]
    )


def get_support_admin_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура под уведомлением саппорта у админа (завершить диалог с юзером)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Завершить диалог",
                callback_data=f"support_close:{user_id}",
            )]
        ]
    )
```

- [ ] **Step 2: Add support button to the `/start` welcome keyboard**

In `bot/keyboards/inline.py`, replace the entire `get_gender_keyboard` function with:

```python
def get_gender_keyboard(with_support: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура выбора пола (опционально с кнопкой поддержки)"""
    rows = [
        [
            InlineKeyboardButton(text="👨 Мужской", callback_data="gender:male"),
            InlineKeyboardButton(text="👩 Женский", callback_data="gender:female"),
        ]
    ]
    if with_support:
        rows.append([
            InlineKeyboardButton(text="🆘 Поддержка", callback_data="support_open"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 3: Add support button to `get_restart_keyboard` (after-generation + error contexts)**

In `bot/keyboards/inline.py`, in `get_restart_keyboard`, replace the final block:

```python
    if not has_credits:
        buttons.append([
            InlineKeyboardButton(text="💳 Купить генерации", callback_data="buy_credits"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

with:

```python
    if not has_credits:
        buttons.append([
            InlineKeyboardButton(text="💳 Купить генерации", callback_data="buy_credits"),
        ])

    buttons.append([
        InlineKeyboardButton(text="🆘 Поддержка", callback_data="support_open"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

- [ ] **Step 4: Verify keyboards import and build (manual)**

Run:
```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && python -c "
from bot.keyboards.inline import (
    get_support_invite_keyboard, get_support_admin_keyboard,
    get_gender_keyboard, get_restart_keyboard,
)
assert get_support_admin_keyboard(123).inline_keyboard[0][0].callback_data == 'support_close:123'
assert get_gender_keyboard(with_support=True).inline_keyboard[1][0].callback_data == 'support_open'
assert any(b.callback_data == 'support_open' for row in get_restart_keyboard().inline_keyboard for b in row)
print('OK')
"
```
Expected: prints `OK`.

- [ ] **Step 5: Commit**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai"
git add bot/keyboards/inline.py
git commit -m "Add support keyboards + support button on gender/restart keyboards"
```

---

## Task 3: Support router — entry, relay, close

**Files:**
- Create: `bot/handlers/support.py`

**Handler ordering matters within the router.** aiogram checks handlers in definition order. `support_command_passthrough` (`F.text.startswith("/")`) MUST be defined before `support_user_text` (`F.text`), otherwise a `/command` inside a session would be relayed as a support message instead of closing the session. The admin-reply handlers come after the user-relay handlers; the admin is never in a session, so `InSupportSession` returns `False` for them and they fall through to the admin handlers.

- [ ] **Step 1: Create `bot/handlers/support.py` with the full content below**

```python
"""Хендлеры внутрибот-поддержки (двусторонний диалог юзер ↔ админ).

Сессия хранится в БД (support_sessions). user_id зашит в текст/подпись
уведомления админу с маркером 🆘 — нативный Reply админа роутится обратно
парсингом id из reply_to_message. Маппинг-таблицы нет, переживает рестарт.
"""

from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command
from aiogram.filters.base import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import (
    get_support_admin_keyboard,
    get_support_invite_keyboard,
)
from bot.services.user_limits import (
    ADMIN_ID,
    close_support_session,
    is_admin,
    is_in_support_session,
    open_support_session,
)

logger = logging.getLogger(__name__)
router = Router()

# Маркер + якорь user_id в уведомлениях админу (для роутинга Reply)
_SUPPORT_MARKER = "🆘"
_UID_RE = re.compile(r"id\s+(\d+)")

_INVITE_TEXT = (
    "🆘 Опиши проблему одним или несколькими сообщениями — я передам в "
    "поддержку. Можно приложить скриншот.\n\n"
    "Когда закончишь — нажми «Завершить»."
)
_FIRST_ACK = "✅ Передал в поддержку, скоро отвечу."
_ACK_KEY = "support_acked"


class InSupportSession(Filter):
    """Пропускает сообщение, только если юзер в активной сессии поддержки."""

    async def __call__(self, message: Message) -> bool:
        if message.from_user is None:
            return False
        return is_in_support_session(message.from_user.id)


def _user_label(message: Message) -> str:
    user = message.from_user
    name = user.full_name or ""
    username = f" (@{user.username})" if user.username else ""
    return f"{name}{username}".strip()


async def _acked(state: FSMContext) -> bool:
    data = await state.get_data()
    return bool(data.get(_ACK_KEY))


async def _set_acked(state: FSMContext, value: bool) -> None:
    await state.update_data(**{_ACK_KEY: value})


def _extract_uid(reply: Message | None) -> int | None:
    """Достаёт user_id из reply_to_message, только если это саппорт-уведомление."""
    if reply is None:
        return None
    body = reply.text or reply.caption or ""
    if _SUPPORT_MARKER not in body:
        return None
    m = _UID_RE.search(body)
    return int(m.group(1)) if m else None


# --- Вход в саппорт ---


async def _enter_support(message: Message, state: FSMContext, user_id: int) -> None:
    """Открывает сессию и показывает приглашение."""
    if is_admin(user_id):
        await message.answer("Ты админ — поддержка тебе не нужна 🙂")
        return
    await state.clear()
    open_support_session(user_id)
    await _set_acked(state, False)
    await message.answer(_INVITE_TEXT, reply_markup=get_support_invite_keyboard())


@router.message(Command("support"))
async def cmd_support(message: Message, state: FSMContext) -> None:
    await _enter_support(message, state, message.from_user.id)


@router.callback_query(F.data == "support_open")
async def open_support(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _enter_support(callback.message, state, callback.from_user.id)


# --- Юзер → админ (только в активной сессии) ---
# ВАЖНО: passthrough определён ДО support_user_text (порядок проверки хендлеров).


@router.message(InSupportSession(), F.text.startswith("/"))
async def support_command_passthrough(message: Message, state: FSMContext) -> None:
    """Команда внутри сессии → закрываем сессию и просим повторить команду."""
    close_support_session(message.from_user.id)
    await _set_acked(state, False)
    await message.answer(
        "Диалог с поддержкой завершён. Отправь команду ещё раз, чтобы продолжить."
    )


@router.message(InSupportSession(), F.text)
async def support_user_text(message: Message, bot: Bot, state: FSMContext) -> None:
    uid = message.from_user.id
    first = not await _acked(state)
    await bot.send_message(
        ADMIN_ID,
        f"{_SUPPORT_MARKER} <b>Поддержка</b>\n"
        f"От {_user_label(message)}, id <code>{uid}</code>:\n\n"
        f"{message.text}",
        reply_markup=get_support_admin_keyboard(uid),
    )
    if first:
        await _set_acked(state, True)
        await message.answer(_FIRST_ACK)


@router.message(InSupportSession(), F.photo)
async def support_user_photo(message: Message, bot: Bot, state: FSMContext) -> None:
    uid = message.from_user.id
    first = not await _acked(state)
    caption = message.caption or ""
    await bot.send_photo(
        ADMIN_ID,
        message.photo[-1].file_id,
        caption=(
            f"{_SUPPORT_MARKER} <b>Поддержка</b>\n"
            f"От {_user_label(message)}, id <code>{uid}</code>:\n\n{caption}"
        ),
        reply_markup=get_support_admin_keyboard(uid),
    )
    if first:
        await _set_acked(state, True)
        await message.answer(_FIRST_ACK)


# --- Админ → юзер (нативный Reply на уведомление саппорта) ---


@router.message(F.from_user.id == ADMIN_ID, F.reply_to_message, F.text)
async def admin_reply_text(message: Message, bot: Bot) -> None:
    uid = _extract_uid(message.reply_to_message)
    if uid is None:
        return  # не саппорт-реплай — не трогаем
    if message.text.startswith("/"):
        return  # команды не пересылаем
    try:
        await bot.send_message(uid, f"💬 <b>Поддержка:</b>\n\n{message.text}")
        await message.answer("✅ Отправлено.")
    except TelegramForbiddenError:
        await message.answer(f"Пользователь {uid} заблокировал бота.")
    except Exception as e:
        await message.answer(f"Не удалось отправить: {e}")


@router.message(F.from_user.id == ADMIN_ID, F.reply_to_message, F.photo)
async def admin_reply_photo(message: Message, bot: Bot) -> None:
    uid = _extract_uid(message.reply_to_message)
    if uid is None:
        return
    caption = message.caption or ""
    try:
        await bot.send_photo(
            uid,
            message.photo[-1].file_id,
            caption=f"💬 <b>Поддержка:</b>\n\n{caption}" if caption else "💬 Поддержка",
        )
        await message.answer("✅ Отправлено.")
    except TelegramForbiddenError:
        await message.answer(f"Пользователь {uid} заблокировал бота.")
    except Exception as e:
        await message.answer(f"Не удалось отправить: {e}")


# --- Закрытие диалога ---


@router.callback_query(F.data == "support_close_user")
async def close_by_user(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    uid = callback.from_user.id
    close_support_session(uid)
    await callback.message.answer("Диалог завершён.")
    if not is_admin(uid):
        try:
            await bot.send_message(ADMIN_ID, f"Юзер {uid} закрыл диалог поддержки.")
        except Exception:
            pass


@router.callback_query(F.data.startswith("support_close:"))
async def close_by_admin(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    try:
        uid = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        return
    close_support_session(uid)
    try:
        await bot.send_message(uid, "Диалог с поддержкой завершён. Спасибо! 🙏")
    except Exception:
        pass
    await callback.message.answer(f"Диалог с {uid} завершён.")
```

- [ ] **Step 2: Verify the module imports cleanly + uid parsing (manual)**

Run:
```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && python -c "
import bot.handlers.support as s
assert s.router is not None
assert s._extract_uid(None) is None
class M:  # fake support reply
    text = '🆘 Поддержка\nОт X, id 4567:\n\nhi'
    caption = None
assert s._extract_uid(M()) == 4567
class M2:  # unrelated reply, no marker
    text = 'some message id 99'
    caption = None
assert s._extract_uid(M2()) is None
print('OK')
"
```
Expected: prints `OK`. (Confirms uid parsing triggers only on marked messages.)

- [ ] **Step 3: Commit**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai"
git add bot/handlers/support.py
git commit -m "Add support router: entry, user<->admin relay, close handlers"
```

---

## Task 4: Register router + wire entry points

**Files:**
- Modify: `bot/main.py:11` (import) and `bot/main.py:43-50` (registration)
- Modify: `bot/handlers/start.py:105-107` (welcome keyboard)

- [ ] **Step 1: Import the support router in `main.py`**

In `bot/main.py`, change line 11 from:

```python
from bot.handlers import admin_test, broadcast, payment, photo, rating, start, watermark
```

to:

```python
from bot.handlers import (
    admin_test, broadcast, payment, photo, rating, start, support, watermark,
)
```

- [ ] **Step 2: Register `support.router` after `start.router`, before `photo.router`**

In `bot/main.py`, change:

```python
    # Регистрируем роутеры
    dp.include_router(start.router)
    dp.include_router(broadcast.router)
```

to:

```python
    # Регистрируем роутеры
    dp.include_router(start.router)
    # support ДО photo: InSupportSession перехватывает текст/фото активной сессии
    dp.include_router(support.router)
    dp.include_router(broadcast.router)
```

(The existing `admin_test` and `photo` registrations stay last, unchanged.)

- [ ] **Step 3: Show the support button in the `/start` welcome**

In `bot/handlers/start.py`, change the welcome `message.answer` call (around line 105-107) from:

```python
    await message.answer(
        welcome_text, reply_markup=get_gender_keyboard()
    )
```

to:

```python
    await message.answer(
        welcome_text, reply_markup=get_gender_keyboard(with_support=True)
    )
```

- [ ] **Step 4: Verify imports and registration order (manual)**

Run:
```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && python -c "
src = open('bot/main.py').read()
assert 'support.router' in src
assert src.index('support.router') < src.index('dp.include_router(photo.router)')
import bot.handlers.start  # import smoke
import bot.main  # import smoke (does not start polling)
print('OK')
"
```
Expected: prints `OK`.

- [ ] **Step 5: Commit**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai"
git add bot/main.py bot/handlers/start.py
git commit -m "Register support router (before photo) + add support button to /start"
```

---

## Task 5: Documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add an "In-Bot Support" section to CLAUDE.md**

In `CLAUDE.md`, after the "First-Generation Watermark + 50₽ Unlock" section (before "## Landing Page"), insert:

```markdown
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
messages are ignored. The user gets a one-time ack on their first message per session
(tracked via FSM data key `support_acked`).

**Closing:** admin `✅ Завершить диалог` button (`support_close:{uid}`) or user
`✅ Завершить диалог` button (`support_close_user`). A command (`/...`) sent inside a session
closes it and asks the user to resend the command. Admin (`ADMIN_ID`) cannot open a session.

**Design docs:** [docs/superpowers/specs/2026-05-29-in-bot-support-design.md](docs/superpowers/specs/2026-05-29-in-bot-support-design.md) and [docs/superpowers/plans/2026-05-29-in-bot-support.md](docs/superpowers/plans/2026-05-29-in-bot-support.md).
```

Also: add a `bot/handlers/support.py` row to the **Key modules** table, and add `support_sessions` to the **Data persistence** tables list in CLAUDE.md.

- [ ] **Step 2: Commit**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai"
git add CLAUDE.md
git commit -m "Document in-bot support feature in CLAUDE.md"
```

---

## Task 6: Live smoke test (manual, after local run or deploy)

**Files:** none (verification only)

- [ ] **Step 1: Start the bot locally**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && python -m bot.main
```
Expected: logs `Bot started successfully!` with no traceback. Leave running.

- [ ] **Step 2: Run the smoke checklist in Telegram** (non-admin account = "user", admin account = "admin")

1. Send `/support` (as user) → bot shows the invite + «Завершить» button.
2. Send text → admin receives `🆘 Поддержка ... id <uid>`; user gets the one-time ack.
3. Send a second text → admin receives it; user gets **no** second ack.
4. Admin: Reply (swipe) to the notification with text → user receives `💬 Поддержка: ...`.
5. Admin: Reply with a photo → user receives the photo.
6. User: send a photo in-session → admin receives it with the `id`.
7. Admin: press `✅ Завершить диалог` → user gets "завершён", admin sees confirmation. Verify a follow-up user text is **no longer** relayed.
8. Re-open via `/start` → press `🆘 Поддержка` button → repeat 2. Press user-side «Завершить» → admin gets "Юзер … закрыл диалог".
9. In-session, send `/start` → session closes with the "resend command" hint; sending `/start` again shows the normal welcome.
10. Inspect a generation result / error keyboard → confirm `🆘 Поддержка` button is present.

- [ ] **Step 3: Stop the bot** (Ctrl+C). No commit — verification only.

---

## Deployment note

After local verification, deploy per the **Bot Deployment (CRITICAL)** ritual in project memory:
stop service → SCP each changed file individually to `/tmp` → `sudo cp` to `/opt/photoshoot_ai/` + fix ownership → **verify** new code is present (grep) → start service → check logs. Changed files: `bot/services/user_limits.py`, `bot/keyboards/inline.py`, `bot/handlers/support.py` (new), `bot/main.py`, `bot/handlers/start.py`. The `support_sessions` table is created automatically by `init_db()` on startup.

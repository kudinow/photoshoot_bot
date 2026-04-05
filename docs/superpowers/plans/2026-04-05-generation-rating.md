# Generation Rating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a user's first successful generation, ask them to rate the result 1–5 stars; forward low ratings with both photos to admin, and offer a referral link on 5-star ratings.

**Architecture:** New `bot/handlers/rating.py` router handles all rating flow. Existing `users` table gets three new columns (`last_photo_file_id`, `last_result_url`, `has_rated`). Admin notifications are sent in two stages: rating + both photos immediately upon star click, feedback text later (if provided) to tolerate FSM loss. The 5-star branch reuses the existing `referral_link` callback handler to surface the referral link without writing new referral code.

**Tech Stack:** Python 3.9+, aiogram 3.x, sqlite3 (stdlib), existing `bot/services/user_limits.py` helpers.

**Design spec:** [docs/superpowers/specs/2026-04-05-generation-rating-design.md](../specs/2026-04-05-generation-rating-design.md)

**Note on tests:** This project has no test suite, linter, or build step (confirmed in CLAUDE.md). TDD is not applicable. Verification is done via manual smoke tests after each task and a final end-to-end checklist at the end of the plan. Commits happen at the end of each task.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `bot/services/user_limits.py` | Modify | Add 3 columns + migrations, extend `save_last_photo`, add `mark_as_rated`, `has_user_rated`, `get_last_generation_context` |
| `bot/states/generation.py` | Modify | Add `awaiting_feedback_text` state |
| `bot/keyboards/inline.py` | Modify | Add `get_rating_keyboard`, `get_feedback_skip_keyboard`, `get_five_star_keyboard` |
| `bot/handlers/rating.py` | Create | Rating flow router: star callbacks, feedback text handler, skip handler, admin forwarding |
| `bot/handlers/photo.py` | Modify | Pass `photo_file_id` and `result_url` to `save_last_photo`; call `send_rating_request` after first successful generation |
| `bot/handlers/start.py` | Modify | Same rating trigger in regenerate branch (symmetry per spec — currently unreachable in practice, but matches existing pattern) |
| `bot/main.py` | Modify | Register new `rating.router` |

---

## Task 1: DB migrations — three new columns in `users`

**Files:**
- Modify: `bot/services/user_limits.py` (function `init_db()`, around line 75–130 where other ALTER TABLE migrations live)

- [ ] **Step 1: Add three migration blocks in `init_db()`**

Open `bot/services/user_limits.py`. Find the block around line 68–75 that does the `last_style` migration:

```python
        # Миграция: добавляем колонку last_style
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN last_style TEXT"
            )
            logger.info("Added last_style column to users table")
        except sqlite3.OperationalError:
            pass  # Колонка уже существует
```

Immediately after it (before the `payments` table CREATE), add:

```python
        # Миграция: добавляем колонку last_photo_file_id (для отправки админу оригинала фото)
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN last_photo_file_id TEXT"
            )
            logger.info("Added last_photo_file_id column to users table")
        except sqlite3.OperationalError:
            pass  # Колонка уже существует

        # Миграция: добавляем колонку last_result_url (URL результата из kie.ai для отправки админу)
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN last_result_url TEXT"
            )
            logger.info("Added last_result_url column to users table")
        except sqlite3.OperationalError:
            pass  # Колонка уже существует

        # Миграция: добавляем колонку has_rated (флаг "юзер уже оценивал генерацию")
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN has_rated INTEGER NOT NULL DEFAULT 0"
            )
            logger.info("Added has_rated column to users table")
        except sqlite3.OperationalError:
            pass  # Колонка уже существует
```

- [ ] **Step 2: Manual verification — run bot locally and check schema**

Delete local test DB if present (to force re-init from existing schema), or just run against the current DB (ALTER is idempotent via the try/except):

```bash
source venv/bin/activate
python -c "from bot.services.user_limits import init_db; init_db()"
```

Expected: no errors. Log lines `Added last_photo_file_id column to users table`, `Added last_result_url column to users table`, `Added has_rated column to users table` appear on first run; silent on re-run.

Verify schema:

```bash
python -c "
import sqlite3
conn = sqlite3.connect('user_data.db')
print([r for r in conn.execute('PRAGMA table_info(users)').fetchall()])
"
```

Expected: the output includes rows for `last_photo_file_id`, `last_result_url`, and `has_rated`.

- [ ] **Step 3: Commit**

```bash
git add bot/services/user_limits.py
git commit -m "Add DB columns for rating feature: photo file_id, result URL, has_rated flag"
```

---

## Task 2: Extend `save_last_photo` and add rating helpers

**Files:**
- Modify: `bot/services/user_limits.py` (function `save_last_photo` around line 361, add new functions after `get_last_photo`)

- [ ] **Step 1: Extend `save_last_photo` signature**

Find the existing function (around line 361):

```python
def save_last_photo(
    user_id: int, photo_url: str, gender: str, style: str = "casual"
) -> None:
    """Сохраняет последнюю фотографию пользователя"""
    with _get_conn() as conn:
        _ensure_user(conn, user_id)
        conn.execute(
            "UPDATE users SET last_photo_url = ?, last_gender = ?, "
            "last_style = ? WHERE user_id = ?",
            (photo_url, gender, style, user_id),
        )
    logger.info(f"Saved last photo for user {user_id}")
```

Replace with:

```python
def save_last_photo(
    user_id: int,
    photo_url: str,
    gender: str,
    style: str = "casual",
    photo_file_id: str | None = None,
    result_url: str | None = None,
) -> None:
    """Сохраняет последнюю фотографию пользователя (URL, file_id, результат)."""
    with _get_conn() as conn:
        _ensure_user(conn, user_id)
        conn.execute(
            "UPDATE users SET last_photo_url = ?, last_gender = ?, "
            "last_style = ?, last_photo_file_id = ?, last_result_url = ? "
            "WHERE user_id = ?",
            (photo_url, gender, style, photo_file_id, result_url, user_id),
        )
    logger.info(f"Saved last photo for user {user_id}")
```

Rationale for making the new params keyword-only with defaults: existing callsites in `start.py`'s regenerate path don't have `photo_file_id` / `result_url` (regenerate reuses prior photo), so they stay compatible without edits.

- [ ] **Step 2: Add three new helper functions**

After `get_last_photo` (around line 387), add:

```python
def mark_as_rated(user_id: int) -> None:
    """Помечает пользователя как уже оценившего генерацию (один раз в жизни)."""
    with _get_conn() as conn:
        _ensure_user(conn, user_id)
        conn.execute(
            "UPDATE users SET has_rated = 1 WHERE user_id = ?",
            (user_id,),
        )
    logger.info(f"User {user_id} marked as rated")


def has_user_rated(user_id: int) -> bool:
    """Возвращает True, если пользователь уже оценивал генерацию."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT has_rated FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return bool(row and row[0])


def get_last_generation_context(
    user_id: int,
) -> dict | None:
    """Возвращает контекст последней генерации для отправки админу.

    Returns dict with keys: photo_file_id, result_url, gender, style.
    Returns None if user not found or no generation data.
    """
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT last_photo_file_id, last_result_url, last_gender, last_style "
            "FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "photo_file_id": row[0],
        "result_url": row[1],
        "gender": row[2],
        "style": row[3],
    }
```

- [ ] **Step 3: Manual verification — syntax + smoke test**

```bash
python -c "
from bot.services.user_limits import init_db, save_last_photo, mark_as_rated, has_user_rated, get_last_generation_context
init_db()
# Test flow
save_last_photo(999999999, 'http://example.com/photo.jpg', 'male', 'business', photo_file_id='AgACAg_test', result_url='http://example.com/result.jpg')
print('has_rated before:', has_user_rated(999999999))
print('context:', get_last_generation_context(999999999))
mark_as_rated(999999999)
print('has_rated after:', has_user_rated(999999999))
# Cleanup
import sqlite3
sqlite3.connect('user_data.db').execute('DELETE FROM users WHERE user_id = 999999999').connection.commit()
"
```

Expected output:
```
has_rated before: False
context: {'photo_file_id': 'AgACAg_test', 'result_url': 'http://example.com/result.jpg', 'gender': 'male', 'style': 'business'}
has_rated after: True
```

- [ ] **Step 4: Commit**

```bash
git add bot/services/user_limits.py
git commit -m "Add rating helpers: mark_as_rated, has_user_rated, get_last_generation_context"
```

---

## Task 3: Add `awaiting_feedback_text` FSM state

**Files:**
- Modify: `bot/states/generation.py`

- [ ] **Step 1: Add new state**

Current content:

```python
from aiogram.fsm.state import State, StatesGroup


class GenerationStates(StatesGroup):
    """Состояния для процесса генерации фото"""

    selecting_gender = State()  # Выбор пола для промпта
    selecting_style = State()   # Выбор стиля одежды
    awaiting_photo = State()    # Ждём фото от пользователя
    processing = State()        # Обрабатываем через API
```

Replace with:

```python
from aiogram.fsm.state import State, StatesGroup


class GenerationStates(StatesGroup):
    """Состояния для процесса генерации фото"""

    selecting_gender = State()  # Выбор пола для промпта
    selecting_style = State()   # Выбор стиля одежды
    awaiting_photo = State()    # Ждём фото от пользователя
    processing = State()        # Обрабатываем через API
    awaiting_feedback_text = State()  # Ждём текст фидбека после низкой оценки
```

- [ ] **Step 2: Commit**

```bash
git add bot/states/generation.py
git commit -m "Add awaiting_feedback_text FSM state for rating flow"
```

---

## Task 4: Add rating keyboards

**Files:**
- Modify: `bot/keyboards/inline.py`

- [ ] **Step 1: Add three new keyboard builders**

Append at the end of `bot/keyboards/inline.py` (after `get_broadcast_confirm_keyboard`):

```python
def get_rating_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура оценки генерации (5 звёзд в один ряд)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐", callback_data="rate:1"),
                InlineKeyboardButton(text="⭐", callback_data="rate:2"),
                InlineKeyboardButton(text="⭐", callback_data="rate:3"),
                InlineKeyboardButton(text="⭐", callback_data="rate:4"),
                InlineKeyboardButton(text="⭐", callback_data="rate:5"),
            ]
        ]
    )


def get_feedback_skip_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой 'Пропустить' для пропуска текстового фидбека"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Пропустить",
                    callback_data="feedback_skip",
                )
            ]
        ]
    )


def get_five_star_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после оценки 5 звёзд — предложение поделиться реферальной ссылкой.

    Переиспользует существующий callback 'referral_link' (см. bot/handlers/start.py).
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎁 Получить реферальную ссылку",
                    callback_data="referral_link",
                )
            ]
        ]
    )
```

- [ ] **Step 2: Syntax check**

```bash
python -c "from bot.keyboards.inline import get_rating_keyboard, get_feedback_skip_keyboard, get_five_star_keyboard; print(get_rating_keyboard()); print(get_feedback_skip_keyboard()); print(get_five_star_keyboard())"
```

Expected: three `InlineKeyboardMarkup(...)` objects printed, no errors.

- [ ] **Step 3: Commit**

```bash
git add bot/keyboards/inline.py
git commit -m "Add rating, feedback-skip, and five-star referral keyboards"
```

---

## Task 5: Create `bot/handlers/rating.py` router

**Files:**
- Create: `bot/handlers/rating.py`

- [ ] **Step 1: Create the new router file**

Create `bot/handlers/rating.py` with this exact content:

```python
"""Хендлеры флоу оценки генераций (звёзды + текстовый фидбек)."""

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import (
    get_feedback_skip_keyboard,
    get_five_star_keyboard,
    get_rating_keyboard,
)
from bot.services.user_limits import (
    ADMIN_ID,
    get_last_generation_context,
    mark_as_rated,
)
from bot.states.generation import GenerationStates

logger = logging.getLogger(__name__)

router = Router()

STYLE_LABELS_RU = {
    "business": "деловой",
    "casual": "кежуал",
    "creative": "креативный",
}

GENDER_LABELS_RU = {
    "male": "мужской",
    "female": "женский",
}


async def send_rating_request(bot: Bot, chat_id: int) -> None:
    """Отправляет пользователю запрос на оценку генерации."""
    try:
        await bot.send_message(
            chat_id,
            "Как тебе результат?",
            reply_markup=get_rating_keyboard(),
        )
    except Exception as e:
        logger.error(f"Failed to send rating request to {chat_id}: {e}")


async def _send_rating_to_admin_stage1(
    bot: Bot,
    user_id: int,
    username: str | None,
    first_name: str | None,
    rating: int,
) -> None:
    """Отправляет админу оценку + оба фото (первый этап, сразу после клика по звезде).

    При rating == 5 админу ничего не отправляется (обрабатывается на уровне вызова).
    """
    if user_id == ADMIN_ID:
        # Не спамим админу его собственные оценки
        return

    ctx = get_last_generation_context(user_id)
    if not ctx:
        logger.error(f"No generation context for user {user_id}, cannot notify admin")
        return

    username_str = f"@{username}" if username else "(нет username)"
    name_str = first_name or ""
    gender_ru = GENDER_LABELS_RU.get(ctx["gender"], ctx["gender"] or "?")
    style_ru = STYLE_LABELS_RU.get(ctx["style"], ctx["style"] or "?")

    caption = (
        f"⭐ Новая оценка: {rating}/5\n"
        f"User: {user_id} ({username_str}) {name_str}\n"
        f"Пол: {gender_ru}, стиль: {style_ru}"
    )

    # Сообщение 1: оригинальное фото (по file_id)
    if ctx["photo_file_id"]:
        try:
            await bot.send_photo(
                ADMIN_ID,
                photo=ctx["photo_file_id"],
                caption=caption,
            )
        except Exception as e:
            logger.error(f"Failed to send original photo to admin: {e}")
            # Фолбэк: хотя бы текстовое сообщение с оценкой
            await bot.send_message(ADMIN_ID, caption)
    else:
        # Нет file_id — отправляем только текст
        await bot.send_message(ADMIN_ID, caption)

    # Сообщение 2: сгенерированный результат (по URL)
    if ctx["result_url"]:
        try:
            await bot.send_photo(
                ADMIN_ID,
                photo=ctx["result_url"],
                caption="Результат генерации",
            )
        except Exception as e:
            logger.error(f"Failed to send result photo to admin: {e}")


async def _send_feedback_text_to_admin(
    bot: Bot, user_id: int, feedback_text: str
) -> None:
    """Отправляет админу текст фидбека (второй этап)."""
    if user_id == ADMIN_ID:
        return
    try:
        await bot.send_message(
            ADMIN_ID,
            f"Фидбек от {user_id}:\n{feedback_text}",
        )
    except Exception as e:
        logger.error(f"Failed to send feedback text to admin: {e}")


@router.callback_query(F.data.startswith("rate:"))
async def handle_rating(
    callback: CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    """Обработчик клика по звезде оценки."""
    await callback.answer()
    user_id = callback.from_user.id
    try:
        rating = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        logger.warning(f"Invalid rating callback: {callback.data}")
        return

    if not 1 <= rating <= 5:
        logger.warning(f"Rating out of range: {rating}")
        return

    # Помечаем юзера как оценившего (один раз в жизни)
    mark_as_rated(user_id)

    if rating == 5:
        # 5 звёзд — благодарим и предлагаем поделиться
        try:
            await callback.message.edit_text(
                "🎉 Рад, что понравилось!\n\n"
                "Поделись ботом с другом — и получишь бесплатную "
                "генерацию за его первое фото.",
                reply_markup=get_five_star_keyboard(),
            )
        except Exception as e:
            logger.error(f"Failed to edit message after 5-star: {e}")
        return

    # 1–4 звезды — отправляем админу сразу, запрашиваем текстовый фидбек
    await _send_rating_to_admin_stage1(
        bot=bot,
        user_id=user_id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        rating=rating,
    )

    try:
        await callback.message.edit_text(
            "Жаль, что не идеально 😔\n\n"
            "Расскажи, что можно улучшить? Напиши в ответ "
            "или нажми «Пропустить».",
            reply_markup=get_feedback_skip_keyboard(),
        )
    except Exception as e:
        logger.error(f"Failed to edit message after low rating: {e}")

    await state.set_state(GenerationStates.awaiting_feedback_text)


@router.message(GenerationStates.awaiting_feedback_text, F.text)
async def handle_feedback_text(
    message: Message, state: FSMContext, bot: Bot
) -> None:
    """Обработчик текстового фидбека после низкой оценки."""
    user_id = message.from_user.id
    feedback = message.text or ""

    # Игнорим команды — пусть они обрабатываются своими хендлерами
    if feedback.startswith("/"):
        await state.clear()
        return

    await _send_feedback_text_to_admin(bot, user_id, feedback)
    await message.answer("Спасибо за фидбек! Мы это учтём.")
    await state.clear()


@router.callback_query(
    F.data == "feedback_skip", GenerationStates.awaiting_feedback_text
)
async def handle_feedback_skip(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Обработчик кнопки 'Пропустить' на запросе текстового фидбека."""
    await callback.answer()
    try:
        await callback.message.edit_text("Ок, спасибо за оценку!")
    except Exception as e:
        logger.error(f"Failed to edit message on feedback skip: {e}")
    await state.clear()


@router.message(GenerationStates.awaiting_feedback_text)
async def handle_non_text_in_feedback_state(message: Message) -> None:
    """Ловит любое НЕ-текстовое сообщение в состоянии ожидания фидбека.

    Без этого хендлера (менее специфичного, чем F.text выше, но более
    специфичного, чем фолбэк photo.handle_photo_without_state без стейта)
    фото/стикеры/GIF'ы провалились бы в handle_photo_without_state и
    прерывали бы флоу фидбека. Явно просим пользователя написать текст
    или нажать Пропустить.
    """
    await message.answer(
        "Напиши, пожалуйста, текстом что можно улучшить, "
        "или нажми «Пропустить» под предыдущим сообщением."
    )
```

**Ordering note:** this handler must be declared AFTER `handle_feedback_text` in the file. Aiogram matches handlers in registration order within a router. `handle_feedback_text` has the narrower filter (`F.text`), so it wins for text messages; this catch-all picks up everything else (photos, stickers, GIFs, etc.).

- [ ] **Step 2: Syntax check**

```bash
python -c "from bot.handlers import rating; print(rating.router)"
```

Expected: `<Router 'unnamed'>` or similar, no errors.

- [ ] **Step 3: Commit**

```bash
git add bot/handlers/rating.py
git commit -m "Add rating handlers: star clicks, feedback text, skip, admin forwarding"
```

---

## Task 6: Wire rating router into `bot/main.py`

**Files:**
- Modify: `bot/main.py`

- [ ] **Step 1: Import and register the new router**

Find the existing import (line 11):

```python
from bot.handlers import broadcast, payment, photo, start
```

Replace with:

```python
from bot.handlers import broadcast, payment, photo, rating, start
```

Find the router registration block (lines 43–46):

```python
    dp.include_router(start.router)
    dp.include_router(broadcast.router)
    dp.include_router(payment.router)
    dp.include_router(photo.router)
```

Replace with:

```python
    dp.include_router(start.router)
    dp.include_router(broadcast.router)
    dp.include_router(payment.router)
    dp.include_router(rating.router)
    dp.include_router(photo.router)
```

**Important ordering:** `rating.router` must be registered **before** `photo.router`. Reason: `photo.router` has a catch-all `@router.message(GenerationStates.awaiting_photo)` handler and similar state-bound handlers. We want the rating's `@router.message(GenerationStates.awaiting_feedback_text, F.text)` to win for feedback text. Registering rating first ensures its filter gets first pick. (In practice state filters don't collide with each other since they target different states, but this ordering is safer for future changes.)

- [ ] **Step 2: Syntax check**

```bash
python -c "from bot.main import main; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add bot/main.py
git commit -m "Register rating router in bot main"
```

---

## Task 7: Trigger rating request in `bot/handlers/photo.py`

**Files:**
- Modify: `bot/handlers/photo.py` (imports at top; handler body around lines 108–158)

- [ ] **Step 1: Update imports**

Find the imports block (lines 7–20):

```python
from bot.keyboards.inline import get_buy_keyboard, get_restart_keyboard
from bot.services.kie_client import KieClientError, kie_client
from bot.services.openai_client import OpenAIClientError, openai_client
from bot.services.user_limits import (
    can_generate,
    get_generations_count,
    get_remaining_generations,
    has_free_generations,
    increment_generations,
    log_generation,
    reward_referrer,
    save_last_photo,
)
from bot.states.generation import GenerationStates
```

Replace with:

```python
from bot.handlers.rating import send_rating_request
from bot.keyboards.inline import get_buy_keyboard, get_restart_keyboard
from bot.services.kie_client import KieClientError, kie_client
from bot.services.openai_client import OpenAIClientError, openai_client
from bot.services.user_limits import (
    can_generate,
    get_generations_count,
    get_remaining_generations,
    has_free_generations,
    has_user_rated,
    increment_generations,
    log_generation,
    reward_referrer,
    save_last_photo,
)
from bot.states.generation import GenerationStates
```

- [ ] **Step 2: Pass `photo_file_id` and `result_url` to `save_last_photo`**

Find the existing `save_last_photo` call (line 130):

```python
        # Сохраняем URL фото, пол и стиль для возможности регенерации
        save_last_photo(user_id, file_url, gender, style)
```

Replace with:

```python
        # Сохраняем URL фото, file_id оригинала, пол, стиль и URL результата
        save_last_photo(
            user_id,
            file_url,
            gender,
            style,
            photo_file_id=photo.file_id,
            result_url=result_url,
        )
```

Note: `photo` is already defined on line 81 (`photo = message.photo[-1]`), and `result_url` is already defined on line 96 (from `kie_client.transform_photo`). Both are in scope.

- [ ] **Step 3: Call `send_rating_request` after the result is sent**

Find the block ending with logger.info on line 160–162:

```python
        logger.info(
            f"Successfully generated photo for user {user_id}"
        )
```

Immediately after it (still inside the `try:` block, before the `except` clauses), add:

```python
        # После первой успешной генерации — запросить оценку (один раз в жизни)
        if was_first_generation and not has_user_rated(user_id):
            await send_rating_request(bot, message.chat.id)
```

Note: `was_first_generation` is already defined on line 108 of the handler. `bot` is a parameter of `handle_photo`. `message.chat.id` is the user's chat.

**Important:** this must happen BEFORE `state.clear()` in the `finally:` block — but since the `finally` runs after this `try:` body completes anyway, we just place our call at the end of the successful path. The state will be cleared by `finally:`, and the rating handler in Task 5 sets its own state (`awaiting_feedback_text`) fresh from the callback FSM context.

- [ ] **Step 4: Manual verification — syntax**

```bash
python -c "from bot.handlers import photo; print('ok')"
```

Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/photo.py
git commit -m "Trigger rating request after first successful generation in photo handler"
```

---

## Task 8: Trigger rating request in `bot/handlers/start.py` regenerate branch

**Files:**
- Modify: `bot/handlers/start.py` (regenerate handler, imports block around line 189, body around line 288)

- [ ] **Step 1: Update the inline import inside the regenerate handler**

Find the import block inside the regenerate handler (lines 189–195):

```python
    from bot.services.user_limits import (
        get_generations_count,
        has_free_generations,
        increment_generations,
        log_generation,
        reward_referrer,
    )
```

Replace with:

```python
    from bot.handlers.rating import send_rating_request
    from bot.services.user_limits import (
        get_generations_count,
        has_free_generations,
        has_user_rated,
        increment_generations,
        log_generation,
        reward_referrer,
    )
```

- [ ] **Step 2: Call `send_rating_request` after successful regeneration**

Find the `logger.info` block on lines 288–290:

```python
        logger.info(
            f"Successfully regenerated photo for user {user_id}"
        )
```

Immediately after it (still inside the `try:` block), add:

```python
        # После первой успешной генерации — запросить оценку (один раз в жизни)
        if was_first_generation and not has_user_rated(user_id):
            await send_rating_request(callback.bot, callback.message.chat.id)
```

Note: `was_first_generation` is already defined on line 239. `callback` is a parameter of the regenerate handler.

**Note on reachability:** In the current codebase, `was_first_generation == True` inside the regenerate handler is practically unreachable — regenerate requires a prior `save_last_photo` which only runs after a successful generation (which already incremented the counter). This code path is added for symmetry with `photo.py` and robustness against future refactors.

- [ ] **Step 3: Manual verification — syntax**

```bash
python -c "from bot.handlers import start; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add bot/handlers/start.py
git commit -m "Trigger rating request in regenerate branch for symmetry"
```

---

## Task 9: End-to-end manual smoke test

**Files:** none (runtime verification only)

- [ ] **Step 1: Start bot locally**

```bash
source venv/bin/activate
python -m bot.main
```

Expected: logs show `Starting bot...`, `Added last_photo_file_id column...` (first run only), `Bot started successfully!`.

- [ ] **Step 2: Test path A — fresh user, 5-star rating**

1. From a Telegram account that has **never used the bot before** (or delete its row from `user_data.db` first: `python -c "import sqlite3; sqlite3.connect('user_data.db').execute('DELETE FROM users WHERE user_id = YOUR_ID').connection.commit()"`).
2. Send `/start`.
3. Pick gender, pick style, send a photo.
4. Wait for the generated result.
5. **Expected:** immediately after the result, a second message appears: *"Как тебе результат?"* with 5 star buttons.
6. Click the 5th star.
7. **Expected:** the rating message is edited to *"🎉 Рад, что понравилось! Поделись ботом с другом..."* with a single button *"🎁 Получить реферальную ссылку"*.
8. Click the button.
9. **Expected:** a new message with the referral link appears (handled by existing `show_referral_link`).
10. **Expected:** admin (you, ADMIN_ID = 91892537) received **nothing** for this 5-star case.

- [ ] **Step 3: Test path B — fresh user, low rating + text feedback**

1. Reset DB row for the test account again.
2. `/start` → gender → style → photo → wait for result.
3. Click the 3rd star on the rating message.
4. **Expected:** admin receives three things in sequence:
   - Photo: the original selfie (via file_id), caption `⭐ Новая оценка: 3/5\nUser: <id> (@username) <name>\nПол: ..., стиль: ...`
   - Photo: the generated result, caption `Результат генерации`
   - (No text yet)
5. **Expected in user chat:** rating message edited to *"Жаль, что не идеально 😔 Расскажи, что можно улучшить?"* with a *"Пропустить"* button.
6. Send a text message: *"лицо не похоже на меня"*.
7. **Expected:** bot replies *"Спасибо за фидбек! Мы это учтём."*
8. **Expected:** admin receives a third message: `Фидбек от <user_id>:\nлицо не похоже на меня`.

- [ ] **Step 4: Test path C — fresh user, low rating + skip**

1. Reset DB row. `/start` → gender → style → photo → wait for result.
2. Click the 2nd star.
3. **Expected:** admin receives 2 photo messages + caption (stage 1), same as path B step 4.
4. Click *"Пропустить"* instead of typing.
5. **Expected:** bot replies *"Ок, спасибо за оценку!"*
6. **Expected:** admin receives **no** additional feedback text message (only the stage-1 photos from before).

- [ ] **Step 5: Test path D — rating shown only once**

1. After any of paths A/B/C (no DB reset), send another photo to the bot (new generation).
2. **Expected:** no rating request appears after the second generation.

- [ ] **Step 6: Test path E — user ignores rating request**

1. Reset DB row. `/start` → gender → style → photo → wait for result + rating request.
2. Do **not** click any star. Instead, click *"Создать с новым фото"* (or upload a new photo directly).
3. Complete a second generation.
4. **Expected:** no new rating request. (The first one also never resolved — its star buttons still work if clicked, but that's fine; `has_rated` was never set, but the second generation is no longer the first.)
5. Manually verify in DB: `python -c "import sqlite3; print(sqlite3.connect('user_data.db').execute('SELECT has_rated FROM users WHERE user_id = YOUR_ID').fetchone())"`. Expected: `(0,)`.

- [ ] **Step 7: Edge case — non-text in feedback state**

1. Reset DB row. Full flow → click 3 stars → get the feedback prompt.
2. Instead of text, send a photo (or a sticker).
3. **Expected:** bot replies *"Напиши, пожалуйста, текстом что можно улучшить, или нажми «Пропустить»..."*
4. **Expected:** the FSM state is NOT cleared (user can still type text or click Skip after this).
5. Now send text. **Expected:** feedback is forwarded to admin, state clears normally.

- [ ] **Step 8: Edge case — admin rating themselves**

1. From the admin account (ADMIN_ID = 91892537), reset own DB row, do a full generation flow.
2. Click any low star (1–4).
3. **Expected:** bot shows the feedback prompt to admin as usual, but **no** admin-notification photos/messages are sent (skip on `user_id == ADMIN_ID`).

- [ ] **Step 9: Commit (if nothing changed)**

No code changes in this task; just verification. Skip the commit step.

---

## Post-implementation

After all tasks pass their manual verification, the feature is ready for deployment. Use the deployment procedure from `CLAUDE.md` / memory (individual-file SCP to `/tmp`, `sudo cp` to `/opt/photoshoot_ai/`, verify, restart service, check logs).

Files to deploy:
- `bot/services/user_limits.py`
- `bot/states/generation.py`
- `bot/keyboards/inline.py`
- `bot/handlers/rating.py` (new)
- `bot/handlers/photo.py`
- `bot/handlers/start.py`
- `bot/main.py`

Post-deploy smoke: do one test generation from a fresh account against the production bot and confirm the rating request appears.

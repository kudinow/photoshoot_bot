# First-Generation Watermark + 50₽ Unlock — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Watermark every non-admin user's first free generation with a diagonal `ai-photobot.ru` mark; let them remove it by paying a dedicated **50₽** micro-payment, after which the bot auto-sends the clean photo (no generation credits granted).

**Architecture:** A pure-function Pillow watermark module writes the clean bytes to disk (`/opt/photoshoot_ai/clean/{user_id}.jpg`) and returns watermarked JPEG. The first-gen branch in `bot/handlers/photo.py` applies it and shows a `🔓 Убрать знак — 50₽` button. The 50₽ unlock is modelled as a special `CreditPackage` (`watermark_unlock`, 0 credits) that rides the **existing** YooKassa payment pipeline; on confirmation the pipeline branches to deliver the clean photo from disk instead of crediting generations.

**Tech Stack:** Python 3.9+, aiogram 3.x, Pillow (new), existing aiohttp / sqlite / YooKassa infra.

**Spec:** [docs/superpowers/specs/2026-05-29-watermark-unlock-50r-design.md](../specs/2026-05-29-watermark-unlock-50r-design.md)

**Testing approach:** No pytest suite exists. Verification per task is (a) `ast.parse` + import checks, (b) one-off local scripts for pure functions, (c) end-to-end Telegram smoke test with an admin account + a non-admin test account.

**Deployment approach:** Per project memory — SCP each file to `/tmp` → `sudo cp` to `/opt/photoshoot_ai/` → `chown deploy:deploy` → `grep`-verify → restart. NEVER `scp -r` / `cp -r`. Install Pillow on prod **before** restart. Branch: `feature/watermark` (already created).

---

## File Structure

**Create:**
- `bot/services/watermark.py` — pure functions: `apply_watermark()`, `save_clean_copy()`, `get_clean_copy()`, internal `_clean_dir()` / `_clean_path()` / `_load_font()`.
- `bot/handlers/watermark.py` — `handle_unlock_watermark` callback: idempotent re-delivery if already paid, else start a 50₽ payment.

**Modify:**
- `requirements.txt` — add `Pillow>=10.0.0`.
- `bot/config.py` — add `WATERMARK_UNLOCK_ID` + `WATERMARK_UNLOCK` package; extend `get_package_by_id()` to resolve it.
- `bot/services/user_limits.py` — add `has_unlocked_watermark(user_id)`.
- `bot/keyboards/inline.py` — add `has_watermarked` kwarg to `get_restart_keyboard`.
- `bot/handlers/payment.py` — add `_deliver_after_payment()` helper; branch `_poll_payment` + `check_payment_status` + `_notify_admin_payment` on the unlock package.
- `bot/handlers/photo.py` — hook watermark after `download_image`; branch caption + keyboard on `watermarked`.
- `bot/main.py` — register `watermark.router`.
- `CLAUDE.md` — document the feature.

**Not touched:** `bot/handlers/start.py` (regenerate branch — `was_first_generation` is always `False` there for non-admin, so a hook would be dead code).

---

## Task 1: Add Pillow dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Append Pillow to requirements.txt**

Add one line at the end of `requirements.txt`:

```
Pillow>=10.0.0
```

- [ ] **Step 2: Install locally**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && pip install -r requirements.txt
```
Expected: `Successfully installed pillow-X.Y.Z` or "Requirement already satisfied".

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "Add Pillow dependency for watermarking"
```

---

## Task 2: Create watermark module (pure functions + disk storage)

**Files:**
- Create: `bot/services/watermark.py`

- [ ] **Step 1: Write `bot/services/watermark.py`**

```python
"""Наложение водяного знака на фото первой генерации + хранение чистой версии."""

from __future__ import annotations

import io
import logging
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

WATERMARK_TEXT = "ai-photobot.ru"

# Пути к директориям с чистыми версиями (prod / локально)
_PROD_CLEAN_DIR = Path("/opt/photoshoot_ai/clean")
_LOCAL_CLEAN_DIR = Path(__file__).parent.parent.parent / "clean"

# Кандидаты на шрифт (Ubuntu prod + macOS dev)
_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def _clean_dir() -> Path:
    """Директория для чистых версий: prod, если есть /opt/photoshoot_ai, иначе локально."""
    if _PROD_CLEAN_DIR.parent.exists():
        return _PROD_CLEAN_DIR
    return _LOCAL_CLEAN_DIR


def _clean_path(user_id: int) -> Path:
    return _clean_dir() / f"{user_id}.jpg"


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception as e:
                logger.warning(f"Failed to load font {path}: {e}")
    return ImageFont.load_default()


def apply_watermark(image_bytes: bytes) -> bytes:
    """Наложить диагональный водяной знак ai-photobot.ru и вернуть JPEG."""
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = base.size

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    font_size = max(18, int(min(w, h) * 0.035))
    font = _load_font(font_size)

    # Большой холст для повторов, потом повернём и наложим по центру
    diagonal = math.hypot(w, h)
    big = int(diagonal * 1.3)
    tile = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    tile_draw = ImageDraw.Draw(tile)

    # Ширина одного повтора текста
    try:
        bbox = tile_draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
        text_w = bbox[2] - bbox[0]
    except Exception:
        text_w = font_size * 8

    step = max(int(diagonal * 0.22), text_w + 40)

    for i, y in enumerate(range(-step, big + step, step)):
        offset = (i % 2) * (step // 2)
        for x in range(-step + offset, big + step, step):
            tile_draw.text(
                (x, y),
                WATERMARK_TEXT,
                font=font,
                fill=(255, 255, 255, 110),
                stroke_width=max(1, font_size // 14),
                stroke_fill=(0, 0, 0, 140),
            )

    rotated = tile.rotate(-30, resample=Image.BICUBIC, expand=False)
    ox = (w - big) // 2
    oy = (h - big) // 2
    overlay.paste(rotated, (ox, oy), rotated)

    composited = Image.alpha_composite(base, overlay).convert("RGB")
    out = io.BytesIO()
    composited.save(out, format="JPEG", quality=92)
    return out.getvalue()


def save_clean_copy(user_id: int, image_bytes: bytes) -> None:
    """Сохраняет чистую (без знака) версию на диск атомарно."""
    target_dir = _clean_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = _clean_path(user_id)
    tmp = target.with_suffix(".jpg.tmp")
    tmp.write_bytes(image_bytes)
    os.replace(tmp, target)
    logger.info(f"Saved clean copy for user {user_id} at {target}")


def get_clean_copy(user_id: int) -> bytes | None:
    """Читает чистую версию с диска или None, если файла нет."""
    path = _clean_path(user_id)
    if not path.exists():
        return None
    return path.read_bytes()
```

- [ ] **Step 2: Smoke-test `apply_watermark` on a sample JPG**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && python3 -c "
from pathlib import Path
from bot.services.watermark import apply_watermark
sample = Path('landing/photo/hero-after.jpg').read_bytes()
out = apply_watermark(sample)
Path('/tmp/wm_test.jpg').write_bytes(out)
print(f'Wrote /tmp/wm_test.jpg ({len(out)} bytes)')
"
```
Expected: prints `Wrote /tmp/wm_test.jpg (<size>)`. (If `landing/photo/hero-after.jpg` is absent, substitute any local JPG.)

- [ ] **Step 3: Visually verify**

```bash
open /tmp/wm_test.jpg
```
Confirm: `ai-photobot.ru` repeated diagonally, semi-transparent white with dark stroke, readable on light & dark regions, face still recognizable. If too faint/opaque/sparse, tweak `fill` alpha (110), `step` factor (0.22), `font_size` factor (0.035) and re-run Step 2. Ship a reasonable default — do not over-engineer.

- [ ] **Step 4: Round-trip test for disk storage**

```bash
python3 -c "
from bot.services.watermark import save_clean_copy, get_clean_copy, _clean_path
save_clean_copy(99999, b'hello-bytes')
assert get_clean_copy(99999) == b'hello-bytes', 'round-trip failed'
assert get_clean_copy(88888) is None, 'missing should be None'
print('round-trip ok, file at', _clean_path(99999))
_clean_path(99999).unlink()
"
```
Expected: `round-trip ok, file at <project>/clean/99999.jpg`.

- [ ] **Step 5: Commit**

```bash
git add bot/services/watermark.py
git commit -m "Add watermark service (Pillow) with clean-copy disk storage"
```

---

## Task 3: Add the 50₽ unlock package to config

**Files:**
- Modify: `bot/config.py`

- [ ] **Step 1: Add the unlock package constants**

In `bot/config.py`, right after the `CREDIT_PACKAGES: tuple[...] = (...)` block (after the closing `)` of the tuple, before `def get_package_by_id`), add:

```python
# Спец-«пакет» для снятия водяного знака (50₽, 0 кредитов).
# НЕ входит в CREDIT_PACKAGES — не показывается в меню покупки.
WATERMARK_UNLOCK_ID = "watermark_unlock"

WATERMARK_UNLOCK = CreditPackage(
    id=WATERMARK_UNLOCK_ID,
    credits=0,
    price_rub=50,
    price_kopecks=5000,
    label="Фото без водяного знака — 50 ₽",
)
```

- [ ] **Step 2: Extend `get_package_by_id` to resolve the unlock package**

Replace the existing `get_package_by_id`:

```python
def get_package_by_id(package_id: str) -> CreditPackage | None:
    """Возвращает пакет по его ID"""
    for pkg in CREDIT_PACKAGES:
        if pkg.id == package_id:
            return pkg
    return None
```

with:

```python
def get_package_by_id(package_id: str) -> CreditPackage | None:
    """Возвращает пакет по его ID (включая спец-пакет снятия водяного знака)"""
    if package_id == WATERMARK_UNLOCK_ID:
        return WATERMARK_UNLOCK
    for pkg in CREDIT_PACKAGES:
        if pkg.id == package_id:
            return pkg
    return None
```

- [ ] **Step 3: Verify**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && python3 -c "
from bot.config import get_package_by_id, CREDIT_PACKAGES, WATERMARK_UNLOCK_ID
u = get_package_by_id(WATERMARK_UNLOCK_ID)
assert u is not None and u.credits == 0 and u.price_kopecks == 5000, u
assert all(p.id != WATERMARK_UNLOCK_ID for p in CREDIT_PACKAGES), 'unlock leaked into menu'
assert get_package_by_id('pack_5') is not None
assert get_package_by_id('nope') is None
print('config ok:', u.label)
"
```
Expected: `config ok: Фото без водяного знака — 50 ₽`.

- [ ] **Step 4: Commit**

```bash
git add bot/config.py
git commit -m "Add 50r watermark_unlock package (0 credits), resolvable via get_package_by_id"
```

---

## Task 4: Add `has_unlocked_watermark` helper

**Files:**
- Modify: `bot/services/user_limits.py`

- [ ] **Step 1: Add the function**

In `bot/services/user_limits.py`, add this function immediately after `get_pending_payment_by_provider_id()` (end of the `# --- Платежи ---` section):

```python
def has_unlocked_watermark(user_id: int) -> bool:
    """True, если у юзера есть подтверждённый платёж за снятие водяного знака."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM payments "
            "WHERE user_id = ? AND package_id = ? AND status = 'confirmed' "
            "LIMIT 1",
            (user_id, "watermark_unlock"),
        ).fetchone()
    return row is not None
```

- [ ] **Step 2: Verify**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && python3 -c "
from bot.services.user_limits import has_unlocked_watermark
print('admin:', has_unlocked_watermark(91892537))
print('random:', has_unlocked_watermark(1234567890))
"
```
Expected: both print `False` on a fresh local DB, no crash.

- [ ] **Step 3: Commit**

```bash
git add bot/services/user_limits.py
git commit -m "Add has_unlocked_watermark helper"
```

---

## Task 5: Extend `get_restart_keyboard` with `has_watermarked`

**Files:**
- Modify: `bot/keyboards/inline.py`

- [ ] **Step 1: Replace `get_restart_keyboard`**

Current implementation (lines ~30-50):

```python
def get_restart_keyboard(
    has_last_photo: bool = False, has_credits: bool = True
) -> InlineKeyboardMarkup:
    """Клавиатура для повторной генерации"""
    buttons = []

    if has_last_photo:
        buttons.append([
            InlineKeyboardButton(text="🔄 Сгенерировать заново", callback_data="regenerate"),
        ])

    buttons.append([
        InlineKeyboardButton(text="✨ Создать с новым фото", callback_data="restart"),
    ])

    if not has_credits:
        buttons.append([
            InlineKeyboardButton(text="💳 Купить генерации", callback_data="buy_credits"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

Replace with (adds `has_watermarked` as the LAST kwarg and PREPENDS the unlock row):

```python
def get_restart_keyboard(
    has_last_photo: bool = False,
    has_credits: bool = True,
    has_watermarked: bool = False,
) -> InlineKeyboardMarkup:
    """Клавиатура для повторной генерации"""
    buttons = []

    if has_watermarked:
        buttons.append([
            InlineKeyboardButton(text="🔓 Убрать знак — 50 ₽", callback_data="unlock_watermark"),
        ])

    if has_last_photo:
        buttons.append([
            InlineKeyboardButton(text="🔄 Сгенерировать заново", callback_data="regenerate"),
        ])

    buttons.append([
        InlineKeyboardButton(text="✨ Создать с новым фото", callback_data="restart"),
    ])

    if not has_credits:
        buttons.append([
            InlineKeyboardButton(text="💳 Купить генерации", callback_data="buy_credits"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

- [ ] **Step 2: Verify both paths**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && python3 -c "
from bot.keyboards.inline import get_restart_keyboard
kb = get_restart_keyboard(has_last_photo=True, has_credits=True, has_watermarked=True)
flat = [b.callback_data for row in kb.inline_keyboard for b in row]
assert flat[0] == 'unlock_watermark', flat
print('watermarked layout:', flat)
kb2 = get_restart_keyboard(has_last_photo=True, has_credits=True)
flat2 = [b.callback_data for row in kb2.inline_keyboard for b in row]
assert 'unlock_watermark' not in flat2, flat2
print('default layout:', flat2)
"
```
Expected: first list starts with `unlock_watermark`; second has no `unlock_watermark`.

- [ ] **Step 3: Commit**

```bash
git add bot/keyboards/inline.py
git commit -m "Add 'Убрать знак — 50₽' button to restart keyboard via has_watermarked"
```

---

## Task 6: Payment-pipeline delivery branch for the unlock package

**Files:**
- Modify: `bot/handlers/payment.py`

- [ ] **Step 1: Update imports**

At the top of `bot/handlers/payment.py`, change the config import:

```python
from bot.config import CREDIT_PACKAGES, get_package_by_id
```
to:
```python
from bot.config import CREDIT_PACKAGES, WATERMARK_UNLOCK_ID, get_package_by_id
```

Add to the aiogram types import (currently `from aiogram.types import CallbackQuery`):
```python
from aiogram.types import BufferedInputFile, CallbackQuery
```

Add a new import line below the existing `from bot.services...` imports:
```python
from bot.services.watermark import get_clean_copy
```

- [ ] **Step 2: Add the shared delivery helper**

Add this function near the bottom of `payment.py`, right before `_notify_admin_payment`:

```python
async def _deliver_after_payment(bot: Bot, user_id: int, pkg) -> None:
    """Доставка результата после подтверждённой оплаты.

    Для пакета снятия водяного знака — присылает чистое фото.
    Для обычных пакетов — сообщение о начислении генераций.
    """
    if pkg.id == WATERMARK_UNLOCK_ID:
        clean = get_clean_copy(user_id)
        if clean:
            await bot.send_photo(
                user_id,
                BufferedInputFile(clean, filename="studio_portrait.jpg"),
                caption="🎁 Готово! Вот твоё фото без водяного знака.",
            )
        else:
            await bot.send_message(
                user_id,
                "Оплата прошла, но чистая версия не найдена 😔\n"
                "Напиши в поддержку — поможем.",
            )
        return

    # Обычный пакет
    remaining = get_remaining_generations(user_id)
    await bot.send_message(
        user_id,
        f"✅ <b>Оплата прошла успешно!</b>\n\n"
        f"Начислено: <b>{pkg.credits} генераций</b>\n"
        f"Доступно генераций: <b>{remaining}</b>\n\n"
        f"Нажми кнопку ниже, чтобы создать фото!",
        reply_markup=get_after_payment_keyboard(),
    )
```

- [ ] **Step 3: Use the helper in the background poll**

In `_poll_payment`, find the `if status == "succeeded":` block (the `success = confirm_payment(internal_id)` branch that currently sends the "Оплата прошла успешно" message inline). Replace its inner body:

```python
        if status == "succeeded":
            success = confirm_payment(internal_id)
            if success:
                remaining = get_remaining_generations(user_id)
                try:
                    await bot.send_message(
                        user_id,
                        f"✅ <b>Оплата прошла успешно!</b>"
                        f"\n\n"
                        f"Начислено: "
                        f"<b>{pkg.credits} генераций</b>\n"
                        f"Доступно генераций: "
                        f"<b>{remaining}</b>\n\n"
                        f"Нажми кнопку ниже, чтобы "
                        f"создать фото!",
                        reply_markup=(
                            get_after_payment_keyboard()
                        ),
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to notify user "
                        f"{user_id}: {e}"
                    )
                logger.info(
                    f"Poll: payment {internal_id} "
                    f"confirmed for user {user_id}"
                )
                await _notify_admin_payment(
                    bot, user_id, None, pkg
                )
            return
```

with:

```python
        if status == "succeeded":
            success = confirm_payment(internal_id)
            if success:
                try:
                    await _deliver_after_payment(bot, user_id, pkg)
                except Exception as e:
                    logger.error(
                        f"Failed to deliver to user {user_id}: {e}"
                    )
                logger.info(
                    f"Poll: payment {internal_id} "
                    f"confirmed for user {user_id}"
                )
                await _notify_admin_payment(
                    bot, user_id, None, pkg
                )
            return
```

- [ ] **Step 4: Use the helper in the manual check (unlock-only)**

In `check_payment_status`, find the `if status == "succeeded":` block:

```python
    if status == "succeeded":
        success = confirm_payment(internal_id)
        if success and pkg:
            remaining = get_remaining_generations(user_id)
            await callback.message.edit_text(
                f"✅ <b>Оплата прошла успешно!</b>\n\n"
                f"Начислено: <b>{pkg.credits} генераций</b>\n"
                f"Доступно генераций: "
                f"<b>{remaining}</b>\n\n"
                f"Теперь можешь создать "
                f"профессиональный портрет!",
                reply_markup=get_after_payment_keyboard(),
            )
            logger.info(
                f"User {user_id}: manual check confirmed "
                f"payment {internal_id}"
            )
            await _notify_admin_payment(
                callback.bot, user_id, callback.from_user, pkg
            )
```

Replace with (the manual-check path EDITS the existing message itself, so it calls `_deliver_after_payment` **only** for the unlock package — calling it for a regular package would re-send the credit message and duplicate it):

```python
    if status == "succeeded":
        success = confirm_payment(internal_id)
        if success and pkg:
            if pkg.id == WATERMARK_UNLOCK_ID:
                await callback.message.edit_text(
                    "✅ <b>Оплата прошла успешно!</b>\n\n"
                    "Сейчас пришлю фото без водяного знака 👇"
                )
                await _deliver_after_payment(callback.bot, user_id, pkg)
            else:
                remaining = get_remaining_generations(user_id)
                await callback.message.edit_text(
                    f"✅ <b>Оплата прошла успешно!</b>\n\n"
                    f"Начислено: <b>{pkg.credits} генераций</b>\n"
                    f"Доступно генераций: "
                    f"<b>{remaining}</b>\n\n"
                    f"Теперь можешь создать "
                    f"профессиональный портрет!",
                    reply_markup=get_after_payment_keyboard(),
                )
            logger.info(
                f"User {user_id}: manual check confirmed "
                f"payment {internal_id}"
            )
            await _notify_admin_payment(
                callback.bot, user_id, callback.from_user, pkg
            )
```

> **Why the asymmetry:** the background `_poll_payment` path (Step 3) has no message to edit, so `_deliver_after_payment` is its *only* notification and is called for both package types. The manual-check path already edits a message, so it only needs the helper for the unlock photo.

- [ ] **Step 5: Branch the admin notification**

Replace `_notify_admin_payment`:

```python
async def _notify_admin_payment(
    bot: Bot, user_id: int, user, pkg
) -> None:
    """Уведомляет админа об успешной оплате"""
    if user:
        name = user.full_name or ""
        username = f" (@{user.username})" if user.username else ""
    else:
        name = ""
        username = ""

    try:
        await bot.send_message(
            ADMIN_ID,
            f"💰 Оплата!\n"
            f"Пользователь: {name}{username}\n"
            f"ID: {user_id}\n"
            f"Пакет: {pkg.credits} генераций за {pkg.price_rub} ₽",
        )
    except Exception as e:
        logger.error(f"Failed to notify admin about payment: {e}")
```

with:

```python
async def _notify_admin_payment(
    bot: Bot, user_id: int, user, pkg
) -> None:
    """Уведомляет админа об успешной оплате"""
    if user:
        name = user.full_name or ""
        username = f" (@{user.username})" if user.username else ""
    else:
        name = ""
        username = ""

    if pkg.id == WATERMARK_UNLOCK_ID:
        detail = f"Снятие водяного знака за {pkg.price_rub} ₽"
    else:
        detail = f"Пакет: {pkg.credits} генераций за {pkg.price_rub} ₽"

    try:
        await bot.send_message(
            ADMIN_ID,
            f"💰 Оплата!\n"
            f"Пользователь: {name}{username}\n"
            f"ID: {user_id}\n"
            f"{detail}",
        )
    except Exception as e:
        logger.error(f"Failed to notify admin about payment: {e}")
```

- [ ] **Step 6: Syntax + import check**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && python3 -c "
import ast; ast.parse(open('bot/handlers/payment.py').read()); print('syntax ok')
from bot.handlers.payment import router, _deliver_after_payment, _poll_payment
print('payment imports ok')
"
```
Expected: `syntax ok` then `payment imports ok`.

- [ ] **Step 7: Commit**

```bash
git add bot/handlers/payment.py
git commit -m "Branch payment pipeline: deliver clean photo for watermark_unlock package"
```

---

## Task 7: Create the unlock handler + register router

**Files:**
- Create: `bot/handlers/watermark.py`
- Modify: `bot/main.py`

- [ ] **Step 1: Write `bot/handlers/watermark.py`**

```python
"""Хендлер кнопки «🔓 Убрать знак — 50₽» под фото первой генерации."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from bot.config import WATERMARK_UNLOCK_ID, get_package_by_id
from bot.handlers.payment import _poll_payment
from bot.keyboards.inline import get_payment_url_keyboard
from bot.services.user_limits import (
    cancel_payment,
    create_payment,
    has_unlocked_watermark,
    update_payment_provider_id,
)
from bot.services.watermark import get_clean_copy
from bot.services.yookassa_client import create_yookassa_payment

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(F.data == "unlock_watermark")
async def handle_unlock_watermark(
    callback: CallbackQuery, bot: Bot
) -> None:
    """По кнопке под WM-фото: отдать чистое фото (если оплачено) или начать оплату 50₽."""
    await callback.answer()
    user_id = callback.from_user.id

    clean_bytes = get_clean_copy(user_id)
    if clean_bytes is None:
        await callback.message.answer("Чистая версия больше недоступна.")
        return

    # Уже оплачено ранее — отдаём бесплатно (идемпотентно)
    if has_unlocked_watermark(user_id):
        await callback.message.answer_photo(
            photo=BufferedInputFile(
                clean_bytes, filename="studio_portrait.jpg"
            ),
            caption="🎁 Готово! Вот твоё фото без водяного знака.",
        )
        return

    # Создаём платёж 50₽ и стартуем фоновую проверку статуса
    pkg = get_package_by_id(WATERMARK_UNLOCK_ID)
    internal_id = create_payment(
        user_id=user_id,
        package_id=pkg.id,
        credits=pkg.credits,
        amount=pkg.price_kopecks,
    )

    try:
        yookassa_id, payment_url = await create_yookassa_payment(
            amount_kopecks=pkg.price_kopecks,
            description="Фото без водяного знака",
            user_id=user_id,
            package_id=pkg.id,
            internal_payment_id=internal_id,
        )
    except Exception as e:
        logger.error(
            f"YooKassa unlock payment creation failed "
            f"for user {user_id}: {e}"
        )
        cancel_payment(internal_id)
        await callback.message.answer(
            "❌ Не удалось создать платёж.\nПопробуй ещё раз позже."
        )
        return

    update_payment_provider_id(internal_id, yookassa_id)

    await callback.message.answer(
        "💳 <b>Оплата 50 ₽</b> — фото без водяного знака.\n\n"
        "Нажми «Перейти к оплате», после оплаты — «Проверить оплату».\n"
        "Чистое фото придёт автоматически.",
        reply_markup=get_payment_url_keyboard(payment_url, internal_id),
    )

    logger.info(
        f"User {user_id}: unlock payment {internal_id} created, "
        f"YooKassa ID: {yookassa_id}"
    )

    asyncio.create_task(
        _poll_payment(bot, internal_id, yookassa_id, user_id, pkg)
    )
```

- [ ] **Step 2: Register the router in `bot/main.py`**

Open `bot/main.py`. Match the existing handler-import style (search for how `rating` / `payment` routers are imported and included). Add an import alongside the others, e.g. if the file uses `from bot.handlers import payment`:

```python
from bot.handlers import watermark as watermark_handler
```

and an include near the other `dp.include_router(...)` calls:

```python
dp.include_router(watermark_handler.router)
```

(If the file imports routers as `from bot.handlers.payment import router as payment_router`, follow that pattern instead: `from bot.handlers.watermark import router as watermark_router` + `dp.include_router(watermark_router)`.)

- [ ] **Step 3: Syntax + import check**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && python3 -c "
import ast
ast.parse(open('bot/handlers/watermark.py').read())
ast.parse(open('bot/main.py').read())
print('syntax ok')
from bot.handlers.watermark import router
print('handler import ok:', router)
import bot.main
print('main import ok')
"
```
Expected: `syntax ok`, `handler import ok: <...Router...>`, `main import ok`. No circular-import error (handler imports `_poll_payment` from `payment`, which does NOT import the watermark handler).

- [ ] **Step 4: Commit**

```bash
git add bot/handlers/watermark.py bot/main.py
git commit -m "Add unlock_watermark handler (50₽ pay or idempotent re-deliver); register router"
```

---

## Task 8: Hook watermark into the first-generation branch in photo.py

**Files:**
- Modify: `bot/handlers/photo.py`

- [ ] **Step 1: Update imports**

In `bot/handlers/photo.py`, add `is_admin` to the `from bot.services.user_limits import (...)` block (alphabetical position, after `increment_generations`):

```python
from bot.services.user_limits import (
    can_generate,
    get_generations_count,
    get_remaining_generations,
    has_free_generations,
    has_user_rated,
    increment_generations,
    is_admin,
    log_generation,
    reward_referrer,
    save_last_photo,
)
```

Add below the existing service imports:

```python
from bot.services.watermark import apply_watermark, save_clean_copy
```

- [ ] **Step 2: Apply the watermark right after download**

Find (lines ~105-114):

```python
        # Скачиваем результат
        result_image = await kie_client.download_image(result_url)

        # Удаляем сообщение о обработке
        await processing_msg.delete()

        # Увеличиваем счётчик генераций
        was_first_generation = get_generations_count(user_id) == 0
        is_paid = not has_free_generations(user_id)
        increment_generations(user_id)
        log_generation(user_id, gender, style, is_paid)
```

Replace with (compute `was_first_generation` BEFORE the increment, add the watermark block, drop the duplicate assignment):

```python
        # Скачиваем результат
        result_image = await kie_client.download_image(result_url)

        # Водяной знак на первой бесплатной генерации (кроме админа)
        was_first_generation = get_generations_count(user_id) == 0
        watermarked = False
        if was_first_generation and not is_admin(user_id):
            try:
                save_clean_copy(user_id, result_image)
                result_image = apply_watermark(result_image)
                watermarked = True
            except Exception as e:
                logger.error(
                    f"Watermark failed for user {user_id}: {e}"
                )
                # Soft degradation: шлём чистое фото без кнопки разблокировки

        # Удаляем сообщение о обработке
        await processing_msg.delete()

        # Увеличиваем счётчик генераций
        is_paid = not has_free_generations(user_id)
        increment_generations(user_id)
        log_generation(user_id, gender, style, is_paid)
```

- [ ] **Step 3: Branch the result caption + keyboard on `watermarked`**

Find (lines ~143-169):

```python
        # Формируем caption с информацией об оставшихся генерациях
        remaining_after = get_remaining_generations(user_id)
        if remaining_after == -1:
            caption = "Готово! Вот твой профессиональный портрет."
        elif remaining_after > 0:
            caption = (
                f"Готово! Вот твой профессиональный портрет.\n\n"
                f"📊 Осталось генераций: {remaining_after}"
            )
        else:
            caption = (
                "Готово! Вот твой профессиональный портрет.\n\n"
                "⚠️ Это была последняя генерация.\n"
                "Купи пакет генераций, чтобы продолжить!"
            )

        # Отправляем результат
        await message.answer_photo(
            photo=BufferedInputFile(
                result_image, filename="studio_portrait.jpg"
            ),
            caption=caption,
            reply_markup=get_restart_keyboard(
                has_last_photo=True,
                has_credits=(remaining_after != 0),
            ),
        )
```

Replace with:

```python
        # Формируем caption с информацией об оставшихся генерациях
        remaining_after = get_remaining_generations(user_id)
        if watermarked:
            caption = (
                "Готово! Но фото пока с водяным знаком.\n\n"
                "Чистую версию без знака можно забрать за 50 ₽ 👇"
            )
        elif remaining_after == -1:
            caption = "Готово! Вот твой профессиональный портрет."
        elif remaining_after > 0:
            caption = (
                f"Готово! Вот твой профессиональный портрет.\n\n"
                f"📊 Осталось генераций: {remaining_after}"
            )
        else:
            caption = (
                "Готово! Вот твой профессиональный портрет.\n\n"
                "⚠️ Это была последняя генерация.\n"
                "Купи пакет генераций, чтобы продолжить!"
            )

        # Отправляем результат
        await message.answer_photo(
            photo=BufferedInputFile(
                result_image, filename="studio_portrait.jpg"
            ),
            caption=caption,
            reply_markup=get_restart_keyboard(
                has_last_photo=True,
                has_credits=(remaining_after != 0),
                has_watermarked=watermarked,
            ),
        )
```

- [ ] **Step 4: Syntax + import check**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && python3 -c "
import ast; ast.parse(open('bot/handlers/photo.py').read()); print('syntax ok')
from bot.handlers.photo import router; print('photo router ok')
"
```
Expected: `syntax ok` then `photo router ok`.

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/photo.py
git commit -m "Watermark first-gen result for non-admin; upsell caption + unlock button"
```

---

## Task 9: Local end-to-end smoke test

**Files:** none (manual verification)

> **Note:** the local bot shares the production `BOT_TOKEN`, so running it locally conflicts with prod. Either (A) `sudo systemctl stop photoshoot_ai` briefly, or (B) skip local and go straight to prod deploy (Task 10) — deploy is cheap to revert. If unsure, prefer to verify the pure pieces locally (Tasks 2-8 already did) and rely on the prod smoke test.

**If running locally (Option A):**

- [ ] **Step 1: Stop prod, wipe local test data**

```bash
ssh kudinow@89.169.163.73 "sudo systemctl stop photoshoot_ai"
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && rm -f user_data.db && rm -rf clean/
```

- [ ] **Step 2: Start the bot**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && python -m bot.main
```
Expected: `Bot started successfully!` then `Start polling`.

- [ ] **Step 3: Admin first generation**

From the admin account (91892537): `/start` → gender → style → upload selfie.
Expected: photo **without** watermark; NO `🔓 Убрать знак` button; `ls clean/` shows no admin file.

- [ ] **Step 4: Non-admin first generation**

From a second (test) account: `/start` → gender → style → upload selfie.
Expected: photo **with** diagonal watermark; caption mentions 50₽; first button row is `🔓 Убрать знак — 50 ₽`; `clean/<test_id>.jpg` exists; rating request follows.

- [ ] **Step 5: Click unlock without paying**

Click `🔓 Убрать знак — 50 ₽`.
Expected: a message with YooKassa link (`Перейти к оплате` / `Проверить оплату` / `Отмена`). No clean photo yet.

- [ ] **Step 6: Simulate payment, then deliver**

Stop the bot (Ctrl+C). Mark the unlock payment confirmed directly (find the pending unlock payment id):

```bash
python3 -c "
from bot.services.user_limits import _get_conn
with _get_conn() as conn:
    conn.execute(
        \"UPDATE payments SET status='confirmed', confirmed_at=datetime('now') \"
        \"WHERE package_id='watermark_unlock' AND status='pending'\"
    )
print('unlock payment marked confirmed')
"
```

Restart the bot. From the test account, click `🔓 Убрать знак — 50 ₽` again.
Expected: bot replies with a **clean** photo, caption `🎁 Готово! Вот твоё фото без водяного знака.` (idempotent re-delivery path via `has_unlocked_watermark`).

- [ ] **Step 7: Stop bot, restart prod**

```bash
# Ctrl+C to stop local bot, then:
ssh kudinow@89.169.163.73 "sudo systemctl start photoshoot_ai"
```
Optionally `rm -f user_data.db && rm -rf clean/` to clean local test data.

- [ ] **Step 8: No commit (manual verification only).** If any step fails, fix before deploying.

---

## Task 10: Deploy to production

**Files:** none new — deploys files changed in Tasks 1-8.

- [ ] **Step 1: Install Pillow on prod (before stopping the service)**

```bash
ssh kudinow@89.169.163.73 "sudo /opt/photoshoot_ai/venv/bin/pip install 'Pillow>=10.0.0'"
```
Expected: `Successfully installed pillow-X.Y.Z` or already-satisfied.

- [ ] **Step 2: Create the clean/ directory with deploy ownership**

```bash
ssh kudinow@89.169.163.73 "sudo mkdir -p /opt/photoshoot_ai/clean && sudo chown deploy:deploy /opt/photoshoot_ai/clean && ls -ld /opt/photoshoot_ai/clean"
```
Expected: `drwxr-xr-x ... deploy deploy ... /opt/photoshoot_ai/clean`.

- [ ] **Step 3: Verify the DejaVu font on prod**

```bash
ssh kudinow@89.169.163.73 "ls /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
```
Expected: the path lists. If MISSING: `ssh kudinow@89.169.163.73 "sudo apt-get install -y fonts-dejavu-core"` and re-verify.

- [ ] **Step 4: Stop the service**

```bash
ssh kudinow@89.169.163.73 "sudo systemctl stop photoshoot_ai" && echo stopped
```

- [ ] **Step 5: SCP each changed file individually to /tmp**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && \
scp requirements.txt kudinow@89.169.163.73:/tmp/requirements.txt && \
scp bot/config.py kudinow@89.169.163.73:/tmp/config.py && \
scp bot/services/watermark.py kudinow@89.169.163.73:/tmp/watermark_service.py && \
scp bot/services/user_limits.py kudinow@89.169.163.73:/tmp/user_limits.py && \
scp bot/keyboards/inline.py kudinow@89.169.163.73:/tmp/inline.py && \
scp bot/handlers/payment.py kudinow@89.169.163.73:/tmp/payment.py && \
scp bot/handlers/watermark.py kudinow@89.169.163.73:/tmp/watermark_handler.py && \
scp bot/handlers/photo.py kudinow@89.169.163.73:/tmp/photo.py && \
scp bot/main.py kudinow@89.169.163.73:/tmp/main.py && \
echo "scp done"
```
Expected: all succeed, final `scp done`.

- [ ] **Step 6: sudo cp into production + fix ownership**

```bash
ssh kudinow@89.169.163.73 "
sudo cp /tmp/requirements.txt /opt/photoshoot_ai/requirements.txt &&
sudo cp /tmp/config.py /opt/photoshoot_ai/bot/config.py &&
sudo cp /tmp/watermark_service.py /opt/photoshoot_ai/bot/services/watermark.py &&
sudo cp /tmp/user_limits.py /opt/photoshoot_ai/bot/services/user_limits.py &&
sudo cp /tmp/inline.py /opt/photoshoot_ai/bot/keyboards/inline.py &&
sudo cp /tmp/payment.py /opt/photoshoot_ai/bot/handlers/payment.py &&
sudo cp /tmp/watermark_handler.py /opt/photoshoot_ai/bot/handlers/watermark.py &&
sudo cp /tmp/photo.py /opt/photoshoot_ai/bot/handlers/photo.py &&
sudo cp /tmp/main.py /opt/photoshoot_ai/bot/main.py &&
sudo chown deploy:deploy \
  /opt/photoshoot_ai/requirements.txt \
  /opt/photoshoot_ai/bot/config.py \
  /opt/photoshoot_ai/bot/services/watermark.py \
  /opt/photoshoot_ai/bot/services/user_limits.py \
  /opt/photoshoot_ai/bot/keyboards/inline.py \
  /opt/photoshoot_ai/bot/handlers/payment.py \
  /opt/photoshoot_ai/bot/handlers/watermark.py \
  /opt/photoshoot_ai/bot/handlers/photo.py \
  /opt/photoshoot_ai/bot/main.py &&
echo 'copied + chowned'
"
```
Expected: `copied + chowned`.

- [ ] **Step 7: Verify new code is in place on prod**

```bash
ssh kudinow@89.169.163.73 "sudo grep -l 'apply_watermark\|unlock_watermark\|WATERMARK_UNLOCK_ID\|has_unlocked_watermark\|has_watermarked\|_deliver_after_payment' \
  /opt/photoshoot_ai/bot/config.py \
  /opt/photoshoot_ai/bot/services/watermark.py \
  /opt/photoshoot_ai/bot/services/user_limits.py \
  /opt/photoshoot_ai/bot/keyboards/inline.py \
  /opt/photoshoot_ai/bot/handlers/payment.py \
  /opt/photoshoot_ai/bot/handlers/watermark.py \
  /opt/photoshoot_ai/bot/handlers/photo.py"
```
Expected: at least 7 paths printed.

- [ ] **Step 8: Start the service and check logs**

```bash
ssh kudinow@89.169.163.73 "sudo systemctl start photoshoot_ai && sleep 3 && sudo journalctl -u photoshoot_ai -n 30 --no-pager | grep -vE 'DEBUG|httpcore|httpx'"
```
Expected: `Bot started successfully!` + `Start polling`, no `ModuleNotFoundError` / `ImportError` / traceback.
If errors: `sudo systemctl stop photoshoot_ai`, redeploy the previous files (git checkout the prior versions + repeat Steps 5-7), restart. See Rollback Plan.

- [ ] **Step 9: Prod smoke — admin**

Admin account: fresh `/start` → upload selfie. Expected: clean photo, no unlock button; `ssh kudinow@89.169.163.73 "sudo ls /opt/photoshoot_ai/clean/"` shows no admin file.

- [ ] **Step 10: Prod smoke — new user**

Second account: `/start` → upload selfie. Expected: watermarked photo, 50₽ caption, `🔓 Убрать знак — 50 ₽` button; `sudo ls /opt/photoshoot_ai/clean/` shows `<test_id>.jpg`; rating request follows.

- [ ] **Step 11: Prod smoke — pay 50₽ end-to-end (real or simulated)**

Real: click the button → pay 50₽ on YooKassa → return. Expected: within ~15s (poll) the bot auto-sends the clean photo with `🎁` caption; admin gets `💰 Оплата! ... Снятие водяного знака за 50 ₽`. Pressing `Проверить оплату` also delivers.

Simulated (no real charge):
```bash
ssh kudinow@89.169.163.73 "sudo /opt/photoshoot_ai/venv/bin/python3 -c \"
from bot.services.user_limits import _get_conn
with _get_conn() as conn:
    conn.execute(\\\"UPDATE payments SET status='confirmed', confirmed_at=datetime('now') WHERE package_id='watermark_unlock' AND status='pending'\\\")
print('unlock confirmed')
\""
```
Then click `🔓 Убрать знак — 50 ₽` again → idempotent clean-photo delivery.

- [ ] **Step 12: No commit (deploy-only).**

---

## Task 11: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a feature section after "## Generation Rating"**

Right before `## Landing Page`, insert:

```markdown
## First-Generation Watermark + 50₽ Unlock

On every non-admin user's **first successful generation**, the result is watermarked with a diagonal `ai-photobot.ru` pattern. The clean version is saved to disk and delivered after the user pays a dedicated **50₽** (`watermark_unlock`) micro-payment — which grants **0 generation credits**, only the clean photo.

**Scope:**
- Fires only when `was_first_generation and not is_admin(user_id)` in [bot/handlers/photo.py](bot/handlers/photo.py) (computed before `increment_generations`).
- Admin (`ADMIN_ID`) bypassed — always clean, no unlock button.
- Referral-credit generations (#2+) are clean.
- Soft degradation: if `apply_watermark` raises, user gets the clean photo and NO unlock button.

**Visual:** diagonal white `ai-photobot.ru`, black stroke, alpha ≈ 110, rotated -30°, step ≈ 22% of the diagonal. Rendered by [bot/services/watermark.py](bot/services/watermark.py) (Pillow + DejaVuSans-Bold on Ubuntu / Arial Bold on macOS, default-font fallback).

**Storage:** `/opt/photoshoot_ai/clean/{user_id}.jpg` (prod) or `<project>/clean/{user_id}.jpg` (local). No DB column — file existence is the source of truth. No cleanup cron.

**Unlock flow:**
- Caption on the watermarked photo upsells 50₽; the keyboard's top row is `🔓 Убрать знак — 50 ₽` (callback `unlock_watermark`).
- [bot/handlers/watermark.py](bot/handlers/watermark.py): no clean file → "Чистая версия больше недоступна."; already paid (`has_unlocked_watermark`) → re-send clean photo free (idempotent); else create a 50₽ YooKassa payment + link and start polling.
- The 50₽ unlock is a special `CreditPackage` `watermark_unlock` (credits=0, [bot/config.py](bot/config.py)), **not** in `CREDIT_PACKAGES` (hidden from the buy menu) but resolvable via `get_package_by_id`. It rides the existing payment pipeline; on confirmation [bot/handlers/payment.py](bot/handlers/payment.py)::`_deliver_after_payment` sends the clean photo (caption `🎁 Готово! Вот твоё фото без водяного знака.`) instead of crediting generations. Admin notification says "Снятие водяного знака за 50 ₽".

**Key code:** [bot/services/watermark.py](bot/services/watermark.py) (`apply_watermark`, `save_clean_copy`, `get_clean_copy`), [bot/services/user_limits.py](bot/services/user_limits.py) (`has_unlocked_watermark`), [bot/keyboards/inline.py](bot/keyboards/inline.py) (`has_watermarked` kwarg).

**Not in `start.py` regenerate branch** on purpose: `was_first_generation` there is always `False` for non-admin (photo.py increments before save_last_photo) — a hook would be dead code.

**Design docs:** [docs/superpowers/specs/2026-05-29-watermark-unlock-50r-design.md](docs/superpowers/specs/2026-05-29-watermark-unlock-50r-design.md) and [docs/superpowers/plans/2026-05-29-watermark-unlock-50r.md](docs/superpowers/plans/2026-05-29-watermark-unlock-50r.md).
```

- [ ] **Step 2: Add a Core-flow bullet**

After the rating bullet (item 6 in "Core flow"), add:

```markdown
7. For non-admin users, the first-generation result is watermarked (`ai-photobot.ru` diagonal); the clean version is delivered after a dedicated 50₽ `watermark_unlock` payment (0 credits) via the `🔓 Убрать знак — 50 ₽` button.
```

- [ ] **Step 3: Update the module table**

In the module table, update the `bot/services/user_limits.py` row to mention `has_unlocked_watermark`, and the `bot/handlers/payment.py` row to mention the `watermark_unlock` delivery branch. Add two rows after `bot/handlers/rating.py`:

```
| `bot/services/watermark.py` | Pillow `apply_watermark()` + `save_clean_copy()` / `get_clean_copy()` for first-generation watermarking |
| `bot/handlers/watermark.py` | `unlock_watermark` callback: idempotent clean-photo delivery if already paid, else starts a 50₽ payment |
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "Document watermark + 50₽ unlock feature in CLAUDE.md"
```

---

## Post-Implementation Checklist

- [ ] Bot is `active (running)` on prod.
- [ ] Admin first gen → clean photo, no unlock button, no clean file.
- [ ] Non-admin first gen → watermarked photo + 50₽ caption + unlock button + clean file on disk.
- [ ] Click unlock (unpaid) → YooKassa 50₽ payment link.
- [ ] Pay 50₽ → clean photo auto-delivered; admin notified "Снятие водяного знака".
- [ ] Re-click unlock after paying → clean photo re-delivered, no second charge.
- [ ] Regular package purchase still works (credits added, normal message) — unchanged.
- [ ] `CLAUDE.md` updated.
- [ ] Merge `feature/watermark` → `main` (or open PR) and push.

## Rollback Plan

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && git log --oneline -12
# Revert the feature commits, then redeploy the reverted files via Task 10 steps 5-7:
git revert <range>
ssh kudinow@89.169.163.73 "sudo systemctl restart photoshoot_ai"
```

`clean/` files and any already-sent watermarked photos are acceptable leftovers — no cleanup needed.
```

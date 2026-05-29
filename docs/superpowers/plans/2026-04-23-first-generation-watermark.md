# First-Generation Watermark Implementation Plan

> ⚠️ **SUPERSEDED (2026-05-29)** — the unlock mechanic changed to a dedicated 50₽ micro-payment with auto-delivery. A new plan supersedes this one. See [docs/superpowers/specs/2026-05-29-watermark-unlock-50r-design.md](../specs/2026-05-29-watermark-unlock-50r-design.md).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Watermark every user's first free generation with `ai-photobot.ru` diagonally, unlock clean version via explicit button after any confirmed payment.

**Architecture:** Add a pure-function watermark module using Pillow; save the clean bytes to disk (`/opt/photoshoot_ai/clean/{user_id}.jpg`); add a new `unlock_watermark` callback button on the first-gen result message; hook the pipeline only inside `bot/handlers/photo.py` (first-gen branch is unreachable from the regenerate path for non-admin users, so we skip `start.py`).

**Tech Stack:** Python 3.9+, aiogram 3.x, Pillow (new), existing aiohttp/sqlite/aiogram infra.

**Spec:** [docs/superpowers/specs/2026-04-23-first-generation-watermark-design.md](../specs/2026-04-23-first-generation-watermark-design.md)

**Testing approach:** This project has no pytest suite. Verification is manual via (a) a one-off local script for the pure `apply_watermark` function and (b) end-to-end smoke test in Telegram with two accounts (admin + test user). Each task lists exact verification steps.

**Deployment approach:** Per project memory, deploy by SCP to `/tmp` → `sudo cp` → verify with `grep` → restart. Do NOT use `scp -r` or `cp -r`. Pillow is installed on prod before the restart.

---

## File Structure

**Create:**
- `bot/services/watermark.py` — pure functions: `apply_watermark()`, `save_clean_copy()`, `get_clean_copy()`, plus internal `_clean_dir()` / `_load_font()` helpers.
- `bot/handlers/watermark.py` — `handle_unlock_watermark` callback handler.

**Modify:**
- `requirements.txt` — add `Pillow>=10.0.0`.
- `bot/services/user_limits.py` — add `has_ever_paid(user_id)`.
- `bot/keyboards/inline.py` — add `has_watermarked` kwarg to `get_restart_keyboard`.
- `bot/handlers/photo.py` — hook watermark after `download_image`, pass `has_watermarked` to keyboard.
- `bot/main.py` — register `watermark.router`.
- `CLAUDE.md` — document the new feature.

**Not touched:** `bot/handlers/start.py` (regenerate branch unreachable for first-gen + non-admin — dead code).

---

## Task 1: Add Pillow dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add Pillow to requirements.txt**

Edit `requirements.txt`. Append one line:

```
Pillow>=10.0.0
```

Final file content:

```
aiogram==3.13.1
aiohttp==3.10.5
python-dotenv==1.0.1
pydantic==2.9.2
pydantic-settings==2.5.2
openai>=1.0.0
yookassa>=3.5.0
Pillow>=10.0.0
```

- [ ] **Step 2: Install locally**

Run:
```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && pip install -r requirements.txt
```
Expected: `Successfully installed pillow-X.Y.Z` (or "Requirement already satisfied").

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "Add Pillow dependency for watermarking"
```

---

## Task 2: Create watermark module (pure function + disk storage)

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

# Пути к директориям с чистыми версиями
_PROD_CLEAN_DIR = Path("/opt/photoshoot_ai/clean")
_LOCAL_CLEAN_DIR = Path(__file__).parent.parent.parent / "clean"

# Кандидаты на шрифт (Ubuntu prod + macOS dev)
_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def _clean_dir() -> Path:
    """Возвращает директорию для чистых версий (prod или локально)."""
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
    draw = ImageDraw.Draw(overlay)

    font_size = max(18, int(min(w, h) * 0.035))
    font = _load_font(font_size)

    # Ширина одного повтора (примерно)
    try:
        bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except Exception:
        text_w, text_h = font_size * 8, font_size

    # Диагональный шаг между повторами (~25% диагонали)
    diagonal = math.hypot(w, h)
    step = max(int(diagonal * 0.22), text_w + 40)

    # Рисуем на большом холсте, потом поворачиваем и накладываем
    big = int(diagonal * 1.3)
    tile = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    tile_draw = ImageDraw.Draw(tile)

    for y in range(-step, big + step, step):
        offset = (y // step) % 2 * (step // 2)
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
    # Центрируем на overlay
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

- [ ] **Step 2: Smoke-test `apply_watermark` with a one-off script**

Find any sample JPG (e.g., one of the landing photos):

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

Expected: prints `Wrote /tmp/wm_test.jpg (<size>)`.

- [ ] **Step 3: Visually verify the watermark**

Open `/tmp/wm_test.jpg` (e.g., `open /tmp/wm_test.jpg` on macOS). Confirm:
- `ai-photobot.ru` text appears repeated diagonally across the image.
- Text is semi-transparent white with a dark stroke, readable on both light and dark regions.
- Face is still recognizable underneath but not pristine.

If the watermark is too faint / too opaque / too sparse — tweak constants (`fill` alpha from `110`, `step` from `0.22 * diagonal`, `font_size` from `0.035 * min`) in the module and re-run step 2. Do not over-engineer; ship a reasonable default.

- [ ] **Step 4: Smoke-test `save_clean_copy` / `get_clean_copy` round-trip**

```bash
python3 -c "
from bot.services.watermark import save_clean_copy, get_clean_copy, _clean_path
save_clean_copy(99999, b'hello-bytes')
assert get_clean_copy(99999) == b'hello-bytes', 'round-trip failed'
print('round-trip ok, file at', _clean_path(99999))
_clean_path(99999).unlink()  # cleanup
"
```
Expected: `round-trip ok, file at <project>/clean/99999.jpg`.

- [ ] **Step 5: Commit**

```bash
git add bot/services/watermark.py
git commit -m "Add watermark service (Pillow-based) with clean-copy disk storage"
```

---

## Task 3: Add `has_ever_paid` helper

**Files:**
- Modify: `bot/services/user_limits.py`

- [ ] **Step 1: Add the function**

Open `bot/services/user_limits.py`. Add this function right after the existing `get_pending_payment_by_provider_id()` function (end of the Payments section, before `# --- Реферальная статистика ---`):

```python
def has_ever_paid(user_id: int) -> bool:
    """Возвращает True, если у юзера есть хотя бы один подтверждённый платёж."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM payments "
            "WHERE user_id = ? AND status = 'confirmed' LIMIT 1",
            (user_id,),
        ).fetchone()
    return row is not None
```

- [ ] **Step 2: Smoke-test**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && python3 -c "
from bot.services.user_limits import has_ever_paid
# Test against local DB (will be empty on dev, so both should be False)
print('admin has_ever_paid:', has_ever_paid(91892537))
print('random id has_ever_paid:', has_ever_paid(1234567890))
"
```
Expected: both print `False` on a fresh local DB, no crash.

- [ ] **Step 3: Commit**

```bash
git add bot/services/user_limits.py
git commit -m "Add has_ever_paid helper for watermark unlock check"
```

---

## Task 4: Extend keyboard with `has_watermarked` flag

**Files:**
- Modify: `bot/keyboards/inline.py`

- [ ] **Step 1: Read the current `get_restart_keyboard` signature**

Run:
```bash
grep -n "def get_restart_keyboard" "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai/bot/keyboards/inline.py"
```
Open the file, find `get_restart_keyboard`, note exact current signature.

- [ ] **Step 2: Add `has_watermarked` kwarg and conditional button row**

In `bot/keyboards/inline.py`, modify `get_restart_keyboard` to add `has_watermarked: bool = False` as the LAST kwarg. At the top of the button-building list, when `has_watermarked` is True, prepend a row with:

```python
InlineKeyboardButton(
    text="🔓 Получить без знака",
    callback_data="unlock_watermark",
)
```

Exact code (adapt to the existing structure — DO NOT rewrite unrelated parts; edit minimally):

```python
def get_restart_keyboard(
    has_last_photo: bool = False,
    has_credits: bool = True,
    has_watermarked: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    if has_watermarked:
        rows.append([
            InlineKeyboardButton(
                text="🔓 Получить без знака",
                callback_data="unlock_watermark",
            )
        ])
    # ... existing rows building ...
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

**Important:** read the existing implementation first and preserve the exact layout of existing rows. Only PREPEND the new row when `has_watermarked=True`.

- [ ] **Step 3: Syntax check**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && python3 -c "
from bot.keyboards.inline import get_restart_keyboard
kb = get_restart_keyboard(has_last_photo=True, has_credits=True, has_watermarked=True)
print('buttons:')
for row in kb.inline_keyboard:
    for b in row:
        print(f'  {b.text} -> {b.callback_data}')
"
```
Expected: first row shows `🔓 Получить без знака -> unlock_watermark`, then the regular restart/regenerate rows follow.

Also verify the default (no watermark) is unchanged:
```bash
python3 -c "
from bot.keyboards.inline import get_restart_keyboard
kb = get_restart_keyboard(has_last_photo=True, has_credits=True)
assert all(b.callback_data != 'unlock_watermark' for row in kb.inline_keyboard for b in row), 'unlock button leaked'
print('default unchanged, OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add bot/keyboards/inline.py
git commit -m "Add 'unlock watermark' button to restart keyboard when has_watermarked=True"
```

---

## Task 5: Create unlock handler + register router

**Files:**
- Create: `bot/handlers/watermark.py`
- Modify: `bot/main.py`

- [ ] **Step 1: Write the handler**

Create `bot/handlers/watermark.py`:

```python
"""Хендлер кнопки «🔓 Получить без знака» на водяном фото первой генерации."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from bot.keyboards.inline import get_buy_keyboard
from bot.services.user_limits import has_ever_paid
from bot.services.watermark import get_clean_copy

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(F.data == "unlock_watermark")
async def handle_unlock_watermark(callback: CallbackQuery) -> None:
    """По кнопке под WM-фото: либо отдать чистую версию, либо предложить купить."""
    await callback.answer()
    user_id = callback.from_user.id

    clean_bytes = get_clean_copy(user_id)
    if clean_bytes is None:
        await callback.message.answer("Чистая версия уже недоступна.")
        return

    if not has_ever_paid(user_id):
        await callback.message.answer(
            "Чтобы получить это фото без знака — купи любой пакет 👇",
            reply_markup=get_buy_keyboard(),
        )
        return

    try:
        await callback.message.answer_photo(
            photo=BufferedInputFile(
                clean_bytes, filename="studio_portrait.jpg"
            ),
            caption="🎁 Держи твоё первое фото без знака",
        )
        logger.info(f"Delivered clean photo to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send clean photo to user {user_id}: {e}")
        await callback.message.answer(
            "Не получилось отправить чистую версию. Попробуй ещё раз."
        )
```

- [ ] **Step 2: Register the router in `bot/main.py`**

Open `bot/main.py`. Locate the block where routers are registered (search for `dp.include_router` or `router` imports).

Add an import alongside existing handler imports:
```python
from bot.handlers import watermark as watermark_handler
```
(Match the existing import style — if the file uses `from bot.handlers.rating import router as rating_router`, use the same pattern.)

And register:
```python
dp.include_router(watermark_handler.router)
```
Place it near the other `include_router` calls. Exact position does not matter for correctness (aiogram routes by filter).

- [ ] **Step 3: Syntax check**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && python3 -c "
import ast
ast.parse(open('bot/handlers/watermark.py').read())
ast.parse(open('bot/main.py').read())
print('syntax ok')
"
```
Expected: `syntax ok`.

- [ ] **Step 4: Import-check the full chain**

```bash
python3 -c "
from bot.handlers.watermark import router
print('handler imports ok, router:', router)
"
```
Expected: no error, prints `handler imports ok, router: <aiogram.dispatcher.router.Router ...>`.

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/watermark.py bot/main.py
git commit -m "Add unlock_watermark callback handler and register router"
```

---

## Task 6: Hook watermark into first-generation branch in photo.py

**Files:**
- Modify: `bot/handlers/photo.py`

- [ ] **Step 1: Update imports at the top of `photo.py`**

Find the existing import block:
```python
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
```

Add `is_admin` to the list (alphabetical position):
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

Also add a new import below the existing imports:
```python
from bot.services.watermark import apply_watermark, save_clean_copy
```

- [ ] **Step 2: Insert watermark logic right after `result_image = await kie_client.download_image(result_url)`**

Find in `photo.py` (around line 104):

```python
        # Скачиваем результат
        result_image = await kie_client.download_image(result_url)

        # Удаляем сообщение о обработке
        await processing_msg.delete()
```

Insert **between** them:

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
```

**Important — there is already a line** `was_first_generation = get_generations_count(user_id) == 0` later in the function (around line 110). That line must be REMOVED since we now compute it earlier. Find and delete:

```python
        # Увеличиваем счётчик генераций
        was_first_generation = get_generations_count(user_id) == 0
        is_paid = not has_free_generations(user_id)
```

Replace with:
```python
        # Увеличиваем счётчик генераций
        is_paid = not has_free_generations(user_id)
```

The `was_first_generation` variable is already defined above now.

- [ ] **Step 3: Pass `has_watermarked` to the keyboard on the result message**

Find (around line 163):
```python
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

Update the `get_restart_keyboard` call to include `has_watermarked=watermarked`:
```python
            reply_markup=get_restart_keyboard(
                has_last_photo=True,
                has_credits=(remaining_after != 0),
                has_watermarked=watermarked,
            ),
```

- [ ] **Step 4: Syntax check**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && python3 -c "
import ast; ast.parse(open('bot/handlers/photo.py').read()); print('syntax ok')
"
```
Expected: `syntax ok`.

- [ ] **Step 5: Import-check**

```bash
python3 -c "from bot.handlers.photo import router; print('photo router ok')"
```
Expected: `photo router ok`, no import errors.

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/photo.py
git commit -m "Watermark first-gen result for non-admin users; pass has_watermarked to keyboard"
```

---

## Task 7: Local end-to-end smoke test

**Files:** none (manual verification)

**Pre-condition:** stop the production bot connection is NOT required — local bot uses the same BOT_TOKEN, so if both are running they'll conflict. **Option A (safer):** stop prod temporarily; **Option B:** register a second Telegram bot for dev. For this smoke test use Option A only briefly, or skip if Option B is set up. If you are unsure, prefer to skip step-7 local and go straight to prod deploy (Task 8) with rollback plan — deploy failure is cheap to revert via git + restart.

**If proceeding with local run:**

- [ ] **Step 1: Wipe local test data to simulate a fresh user (optional)**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && rm -f user_data.db && rm -rf clean/
```

- [ ] **Step 2: Start bot locally**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && source venv/bin/activate && python -m bot.main
```

Expected logs: `Bot started successfully!` then `Start polling`.

- [ ] **Step 3: Smoke-test from Telegram (admin account)**

From your admin Telegram account (ID 91892537): `/start` → gender → style → upload selfie. Wait for result.

Expected:
- Photo arrives **without** watermark.
- Keyboard has NO `🔓 Получить без знака` button.
- No file created at `clean/91892537.jpg` (check with `ls clean/`).

- [ ] **Step 4: Smoke-test from a non-admin account**

From a different Telegram account (ask a friend or use a test account): `/start` → gender → style → upload selfie.

Expected:
- Photo arrives **with** diagonal `ai-photobot.ru` watermark.
- Keyboard's first row shows `🔓 Получить без знака`.
- File created at `clean/<that_user_id>.jpg`.
- Rating request arrives as second message (existing behavior).

- [ ] **Step 5: Click `🔓 Получить без знака` without paying**

Expected: bot replies `Чтобы получить это фото без знака — купи любой пакет 👇` with the buy-keyboard. No clean photo sent.

- [ ] **Step 6: Simulate payment and retry unlock**

Stop the bot (Ctrl+C) briefly, run:

```bash
python3 -c "
from bot.services.user_limits import _get_conn
with _get_conn() as conn:
    conn.execute(\"\"\"
        INSERT INTO payments (user_id, package_id, credits, amount, status, confirmed_at)
        VALUES (?, 'test', 5, 14900, 'confirmed', datetime('now'))
    \"\"\", (<TEST_USER_ID>,))
print('payment marked confirmed')
"
```
(Replace `<TEST_USER_ID>` with the actual numeric ID.)

Restart the bot. From the test account, click `🔓 Получить без знака` again.

Expected: bot replies with a new photo message, caption `🎁 Держи твоё первое фото без знака`, photo is the **clean** (un-watermarked) version.

- [ ] **Step 7: Stop bot and clean up**

Ctrl+C to stop. Remove test data if wanted:
```bash
rm -f user_data.db && rm -rf clean/
```

- [ ] **Step 8: No commit (manual verification only)**

If any step fails, go back and fix. Do not commit broken code.

---

## Task 8: Deploy to production

**Files:** none new; deploying files changed in tasks 1-6.

- [ ] **Step 1: Install Pillow on prod (BEFORE stopping service)**

```bash
ssh kudinow@89.169.163.73 "sudo /opt/photoshoot_ai/venv/bin/pip install 'Pillow>=10.0.0'"
```
Expected: `Successfully installed pillow-X.Y.Z` (or already-satisfied message). No bot restart yet.

- [ ] **Step 2: Create the clean/ directory on prod with correct ownership**

```bash
ssh kudinow@89.169.163.73 "sudo mkdir -p /opt/photoshoot_ai/clean && sudo chown deploy:deploy /opt/photoshoot_ai/clean && ls -la /opt/photoshoot_ai/ | grep clean"
```
Expected: output shows `drwxr-xr-x ... deploy deploy ... clean`.

- [ ] **Step 3: Verify DejaVu font is available on prod**

```bash
ssh kudinow@89.169.163.73 "ls /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
```
Expected: the file is listed. If MISSING: install with `ssh kudinow@89.169.163.73 "sudo apt-get install -y fonts-dejavu-core"` and re-verify.

- [ ] **Step 4: Stop the bot service**

```bash
ssh kudinow@89.169.163.73 "sudo systemctl stop photoshoot_ai" && echo "stopped"
```

- [ ] **Step 5: SCP each changed file individually to /tmp**

```bash
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && \
scp requirements.txt kudinow@89.169.163.73:/tmp/requirements.txt && \
scp bot/services/watermark.py kudinow@89.169.163.73:/tmp/watermark_service.py && \
scp bot/services/user_limits.py kudinow@89.169.163.73:/tmp/user_limits.py && \
scp bot/keyboards/inline.py kudinow@89.169.163.73:/tmp/inline.py && \
scp bot/handlers/watermark.py kudinow@89.169.163.73:/tmp/watermark_handler.py && \
scp bot/handlers/photo.py kudinow@89.169.163.73:/tmp/photo.py && \
scp bot/main.py kudinow@89.169.163.73:/tmp/main.py && \
echo "scp done"
```
Expected: all transfers succeed, final `scp done`.

- [ ] **Step 6: sudo cp files into production paths + fix ownership**

```bash
ssh kudinow@89.169.163.73 "
sudo cp /tmp/requirements.txt /opt/photoshoot_ai/requirements.txt &&
sudo cp /tmp/watermark_service.py /opt/photoshoot_ai/bot/services/watermark.py &&
sudo cp /tmp/user_limits.py /opt/photoshoot_ai/bot/services/user_limits.py &&
sudo cp /tmp/inline.py /opt/photoshoot_ai/bot/keyboards/inline.py &&
sudo cp /tmp/watermark_handler.py /opt/photoshoot_ai/bot/handlers/watermark.py &&
sudo cp /tmp/photo.py /opt/photoshoot_ai/bot/handlers/photo.py &&
sudo cp /tmp/main.py /opt/photoshoot_ai/bot/main.py &&
sudo chown deploy:deploy \
  /opt/photoshoot_ai/requirements.txt \
  /opt/photoshoot_ai/bot/services/watermark.py \
  /opt/photoshoot_ai/bot/services/user_limits.py \
  /opt/photoshoot_ai/bot/keyboards/inline.py \
  /opt/photoshoot_ai/bot/handlers/watermark.py \
  /opt/photoshoot_ai/bot/handlers/photo.py \
  /opt/photoshoot_ai/bot/main.py &&
echo 'copied + chowned'
"
```
Expected: `copied + chowned`.

- [ ] **Step 7: Verify new code is in place on prod**

```bash
ssh kudinow@89.169.163.73 "sudo grep -l 'apply_watermark\|unlock_watermark\|has_ever_paid\|has_watermarked' /opt/photoshoot_ai/bot/services/watermark.py /opt/photoshoot_ai/bot/services/user_limits.py /opt/photoshoot_ai/bot/keyboards/inline.py /opt/photoshoot_ai/bot/handlers/watermark.py /opt/photoshoot_ai/bot/handlers/photo.py /opt/photoshoot_ai/bot/main.py"
```
Expected: at least five paths printed (files where the keywords appear).

- [ ] **Step 8: Start the service**

```bash
ssh kudinow@89.169.163.73 "sudo systemctl start photoshoot_ai && sleep 3 && sudo journalctl -u photoshoot_ai -n 30 --no-pager | grep -vE 'DEBUG|httpcore|httpx'"
```
Expected: log shows `Bot started successfully!` and `Start polling`. No Python import errors. No ModuleNotFoundError.

If there are errors: roll back with `sudo systemctl stop photoshoot_ai`, `git checkout HEAD~N -- <files>` locally, redeploy the previous version by repeating steps 5-7 with the old files, restart.

- [ ] **Step 9: Prod smoke test — admin**

From your admin Telegram account: do a fresh `/start` → gender → style → upload selfie.

Expected:
- Photo arrives **without** watermark.
- Keyboard has NO `🔓 Получить без знака` button.
- `ssh kudinow@89.169.163.73 "ls /opt/photoshoot_ai/clean/"` shows NO file for ADMIN_ID.

- [ ] **Step 10: Prod smoke test — new user**

Use a second Telegram account (or ask a friend): `/start` → gender → style → upload selfie.

Expected:
- Photo arrives **with** watermark.
- Keyboard shows `🔓 Получить без знака`.
- `ssh kudinow@89.169.163.73 "ls /opt/photoshoot_ai/clean/"` shows `<that_user_id>.jpg`.
- Rating request arrives as a separate message.

- [ ] **Step 11: Prod smoke test — unlock without payment**

Click `🔓 Получить без знака` from the test account.

Expected: `Чтобы получить это фото без знака — купи любой пакет 👇` + buy-keyboard.

- [ ] **Step 12: Prod smoke test — unlock after payment (optional)**

If you want a full end-to-end test of the paid path:
- Simulate payment via prod DB:
  ```bash
  ssh kudinow@89.169.163.73 "sudo /opt/photoshoot_ai/venv/bin/python3 -c \"
  from bot.services.user_limits import _get_conn
  with _get_conn() as conn:
      conn.execute('INSERT INTO payments (user_id, package_id, credits, amount, status, confirmed_at) VALUES (?, \\\"test\\\", 5, 14900, \\\"confirmed\\\", datetime(\\\"now\\\"))', (<TEST_USER_ID>,))
  print('payment inserted')
  \""
  ```
- Click `🔓 Получить без знака` again.
- Expected: clean photo arrives with caption `🎁 Держи твоё первое фото без знака`.
- Cleanup the fake payment:
  ```bash
  ssh kudinow@89.169.163.73 "sudo /opt/photoshoot_ai/venv/bin/python3 -c \"
  from bot.services.user_limits import _get_conn
  with _get_conn() as conn:
      conn.execute('DELETE FROM payments WHERE package_id = \\\"test\\\"')
  print('cleanup ok')
  \""
  ```

- [ ] **Step 13: No commit (deploy-only task, all code is already committed).**

---

## Task 9: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a new section after "Generation Rating"**

Open `CLAUDE.md`. Find the `## Generation Rating` section. Right before the next `## Landing Page` section, insert:

```markdown
## First-Generation Watermark

On every non-admin user's **first successful generation**, the result image is watermarked with a diagonal `ai-photobot.ru` text pattern. The clean (un-watermarked) version is saved to disk and can be retrieved via the new `🔓 Получить без знака` button under the photo, but only after the user has made at least one confirmed payment.

**Scope:**
- Watermark fires only when `was_first_generation and not is_admin(user_id)` in [bot/handlers/photo.py](bot/handlers/photo.py).
- Admin (`ADMIN_ID`) is bypassed — always clean, no unlock button.
- Referral-credit-based generations (#2+) are clean.
- Soft degradation: if `apply_watermark` raises, user gets the clean photo and NO unlock button (no breakage).

**Visual:** diagonal white `ai-photobot.ru` with black stroke, alpha ≈ 110/255, rotated -30°, repeated at ~22% of the diagonal step. Rendered by [bot/services/watermark.py](bot/services/watermark.py) using Pillow + DejaVuSans-Bold (Ubuntu) / Arial Bold (macOS dev) with fallback to default.

**Storage:** clean bytes at `/opt/photoshoot_ai/clean/{user_id}.jpg` (prod) or `<project>/clean/{user_id}.jpg` (local). No DB column — file existence is the source of truth. No cleanup cron (revisit if disk usage matters).

**Unlock flow ([bot/handlers/watermark.py](bot/handlers/watermark.py)):**
- User clicks `🔓 Получить без знака` (callback `unlock_watermark`).
- If no clean file → `Чистая версия уже недоступна.`
- Else if `has_ever_paid(user_id) == False` → upsell with `get_buy_keyboard()`.
- Else → send clean photo with caption `🎁 Держи твоё первое фото без знака`. Idempotent.

**Key code:** [bot/services/watermark.py](bot/services/watermark.py) (pure `apply_watermark`, `save_clean_copy`, `get_clean_copy`), [bot/services/user_limits.py](bot/services/user_limits.py) (`has_ever_paid`), [bot/keyboards/inline.py](bot/keyboards/inline.py) (`has_watermarked` kwarg on `get_restart_keyboard`).

**Not integrated into `start.py` regenerate branch** on purpose: `was_first_generation` in that branch is always `False` for non-admin users (photo.py increments before save_last_photo), so adding the hook there would be dead code.

**Design docs:** [docs/superpowers/specs/2026-04-23-first-generation-watermark-design.md](docs/superpowers/specs/2026-04-23-first-generation-watermark-design.md) and [docs/superpowers/plans/2026-04-23-first-generation-watermark.md](docs/superpowers/plans/2026-04-23-first-generation-watermark.md).
```

- [ ] **Step 2: Update the top-level "Core flow" bullet**

Find line 34 (`6. **After the user's first successful generation only**, bot sends a rating prompt...`). Right after it, add a new bullet 7:

```markdown
7. For non-admin users, the first-generation result image is watermarked (`ai-photobot.ru` diagonal); clean version is stored on disk and retrievable via the `🔓 Получить без знака` button only after any confirmed payment.
```

- [ ] **Step 3: Update the module table**

Find the `bot/services/user_limits.py` row in the module table (around line 50). Replace the description to include `has_ever_paid` and watermark:

```
| `bot/services/user_limits.py` | SQLite-based user limit tracking (1 free generation + paid credits, admin bypass), payment history, deep-link referral stats, user-to-user referral program, rating helpers, `has_ever_paid()` for watermark unlock, `init_db()` called at startup |
```

Add two new rows to the module table (after `bot/handlers/rating.py`):

```
| `bot/services/watermark.py` | Pillow-based `apply_watermark()` + `save_clean_copy()` / `get_clean_copy()` for first-generation watermarking |
| `bot/handlers/watermark.py` | `unlock_watermark` callback handler: serves clean version if user has confirmed payment, else shows buy-keyboard |
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "Document watermark feature in CLAUDE.md"
```

---

## Post-Implementation Checklist

After all tasks complete:

- [ ] Bot is running on prod (`sudo systemctl status photoshoot_ai` shows `active (running)`).
- [ ] Admin generation produces clean photo, no unlock button.
- [ ] Non-admin first generation produces watermarked photo with unlock button.
- [ ] Unlock without payment shows upsell.
- [ ] Unlock after payment returns clean version.
- [ ] `clean/` directory contains one file per non-admin first-gen user.
- [ ] `CLAUDE.md` reflects the new feature.
- [ ] All commits pushed (if working on a branch, create PR; if on `main`, push to origin).

## Rollback Plan

If a critical bug is found post-deploy:

```bash
# Local: revert commits
cd "/Users/kudinow/Yandex.Disk.localized/Cursor/1. Production/photoshoot_ai" && git log --oneline -10
git revert <commit-sha-range>

# Redeploy reverted files the same way as Task 8 (SCP → sudo cp → restart)
ssh kudinow@89.169.163.73 "sudo systemctl restart photoshoot_ai"
```

The `clean/` directory and any watermarked photos already sent to users are acceptable leftovers — no cleanup needed.

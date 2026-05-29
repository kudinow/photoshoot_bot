# First-Generation Watermark — Design Spec

> ⚠️ **SUPERSEDED (2026-05-29)** by [2026-05-29-watermark-unlock-50r-design.md](2026-05-29-watermark-unlock-50r-design.md). The unlock mechanic changed: instead of "buy any package + click button", the user pays a dedicated **50₽** and the bot auto-sends the clean photo. Watermark rendering/storage/scope below are still accurate; the unlock flow is not. Use the new spec.

**Date:** 2026-04-23
**Status:** Superseded
**Topic:** Monetization driver — watermark on first free generation, removable via payment + explicit button.

## Goal

Drive conversion to paid packages by putting a visible, non-trivially-removable watermark on every user's first (free) generation. After any successful payment, the user can retrieve the same photo without the watermark via an explicit button.

## Product Flow

**When watermark is applied:**
- Only on the user's **first successful generation** (the branch gated by `was_first_generation == True` in `bot/handlers/photo.py` and the regenerate branch of `bot/handlers/start.py`).
- Admin (`ADMIN_ID`) is bypassed — admin always receives a clean photo and does not see the unlock button.
- Referral credits (generation #2 and beyond) produce clean photos — no watermark on them.

**What the user sees:**

1. User uploads a selfie → normal processing message.
2. Bot replies with the generated result **with a diagonal repeating `ai-photobot.ru` watermark across the whole image**.
3. The keyboard under that photo includes a new row with **`🔓 Получить без знака`** (callback_data=`unlock_watermark`) above the existing `Сгенерировать заново` / `Новое фото` buttons.
4. Rating-request message is sent afterwards, identical to current behavior.

**Button behavior (`unlock_watermark`):**
- If the clean file for this user does not exist on disk → reply `Чистая версия уже недоступна.` (edge case, should be rare).
- Else if `has_ever_paid(user_id) == False` → reply `Чтобы получить это фото без знака — купи любой пакет 👇` + `get_buy_keyboard()`.
- Else → reply with a new photo message: `🎁 Держи твоё первое фото без знака` with the clean bytes from disk.
- Idempotent: the file is not deleted on success; repeated clicks keep working.

**What the payment flow does:** nothing automatic on `confirm_payment`. The user must explicitly click the unlock button on the old watermarked message. (Deliberately no auto-send — per user choice.)

## Technical Design

### Dependencies

Add `Pillow>=10.0.0` to `requirements.txt`. Install on prod via `sudo /opt/photoshoot_ai/venv/bin/pip install Pillow` **before** restarting the service.

### Watermark Module (`bot/services/watermark.py`)

New module exposing a single pure function:

```python
def apply_watermark(image_bytes: bytes) -> bytes:
    """Apply diagonal 'ai-photobot.ru' watermark, return JPEG bytes."""
```

Implementation:
- Open image via `PIL.Image.open(io.BytesIO(image_bytes))`, convert to `RGBA`.
- Create a transparent `RGBA` overlay.
- Draw `ai-photobot.ru` repeated across the canvas with ~30° rotation, semi-transparent white (alpha ≈ 110/255) with a thin black stroke for contrast on any background.
- Font: `DejaVuSans-Bold.ttf` from the system (`/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`), fallback to `ImageFont.load_default()` if missing.
- Font size: adaptive, `int(min(w, h) * 0.035)`.
- Repeat step: ~25% of diagonal, creating a grid of overlapping text.
- Alpha-composite overlay onto base, flatten to RGB, save as JPEG quality 92.
- Return bytes.

Error handling: the function itself raises on malformed input. Callers wrap in `try/except` and fall back to sending the original clean bytes (soft degradation; a broken watermark must not break the generation pipeline).

### Hook Point in `photo.py`

Right after `result_image = await kie_client.download_image(result_url)`:

```python
from bot.services.watermark import apply_watermark, save_clean_copy

display_image = result_image
if was_first_generation and not is_admin(user_id):
    try:
        save_clean_copy(user_id, result_image)
        display_image = apply_watermark(result_image)
    except Exception as e:
        logger.error(f"Watermark failed for user {user_id}: {e}")
        # Soft degradation: send clean photo, no unlock button
        display_image = result_image
```

Then use `display_image` in `BufferedInputFile` and set `has_watermarked=True` on the keyboard when `display_image != result_image` (i.e., watermark was successfully applied).

### Clean-Copy Storage

- Path: `/opt/photoshoot_ai/clean/{user_id}.jpg` on prod; `<project>/clean/{user_id}.jpg` locally.
- Helper in `bot/services/watermark.py`:
  - `save_clean_copy(user_id: int, image_bytes: bytes) -> None` — writes bytes atomically (write to `.tmp`, rename).
  - `get_clean_copy(user_id: int) -> bytes | None` — reads or returns None.
- Overwriting allowed (future regeneration before payment).
- No cleanup cron in this iteration. At 200 KB/file, even 10k users = 2 GB; reassess then.
- No DB column — file existence is the source of truth.

### `has_ever_paid` Helper

New function in `bot/services/user_limits.py`:

```python
def has_ever_paid(user_id: int) -> bool:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM payments WHERE user_id = ? AND status = 'confirmed' LIMIT 1",
            (user_id,),
        ).fetchone()
    return row is not None
```

### Keyboard Change (`bot/keyboards/inline.py`)

Add optional `has_watermarked: bool = False` parameter to `get_restart_keyboard`. When True, prepend a row with:

```
[🔓 Получить без знака]   (callback_data="unlock_watermark")
```

above the existing buttons. All existing call sites remain unchanged (default `False`).

### New Handler

Create `bot/handlers/watermark.py` (by analogy with `rating.py`):

```python
@router.callback_query(F.data == "unlock_watermark")
async def handle_unlock_watermark(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    await callback.answer()

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

    await callback.message.answer_photo(
        photo=BufferedInputFile(clean_bytes, filename="studio_portrait.jpg"),
        caption="🎁 Держи твоё первое фото без знака",
    )
```

Register the router in `bot/main.py`.

## Data Model

**No schema changes.** The `payments` table already supports `has_ever_paid` (status='confirmed' check). The `clean/` directory on disk is the only new persistence.

## Edge Cases

| Scenario | Handling |
|---|---|
| Admin (`ADMIN_ID`) first generation | No watermark, no unlock button, no clean file saved. |
| User clicks unlock twice | Both clicks send the photo. Idempotent. |
| Watermark generation raises exception | Logged at ERROR; user still gets clean result image, no unlock button shown. |
| User regenerates before paying | Generation #2 is clean, no unlock button in #2's keyboard. The `clean/{user_id}.jpg` file from #1 remains and can still be unlocked from the old #1 message after payment. |
| User pays but never clicks button | No-op — we never auto-send. User can return to any old message with an unlock button. |
| `clean/{user_id}.jpg` missing at click time | Reply `Чистая версия уже недоступна.` (minimal fallback, rare). |
| Users created before this feature | Never triggered — their `was_first_generation` is permanently past. No retroactive watermarking. |

## Testing Plan

Local/manual:
1. **Admin smoke test** — admin account does first gen → receives clean photo, no unlock button. Verify `clean/` is empty.
2. **Unpaid user** — fresh test account does first gen → receives watermarked photo + unlock button. Click unlock → receive buy-keyboard upsell. Do regen #2 (via referral credit from admin or manually) → receive clean photo, no unlock button.
3. **Pay-and-unlock** — test account pays via a confirmed test payment (mark via `confirm_payment` direct call if needed). Click unlock on the old message → receive clean version with caption.
4. **Soft degradation** — temporarily break `apply_watermark` (e.g., missing font). Verify user still gets clean photo and no unlock button.

## Out of Scope (YAGNI)

- Cleanup cron for the `clean/` directory.
- Auto-send of the clean version on `confirm_payment` (user chose button-only).
- Retroactive watermarking of existing generations.
- Analytics: no new columns tracking "unlock clicks" — rating/payment tables are enough signal for now.
- Watermark variants, A/B tests, per-user watermark text.

## Documentation Updates

Update `CLAUDE.md` with a new section **"First-Generation Watermark"** covering:
- When watermark fires (first successful generation, non-admin).
- Text/style of the watermark.
- Unlock button mechanic (button, not auto-send).
- Storage path `/opt/photoshoot_ai/clean/{user_id}.jpg`.
- `has_ever_paid()` helper.
- New module `bot/services/watermark.py` and handler `bot/handlers/watermark.py`.

## Open Questions

None — all clarified during brainstorming.

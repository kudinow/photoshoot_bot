# First-Generation Watermark + 50₽ Unlock — Design Spec

**Date:** 2026-05-29
**Status:** Approved, pending implementation plan
**Topic:** Monetization driver — watermark on the first free generation, removable via a dedicated **50₽ micro-payment** that auto-delivers the clean photo.

**Supersedes:** [2026-04-23-first-generation-watermark-design.md](2026-04-23-first-generation-watermark-design.md). The watermark rendering, storage, and scope are unchanged from that spec; the **unlock mechanic is replaced**: instead of "buy any package, then click a button", the user pays a dedicated 50₽ and the bot auto-sends the clean photo.

## Goal

Put a visible, non-trivially-removable watermark on every non-admin user's first (free) generation. Offer to remove it for **50₽** via an explicit button under the photo. After the 50₽ payment confirms, the bot **automatically** sends the same photo without the watermark. The 50₽ buys only the clean version of that one photo — **no generation credits**.

## Product Flow

**When the watermark is applied:**
- Only on the user's **first successful generation** (`was_first_generation == True` in `bot/handlers/photo.py`).
- Admin (`ADMIN_ID`) is bypassed — always receives a clean photo, no unlock button, no clean-copy saved.
- Referral-credit generations (#2 and beyond) are clean — no watermark.

**What the user sees:**

1. User uploads a selfie → normal processing message.
2. Bot replies with the result **with a diagonal repeating `ai-photobot.ru` watermark across the whole image**, and an upsell caption:
   > Готово! Но фото пока с водяным знаком. Чистую версию без знака можно забрать за 50₽ 👇
3. The keyboard under that photo has a new top row **`🔓 Убрать знак — 50₽`** (callback_data=`unlock_watermark`), above the existing `🔄 Сгенерировать заново` / `✨ Создать с новым фото` buttons.
4. Rating-request message is sent afterwards, identical to current behavior.

**Button behavior (`unlock_watermark`):**
- If the clean file for this user does not exist on disk → reply `Чистая версия больше недоступна.` (rare edge case).
- Else if the user **already has a confirmed `watermark_unlock` payment** → re-send the clean photo immediately (idempotent, free — handles repeated clicks on the old message after paying).
- Else → create a 50₽ YooKassa payment, send the payment-link keyboard (`Перейти к оплате` / `Проверить оплату` / `Отмена`), and start background polling — exactly like a normal package purchase.

**Delivery after payment (the key new piece):**
- Both the background poll (`_poll_payment`) and the manual `Проверить оплату` handler (`check_payment_status`), on `succeeded`, branch on `pkg.id == "watermark_unlock"`:
  - **Unlock payment:** do **not** show "начислено N генераций". Instead, send the clean photo from `get_clean_copy(user_id)` with caption `🎁 Готово! Вот фото без водяного знака.` If the clean file is missing, send a short fallback text. Notify admin with a short "куплено снятие знака за 50₽" message.
  - **Regular package:** unchanged behavior (credits added + "начислено N генераций").

## Technical Design

### Dependencies

Add `Pillow>=10.0.0` to `requirements.txt`. Install on prod via `sudo /opt/photoshoot_ai/venv/bin/pip install 'Pillow>=10.0.0'` **before** restarting the service.

### Watermark Module (`bot/services/watermark.py`)

New module, pure functions (unchanged from the 2026-04-23 spec):

```python
def apply_watermark(image_bytes: bytes) -> bytes: ...   # diagonal ai-photobot.ru, returns JPEG
def save_clean_copy(user_id: int, image_bytes: bytes) -> None: ...   # atomic write
def get_clean_copy(user_id: int) -> bytes | None: ...
```

Rendering: open via `PIL.Image.open(io.BytesIO(...))` → RGBA; transparent overlay; draw `ai-photobot.ru` repeated on a large tile, rotate -30°, paste centered; semi-transparent white (alpha ≈ 110) with black stroke; font `DejaVuSans-Bold.ttf` (Ubuntu) / `Arial Bold` (macOS dev) with `ImageFont.load_default()` fallback; font size `max(18, int(min(w, h) * 0.035))`; step ≈ 22% of diagonal; alpha-composite, flatten to RGB, JPEG quality 92.

Storage: `/opt/photoshoot_ai/clean/{user_id}.jpg` (prod) or `<project>/clean/{user_id}.jpg` (local), chosen by which parent dir exists. Atomic write (`.tmp` + `os.replace`). Overwriting allowed. No cleanup cron this iteration. No DB column — file existence is the source of truth.

Error handling: `apply_watermark` raises on malformed input; the caller in `photo.py` wraps in `try/except` and falls back to sending the original clean bytes with no unlock button (soft degradation — a broken watermark must never break the generation pipeline).

### Hook Point in `photo.py`

Right after `result_image = await kie_client.download_image(result_url)`, compute `was_first_generation` (must be read **before** `increment_generations`) and apply the watermark:

```python
was_first_generation = get_generations_count(user_id) == 0
watermarked = False
if was_first_generation and not is_admin(user_id):
    try:
        save_clean_copy(user_id, result_image)
        result_image = apply_watermark(result_image)
        watermarked = True
    except Exception as e:
        logger.error(f"Watermark failed for user {user_id}: {e}")
        # soft degradation: send clean photo, no unlock button
```

The existing later line `was_first_generation = get_generations_count(user_id) == 0` (currently ~line 112) is **moved up** to this hook (it must run before `increment_generations`), and the duplicate is removed.

The result message caption and keyboard branch on `watermarked`:
- `watermarked == True` → upsell caption (see Product Flow §2) + `get_restart_keyboard(..., has_watermarked=True)`.
- `watermarked == False` → existing caption + keyboard unchanged.

### Config — the 50₽ Unlock "Package" (`bot/config.py`)

```python
WATERMARK_UNLOCK_ID = "watermark_unlock"

WATERMARK_UNLOCK = CreditPackage(
    id=WATERMARK_UNLOCK_ID,
    credits=0,
    price_rub=50,
    price_kopecks=5000,
    label="Фото без водяного знака — 50₽",
)
```

- **Not** added to `CREDIT_PACKAGES` (so it never appears in the buy menu / `get_packages_keyboard`).
- `get_package_by_id()` is extended to also resolve `WATERMARK_UNLOCK` by its id, so the existing payment pipeline (`confirm_buy`, `_poll_payment`, `check_payment_status`) finds it via `pkg`.
- `confirm_payment` calls `add_paid_credits(user_id, 0)` — verified harmless no-op (`paid_credits + 0`). No special-casing needed in `confirm_payment`.

### Keyboard Change (`bot/keyboards/inline.py`)

Add `has_watermarked: bool = False` as the last kwarg of `get_restart_keyboard`. When `True`, prepend a row:

```python
InlineKeyboardButton(text="🔓 Убрать знак — 50₽", callback_data="unlock_watermark")
```

All existing call sites are unaffected (default `False`).

### New Handler (`bot/handlers/watermark.py`)

```python
@router.callback_query(F.data == "unlock_watermark")
async def handle_unlock_watermark(callback: CallbackQuery, bot: Bot) -> None:
    user_id = callback.from_user.id
    await callback.answer()

    clean_bytes = get_clean_copy(user_id)
    if clean_bytes is None:
        await callback.message.answer("Чистая версия больше недоступна.")
        return

    # Уже оплачено — отдаём бесплатно (идемпотентно)
    if has_unlocked_watermark(user_id):
        await callback.message.answer_photo(
            photo=BufferedInputFile(clean_bytes, filename="studio_portrait.jpg"),
            caption="🎁 Готово! Вот фото без водяного знака.",
        )
        return

    # Создаём 50₽-платёж и стартуем polling (как confirm_buy)
    pkg = get_package_by_id(WATERMARK_UNLOCK_ID)
    internal_id = create_payment(user_id, pkg.id, pkg.credits, pkg.price_kopecks)
    try:
        yk_id, url = await create_yookassa_payment(
            amount_kopecks=pkg.price_kopecks,
            description="Фото без водяного знака",
            user_id=user_id, package_id=pkg.id, internal_payment_id=internal_id,
        )
    except Exception as e:
        logger.error(...); cancel_payment(internal_id)
        await callback.message.answer("❌ Не удалось создать платёж. Попробуй позже.")
        return
    update_payment_provider_id(internal_id, yk_id)
    await callback.message.answer(
        "💳 Оплата 50₽ за фото без водяного знака.\n"
        "Нажми «Перейти к оплате», затем «Проверить оплату».",
        reply_markup=get_payment_url_keyboard(url, internal_id),
    )
    asyncio.create_task(_poll_payment(bot, internal_id, yk_id, user_id, pkg))
```

`_poll_payment` is imported from `bot.handlers.payment` (it already lives there). Register `watermark.router` in `bot/main.py`.

### Delivery Branch in `payment.py`

Factor a small helper so both success paths share it:

```python
async def _deliver_after_payment(bot, user_id, pkg, edit_target=None):
    if pkg.id == WATERMARK_UNLOCK_ID:
        clean = get_clean_copy(user_id)
        if clean:
            await bot.send_photo(user_id, BufferedInputFile(clean, "studio_portrait.jpg"),
                                 caption="🎁 Готово! Вот фото без водяного знака.")
        else:
            await bot.send_message(user_id, "Оплата прошла, но чистая версия не найдена. Напиши в поддержку.")
    else:
        # existing "начислено N генераций" message + after-payment keyboard
        ...
```

Both `_poll_payment` (success branch) and `check_payment_status` (succeeded branch) call this after `confirm_payment(...)`. Admin notification (`_notify_admin_payment`) gets a branch: for unlock → "куплено снятие знака за 50₽"; for packages → unchanged.

### `has_unlocked_watermark` Helper (`bot/services/user_limits.py`)

```python
def has_unlocked_watermark(user_id: int) -> bool:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM payments "
            "WHERE user_id = ? AND package_id = ? AND status = 'confirmed' LIMIT 1",
            (user_id, "watermark_unlock"),
        ).fetchone()
    return row is not None
```

## Data Model

**No schema changes.** The unlock is a row in the existing `payments` table with `package_id='watermark_unlock'`, `credits=0`, `amount=5000`. The `clean/` directory on disk is the only new persistence.

## Edge Cases

| Scenario | Handling |
|---|---|
| Admin first generation | No watermark, no unlock button, no clean file saved. |
| Watermark generation raises | Logged ERROR; user gets clean result, no unlock button. |
| User regenerates before paying | Gen #2 is clean, no unlock button. The `clean/{user_id}.jpg` from #1 remains; the #1 message's button still works. |
| User clicks `🔓 Убрать знак` after already paying | `has_unlocked_watermark` true → clean photo re-sent free. No second charge. |
| User clicks the button, pays, returns | Poll or manual check detects success → clean photo auto-sent. |
| 50₽ paid but `clean/{user_id}.jpg` missing | Fallback message: "Оплата прошла, но чистая версия не найдена. Напиши в поддержку." |
| `unlock_watermark` clicked, clean file missing, never paid | `Чистая версия больше недоступна.` |
| Users created before this feature | Never triggered — `was_first_generation` permanently past. No retroactive watermarking. |
| 50₽ payment times out / canceled | Same as a normal package: poll cancels it; no clean photo sent. |

## Testing Plan

Local/manual (project has no pytest suite):
1. **`apply_watermark` script** — run on a sample JPG, open output, confirm diagonal `ai-photobot.ru` is visible and readable on light/dark regions, face still recognizable.
2. **Round-trip** — `save_clean_copy` / `get_clean_copy` returns identical bytes.
3. **Admin smoke** — admin first gen → clean photo, no unlock button, no `clean/<admin>.jpg`.
4. **New user smoke** — test account first gen → watermarked photo + upsell caption + `🔓 Убрать знак — 50₽` button; `clean/<id>.jpg` exists; rating request follows.
5. **Pay-and-deliver** — click button → YooKassa link; complete a test payment (or mark confirmed in DB); confirm bot auto-sends clean photo with `🎁` caption and admin gets the short notice.
6. **Idempotent re-click** — after paying, click the old button again → clean photo re-sent, no new payment created.
7. **Soft degradation** — break `apply_watermark` (e.g. missing font path) → user still gets clean photo, no unlock button.

## Out of Scope (YAGNI)

- Cleanup cron for `clean/`.
- Granting any generation credits with the 50₽ unlock (explicitly 0 credits).
- Retroactive watermarking of existing users.
- Watermark variants / A-B tests / per-user text.
- Unlock analytics columns — the `payments` rows (`package_id='watermark_unlock'`) are enough signal.
- `start.py` regenerate hook (dead code for non-admin first-gen).

## Documentation Updates

Add a **"First-Generation Watermark + 50₽ Unlock"** section to `CLAUDE.md`: when the watermark fires, the upsell caption + button, the 50₽ `watermark_unlock` payment product (credits=0, not in the buy menu), auto-delivery on confirmation, idempotent re-delivery, storage path, `has_unlocked_watermark()` helper, new module/handler. Update the Core flow bullets and the module table.

## Open Questions

None — all clarified during brainstorming (2026-05-29).

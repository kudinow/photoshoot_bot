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

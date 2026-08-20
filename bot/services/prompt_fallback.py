"""Локальная сборка промпта для kie.ai — без обращения к LLM.

Аварийный фолбэк на случай, когда OpenRouter недоступен с сервера
(Cloudflare отдаёт 403 на российские IP). Собирает промпт по той же
структуре, что и «Universal Prompt Template» из bot/config.py,
случайно комбинируя одежду, цвета, фон, свет и аксессуары.

Модуль намеренно не импортирует bot.config — он самодостаточен и
не требует .env, чтобы его можно было прогонять тестами отдельно.
"""

from __future__ import annotations

import random

GENDERS: tuple[str, ...] = ("male", "female")
STYLES: tuple[str, ...] = ("casual", "business", "creative")

_DEFAULT_GENDER = "male"
_DEFAULT_STYLE = "casual"

_SUBJECT: dict[str, str] = {"male": "man", "female": "woman"}

_AGES: tuple[str, ...] = (
    "in his/her mid 20s",
    "in his/her late 20s",
    "in his/her early 30s",
    "in his/her mid 30s",
    "in his/her late 30s",
    "in his/her early 40s",
)

# Одежда: (gender, style) -> варианты предметов
_GARMENTS: dict[tuple[str, str], tuple[str, ...]] = {
    ("male", "casual"): (
        "crew neck knit sweater",
        "fine-knit v-neck sweater",
        "long sleeve henley",
        "quarter-zip knit pullover",
        "classic cotton t-shirt",
        "Oxford button-up shirt",
        "chambray button-up shirt with sleeves casually rolled",
        "muted flannel shirt",
        "linen button-up shirt",
        "minimal polo shirt",
        "waffle-knit thermal top",
        "denim jacket over a plain tee",
        "cardigan over a plain crew tee",
    ),
    ("female", "casual"): (
        "relaxed crew neck knit sweater",
        "oversized v-neck sweater",
        "soft open-front cardigan over a tee",
        "classic cotton t-shirt",
        "scoop neck cotton top",
        "chambray denim shirt with sleeves rolled",
        "relaxed linen blouse",
        "long sleeve henley top",
        "soft jersey wrap top",
        "ribbed knit top",
        "casual Oxford button-down shirt",
        "lightweight waffle-knit pullover",
    ),
    ("male", "business"): (
        "slim-fit single-breasted suit with a crisp dress shirt, collar open",
        "two-button tailored suit with a dress shirt and a silk tie",
        "single-breasted blazer over a dress shirt, no tie",
        "structured sport coat over a poplin dress shirt",
        "tailored blazer with a neatly folded pocket square",
        "modern-cut suit with a slim knit tie",
        "French-cuff dress shirt with subtle cufflinks, no jacket",
        "worsted wool blazer over a fine merino mock-neck",
    ),
    ("female", "business"): (
        "tailored single-breasted blazer over a silk blouse",
        "double-breasted structured blazer over a fine knit shell",
        "collarless structured jacket over a satin top",
        "fitted blazer over a classic cotton dress shirt",
        "bow-neck silk blouse under a tailored jacket",
        "fine-knit turtleneck under a structured blazer",
        "minimal sheath dress with clean tailoring",
        "lightweight tweed jacket over a crepe top",
    ),
    ("male", "creative"): (
        "fitted merino turtleneck",
        "ribbed mock-neck sweater",
        "chunky cable knit sweater",
        "deconstructed drop-shoulder knit",
        "Nehru-collar shirt with clean modern lines",
        "textured long sleeve knit polo",
        "structured heavy cotton overshirt",
        "minimal bomber jacket with no logos",
        "turtleneck layered under an unstructured blazer",
        "grandad-collar shirt with raw-edge detailing",
    ),
    ("female", "creative"): (
        "oversized cashmere turtleneck with sculptural draping",
        "fine ribbed mock-neck top",
        "asymmetric one-shoulder silk top",
        "draped cowl-neck blouse",
        "slouchy deconstructed oversized sweater",
        "open-weave statement knit",
        "longline knit vest layered over a fine shirt",
        "cocoon-shaped architectural jacket",
        "matte leather top with minimalist clean lines",
        "mixed-texture layered look, knit over silk",
    ),
}

# Цвета: (gender, style) -> палитра
_COLORS: dict[tuple[str, str], tuple[str, ...]] = {
    ("male", "casual"): (
        "oatmeal", "warm beige", "cream", "sand", "warm grey", "charcoal",
        "off-white", "olive", "forest green", "moss", "rust", "clay",
        "camel", "navy", "slate blue", "dusty teal", "burgundy", "sage",
        "warm taupe", "burnt orange",
    ),
    ("female", "casual"): (
        "cream", "ivory", "oatmeal", "sand", "warm grey", "soft white",
        "olive", "sage green", "terracotta", "dusty rose", "powder blue",
        "sky blue", "lavender", "mint", "peach", "muted mustard",
        "soft burgundy", "mauve", "camel", "clay",
    ),
    ("male", "business"): (
        "charcoal", "navy", "dark grey", "midnight blue", "slate",
        "graphite", "deep espresso", "steel grey",
    ),
    ("female", "business"): (
        "navy", "charcoal", "dark grey", "midnight blue", "ivory",
        "soft blush", "burgundy", "deep wine", "camel", "cognac",
        "slate blue", "deep teal", "muted plum", "steel grey",
    ),
    ("male", "creative"): (
        "all-black", "tonal charcoal", "deep forest green", "midnight navy",
        "espresso", "oxblood", "deep plum", "cognac", "clay",
        "warm chocolate", "toffee", "ice grey", "slate", "graphite",
        "pewter", "burnt orange", "deep mustard", "dark teal", "muted olive",
    ),
    ("female", "creative"): (
        "all-black", "all-cream", "deep emerald", "sapphire", "burnt sienna",
        "oxblood", "plum", "cognac", "terracotta", "warm chocolate",
        "toffee", "amber", "ice blue", "silvery grey", "stone", "pewter",
        "mustard yellow", "deep coral", "forest green",
    ),
}

# Аксессуары: (gender, style) -> варианты
_ACCESSORIES: dict[tuple[str, str], tuple[str, ...]] = {
    ("male", "casual"): (
        "A simple watch on the wrist.",
        "A minimal matte ring.",
        "A thin chain barely visible at the collar.",
        "No accessories, clean and unadorned.",
    ),
    ("female", "casual"): (
        "Small gold hoop earrings.",
        "Delicate silver stud earrings.",
        "A dainty pendant necklace.",
        "A thin chain necklace and minimal rings.",
    ),
    ("male", "business"): (
        "A classic leather-strap watch.",
        "A metal-bracelet dress watch.",
        "Minimal silver cufflinks.",
        "A neatly folded white pocket square.",
    ),
    ("female", "business"): (
        "Small pearl stud earrings.",
        "Refined pearl drop earrings.",
        "Small gold geometric earrings.",
        "A thin gold chain necklace.",
        "A structured minimal watch.",
    ),
    ("male", "creative"): (
        "A modern architectural watch with an unusual dial.",
        "A matte signet ring.",
        "A thin leather cord necklace.",
        "A woven leather bracelet.",
    ),
    ("female", "creative"): (
        "Architectural geometric earrings.",
        "Sculptural gold earrings.",
        "Layered thin necklaces in mixed metals.",
        "Geometric ceramic earrings.",
        "A statement cuff bracelet and stacked rings.",
    ),
}

# Выражение лица: style -> варианты
_EXPRESSIONS: dict[str, tuple[str, ...]] = {
    "casual": (
        "a natural warm smile",
        "a relaxed friendly expression",
        "calm approachable confidence",
        "a gentle authentic smile",
    ),
    "business": (
        "a composed confident expression",
        "professional warmth and a slight assured smile",
        "quiet authority and a neutral steady look",
        "assured professional demeanour",
    ),
    "creative": (
        "thoughtful intensity",
        "calm creative confidence",
        "intriguing composure with artistic gravitas",
        "intellectual calm and a subtle edge",
    ),
}

# Свет: style -> варианты
_LIGHTING: dict[str, tuple[str, ...]] = {
    "casual": (
        "Soft studio lighting with a large softbox key and gentle fill",
        "Even three-point studio lighting with a subtle rim light",
        "Bright airy studio setup with soft shadow falloff",
    ),
    "business": (
        "Classic three-point studio lighting with a soft key and subtle rim light",
        "Polished corporate lighting, soft key with controlled fill",
        "Broad softbox key with a delicate hair light for separation",
    ),
    "creative": (
        "Dramatic directional key light with deep controlled shadows",
        "Moody studio lighting with strong side key and minimal fill",
        "Editorial lighting with sculpted contrast and crisp catchlights",
    ),
}

_BACKDROPS: dict[str, tuple[str, ...]] = {
    "casual": (
        "neutral warm grey", "pale beige", "soft grey", "warm taupe",
        "off-white", "light sand",
    ),
    "business": (
        "neutral grey", "cream", "soft grey", "cool light grey",
        "pale slate", "muted charcoal",
    ),
    "creative": (
        "dark charcoal", "deep grey", "stone-coloured", "warm grey",
        "muted graphite", "matte black",
    ),
}

_CAMERAS: tuple[str, ...] = (
    "Canon EOS R5", "Sony A7 IV", "Nikon Z8", "Canon EOS R6 Mark II",
)

_LENSES: tuple[str, ...] = (
    "85mm f/1.4 lens at f/2.8",
    "85mm f/1.8 lens at f/2.5",
    "105mm f/2.8 lens at f/3.2",
    "70-200mm lens at 135mm, f/4",
)

_FRAMINGS: tuple[str, ...] = (
    "chest-up framing",
    "head-and-shoulders framing",
    "classic headshot framing with breathing room above the head",
)

_PHOTOREALISM_TAIL = (
    "Photorealistic detail: visible skin pores and natural micro-texture, "
    "fine lines and subtle natural redness near the nose and cheeks, "
    "individual hair strands and natural flyaways at the edges, "
    "detailed iris texture with wet specular catchlights from the studio lights, "
    "realistic fabric weave with natural wrinkles and gravity-driven draping, "
    "soft shadow transitions and gentle ambient occlusion in skin folds, "
    "very subtle ISO 200 sensor grain, natural lens vignetting, "
    "professional color science and micro-contrast. "
    "Tack sharp on the eyes, shallow depth of field with soft background "
    "separation. Contemporary professional headshot photography, natural "
    "color grading, indistinguishable from a real RAW photograph — "
    "no CGI, no 3D render, no illustration, no airbrushed plastic skin."
)


def _normalize(gender: str, style: str) -> tuple[str, str]:
    safe_gender = gender if gender in GENDERS else _DEFAULT_GENDER
    safe_style = style if style in STYLES else _DEFAULT_STYLE
    return safe_gender, safe_style


def _age_for(gender: str) -> str:
    pronoun = "his" if gender == "male" else "her"
    return random.choice(_AGES).replace("his/her", pronoun)


def build_local_prompt(gender: str, style: str) -> str:
    """Собирает промпт локально, без обращения к LLM.

    Args:
        gender: "male" или "female" (неизвестные значения → male)
        style: "casual", "business" или "creative" (неизвестные → casual)

    Returns:
        Готовый промпт для kie.ai (без PROMPT_CRITICAL_SUFFIX).
    """
    safe_gender, safe_style = _normalize(gender, style)
    key = (safe_gender, safe_style)

    subject = _SUBJECT[safe_gender]
    age = _age_for(safe_gender)
    garment = random.choice(_GARMENTS[key])
    color = random.choice(_COLORS[key])
    accessory = random.choice(_ACCESSORIES[key])
    expression = random.choice(_EXPRESSIONS[safe_style])
    lighting = random.choice(_LIGHTING[safe_style])
    backdrop = random.choice(_BACKDROPS[safe_style])
    camera = random.choice(_CAMERAS)
    lens = random.choice(_LENSES)
    framing = random.choice(_FRAMINGS)

    return (
        f"RAW photo, 8K UHD, DSLR, professional studio portrait of a "
        f"{subject} {age} wearing a {color} {garment}. "
        f"Direct eye contact with the camera, {expression}. "
        f"{lighting}, even illumination on the face with subtle dimension. "
        f"{accessory} "
        f"Seamless {backdrop} studio backdrop, softly blurred. "
        f"Shot on a {camera} with an {lens}, {framing}. "
        f"{_PHOTOREALISM_TAIL}"
    )

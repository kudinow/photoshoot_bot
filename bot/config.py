from __future__ import annotations

from dataclasses import dataclass

from pydantic_settings import BaseSettings
from yookassa import Configuration as YooKassaConfiguration


class Settings(BaseSettings):
    # Telegram
    bot_token: str

    # kie.ai
    kie_api_key: str
    kie_api_url: str = "https://kie.ai"

    # OpenRouter (замена OpenAI для работы из РФ)
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # YooKassa
    yookassa_shop_id: str
    yookassa_secret_key: str
    yookassa_return_url: str = "https://t.me/photoshoot_generator_bot"

    # Settings
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Инициализация YooKassa SDK
YooKassaConfiguration.account_id = settings.yookassa_shop_id
YooKassaConfiguration.secret_key = settings.yookassa_secret_key


# --- Пакеты генераций для покупки ---


@dataclass(frozen=True)
class CreditPackage:
    """Пакет генераций для покупки"""

    id: str
    credits: int
    price_rub: int
    price_kopecks: int
    label: str


CREDIT_PACKAGES: tuple[CreditPackage, ...] = (
    CreditPackage(
        id="pack_5",
        credits=5,
        price_rub=149,
        price_kopecks=14900,
        label="5 генераций — 149 ₽",
    ),
    CreditPackage(
        id="pack_15",
        credits=15,
        price_rub=349,
        price_kopecks=34900,
        label="15 генераций — 349 ₽",
    ),
    CreditPackage(
        id="pack_50",
        credits=50,
        price_rub=899,
        price_kopecks=89900,
        label="50 генераций — 899 ₽",
    ),
)


def get_package_by_id(package_id: str) -> CreditPackage | None:
    """Возвращает пакет по его ID"""
    for pkg in CREDIT_PACKAGES:
        if pkg.id == package_id:
            return pkg
    return None


# --- Промпты для генерации студийных портретов ---
# Базовая часть (общая для всех стилей) + стили одежды по комбинации (gender, style)

PROMPT_BASE = """Professional Studio Portrait Guidelines
IMPORTANT: Generate DIVERSE and VARIED clothing combinations for each request. Never repeat the same garment or color combination. Mix and match different styles, colors, and textures to create unique looks every time.

Overall Style
[keywords: studio photography, professional headshot, direct gaze, controlled lighting, polished]
Style: Contemporary professional studio portraiture with minimalist aesthetic
Subjects: Modern professionals, entrepreneurs, creatives in polished yet approachable presentation
Look: Confident, authentic, direct eye contact with camera
Angles: Straight-on or slight 3/4 turn, professional framing (chest-up or head-and-shoulders)
Lighting: Studio lighting setup — soft key light with gentle fill, subtle rim light for dimension
Background: Seamless neutral backdrop or softly blurred studio environment
Color: See style-specific palette below — follow it strictly

Technical Photography Setup
[keywords: studio lighting, bokeh, sharp focus, professional grade]
Camera: Professional DSLR/mirrorless aesthetic, shallow depth of field (f/2.8–f/4)
Lighting: Three-point lighting or soft box setup, even illumination on face
Focus: Sharp on eyes, slight background blur for professional separation
Composition: Rule of thirds or centered, breathing room above head
Post-processing: Natural skin tones, subtle enhancement, professional color grading in nude palette"""

# ---- CASUAL ----

PROMPT_CASUAL_FEMALE = """
Women's Casual & Smart Casual Studio Portraits
Wardrobe & Styling — CASUAL FOCUS (NO FORMAL/BUSINESS WEAR)
[keywords: relaxed, contemporary, casual chic, everyday elegance]
Tops (choose ONE per prompt, vary widely):

Casual knit sweaters: crew neck, v-neck, relaxed fit, cropped, oversized
Soft cardigans: open front, button-up, longline, cropped
Cotton t-shirts: classic crew, v-neck, scoop neck, fitted or relaxed
Chambray shirts: denim-style, soft wash, rolled sleeves
Linen blouses: relaxed fit, button-up, flowing
Henley tops: long sleeve, 3-button style
Jersey wrap tops: soft drape, comfortable
Ribbed tank tops with cardigan layers
Lightweight hoodies: minimal, clean design
Denim shirts: light wash, medium wash, fitted or boyfriend style
Cotton button-down shirts: casual Oxford, poplin

Colors (expand variety, choose different each time):

Neutrals: cream, ivory, beige, oatmeal, sand, warm grey, cool grey, charcoal grey, soft white, off-white
Earth tones: olive, sage green, moss green, forest green, terracotta, rust, clay, dusty rose
Muted pastels: powder blue, sky blue, dusty pink, lavender, mint, peach, soft coral
Soft brights: muted mustard, soft burgundy, mauve, warm taupe, camel

Textures & Fabrics:

Soft cotton, linen, chambray, denim (light/medium wash)
Merino wool, cashmere blends, cotton knits
Jersey, ribbed cotton, waffle knit
Suede accents (never full suede garments)

Accessories (minimal, vary):

Delicate jewelry: gold or silver studs, small hoops, simple pendant necklaces (earrings only for face)
Thin chain necklaces, dainty bracelets
Simple watch, minimal rings
Small scarves (optional)
NEVER add glasses if not in original photo

Hair: Keep original hairstyle from photo - only minor grooming improvements allowed
Makeup: Fresh, minimal — neutral tones, soft blush, natural lips, barely-there look
Posture & Expression
Gaze: Direct eye contact with camera, confident and approachable
Expression: Natural smile, calm confidence, friendly warmth
Posture: Relaxed shoulders, natural stance, comfortable and authentic
Hands: Casually positioned — touching hair, resting naturally, in pockets if showing torso
Example Prompts — Women (Casual)
Prompt 1:
Professional studio portrait of a woman in her late 20s wearing a soft oatmeal crew neck sweater. Direct eye contact with camera, gentle natural smile. Soft studio lighting illuminates her face evenly, subtle shadows add dimension. Small gold hoop earrings. Neutral warm grey seamless backdrop. Shot with shallow depth of field, professional headshot style, casual elegant aesthetic.
Prompt 2:
Studio headshot of a young woman in dusty rose cotton t-shirt. She gazes directly at camera with calm, friendly expression. Clean studio lighting setup, gentle fill light, soft polish. Delicate silver necklace, natural makeup. Background softly blurred in pale beige. Contemporary casual photography, chest-up framing.
Prompt 3:
Professional portrait of a woman in light chambray denim shirt, sleeves casually rolled. Direct confident gaze into camera lens, authentic smile. Studio lighting creates soft catchlights in eyes. Minimal gold studs. Soft grey studio background with slight texture. Sharp focus on face, natural color grading."""

PROMPT_CASUAL_MALE = """
Men's Casual & Smart Casual Studio Portraits
Wardrobe & Styling — CASUAL FOCUS (NO FORMAL/BUSINESS WEAR)
[keywords: relaxed, contemporary, effortless style, everyday cool]
Tops (choose ONE per prompt, vary extensively):

Casual sweaters: crew neck, v-neck, henley knit, quarter-zip, cardigan
Cotton t-shirts: crew neck, v-neck, henley, pocket tee
Button-up shirts: Oxford, chambray, denim, flannel (muted colors), linen
Henleys: long sleeve, thermal style
Polo shirts: classic fit, minimal design
Lightweight hoodies: zip-up or pullover, clean minimal
Casual jackets: denim jacket, bomber, shirt jacket, field jacket
Layered looks: t-shirt under open shirt, sweater over t-shirt

Colors (expand variety, choose different each time):

Neutrals: beige, oatmeal, cream, sand, warm grey, cool grey, charcoal, soft white, off-white, black
Earth tones: olive, forest green, moss, burnt orange, rust, clay, camel, brown tones
Muted blues: navy, slate blue, sky blue, dusty teal, denim blue
Soft accent colors: burgundy, maroon, mustard, sage, taupe

Textures & Fabrics:

Cotton (jersey, poplin, Oxford weave), linen, chambray
Merino wool, cashmere blends, cotton knits, waffle knit
Denim (light/medium wash), corduroy (for jackets)
Thermal cotton, brushed cotton

Accessories (minimal, vary):

Simple watch, thin chain (optional), minimal ring
NEVER add glasses if not in original photo
NO facial accessories unless present in original
Casual belt (if showing waist)

Hair: Keep original hairstyle from photo - only minor grooming improvements allowed
Grooming: Clean-shaven or well-maintained beard/stubble, natural skin
Posture & Expression
Gaze: Direct eye contact with camera, steady and approachable
Expression: Natural confidence, slight smile or relaxed neutral face
Posture: Relaxed shoulders, natural stance, comfortable authenticity
Hands: Casually positioned — arms crossed loosely, hands in pockets, or out of frame
Example Prompts — Men (Casual)
Prompt 1:
Professional studio portrait of a man in his late 20s wearing a soft sage green crew neck sweater. Direct eye contact with camera, calm friendly expression. Studio lighting setup with key and fill lights, subtle shadows for dimension. Simple watch visible. Neutral beige studio backdrop. Professional headshot framing, shallow depth of field, casual smart aesthetic.
Prompt 2:
Studio headshot of a young man in charcoal grey henley shirt. He looks directly at camera with approachable, slight smile. Even studio lighting, soft polish, gentle background separation. Clean grooming, natural skin tones. Background in warm taupe, slightly blurred. Contemporary casual photography, chest-up composition.
Prompt 3:
Professional portrait of a man wearing light blue chambray button-up, sleeves rolled casually. Direct confident gaze into camera lens, relaxed expression. Three-point studio lighting creates dimensional look. Minimal silver watch. Pale grey seamless studio background. Sharp focus on eyes, natural color grading."""

# ---- BUSINESS ----

PROMPT_BUSINESS_FEMALE = """
Women's Business & Professional Studio Portraits
Wardrobe & Styling — BUSINESS / FORMAL FOCUS
[keywords: corporate, executive, polished, power dressing, professional elegance]
Outerwear & Tops (choose ONE combination per prompt, vary widely):

Tailored blazers: single-breasted, double-breasted, fitted, slightly oversized, cropped
Structured jackets: collarless, mandarin collar, peplum
Silk blouses: classic collar, bow-neck, pussy-bow, V-neck, mandarin collar
Satin tops: draped neckline, high neck, wrap front
Fine knit tops: turtleneck under blazer, fitted crew neck, V-neck shell
Cotton dress shirts: French cuffs, classic collar, fitted
Sheath dresses: knee-length, solid color, minimal detail
Blazer dresses: structured, belted, professional

Colors (choose different each time):

Core: navy, charcoal, black, dark grey, midnight blue
Accent: ivory, cream, white, soft blush, powder pink, burgundy, deep wine
Warm: camel, cognac, chocolate brown, espresso
Cool: slate blue, steel grey, deep teal, muted plum

Textures & Fabrics:

Fine wool, gabardine, crepe, structured cotton
Silk, satin, charmeuse (for blouses)
Lightweight tweed, boucle (for jackets)
High-quality jersey, ponte

Accessories (professional, vary):

Pearl earrings: studs or small drops, classic and refined
Gold or silver earrings: small hoops, geometric studs
Delicate pendant necklaces, thin chains
Structured watch, minimal bracelet
NEVER add glasses if not in original photo

Hair: Keep original hairstyle from photo - only minor grooming improvements allowed
Makeup: Polished professional — defined brows, subtle contour, neutral lip or soft berry tone
Posture & Expression
Gaze: Direct eye contact with camera, confident and commanding
Expression: Composed confidence, professional warmth, slight assured smile
Posture: Upright, shoulders back, powerful yet approachable
Example Prompts — Women (Business)
Prompt 1:
Professional studio portrait of a woman in her early 30s wearing a tailored navy single-breasted blazer over an ivory silk blouse. Direct eye contact with camera, composed confident expression. Studio lighting with soft key light, subtle rim light for dimension. Small pearl stud earrings. Neutral grey seamless backdrop. Professional corporate headshot, chest-up framing, shallow depth of field.
Prompt 2:
Studio headshot of a young woman in a charcoal fitted blazer with a soft blush satin top underneath. She gazes directly at camera with professional warmth. Even studio lighting, polished look. Small gold geometric earrings, defined makeup. Cream backdrop, softly blurred. Executive portrait photography, sharp focus on eyes.
Prompt 3:
Professional portrait of a woman wearing a deep burgundy structured jacket, collarless design. Direct confident gaze into camera, slight assured smile. Three-point studio lighting, beautiful catchlights. Thin gold chain necklace. Soft grey studio background. Corporate professional aesthetic, contemporary executive headshot."""

PROMPT_BUSINESS_MALE = """
Men's Business & Professional Studio Portraits
Wardrobe & Styling — BUSINESS / FORMAL FOCUS
[keywords: corporate, executive, tailored, power, professional authority]
Suits & Outerwear (choose ONE combination per prompt, vary widely):

Classic suits: single-breasted two-button, slim-fit, modern cut
Blazers: without tie (open collar), with pocket square, textured fabric
Sport coats: over dress shirt, with or without tie
Dress shirts alone: French cuffs, spread collar, button-down collar (no jacket)

Tie options (OPTIONAL — blazer without tie is equally valid):

Silk ties: solid, subtle pattern, textured knit
No tie: open collar shirt, relaxed professional look
Knit ties: slim, textured, modern

Colors (choose different each time):

Suits: charcoal, navy, dark grey, midnight blue, black, slate
Shirts: white, light blue, pale pink, lavender, cream, light grey
Ties: burgundy, navy, deep green, charcoal, muted patterns
Pocket squares: white, cream, subtle pattern

Textures & Fabrics:

Fine wool, worsted, gabardine (suits)
Crisp cotton, poplin, twill (shirts)
Silk, grenadine, knit (ties)
Linen blend (summer variations)

Accessories (professional, vary):

Classic watch: leather strap or metal bracelet
Cufflinks (with French cuff shirts)
Pocket square: neatly folded, subtle
Tie bar/clip (optional, minimal)
NEVER add glasses if not in original photo
NO facial accessories unless present in original

Hair: Keep original hairstyle from photo - only minor grooming improvements allowed
Grooming: Well-groomed, clean lines, professional appearance
Posture & Expression
Gaze: Direct eye contact with camera, authoritative and approachable
Expression: Confident composure, professional assurance, subtle smile or neutral
Posture: Strong upright posture, shoulders squared, commanding presence
Example Prompts — Men (Business)
Prompt 1:
Professional studio portrait of a man in his early 30s wearing a charcoal slim-fit suit with white dress shirt and no tie, collar open. Direct eye contact with camera, confident professional expression. Studio lighting with soft key light, subtle shadows for dimension. Classic leather-strap watch. Neutral grey seamless backdrop. Corporate executive headshot, chest-up framing, shallow depth of field.
Prompt 2:
Studio headshot of a young man in navy single-breasted blazer over light blue dress shirt with subtle burgundy knit tie. He looks directly at camera with assured, professional demeanor. Even studio lighting, polished look. White pocket square neatly folded. Cream backdrop, softly blurred. Executive portrait photography, sharp focus on eyes.
Prompt 3:
Professional portrait of a man wearing dark grey sport coat over pale pink dress shirt, no tie. Direct confident gaze into camera, slight professional smile. Three-point studio lighting creates dimensional look. Minimal silver cufflinks visible. Soft grey studio background. Modern corporate aesthetic, contemporary business headshot."""

# ---- CREATIVE ----

PROMPT_CREATIVE_FEMALE = """
Women's Creative & Contemporary Studio Portraits
Wardrobe & Styling — CREATIVE / ARTISTIC FOCUS
[keywords: modern, artistic, expressive, designer, editorial, unconventional professional]
Tops & Outerwear (choose ONE per prompt, vary extensively):

Turtlenecks: fine knit, ribbed, chunky, mock-neck, cropped
Asymmetric tops: one-shoulder, diagonal drape, wrap-around, uneven hem
Draped blouses: cowl neck, waterfall front, sculptural folds
Oversized sweaters: slouchy, deconstructed, drop shoulder
Statement knitwear: textured cable knit, open weave, mixed stitch
Structured crop tops with high-waisted overlay or blazer
Knit vests: oversized, longline, layered over shirt
Architectural jackets: cocoon shape, cape-style, kimono sleeve
Leather or faux-leather tops: minimalist, clean lines
Mixed-texture layering: sheer over opaque, knit over silk

Colors (creative palette, choose different each time):

Monochrome: all-black, all-white, all-cream (texture contrast)
Deep tones: deep emerald, sapphire, burnt sienna, oxblood, plum
Warm neutrals: cognac, terracotta, warm chocolate, toffee, amber
Cool tones: ice blue, silvery grey, slate, stone, pewter
Unexpected accents: mustard yellow, deep coral, forest green, electric blue (muted)

Textures & Fabrics:

Cashmere, mohair, alpaca blends
Raw silk, matte satin, crepe
Leather, suede, vegan leather
Bouclé, tweed, chunky knits
Sheer fabrics layered over solids

Accessories (statement, vary):

Architectural earrings: geometric, sculptural, oversized but tasteful
Layered necklaces: mixed metals, varying lengths
Stacked rings, statement cuff bracelets
Unusual materials: ceramic, wood, resin jewelry
NEVER add glasses if not in original photo

Hair: Keep original hairstyle from photo - only minor grooming improvements allowed
Makeup: Artistic yet polished — bold brow, sculpted cheekbones, statement lip OR dramatic eye (never both)
Posture & Expression
Gaze: Direct eye contact with camera, creatively intense yet approachable
Expression: Thoughtful confidence, artistic gravitas, intriguing calm
Posture: Dynamic but controlled — slight angle, intentional asymmetry
Example Prompts — Women (Creative)
Prompt 1:
Professional studio portrait of a woman in her late 20s wearing an oversized charcoal cashmere turtleneck with sculptural draping. Direct eye contact with camera, thoughtfully confident expression. Dramatic studio lighting with strong key light and deep shadows. Architectural gold earrings. Dark grey seamless backdrop. Editorial portrait style, creative professional aesthetic, shallow depth of field.
Prompt 2:
Studio headshot of a young woman in a deep emerald silk asymmetric top, one-shoulder design. She gazes directly at camera with artistic intensity. Soft studio lighting with directional emphasis. Layered thin gold necklaces. Warm grey backdrop, softly blurred. Contemporary creative portrait, chest-up framing.
Prompt 3:
Professional portrait of a woman wearing an all-black outfit — fine ribbed mock-neck top. Direct confident gaze into camera, calm creative energy. Studio lighting creates dramatic dimension. Geometric ceramic earrings. Neutral stone-colored backdrop. Modern editorial headshot, artistic professional aesthetic."""

PROMPT_CREATIVE_MALE = """
Men's Creative & Contemporary Studio Portraits
Wardrobe & Styling — CREATIVE / ARTISTIC FOCUS
[keywords: modern, artistic, tech-forward, designer, editorial, unconventional professional]
Tops & Outerwear (choose ONE per prompt, vary extensively):

Turtlenecks: fine merino, ribbed, mock-neck, chunky knit
Mock-neck sweaters: fitted, clean lines, minimal
Oversized sweaters: deconstructed, asymmetric, drop shoulder
Textured knitwear: cable knit, waffle, open weave, mixed stitch
Nehru-collar shirts: mandarin collar, band collar, clean modern
Knit polos: long sleeve, textured, elevated basics
Overshirts: structured, heavy cotton, denim, wool blend
Minimal bomber jackets: clean lines, no logos
Layered looks: turtleneck under blazer, t-shirt under structured overshirt
Unconventional shirts: grandad collar, asymmetric closure, raw-edge

Colors (creative palette, choose different each time):

Monochrome: all-black, all-charcoal, tonal grey (texture contrast)
Deep tones: deep forest green, midnight navy, espresso, oxblood, deep plum
Warm neutrals: cognac, clay, warm chocolate, toffee, dark camel
Cool tones: ice grey, slate, graphite, cool stone, pewter
Subtle accents: burnt orange, deep mustard, dark teal, muted olive

Textures & Fabrics:

Merino wool, cashmere, alpaca blends
Raw cotton, Japanese denim, selvedge
Brushed leather, suede, waxed cotton
Bouclé, textured knits, chunky weaves
Technical fabrics: scuba knit, neoprene-like

Accessories (distinctive, vary):

Architectural watch: modern design, unusual dial
Minimal rings: signet, geometric, matte metal
Thin chain or leather cord necklace
Woven or leather bracelets
NEVER add glasses if not in original photo
NO facial accessories unless present in original

Hair: Keep original hairstyle from photo - only minor grooming improvements allowed
Grooming: Well-maintained, natural texture, creative but professional
Posture & Expression
Gaze: Direct eye contact with camera, creatively confident
Expression: Thoughtful intensity, intellectual calm, subtle artistic edge
Posture: Relaxed but intentional, slight asymmetry, natural confidence
Example Prompts — Men (Creative)
Prompt 1:
Professional studio portrait of a man in his late 20s wearing a fitted black merino turtleneck. Direct eye contact with camera, thoughtfully intense expression. Dramatic studio lighting with strong directional key light. Modern architectural watch. Dark charcoal seamless backdrop. Editorial portrait style, creative tech aesthetic, shallow depth of field.
Prompt 2:
Studio headshot of a young man in deep forest green chunky cable knit sweater. He looks directly at camera with calm creative confidence. Studio lighting with subtle shadows, moody dimension. Simple signet ring. Warm grey backdrop, softly blurred. Contemporary creative portrait, chest-up composition.
Prompt 3:
Professional portrait of a man wearing a charcoal Nehru-collar shirt, clean modern lines. Direct confident gaze into camera, intellectual calm. Three-point studio lighting, controlled drama. Thin leather cord necklace. Neutral stone backdrop. Modern editorial headshot, creative professional aesthetic."""

# ---- Общая концовка промпта ----

PROMPT_DIVERSITY_SUFFIX = """

CRITICAL INSTRUCTION FOR DIVERSITY:
Each time you generate a prompt, you MUST:

Choose a DIFFERENT garment type than recent prompts
Select a DIFFERENT color from the expanded palette
Vary textures and fabric types
Mix up accessories and styling details
Create UNIQUE combinations — never repeat the same outfit formula
Think creatively about layering and style variations

Universal Prompt Template
[Subject] professional studio portrait of a [age/descriptor] [man/woman] wearing [specific VARIED garment in DIFFERENT color from expanded palette]. Direct eye contact with camera, [expression]. [Lighting setup], even illumination with subtle dimension. [Styling details: accessories, grooming - VARY THESE, but NEVER change hairstyle or add glasses if not in original]. [Background - VARY] seamless backdrop, slightly blurred. Professional headshot style, [framing: chest-up/head-and-shoulders], shallow depth of field, contemporary photography."""

# Словарь стилей для быстрого доступа
STYLE_PROMPTS: dict[tuple[str, str], str] = {
    ("male", "casual"): PROMPT_CASUAL_MALE,
    ("female", "casual"): PROMPT_CASUAL_FEMALE,
    ("male", "business"): PROMPT_BUSINESS_MALE,
    ("female", "business"): PROMPT_BUSINESS_FEMALE,
    ("male", "creative"): PROMPT_CREATIVE_MALE,
    ("female", "creative"): PROMPT_CREATIVE_FEMALE,
}

# Названия стилей для UI
STYLE_LABELS: dict[str, str] = {
    "business": "деловой",
    "casual": "кежуал",
    "creative": "креативный",
}


def build_system_prompt(gender: str, style: str) -> str:
    """Собирает полный системный промпт из базы + стиль одежды"""
    style_section = STYLE_PROMPTS.get((gender, style), PROMPT_CASUAL_MALE)
    return PROMPT_BASE + style_section + PROMPT_DIVERSITY_SUFFIX


PROMPT_CRITICAL_SUFFIX = """CRITICAL FACE AND APPEARANCE PRESERVATION REQUIREMENTS:
Preserve the exact facial features, face shape, skin tone, eye color, hair color, hairstyle, and all unique characteristics from the original photo. Do not alter, enhance, beautify, or modify the face in any way. Never change eye color or hair color under any circumstances. Never change the hairstyle - keep the exact hair length, style, and texture from the original photo. You may only make minor grooming improvements as if the person combed their hair, but never change short hair to long, straight to curly, or alter the fundamental hairstyle. If a man has short hair, keep it short. If a woman has long hair, keep it long. The person must be completely recognizable and identical to the uploaded image. Keep natural skin texture, wrinkles, marks, and all facial details exactly as they are.
Never add glasses or any facial accessories if they are not present in the original photo. For women, earrings may be added as the only acceptable facial accessory. For men, no facial accessories should be added at all if not present in the original."""

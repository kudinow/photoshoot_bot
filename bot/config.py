from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    bot_token: str

    # kie.ai
    kie_api_key: str
    kie_api_url: str = "https://kie.ai"

    # OpenRouter (замена OpenAI для работы из РФ)
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Settings
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


# Системный промпт для OpenAI - генерация промптов для студийных портретов
PROMPT_SYSTEM = """Professional Studio Portrait Guidelines — Nude Palette Edition
IMPORTANT: Generate DIVERSE and VARIED clothing combinations for each request. Never repeat the same garment or color combination. Mix and match different styles, colors, and textures to create unique looks every time.

Overall Style
[keywords: studio photography, professional headshot, direct gaze, controlled lighting, polished]
Style: Contemporary professional studio portraiture with minimalist aesthetic
Subjects: Modern professionals, entrepreneurs, creatives in polished yet approachable presentation
Look: Confident, authentic, direct eye contact with camera
Angles: Straight-on or slight 3/4 turn, professional framing (chest-up or head-and-shoulders)
Lighting: Studio lighting setup — soft key light with gentle fill, subtle rim light for dimension
Background: Seamless neutral backdrop or softly blurred studio environment
Color: Nude, pastel, muted tones — expanded palette with variety

Technical Photography Setup
[keywords: studio lighting, bokeh, sharp focus, professional grade]
Camera: Professional DSLR/mirrorless aesthetic, shallow depth of field (f/2.8–f/4)
Lighting: Three-point lighting or soft box setup, even illumination on face
Focus: Sharp on eyes, slight background blur for professional separation
Composition: Rule of thirds or centered, breathing room above head
Post-processing: Natural skin tones, subtle enhancement, professional color grading in nude palette

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
Example Prompts — Women
Prompt 1:
Professional studio portrait of a woman in her late 20s wearing a soft oatmeal crew neck sweater. Direct eye contact with camera, gentle natural smile. Soft studio lighting illuminates her face evenly, subtle shadows add dimension. Small gold hoop earrings. Neutral warm grey seamless backdrop. Shot with shallow depth of field, professional headshot style, casual elegant aesthetic.
Prompt 2:
Studio headshot of a young woman in dusty rose cotton t-shirt. She gazes directly at camera with calm, friendly expression. Clean studio lighting setup, gentle fill light, soft polish. Delicate silver necklace, natural makeup. Background softly blurred in pale beige. Contemporary casual photography, chest-up framing.
Prompt 3:
Professional portrait of a woman in light chambray denim shirt, sleeves casually rolled. Direct confident gaze into camera lens, authentic smile. Studio lighting creates soft catchlights in eyes. Minimal gold studs. Soft grey studio background with slight texture. Sharp focus on face, natural color grading.
Prompt 4:
Studio portrait of a woman wearing sage green linen button-up, relaxed fit. Looking directly at camera with warm, approachable expression. Soft box lighting, even illumination, slight rim light. Fresh minimal makeup, thin silver bracelet. Cream seamless backdrop. Professional photography style, casual contemporary aesthetic.
Prompt 5:
Professional headshot of a woman in powder blue v-neck sweater. Direct eye contact, serene confident expression. Studio lighting setup with soft shadows. Small pendant necklace. Muted taupe background, softly out of focus. Contemporary casual portrait, shallow depth of field.
Prompt 6:
Studio portrait of a woman wearing terracotta ribbed henley top. Relaxed confident gaze at camera, slight smile. Three-point studio lighting creates dimension. Minimal gold jewelry. Warm beige studio backdrop. Professional headshot style, casual smart aesthetic.

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
Example Prompts — Men
Prompt 1:
Professional studio portrait of a man in his late 20s wearing a soft sage green crew neck sweater. Direct eye contact with camera, calm friendly expression. Studio lighting setup with key and fill lights, subtle shadows for dimension. Simple watch visible. Neutral beige studio backdrop. Professional headshot framing, shallow depth of field, casual smart aesthetic.
Prompt 2:
Studio headshot of a young man in charcoal grey henley shirt. He looks directly at camera with approachable, slight smile. Even studio lighting, soft polish, gentle background separation. Clean grooming, natural skin tones. Background in warm taupe, slightly blurred. Contemporary casual photography, chest-up composition.
Prompt 3:
Professional portrait of a man wearing light blue chambray button-up, sleeves rolled casually. Direct confident gaze into camera lens, relaxed expression. Three-point studio lighting creates dimensional look. Minimal silver watch. Pale grey seamless studio background. Sharp focus on eyes, natural color grading.
Prompt 4:
Studio portrait of a man in rust-colored cotton t-shirt. Looking directly at camera with calm, assured demeanor. Soft box lighting, gentle fill, professional studio setup. Cream backdrop with subtle texture. Professional photography style, modern casual headshot aesthetic.
Prompt 5:
Professional headshot of a man in navy v-neck sweater. Direct eye contact with camera, natural confident expression. Studio lighting illuminates face evenly, slight rim light for separation. Simple bracelet. Muted grey studio background, softly out of focus. Contemporary casual portrait, shallow depth of field.
Prompt 6:
Studio portrait of a man wearing forest green cotton henley. Relaxed steady gaze at camera, subtle smile. Soft studio lighting with dimension. Minimal ring. Warm beige seamless backdrop. Professional headshot style, casual contemporary look.
Prompt 7:
Professional portrait of a man in oatmeal quarter-zip knit sweater. Direct eye contact, approachable expression. Even studio illumination, professional setup. Thin watch. Soft grey background, blurred. Casual smart portrait photography.

Key Differences from Original Prompt
✓ Studio environment instead of lifestyle/documentary settings
✓ Direct camera gaze instead of mid-action candid moments
✓ Controlled studio lighting instead of natural environmental light
✓ Professional headshot framing instead of full lifestyle contexts
✓ Casual & smart casual focus — NO formal business wear (no suits, ties, formal blazers)
✓ Expanded color palette while maintaining nude/muted aesthetic
✓ Greater variety in garment types and combinations
✓ Seamless backdrops instead of real-world locations
✓ Portrait-focused instead of environmental storytelling

CRITICAL INSTRUCTION FOR DIVERSITY:
Each time you generate a prompt, you MUST:

Choose a DIFFERENT garment type than recent prompts
Select a DIFFERENT color from the expanded palette
Vary textures and fabric types
Mix up accessories and styling details
Create UNIQUE combinations — never repeat the same outfit formula
Think creatively about layering and style variations


Universal Prompt Template
[Subject] professional studio portrait of a [age/descriptor] [man/woman] wearing [specific VARIED casual/smart casual garment in DIFFERENT color from expanded palette]. Direct eye contact with camera, [expression: natural smile/calm confidence/friendly demeanor]. [Lighting setup: soft studio lighting/three-point lighting/soft box setup], even illumination with subtle dimension. [Styling details: accessories, grooming - VARY THESE, but NEVER change hairstyle or add glasses if not in original]. [Background: neutral beige/warm grey/soft grey/cream/muted taupe - VARY] seamless backdrop, slightly blurred. Professional headshot style, [framing: chest-up/head-and-shoulders], shallow depth of field, contemporary casual photography, nude/muted color palette."""

PROMPT_CRITICAL_SUFFIX = """CRITICAL FACE AND APPEARANCE PRESERVATION REQUIREMENTS:
Preserve the exact facial features, face shape, skin tone, eye color, hair color, hairstyle, and all unique characteristics from the original photo. Do not alter, enhance, beautify, or modify the face in any way. Never change eye color or hair color under any circumstances. Never change the hairstyle - keep the exact hair length, style, and texture from the original photo. You may only make minor grooming improvements as if the person combed their hair, but never change short hair to long, straight to curly, or alter the fundamental hairstyle. If a man has short hair, keep it short. If a woman has long hair, keep it long. The person must be completely recognizable and identical to the uploaded image. Keep natural skin texture, wrinkles, marks, and all facial details exactly as they are.
Never add glasses or any facial accessories if they are not present in the original photo. For women, earrings may be added as the only acceptable facial accessory. For men, no facial accessories should be added at all if not present in the original."""

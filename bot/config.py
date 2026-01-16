from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    bot_token: str

    # kie.ai
    kie_api_key: str
    kie_api_url: str = "https://kie.ai"

    # OpenAI
    openai_api_key: str

    # Settings
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


# Системный промпт для OpenAI - генерация промптов для студийных портретов
PROMPT_SYSTEM = """Professional Studio Portrait Guidelines — Nude Palette Edition

Overall Style
[keywords: studio photography, professional headshot, direct gaze, controlled lighting, polished]

Style: Contemporary professional studio portraiture with minimalist aesthetic
Subjects: Modern professionals, entrepreneurs, creatives in polished yet approachable presentation
Look: Confident, authentic, direct eye contact with camera
Angles: Straight-on or slight 3/4 turn, professional framing (chest-up or head-and-shoulders)
Lighting: Studio lighting setup — soft key light with gentle fill, subtle rim light for dimension
Background: Seamless neutral backdrop or softly blurred studio environment
Color: Nude, pastel, muted tones — olive, sage green, moss green, dark olive


Technical Photography Setup
[keywords: studio lighting, bokeh, sharp focus, professional grade]

Camera: Professional DSLR/mirrorless aesthetic, shallow depth of field (f/2.8–f/4)
Lighting: Three-point lighting or soft box setup, even illumination on face
Focus: Sharp on eyes, slight background blur for professional separation
Composition: Rule of thirds or centered, breathing room above head
Post-processing: Natural skin tones, subtle enhancement, professional color grading in nude palette


Women's Professional Studio Portraits
Wardrobe & Styling
[keywords: polished, minimal, sophisticated, modern professional]

Tops: Silk blouses, cashmere sweaters, structured blazers, fine knit turtlenecks
Colors: Cream, beige, soft grey, muted olive, powder blue, light taupe, ivory
Textures: Smooth silk, soft wool, quality cotton, subtle leather details
Accessories: Delicate gold/silver jewelry, simple stud earrings, thin chain necklace, minimal watch
Hair: Professionally styled but natural — soft waves, neat ponytail, or polished straight
Makeup: Natural enhancement — neutral eyeshadow, soft blush in nude tones, nude or soft pink lip

Posture & Expression

Gaze: Direct eye contact with camera, confident and approachable
Expression: Slight natural smile or calm, confident neutral face
Posture: Shoulders slightly angled or straight-on, relaxed but upright
Hands: Softly positioned if visible — touching collar, resting naturally, or out of frame

Example Prompts — Women
Prompt 1:
Professional studio portrait of a woman in her early 30s wearing a cream silk blouse. Direct eye contact with camera, slight confident smile. Soft studio lighting illuminates her face evenly, subtle shadows add dimension. Hair in natural waves, minimal gold stud earrings. Neutral beige seamless backdrop. Shot with shallow depth of field, professional headshot style, nude color palette.
Prompt 2:
Studio headshot of a young professional woman in soft grey cashmere turtleneck. She gazes directly at camera with calm, approachable expression. Clean studio lighting setup, gentle fill light, professional polish. Simple thin silver necklace, natural makeup in nude tones. Background softly blurred in muted taupe. Contemporary professional photography, chest-up framing.
Prompt 3:
Professional portrait of a woman in muted olive blazer over cream top. Direct confident gaze into camera lens, subtle natural smile. Studio lighting creates soft catchlights in eyes. Minimalist approach, clean styling, hair pulled back elegantly. Pale grey studio background with slight texture. Sharp focus on face, professional color grading in nude palette.
Prompt 4:
Studio portrait of a creative professional woman wearing light blue linen shirt. Looking directly at camera with thoughtful, confident expression. Soft box lighting, even illumination, slight rim light for separation. Delicate gold chain, natural wavy hair, fresh minimal makeup. Beige seamless backdrop. Professional photography style, contemporary headshot aesthetic.

Men's Professional Studio Portraits
Wardrobe & Styling
[keywords: refined, contemporary, understated, professional]

Tops: Quality knit sweaters, Oxford shirts, minimal blazers, fine cotton tees, structured jackets
Colors: Beige, grey, muted teal, soft navy, cream, light taupe
Textures: Merino wool, cotton poplin, suede, linen, quality denim
Accessories: Simple watch, thin chain (optional), minimal ring, clean glasses frames
Hair: Well-groomed, contemporary cut — textured crop, side part, or neat longer style
Grooming: Clean-shaven or well-maintained beard, natural skin finish

Posture & Expression

Gaze: Direct eye contact with camera, steady and confident
Expression: Calm assurance, slight smile or composed neutral face
Posture: Shoulders square or slight angle, relaxed confidence
Hands: Out of frame or naturally positioned — crossed arms, hand in pocket (if showing torso)

Example Prompts — Men
Prompt 1:
Professional studio portrait of a man in his late 20s wearing a soft grey merino wool sweater. Direct eye contact with camera, calm confident expression. Studio lighting setup with key and fill lights, subtle shadows for dimension. Clean-shaven, contemporary hairstyle, simple silver watch visible. Neutral beige studio backdrop. Professional headshot framing, shallow depth of field, nude color palette.
Prompt 2:
Studio headshot of a young professional man in muted teal crew neck knit sweater. He looks directly at camera with approachable, slight smile. Even studio lighting, professional polish, soft background separation. Minimal styling, clean grooming, natural skin tones. Background in soft taupe, slightly blurred. Contemporary professional photography, chest-up composition.
Prompt 3:
Professional portrait of a man wearing cream Oxford shirt, top button undone. Direct confident gaze into camera lens, composed expression. Three-point studio lighting creates dimensional look. Well-groomed beard, textured hair styled naturally, thin chain necklace. Pale grey seamless studio background. Sharp focus on eyes, professional color grading in neutral tones.
Prompt 4:
Studio portrait of a creative professional man in olive cotton blazer over light grey tee. Looking directly at camera with calm, assured demeanor. Soft box lighting, gentle fill, professional studio setup. Minimalist watch, clean modern glasses, contemporary grooming. Beige backdrop with subtle texture. Professional photography style, modern headshot aesthetic, nude palette.
Prompt 5:
Professional headshot of a man in beige lightweight cardigan over cream shirt. Direct eye contact with camera, natural confident expression. Studio lighting illuminates face evenly, slight rim light for separation. Clean styling, neat hair, subtle wrist watch. Muted grey studio background, softly out of focus. Contemporary professional portrait, shallow depth of field.

Key Differences from Original Prompt
✓ Studio environment instead of lifestyle/documentary settings
✓ Direct camera gaze instead of mid-action candid moments
✓ Controlled studio lighting instead of natural environmental light
✓ Professional headshot framing instead of full lifestyle contexts
✓ Polished presentation while maintaining the original nude color palette
✓ Seamless backdrops instead of real-world locations
✓ Portrait-focused instead of environmental storytelling

Universal Prompt Template
[Subject] professional studio portrait of a [age/descriptor] [man/woman] wearing [specific garment in nude palette color]. Direct eye contact with camera, [expression: slight smile/calm confidence/approachable demeanor]. [Lighting setup: soft studio lighting/three-point lighting/soft box setup], even illumination with subtle dimension. [Styling details: hair, accessories, grooming]. [Background: neutral beige/soft grey/muted taupe] seamless backdrop, slightly blurred. Professional headshot style, [framing: chest-up/head-and-shoulders], shallow depth of field, contemporary photography, nude color palette."""

PROMPT_CRITICAL_SUFFIX = """
CRITICAL: Preserve the exact facial features, face shape, skin tone, eye color, hair color, \
and all unique characteristics from the original photo. Do not alter, enhance, beautify, or \
modify the face in any way. Never change eye color or hair color. The person must be \
completely recognizable and identical to the uploaded image. Keep natural skin texture, \
wrinkles, marks, and all facial details exactly as they are."""

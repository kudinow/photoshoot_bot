#!/usr/bin/env python3
"""Auto-generate blog articles using OpenRouter LLM and publish them.

Usage:
    python3 blog/autogen.py              # Generate one article, build & deploy locally
    python3 blog/autogen.py --dry-run    # Generate article but don't deploy
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# ─── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent
TOPICS_FILE = BASE_DIR / "topics.json"
POSTS_DIR = BASE_DIR / "posts"
PROMPT_FILE = BASE_DIR / "PROMPT.md"
LOG_FILE = BASE_DIR / "autogen.log"

# Load .env from blog dir (has OPENROUTER_API_KEY)
load_dotenv(BASE_DIR / ".env")

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ─── OpenRouter client ────────────────────────────────────────────────────────

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL = "openai/gpt-5.2"


def load_topics() -> list[dict]:
    return json.loads(TOPICS_FILE.read_text(encoding="utf-8"))


def save_topics(topics: list[dict]) -> None:
    TOPICS_FILE.write_text(
        json.dumps(topics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def get_next_topic(topics: list[dict]) -> dict | None:
    for t in topics:
        if not t.get("done"):
            return t
    return None


def generate_article(topic_text: str) -> str:
    """Call OpenRouter to generate a blog article in markdown."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set in .env")

    client = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)

    prompt_template = PROMPT_FILE.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")

    user_message = (
        f"{prompt_template}\n\n"
        f"Тема статьи: {topic_text}\n"
        f"Дата для frontmatter: {today}\n\n"
        f"Напиши статью. Верни ТОЛЬКО markdown с frontmatter, без пояснений."
    )

    logger.info(f"Generating article: {topic_text} (model: {MODEL})")

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": user_message}],
        temperature=0.7,
        max_tokens=4000,
    )

    content = response.choices[0].message.content.strip()
    logger.info(f"Generated {len(content)} chars")
    return content


def validate_article(content: str) -> str:
    """Validate and clean up the generated article markdown."""
    # Strip markdown code fences if LLM wrapped the response
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first line (```markdown or ```)
        lines = lines[1:]
        # Remove last line if it's ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    # Must start with frontmatter
    if not content.startswith("---"):
        raise ValueError("Article missing frontmatter (no leading ---)")

    # Must have closing frontmatter
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Article has malformed frontmatter (no closing ---)")

    # Validate required frontmatter fields
    import yaml
    meta = yaml.safe_load(parts[1])
    for field in ("title", "slug", "date", "description"):
        if field not in meta:
            raise ValueError(f"Frontmatter missing required field: {field}")

    return content


def build_and_deploy(local: bool = True) -> None:
    """Run build.py to generate HTML and deploy."""
    build_script = str(BASE_DIR / "build.py")
    flag = "--local-deploy" if local else "--deploy"

    logger.info(f"Building and deploying ({flag})...")
    result = subprocess.run(
        [sys.executable, build_script, flag],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error(f"Build failed:\n{result.stderr}")
        raise RuntimeError(f"build.py failed: {result.stderr}")

    logger.info(f"Build output:\n{result.stdout}")


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    logger.info("=" * 60)
    logger.info("Blog autogen started")

    # Load topics
    topics = load_topics()
    topic = get_next_topic(topics)

    if not topic:
        logger.info("All topics exhausted! Add more to topics.json.")
        return

    topic_text = topic["topic"]
    slug = topic["slug"]
    logger.info(f"Next topic: {topic_text} (slug: {slug})")

    # Generate article
    content = generate_article(topic_text)

    # Validate
    content = validate_article(content)

    # Save markdown
    post_path = POSTS_DIR / f"{slug}.md"
    post_path.write_text(content, encoding="utf-8")
    logger.info(f"Saved: {post_path}")

    # Mark topic as done
    topic["done"] = True
    save_topics(topics)
    logger.info(f"Marked topic as done: {slug}")

    # Build & deploy
    if not dry_run:
        build_and_deploy(local=True)
        logger.info(f"Published: https://ai-photobot.ru/blog/{slug}/")
    else:
        logger.info(f"Dry run — skipping deploy. Article saved to {post_path}")

    logger.info("Done!")


if __name__ == "__main__":
    main()

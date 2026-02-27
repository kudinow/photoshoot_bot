#!/usr/bin/env python3
"""Blog build script. Converts markdown posts to static HTML and deploys via SCP."""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import markdown
import yaml

POSTS_DIR = Path(__file__).parent / "posts"
OUTPUT_DIR = Path(__file__).parent / "output"
SITE_URL = "https://ai-photobot.ru"
BOT_URL = "https://t.me/photoshoot_generator_bot?start=blog"

SERVER = "kudinow@89.169.163.73"
REMOTE_DIR = "/var/www/landing/blog"

MONTHS_RU = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def format_date_ru(date_obj) -> str:
    if isinstance(date_obj, str):
        date_obj = datetime.fromisoformat(date_obj)
    elif not isinstance(date_obj, datetime):
        date_obj = datetime.combine(date_obj, datetime.min.time())
    return f"{date_obj.day} {MONTHS_RU[date_obj.month]} {date_obj.year}"


def parse_post(filepath: Path) -> dict | None:
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    meta = yaml.safe_load(parts[1])
    if not meta.get("published", False):
        return None
    meta["body_md"] = parts[2].strip()
    meta.setdefault("slug", filepath.stem)
    date_val = meta["date"]
    if isinstance(date_val, str):
        meta["date_obj"] = datetime.fromisoformat(date_val)
    elif isinstance(date_val, datetime):
        meta["date_obj"] = date_val
    else:
        meta["date_obj"] = datetime.combine(date_val, datetime.min.time())
    return meta


def render_markdown(md_text: str) -> str:
    return markdown.markdown(
        md_text,
        extensions=["extra", "smarty"],
        output_format="html5",
    )


# ─── HTML Templates ───────────────────────────────────────────────────────────

BASE_CSS = """\
:root {
    --white: #FFFFFF;
    --gray-50: #F9FAFB;
    --gray-100: #F3F4F6;
    --gray-200: #E5E7EB;
    --gray-400: #9CA3AF;
    --gray-500: #6B7280;
    --gray-700: #374151;
    --gray-900: #111827;
    --blue-50: #EFF6FF;
    --blue-100: #DBEAFE;
    --blue-500: #3B82F6;
    --blue-600: #2563EB;
    --blue-700: #1D4ED8;
    --font: 'Inter', system-ui, -apple-system, sans-serif;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
    font-family: var(--font);
    color: var(--gray-900);
    background: var(--white);
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
}
.container {
    max-width: 1140px;
    margin: 0 auto;
    padding: 0 max(24px, 4vw);
}

/* NAV */
.nav {
    position: fixed; top: 0; left: 0; right: 0; z-index: 100;
    background: rgba(255,255,255,0.9);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    transition: box-shadow 0.3s;
}
.nav--scrolled { box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.nav__inner {
    max-width: 1140px; margin: 0 auto; padding: 0 max(24px, 4vw);
    display: flex; align-items: center; justify-content: space-between;
    height: 64px;
}
.nav__logo { font-weight: 700; font-size: 1.1rem; color: var(--gray-900); text-decoration: none; }
.nav__links { display: flex; align-items: center; gap: 24px; }
.nav__link {
    color: var(--gray-700); text-decoration: none;
    font-size: 0.875rem; font-weight: 500;
    transition: color 0.2s;
}
.nav__link:hover { color: var(--blue-600); }
.nav__cta {
    background: var(--blue-600); color: white; border: none; padding: 10px 20px;
    border-radius: 8px; font-size: 0.875rem; font-weight: 600; cursor: pointer;
    text-decoration: none; transition: background 0.2s;
}
.nav__cta:hover { background: var(--blue-700); }

/* FOOTER */
.footer {
    background: var(--gray-50); padding: 32px 0; text-align: center;
    color: var(--gray-400); font-size: 0.85rem;
}

/* CTA SECTION */
.cta-section {
    background: linear-gradient(135deg, var(--blue-600) 0%, #1E40AF 100%);
    padding: 80px 0; text-align: center;
}
.cta-section__title {
    color: white; font-size: clamp(1.5rem, 3vw, 2.2rem);
    font-weight: 800; margin-bottom: 12px; letter-spacing: -0.02em;
}
.cta-section__subtitle {
    color: rgba(255,255,255,0.7); font-size: 1rem;
    margin-bottom: 32px;
}
.cta-section__btn {
    display: inline-flex; align-items: center; gap: 8px;
    background: white; color: var(--blue-600); padding: 16px 32px;
    border-radius: 12px; font-size: 1.05rem; font-weight: 700;
    text-decoration: none; transition: transform 0.2s, box-shadow 0.2s;
}
.cta-section__btn:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.2); }

@media (max-width: 768px) {
    .container { padding: 0 max(20px, 5vw); }
    .nav__inner { height: 52px; padding: 0 max(16px, 5vw); }
    .nav__logo { font-size: 0.95rem; }
    .nav__links { gap: 12px; }
    .nav__link { font-size: 0.75rem; }
    .nav__cta { padding: 7px 14px; font-size: 0.75rem; white-space: nowrap; border-radius: 6px; }
    .cta-section { padding: 56px 0; }
    .cta-section__title { font-size: 1.3rem; margin-bottom: 20px; }
    .cta-section__btn { padding: 14px 28px; font-size: 0.95rem; }
}
"""

LISTING_CSS = """\
.blog-header {
    padding: 120px 0 40px;
    text-align: center;
}
.blog-header__title {
    font-size: clamp(2rem, 4vw, 3rem);
    font-weight: 800; letter-spacing: -0.03em;
}
.blog-header__subtitle {
    color: var(--gray-500); font-size: 1.05rem;
    margin-top: 12px;
}
.blog-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 24px;
    max-width: 860px;
    margin: 0 auto;
    padding-bottom: 80px;
}
.blog-card {
    background: white; border-radius: 16px; padding: 28px;
    border: 1px solid var(--gray-200);
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    transition: transform 0.3s, box-shadow 0.3s;
    text-decoration: none; color: inherit;
    display: flex; flex-direction: column;
}
.blog-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 32px rgba(0,0,0,0.08);
}
.blog-card__date {
    font-size: 0.8rem; color: var(--gray-400);
    font-weight: 500; margin-bottom: 8px;
}
.blog-card__title {
    font-size: 1.15rem; font-weight: 700;
    line-height: 1.35; margin-bottom: 10px;
}
.blog-card__desc {
    font-size: 0.9rem; color: var(--gray-500);
    line-height: 1.6; flex: 1;
}
.blog-card__link {
    margin-top: 16px; font-size: 0.875rem;
    color: var(--blue-600); font-weight: 600;
}
@media (max-width: 768px) {
    .blog-header { padding: 80px 0 28px; }
    .blog-grid { grid-template-columns: 1fr; gap: 16px; padding-bottom: 56px; }
    .blog-card { padding: 20px; }
}
"""

ARTICLE_CSS = """\
.article {
    padding: 120px 0 60px;
}
.article .container {
    max-width: 720px;
}
.article__header {
    margin-bottom: 40px;
}
.article__back {
    display: inline-block;
    color: var(--blue-600); text-decoration: none;
    font-size: 0.875rem; font-weight: 500;
    margin-bottom: 24px;
    transition: color 0.2s;
}
.article__back:hover { color: var(--blue-700); }
.article__date {
    display: block;
    font-size: 0.85rem; color: var(--gray-400);
    font-weight: 500; margin-bottom: 12px;
}
.article__title {
    font-size: clamp(1.75rem, 3.5vw, 2.5rem);
    font-weight: 800; line-height: 1.2;
    letter-spacing: -0.02em;
}
.article__body {
    font-size: 1.05rem; line-height: 1.8;
    color: var(--gray-700);
}
.article__body h2 {
    font-size: 1.5rem; font-weight: 700;
    margin: 40px 0 16px; color: var(--gray-900);
    letter-spacing: -0.01em;
}
.article__body h3 {
    font-size: 1.2rem; font-weight: 700;
    margin: 32px 0 12px; color: var(--gray-900);
}
.article__body p {
    margin-bottom: 20px;
}
.article__body ul, .article__body ol {
    margin: 0 0 20px 24px;
}
.article__body li {
    margin-bottom: 8px;
}
.article__body blockquote {
    border-left: 3px solid var(--blue-600);
    padding: 12px 20px; margin: 24px 0;
    background: var(--blue-50); border-radius: 0 12px 12px 0;
    color: var(--gray-700); font-style: italic;
}
.article__body code {
    background: var(--gray-100); padding: 2px 6px;
    border-radius: 4px; font-size: 0.9em;
}
.article__body pre {
    background: var(--gray-900); color: var(--gray-100);
    padding: 20px; border-radius: 12px;
    overflow-x: auto; margin: 24px 0;
    font-size: 0.9rem; line-height: 1.6;
}
.article__body pre code {
    background: none; padding: 0; border-radius: 0;
    font-size: inherit; color: inherit;
}
.article__body img {
    max-width: 100%; height: auto;
    border-radius: 12px; margin: 24px 0;
}
.article__body a {
    color: var(--blue-600); text-decoration: underline;
    text-underline-offset: 2px;
}
.article__body a:hover { color: var(--blue-700); }
.article__body strong { color: var(--gray-900); }
.article__footer {
    margin-top: 48px; padding-top: 24px;
    border-top: 1px solid var(--gray-200);
}
@media (max-width: 768px) {
    .article { padding: 72px 0 40px; }
    .article__body { font-size: 1rem; }
    .article__body h2 { font-size: 1.3rem; margin: 32px 0 12px; }
    .article__body h3 { font-size: 1.1rem; margin: 24px 0 10px; }
}
"""

METRIKA = """\
<script type="text/javascript">
    (function(m,e,t,r,i,k,a){
        m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
        m[i].l=1*new Date();
        for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
        k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
    })(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id=107010325', 'ym');
    ym(107010325, 'init', {ssr:true, webvisor:true, clickmap:true, ecommerce:"dataLayer", referrer: document.referrer, url: location.href, accurateTrackBounce:true, trackLinks:true});
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/107010325" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
"""

NAV_HTML = f"""\
<nav class="nav" id="nav">
    <div class="nav__inner">
        <a href="/" class="nav__logo">Фото для резюме</a>
        <div class="nav__links">
            <a href="/blog/" class="nav__link">Блог</a>
            <a href="{BOT_URL}" class="nav__cta">Попробовать бесплатно</a>
        </div>
    </div>
</nav>
"""

NAV_JS = """\
<script>
const nav = document.getElementById('nav');
window.addEventListener('scroll', () => {
    nav.classList.toggle('nav--scrolled', window.scrollY > 10);
});
</script>
"""

FOOTER_HTML = """\
<footer class="footer">
    <div class="container">&copy; 2026 Фото для резюме. Все права защищены.</div>
</footer>
"""

CTA_HTML = f"""\
<section class="cta-section">
    <div class="container">
        <h2 class="cta-section__title">Попробуйте прямо сейчас</h2>
        <p class="cta-section__subtitle">Первое фото бесплатно — без регистрации и карты</p>
        <a href="{BOT_URL}" class="cta-section__btn">Открыть бот в Telegram &rarr;</a>
    </div>
</section>
"""


def build_listing_page(posts: list[dict]) -> str:
    cards = "\n".join(
        f'''            <a href="/blog/{p["slug"]}/" class="blog-card">
                <div class="blog-card__date">{format_date_ru(p["date_obj"])}</div>
                <h2 class="blog-card__title">{p["title"]}</h2>
                <p class="blog-card__desc">{p["description"]}</p>
                <span class="blog-card__link">Читать далее &rarr;</span>
            </a>'''
        for p in posts
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Блог — Фото для резюме</title>
    <meta name="description" content="Советы по фотографии для резюме, карьере и использованию AI для создания профессиональных портретов.">
    <link rel="canonical" href="{SITE_URL}/blog/">
    <meta property="og:title" content="Блог — Фото для резюме">
    <meta property="og:description" content="Советы по фотографии для резюме, карьере и использованию AI для создания профессиональных портретов.">
    <meta property="og:type" content="website">
    <meta property="og:url" content="{SITE_URL}/blog/">
    <meta property="og:site_name" content="Фото для резюме">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
{BASE_CSS}
{LISTING_CSS}
    </style>
    {METRIKA}
</head>
<body>
{NAV_HTML}
<section class="blog-header">
    <div class="container">
        <h1 class="blog-header__title">Блог</h1>
        <p class="blog-header__subtitle">Советы по фотографии, карьере и использованию AI</p>
    </div>
</section>

<section>
    <div class="container">
        <div class="blog-grid">
{cards}
        </div>
    </div>
</section>

{CTA_HTML}
{FOOTER_HTML}
{NAV_JS}
</body>
</html>"""


def build_article_page(post: dict) -> str:
    body_html = render_markdown(post["body_md"])
    date_display = format_date_ru(post["date_obj"])
    date_iso = post["date_obj"].strftime("%Y-%m-%d")

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{post["title"]} — Блог Фото для резюме</title>
    <meta name="description" content="{post["description"]}">
    <link rel="canonical" href="{SITE_URL}/blog/{post["slug"]}/">
    <meta property="og:title" content="{post["title"]}">
    <meta property="og:description" content="{post["description"]}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="{SITE_URL}/blog/{post["slug"]}/">
    <meta property="og:site_name" content="Фото для резюме">
    <meta name="twitter:card" content="summary">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
{BASE_CSS}
{ARTICLE_CSS}
    </style>
    {METRIKA}
</head>
<body>
{NAV_HTML}
<article class="article">
    <div class="container">
        <div class="article__header">
            <a href="/blog/" class="article__back">&larr; Все статьи</a>
            <time class="article__date" datetime="{date_iso}">{date_display}</time>
            <h1 class="article__title">{post["title"]}</h1>
        </div>
        <div class="article__body">
            {body_html}
        </div>
        <div class="article__footer">
            <a href="/blog/" class="article__back">&larr; Вернуться к блогу</a>
        </div>
    </div>
</article>

{CTA_HTML}
{FOOTER_HTML}
{NAV_JS}
</body>
</html>"""


def build():
    posts = []
    for f in sorted(POSTS_DIR.glob("*.md")):
        post = parse_post(f)
        if post:
            posts.append(post)

    if not posts:
        print("No published posts found in", POSTS_DIR)
        return

    posts.sort(key=lambda p: p["date_obj"], reverse=True)

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    for post in posts:
        article_html = build_article_page(post)
        slug_dir = OUTPUT_DIR / post["slug"]
        slug_dir.mkdir(parents=True, exist_ok=True)
        (slug_dir / "index.html").write_text(article_html, encoding="utf-8")
        print(f"  Built: /blog/{post['slug']}/")

    listing_html = build_listing_page(posts)
    (OUTPUT_DIR / "index.html").write_text(listing_html, encoding="utf-8")
    print(f"\nBuilt {len(posts)} post(s) to {OUTPUT_DIR}/")


def deploy():
    """Deploy via SCP (for use from local machine)."""
    print("\nDeploying to server...")
    subprocess.run(["ssh", SERVER, f"mkdir -p {REMOTE_DIR}"], check=True)

    for html_file in OUTPUT_DIR.rglob("index.html"):
        rel_path = html_file.relative_to(OUTPUT_DIR)
        remote_subdir = f"{REMOTE_DIR}/{rel_path.parent}"
        remote_path = f"{REMOTE_DIR}/{rel_path}"
        subprocess.run(["ssh", SERVER, f"mkdir -p {remote_subdir}"], check=True)
        subprocess.run(["scp", str(html_file), f"{SERVER}:{remote_path}"], check=True)
        print(f"  Deployed: /blog/{rel_path}")

    print(f"\nDone! Visit {SITE_URL}/blog/")


def local_deploy():
    """Copy output directly to /var/www/landing/blog/ (for use on the server)."""
    remote = Path(REMOTE_DIR)
    print(f"\nLocal deploy to {remote}...")

    for html_file in OUTPUT_DIR.rglob("index.html"):
        rel_path = html_file.relative_to(OUTPUT_DIR)
        dest = remote / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(html_file, dest)
        print(f"  Copied: /blog/{rel_path}")

    print(f"\nDone! Visit {SITE_URL}/blog/")


if __name__ == "__main__":
    build()
    if "--local-deploy" in sys.argv:
        local_deploy()
    elif "--deploy" in sys.argv:
        deploy()

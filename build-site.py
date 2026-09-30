"""Собирает сайт для публикации в папку dist/ — по отдельной странице на язык:

    dist/index.html      русский (главная)
    dist/kk/index.html   қазақша
    dist/en/index.html   English
    dist/zh/index.html   中文

Каждая страница прогоняется через headless Chrome, поэтому весь текст, карточки
туров, FAQ и разметка schema.org уже лежат в HTML — поисковик видит их без JS.
В <head> добавляются canonical, hreflang и Open Graph; рядом — sitemap.xml
и robots.txt. Публиковать нужно содержимое dist/ целиком.

Запуск:  python3 build-site.py
(Chrome ищется по стандартному пути macOS; другой путь — через CHROME=...)
"""
import datetime, html as htmlmod, os, pathlib, re, shutil, subprocess, tempfile

root = pathlib.Path(__file__).resolve().parent
dist = root / "dist"
src = (root / "index.html").read_text(encoding="utf-8")

CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SITE = re.search(r"const SITE_URL = '([^']+)'", src).group(1)
assert SITE.endswith("/"), SITE

LANGS = ["ru", "kk", "en", "zh"]
PATH = {"ru": "", "kk": "kk/", "en": "en/", "zh": "zh/"}
OG_LOCALE = {"ru": "ru_RU", "kk": "kk_KZ", "en": "en_US", "zh": "zh_CN"}
X_DEFAULT = "en"          # для языков, которых на сайте нет
OG_IMAGE = "images/hero-bokty-sm.jpg"   # 1200×675


def render(lang):
    """Страница с data-page-lang, отрендеренная Chrome, как строка HTML."""
    page = src.replace('<html lang="ru">', f'<html lang="{lang}" data-page-lang="{lang}">', 1)
    assert page != src
    # Временный файл кладём в корень проекта, чтобы относительные images/ находились.
    tmp = root / f".render-{lang}.html"
    tmp.write_text(page, encoding="utf-8")
    try:
        with tempfile.TemporaryDirectory() as profile:
            # Сеть отключена: шрифты Google для DOM не нужны, а зависший запрос
            # не даёт наступить событию load, и --dump-dom ждёт бесконечно.
            proc = subprocess.Popen(
                [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
                 "--hide-scrollbars", f"--user-data-dir={profile}", "--window-size=1280,900",
                 "--host-resolver-rules=MAP * ~NOTFOUND",
                 "--dump-dom", tmp.as_uri()],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
            # Chrome на macOS иногда не завершается после вывода DOM —
            # читаем до </html> и закрываем его сами.
            out = ""
            for line in proc.stdout:
                out += line
                if "</html>" in line:
                    break
            proc.kill()
            proc.wait()
    finally:
        tmp.unlink()
    assert "multidayGrid" in out and 'class="tcard' in out, f"{lang}: page did not render"
    return out


def drop_reveal_state(page):
    """Снимок не должен «запоминать», какие блоки уже проявились при рендере."""
    def fix(m):
        cls = m.group(1).split()
        if "reveal" in cls:
            cls = [c for c in cls if c != "in"]
        return 'class="%s"' % " ".join(cls)
    return re.sub(r'class="([^"]*)"', fix, page)


def head_tags(lang, title, desc):
    url = SITE + PATH[lang]
    e = lambda v: htmlmod.escape(v, quote=True)
    tags = [f'<link rel="canonical" href="{url}">']
    tags += [f'<link rel="alternate" hreflang="{l}" href="{SITE + PATH[l]}">' for l in LANGS]
    tags.append(f'<link rel="alternate" hreflang="x-default" href="{SITE + PATH[X_DEFAULT]}">')
    tags += [
        '<meta name="robots" content="index, follow, max-image-preview:large">',
        '<meta name="theme-color" content="#0A3B43">',
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="Visit Aktau">',
        f'<meta property="og:title" content="{e(title)}">',
        f'<meta property="og:description" content="{e(desc)}">',
        f'<meta property="og:url" content="{url}">',
        f'<meta property="og:image" content="{SITE + OG_IMAGE}">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="675">',
        f'<meta property="og:locale" content="{OG_LOCALE[lang]}">',
    ]
    tags += [f'<meta property="og:locale:alternate" content="{OG_LOCALE[l]}">' for l in LANGS if l != lang]
    tags += [
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{e(title)}">',
        f'<meta name="twitter:description" content="{e(desc)}">',
        f'<meta name="twitter:image" content="{SITE + OG_IMAGE}">',
    ]
    return "\n  ".join(tags)


def build(lang):
    page = drop_reveal_state(render(lang))
    # /kk/, /en/, /zh/ лежат во вложенных папках — картинки берём от корня сайта.
    # (video/ — только пути к файлам, а не MIME-тип type="video/mp4")
    page = re.sub(r"""(?<=["'(\s,])(images|video)/(?!mp4["'])""", r"/\1/", page)

    title = htmlmod.unescape(re.search(r"<title>(.*?)</title>", page, re.S).group(1))
    m = re.search(r'<meta name="description"[^>]*>', page, re.S)
    desc = htmlmod.unescape(re.search(r'content="([^"]*)"', m.group(0)).group(1))
    page = page[:m.end()] + "\n  " + head_tags(lang, title, desc) + page[m.end():]

    if not page.lstrip().lower().startswith("<!doctype"):
        page = "<!DOCTYPE html>\n" + page
    out = dist / PATH[lang] / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"{lang}: {out.relative_to(root)}  {len(page) // 1024} KB  «{title}»")


def sitemap():
    today = datetime.date.today().isoformat()
    alts = "".join(
        f'\n    <xhtml:link rel="alternate" hreflang="{l}" href="{SITE + PATH[l]}"/>' for l in LANGS
    ) + f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{SITE + PATH[X_DEFAULT]}"/>'
    urls = "".join(
        f"\n  <url>\n    <loc>{SITE + PATH[l]}</loc>\n    <lastmod>{today}</lastmod>{alts}\n  </url>"
        for l in LANGS)
    (dist / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">'
        f"{urls}\n</urlset>\n", encoding="utf-8")
    (dist / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {SITE}sitemap.xml\n", encoding="utf-8")


if dist.exists():
    shutil.rmtree(dist)
dist.mkdir()
for lang in LANGS:
    build(lang)
shutil.copytree(root / "images", dist / "images", ignore=shutil.ignore_patterns(".DS_Store"))
shutil.copytree(root / "video", dist / "video", ignore=shutil.ignore_patterns(".DS_Store"))
# Google и браузеры запрашивают /favicon.ico от корня сайта, даже без <link rel="icon">.
shutil.copy(root / "images/icons/favicon.ico", dist / "favicon.ico")
sitemap()
print("sitemap.xml, robots.txt, favicon.ico, images/, video/ → dist/")

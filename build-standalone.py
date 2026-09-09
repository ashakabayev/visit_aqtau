"""Собирает visit-aktau-standalone.html — один файл со всеми фото внутри
(base64), чтобы страница открывалась откуда угодно, без папки images/.

Запуск:  python3 build-standalone.py
"""
import base64, re, pathlib

root = pathlib.Path(__file__).resolve().parent
html = (root / "index.html").read_text(encoding="utf-8")

# 1. Preload of the hero is pointless once inlined, and would duplicate a 2MB blob.
html = re.sub(r'\n\s*<link rel="preload" as="image"[^>]*>\n', '\n', html, count=1)

# 2. <picture> -> plain <img>: webp is embedded directly, so the jpg fallback
#    would only double the file size.
old_pic = """const pic = (src, alt = '') => `<picture><source srcset="${src.replace(/\\.jpg$/, '.webp')}" type="image/webp">
      <img src="${src}" alt="${alt}" loading="lazy"></picture>`;"""
new_pic = """const pic = (src, alt = '') => `<img src="${src}" alt="${alt}" loading="lazy">`;"""
assert old_pic in html
html = html.replace(old_pic, new_pic)

# 3. Drop the image-set() @supports blocks — same reason.
def strip_supports(s):
    while True:
        m = re.search(r'\n[ \t]*@supports \(background-image: image-set\(', s)
        if not m:
            return s
        i, depth = s.index('{', m.end()), 0
        for j in range(i, len(s)):
            depth += (s[j] == '{') - (s[j] == '}')
            if depth == 0:
                s = s[:m.start()] + s[j + 1:]
                break
html = strip_supports(html)

# 4. Photos referenced from JS are quoted string literals, and several are reused
#    across sections. Hoist each blob into an IMG map so it is embedded once.
def uri(rel):
    src = root / rel
    use = src.with_suffix(".webp") if src.with_suffix(".webp").exists() else src
    mime = "image/webp" if use.suffix == ".webp" else "image/jpeg"
    return "data:%s;base64,%s" % (mime, base64.b64encode(use.read_bytes()).decode())

# CSS url('...') is single-quoted too, so inline it before touching JS literals.
for rel in sorted(set(re.findall(r"url\('(images/[A-Za-z0-9._/-]+\.(?:jpg|jpeg|png|webp))'\)", html)),
                  key=len, reverse=True):
    assert (root / rel).exists(), rel
    html = html.replace("url('%s')" % rel, "url('%s')" % uri(rel))

js_paths = sorted(set(re.findall(r"'(images/[A-Za-z0-9._/-]+\.(?:jpg|jpeg|png|webp))'", html)))
missing = [r for r in js_paths if not (root / r).exists()]
assert not missing, missing
# The key becomes a JS identifier (IMG.<key>), so it must not start with a digit
# and must stay unique: per-location folders all hold 01.jpg..04.jpg, so the file
# stem alone would collide and emit invalid `IMG.01`.
keys = {rel: 'img_' + re.sub(r'\W', '_', rel[len('images/'):].rsplit('.', 1)[0])
        for rel in js_paths}
assert len(set(keys.values())) == len(keys), 'duplicate IMG keys'

table = "const IMG = {\n" + "".join(
    "      %s: '%s',\n" % (keys[rel], uri(rel)) for rel in js_paths) + "    };\n    "
anchor = "    const artSvg = "
assert anchor in html
html = html.replace(anchor, "    " + table + "const artSvg = ", 1)
for rel in js_paths:
    html = html.replace("'%s'" % rel, "IMG.%s" % keys[rel])

# 5. Nothing should reference the images/ folder any more.
# (the only survivors are prose mentions inside comments, which load nothing)
for line in html.splitlines():
    if re.search(r'images/[A-Za-z0-9._/-]+\.(?:jpg|jpeg|png|webp)', line) \
       and not re.search(r'(Файл|<!--)', line):
        raise SystemExit("unreplaced reference: " + line.strip())

out = root / "visit-aktau-standalone.html"
out.write_text(html, encoding="utf-8")
print("embedded %d images -> %s (%.1f MB)" % (len(js_paths), out.name, out.stat().st_size / 1e6))

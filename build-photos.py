"""Готовит веб-версии фото из папки заказчика в images/loc/<локация>/NN.jpg|webp.

Из каждой папки берём до MAX_PER лучших кадров: сначала горизонтальные
(они лучше ложатся в карточки и карусель), затем квадратные и вертикальные,
внутри группы — по убыванию разрешения. Дубликаты отсеиваются по хешу
уменьшенной копии. Видео игнорируются.

Запуск:  python3 build-photos.py
"""
import hashlib, pathlib, shutil, subprocess, sys
from PIL import Image, ImageOps

SRC = pathlib.Path("/Users/shakabayev/Downloads/сайт фото")
OUT = pathlib.Path(__file__).resolve().parent / "images" / "loc"
MAX_PER, MAX_W, JPG_Q, WEBP_Q = 4, 1200, 76, 70

# папка заказчика -> ключ локации в LOC
FOLDERS = {
    "Айрақты": "airakty", "Акеспе": "akespe", "Бозжыра": "bozzhyra", "Боқты": "bokty",
    "Жығылған": "zhygylgan", "Капамсай": "kapamsai", "Көкала": "kokala", "Торыш": "torysh",
    "Тұзбайыр": "tuzbair", "Шерқала": "sherkala", "карынжарык": "karynzharyk",
    "Қызылқұп": "kyzylkup", "Шакпак ата": "shakpak", "Ыбықты сай": "ybykty",
    "Қараман Ата": "karaman-ata",
}
EXT = {".jpg", ".jpeg", ".png", ".webp"}


def pick(folder):
    """Лучшие кадры папки: горизонтальные вперёд, дубликаты прочь."""
    cands, seen = [], set()
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() not in EXT:
            continue
        try:
            im = ImageOps.exif_transpose(Image.open(p))
        except Exception as e:
            print("   пропуск %s (%s)" % (p.name, e))
            continue
        sig = hashlib.md5(im.convert("L").resize((16, 16)).tobytes()).digest()
        if sig in seen:
            continue
        seen.add(sig)
        w, h = im.size
        shape = 0 if w > h * 1.15 else (1 if w > h * 0.9 else 2)   # гор. / квадрат / верт.
        cands.append((shape, -w * h, p))
    cands.sort(key=lambda c: (c[0], c[1]))
    return [p for _, _, p in cands[:MAX_PER]]


def emit(src, dst_jpg):
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    if im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
    im.save(dst_jpg, "JPEG", quality=JPG_Q, optimize=True, progressive=True)
    subprocess.run(["cwebp", "-quiet", "-q", str(WEBP_Q), str(dst_jpg),
                    "-o", str(dst_jpg.with_suffix(".webp"))], check=True)
    return im.size


if not SRC.is_dir():
    sys.exit("нет папки с исходниками: %s" % SRC)

total = 0
for folder, key in FOLDERS.items():
    d = SRC / folder
    if not d.is_dir():
        print("!! нет папки", folder); continue
    chosen = pick(d)
    if not chosen:
        print("-- %s: фото нет, останется запасная SVG-иллюстрация" % key); continue
    dest = OUT / key
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    sizes = [emit(p, dest / ("%02d.jpg" % (i + 1))) for i, p in enumerate(chosen)]
    kb = sum(f.stat().st_size for f in dest.iterdir()) // 1024
    total += len(chosen)
    print("%-12s %d шт  %s  %d КБ" % (key, len(chosen), sizes[0], kb))

print("готово: %d фото" % total)

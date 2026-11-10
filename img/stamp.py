# Puts the destination shop's logo on a clean product photo (top-left by default, or the calmest corner).
import io
import numpy as np
from PIL import Image, ImageFilter

def _corner_stats(im, box):
    a = np.asarray(im.crop(box).convert("L"), dtype=np.float32)
    return float(a.mean()), float(a.std())

def stamp(im, logo, rel_w=0.22, margin=0.03):
    im = im.convert("RGB")
    w, h = im.size
    lw = max(40, int(w * rel_w)); lh = max(1, int(lw * logo.size[1] / logo.size[0]))
    lg = logo.convert("RGBA").resize((lw, lh), Image.LANCZOS)
    mg = int(w * margin)
    spots = {"tl": (mg, mg), "tr": (w - lw - mg, mg), "bl": (mg, h - lh - mg), "br": (w - lw - mg, h - lh - mg)}
    best, best_score, best_stats = "tl", None, None
    for name, (x, y) in spots.items():
        mean, std = _corner_stats(im, (x, y, x + lw, y + lh))
        score = std + (0 if name == "tl" else 8) + (0 if mean > 150 else 10)
        if best_score is None or score < best_score:
            best, best_score, best_stats = name, score, (mean, std)
    x, y = spots[best]
    mean, std = best_stats
    out = im.copy()
    if std > 14 or mean < 175:
        # busy or dark corner: soft white plate under the logo so it stays readable
        pad = int(lh * 0.22)
        plate = Image.new("L", (lw + 2 * pad, lh + 2 * pad), 0)
        plate.paste(215, (pad // 2, pad // 2, lw + 2 * pad - pad // 2, lh + 2 * pad - pad // 2))
        plate = plate.filter(ImageFilter.GaussianBlur(max(2, pad // 2)))
        out.paste(Image.new("RGB", plate.size, (255, 255, 255)), (x - pad, y - pad), plate)
    out.paste(lg, (x, y), lg)
    return out, best

def to_jpeg(im, max_side=1000, quality=88):
    im = im.convert("RGB")
    w, h = im.size
    s = max_side / max(w, h)
    if s < 1:
        im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, "JPEG", quality=quality, optimize=True)
    return b.getvalue()

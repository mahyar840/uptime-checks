# Image text check: reads a queue of product-image URLs from the worker, runs OCR on each
# (no AI service, no paid API) and posts back the texts it found with their boxes (in percent).
# The worker decides what counts as a foreign watermark. Nothing secret is printed.
import io, json, os, re, sys, time, urllib.request

import numpy as np
from PIL import Image, ImageOps

U = os.environ.get("U", "").rstrip("/")
K = os.environ.get("K", "")
RUN_SECONDS = int(os.environ.get("RUN_SECONDS", "3000"))
IDLE_SLEEP = int(os.environ.get("IDLE_SLEEP", "20"))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

_ocr = None
def ocr_engine():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr

def http(method, path, body=None, timeout=40):
    req = urllib.request.Request(U + path, method=method, headers={"x-check-key": K, "Content-Type": "application/json", "User-Agent": "imgcheck"},
                                 data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")

def download(url):
    last = None
    for ref in ("https://torob.com/", None):
        try:
            h = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
            if ref: h["Referer"] = ref
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
                data = r.read(12_000_000)
            if len(data) > 1500:
                return data
        except Exception as e:  # noqa
            last = e
    raise RuntimeError("download failed: %s" % str(last)[:80])

def load(data, side=1000):
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    w, h = im.size
    s = side / max(w, h)
    if s < 1 or s > 1.6:
        s = min(s, 2.0)
        im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    return im

def run_ocr(im):
    """Returns [(text, score, [x0,y0,x1,y1] in percent)]"""
    arr = np.asarray(im)[:, :, ::-1].copy()  # RGB -> BGR
    res, _ = ocr_engine()(arr)
    h, w = arr.shape[:2]
    out = []
    for item in res or []:
        box, text, score = item[0], str(item[1]).strip(), float(item[2])
        if not text:
            continue
        xs = [p[0] for p in box]; ys = [p[1] for p in box]
        out.append((text, score, [round(100 * min(xs) / w, 1), round(100 * min(ys) / h, 1), round(100 * max(xs) / w, 1), round(100 * max(ys) / h, 1)]))
    return out

def persian_words(im):
    """Persian words with tesseract (only confident ones); the worker keeps shop-like words only."""
    try:
        import pytesseract
        d = pytesseract.image_to_data(im, lang="fas", config="--psm 11", output_type=pytesseract.Output.DICT)
    except Exception:
        return []
    w, h = im.size
    out = []
    for i, t in enumerate(d.get("text", [])):
        t = (t or "").strip()
        try: conf = float(d["conf"][i])
        except Exception: conf = -1
        if conf < 72 or len(t) < 4 or not re.search(r"[؀-ۿ]{4,}", t):
            continue
        x, y, bw, bh = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        out.append((t, conf / 100.0, [round(100 * x / w, 1), round(100 * y / h, 1), round(100 * (x + bw) / w, 1), round(100 * (y + bh) / h, 1)]))
    return out

def check_bytes(data):
    im = load(data)
    found = {}
    def add(items, src):
        for text, score, box in items:
            if score < 0.5 and src != "fa":
                continue
            key = re.sub(r"\s+", "", text.lower())
            if key not in found or found[key]["score"] < score:
                found[key] = {"text": text[:60], "kind": "text", "box": box, "score": round(score, 2), "src": src}
    add(run_ocr(im), "ocr")
    # faint, semi-transparent marks: boost local contrast and read again
    try:
        g = ImageOps.autocontrast(ImageOps.equalize(im.convert("L")), cutoff=1).convert("RGB")
        add(run_ocr(g), "ocr2")
    except Exception:
        pass
    add(persian_words(im), "fa")
    marks = sorted(found.values(), key=lambda m: -m["score"])[:40]
    return {"ok": True, "w": im.size[0], "h": im.size[1], "marks": marks}

def check_url(url):
    try:
        r = check_bytes(download(url))
    except Exception as e:
        r = {"ok": False, "err": str(e)[:100], "marks": []}
    r["url"] = url
    return r

def main():
    if len(sys.argv) > 1:  # local test: python check.py file-or-url ...
        for a in sys.argv[1:]:
            r = check_bytes(open(a, "rb").read()) if os.path.exists(a) else check_url(a)
            print(json.dumps(r, ensure_ascii=False))
        return
    end = time.time() + RUN_SECONDS
    done = 0
    while time.time() < end:
        try:
            q = http("GET", "/gh/img-queue")
        except Exception as e:
            print("queue error", str(e)[:60]); time.sleep(60); continue
        urls = (q or {}).get("urls") or []
        if not urls:
            time.sleep(IDLE_SLEEP); continue
        items = []
        t0 = time.time()
        for u in urls[:20]:
            items.append(check_url(u))
        try:
            http("POST", "/gh/img-result", {"items": items})
            done += len(items)
            print("checked %d in %.1fs (ok=%d, with text=%d)" % (len(items), time.time() - t0, sum(1 for i in items if i["ok"]), sum(1 for i in items if i["marks"])))
        except Exception as e:
            print("result error", str(e)[:60]); time.sleep(30)
    print("done, total", done)

if __name__ == "__main__":
    main()

# Removes small marks (given as boxes in percent) from a product photo with the LaMa inpainting model (ONNX, CPU).
# Works on a crop around each group of boxes so the rest of the photo keeps its original pixels.
import os
import numpy as np
from PIL import Image, ImageFilter

MODEL = os.environ.get("LAMA_MODEL", os.path.join(os.path.dirname(__file__), "lama_fp32.onnx"))
_sess = None

def session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        so = ort.SessionOptions(); so.log_severity_level = 3
        _sess = ort.InferenceSession(MODEL, sess_options=so, providers=["CPUExecutionProvider"])
    return _sess

def _run(img512, mask512):
    x = (np.asarray(img512, dtype=np.float32) / 255.0).transpose(2, 0, 1)[None]
    m = (np.asarray(mask512, dtype=np.float32) / 255.0)[None, None]
    m = (m > 0.5).astype(np.float32)
    out = session().run(None, {"image": x, "mask": m})[0][0].transpose(1, 2, 0)
    if out.max() <= 1.5:
        out = out * 255.0
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

def box_mask(size, boxes, grow=0.35, pad=6):
    w, h = size
    m = Image.new("L", size, 0)
    px = m.load()
    rects = []
    for b in boxes:
        x0, y0, x1, y1 = [float(v) for v in b]
        x0, x1 = x0 * w / 100.0, x1 * w / 100.0
        y0, y1 = y0 * h / 100.0, y1 * h / 100.0
        gx, gy = (y1 - y0) * grow + pad, (y1 - y0) * grow + pad
        r = (max(0, int(x0 - gx)), max(0, int(y0 - gy)), min(w, int(x1 + gx) + 1), min(h, int(y1 + gy) + 1))
        if r[2] > r[0] and r[3] > r[1]:
            m.paste(255, r); rects.append(r)
    return m, rects

def inpaint(im, boxes, max_area=0.22):
    """im: PIL RGB. boxes: [[x0,y0,x1,y1] in percent]. Returns (PIL image, info)."""
    im = im.convert("RGB")
    w, h = im.size
    mask, rects = box_mask(im.size, boxes)
    if not rects:
        return im, {"ok": False, "err": "no boxes"}
    area = np.asarray(mask, dtype=np.uint8).mean() / 255.0
    if area > max_area:
        return im, {"ok": False, "err": "mask too large (%.0f%%)" % (area * 100)}
    out = im.copy()
    for r in rects:
        # square crop with context around the box
        bw, bh = r[2] - r[0], r[3] - r[1]
        side = int(min(max(w, h), max(256, 2.6 * max(bw, bh))))
        cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
        x0 = min(max(0, cx - side // 2), max(0, w - side)); y0 = min(max(0, cy - side // 2), max(0, h - side))
        x1, y1 = min(w, x0 + side), min(h, y0 + side)
        crop = out.crop((x0, y0, x1, y1)); cm = mask.crop((x0, y0, x1, y1))
        res = _run(crop.resize((512, 512), Image.LANCZOS), cm.resize((512, 512), Image.NEAREST)).resize(crop.size, Image.LANCZOS)
        # match the patch's tone to the pixels right around it (the model can drift slightly on flat backgrounds)
        try:
            ring = np.asarray(cm.filter(ImageFilter.MaxFilter(15)), dtype=np.uint8) > 0
            ring &= ~(np.asarray(cm, dtype=np.uint8) > 0)
            if ring.sum() > 50:
                src = np.asarray(crop, dtype=np.float32); dst = np.asarray(res, dtype=np.float32)
                diff = src[ring].mean(axis=0) - dst[ring].mean(axis=0)
                res = Image.fromarray(np.clip(dst + diff, 0, 255).astype(np.uint8))
        except Exception:
            pass
        soft = cm.filter(ImageFilter.GaussianBlur(2))
        crop.paste(res, (0, 0), soft)
        out.paste(crop, (x0, y0))
    return out, {"ok": True, "area": round(float(area), 3), "boxes": len(rects)}

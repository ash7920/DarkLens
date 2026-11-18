"""OCR helpers (Tesseract) — turn a screenshot into text lines with boxes."""
from __future__ import annotations

import io
import re
import shutil

import cv2
import numpy as np
from difflib import SequenceMatcher

from PIL import Image

try:
    import pytesseract
    import os as _os
    if _os.getenv("TESSERACT_CMD"):  # Windows: set to C:\\Program Files\\Tesseract-OCR\\tesseract.exe
        pytesseract.pytesseract.tesseract_cmd = _os.environ["TESSERACT_CMD"]
except Exception:  # pragma: no cover
    pytesseract = None

OCR_LANGS = "eng+deu+fra+spa+ita+nld"


def ocr_available() -> bool:
    if pytesseract is None:
        return False
    return shutil.which(pytesseract.pytesseract.tesseract_cmd) is not None


def _langs() -> str:
    try:
        have = set(pytesseract.get_languages(config=""))
        wanted = [l for l in OCR_LANGS.split("+") if l in have]
        return "+".join(wanted) or "eng"
    except Exception:
        return "eng"


def ocr_lines(img: Image.Image, min_conf: int = 40) -> list[dict]:
    """Return [{'id', 'text', 'bbox':[x,y,w,h], 'conf'}] grouped by Tesseract line."""
    if not ocr_available():
        return []
    gray = np.array(img.convert("L"))
    # Upscale to ~2700px wide (Tesseract prefers large glyphs), then adaptive
    # thresholding, which copes with dimmed overlays and coloured banners.
    scale = min(2.0, max(1.0, 2700 / gray.shape[1]))
    if scale > 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    binar = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
    data = pytesseract.image_to_data(Image.fromarray(binar), lang=_langs(), config="--psm 3",
                                     output_type=pytesseract.Output.DICT)
    groups: dict[tuple, list[int]] = {}
    for i, word in enumerate(data["text"]):
        if not word.strip() or float(data["conf"][i]) < min_conf:
            continue
        k = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        groups.setdefault(k, []).append(i)
    lines = []
    for idxs in groups.values():
        xs = [data["left"][i] for i in idxs]
        ys = [data["top"][i] for i in idxs]
        x2 = [data["left"][i] + data["width"][i] for i in idxs]
        y2 = [data["top"][i] + data["height"][i] for i in idxs]
        text = " ".join(data["text"][i] for i in idxs).strip()
        text = re.sub(r"(?<=\s)\|(?=\s)", "I", text)
        if len(text) < 2:
            continue
        lines.append({
            "text": text,
            "bbox": [int(min(xs) / scale), int(min(ys) / scale),
                     int((max(x2) - min(xs)) / scale), int((max(y2) - min(ys)) / scale)],
            "conf": float(sum(float(data["conf"][i]) for i in idxs) / len(idxs)),
        })
    # reading order, then merge lines on the same row that are close together
    lines.sort(key=lambda l: (round(l["bbox"][1] / 12), l["bbox"][0]))
    merged: list[dict] = []
    for l in lines:
        if merged:
            p = merged[-1]
            same_row = abs(p["bbox"][1] - l["bbox"][1]) < max(8, p["bbox"][3] * 0.6)
            gap = l["bbox"][0] - (p["bbox"][0] + p["bbox"][2])
            if same_row and 0 <= gap < max(25, p["bbox"][3] * 1.5):
                x0 = p["bbox"][0]
                y0 = min(p["bbox"][1], l["bbox"][1])
                x1 = l["bbox"][0] + l["bbox"][2]
                y1 = max(p["bbox"][1] + p["bbox"][3], l["bbox"][1] + l["bbox"][3])
                p["text"] += " " + l["text"]
                p["bbox"] = [x0, y0, x1 - x0, y1 - y0]
                continue
        merged.append(dict(l))
    for i, l in enumerate(merged, 1):
        l["id"] = i
    return merged


def load_image(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img


def to_png_bytes(img: Image.Image, max_side: int = 2000) -> bytes:
    if max(img.size) > max_side:
        r = max_side / max(img.size)
        img = img.resize((int(img.width * r), int(img.height * r)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def find_text_box(lines: list[dict], quote: str, min_ratio: float = 0.6):
    """Locate an evidence quote among OCR lines (fuzzy) and return its bbox."""
    if not quote:
        return None
    q = quote.lower().strip()
    best, best_r = None, 0.0
    for l in lines:
        t = l["text"].lower()
        r = 1.0 if q in t or (len(t) > 6 and t in q) else SequenceMatcher(None, q, t).ratio()
        if r > best_r:
            best, best_r = l, r
    return best["bbox"] if best and best_r >= min_ratio else None

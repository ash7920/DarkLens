"""
DarkLens web interface — FastAPI backend.

    uvicorn app.server:app --reload --port 8000      (then open http://localhost:8000)

Endpoints
  GET  /api/status                 engine / provider status
  GET  /api/taxonomy               categories, definitions, regulation pointers
  POST /api/analyze                upload a screenshot -> verdict, findings, boxes
  POST /api/analyze-url            render a live URL, analyse DOM + screenshot
  GET  /api/history                recent analyses
  GET  /api/results                evaluation results for the dashboard
  GET  /api/annotate/next          next item for an annotator
  POST /api/annotate               save a label
  GET  /api/annotate/agreement     inter-annotator agreement so far
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # models/, data/ and results/ are resolved relative to the repo root
# Interactive use: give up after ~1 minute of provider overload instead of the batch default (~4 min).
os.environ.setdefault("DARKLENS_RETRIES", "4")

from darklens.detection.detector import DarkPatternDetector  # noqa: E402
from darklens.detection.llm_client import LLMError, available_providers  # noqa: E402
from darklens.evaluation import annotation  # noqa: E402
from darklens.taxonomy import ALL_LABELS, CATEGORY_BY_KEY, NOT_DARK, display_name, taxonomy_as_dict  # noqa: E402

UPLOADS = ROOT / "data/uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 15 * 1024 * 1024

app = FastAPI(title="DarkLens", version="1.0", description="Dark-pattern detection for screenshots and live pages")
_detectors: dict[tuple, DarkPatternDetector] = {}
_lock = threading.Lock()


def get_detector(engine: str, mode: str) -> DarkPatternDetector:
    key = (engine, mode)
    with _lock:
        if key not in _detectors:
            _detectors[key] = DarkPatternDetector(engine=engine, mode=mode)
        return _detectors[key]


_LOCAL = {"127.0.0.1", "::1", "localhost"}


def _remote(request: Request) -> bool:
    """True for visitors who reach the app through a tunnel or the network rather than from the
    laptop itself. They get the offline engine only, so a shared labelling link can never spend
    the owner's language-model quota or make the laptop open arbitrary web pages."""
    h = request.headers
    if any(k in h for k in ("cf-connecting-ip", "cf-ray", "x-forwarded-for", "x-real-ip")):
        return True
    return (request.client.host if request.client else "") not in _LOCAL


def _read_json(f: Path):
    raw = f.read_bytes()
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:  # reports saved by an older version on Windows
        return json.loads(raw.decode("cp1252", errors="replace"))


def _save(result: dict, image_bytes: bytes, source: str) -> dict:
    h = hashlib.sha1(image_bytes).hexdigest()[:12]
    img_path = UPLOADS / f"{h}.png"
    img_path.write_bytes(image_bytes)
    result.update({"id": f"{h}_{int(time.time())}", "image_url": f"/api/file?path=data/uploads/{h}.png",
                   "source": source, "created": time.strftime("%Y-%m-%d %H:%M")})
    (UPLOADS / f"{result['id']}.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


@app.get("/api/status")
def status(request: Request):
    if _remote(request):
        return {"detector": {"engine": "offline", "note": "shared link: offline engine only"},
                "providers": {}, "offline_model": (ROOT / "models/tfidf_lr_binary.joblib").exists()}
    try:
        det = get_detector("auto", "multistage")
        info = det.info()
    except LLMError as exc:
        info = {"engine": "offline", "error": str(exc)}
    return {"detector": info, "providers": available_providers(),
            "offline_model": (ROOT / "models/tfidf_lr_binary.joblib").exists()}


@app.get("/api/taxonomy")
def taxonomy():
    return taxonomy_as_dict()


@app.post("/api/analyze")
def analyze(request: Request, file: UploadFile = File(...), engine: str = Form("auto"),
            mode: str = Form("multistage")):
    if engine not in ("auto", "llm", "offline") or mode not in ("multistage", "single"):
        raise HTTPException(400, "engine must be auto|llm|offline and mode multistage|single")
    if _remote(request):
        engine = "offline"
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image is larger than 15 MB. Crop it or save it as JPEG and try again.")
    if not data[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\xff\xd8\xff\xdb", b"RIFF") \
            and not data[:3] == b"\xff\xd8\xff":
        raise HTTPException(415, "Upload a PNG, JPEG or WebP screenshot.")
    try:
        det = get_detector(engine, mode)
        res = det.analyze_screenshot(data)
    except LLMError as exc:
        raise HTTPException(502, f"{exc} You can also switch the engine to Offline.")
    from darklens.detection.ocr import load_image, to_png_bytes
    return _save(res, to_png_bytes(load_image(data), max_side=4000), f"upload:{file.filename}")


class UrlIn(BaseModel):
    url: str
    engine: str = "auto"
    mode: str = "multistage"


@app.post("/api/analyze-url")
def analyze_url(body: UrlIn, request: Request):
    """Render a page with Playwright and combine DOM-level detection (exact element
    boxes, checkbox state) with screenshot detection."""
    from playwright.sync_api import sync_playwright

    from darklens.crawler.crawler import DEFAULT_UA
    from darklens.crawler.evidence_collector import collect_page_state
    from darklens.crawler.page_classifier import classify_page
    from darklens.pipeline import prefilter
    from darklens.preprocessing.segments import page_segments

    if _remote(request):
        raise HTTPException(403, "Inspecting a live URL only works on the laptop running DarkLens. Upload a screenshot instead.")
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(400, "Enter a full URL starting with http:// or https://")
    det = get_detector(body.engine, body.mode)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1366, "height": 900}, user_agent=DEFAULT_UA, locale="en-GB")
        page = ctx.new_page()
        try:
            page.goto(body.url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass
            page.wait_for_timeout(2500)
            state = collect_page_state(page, None, "initial")
            shot = page.screenshot(full_page=True, timeout=20000)
        except Exception as exc:
            browser.close()
            raise HTTPException(502, f"Could not load {body.url}: {type(exc).__name__}")
        browser.close()
    state["page_type"] = classify_page(state["url"], state["title"], state["text"], state["buttons"])
    segs = page_segments(state)
    keep = prefilter(segs, det)
    sent = [dict(s, id=i + 1) for i, s in enumerate(segs) if keep[i]]
    preds = det.classify_segments(sent, {"page type": state["page_type"], "url": state["url"],
                                         "language": state["language"]}) if sent else []
    dom_dets = []
    for s, p in zip(sent, preds):
        if p["label"] == NOT_DARK or p["confidence"] < det.dark_threshold:
            continue
        cat = CATEGORY_BY_KEY[p["label"]]
        dom_dets.append({"label": p["label"], "name": display_name(p["label"]), "color": cat.color,
                         "regulation": cat.regulation, "confidence": p["confidence"],
                         "evidence": f"{s['ui']} {s['text']}"[:300], "explanation": p["explanation"],
                         "box": s["bbox"], "source": f"dom:{det.info()['model']}"})
    res = det.analyze_screenshot(shot)
    merged = det._dedupe(dom_dets + res["detections"])
    res["detections"] = sorted(merged, key=lambda d: -d["confidence"])
    res["is_dark"] = bool(merged)
    res["verdict"] = "Dark pattern detected" if merged else "No dark pattern detected"
    if merged:
        res["confidence"] = round(max(d["confidence"] for d in merged), 3)
    cats = {}
    for d in merged:
        cats[d["label"]] = cats.get(d["label"], 0) + 1
    res["categories"] = [{"key": k, "name": display_name(k), "count": v, "regulation": CATEGORY_BY_KEY[k].regulation,
                          "color": CATEGORY_BY_KEY[k].color} for k, v in sorted(cats.items(), key=lambda x: -x[1])]
    res["page"] = {"url": state["url"], "title": state["title"], "page_type": state["page_type"],
                   "language": state["language"], "segments": len(segs), "sent_to_detector": len(sent)}
    return _save(res, shot, f"url:{body.url}")


@app.get("/api/history")
def history(limit: int = 12):
    files = sorted(UPLOADS.glob("*_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    out = []
    for f in files:
        try:
            r = _read_json(f)
        except (ValueError, OSError):
            continue
        out.append({"id": r["id"], "verdict": r["verdict"], "is_dark": r["is_dark"], "image_url": r["image_url"],
                    "source": r.get("source"), "created": r.get("created"),
                    "categories": [c["name"] for c in r.get("categories", [])]})
    return out


@app.get("/api/history/{rid}")
def history_item(rid: str):
    f = UPLOADS / f"{Path(rid).name}.json"
    if not f.exists():
        raise HTTPException(404, "Analysis not found")
    return _read_json(f)


@app.get("/api/file")
def get_file(path: str):
    p = (ROOT / path).resolve()
    allowed = [(ROOT / d).resolve() for d in ("data", "testbed", "results")]
    if not any(str(p).startswith(str(a)) for a in allowed) or not p.is_file():
        raise HTTPException(404, "File not found")
    if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(403, "Only images can be served")
    return FileResponse(p)


@app.get("/api/results")
def results():
    out = {}
    for f in sorted((ROOT / "results").glob("*.json")):
        try:
            out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
    return out


# ---------------------------------------------------------------- annotation
def _adjudication_ids() -> list[str]:
    """Items the two annotators disagreed on (written by scripts/agreement.py)."""
    import csv
    p = annotation.ANN_DIR / "adjudication.csv"
    if not p.exists():
        return []
    with open(p, encoding="utf-8", newline="") as f:
        return [row["segment_id"] for row in csv.DictReader(f)]


RECHECK_N = 50


def recheck_items(sample: list[dict]) -> list[dict]:
    """A fixed random 50 of the sample, in an order unrelated to the first pass, for a blind
    re-labelling by the same annotator (intra-rater agreement)."""
    return sorted(sample, key=lambda s: hashlib.sha1(("recheck:" + s["segment_id"]).encode()).hexdigest())[:RECHECK_N]


@app.get("/api/annotate/next")
def annotate_next(annotator: str, skip: str = "", adjudicate: int = 0, recheck: int = 0, segment_id: str = ""):
    """The next unlabelled item, or with segment_id the given item again (to correct a label:
    the newest label for an item is the one that counts)."""
    sample = annotation.load_sample()
    if not sample:
        return {"done": True, "total": 0, "message": "No annotation sample yet. Run "
                "scripts/make_annotation_sample.py after the crawl and detection steps."}
    labels = annotation.load_labels()
    safe = "".join(c for c in annotator.lower() if c.isalnum() or c in "-_")[:40]
    if adjudicate:
        ids = set(_adjudication_ids())
        if not ids:
            return {"done": True, "total": 0, "message": "No disagreements to settle. Run "
                    "python scripts/agreement.py first (it lists them)."}
        sample = [s for s in sample if s["segment_id"] in ids]
    elif recheck:
        sample = recheck_items(sample)
    mine = {k: v for k, v in labels.get(safe, {}).items() if any(s["segment_id"] == k for s in sample)}
    todo = [s for s in sample if s["segment_id"] not in mine]
    if segment_id:
        found = next((s for s in sample if s["segment_id"] == segment_id), None)
        if found is None:
            raise HTTPException(404, "Item not found")
        item = dict(found)
        item["your_label"] = mine.get(segment_id)
    elif not todo:
        return {"done": True, "total": len(sample), "labelled": len(mine)}
    else:
        skipped = set(skip.split(",")) if skip else set()
        item = dict(next((s for s in todo if s["segment_id"] not in skipped), todo[0]))
    for hidden in ("stratum", "weight", "occurrences"):  # annotators stay blind to the model's answer
        item.pop(hidden, None)
    if adjudicate:  # the adjudicator sees what the two annotators said (never the model)
        item["earlier"] = {n: l[item["segment_id"]] for n, l in sorted(labels.items())
                           if n != safe and item["segment_id"] in l}
    if item.get("screenshot"):
        item["screenshot_url"] = f"/api/file?path={Path(item['screenshot']).as_posix()}"
    return {"done": False, "total": len(sample), "labelled": len(mine), "item": item}


class LabelIn(BaseModel):
    annotator: str
    segment_id: str
    label: str
    note: str = ""


@app.post("/api/annotate")
def annotate(body: LabelIn):
    if body.label not in ALL_LABELS:
        raise HTTPException(400, f"label must be one of {ALL_LABELS}")
    if not body.annotator.strip():
        raise HTTPException(400, "Enter your name before labelling")
    annotation.save_label(body.annotator, body.segment_id, body.label, body.note)
    return {"ok": True}


def _sample_item(segment_id: str) -> dict:
    for it in annotation.load_sample():
        if it["segment_id"] == segment_id:
            return it
    raise HTTPException(404, "Item not found")


def _screenshot_for(item: dict):
    from PIL import Image
    raw = (item.get("screenshot") or "").replace("\\", "/")
    p = (ROOT / raw).resolve() if raw else None
    if not p or not str(p).startswith(str((ROOT / "data").resolve())) or not p.is_file():
        raise HTTPException(404, "No screenshot for this item")
    return Image.open(p).convert("RGB")


def _png(img, max_w: int, headers: dict | None = None) -> Response:
    import io
    if img.width > max_w:
        img = img.resize((max_w, int(img.height * max_w / img.width)))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    h = {"Cache-Control": "max-age=3600", "Access-Control-Expose-Headers": "X-Item-Shown"}
    h.update(headers or {})
    return Response(buf.getvalue(), media_type="image/png", headers=h)


def _item_box(item, img):
    """The item's box clipped to the screenshot, or None when the item cannot be seen in it
    (hidden element, closed menu, or below the point where the screenshot ends)."""
    W, H = img.size
    b = item.get("bbox")
    if not b or len(b) != 4:
        return None
    x, y, w, h = [int(v) for v in b]
    if w < 2 or h < 2:
        return None
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    if (x1 - x0) * (y1 - y0) < 0.3 * w * h:  # mostly outside the picture
        return None
    if _blank(img, (max(0, x0 - 60), max(0, y0 - 60), min(W, x1 + 60), min(H, y1 + 60))):
        return None
    return x0, y0, x1, y1


def _blank(img, region) -> bool:
    """True when the screenshot is empty around the item (content that had not loaded when the
    picture was taken, or a page too long for the browser to draw): an outline there means nothing."""
    from PIL import ImageStat
    stat = ImageStat.Stat(img.crop(region).convert("L"))
    return stat.stddev[0] < 4.0


def _outline(img, box, color, width):
    """Dim everything except the item and draw a thick frame round it."""
    from PIL import Image as _I, ImageDraw
    x0, y0, x1, y1 = box
    shade = _I.new("RGBA", img.size, (15, 20, 25, 95))
    ImageDraw.Draw(shade).rectangle((x0, y0, x1, y1), fill=(0, 0, 0, 0))
    out = _I.alpha_composite(img.convert("RGBA"), shade).convert("RGB")
    pad = width + 2
    ImageDraw.Draw(out).rectangle((x0 - pad, y0 - pad, x1 + pad, y1 + pad), outline=color, width=width)
    return out


@app.get("/api/annotate/crop")
def annotate_crop(segment_id: str, narrow: int = 0):
    """The part of the page around the item, with the item outlined: cut out here so it looks the
    same on any screen and loads fast over a slow link. narrow=1 gives a tighter cut for phones."""
    item = _sample_item(segment_id)
    img = _screenshot_for(item)
    W, H = img.size
    box = _item_box(item, img)
    if box is None:  # cannot point at it: show the top of the page and say so
        return _png(img.crop((0, 0, W, min(H, 900))), 1100, {"X-Item-Shown": "0"})
    x0, y0, x1, y1 = box
    if y1 - y0 > 1100:  # very tall item: keep its top part
        y1 = y0 + 1100
    mx, my, minw, minh = (140, 200, 560, 420) if narrow else (380, 260, 900, 480)
    cx0, cy0 = max(0, x0 - mx), max(0, y0 - my)
    cx1, cy1 = min(W, x1 + mx), min(H, y1 + my)
    if cx1 - cx0 < minw:
        g = (minw - (cx1 - cx0)) // 2
        cx0, cx1 = max(0, cx0 - g), min(W, cx1 + g)
    if cy1 - cy0 < minh:
        g = (minh - (cy1 - cy0)) // 2
        cy0, cy1 = max(0, cy0 - g), min(H, cy1 + g)
    crop = img.crop((cx0, cy0, cx1, cy1))
    lw = max(4, round((cx1 - cx0) / 110))  # stays visible after the picture is shrunk to fit
    crop = _outline(crop, (x0 - cx0, y0 - cy0, x1 - cx0, y1 - cy0), (13, 140, 140), lw)
    return _png(crop, 900 if narrow else 1200, {"X-Item-Shown": "1"})


@app.get("/api/annotate/full")
def annotate_full(segment_id: str):
    """The whole page screenshot with the item outlined (opened in a new tab)."""
    item = _sample_item(segment_id)
    img = _screenshot_for(item)
    box = _item_box(item, img)
    if box:
        img = _outline(img, box, (220, 30, 30), max(6, round(img.width / 200)))
    return _png(img, 1400)


@app.get("/api/annotate/agreement")
def annotate_agreement():
    return annotation.agreement()


@app.exception_handler(Exception)
def unhandled(request, exc):
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


app.mount("/", StaticFiles(directory=ROOT / "app/static", html=True), name="static")

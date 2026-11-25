"""
DarkLens detector — block diagram stage 4 (LLM-Based Dark Pattern Detection).

Inputs : clean text, UI elements (with state), relevant HTML context, screenshots
Outputs: pattern detection, category, evidence, confidence

Engines
  llm      – extract → infer → verify with any configured LLM (multistage), or a
             single inference call (mode="single", used for the ablation study)
  offline  – rules + TF-IDF classifier (+ OCR for screenshots); no API needed

Both engines return the same result structure, so the crawler pipeline, the
evaluation scripts and the web interface are engine-agnostic.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from PIL import Image

from ..preprocessing.lexicon import rule_label
from ..taxonomy import CATEGORY_BY_KEY, NOT_DARK, display_name
from .llm_client import LLMClient, LLMError, default_provider
from .ocr import find_text_box, load_image, ocr_available, ocr_lines, to_png_bytes
from .prompts import SYSTEM, few_shot_block, infer_screenshot_prompt, infer_segments_prompt, verify_prompt

VALID = set(CATEGORY_BY_KEY) | {NOT_DARK}
PRETICK_RE = re.compile(r"protect|insur|warrant|donat|newsletter|offer|marketing|partner|share|subscri|gift|"
                        r"priority|express|advertis|personali|\+\s?[€£$]|[€£$]\s?\d", re.I)
SURCHARGE_RE = re.compile(r"\+\s?[€£$]\s?\d|\+\s?\d+[.,]?\d*\s?(€|£|\$|eur)", re.I)


def _norm_label(lab) -> str:
    lab = str(lab or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {"pre_ticked_add_ons": "preselection", "sneaking": "preselection", "pre_selection": "preselection",
               "difficult_cancellation": "obstruction", "hard_to_cancel": "obstruction",
               "misdirection": "confirmshaming", "visual_interference": "interface_interference",
               "none": NOT_DARK, "not_a_dark_pattern": NOT_DARK, "no_dark_pattern": NOT_DARK,
               "low_stock": "scarcity", "countdown_timer": "urgency", "activity_notification": "social_proof"}
    lab = aliases.get(lab, lab)
    return lab if lab in VALID else NOT_DARK


def _clip(x, lo=0.0, hi=1.0):
    try:
        return max(lo, min(hi, float(x)))
    except (TypeError, ValueError):
        return 0.5


class DarkPatternDetector:
    def __init__(self, engine: str = "auto", provider: str | None = None, model: str | None = None,
                 mode: str = "multistage", batch_size: int = 40, model_dir: str | Path = "models",
                 dark_threshold: float = 0.5, ocr_threshold: float = 0.5):
        self.mode = mode
        self.batch_size = batch_size
        self.dark_threshold = dark_threshold
        self.ocr_threshold = ocr_threshold
        self.llm = None
        if engine in ("auto", "llm") and (provider or default_provider()):
            self.llm = LLMClient(provider, model)
        elif engine == "llm":
            raise LLMError("engine='llm' requested but no provider configured")
        self.engine = "llm" if self.llm else "offline"
        self.text_clf = None
        try:
            from .baselines import TextClassifier
            self.text_clf = TextClassifier(model_dir)
        except Exception:
            self.text_clf = None
        self.shots = few_shot_block()

    def info(self) -> dict:
        return {"engine": self.engine, "mode": self.mode if self.llm else "rules+tfidf",
                "provider": self.llm.provider if self.llm else None,
                "model": self.llm.model if self.llm else "tfidf_lr + rules",
                "ocr": ocr_available()}

    # ================================================================ text
    def _offline_segments(self, items: list[dict]) -> list[dict]:
        preds = self.text_clf.predict([it["text"] for it in items]) if self.text_clf else None
        out = []
        for i, it in enumerate(items):
            kind = it.get("kind")
            rule = rule_label(it["text"])  # text only: UI tags must not trigger rules
            p = preds[i]["p_dark"] if preds else (0.9 if rule != NOT_DARK else 0.1)
            cat = rule if rule != NOT_DARK else (preds[i]["category"] if preds else NOT_DARK)
            basis = "rule" if rule != NOT_DARK else "classifier"
            if kind in ("checkbox", "radio"):
                # form controls are judged by their state, not their wording
                if it.get("checked") and PRETICK_RE.search(it["text"]):
                    cat, p, rule, basis = "preselection", 0.8, "preselection", "ui_state"
                else:
                    cat, p, rule, basis = NOT_DARK, 0.1, NOT_DARK, "ui_state"
            elif kind == "select":
                if SURCHARGE_RE.search(it["text"]):
                    cat, p, rule, basis = "preselection", 0.75, "preselection", "ui_select"
                else:
                    cat, p, rule = NOT_DARK, 0.1, NOT_DARK
            elif kind == "choice_pair":
                cat, p, rule, basis = "interface_interference", 0.7, "interface_interference", "ui_size"
            is_dark = (p >= self.dark_threshold or rule != NOT_DARK) and cat != NOT_DARK
            out.append({"id": it["id"], "label": cat if is_dark else NOT_DARK,
                        "confidence": round(p if is_dark else 1 - p, 3),
                        "evidence": it["text"][:200] if is_dark else "",
                        "explanation": self._offline_why(basis, cat if is_dark else NOT_DARK, p),
                        "basis": basis, "engine": "offline"})
        return out

    @staticmethod
    def _offline_why(basis: str, cat: str, p: float) -> str:
        name = display_name(cat)
        if cat == NOT_DARK:
            return f"Reads as ordinary shop content (classifier: {p:.0%} likely dark)."
        return {
            "rule": f"The wording follows a typical {name.lower()} formula from our pattern lexicon.",
            "classifier": f"The text classifier rates this {p:.0%} likely to be a dark pattern; closest category: {name}.",
            "ui_state": "A checkbox for a paid extra or for marketing consent is ticked before the shopper chose it.",
            "ui_select": "The more expensive option is selected by default.",
            "ui_size": "One choice is drawn far larger or bolder than the alternative, steering the shopper towards it.",
        }[basis]

    def _verify(self, cands: list[dict], images: list[bytes] | None) -> dict[int, dict]:
        verdicts = {}
        for s in range(0, len(cands), 30):
            chunk = cands[s:s + 30]
            r = self.llm.complete_json(SYSTEM, verify_prompt(chunk, bool(images)), images)
            for v in (r.data.get("verdicts", []) if isinstance(r.data, dict) else []):
                try:
                    verdicts[int(v["cid"])] = v
                except (KeyError, ValueError, TypeError):
                    continue
        return verdicts

    def classify_segments(self, items: list[dict], context: dict | None = None,
                          images: list[bytes] | None = None) -> list[dict]:
        """items: [{'id': int, 'text': str, 'ui': str?, 'kind'?, 'checked'?}] -> one result per id."""
        if not items:
            return []
        if not self.llm:
            return self._offline_segments(items)
        context = context or {}
        results: dict[int, dict] = {}
        for s in range(0, len(items), self.batch_size):
            chunk = items[s:s + self.batch_size]
            r = self.llm.complete_json(SYSTEM, infer_segments_prompt(chunk, context, self.shots), images,
                                       max_tokens=max(4096, 110 * len(chunk)))
            rows = r.data.get("items", []) if isinstance(r.data, dict) else (r.data if isinstance(r.data, list) else [])
            for row in rows:
                try:
                    rid = int(row["id"])
                except (KeyError, ValueError, TypeError):
                    continue
                lab = _norm_label(row.get("label"))
                results[rid] = {"id": rid, "label": lab, "stage1_label": lab,
                                "confidence": _clip(row.get("confidence", 0.5)),
                                "evidence": str(row.get("evidence", ""))[:300],
                                "explanation": str(row.get("explanation", ""))[:400], "engine": "llm"}
        for it in items:  # ids the model skipped
            results.setdefault(it["id"], {"id": it["id"], "label": NOT_DARK, "stage1_label": NOT_DARK,
                                          "confidence": 0.0, "evidence": "", "explanation": "no answer",
                                          "engine": "llm"})
        if self.mode == "multistage":
            cands = [{"cid": rid, **res} for rid, res in results.items() if res["label"] != NOT_DARK]
            if cands:
                for cid, v in self._verify(cands, images).items():
                    if cid not in results:
                        continue
                    if not v.get("keep", True):
                        results[cid].update(label=NOT_DARK, confidence=_clip(1 - _clip(v.get("confidence", 0.5))),
                                            verify_reason=str(v.get("reason", ""))[:300])
                    else:
                        results[cid].update(label=_norm_label(v.get("label", results[cid]["label"])),
                                            confidence=_clip(v.get("confidence", results[cid]["confidence"])),
                                            verify_reason=str(v.get("reason", ""))[:300])
        return [results[it["id"]] for it in items]

    # ========================================================== screenshot
    def _tiles(self, img: Image.Image) -> list[tuple[int, Image.Image]]:
        w, h = img.size
        tile_h = int(w * 1.1)
        if h <= tile_h * 1.4:
            return [(0, img)]
        tiles, y = [], 0
        while y < h:
            tiles.append((y, img.crop((0, y, w, min(h, y + tile_h)))))
            if y + tile_h >= h:
                break
            y += tile_h - 80
        return tiles[:12]

    def analyze_screenshot(self, image_bytes: bytes, context: dict | None = None) -> dict:
        t0 = time.time()
        img = load_image(image_bytes)
        detections, all_lines = [], []
        line_offset = 0
        for y0, tile in self._tiles(img):
            lines = ocr_lines(tile)
            for l in lines:
                l["bbox"] = [l["bbox"][0], l["bbox"][1] + y0, l["bbox"][2], l["bbox"][3]]
                l["id"] += line_offset
            line_offset += len(lines)
            all_lines.extend(lines)
            if self.llm:
                detections.extend(self._llm_tile(tile, y0, lines, context))
            else:
                detections.extend(self._offline_tile(lines))
        detections = self._dedupe(detections)
        dark = [d for d in detections if d["confidence"] >= self.dark_threshold]
        cats = {}
        for d in dark:
            cats.setdefault(d["label"], 0)
            cats[d["label"]] += 1
        return {
            "is_dark": bool(dark),
            "verdict": "Dark pattern detected" if dark else "No dark pattern detected",
            "confidence": round(max([d["confidence"] for d in dark], default=1 - max(
                [d["confidence"] for d in detections], default=0.0)), 3),
            "categories": [{"key": k, "name": display_name(k), "count": v,
                            "regulation": CATEGORY_BY_KEY[k].regulation, "color": CATEGORY_BY_KEY[k].color}
                           for k, v in sorted(cats.items(), key=lambda x: -x[1])],
            "detections": sorted(dark, key=lambda d: -d["confidence"]),
            "low_confidence": [d for d in detections if d["confidence"] < self.dark_threshold],
            "ocr_lines": all_lines,
            "image_size": list(img.size),
            "engine": self.info(),
            "elapsed_s": round(time.time() - t0, 2),
            "usage": dict(self.llm.usage) if self.llm else None,
        }

    def _decorate(self, d: dict) -> dict:
        cat = CATEGORY_BY_KEY.get(d["label"])
        d["name"] = display_name(d["label"])
        d["color"] = cat.color if cat else "#888"
        d["regulation"] = cat.regulation if cat else ""
        return d

    def _offline_tile(self, lines: list[dict]) -> list[dict]:
        if not lines:
            return []
        # OCR fragments are noisy: only lines with real words go to the classifier,
        # and the classifier alone needs a higher bar than a rule match.
        items = [{"id": l["id"], "text": l["text"], "ui": ""} for l in lines
                 if len(re.findall(r"[A-Za-zÀ-ÿ]{2,}", l["text"])) >= 2]
        res = self._offline_segments(items)
        res = [r for r in res if r.get("basis") != "classifier" or r["confidence"] >= self.ocr_threshold]
        by_id = {l["id"]: l for l in lines}
        out = []
        for r in res:
            if r["label"] == NOT_DARK:
                continue
            out.append(self._decorate({"label": r["label"], "confidence": r["confidence"],
                                       "evidence": by_id[r["id"]]["text"], "explanation": r["explanation"],
                                       "box": by_id[r["id"]]["bbox"], "line_ids": [r["id"]],
                                       "basis": r.get("basis"), "source": "ocr+classifier"}))
        return out

    def _llm_tile(self, tile: Image.Image, y0: int, lines: list[dict], context) -> list[dict]:
        png = to_png_bytes(tile)
        by_id = {l["id"]: l for l in lines}
        r = self.llm.complete_json(SYSTEM, infer_screenshot_prompt(lines[:250], self.shots, context), [png],
                                   max_tokens=8192)
        raw = r.data.get("detections", []) if isinstance(r.data, dict) else []
        dets = []
        for i, d in enumerate(raw):
            lab = _norm_label(d.get("label"))
            if lab == NOT_DARK:
                continue
            ids = []
            for x in d.get("line_ids") or []:
                sx = str(x).strip().lstrip("Ll")
                if sx.isdigit():
                    ids.append(int(sx))
            box = self._locate(d, ids, lines, by_id, tile, y0)
            dets.append({"cid": i, "label": lab, "stage1_label": lab, "confidence": _clip(d.get("confidence", 0.5)),
                         "evidence": str(d.get("evidence", ""))[:300],
                         "explanation": str(d.get("explanation", ""))[:400],
                         "box": box, "line_ids": ids, "source": f"llm:{self.llm.model}",
                         "page_kind": r.data.get("page_kind") if isinstance(r.data, dict) else None})
        if self.mode == "multistage" and dets:
            verdicts = self._verify(dets, [png])
            kept = []
            for d in dets:
                v = verdicts.get(d["cid"])
                if v is not None and not v.get("keep", True):
                    continue
                if v is not None:
                    d["label"] = _norm_label(v.get("label", d["label"]))
                    d["confidence"] = _clip(v.get("confidence", d["confidence"]))
                    d["verify_reason"] = str(v.get("reason", ""))[:300]
                if d["label"] != NOT_DARK:
                    kept.append(d)
            dets = kept
        return [self._decorate(d) for d in dets]

    @staticmethod
    def _locate(d: dict, ids: list[int], lines: list[dict], by_id: dict, tile: Image.Image, y0: int):
        """Pixel box [x, y, w, h] for one LLM finding, most reliable source first:
        1. the OCR line(s) whose text matches the evidence quote,
        2. the cited OCR line ids (only lines adjacent to the first one, so one finding
           never stretches over unrelated text),
        3. the model's own box, read as [y_min, x_min, y_max, x_max] in 0-1000
           (Gemini's native order; the prompt asks every provider for it)."""
        quote = str(d.get("evidence", ""))
        box = find_text_box(lines, quote, min_ratio=0.6)
        if box:
            return box
        cited = [by_id[j] for j in ids if j in by_id]
        if cited:
            cited.sort(key=lambda l: l["bbox"][1])
            group = [cited[0]]
            for l in cited[1:]:  # keep a vertically contiguous run of lines
                prev = group[-1]["bbox"]
                if l["bbox"][1] - (prev[1] + prev[3]) <= max(12, prev[3] * 1.2):
                    group.append(l)
                else:
                    break
            x0 = min(l["bbox"][0] for l in group); yy0 = min(l["bbox"][1] for l in group)
            x1 = max(l["bbox"][0] + l["bbox"][2] for l in group)
            y1 = max(l["bbox"][1] + l["bbox"][3] for l in group)
            return [x0, yy0, x1 - x0, y1 - yy0]
        raw = d.get("box_2d", d.get("box"))
        if isinstance(raw, list) and len(raw) == 4:
            ymin, xmin, ymax, xmax = [_clip(v, 0, 1000) / 1000 for v in raw]
            if ymax > ymin and xmax > xmin:
                return [round(xmin * tile.width), round(ymin * tile.height) + y0,
                        max(4, round((xmax - xmin) * tile.width)), max(4, round((ymax - ymin) * tile.height))]
        return None

    @staticmethod
    def _dedupe(dets: list[dict]) -> list[dict]:
        def iou(a, b):
            if not a or not b:
                return 0.0
            ax1, ay1, bx1, by1 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
            iw = max(0, min(ax1, bx1) - max(a[0], b[0]))
            ih = max(0, min(ay1, by1) - max(a[1], b[1]))
            inter = iw * ih
            union = a[2] * a[3] + b[2] * b[3] - inter
            return inter / union if union else 0.0
        out = []
        for d in sorted(dets, key=lambda d: -d["confidence"]):
            if any(o["label"] == d["label"] and (iou(o.get("box"), d.get("box")) > 0.5 or
                                                 o["evidence"].lower() == d["evidence"].lower()) for o in out):
                continue
            out.append(d)
        return out

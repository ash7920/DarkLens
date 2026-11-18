"""
Prompts for the extract → infer → verify pipeline (adapted from DPDGPT,
Lin et al. 2026, for web pages and screenshots).

Stage 1  INFER   – classify every candidate element (text segments from the
                   crawler, or OCR lines from a screenshot) against the taxonomy;
                   in screenshot mode the model also reports purely visual findings.
Stage 2  VERIFY  – the model re-checks each positive against the definition
                   and counter-examples and rejects false positives.
"""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

from ..taxonomy import ALL_LABELS, CATEGORY_BY_KEY, NOT_DARK, taxonomy_as_text

SYSTEM = f"""You are DarkLens, an expert auditor of deceptive design ("dark patterns") on e-commerce
websites, working for EU consumer-protection research (DSA, UCPD, GDPR).

TAXONOMY (use exactly these keys):
{taxonomy_as_text()}

DECISION RULES
1. Judge the manipulative MECHANISM, not keywords. "In stock" or "Free delivery over €50" is
   ordinary information; "Only 2 left!" or a ticking countdown on a deal is a pressure tactic.
2. Use the UI state given in square brackets: a "[checkbox, PRE-TICKED]" for a paid add-on,
   donation, insurance or marketing consent is preselection; the same checkbox unticked is fine.
3. A decline option phrased to shame the user is confirmshaming; a neutral "No thanks" is not.
4. When the evidence is genuinely ambiguous, prefer {NOT_DARK} and lower confidence —
   auditors need precision.
5. Confidence is your probability (0–1) that the label is correct.
6. Answer with valid JSON only, no prose outside JSON."""


def few_shot_block(train_csv: str | Path = "data/splits/text_train.csv", per_class: int = 2,
                   seed: int = 7) -> str:
    """Labelled examples drawn ONLY from the training split (never the test split)."""
    lines = []
    p = Path(train_csv)
    if p.exists():
        df = pd.read_csv(p)
        rng = random.Random(seed)
        for lab in ALL_LABELS:
            sub = df[df["category"] == lab]
            if sub.empty:
                continue
            idx = rng.sample(list(sub.index), min(per_class + (1 if lab == NOT_DARK else 0), len(sub)))
            for i in idx:
                t = str(df.loc[i, "text"])[:160]
                lines.append(f'"{t}" -> {lab}')
    else:
        for key, cat in CATEGORY_BY_KEY.items():
            for ex in cat.examples[:per_class]:
                lines.append(f'"{ex}" -> {key}')
            for ex in cat.counter_examples[:1]:
                lines.append(f'"{ex}" -> {NOT_DARK}')
    return "LABELLED EXAMPLES\n" + "\n".join(lines)


def infer_segments_prompt(items: list[dict], context: dict, shots: str) -> str:
    ctx = ", ".join(f"{k}: {v}" for k, v in context.items() if v)
    listing = "\n".join(f"{it['id']}. {it.get('ui', '')} {it['text']}".replace("  ", " ") for it in items)
    return f"""{shots}

PAGE CONTEXT: {ctx or 'unknown'}

Classify EACH numbered element below. Elements come from one web page, in page order, so use
neighbouring elements as context.

ELEMENTS
{listing}

Return JSON:
{{"items": [{{"id": <int>, "label": "<taxonomy key or {NOT_DARK}>", "confidence": <0-1>,
  "evidence": "<short exact quote>", "explanation": "<one sentence, why>"}}]}}
Include every id exactly once."""


def infer_screenshot_prompt(lines: list[dict], shots: str, context: dict | None = None) -> str:
    ctx = ", ".join(f"{k}: {v}" for k, v in (context or {}).items() if v)
    listing = "\n".join(f"L{l['id']}: {l['text']}" for l in lines) or "(no text was recognised)"
    return f"""{shots}

You are given a SCREENSHOT of a web or app interface{(' (' + ctx + ')') if ctx else ''} and the text lines
OCR found in it (OCR may contain small errors; trust the image when they disagree).

OCR LINES
{listing}

Task: find every dark pattern instance in the screenshot.
- Use the OCR line ids to point at the text that carries each pattern (one or more lines).
- Also report patterns that are only VISUAL (pre-ticked boxes, a huge 'Accept' next to a tiny
  grey 'reject', a countdown graphic) — give its box as "box_2d": [y_min, x_min, y_max, x_max]
  in 0–1000 coordinates relative to the image height/width (y first).
- "evidence" must be the exact text as it appears in the OCR lines when the pattern is textual.
- Do not report ordinary prices, navigation, product names or neutral information.

Return JSON:
{{"page_kind": "<product|cart|checkout|cookie_banner|popup|subscription|homepage|other>",
  "detections": [{{"label": "<taxonomy key>", "line_ids": [<int>...], "box_2d": [y_min, x_min, y_max, x_max] or null,
     "evidence": "<exact quote or visual description>", "confidence": <0-1>,
     "explanation": "<one sentence>"}}]}}
Return "detections": [] if the screenshot contains no dark pattern."""


def verify_prompt(candidates: list[dict], screenshot: bool) -> str:
    defs = []
    for lab in sorted({c["label"] for c in candidates if c["label"] in CATEGORY_BY_KEY}):
        cat = CATEGORY_BY_KEY[lab]
        defs.append(f"- {lab}: {cat.definition}\n    NOT this: {' | '.join(cat.counter_examples)}")
    listing = "\n".join(
        f"{c['cid']}. label={c['label']} conf={c.get('confidence', 0):.2f} | \"{c.get('evidence', '')[:200]}\""
        f" | reason: {c.get('explanation', '')[:200]}" for c in candidates)
    where = "the attached screenshot" if screenshot else "the page elements"
    return f"""VERIFICATION STAGE. A first-pass detector flagged the candidates below in {where}.
Your job is to catch FALSE POSITIVES and wrong categories. For each candidate, check it strictly
against the definition and the counter-examples. Keep it only if a careful EU consumer-protection
auditor would agree it is manipulative.

DEFINITIONS
{chr(10).join(defs)}

CANDIDATES
{listing}

Return JSON:
{{"verdicts": [{{"cid": <int>, "keep": true|false, "label": "<final taxonomy key>",
  "confidence": <0-1>, "reason": "<one sentence>"}}]}}"""

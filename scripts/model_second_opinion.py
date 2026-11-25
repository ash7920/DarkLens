"""
A second opinion on the annotation sample from a language model, used only as a supporting check
on the human labels (never as ground truth).

    python scripts/model_second_opinion.py            # needs the Gemini key set

It is kept independent of the detector being evaluated: a different model (by default
gemini-3.5-flash, not the detector's gemini-3.5-flash-lite), a different prompt (the written
labelling guide the human annotator used, not the detector's infer/verify prompts), and it sees
the item exactly as the annotator did (element type, page type, original text, English text).
It does not see the screenshot, which the human did; the paper says so.

Writes data/annotation/model_opinion.jsonl (one line per item). Safe to re-run: items that
already have an answer are skipped. If a model is busy it moves on to the next
(DARKLENS_MODELS=a,b,c to choose them).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from darklens.detection.llm_client import LLMClient, LLMError  # noqa: E402
from darklens.evaluation.annotation import load_sample  # noqa: E402
from darklens.taxonomy import ALL_LABELS  # noqa: E402

OUT = ROOT / "data/annotation/model_opinion.jsonl"
DETECTOR_MODEL = "gemini-3.5-flash-lite"
DEFAULT_MODELS = ["gemini-3.5-flash", "gemini-2.5-flash", "gemma-4-31b-it", "gemini-3.1-flash-lite"]

GUIDE = """You label elements from online shops for a study of dark patterns. Ask one question: is this
element trying to push the shopper into something they might not choose if it were presented
neutrally? When in doubt, answer not_dark.

Most items are ordinary shop content and are not_dark: product names, prices, sizes, weights,
colours, rating counts like "(31)", menu links, plain discounts ("-14%"), delivery costs, legal or
error text.

Labels:
- urgency: a deadline or timer pressuring a quick decision ("Offer ends in 02:14:55", "Order in the
  next 3 hours", "Today only"). Not a plain date, price, or a sale with no deadline.
- scarcity: claims that stock or availability is limited ("Only 2 left", "Only a few left in stock",
  "Almost sold out", "High demand"). Not "In stock" or "Available online".
- social_proof: pressure from what other people do ("13 people viewed this item in the past day",
  "Bought 500 times this week", "4% bought", "Most booked hotels"). Not a star rating or review count alone.
- confirmshaming: the "no" option makes the shopper feel guilty or stupid ("No thanks, I don't like saving money").
- preselection: something extra already selected or added: a [checkbox, PRE-TICKED] for insurance,
  newsletter or donation; an add-on or fee slipped into the basket. Not a size or delivery option
  the shopper must choose anyway.
- obstruction: leaving, cancelling or unsubscribing made hard ("call us to cancel", hidden cancel links).
- interface_interference: layout steering the choice. Lines like "'Accept all' (large) vs 'Reject'
  (small)" count when the option good for the shop is much bigger or brighter than its alternative
  in the same choice (cookies, consent, add-on yes/no). Not two unrelated links or a policy link.
- forced_action: the shopper must do something unrelated to continue (create an account to check
  out, accept marketing to see prices, install an app to buy).

Answer with JSON only."""


def _models() -> list[str]:
    if os.getenv("DARKLENS_MODELS"):
        return [m.strip() for m in os.environ["DARKLENS_MODELS"].split(",") if m.strip()]
    return DEFAULT_MODELS


def _describe(it: dict) -> str:
    en = (it.get("text_en") or "").strip()
    text = (it.get("text") or "").strip()[:400]
    line = f"[{it.get('kind') or 'element'} on a {it.get('page_type') or 'unknown'} page {it.get('ui') or ''}".rstrip() + "] "
    line += text
    if en and en.lower() != text.lower():
        line += f"  (English: {en[:400]})"
    host = urlparse(it.get("url") or "").netloc
    return line + (f"  (shop: {host})" if host else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--retries", type=int, default=4)
    args = ap.parse_args()

    items = load_sample()
    done = {}
    if OUT.exists():
        for line in open(OUT, encoding="utf-8"):
            r = json.loads(line)
            done[r["segment_id"]] = r
    todo = [it for it in items if it["segment_id"] not in done]
    models = [m for m in _models() if m != DETECTOR_MODEL]
    print(f"{len(items)} items, {len(todo)} to label, models: {', '.join(models)}")
    try:
        clients = {m: LLMClient(model=m, timeout=300) for m in models}
    except LLMError as exc:
        sys.exit(f"  ! {exc}")
    dead: set[str] = set()
    n_batches = (len(todo) + args.batch - 1) // args.batch
    for b, s in enumerate(range(0, len(todo), args.batch), 1):
        chunk = todo[s:s + args.batch]
        listing = "\n".join(f"{i + 1}. {_describe(it)}" for i, it in enumerate(chunk))
        prompt = (f"Label each numbered element.\n\n{listing}\n\n"
                  f'Return JSON: {{"items": [{{"id": <number>, "label": "<one of {", ".join(ALL_LABELS)}>"}}]}} '
                  "with every id exactly once.")
        r, used = None, None
        for m, llm in clients.items():
            if m in dead:
                continue
            try:
                r, used = llm.complete_json(GUIDE, prompt, max_tokens=2048, retries=args.retries), m
                break
            except LLMError as exc:
                msg = str(exc)
                if "DAILY" in msg or "404" in msg or "not available" in msg.lower():
                    dead.add(m)
                    print(f"  ! {m}: not usable now; dropping it")
                else:
                    print(f"  ! {m}: still busy, trying the next model")
        if r is None:
            if len(dead) == len(clients):
                print("  ! no model left to try today; stopping")
                break
            print(f"  batch {b}/{n_batches}: all models busy, skipped (re-run later)")
            continue
        got = 0
        with open(OUT, "a", encoding="utf-8") as f:
            for row in (r.data.get("items", []) if isinstance(r.data, dict) else []):
                try:
                    it = chunk[int(row["id"]) - 1]
                except (KeyError, ValueError, IndexError, TypeError):
                    continue
                label = str(row.get("label", "")).strip().lower()
                if label in ALL_LABELS and it["segment_id"] not in done:
                    rec = {"segment_id": it["segment_id"], "label": label, "model": used}
                    done[it["segment_id"]] = rec
                    f.write(json.dumps(rec) + "\n")
                    got += 1
        print(f"  batch {b}/{n_batches}: {got}/{len(chunk)} labelled ({used})")
    left = sum(1 for it in items if it["segment_id"] not in done)
    print(f"done; {left} item(s) still without a model label" + (" (re-run to retry)" if left else ""))


if __name__ == "__main__":
    main()

"""
Add an English translation to every annotation item, so labellers who do not read the
shop's language can still judge it.  Both labellers see the same translation (plus the
original text), which keeps their labels comparable.

    python scripts/translate_sample.py            # needs the Gemini key set
    python scripts/translate_sample.py --batch 10 # even smaller requests when servers are very busy

When a model is overloaded it moves on to the next one (DARKLENS_MODELS=a,b,c to choose them).

Safe to re-run: items that already have a translation are skipped, and every answer is cached.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from darklens.detection.llm_client import LLMClient, LLMError  # noqa: E402

SAMPLE = ROOT / "data/annotation/sample.jsonl"
SYSTEM = ("You translate short snippets of e-commerce website text into plain English for human annotators. "
          "Translate faithfully: keep the tone, urgency and wording choices, numbers, prices, currencies and brand "
          "names. Do not explain, judge or summarise. If a snippet is already English, return it unchanged. "
          "Answer with JSON only.")


def needs_translation(item: dict) -> bool:
    return not item.get("text_en")


FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-2.0-flash", "gemini-flash-latest",
                   "gemma-3-27b-it", "gemma-3-12b-it"]


def _models() -> list[str]:
    """Models to rotate through when one is overloaded: DARKLENS_MODELS (comma-separated) if set,
    else DARKLENS_MODEL first and the usual fallbacks after it."""
    import os
    if os.getenv("DARKLENS_MODELS"):
        return [m.strip() for m in os.environ["DARKLENS_MODELS"].split(",") if m.strip()]
    first = os.getenv("DARKLENS_MODEL")
    return ([first] if first else []) + [m for m in FALLBACK_MODELS if m != first]


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", type=int, default=20, help="snippets per request (smaller gets through busy servers)")
    ap.add_argument("--retries", type=int, default=4, help="attempts per model before trying the next model")
    args = ap.parse_args()

    items = [json.loads(l) for l in open(SAMPLE, encoding="utf-8")]
    todo = [it for it in items if needs_translation(it)]
    print(f"{len(items)} items, {len(todo)} to translate, {args.batch} per request")
    clients, dead = {}, set()
    for m in _models():
        try:
            clients[m] = LLMClient(model=m, timeout=300)
        except LLMError as exc:
            print(f"  ! {exc}")
            return
    by_id = {it["segment_id"]: it for it in items}
    n_batches = (len(todo) + args.batch - 1) // args.batch
    for b, s in enumerate(range(0, len(todo), args.batch), 1):
        chunk = todo[s:s + args.batch]
        listing = "\n".join(f"{i + 1}. {it['text'][:400]}" for i, it in enumerate(chunk))
        prompt = (f"Translate each numbered snippet into English.\n\n{listing}\n\n"
                  'Return JSON: {"items": [{"id": <number>, "en": "<English text>"}]} with every id exactly once.')
        r = None
        for m, llm in clients.items():
            if m in dead:
                continue
            try:
                r = llm.complete_json(SYSTEM, prompt, max_tokens=4096, retries=args.retries)
                break
            except LLMError as exc:
                msg = str(exc)
                if "DAILY" in msg or "404" in msg or "not found" in msg.lower():
                    dead.add(m)  # used up for today, or not available for this key
                    print(f"  ! {m}: not usable now ({msg[:90]}...); dropping it")
                else:
                    print(f"  ! {m}: still busy, trying the next model")
        if r is None:
            if len(dead) == len(clients):
                print("  ! every model is used up for today; stopping")
                break
            print(f"  batch {b}/{n_batches}: all models busy, skipped (re-run later)")
            continue
        got = 0
        for row in (r.data.get("items", []) if isinstance(r.data, dict) else []):
            try:
                it = chunk[int(row["id"]) - 1]
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            en = str(row.get("en", "")).strip()
            if en:
                by_id[it["segment_id"]]["text_en"] = en
                got += 1
        print(f"  batch {b}/{n_batches}: {got}/{len(chunk)} translated ({r.model})")
        # write after every batch so nothing is lost if it stops
        with open(SAMPLE, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
    left = sum(1 for it in items if needs_translation(it))
    print(f"done; {left} item(s) still without a translation" + (" (re-run to retry)" if left else ""))


if __name__ == "__main__":
    main()

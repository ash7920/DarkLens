"""
Add an English translation to every annotation item, so labellers who do not read the
shop's language can still judge it.  Both labellers see the same translation (plus the
original text), which keeps their labels comparable.

    python scripts/translate_sample.py          # needs the Gemini key set; ~15 calls for ~1000 items

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


def main(batch: int = 60):
    items = [json.loads(l) for l in open(SAMPLE, encoding="utf-8")]
    todo = [it for it in items if needs_translation(it)]
    print(f"{len(items)} items, {len(todo)} to translate")
    llm = LLMClient()
    by_id = {it["segment_id"]: it for it in items}
    for s in range(0, len(todo), batch):
        chunk = todo[s:s + batch]
        listing = "\n".join(f"{i + 1}. {it['text'][:400]}" for i, it in enumerate(chunk))
        prompt = (f"Translate each numbered snippet into English.\n\n{listing}\n\n"
                  'Return JSON: {"items": [{"id": <number>, "en": "<English text>"}]} with every id exactly once.')
        try:
            r = llm.complete_json(SYSTEM, prompt, max_tokens=8192)
        except LLMError as exc:
            print(f"  ! batch {s // batch + 1} failed: {exc}. Re-run later to finish.")
            if "DAILY" in str(exc):
                break
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
        print(f"  batch {s // batch + 1}: {got}/{len(chunk)} translated")
        # write after every batch so nothing is lost if it stops
        with open(SAMPLE, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
    left = sum(1 for it in items if needs_translation(it))
    print(f"done; {left} item(s) still without a translation" + (" (re-run to retry)" if left else ""))


if __name__ == "__main__":
    main()

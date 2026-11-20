"""
Loaders for the existing labelled datasets (block diagram stage 1) and the
builder for the unified dataset (stage 3 output).

  EC   – Yada et al. 2022, github.com/yamanalab/ec-darkpattern (dataset/dataset.tsv)
  MATH – Mathur et al. 2019, github.com/aruneshmathur/dark-patterns (data/final-dark-patterns/dark-patterns.csv)
  AIDUI– Mansur et al. 2023, github.com/SageSELab/AidUI (evaluation/evaluation_dataset/{web,mobile})

Download with scripts/download_datasets.sh (plain git clones into data/external/).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..taxonomy import AIDUI_LABEL_TO_KEY, EC_CATEGORY_TO_KEY, MATHUR_TYPE_TO_KEY, NOT_DARK

EXTERNAL = Path("data/external")


def load_ec(root: Path = EXTERNAL) -> pd.DataFrame:
    df = pd.read_csv(root / "ec-darkpattern/dataset/dataset.tsv", sep="\t")
    out = pd.DataFrame({
        "source": "ec",
        "item_id": "ec_" + df.index.astype(str),
        "group": "ec_page_" + df["page_id"].astype(str),
        "text": df["text"].astype(str),
        "label_binary": df["label"].astype(int),
        "category": df["Pattern Category"].map(EC_CATEGORY_TO_KEY).fillna(NOT_DARK),
        "orig_category": df["Pattern Category"],
    })
    return out


def load_mathur(root: Path = EXTERNAL) -> pd.DataFrame:
    df = pd.read_csv(root / "dark-patterns/data/final-dark-patterns/dark-patterns.csv")
    df = df.dropna(subset=["Pattern String"])
    out = pd.DataFrame({
        "source": "mathur",
        "item_id": "mathur_" + df.index.astype(str),
        "group": "mathur_site_" + df["Website Page"].fillna("").str.extract(r"https?://([^/]+)")[0].fillna("na"),
        "text": df["Pattern String"].astype(str),
        "label_binary": 1,
        "category": df["Pattern Type"].map(MATHUR_TYPE_TO_KEY),
        "orig_category": df["Pattern Category"] + " / " + df["Pattern Type"],
        "location": df["Where in website?"],
        "deceptive": df["Deceptive?"],
    })
    return out


def load_aidui(root: Path = EXTERNAL, split: str = "web") -> pd.DataFrame:
    """One row per *image*, with the set of dark-pattern labels it contains
    and the boxes (for drawing / localisation checks)."""
    base = root / "AidUI/evaluation/evaluation_dataset" / split
    coco = json.loads((base / "result.json").read_text(encoding="utf-8"))
    cats = {c["id"]: c["name"] for c in coco["categories"]}
    anns: dict[int, list] = {}
    for a in coco["annotations"]:
        anns.setdefault(a["image_id"], []).append(a)
    rows = []
    for img in coco["images"]:
        labels = [AIDUI_LABEL_TO_KEY.get(cats[a["category_id"]], NOT_DARK) for a in anns.get(img["id"], [])]
        dark = sorted({l for l in labels if l != NOT_DARK})
        rows.append({
            "source": f"aidui_{split}",
            "item_id": f"aidui_{split}_{img['id']}",
            "image_path": str(base / img["file_name"]),
            "width": img["width"], "height": img["height"],
            "label_binary": int(bool(dark)),
            "categories": dark,
            "boxes": [{"category": AIDUI_LABEL_TO_KEY.get(cats[a["category_id"]], NOT_DARK), "bbox": a["bbox"]}
                      for a in anns.get(img["id"], [])],
        })
    return pd.DataFrame(rows)


def build_text_corpus(root: Path = EXTERNAL) -> pd.DataFrame:
    """Unified text corpus: EC (balanced binary, Mathur-derived dark texts + scraped
    non-dark texts) enriched with Mathur's fine-grained *type* where the text matches,
    so every dark item carries one of our taxonomy keys."""
    ec = load_ec(root)
    m = load_mathur(root)
    type_by_text = (m.assign(key=m["text"].str.strip().str.lower())
                     .drop_duplicates("key").set_index("key")["category"])
    key = ec["text"].str.strip().str.lower()
    refined = key.map(type_by_text)
    dark = ec["label_binary"] == 1
    ec.loc[dark & refined.notna(), "category"] = refined[dark & refined.notna()]
    ec["category_source"] = "ec_category"
    ec.loc[dark & refined.notna(), "category_source"] = "mathur_type"
    return ec

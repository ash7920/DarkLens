"""
RoBERTa baseline (Yada et al. 2022's strongest model) — run on a GPU.

Google Colab (free T4 GPU, ~5 minutes):
    !git clone <your repo url> darklens && cd darklens
    !pip install -q transformers scikit-learn pandas
    !python scripts/train_baselines.py          # creates data/splits/ (needs data/external, see README)
    !python scripts/train_roberta.py --task binary
    !python scripts/train_roberta.py --task multiclass

Trains on data/splits/text_train.csv and evaluates on data/splits/text_test.csv
(the same held-out split the LLM is evaluated on), writing results/roberta_<task>.json.
A plain PyTorch loop is used so it works across transformers versions.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from darklens.evaluation.metrics import binary_metrics, multiclass_metrics  # noqa: E402


def set_seed(s):
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)
    torch.cuda.manual_seed_all(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["binary", "multiclass"], default="binary")
    ap.add_argument("--model", default="roberta-base")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--max-len", type=int, default=64)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    set_seed(a.seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    tr = pd.read_csv(ROOT / "data/splits/text_train.csv")
    te = pd.read_csv(ROOT / "data/splits/text_test.csv")
    col = "label_binary" if a.task == "binary" else "category"
    labels = sorted(set(tr[col].astype(str)) | set(te[col].astype(str)))
    lid = {l: i for i, l in enumerate(labels)}

    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForSequenceClassification.from_pretrained(a.model, num_labels=len(labels)).to(dev)

    def batches(df, shuffle):
        idx = list(range(len(df)))
        if shuffle:
            random.shuffle(idx)
        for s in range(0, len(idx), a.batch):
            b = df.iloc[idx[s:s + a.batch]]
            enc = tok(list(b["text"].astype(str)), truncation=True, max_length=a.max_len, padding=True,
                      return_tensors="pt")
            y = torch.tensor([lid[str(v)] for v in b[col]])
            yield {k: v.to(dev) for k, v in enc.items()}, y.to(dev)

    steps = a.epochs * ((len(tr) + a.batch - 1) // a.batch)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    sch = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)
    t0 = time.time()
    for ep in range(a.epochs):
        model.train()
        tot = 0.0
        for enc, y in batches(tr, True):
            out = model(**enc, labels=y)
            out.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sch.step()
            opt.zero_grad()
            tot += out.loss.item()
        print(f"epoch {ep + 1}: loss {tot:.2f}")
    train_s = time.time() - t0

    model.eval()
    preds = []
    t1 = time.time()
    with torch.no_grad():
        for enc, _ in batches(te, False):
            preds.extend(model(**enc).logits.argmax(-1).tolist())
    infer_s = time.time() - t1
    pred_labels = [labels[p] for p in preds]
    if a.task == "binary":
        m = binary_metrics(te["label_binary"].astype(int).to_numpy(), np.array(pred_labels).astype(int))
    else:
        m = multiclass_metrics(list(te["category"]), pred_labels)
    m.update({"model": a.model, "epochs": a.epochs, "lr": a.lr, "max_len": a.max_len, "seed": a.seed,
              "train_seconds": round(train_s, 1), "inference_seconds": round(infer_s, 2), "device": dev})
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / f"results/roberta_{a.task}.json").write_text(json.dumps(m, indent=2, default=float))
    key = "f1" if a.task == "binary" else "macro_f1"
    print(f"RoBERTa {a.task}: {key}={m[key]:.3f} -> results/roberta_{a.task}.json")


if __name__ == "__main__":
    main()

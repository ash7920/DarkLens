"""
Evaluation module metrics (block diagram stage 5):
precision, recall, F1, confusion matrix, Cohen's kappa (LLM vs. human),
Fleiss' kappa (between annotators), bootstrap confidence intervals.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
from sklearn.metrics import (accuracy_score, cohen_kappa_score, confusion_matrix,
                             precision_recall_fscore_support)


def binary_metrics(y_true, y_pred, n_boot: int = 1000, seed: int = 0, sample_weight=None) -> dict:
    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    w = None if sample_weight is None else np.asarray(sample_weight, dtype=float)
    p, r, f, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0, sample_weight=w)
    out = {
        "n": int(len(y_true)), "precision": float(p), "recall": float(r), "f1": float(f),
        "accuracy": float(accuracy_score(y_true, y_pred, sample_weight=w)),
        "kappa": float(cohen_kappa_score(y_true, y_pred, sample_weight=w)) if len(set(y_true) | set(y_pred)) > 1 else 1.0,
        "confusion": confusion_matrix(y_true, y_pred, labels=[0, 1], sample_weight=w).tolist(),
        "weighted": w is not None,
    }
    if n_boot and w is None:
        rng = np.random.default_rng(seed)
        f1s = []
        for _ in range(n_boot):
            idx = rng.integers(0, len(y_true), len(y_true))
            f1s.append(precision_recall_fscore_support(y_true[idx], y_pred[idx], average="binary",
                                                       zero_division=0)[2])
        out["f1_ci95"] = [float(np.percentile(f1s, 2.5)), float(np.percentile(f1s, 97.5))]
    return out


def multiclass_metrics(y_true: list[str], y_pred: list[str], labels: list[str] | None = None,
                       sample_weight=None) -> dict:
    labels = labels or sorted(set(y_true) | set(y_pred))
    w = sample_weight
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    per = {lab: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]), "support": int(s[i])}
           for i, lab in enumerate(labels)}
    dark_labels = [l for l in labels if l != "not_dark" and per[l]["support"] > 0]
    mp, mr, mf, _ = precision_recall_fscore_support(y_true, y_pred, labels=dark_labels, average="macro",
                                                    zero_division=0, sample_weight=w)
    up, ur, uf, _ = precision_recall_fscore_support(y_true, y_pred, labels=dark_labels, average="micro",
                                                    zero_division=0, sample_weight=w)
    return {
        "n": len(y_true),
        "accuracy": float(accuracy_score(y_true, y_pred, sample_weight=w)),
        "macro_precision": float(mp), "macro_recall": float(mr), "macro_f1": float(mf),
        "micro_precision": float(up), "micro_recall": float(ur), "micro_f1": float(uf),
        "kappa": float(cohen_kappa_score(y_true, y_pred, sample_weight=w)),
        "per_class": per,
        "labels": labels,
        "confusion": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        "note": "macro/micro averages over dark-pattern classes present in the gold labels",
    }


def fleiss_kappa(ratings: list[list[str]]) -> float:
    """ratings[i] = labels given to item i by each annotator (same count per item)."""
    if not ratings:
        return float("nan")
    cats = sorted({c for r in ratings for c in r})
    n = len(ratings[0])
    N = len(ratings)
    table = np.array([[Counter(r)[c] for c in cats] for r in ratings], dtype=float)
    p_j = table.sum(axis=0) / (N * n)
    P_i = (np.square(table).sum(axis=1) - n) / (n * (n - 1))
    P_bar, P_e = P_i.mean(), np.square(p_j).sum()
    return float((P_bar - P_e) / (1 - P_e)) if P_e < 1 else 1.0


def multilabel_image_metrics(gold: list[set], pred: list[set], categories: list[str]) -> dict:
    """Image-level evaluation for screenshot datasets (AidUI): an image can
    contain several patterns.  Reports binary (any dark pattern) and per-category."""
    yb = np.array([int(bool(g)) for g in gold])
    pb = np.array([int(bool(p)) for p in pred])
    out = {"binary": binary_metrics(yb, pb), "per_category": {}}
    tp_all = fp_all = fn_all = 0
    for c in categories:
        tp = sum(1 for g, p in zip(gold, pred) if c in g and c in p)
        fp = sum(1 for g, p in zip(gold, pred) if c not in g and c in p)
        fn = sum(1 for g, p in zip(gold, pred) if c in g and c not in p)
        tp_all, fp_all, fn_all = tp_all + tp, fp_all + fp, fn_all + fn
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        out["per_category"][c] = {"precision": prec, "recall": rec,
                                  "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
                                  "support": tp + fn}
    prec = tp_all / (tp_all + fp_all) if tp_all + fp_all else 0.0
    rec = tp_all / (tp_all + fn_all) if tp_all + fn_all else 0.0
    out["micro"] = {"precision": prec, "recall": rec, "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0}
    present = [c for c in categories if out["per_category"][c]["support"] > 0]
    out["macro_f1"] = float(np.mean([out["per_category"][c]["f1"] for c in present])) if present else 0.0
    return out

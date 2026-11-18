"""
Train and evaluate the classical baselines on the unified text corpus.

    python scripts/train_baselines.py

Outputs
    results/baselines.json          cross-validated metrics (paper Table: baselines)
    data/splits/text_test.csv       fixed held-out test split used for LLM comparison
    models/tfidf_lr_*.joblib        final models trained on all data (used by the app)

Evaluation uses 5-fold *StratifiedGroupKFold*, grouping by source page so the
same page never appears in both train and test (stricter than a random split).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.model_selection import StratifiedGroupKFold

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from darklens.detection.baselines import RuleModel, make_model  # noqa: E402
from darklens.evaluation.metrics import binary_metrics, multiclass_metrics  # noqa: E402
from darklens.preprocessing.datasets import build_text_corpus  # noqa: E402

SEED = 42


def cv_eval(model_factory, X, y, groups, multiclass: bool, n_splits=5):
    skf = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=SEED)
    y_pred = np.empty(len(y), dtype=object if multiclass else int)
    t0 = time.time()
    for tr, te in skf.split(X, y, groups):
        m = model_factory()
        m.fit(X[tr], y[tr])
        y_pred[te] = m.predict(X[te])
    secs = time.time() - t0
    res = multiclass_metrics(list(y), list(y_pred)) if multiclass else binary_metrics(y, y_pred.astype(int))
    res["cv_seconds"] = round(secs, 2)
    return res, y_pred


def main():
    corpus = build_text_corpus()
    X = corpus["text"].to_numpy()
    yb = corpus["label_binary"].to_numpy()
    ym = corpus["category"].to_numpy()
    groups = corpus["group"].to_numpy()

    results = {"dataset": {"n": int(len(corpus)), "n_dark": int(yb.sum()),
                           "categories": corpus["category"].value_counts().to_dict(),
                           "cv": "5-fold StratifiedGroupKFold (group = source page)", "seed": SEED}}
    for name, factory in [
        ("rules", lambda: RuleModel(False)),
        ("tfidf_lr", lambda: make_model("tfidf_lr")),
        ("tfidf_svm", lambda: make_model("tfidf_svm")),
    ]:
        r, _ = cv_eval(factory, X, yb, groups, multiclass=False)
        results.setdefault("binary", {})[name] = r
        print(f"binary  {name:10s} P={r['precision']:.3f} R={r['recall']:.3f} F1={r['f1']:.3f}")

    for name, factory in [
        ("rules", lambda: RuleModel(True)),
        ("tfidf_lr", lambda: make_model("tfidf_lr", multiclass=True)),
        ("tfidf_svm", lambda: make_model("tfidf_svm", multiclass=True)),
    ]:
        r, _ = cv_eval(factory, X, ym, groups, multiclass=True)
        results.setdefault("multiclass", {})[name] = r
        print(f"multi   {name:10s} macroF1={r['macro_f1']:.3f} microF1={r['micro_f1']:.3f} acc={r['accuracy']:.3f}")

    # Fixed held-out split (one CV fold) for the LLM comparison.
    skf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    tr, te = next(skf.split(X, ym, groups))
    Path("data/splits").mkdir(parents=True, exist_ok=True)
    corpus.iloc[te].to_csv("data/splits/text_test.csv", index=False)
    corpus.iloc[tr].to_csv("data/splits/text_train.csv", index=False)
    held = {}
    for name, factory, mc in [("tfidf_lr_binary", lambda: make_model("tfidf_lr"), False),
                              ("tfidf_lr_multiclass", lambda: make_model("tfidf_lr", True), True),
                              ("rules_binary", lambda: RuleModel(False), False),
                              ("rules_multiclass", lambda: RuleModel(True), True)]:
        y = ym if mc else yb
        m = factory().fit(X[tr], y[tr])
        p = m.predict(X[te])
        held[name] = multiclass_metrics(list(y[te]), list(p)) if mc else binary_metrics(y[te], p)
    results["held_out_test"] = {"n": int(len(te)), **held}
    print(f"held-out test split: {len(te)} items -> data/splits/text_test.csv")

    Path("models").mkdir(exist_ok=True)
    joblib.dump(make_model("tfidf_lr").fit(X, yb), "models/tfidf_lr_binary.joblib")
    joblib.dump(make_model("tfidf_lr", True).fit(X, ym), "models/tfidf_lr_multiclass.joblib")
    Path("results").mkdir(exist_ok=True)
    Path("results/baselines.json").write_text(json.dumps(results, indent=2, default=float))
    print("saved models/ and results/baselines.json")


if __name__ == "__main__":
    main()

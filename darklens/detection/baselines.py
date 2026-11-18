"""
Classical baselines (block diagram: comparison points for the LLM).

  rules        – regex lexicon (darklens.preprocessing.lexicon)
  tfidf_lr     – TF-IDF (word 1–2 grams + char 2–5 grams) + logistic regression
  tfidf_svm    – same features + linear SVM

RoBERTa (Yada et al. 2022's best model) is in scripts/train_roberta.py and is
meant to run on a GPU (Google Colab).
"""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from ..preprocessing.lexicon import rule_label
from ..taxonomy import NOT_DARK


def _features():
    return FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True, lowercase=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)),
    ])


def make_model(kind: str = "tfidf_lr", multiclass: bool = False) -> Pipeline:
    if kind == "tfidf_lr":
        clf = LogisticRegression(max_iter=3000, C=10.0, class_weight="balanced")
    elif kind == "tfidf_svm":
        clf = LinearSVC(C=1.0, class_weight="balanced")
    else:
        raise ValueError(kind)
    return Pipeline([("feats", _features()), ("clf", clf)])


class RuleModel:
    """sklearn-like wrapper so rules can be evaluated with the same code."""

    def __init__(self, multiclass: bool = False):
        self.multiclass = multiclass

    def fit(self, X, y):
        return self

    def predict(self, X):
        labels = [rule_label(t) for t in X]
        if self.multiclass:
            return np.array(labels)
        return np.array([int(l != NOT_DARK) for l in labels])


class TextClassifier:
    """Loads the trained binary + multiclass TF-IDF models used by the offline
    mode of the app and by the candidate pre-filter."""

    def __init__(self, model_dir: str | Path = "models"):
        model_dir = Path(model_dir)
        self.binary = joblib.load(model_dir / "tfidf_lr_binary.joblib")
        self.multi = joblib.load(model_dir / "tfidf_lr_multiclass.joblib")

    def predict(self, texts: list[str]) -> list[dict]:
        if not texts:
            return []
        p_dark = self.binary.predict_proba(texts)[:, 1]
        multi_proba = self.multi.predict_proba(texts)
        classes = list(self.multi.classes_)
        out = []
        for i, t in enumerate(texts):
            # best *dark* class from the multiclass model
            order = np.argsort(-multi_proba[i])
            best = next((classes[j] for j in order if classes[j] != NOT_DARK), NOT_DARK)
            rule = rule_label(t)
            out.append({
                "text": t,
                "p_dark": float(p_dark[i]),
                "category": rule if rule != NOT_DARK else best,
                "category_p": float(multi_proba[i][classes.index(best)]) if best in classes else 0.0,
                "rule": rule,
            })
        return out

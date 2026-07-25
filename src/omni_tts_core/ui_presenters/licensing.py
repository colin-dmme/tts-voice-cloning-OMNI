"""License feature gating rules keyed by model id.

Ported from the tkinter controller so both GUIs agree on which license
features a given model requires.
"""

from __future__ import annotations


def required_features_for_model(model_id: str) -> list[str]:
    features = ["tts"]
    if model_id.startswith("vieneu"):
        features.append("vieneu")
    elif model_id.startswith("qwen"):
        features.append("qwen")
    elif model_id.startswith("f5tts"):
        features.append("f5tts")
    return features

from __future__ import annotations


NO_CODEC_LABEL = "Không dùng codec"
NO_CODEC_ID = ""

VIENEU_CODEC_CHOICES: tuple[tuple[str, str], ...] = (
    ("NeuCodec Standard", "neuphonic/neucodec"),
    ("NeuCodec Distill", "neuphonic/distill-neucodec"),
    ("NeuCodec ONNX Fast CPU", "neuphonic/neucodec-onnx-decoder-int8"),
)

ONNX_CODEC_REPO = "neuphonic/neucodec-onnx-decoder-int8"


def codec_choices(include_none: bool = False) -> list[tuple[str, str]]:
    choices = list(VIENEU_CODEC_CHOICES)
    if include_none:
        return [(NO_CODEC_LABEL, NO_CODEC_ID), *choices]
    return choices


def codec_label(codec_repo: str | None) -> str:
    if not codec_repo:
        return NO_CODEC_LABEL
    for label, repo in VIENEU_CODEC_CHOICES:
        if repo == codec_repo:
            return label
    return codec_repo


def valid_codec_repo(codec_repo: str | None) -> str | None:
    if not codec_repo:
        return None
    valid_repos = {repo for _label, repo in VIENEU_CODEC_CHOICES}
    return codec_repo if codec_repo in valid_repos else None

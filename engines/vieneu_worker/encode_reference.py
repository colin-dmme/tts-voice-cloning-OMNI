from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def main() -> None:
    try:
        args = _parse_args()
        payload = json.loads(args.request.read_text(encoding="utf-8-sig"))
        output_path = Path(payload["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        codec_repo = payload.get("codec_repo") or "neuphonic/distill-neucodec"
        codec_device = payload.get("codec_device") or "cpu"
        ref_audio = payload["ref_audio"]

        codec = _load_codec(codec_repo, codec_device)
        codes = codec.encode_code(ref_audio)
        try:
            codes = codes.detach().cpu().numpy()
        except AttributeError:
            codes = np.asarray(codes)
        codes = np.asarray(codes, dtype=np.int32).reshape(-1)
        np.save(str(output_path), codes)
    except Exception as exc:
        raise SystemExit(f"VieNeu encode reference lỗi: {exc}") from exc


def _load_codec(codec_repo: str, codec_device: str):
    from neucodec import DistillNeuCodec, NeuCodec

    if codec_repo == "neuphonic/neucodec":
        codec = NeuCodec.from_pretrained(codec_repo)
    elif codec_repo == "neuphonic/distill-neucodec":
        codec = DistillNeuCodec.from_pretrained(codec_repo)
    else:
        raise ValueError(
            "Profile giọng cho VieNeu Standard/GGUF cần NeuCodec Standard hoặc Distill."
        )
    return codec.eval().to(codec_device)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()

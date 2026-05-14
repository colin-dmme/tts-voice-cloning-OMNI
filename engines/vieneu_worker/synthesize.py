from __future__ import annotations

import argparse
import json
from pathlib import Path


STANDARD_CLONE_CODEC_REPO = "neuphonic/distill-neucodec"
STANDARD_CLONE_CODEC_DEVICE = "cpu"


def main() -> None:
    try:
        args = parse_args()
        payload = json.loads(args.request.read_text(encoding="utf-8-sig"))
        output_path = Path(payload["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        from vieneu import Vieneu

        tts = create_tts(Vieneu, payload)
        audio = synthesize(tts, payload)
        tts.save(audio, str(output_path))
    except Exception as exc:
        raise SystemExit(f"VieNeu worker lỗi: {exc}") from exc


def create_tts(vieneu_factory, payload: dict):
    mode = payload.get("mode", "standard")
    if mode != "standard":
        return vieneu_factory(mode=mode)

    kwargs = {"emotion": payload.get("emotion", "natural")}
    if payload.get("ref_audio"):
        kwargs.update({
            "codec_repo": payload.get("codec_repo") or STANDARD_CLONE_CODEC_REPO,
            "codec_device": payload.get("codec_device") or STANDARD_CLONE_CODEC_DEVICE,
            "backbone_device": payload.get("backbone_device") or "cpu",
        })
    return vieneu_factory(**kwargs)


def synthesize(tts, payload: dict):
    text = payload["text"]
    ref_audio = payload.get("ref_audio")
    ref_text = payload.get("ref_text")
    mode = payload.get("mode", "standard")
    if ref_audio and mode == "turbo":
        voice = tts.encode_reference(ref_audio)
        return tts.infer(text=text, voice=voice)
    if ref_audio and mode == "standard":
        try:
            return tts.infer(text=text, ref_audio=ref_audio, ref_text=ref_text)
        except AttributeError as exc:
            if "encode_code" not in str(exc):
                raise
            raise RuntimeError(
                "VieNeu Standard cần backend codec có encode_code để clone giọng. "
                "Hãy chạy install_vieneu_worker.bat để cài neucodec."
            ) from exc
    if ref_audio:
        return tts.infer(text=text, ref_audio=ref_audio, ref_text=ref_text)
    return tts.infer(text=text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()

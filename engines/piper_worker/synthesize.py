from __future__ import annotations

import argparse
import json
import os
import sys
import wave
from collections import OrderedDict
from pathlib import Path

_MAX_CACHED_VOICES = 3
_VOICE_CACHE: OrderedDict[tuple[str, str], object] = OrderedDict()


def main() -> None:
    try:
        args = _parse_args()
        if args.serve:
            _serve()
            return
        payload = json.loads(args.request.read_text(encoding="utf-8-sig"))
        _synthesize(payload)
    except Exception as exc:
        raise SystemExit(f"Piper worker lỗi: {exc}") from exc


def _synthesize(payload: dict) -> None:
    import numpy as np
    import onnxruntime as ort
    from piper import PiperVoice, SynthesisConfig

    model_path = Path(payload["model_path"])
    config_path = Path(payload["config_path"])
    if not model_path.exists() or not config_path.exists():
        raise FileNotFoundError(
            f"Thiếu package giọng Piper: {model_path.name} / {config_path.name}"
        )
    seed = payload.get("seed")
    seeded = seed not in (None, "")
    if seeded:
        # ONNX Runtime applies this seed while constructing the session. A
        # seeded A/B run therefore uses a fresh session; ordinary random runs
        # keep the fast shared voice cache.
        np.random.seed(int(seed))
        ort.set_seed(int(seed))
    cache_key = (str(model_path.resolve()), str(config_path.resolve()))
    voice = None if seeded else _VOICE_CACHE.get(cache_key)
    if voice is None:
        voice = PiperVoice.load(str(model_path), config_path=str(config_path))
        if not seeded:
            _VOICE_CACHE[cache_key] = voice
            while len(_VOICE_CACHE) > _MAX_CACHED_VOICES:
                _VOICE_CACHE.popitem(last=False)
    else:
        _VOICE_CACHE.move_to_end(cache_key)
    speed = max(0.5, min(1.8, float(payload.get("speed") or 1.0)))
    speaker_id_raw = payload.get("speaker_id")
    speaker_id = int(speaker_id_raw) if speaker_id_raw not in (None, "") else None
    synthesis_config = SynthesisConfig(
        speaker_id=speaker_id,
        length_scale=1.0 / speed,
        noise_scale=max(0.0, min(1.0, float(payload.get("noise_scale", 0.667)))),
        noise_w_scale=max(0.0, min(1.0, float(payload.get("noise_w", 0.8)))),
    )
    for chunk in payload.get("chunks") or []:
        output_path = Path(chunk["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = output_path.with_name(output_path.name + ".part")
        part_path.unlink(missing_ok=True)
        try:
            with wave.open(str(part_path), "wb") as wav_file:
                segments = chunk.get("segments")
                if isinstance(segments, list) and segments:
                    _synthesize_segments(
                        voice,
                        segments,
                        wav_file,
                        synthesis_config,
                        fallback_sentence_pause_ms=max(
                            0, int(payload.get("sentence_pause_ms") or 0)
                        ),
                    )
                else:
                    voice.synthesize_wav(
                        str(chunk["text"]),
                        wav_file,
                        syn_config=synthesis_config,
                    )
            # The final name is published only after Wave_write has closed and
            # patched its header.  Readers therefore never observe a growing
            # production WAV as if it were complete.
            os.replace(str(part_path), str(output_path))
        finally:
            part_path.unlink(missing_ok=True)


def _synthesize_segments(
    voice,
    segments: list[dict],
    wav_file,
    synthesis_config,
    *,
    fallback_sentence_pause_ms: int,
) -> None:
    """Write Piper fragments and exact PCM silence into one valid WAV."""
    first_audio = True
    for segment_index, segment in enumerate(segments):
        audio_chunks = list(
            voice.synthesize(
                str(segment.get("text") or ""),
                syn_config=synthesis_config,
            )
        )
        for audio_index, audio_chunk in enumerate(audio_chunks):
            if first_audio:
                wav_file.setframerate(audio_chunk.sample_rate)
                wav_file.setsampwidth(audio_chunk.sample_width)
                wav_file.setnchannels(audio_chunk.sample_channels)
                first_audio = False
            wav_file.writeframes(audio_chunk.audio_int16_bytes)
            if audio_index < len(audio_chunks) - 1:
                _write_silence(
                    wav_file,
                    audio_chunk,
                    fallback_sentence_pause_ms,
                )
        if audio_chunks and segment_index < len(segments) - 1:
            _write_silence(
                wav_file,
                audio_chunks[-1],
                max(0, int(segment.get("pause_after_ms") or 0)),
            )


def _write_silence(wav_file, audio_chunk, pause_ms: int) -> None:
    if pause_ms <= 0:
        return
    frame_count = int(audio_chunk.sample_rate * pause_ms / 1000)
    wav_file.writeframes(
        bytes(frame_count * audio_chunk.sample_width * audio_chunk.sample_channels)
    )


def _serve() -> None:
    for line in sys.stdin:
        try:
            payload = json.loads(line)
            _synthesize(payload)
            response = {"ok": True}
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path)
    parser.add_argument("--serve", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()

"""Higgs TTS specific authoring, compilation, and remote-voice helpers."""

from omni_tts_core.higgs.script import (
    HiggsScriptAnalysis,
    HiggsScriptIssue,
    compile_higgs_chunks,
    validate_higgs_script,
)

__all__ = [
    "HiggsScriptAnalysis",
    "HiggsScriptIssue",
    "compile_higgs_chunks",
    "validate_higgs_script",
]

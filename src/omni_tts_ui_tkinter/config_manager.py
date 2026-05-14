"""
Configuration manager for the Tkinter TTS app.
Handles loading/saving of settings and window position.
Ported from Qwen3-TTS app and adapted for multi-engine use.
"""

import json
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional

import logging

logger = logging.getLogger(__name__)


@dataclass
class WindowGeometry:
    """Window position and size."""
    x: int = 100
    y: int = 100
    width: int = 1000
    height: int = 850


@dataclass
class AppConfig:
    """Application configuration."""
    # Model settings
    model_id: str = "omnivoice_vietnamese"
    device: str = "cuda:0"

    # Voice settings
    default_language: str = "vi"
    voice_profile_id: str = ""

    # Voice Clone settings
    clone_sample_folder: str = ""  # Folder containing voice+text sample pairs
    clone_sample_name: str = ""  # Selected clone sample filename
    ref_audio_path: str = ""
    ref_text: str = ""

    # Output settings
    input_files: list = field(default_factory=list)
    auto_close: bool = False
    default_speed: float = 1.0  # Speed adjustment (0.5 - 2.0)

    # Generation settings
    sentence_pause_ms: int = 450
    max_chunk_chars: int = 220

    # Trim settings
    trim_enabled: bool = True
    trim_threshold: int = -40  # dB
    trim_min_silence: int = 20  # ms
    trim_padding1: int = 25  # ms
    trim_padding2: int = 100  # ms

    # Column widths for batch file list
    column_widths: dict = field(default_factory=dict)

    # Window geometry
    window: WindowGeometry = field(default_factory=WindowGeometry)


class ConfigManager:
    """Manages application configuration persistence."""

    DEFAULT_CONFIG_FILE = "config/ui_tkinter.json"

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            # Store config relative to project root
            from omni_tts_core.paths import project_path
            config_path = project_path(self.DEFAULT_CONFIG_FILE)

        self.config_path = config_path
        self.config = self._load_config()
        logger.info(f"Config loaded from: {self.config_path}")

    def _load_config(self) -> AppConfig:
        """Load configuration from file."""
        if not self.config_path.exists():
            logger.info("Config file not found, using defaults")
            return AppConfig()

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Parse window geometry
            window_data = data.pop('window', {})
            window = WindowGeometry(**{
                k: v for k, v in window_data.items()
                if k in WindowGeometry.__dataclass_fields__
            })

            # Migrate old keys
            if 'language' in data and 'default_language' not in data:
                data['default_language'] = data.pop('language')
            if 'speed' in data and 'default_speed' not in data:
                data['default_speed'] = data.pop('speed')

            # Filter out unknown keys
            valid_keys = set(AppConfig.__dataclass_fields__.keys()) - {'window'}
            filtered = {k: v for k, v in data.items() if k in valid_keys}

            config = AppConfig(**filtered, window=window)
            logger.debug("Config loaded successfully")
            return config

        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return AppConfig()

    def save(self) -> bool:
        """Save configuration to file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            data = asdict(self.config)

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Config saved to: {self.config_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False

    def update_window_geometry(self, x: int, y: int, width: int, height: int):
        """Update window geometry and save."""
        self.config.window.x = x
        self.config.window.y = y
        self.config.window.width = width
        self.config.window.height = height
        self.save()

    def update_model_settings(self, model_id: str = None):
        """Update model settings and save."""
        if model_id is not None:
            self.config.model_id = model_id
        self.save()

    def update_voice_settings(self, language: str = None, voice_profile_id: str = None):
        """Update voice settings and save."""
        if language is not None:
            self.config.default_language = language
        if voice_profile_id is not None:
            self.config.voice_profile_id = voice_profile_id
        self.save()

    def update_clone_settings(
        self,
        ref_audio_path: str = None,
        ref_text: str = None,
        clone_sample_name: str = None,
        clone_sample_folder: str = None
    ):
        """Update voice clone settings and save."""
        if ref_audio_path is not None:
            self.config.ref_audio_path = ref_audio_path
        if ref_text is not None:
            self.config.ref_text = ref_text
        if clone_sample_name is not None:
            self.config.clone_sample_name = clone_sample_name
        if clone_sample_folder is not None:
            self.config.clone_sample_folder = clone_sample_folder
        self.save()

    def update_input_files(self, file_paths: list):
        """Update input file paths list and save."""
        self.config.input_files = file_paths
        self.save()

    def update_auto_close(self, value: bool):
        """Update auto_close setting and save."""
        self.config.auto_close = value
        self.save()

    def update_trim_settings(
        self,
        enabled: bool = None,
        threshold: int = None,
        min_silence: int = None,
        padding1: int = None,
        padding2: int = None
    ):
        """Update trim settings and save."""
        if enabled is not None:
            self.config.trim_enabled = enabled
        if threshold is not None:
            self.config.trim_threshold = threshold
        if min_silence is not None:
            self.config.trim_min_silence = min_silence
        if padding1 is not None:
            self.config.trim_padding1 = padding1
        if padding2 is not None:
            self.config.trim_padding2 = padding2
        self.save()

from __future__ import annotations

import argparse
import json

from omni_tts_core.user_state import restore_user_state


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore Git-backed Colin TTS user state.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing local profiles and samples.")
    parser.add_argument(
        "--force-settings",
        action="store_true",
        help="Overwrite config/ui_tkinter.json with shared settings from user_state.",
    )
    args = parser.parse_args()
    result = restore_user_state(overwrite=args.force, overwrite_settings=args.force_settings)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

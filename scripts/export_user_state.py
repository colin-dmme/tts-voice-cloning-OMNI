from __future__ import annotations

import json

from omni_tts_core.user_state import export_user_state


def main() -> None:
    result = export_user_state()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

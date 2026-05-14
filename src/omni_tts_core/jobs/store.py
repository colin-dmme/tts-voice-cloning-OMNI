from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel


class JobStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create_job_dir(self) -> tuple[str, Path]:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_id = f"{stamp}_{uuid4().hex[:8]}"
        job_dir = self.root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_id, job_dir

    @staticmethod
    def save_json(path: Path, payload: BaseModel | dict) -> None:
        if isinstance(payload, BaseModel):
            data = payload.model_dump(mode="json")
        else:
            data = payload
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

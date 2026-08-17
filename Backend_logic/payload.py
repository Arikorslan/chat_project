from __future__ import annotations

import base64
import json
import secrets
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAYLOAD_PATH = PROJECT_ROOT / "payload.json"
DEFAULT_STATUS = "enabled"
DEFAULT_SALT_BYTES = 16


def _ensure_payload_file() -> None:
    if not PAYLOAD_PATH.exists():
        create_payload_file(DEFAULT_STATUS)


def load_payload() -> Dict[str, Any]:
    _ensure_payload_file()
    try:
        with PAYLOAD_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {"status": DEFAULT_STATUS}


def save_payload(payload: Dict[str, Any]) -> None:
    payload.setdefault("status", DEFAULT_STATUS)
    if "salt" not in payload:
        payload["salt"] = base64.b64encode(secrets.token_bytes(DEFAULT_SALT_BYTES)).decode("ascii")
    with PAYLOAD_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def create_payload_file(status: str) -> None:
    payload = {
        "status": status,
        "date": str(date.today()),
        "time": time.strftime("%H:%M:%S", time.localtime()),
        "salt": base64.b64encode(secrets.token_bytes(DEFAULT_SALT_BYTES)).decode("ascii"),
    }
    save_payload(payload)


def get_status() -> str:
    payload = load_payload()
    return str(payload.get("status", DEFAULT_STATUS))


def get_salt() -> bytes:
    payload = load_payload()
    salt = payload.get("salt")
    if not salt:
        salt = base64.b64encode(secrets.token_bytes(DEFAULT_SALT_BYTES)).decode("ascii")
        payload["salt"] = salt
        save_payload(payload)
    return base64.b64decode(salt)

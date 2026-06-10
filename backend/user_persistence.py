from __future__ import annotations

import json
from pathlib import Path

from backend.config import ROOT_DIR
from backend.models import Store, User


_USERS_FILE = ROOT_DIR / "config" / "users.json"


def load_registered_users_unlocked(store: Store) -> None:
    try:
        if not _USERS_FILE.exists():
            return
        data = json.loads(_USERS_FILE.read_text(encoding="utf-8"))
        users = data.get("users", data) if isinstance(data, dict) else data
        if not isinstance(users, list):
            return
        changed = False
        for item in users:
            if not isinstance(item, dict):
                continue
            if not item.get("frpc_token"):
                changed = True
            if not item.get("frpc_token_version"):
                changed = True
            if not item.get("frpc_token_rotated_at"):
                changed = True
            user = User.model_validate(item)
            if user.username and user.password_hash:
                store.users[user.uid] = user
        if changed:
            save_registered_users_unlocked(store)
    except Exception:
        return


def save_registered_users_unlocked(store: Store) -> None:
    users = [
        user.model_dump(mode="json")
        for user in sorted(store.users.values(), key=lambda u: u.uid)
        if user.username and user.password_hash
    ]
    _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _USERS_FILE.with_suffix(_USERS_FILE.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps({"users": users}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    tmp_path.replace(_USERS_FILE)

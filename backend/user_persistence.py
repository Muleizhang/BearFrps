"""@file backend/user_persistence.py
@brief 把注册用户、密码哈希、余额和 frpc 令牌保存到本地 JSON 文件。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：json、pathlib、backend.models.User。
  修改记录：2026-06-10，补充 Doxygen 风格文件头和迁移说明。
  历史用户记录可能没有 frpc_token、version 或 rotated_at 字段。
  load_registered_users_unlocked 会通过 User 模型默认值补齐缺失字段，并回写文件。
  这样旧账号在升级后可以直接获得用户级令牌，不需要手工迁移数据库。
  读取和保存都访问 config/users.json。
  函数名带 unlocked，表示调用方必须在 store.lock 内调用，避免并发写文件。
"""

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

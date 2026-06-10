"""@file backend/persist_config.py
@brief 保存和加载管理员配置的可分配公网端口范围。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：json、pathlib、backend.config.ROOT_DIR。
  修改记录：2026-06-10，补充 Doxygen 风格文件头和异常处理说明。
  端口池范围保存在 config/allocatable_range.json，使管理员调整在重启后仍然生效。
  读取失败或文件格式错误时回退默认值，保证课堂演示环境可以继续启动。
  保存时只写 start/end 两个字段，不保存已分配端口，已分配端口仍由 Store 中代理记录决定。
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.config import ROOT_DIR

_PERSIST_FILE = ROOT_DIR / "config" / "allocatable_range.json"


def load_allocatable_range(default_start: int, default_end: int) -> tuple[int, int]:
    try:
        if _PERSIST_FILE.exists():
            data = json.loads(_PERSIST_FILE.read_text(encoding="utf-8"))
            start = int(data.get("start", default_start))
            end = int(data.get("end", default_end))
            if start > end or start < 1 or end > 65535:
                return default_start, default_end
            return start, end
    except Exception:
        pass
    return default_start, default_end


def save_allocatable_range(start: int, end: int) -> None:
    _PERSIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PERSIST_FILE.write_text(
        json.dumps({"start": start, "end": end}), encoding="utf-8"
    )

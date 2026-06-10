"""@file backend/sqlite_persistence.py
@brief 使用 SQLite 持久化用户、连接、TCP 映射和充值日志。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-11
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：sqlite3、json、backend.models。
  运行时仍使用内存 Store，SQLite 负责重启后的完整恢复。
  payload_json 保存完整 Pydantic 模型，普通列用于人工检查和基础查询。
  函数名带 unlocked，表示调用方必须持有 store.lock。
"""

from __future__ import annotations

import sqlite3
from typing import Iterable

from backend.config import ROOT_DIR
from backend.models import Proxy, RechargeLog, Store, User


_DB_FILE = ROOT_DIR / "config" / "bearfrps.db"


def load_store_unlocked(store: Store) -> bool:
    if not _DB_FILE.exists():
        return False
    _ensure_schema()
    loaded = False
    with _connect() as conn:
        for row in conn.execute("SELECT payload_json FROM users ORDER BY uid"):
            user = User.model_validate_json(row["payload_json"])
            store.users[user.uid] = user
            loaded = True
        for row in conn.execute("SELECT payload_json FROM proxies ORDER BY id"):
            proxy = Proxy.model_validate_json(row["payload_json"])
            store.proxies[proxy.id] = proxy
            store.proxy_id_counter = max(store.proxy_id_counter, proxy.id)
            loaded = True
        for row in conn.execute("SELECT payload_json FROM recharge_logs ORDER BY id"):
            log = RechargeLog.model_validate_json(row["payload_json"])
            store.recharge_logs.append(log)
            store.recharge_id_counter = max(store.recharge_id_counter, log.id)
            loaded = True
    return loaded


def save_store_unlocked(store: Store) -> None:
    _ensure_schema()
    with _connect() as conn:
        conn.execute("DELETE FROM tcp_mappings")
        conn.execute("DELETE FROM proxies")
        conn.execute("DELETE FROM recharge_logs")
        conn.execute("DELETE FROM users")
        conn.executemany(
            """
            INSERT INTO users (
                uid, username, balance_mb, total_recharged_mb, frpc_token_version,
                created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [_user_row(user) for user in sorted(store.users.values(), key=lambda item: item.uid)],
        )
        conn.executemany(
            """
            INSERT INTO proxies (
                id, uid, name, proxy_type, status, frps_name, frps_remote_port,
                local_ip, local_port, subdomain, traffic_limit_mb, traffic_used_bytes,
                created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [_proxy_row(proxy) for proxy in sorted(store.proxies.values(), key=lambda item: item.id)],
        )
        mapping_rows = [
            row
            for proxy in sorted(store.proxies.values(), key=lambda item: item.id)
            for row in _tcp_mapping_rows(proxy)
        ]
        conn.executemany(
            """
            INSERT INTO tcp_mappings (
                proxy_id, frps_name, remote_port, local_port, actual_local_port,
                is_online, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            mapping_rows,
        )
        conn.executemany(
            """
            INSERT INTO recharge_logs (id, uid, amount_mb, created_at, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            [_recharge_row(log) for log in sorted(store.recharge_logs, key=lambda item: item.id)],
        )


def _connect() -> sqlite3.Connection:
    _DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_schema() -> None:
    _DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                uid TEXT PRIMARY KEY,
                username TEXT,
                balance_mb INTEGER NOT NULL,
                total_recharged_mb INTEGER NOT NULL,
                frpc_token_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS proxies (
                id INTEGER PRIMARY KEY,
                uid TEXT NOT NULL,
                name TEXT NOT NULL,
                proxy_type TEXT NOT NULL,
                status TEXT NOT NULL,
                frps_name TEXT NOT NULL,
                frps_remote_port INTEGER,
                local_ip TEXT NOT NULL,
                local_port INTEGER NOT NULL,
                subdomain TEXT,
                traffic_limit_mb INTEGER NOT NULL,
                traffic_used_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_proxies_uid ON proxies(uid);
            CREATE INDEX IF NOT EXISTS idx_proxies_subdomain ON proxies(subdomain);

            CREATE TABLE IF NOT EXISTS tcp_mappings (
                proxy_id INTEGER NOT NULL,
                frps_name TEXT NOT NULL,
                remote_port INTEGER NOT NULL,
                local_port INTEGER NOT NULL,
                actual_local_port INTEGER,
                is_online INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (proxy_id, frps_name)
            );

            CREATE INDEX IF NOT EXISTS idx_tcp_mappings_remote_port
                ON tcp_mappings(remote_port);

            CREATE TABLE IF NOT EXISTS recharge_logs (
                id INTEGER PRIMARY KEY,
                uid TEXT NOT NULL,
                amount_mb INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            """
        )


def _user_row(user: User) -> tuple[object, ...]:
    return (
        user.uid,
        user.username,
        user.balance_mb,
        user.total_recharged_mb,
        user.frpc_token_version,
        user.created_at.isoformat(),
        user.model_dump_json(),
    )


def _proxy_row(proxy: Proxy) -> tuple[object, ...]:
    return (
        proxy.id,
        proxy.uid,
        proxy.name,
        proxy.proxy_type.value,
        proxy.status.value,
        proxy.frps_name,
        proxy.frps_remote_port,
        proxy.local_ip,
        proxy.local_port,
        proxy.subdomain,
        proxy.traffic_limit_mb,
        proxy.traffic_used_bytes,
        proxy.created_at.isoformat(),
        proxy.model_dump_json(),
    )


def _tcp_mapping_rows(proxy: Proxy) -> Iterable[tuple[object, ...]]:
    for mapping in proxy.tcp_mappings:
        yield (
            proxy.id,
            mapping.frps_name,
            mapping.remote_port,
            mapping.local_port,
            mapping.actual_local_port,
            1 if mapping.is_online else 0,
            mapping.model_dump_json(),
        )


def _recharge_row(log: RechargeLog) -> tuple[object, ...]:
    return (
        log.id,
        log.uid,
        log.amount_mb,
        log.created_at.isoformat(),
        log.model_dump_json(),
    )

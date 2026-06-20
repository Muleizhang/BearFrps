"""@file backend/sqlite_persistence.py
@brief 使用 SQLite 持久化用户、连接、TCP 映射和充值日志。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-11
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：sqlite3、backend.models。
  运行时仍使用内存 Store，SQLite 负责重启后的完整恢复。
  payload_json 保存完整 Pydantic 模型，普通列用于人工检查和基础查询。
  函数名带 unlocked，表示调用方必须持有 store.lock。
  保存采用全量替换策略，保证 SQLite 镜像与内存 Store 同步。
  表中的 uid、status、remote_port 等普通列不作为模型反序列化来源。
  反序列化只读取 payload_json，避免表结构扩展破坏旧数据恢复。
"""

from __future__ import annotations

import sqlite3
from typing import Iterable

from backend.config import ROOT_DIR
from backend.models import Proxy, RechargeLog, Store, User


_DB_FILE = ROOT_DIR / "config" / "bearfrps.db"


def load_store_unlocked(store: Store) -> bool:
    """@brief 从 SQLite 恢复内存 Store。
    @param store 调用方已持有锁的进程内 Store。
    @return 成功加载至少一类业务数据时返回 True，否则返回 False。
    @note 本函数不会清空现有 Store，调用方应在启动阶段或测试隔离后使用。
    """

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
    """@brief 把当前 Store 全量写入 SQLite。
    @param store 调用方已持有锁的进程内 Store。
    @return 无返回值。
    @note 使用同一事务先删除旧镜像再插入新快照，避免部分表保存新旧混合数据。
    """

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
    """@brief 创建启用 Row 工厂和外键检查的 SQLite 连接。
    @return 可用于 with 语句的 sqlite3.Connection。
    @note 目录会在连接前创建，便于首次启动时直接写入 config/bearfrps.db。
    """

    _DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_schema() -> None:
    """@brief 创建 SQLite 表和索引。
    @return 无返回值。
    @note CREATE TABLE IF NOT EXISTS 只做增量建表，不主动迁移或删除历史字段。
    """

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
    """@brief 把 User 转换为 users 表插入参数。
    @param user 待持久化的注册用户模型。
    @return 与 INSERT INTO users 字段顺序一致的元组。
    """

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
    """@brief 把 Proxy 转换为 proxies 表插入参数。
    @param proxy 待持久化的代理模型。
    @return 与 INSERT INTO proxies 字段顺序一致的元组。
    """

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
    """@brief 生成一个 Proxy 下所有 TCP 映射的插入参数。
    @param proxy 可能包含多个 tcp_mappings 的代理模型。
    @return 可直接传给 executemany 的映射行迭代器。
    """

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
    """@brief 把 RechargeLog 转换为 recharge_logs 表插入参数。
    @param log 待持久化的充值记录。
    @return 与 INSERT INTO recharge_logs 字段顺序一致的元组。
    """

    return (
        log.id,
        log.uid,
        log.amount_mb,
        log.created_at.isoformat(),
        log.model_dump_json(),
    )

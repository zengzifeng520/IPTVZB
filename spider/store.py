#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQLite 存储层（替代原项目的 MySQL，零部署依赖）。"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS stream (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel     TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    url_hash    TEXT    NOT NULL UNIQUE,
    host        TEXT    DEFAULT '',
    source_id   TEXT    DEFAULT '',
    weight      INTEGER DEFAULT 0,
    ok          INTEGER DEFAULT 0,
    width       INTEGER DEFAULT 0,
    height      INTEGER DEFAULT 0,
    fps         REAL    DEFAULT 0,
    speed       INTEGER DEFAULT 0,
    cors        INTEGER DEFAULT 0,
    error       TEXT    DEFAULT '',
    checked_at  TEXT    DEFAULT '',
    first_seen  TEXT    DEFAULT '',
    last_ok     TEXT    DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_stream_channel ON stream(channel);
CREATE INDEX IF NOT EXISTS idx_stream_ok ON stream(ok);

CREATE TABLE IF NOT EXISTS run_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT,
    finished_at TEXT,
    candidates  INTEGER DEFAULT 0,
    probed      INTEGER DEFAULT 0,
    online      INTEGER DEFAULT 0,
    channels    INTEGER DEFAULT 0,
    note        TEXT DEFAULT ''
);
"""


@contextmanager
def connect(db_path: Path | None = None):
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def upsert_streams(rows: list[dict], db_path: Path | None = None) -> int:
    """写入/更新探测结果，按 url_hash 去重。"""
    if not rows:
        return 0
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    sql = """
    INSERT INTO stream (channel, url, url_hash, host, source_id, weight, ok,
                        width, height, fps, speed, cors, error, checked_at,
                        first_seen, last_ok)
    VALUES (:channel, :url, :url_hash, :host, :source_id, :weight, :ok,
            :width, :height, :fps, :speed, :cors, :error, :checked_at,
            :first_seen, :last_ok)
    ON CONFLICT(url_hash) DO UPDATE SET
        channel   = excluded.channel,
        url       = excluded.url,
        host      = excluded.host,
        source_id = excluded.source_id,
        weight    = excluded.weight,
        ok        = excluded.ok,
        width     = excluded.width,
        height    = excluded.height,
        fps       = excluded.fps,
        speed     = excluded.speed,
        cors      = excluded.cors,
        error     = excluded.error,
        checked_at= excluded.checked_at,
        last_ok   = CASE WHEN excluded.ok = 1 THEN excluded.checked_at ELSE stream.last_ok END
    """
    prepared = []
    for r in rows:
        item = dict(r)
        item.setdefault("first_seen", now)
        item.setdefault("last_ok", now if item.get("ok") else "")
        prepared.append(item)
    with connect(db_path) as conn:
        conn.executemany(sql, prepared)
    return len(prepared)


def known_hashes(db_path: Path | None = None) -> dict[str, dict]:
    """返回已探测过的 url_hash -> {ok, checked_at, speed, width, height}，用于增量跳过。"""
    with connect(db_path) as conn:
        cur = conn.execute("SELECT url_hash, ok, checked_at, speed, width, height, fps, cors FROM stream")
        return {r["url_hash"]: dict(r) for r in cur.fetchall()}


def healthy_streams(min_width: int = 0, db_path: Path | None = None) -> list[dict]:
    """取出当前可用的源。"""
    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT * FROM stream WHERE ok = 1 AND width >= ? ORDER BY channel, speed DESC",
            (min_width,),
        )
        return [dict(r) for r in cur.fetchall()]


def log_run(data: dict, db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO run_log (started_at, finished_at, candidates, probed, online, channels, note)
               VALUES (:started_at, :finished_at, :candidates, :probed, :online, :channels, :note)""",
            data,
        )


def prune_stale(days: int = 7, db_path: Path | None = None) -> int:
    """清理长期失效的源。"""
    with connect(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM stream WHERE ok = 0 AND checked_at != '' "
            "AND julianday('now') - julianday(checked_at) > ?",
            (days,),
        )
        return cur.rowcount


def stats(db_path: Path | None = None) -> dict:
    with connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) c FROM stream").fetchone()["c"]
        online = conn.execute("SELECT COUNT(*) c FROM stream WHERE ok=1").fetchone()["c"]
        chans = conn.execute("SELECT COUNT(DISTINCT channel) c FROM stream WHERE ok=1").fetchone()["c"]
        hd = conn.execute("SELECT COUNT(*) c FROM stream WHERE ok=1 AND width>=1280").fetchone()["c"]
        fhd = conn.execute("SELECT COUNT(*) c FROM stream WHERE ok=1 AND width>=1920").fetchone()["c"]
        cors = conn.execute("SELECT COUNT(*) c FROM stream WHERE ok=1 AND cors=1").fetchone()["c"]
    return {
        "total": total,
        "online": online,
        "channels": chans,
        "hd": hd,
        "fhd": fhd,
        "cors": cors,
        "offline": total - online,
    }


if __name__ == "__main__":
    init_db()
    print("数据库初始化完成:", config.DB_PATH)
    print(stats())

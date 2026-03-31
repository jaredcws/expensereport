from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(sql, tuple(params or ()))
            conn.commit()

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self.connect() as conn:
            conn.executemany(sql, rows)
            conn.commit()

    def fetchall(self, sql: str, params: Iterable[Any] | None = None) -> list[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(sql, tuple(params or ()))
            return cur.fetchall()

    def fetchone(self, sql: str, params: Iterable[Any] | None = None) -> sqlite3.Row | None:
        with self.connect() as conn:
            cur = conn.execute(sql, tuple(params or ()))
            return cur.fetchone()

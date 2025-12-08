from __future__ import annotations

import sqlite3
from pathlib import Path

from config.settings import Settings

def get_conn(settings: Settings) -> sqlite3.Connection:
    return sqlite3.connect(settings.db_path)

def init_db(settings: Settings) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")
    with get_conn(settings) as conn:
        conn.executescript(schema_sql)

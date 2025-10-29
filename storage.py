# storage.py
import sqlite3
import json
import os
from typing import List, Optional, Dict, Tuple

DB_PATH = os.getenv("RECO_DB_PATH", "data/recommendations.db")

def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the recommendations SQLite database."""
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event_type TEXT NOT NULL,
            source TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reco_ts ON recommendations(ts DESC);")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reco_type_ts ON recommendations(event_type, ts DESC);"
    )
    conn.commit()
    conn.close()


def store_recommendation(payload: Dict):
    """Insert a new recommendation event into the database."""
    ts = payload.get("timestamp")
    source = payload.get("source", "recommendation-service")
    # Prefer explicit event_type if present; else try to infer from 'input'/'input_metrics'
    event_type = payload.get("event_type")
    if not event_type:
        # for deterministic payloads where we saved input_metrics only
        et = payload.get("input", {}).get("type") or payload.get("input_metrics", {}).get("type")
        event_type = et or payload.get("type", "unknown")

    payload_json = json.dumps(payload)
    conn = _connect()
    conn.execute(
        "INSERT INTO recommendations (ts, event_type, source, payload_json) VALUES (?, ?, ?, ?)",
        (ts, event_type, source, payload_json),
    )
    conn.commit()
    conn.close()


def query_recommendations(
    limit: int = 50,
    since: Optional[str] = None,
    event_type: Optional[str] = None,
) -> List[Dict]:
    """(Non-paginated) Get up to 'limit' recent rows, for quick uses."""
    conn = _connect()
    query = "SELECT * FROM recommendations WHERE 1=1"
    params = []
    if since:
        query += " AND ts >= ?"
        params.append(since)
    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)
    query += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append(
            {
                "timestamp": r["ts"],
                "event_type": r["event_type"],
                "source": r["source"],
                "payload": json.loads(r["payload_json"]),
            }
        )
    return results


def query_recommendations_paginated(
    page: int = 1,
    page_size: int = 50,
    since: Optional[str] = None,
    event_type: Optional[str] = None,
) -> Tuple[List[Dict], int]:
    """
    Returns (items, total) where:
      - items is a list of rows for the requested page
      - total is the total number of rows matching the filter
    """
    offset = (page - 1) * page_size
    conn = _connect()

    # Count first (for total pages)
    count_sql = "SELECT COUNT(*) AS c FROM recommendations WHERE 1=1"
    count_params = []
    if since:
        count_sql += " AND ts >= ?"
        count_params.append(since)
    if event_type:
        count_sql += " AND event_type = ?"
        count_params.append(event_type)
    total = conn.execute(count_sql, count_params).fetchone()["c"]

    # Page query
    data_sql = "SELECT * FROM recommendations WHERE 1=1"
    data_params = []
    if since:
        data_sql += " AND ts >= ?"
        data_params.append(since)
    if event_type:
        data_sql += " AND event_type = ?"
        data_params.append(event_type)
    data_sql += " ORDER BY ts DESC LIMIT ? OFFSET ?"
    data_params.extend([page_size, offset])

    rows = conn.execute(data_sql, data_params).fetchall()
    conn.close()

    items = []
    for r in rows:
        items.append(
            {
                "timestamp": r["ts"],
                "event_type": r["event_type"],
                "source": r["source"],
                "payload": json.loads(r["payload_json"]),
            }
        )
    return items, int(total)

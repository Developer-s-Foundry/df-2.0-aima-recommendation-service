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
            user_id TEXT,
            project_id TEXT,
            payload_json TEXT NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reco_ts ON recommendations(ts DESC);")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reco_type_ts ON recommendations(event_type, ts DESC);"
    )
    # Add indexes for user_id and project_id for efficient filtering
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reco_user_id ON recommendations(user_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reco_project_id ON recommendations(project_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reco_user_project ON recommendations(user_id, project_id);")

    # Migration: Add columns if they don't exist (for existing databases)
    try:
        conn.execute("ALTER TABLE recommendations ADD COLUMN user_id TEXT;")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        conn.execute("ALTER TABLE recommendations ADD COLUMN project_id TEXT;")
    except sqlite3.OperationalError:
        pass  # Column already exists

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

    # Extract user_id and project_id from the payload
    # These can be at the top level or nested in 'input' or 'input_metrics'
    user_id = payload.get("user_id")
    if not user_id:
        user_id = payload.get("input", {}).get("user_id") or payload.get("input_metrics", {}).get("user_id")

    project_id = payload.get("project_id")
    if not project_id:
        project_id = payload.get("input", {}).get("project_id") or payload.get("input_metrics", {}).get("project_id")

    payload_json = json.dumps(payload)
    conn = _connect()
    conn.execute(
        "INSERT INTO recommendations (ts, event_type, source, user_id, project_id, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, event_type, source, user_id, project_id, payload_json),
    )
    conn.commit()
    conn.close()


def query_recommendations(
    limit: int = 50,
    since: Optional[str] = None,
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
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
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
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
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
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
    if user_id:
        count_sql += " AND user_id = ?"
        count_params.append(user_id)
    if project_id:
        count_sql += " AND project_id = ?"
        count_params.append(project_id)
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
    if user_id:
        data_sql += " AND user_id = ?"
        data_params.append(user_id)
    if project_id:
        data_sql += " AND project_id = ?"
        data_params.append(project_id)
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


def get_user_projects(user_id: Optional[str] = None) -> List[Dict]:
    """
    Get a list of all projects that have recommendations for a specific user.
    Returns project_id, count of recommendations, and most recent timestamp.
    """
    conn = _connect()

    query = """
        SELECT
            project_id,
            COUNT(*) as recommendation_count,
            MAX(ts) as latest_timestamp
        FROM recommendations
        WHERE 1=1
    """
    params = []

    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)

    # Only include rows that have a project_id
    query += " AND project_id IS NOT NULL"
    query += " GROUP BY project_id"
    query += " ORDER BY latest_timestamp DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            "project_id": r["project_id"],
            "recommendation_count": r["recommendation_count"],
            "latest_timestamp": r["latest_timestamp"],
        })
    return results

# storage.py
import sqlite3
import json
import os
from typing import List, Optional, Dict

DB_PATH = os.getenv("RECO_DB_PATH", "data/recommendations.db")


def init_db():
    """Initialize the recommendations SQLite database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
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
    event_type = payload.get("input_metrics", {}).get("type") or payload.get("type", "unknown")
    payload_json = json.dumps(payload)

    conn = sqlite3.connect(DB_PATH)
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
    """Retrieve recent recommendations from the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

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

    cur = conn.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    results = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        results.append(
            {
                "timestamp": row["ts"],
                "event_type": row["event_type"],
                "source": row["source"],
                "payload": payload,
            }
        )
    return results

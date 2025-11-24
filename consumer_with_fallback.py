#!/usr/bin/env python3
"""
consumer_with_fallback.py

Behavior:
- Attach a private exclusive queue (server-named) to the configured logs exchange.
- Poll that queue for real messages. If one exists: process -> send to analyze endpoint -> publish reco.
- If the queue is empty: read next event from mock_events.json (persisting cursor), process it similarly.
- Sleep between mock events (default 60s) but poll frequently to detect new live messages.

Configuration through .env:
- RABBIT_URL (default: amqp://guest:guest@localhost:5672/%2F)
- RABBIT_LOG_EXCHANGE (default: logData)
- RABBIT_LOG_EXCHANGE_TYPE (fanout|direct|topic) default fanout
- RABBIT_LOG_BINDINGS (comma separated bindings used for direct/topic) optional
- RABBIT_CREATE_INFRA (1 or 0) default 0
- RECO_ANALYZE_URL (HTTP URL to your analyze endpoint) default http://localhost:8080/recommendations/analyze
- MOCK_FILE (path) default ./mock_events.json
- MOCK_CURSOR_FILE (path) default ./mock_cursor.json
- POLL_INTERVAL (seconds) default 5
- MOCK_INTERVAL (seconds between mock events) default 60
"""

import os
import time
import json
import sys
import traceback
from storage import init_db, store_recommendation
from typing import Any, Dict, List, Optional

import pika
import requests
from dotenv import load_dotenv

# Optional: import your publisher helper if present
try:
    from rabbitmq_publisher import publish_recommendation, RABBIT_URL as PUB_RABBIT_URL, RECO_EXCHANGE, RECO_EXCHANGE_TYPE
except Exception:
    # If rabbitmq_publisher isn't present, we will still publish directly using pika inside this file.
    publish_recommendation = None

load_dotenv()

# ---------- Config ----------
RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@localhost:5672/%2F")
LOG_EXCHANGE = os.getenv("RABBIT_LOG_EXCHANGE", "logData")
LOG_EXCHANGE_TYPE = os.getenv("RABBIT_LOG_EXCHANGE_TYPE", "fanout").lower()
LOG_BINDINGS = os.getenv("RABBIT_LOG_BINDINGS", "").strip()

RABBIT_CREATE_INFRA = os.getenv("RABBIT_CREATE_INFRA", "0") == "1"

RECO_ANALYZE_URL = os.getenv("RECO_ANALYZE_URL", "http://localhost:8080/recommendations/analyze")

MOCK_FILE = os.getenv("MOCK_FILE", "mock_events.json")
MOCK_CURSOR_FILE = os.getenv("MOCK_CURSOR_FILE", "mock_cursor.json")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))         # seconds to poll queue
MOCK_INTERVAL = int(os.getenv("MOCK_INTERVAL", "60"))        # seconds between mock events

# ---------- Helpers ----------
def load_mock_events(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Mock file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    # If file holds { "items": [...] } or similar, try to be flexible
    if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
        return data["items"]
    raise ValueError("Mock file must be a JSON array or an object containing 'items' array.")

def load_cursor(path: str) -> int:
    if not os.path.exists(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
            idx = int(obj.get("index", 0))
            return max(0, idx)
    except Exception:
        return 0

def save_cursor(path: str, idx: int):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"index": idx}, f)

def call_analyze_endpoint(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """POST event to /recommendations/analyze and return JSON response or None."""
    try:
        r = requests.post(RECO_ANALYZE_URL, json=event, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("⚠️ Analyze endpoint call failed:", e)
        return None

def publish_reco_direct(payload: Dict[str, Any]):
    """If rabbitmq_publisher.publish_recommendation exists, use it; otherwise publish directly."""
    if publish_recommendation:
        try:
            publish_recommendation(payload)
            return True
        except Exception as e:
            print("⚠️ publish_recommendation() failed:", e)
            # fallback to direct publish below
    # direct publish
    try:
        params = pika.URLParameters(RABBIT_URL)
        conn = pika.BlockingConnection(params)
        ch = conn.channel()
        # ensure exchange exists (non-destructive if already exists but beware of precondition mismatch)
        try:
            ch.exchange_declare(exchange=RECO_EXCHANGE, exchange_type=RECO_EXCHANGE_TYPE, durable=True)
        except Exception:
            # ignore declare errors; still try to publish
            pass
        body = json.dumps(payload)
        ch.basic_publish(exchange=RECO_EXCHANGE, routing_key="", body=body,
                         properties=pika.BasicProperties(delivery_mode=2))
        conn.close()
        return True
    except Exception as e:
        print("✖️ Direct publish to recommendations failed:", e)
        return False

# ---------- Core processing ----------
def normalize_message_body(body: bytes) -> Dict[str, Any]:
    """Try to parse JSON, otherwise wrap raw payload into a contract object."""
    try:
        raw = body.decode("utf-8")
    except Exception:
        raw = str(body)
    try:
        obj = json.loads(raw)
        return obj
    except Exception:
        # Non-JSON fallback wrapper
        return {
            "type": "unknown.event",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "resource": "unknown",
            "labels": {},
            "metrics": {},
            "raw": raw,
        }

def process_event(event: Dict[str, Any], source: str = "live") -> Dict[str, Any]:
    """
    Process a single event:
    - Send to analyze endpoint
    - If analyze returns result publish it to recommendations exchange
    - Return the analyze result (or fallback info)
    """
    print(f"🔧 Processing event (source={source}) type={event.get('type')}")
    analyze_result = call_analyze_endpoint(event)
    rec_payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "consumer_with_fallback",
        "input_event": event,
        "analyze_result": analyze_result or {"note": "analysis_failed_or_unavailable"}
    }
    print("\n🟦 RECOMMENDATION RESULT:")
    print(json.dumps(rec_payload, indent=4))
    print("🟦 END RECOMMENDATION\n")

    ok = publish_reco_direct(rec_payload)
    if ok:
        print("📤 Published recommendation (via recommendations exchange).")
    else:
        print("⚠️ Failed to publish recommendation.")

    try:
        store_recommendation(rec_payload)
        print("💾 Stored recommendation to DB.")
    except Exception as e:
        print("⚠️ store_recommendation failed:", e)

    return rec_payload

# ---------- Main worker ----------
def worker_loop():
    print("=== consumer_with_fallback starting ===")
    print(f"Broker: {RABBIT_URL}")
    print(f"Logs exchange: {LOG_EXCHANGE} (type={LOG_EXCHANGE_TYPE})")
    print(f"Analyze endpoint: {RECO_ANALYZE_URL}")
    print(f"Mock file: {MOCK_FILE} / cursor: {MOCK_CURSOR_FILE}")
    print("=======================================")

    # Load mock events once
    try:
        mock_events = load_mock_events(MOCK_FILE)
        print(f"Loaded {len(mock_events)} mock events.")
    except Exception as e:
        print("✖️ Failed to load mock events:", e)
        mock_events = []

    mock_index = load_cursor(MOCK_CURSOR_FILE)

    params = pika.URLParameters(RABBIT_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()

    # Ensure exchange exists (we try only; if central broker forbids re-declare with different args, this may fail)
    try:
        if RABBIT_CREATE_INFRA:
            ch.exchange_declare(exchange=LOG_EXCHANGE, exchange_type=LOG_EXCHANGE_TYPE, durable=True)
    except Exception:
        # ignore, maybe exchange already exists with different options
        pass

    # Create private exclusive queue (server named) so we don't steal messages
    q = ch.queue_declare(queue="", exclusive=True)
    private_queue = q.method.queue
    print(f"Using private queue: {private_queue}")

    # Bind according to exchange type
    if LOG_EXCHANGE_TYPE in ("fanout",):
        ch.queue_bind(exchange=LOG_EXCHANGE, queue=private_queue, routing_key="")
    else:
        # for topic/direct, bind each binding key if provided
        if LOG_BINDINGS:
            patterns = [p.strip() for p in LOG_BINDINGS.split(",") if p.strip()]
            for p in patterns:
                ch.queue_bind(exchange=LOG_EXCHANGE, queue=private_queue, routing_key=p)
        else:
            # if no binding provided, attempt a generic bind so you can still receive messages if broker uses empty routing key
            try:
                ch.queue_bind(exchange=LOG_EXCHANGE, queue=private_queue, routing_key="")
            except Exception:
                pass

    print("🔁 Entering main loop. Press Ctrl+C to quit.")
    try:
        while True:
            # 1) Check the private queue for messages (non-blocking)
            method_frame, properties, body = ch.basic_get(queue=private_queue, auto_ack=False)
            if body:
                try:
                    event = normalize_message_body(body)
                    # process
                    result = process_event(event, source="live")
                    # ack the message after successful processing
                    try:
                        ch.basic_ack(delivery_tag=method_frame.delivery_tag)
                    except Exception:
                        pass
                except Exception as e:
                    print("⚠️ Error processing live message:", e)
                    traceback.print_exc()
                    # nack without requeue to avoid poison loops (tune as needed)
                    try:
                        ch.basic_nack(delivery_tag=method_frame.delivery_tag, requeue=False)
                    except Exception:
                        pass
                # Immediately continue to next iteration (check for more live messages)
                continue
            else:
                print(f"🔍 No messages in log queue '{private_queue}'. Using fallback mock data...")

            # 2) No live message -> fallback to mock events if available
            if mock_events:
                if mock_index >= len(mock_events):
                    # Reset to start or stop; here we wrap to start again
                    print("ℹ️ Reached end of mock events, wrapping to start.")
                    mock_index = 0
                    save_cursor(MOCK_CURSOR_FILE, mock_index)

                event = mock_events[mock_index]
                print(f"🧪 Using mock event index={mock_index}")
                try:
                    process_event(event, source="mock")
                except Exception as e:
                    print("⚠️ Error processing mock event:", e)
                    traceback.print_exc()

                mock_index += 1
                save_cursor(MOCK_CURSOR_FILE, mock_index)

                # Wait up to MOCK_INTERVAL seconds but poll queue every POLL_INTERVAL to break early if live messages appear
                waited = 0
                while waited < MOCK_INTERVAL:
                    time.sleep(POLL_INTERVAL)
                    waited += POLL_INTERVAL
                    # quick peek: if queue has something, break early
                    m_frame, _, _ = ch.basic_get(queue=private_queue, auto_ack=False)
                    if m_frame:
                        # put it back by not acking and relying on the message to remain in queue (basic_get doesn't remove until ack)
                        # Note: basic_get removes from queue; because auto_ack=False the message stays unacked and visible to this connection.
                        # To be safe we nack+requeue it so it becomes available to the next loop iteration
                        try:
                            ch.basic_nack(delivery_tag=m_frame.delivery_tag, requeue=True)
                        except Exception:
                            pass
                        print("🔔 Live message detected during mock wait — switching to live processing.")
                        break
                # continue main loop
                continue
            else:
                # No mock events defined; just sleep a bit before polling again
                time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n🛑 Stopping worker (KeyboardInterrupt).")
    except Exception as e:
        print("✖️ Worker crashed:", e)
        traceback.print_exc()
    finally:
        try:
            conn.close()
        except Exception:
            pass
        print("Worker stopped.")

if __name__ == "__main__":
    try:
        init_db()
        print("DB initialized.")
    except Exception as e:
        print("⚠️ init_db() failed:", e)
    worker_loop()

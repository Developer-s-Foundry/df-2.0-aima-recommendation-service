# consumer2.py
import json, os, time, traceback
import pika
from dotenv import load_dotenv

# --- OpenAI client (SDK v1+ recommended) ---
try:
    from openai import OpenAI
except ImportError:
    raise SystemExit("Please install openai: pip install openai")

load_dotenv()

# -----------------------------
# Config
# -----------------------------
RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@localhost:5672/%2F")

LOG_EXCHANGE = os.getenv("RABBIT_LOG_EXCHANGE", "logs")
LOG_EXCHANGE_TYPE = os.getenv("RABBIT_LOG_EXCHANGE_TYPE", "topic").lower()
LOG_QUEUE_LLM = os.getenv("RABBIT_LOG_QUEUE_LLM", "reco.llm.logs")
LOG_BINDINGS = [p.strip() for p in os.getenv("RABBIT_LOG_BINDINGS", "#").split(",") if p.strip()]

RECO_EXCHANGE = os.getenv("RABBIT_RECO_EXCHANGE", "recommendations")
RECO_EXCHANGE_TYPE = os.getenv("RABBIT_RECO_EXCHANGE_TYPE", "topic").lower()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "400"))
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

# Guardrails
MAX_PAYLOAD_CHARS = 12000  # truncate giant messages defensively

# -----------------------------
# OpenAI helper
# -----------------------------
def llm_recommendations(event: dict) -> str:
    """Send the event JSON to OpenAI and get recommendations text back."""
    if not OPENAI_API_KEY:
        return "⚠️ OPENAI_API_KEY not set; cannot generate model-based recommendations."

    client = OpenAI(api_key=OPENAI_API_KEY)

    # Pretty JSON (truncate if huge)
    try:
        pretty = json.dumps(event, indent=2, ensure_ascii=False)
    except Exception:
        pretty = str(event)

    if len(pretty) > MAX_PAYLOAD_CHARS:
        pretty = pretty[:MAX_PAYLOAD_CHARS] + "\n... [truncated]"

    system_msg = (
        "You are an SRE/Observability assistant. "
        "Given a JSON event with metrics/logs, produce concise, actionable recommendations. "
        "Focus on severity, key signals, likely causes, and next steps. "
        "If required metrics are missing, say what is missing and what to collect next. "
        "Be specific but brief; avoid guessing beyond the provided data."
    )

    user_msg = (
        "Event JSON follows. Analyze it and respond in this format:\n"
        "Severity: <LOW|MODERATE|HIGH|CRITICAL>\n"
        "Signals: • <bullet 1>\n"
        "         • <bullet 2>\n"
        "Recommendations:\n"
        "1) <step 1>\n"
        "2) <step 2>\n"
        "3) <step 3>\n\n"
        "JSON:\n" + pretty
    )

    # Use chat.completions for broad compatibility
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=OPENAI_TEMPERATURE,
        max_tokens=OPENAI_MAX_TOKENS,
    )

    text = resp.choices[0].message.content.strip()
    return text

# -----------------------------
# RabbitMQ provisioning helpers
# -----------------------------
def ensure_exchange(ch, name: str, ex_type: str):
    ch.exchange_declare(exchange=name, exchange_type=ex_type, durable=True)

def ensure_queue(ch, name: str):
    ch.queue_declare(queue=name, durable=True)

def bind_queue(ch, exchange: str, queue: str, key: str = ""):
    ch.queue_bind(exchange=exchange, queue=queue, routing_key=key)

def provision_infrastructure():
    params = pika.URLParameters(RABBIT_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    # Input side (logs)
    ensure_exchange(ch, LOG_EXCHANGE, LOG_EXCHANGE_TYPE)
    ensure_queue(ch, LOG_QUEUE_LLM)
    if LOG_EXCHANGE_TYPE == "topic":
        for key in LOG_BINDINGS:
            bind_queue(ch, LOG_EXCHANGE, LOG_QUEUE_LLM, key)
    else:
        bind_queue(ch, LOG_EXCHANGE, LOG_QUEUE_LLM, "")
    # Output side (recommendations)
    ensure_exchange(ch, RECO_EXCHANGE, RECO_EXCHANGE_TYPE)
    conn.close()

# -----------------------------
# Publisher to recommendations
# -----------------------------
def publish_recommendation(payload: dict):
    params = pika.URLParameters(RABBIT_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.exchange_declare(exchange=RECO_EXCHANGE, exchange_type=RECO_EXCHANGE_TYPE, durable=True)
    routing_key = payload.get("event_type", "reco.llm") if RECO_EXCHANGE_TYPE == "topic" else ""
    ch.basic_publish(
        exchange=RECO_EXCHANGE,
        routing_key=routing_key,
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2),
    )
    conn.close()
    print(f"📤 LLM Recommendation → exchange='{RECO_EXCHANGE}' key='{routing_key}'")

# -----------------------------
# Consumer callback
# -----------------------------
def process_message(ch, method, properties, body):
    try:
        raw = body.decode("utf-8", errors="replace")
        try:
            event = json.loads(raw)
        except Exception:
            # Not valid JSON; wrap as text event
            event = {"type": "unknown.event", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     "resource": "unknown", "labels": {}, "metrics": {}, "raw": raw}

        # Create LLM-based recommendations
        reco_text = llm_recommendations(event)

        payload = {
            "timestamp": event.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            "source": "recommendation-service-llm",
            "event_type": event.get("type", "unknown.event"),
            "input": event,
            "llm_model": OPENAI_MODEL,
            "recommendations_text": reco_text,
        }
        publish_recommendation(payload)

        # Logging
        et = payload["event_type"]
        print(f"\n🧠 [{et}] → LLM recommendations published.")
        print(reco_text)

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print("⚠️ LLM consumer failed:", repr(e))
        traceback.print_exc()
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

# -----------------------------
# Start
# -----------------------------
def start_consumer():
    # Provision infra (safe/idempotent)
    try:
        provision_infrastructure()
        print("🔧 RabbitMQ infra ensured (exchanges/queues/bindings).")
    except Exception as e:
        print("❌ Infra setup error:", e)

    params = pika.URLParameters(RABBIT_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.basic_qos(prefetch_count=10)
    ch.basic_consume(queue=LOG_QUEUE_LLM, on_message_callback=process_message, auto_ack=False)

    print("=== Recommendation LLM Consumer Config ===")
    print(f"Broker URL: {RABBIT_URL}")
    print(f"Logs exchange: {LOG_EXCHANGE} (type={LOG_EXCHANGE_TYPE})")
    print(f"LLM queue:     {LOG_QUEUE_LLM} (bindings={','.join(LOG_BINDINGS)})")
    print(f"Reco exchange: {RECO_EXCHANGE} (type={RECO_EXCHANGE_TYPE})")
    print(f"OpenAI model:  {OPENAI_MODEL}")
    print("==========================================")
    print(f"🚀 LLM Consumer listening on queue '{LOG_QUEUE_LLM}'")

    try:
        ch.start_consuming()
    except KeyboardInterrupt:
        print("🛑 Stopped.")
    finally:
        conn.close()

if __name__ == "__main__":
    start_consumer()

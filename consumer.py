# consumer.py
import os
import time
import json
import traceback
import pika
from dotenv import load_dotenv
from storage import init_db, store_recommendation


# Rule packs (deterministic)
from rules.cpu_rules import CPURulePack
from rules.disk_rules import DiskRulePack
from rules.memory_rules import MemoryRulePack
from rules.payment_rules import PaymentAPIRulePack
from rules.system_net_rules import SystemNetRulePack
from rules.error_rate_rules import ServiceErrorRateRulePack
from rules.network_http_rules import NetworkHttpRulePack
from rules.generic_rules import GenericRulePack

# Uniform publisher (topic-aware) used elsewhere in your project
from rabbitmq_publisher import publish_recommendation

# Optional OpenAI (we'll import lazily if key exists)
OPENAI_CLIENT = None

load_dotenv()

# -----------------------------
# Config
# -----------------------------
RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@localhost:5672/%2F")

# INPUT side (logs)
LOG_EXCHANGE = os.getenv("RABBIT_LOG_EXCHANGE", "logs")
LOG_EXCHANGE_TYPE = os.getenv("RABBIT_LOG_EXCHANGE_TYPE", "topic").lower()  # 'topic' or 'fanout'
LOG_QUEUE = os.getenv("RABBIT_LOG_QUEUE", "reco.logs")

# If topic: which routing keys to bind (comma-separated). Defaults cover your current rule packs.
LOG_BINDINGS = os.getenv(
    "RABBIT_LOG_BINDINGS",
    "system.*, api.payment, service.*, net.*"
)

# OUTPUT side (recommendations)
RECO_EXCHANGE = os.getenv("RABBIT_RECO_EXCHANGE", "recommendations")
RECO_EXCHANGE_TYPE = os.getenv("RABBIT_RECO_EXCHANGE_TYPE", "topic").lower()  # 'topic' or 'fanout'

# Optional debug outbox & infra toggle
CREATE_RECO_DEBUG = os.getenv("RABBIT_CREATE_RECO_DEBUG", "1") == "1"
RECO_DEBUG_QUEUE = os.getenv("RABBIT_RECO_DEBUG_QUEUE", "reco.debug")
CREATE_INFRA = os.getenv("RABBIT_CREATE_INFRA", "1") == "1"

# OpenAI config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "400"))
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
MAX_PAYLOAD_CHARS = 12000  # truncate huge JSON defensively

USE_LLM = bool(OPENAI_API_KEY)

# -----------------------------
# Deterministic rule dispatcher
# -----------------------------
SPECIFIC_RULES = [
    CPURulePack(),
    MemoryRulePack(),
    DiskRulePack(),
    SystemNetRulePack(),
    PaymentAPIRulePack(),
    ServiceErrorRateRulePack(),
    NetworkHttpRulePack(),
]
GENERIC_RULE = GenericRulePack()

def evaluate_rules(event: dict):
    """Deterministic (rule-based) recommendations."""
    et = event.get("type")
    recos = []
    for pack in SPECIFIC_RULES:
        if pack.supports(et):
            recos += pack.evaluate(event)
    if not recos:
        recos += GENERIC_RULE.evaluate(event)
    # de-dup while preserving order
    return list(dict.fromkeys(recos))

def normalize_metrics(event: dict) -> dict:
    """Small normalization layer so legacy/alt names don't break rules."""
    m = (event.get("metrics") or {})
    et = event.get("type", "")
    if et in ("system.cpu", "host.cpu"):
        if "usage_pct" not in m and "used_pct" in m:
            m["usage_pct"] = m["used_pct"]
    event["metrics"] = m
    return event

# -----------------------------
# OpenAI helper (LLM mode)
# -----------------------------
def ensure_openai():
    global OPENAI_CLIENT
    if not USE_LLM:
        return
    if OPENAI_CLIENT is None:
        try:
            from openai import OpenAI
        except Exception as e:
            raise RuntimeError("OpenAI SDK missing: pip install openai") from e
        OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY)

def llm_recommendations_text(event: dict) -> str:
    """Send any JSON event to OpenAI and return recommendations as text block."""
    ensure_openai()
    if OPENAI_CLIENT is None:
        return "⚠️ OPENAI_API_KEY not set; cannot generate model-based recommendations."

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

    resp = OPENAI_CLIENT.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=OPENAI_TEMPERATURE,
        max_tokens=OPENAI_MAX_TOKENS,
    )
    return (resp.choices[0].message.content or "").strip()

def parse_recos_from_text(text: str):
    """
    Try to extract a simple list of recommendations from the LLM text, based on numbered lines.
    If nothing clear is found, return an empty list and rely on 'recommendations_text' for display.
    """
    recos = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        # match "1) Do X", "2) Do Y" etc.
        if s[0].isdigit() and (") " in s or ". " in s):
            # strip leading number + punct
            idx = s.find(") ")
            if idx == -1:
                idx = s.find(". ")
            recos.append(s[idx+2:].strip())
    return recos

# -----------------------------
# RabbitMQ provisioning
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

    # INPUT
    ensure_exchange(ch, LOG_EXCHANGE, LOG_EXCHANGE_TYPE)
    ensure_queue(ch, LOG_QUEUE)
    if LOG_EXCHANGE_TYPE == "topic":
        patterns = [p.strip() for p in LOG_BINDINGS.split(",") if p.strip()]
        for p in patterns:
            bind_queue(ch, LOG_EXCHANGE, LOG_QUEUE, p)
    else:
        bind_queue(ch, LOG_EXCHANGE, LOG_QUEUE, "")

    # OUTPUT
    ensure_exchange(ch, RECO_EXCHANGE, RECO_EXCHANGE_TYPE)
    if CREATE_RECO_DEBUG:
        ensure_queue(ch, RECO_DEBUG_QUEUE)
        if RECO_EXCHANGE_TYPE == "topic":
            bind_queue(ch, RECO_EXCHANGE, RECO_DEBUG_QUEUE, "#")
        else:
            bind_queue(ch, RECO_EXCHANGE, RECO_DEBUG_QUEUE, "")

    conn.close()

# -----------------------------
# Message processing
# -----------------------------
def process_message(ch, method, properties, body):
    try:
        raw = body.decode("utf-8", errors="replace")
        try:
            msg = json.loads(raw)
        except Exception:
            # wrap non-JSON for visibility
            msg = {
                "type": "unknown.event",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "resource": "unknown",
                "labels": {},
                "metrics": {},
                "raw": raw,
            }

        msg = normalize_metrics(msg)
        ts = msg.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        et = msg.get("type", "unknown.event")

        # Extract user_id and project_id from the incoming message
        user_id = msg.get("user_id")
        project_id = msg.get("project_id")

        if USE_LLM:
            # LLM path
            reco_text = llm_recommendations_text(msg)
            recos_list = parse_recos_from_text(reco_text)

            payload = {
                "timestamp": ts,
                "source": "recommendation-service-llm",
                "event_type": et,
                "user_id": user_id,
                "project_id": project_id,
                "input": msg,
                "llm_model": OPENAI_MODEL,
                "recommendations_text": reco_text,
                "recommendations": recos_list,  # may be empty if parsing didn't find numbered lines
            }

            publish_recommendation(payload)
            store_recommendation(payload)
            print(f"\n🧠 [{et}] [user:{user_id}] [proj:{project_id}] → LLM recommendations published.")
            print(reco_text or "(empty LLM response)")
        else:
            # Deterministic rule path
            recos = evaluate_rules(msg)

            payload = {
                "timestamp": ts,
                "source": "recommendation-service",
                "event_type": et,
                "user_id": user_id,
                "project_id": project_id,
                "input_metrics": msg.get("metrics", {}),
                "recommendations": recos,
            }

            publish_recommendation(payload)
            store_recommendation(payload)
            print(f"\n🕒 {ts} | [user:{user_id}] [proj:{project_id}] processed event [{et}] → {len(recos)} recommendation(s):")
            for r in recos:
                print("   →", r)

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print("⚠️ Failed to process message:", repr(e))
        traceback.print_exc()
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

# -----------------------------
# Start
# -----------------------------
def start_consumer():
    # Provision infra once (idempotent)
    if CREATE_INFRA:
        try:
            provision_infrastructure()
            print("🔧 RabbitMQ infrastructure ensured (exchanges/queues/bindings).")
        except Exception as e:
            print("❌ Infrastructure setup error:", e)

    params = pika.URLParameters(RABBIT_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.basic_qos(prefetch_count=20)
    ch.basic_consume(queue=LOG_QUEUE, on_message_callback=process_message, auto_ack=False)

    mode = "LLM (OpenAI)" if USE_LLM else "Deterministic Rules"
    print("========== Recommendation Consumer Config ==========")
    print(f"Mode: {mode}")
    print(f"Broker URL: {RABBIT_URL}")
    print(f"Logs exchange: {LOG_EXCHANGE} (type={LOG_EXCHANGE_TYPE})")
    print(f"Logs queue:    {LOG_QUEUE} (bindings={LOG_BINDINGS})")
    print(f"Reco exchange: {RECO_EXCHANGE} (type={RECO_EXCHANGE_TYPE})")
    if USE_LLM:
        print(f"OpenAI model:  {OPENAI_MODEL}")
    if CREATE_RECO_DEBUG:
        print(f"Reco debug queue: {RECO_DEBUG_QUEUE} (bound to '{RECO_EXCHANGE}')")
    print("=========================================================================")
    print(f"🚀 Recommendation Consumer listening on queue '{LOG_QUEUE}'")

    try:
        ch.start_consuming()
    except KeyboardInterrupt:
        print("🛑 Stopped.")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    start_consumer()

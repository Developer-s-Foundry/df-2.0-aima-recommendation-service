# # consumer.py for Local pc RabbitMQ
# import json, os, time
# import pika
# from dotenv import load_dotenv
# from rabbitmq_publisher import publish_recommendation

# # Import rule packs
# from rules.cpu_rules import CPURulePack
# from rules.payment_rules import PaymentAPIRulePack
# from rules.error_rate_rules import ServiceErrorRateRulePack
# from rules.network_http_rules import NetworkHttpRulePack
# from rules.generic_rules import GenericRulePack

# load_dotenv()

# # RabbitMQ settings
# RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@localhost:5672/%2F")
# LOG_EXCHANGE = os.getenv("RABBIT_LOG_EXCHANGE", "logs")
# LOG_QUEUE = os.getenv("RABBIT_LOG_QUEUE", "reco.logs")  # durable queue bound to logs exchange

# #LOG_EXCHANGE_TYPE = os.getenv("RABBIT_LOG_EXCHANGE_TYPE", "fanout").lower()

# # Register all rule packs here
# SPECIFIC_RULES = [
#     CPURulePack(),
#     PaymentAPIRulePack(),
#     ServiceErrorRateRulePack(),
#     NetworkHttpRulePack(),
# ]
# GENERIC_RULE = GenericRulePack()


# def evaluate_event(event: dict):
#     """Dispatch event to the appropriate rule packs."""
#     et = event.get("type")
#     recos = []

#     # run only specific packs that support the event type
#     for pack in SPECIFIC_RULES:
#         if pack.supports(et):
#             recos += pack.evaluate(event)

#     # only if nothing specific produced a recommendation, fall back
#     if not recos:
#         recos += GENERIC_RULE.evaluate(event)

#     # de-dup, preserve order
#     return list(dict.fromkeys(recos))

# def normalize_metrics(event: dict) -> dict:
#     """
#     Normalizes legacy metric names or formats for backward compatibility.
#     e.g., maps used_pct → usage_pct for CPU events.
#     """
#     m = event.get("metrics", {}) or {}
#     et = event.get("type", "")

#     # Normalize CPU metrics
#     if et in ("system.cpu", "host.cpu"):
#         if "usage_pct" not in m and "used_pct" in m:
#             m["usage_pct"] = m["used_pct"]

#     event["metrics"] = m
#     return event


# def process_message(ch, method, properties, body):
#     """Process each message from the logs exchange."""
#     try:
#         msg = json.loads(body.decode("utf-8"))
#         msg = normalize_metrics(msg)

#         ts = msg.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%S"))
#         et = msg.get("type", "unknown.event")

#         recos = evaluate_event(msg)

#         payload = {
#             "timestamp": ts,
#             "source": "recommendation-service",
#             "event_type": et,
#             "input_metrics": msg.get("metrics", {}),
#             "recommendations": recos,
#         }

#         # publish to recommendations exchange
#         publish_recommendation(payload)

#         print(f"\n🕒 {ts} | processed event [{et}] → {len(recos)} recommendation(s):")
#         for r in recos:
#             print("   →", r)

#         ch.basic_ack(delivery_tag=method.delivery_tag)

#     except Exception as e:
#         print("⚠️ Failed to process message:", e)
#         ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


# def start_consumer():
#     """Start listening to the RabbitMQ queue for incoming logs."""
#     params = pika.URLParameters(RABBIT_URL)
#     conn = pika.BlockingConnection(params)
#     ch = conn.channel()

#     # Use topic exchange (recommended) — fallback to fanout if needed
#     ch.exchange_declare(exchange=LOG_EXCHANGE, exchange_type="topic", durable=True)
#     ch.queue_declare(queue=LOG_QUEUE, durable=True)
#     # Bind queue to multiple routing keys
#     ch.queue_bind(exchange=LOG_EXCHANGE, queue=LOG_QUEUE, routing_key="system.*")
#     ch.queue_bind(exchange=LOG_EXCHANGE, queue=LOG_QUEUE, routing_key="api.payment")
#     ch.queue_bind(exchange=LOG_EXCHANGE, queue=LOG_QUEUE, routing_key="service.*")
#     ch.queue_bind(exchange=LOG_EXCHANGE, queue=LOG_QUEUE, routing_key="net.*")

#     ch.basic_qos(prefetch_count=50)
#     ch.basic_consume(queue=LOG_QUEUE, on_message_callback=process_message, auto_ack=False)

#     print(f"🚀 Recommendation Consumer listening on queue '{LOG_QUEUE}' bound to exchange '{LOG_EXCHANGE}'")
#     try:
#         ch.start_consuming()
#     except KeyboardInterrupt:
#         print("🛑 Stopped.")
#     finally:
#         conn.close()


# if __name__ == "__main__":
#     start_consumer()


# consumer.py for central Message Broker --RABBITMQ
import json, os, time
import pika
from dotenv import load_dotenv
from rules.cpu_rules import CPURulePack
from rules.generic_rules import GenericRulePack
from rules.payment_rules import PaymentAPIRulePack
from rules.error_rate_rules import ServiceErrorRateRulePack
from rules.network_http_rules import NetworkHttpRulePack
from rabbitmq_publisher import publish_recommendation

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
    "system.* , api.payment , service.* , net.*"
)

# OUTPUT side (recommendations)
RECO_EXCHANGE = os.getenv("RABBIT_RECO_EXCHANGE", "recommendations")
RECO_EXCHANGE_TYPE = os.getenv("RABBIT_RECO_EXCHANGE_TYPE", "topic").lower()  # 'topic' or 'fanout'

# Optional debug queue to see outgoing recos easily
CREATE_RECO_DEBUG = os.getenv("RABBIT_CREATE_RECO_DEBUG", "1") == "1"
RECO_DEBUG_QUEUE = os.getenv("RABBIT_RECO_DEBUG_QUEUE", "reco.debug")

# Gate infra creation with a flag (default ON)
CREATE_INFRA = os.getenv("RABBIT_CREATE_INFRA", "1") == "1"

# -----------------------------
# Rule dispatcher
# -----------------------------
SPECIFIC_RULES = [
    CPURulePack(),
    PaymentAPIRulePack(),
    ServiceErrorRateRulePack(),
    NetworkHttpRulePack(),
]
GENERIC_RULE = GenericRulePack()

def evaluate_event(event: dict):
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
    m = event.get("metrics", {}) or {}
    et = event.get("type", "")
    if et in ("system.cpu", "host.cpu"):
        if "usage_pct" not in m and "used_pct" in m:
            m["usage_pct"] = m["used_pct"]
    event["metrics"] = m
    return event

# -----------------------------
# Provision helpers
# -----------------------------
def ensure_exchange(ch, name: str, ex_type: str):
    """
    Idempotently ensure an exchange exists with the given type.
    If it already exists with a different type, RabbitMQ will 406 (precondition failed).
    We catch it and print a clear message.
    """
    try:
        ch.exchange_declare(exchange=name, exchange_type=ex_type, durable=True)
    except pika.exceptions.ChannelClosedByBroker as e:
        # Reopen channel after 406 and report clearly
        if "inequivalent arg 'type' for exchange" in str(e):
            raise RuntimeError(
                f"Exchange '{name}' exists with a different type. "
                f"Broker mismatch: expected '{ex_type}'. Fix in RabbitMQ UI or align your .env."
            )
        else:
            raise

def ensure_queue(ch, name: str, dead_letter_exchange: str = None):
    args = None
    if dead_letter_exchange:
        args = {"x-dead-letter-exchange": dead_letter_exchange}
    ch.queue_declare(queue=name, durable=True, arguments=args)

def bind_queue(ch, exchange: str, queue: str, key: str = ""):
    ch.queue_bind(exchange=exchange, queue=queue, routing_key=key)

def provision_infrastructure():
    """
    Create exchanges/queues/bindings that the consumer and downstreams rely on.
    Safe to run at every startup (idempotent), except when an exchange already
    exists with a different type — then we print a clear error.
    """
    params = pika.URLParameters(RABBIT_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()

    # INPUT: logs exchange + queue + bindings
    ensure_exchange(ch, LOG_EXCHANGE, LOG_EXCHANGE_TYPE)
    ensure_queue(ch, LOG_QUEUE)

    if LOG_EXCHANGE_TYPE == "topic":
        patterns = [p.strip() for p in LOG_BINDINGS.split(",") if p.strip()]
        for p in patterns:
            bind_queue(ch, LOG_EXCHANGE, LOG_QUEUE, p)
    else:
        # fanout: binding key is ignored
        bind_queue(ch, LOG_EXCHANGE, LOG_QUEUE, "")

    # OUTPUT: recommendations exchange + optional debug queue
    ensure_exchange(ch, RECO_EXCHANGE, RECO_EXCHANGE_TYPE)

    if CREATE_RECO_DEBUG:
        ensure_queue(ch, RECO_DEBUG_QUEUE)
        if RECO_EXCHANGE_TYPE == "topic":
            bind_queue(ch, RECO_EXCHANGE, RECO_DEBUG_QUEUE, "#")  # catch-all
        else:
            bind_queue(ch, RECO_EXCHANGE, RECO_DEBUG_QUEUE, "")

    conn.close()

# -----------------------------
# Consumer callback
# -----------------------------
def process_message(ch, method, properties, body):
    try:
        msg = json.loads(body.decode("utf-8"))
        msg = normalize_metrics(msg)

        ts = msg.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        et = msg.get("type", "unknown.event")

        recos = evaluate_event(msg)

        payload = {
            "timestamp": ts,
            "source": "recommendation-service",
            "event_type": et,
            "input_metrics": msg.get("metrics", {}),
            "recommendations": recos,
        }

        # publish to recommendations exchange
        publish_recommendation(payload)

        print(f"\n🕒 {ts} | processed event [{et}] → {len(recos)} recommendation(s):")
        for r in recos:
            print("   →", r)

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print("⚠️ Failed to process message:", repr(e))
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

# -----------------------------
# Main start
# -----------------------------
def start_consumer():
    # Provision infra once (unless disabled)
    if CREATE_INFRA:
        try:
            provision_infrastructure()
            print("🔧 RabbitMQ infrastructure ensured (exchanges/queues/bindings).")
        except Exception as e:
            print("❌ Infrastructure setup error:", e)
            # You can decide to exit here if infra is critical:
            # raise

    params = pika.URLParameters(RABBIT_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()

    # QoS and consume
    ch.basic_qos(prefetch_count=50)
    ch.basic_consume(queue=LOG_QUEUE, on_message_callback=process_message, auto_ack=False)

    print("=== Recommendation Consumer Config ===")
    print(f"Broker URL: {RABBIT_URL}")
    print(f"Logs exchange: {LOG_EXCHANGE} (type={LOG_EXCHANGE_TYPE})")
    print(f"Logs queue:    {LOG_QUEUE}")
    print(f"Reco exchange: {RECO_EXCHANGE} (type={RECO_EXCHANGE_TYPE})")
    if CREATE_RECO_DEBUG:
        print(f"Reco debug queue: {RECO_DEBUG_QUEUE} (bound to '{RECO_EXCHANGE}')")
    print("======================================")

    print(f"🚀 Recommendation Consumer listening on queue '{LOG_QUEUE}' bound to exchange '{LOG_EXCHANGE}'")
    try:
        ch.start_consuming()
    except KeyboardInterrupt:
        print("🛑 Stopped.")
    finally:
        conn.close()

if __name__ == "__main__":
    start_consumer()

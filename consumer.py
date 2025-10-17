# consumer.py
import json, os, time
import pika
from dotenv import load_dotenv
from reco_rules import analyze_cpu, analyze_memory, analyze_disk
from rabbitmq_publisher import publish_recommendation

load_dotenv()

RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@localhost:5672/%2F")
LOG_EXCHANGE = os.getenv("RABBIT_LOG_EXCHANGE", "logs")
LOG_QUEUE = os.getenv("RABBIT_LOG_QUEUE", "reco.logs")  # durable queue for your team

def process_message(ch, method, properties, body):
    try:
        msg = json.loads(body.decode("utf-8"))
        ts = msg.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%S"))
        metrics = msg.get("metrics", {})

        cpu = metrics.get("cpu")
        mem_total = metrics.get("memory_total_gb")
        mem_free  = metrics.get("memory_free_gb")
        disk_total = metrics.get("disk_total_gb")
        disk_free  = metrics.get("disk_free_gb")

        cpu_recos = analyze_cpu([cpu]) if cpu is not None else []
        mem_recos = analyze_memory(mem_total, mem_free) if (mem_total is not None and mem_free is not None) else []
        disk_recos = analyze_disk(disk_total, disk_free, "C:") if (disk_total is not None and disk_free is not None) else []

        all_recos = cpu_recos + mem_recos + disk_recos

        payload = {
            "timestamp": ts,
            "source": "recommendation-service",
            "input_metrics": metrics,
            "recommendations": all_recos
        }

        # publish to recommendations exchange
        publish_recommendation(payload)

        print(f"\n🕒 {ts} | processed metrics -> recos:")
        print(json.dumps(metrics, indent=2))
        for r in all_recos:
            print("   →", r)

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print("⚠️ Failed to process message:", e)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def start_consumer():
    params = pika.URLParameters(RABBIT_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()

    ch.exchange_declare(exchange=LOG_EXCHANGE, exchange_type="fanout", durable=True)
    ch.queue_declare(queue=LOG_QUEUE, durable=True)
    ch.queue_bind(exchange=LOG_EXCHANGE, queue=LOG_QUEUE)

    ch.basic_qos(prefetch_count=50)
    ch.basic_consume(queue=LOG_QUEUE, on_message_callback=process_message, auto_ack=False)

    print(f"🚀 Recommendation Consumer listening on queue '{LOG_QUEUE}' bound to exchange '{LOG_EXCHANGE}'")
    try:
        ch.start_consuming()
    except KeyboardInterrupt:
        print("🛑 Stopped.")
    finally:
        conn.close()

if __name__ == "__main__":
    start_consumer()
